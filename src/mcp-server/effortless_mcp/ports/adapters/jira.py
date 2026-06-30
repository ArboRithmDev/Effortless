"""Adapter Jira concret (STO-TRACKER-02).

`JiraTracker` satisfait le Protocol `Tracker` en déléguant tout I/O à un client
(`FakeJiraClient` en test, `JiraClient` REST en réel). Périmètre MVP (DEC-02) :
`discover_taxonomy` + `create`. `transition` / `log_work` / `import` sont des
stubs documentés, implémentés dans les stories suivantes du backlog M2.
"""

from __future__ import annotations

import os
from typing import List, Optional

from effortless_mcp.ports.tracker import (
    ImportedObject,
    LocalStatus,
    ObjectPayload,
    ProjectRef,
    Taxonomy,
    TrackerRef,
    register_adapter,
)

# Statut local -> id de statut Jira cible (cycle en V observé sur IFX/EFL).
_STATUS_TARGET = {"Todo": "10079", "Doing": "10066", "Done": "10063"}


class JiraTracker:
    """Adapter Jira. `client` porte la frontière réseau ; `project_key` est le
    projet cible (ex. EFL). `taxonomy` est résolue via `discover_taxonomy`."""

    def __init__(self, client, project_key: str, taxonomy: Optional[Taxonomy] = None):
        self._client = client
        self._project_key = project_key
        self._taxonomy = taxonomy

    # --- discover_taxonomy (TSK-04) ---
    def discover_taxonomy(self, project: ProjectRef) -> Taxonomy:
        """Résout types + transitions réels de l'instance en `Taxonomy`.

        `issue_types` mappe le niveau canonique -> **id** de type Jira
        (epic/story/task ; task ↦ Sous-tâche, DEC-01). `transitions` mappe le
        statut local -> transitionId (résolu dynamiquement, DEC-08)."""
        types = self._client.get_issue_types(self._project_key)
        issue_types = {}
        for level, predicate in (
            # Robuste aux shapes réels : hierarchyLevel parfois absent → repli sur le nom.
            ("epic", lambda t: not t.get("subtask") and (t.get("hierarchyLevel") == 1 or (t.get("name") or "").lower() == "epic")),
            ("story", lambda t: not t.get("subtask") and (t.get("name") or "").lower() == "story"),
            ("task", lambda t: bool(t.get("subtask"))),
        ):
            match = next((t for t in types if predicate(t)), None)
            if match:
                issue_types[level] = match["id"]

        # Transitions : résolues depuis une issue échantillon. Sur un projet neuf
        # (REST, aucune issue) l'appel échoue → on tolère (transitions vides). Les
        # types suffisent au scaffold MVP ; `transition` est post-MVP (DEC-02/08).
        transitions = {}
        try:
            sample = next(iter(getattr(self._client, "issues", {}) or {}), project.project_id)
            raw = self._client.get_transitions(sample)
            for status, target_id in _STATUS_TARGET.items():
                tr = next((t for t in raw if t.get("to_status_id") == target_id), None)
                if tr:
                    transitions[status] = tr["id"]
        except Exception:
            transitions = {}

        self._taxonomy = Taxonomy(issue_types=issue_types, transitions=transitions)
        return self._taxonomy

    # --- create (TSK-05) ---
    def create(self, payload: ObjectPayload) -> TrackerRef:
        """Crée l'issue du niveau demandé. Résout le type via la taxonomie (la
        découvre paresseusement si absente), câble le parent, pose les labels.
        `assignee=None` (DEC-07 : scaffold fidèle, non affecté)."""
        if self._taxonomy is None:
            self.discover_taxonomy(ProjectRef(self._project_key, ""))
        type_id = self._taxonomy.issue_types.get(payload.level)
        if not type_id:
            raise ValueError(f"Niveau '{payload.level}' absent de la taxonomie découverte.")
        parent_key = payload.parent_ref.tracker_id if payload.parent_ref else None
        r = self._client.create_issue(
            project_key=self._project_key,
            issue_type_id=type_id,
            summary=payload.title,
            parent_key=parent_key,
            assignee=None,
            description=payload.description,
            labels=payload.labels,
        )
        return TrackerRef(tracker_id=r["key"], tracker_url=r["url"])

    # --- Hors MVP (stories suivantes M2) ---
    def transition(self, ref: TrackerRef, status: LocalStatus) -> None:
        raise NotImplementedError("JiraTracker.transition — hors MVP (story suivante).")

    def log_work(self, ref: TrackerRef, minutes: int, comment: str) -> None:
        raise NotImplementedError("JiraTracker.log_work — hors MVP (story suivante).")

    def import_tree(self, project: ProjectRef) -> List[ImportedObject]:
        return []


def build_jira_tracker(cfg: dict) -> JiraTracker:
    """Fabrique enregistrée pour le type « jira ». Construit le client REST réel
    (import paresseux : il porte les dépendances/credentials, inutiles tant que le
    projet n'est pas couplé en Jira). Les tests réenregistrent leur propre fabrique
    avec un FakeJiraClient."""
    from effortless_mcp.ports.adapters.jira_client import JiraClient
    # Credentials résolus depuis l'env si absents de la config (jamais en clair dans le repo).
    base_url = cfg.get("base_url") or os.environ.get("JIRA_BASE_URL", "")
    email = cfg.get("email") or os.environ.get("JIRA_EMAIL", "")
    api_token = cfg.get("api_token") or os.environ.get("JIRA_API_TOKEN", "")
    client = JiraClient(base_url, email, api_token)
    return JiraTracker(client, cfg["project_id"])


# Effet de bord d'import : rend le type « jira » résoluble par resolve_tracker.
register_adapter("jira", build_jira_tracker)


# --- Projection médiée agent (STO-TRACKER-03) -------------------------------

# Niveau canonique -> nom de type Jira (passé à createJiraIssue côté agent).
_LEVELMAP = {"epic": "Epic", "story": "Story", "task": "Sous-tâche"}


class QueueTracker:
    """Adapter Jira médié (DEC-01/03 STO-TRACKER-03). `create` n'appelle pas le
    réseau : il **enqueue** une op dans l'outbox (`SyncJournal`) et retourne une
    ref placeholder `local:N`. L'agent (qui a Rovo) flushe puis ack les vraies refs.
    """

    def __init__(self, journal, levelmap: Optional[dict] = None):
        self._journal = journal
        self._levelmap = levelmap or dict(_LEVELMAP)
        self._seq = 0

    def discover_taxonomy(self, project: ProjectRef) -> Taxonomy:
        # Médié agent : la taxonomie est fournie via ack si nécessaire. Vide ici.
        return Taxonomy()

    def create(self, payload: ObjectPayload) -> TrackerRef:
        self._seq += 1
        local_id = f"local:{self._seq}"
        parent_local = payload.parent_ref.tracker_id if payload.parent_ref else None
        self._journal.enqueue("create", {
            "local_id": local_id,
            "level": payload.level,
            "issue_type_name": self._levelmap.get(payload.level, payload.level),
            "title": payload.title,
            "parent_local_id": parent_local,
            "labels": list(payload.labels or []),
        })
        return TrackerRef(tracker_id=local_id, tracker_url="")

    def transition(self, ref: TrackerRef, status: LocalStatus) -> None:
        raise NotImplementedError("QueueTracker.transition — hors MVP (story suivante).")

    def log_work(self, ref: TrackerRef, minutes: int, comment: str) -> None:
        raise NotImplementedError("QueueTracker.log_work — hors MVP (story suivante).")

    def import_tree(self, project: ProjectRef) -> List[ImportedObject]:
        return []


def build_queue_tracker(cfg: dict) -> QueueTracker:
    """Fabrique du type « jira » en mode médié. Le SyncJournal écrit sous la racine
    projet injectée dans la cfg (`__root__`)."""
    from effortless_mcp.ports.sync_journal import SyncJournal
    return QueueTracker(SyncJournal(cfg["__root__"]))


# Mode médié = défaut pour « jira » (override de l'enregistrement REST ci-dessus ;
# l'ancien chemin REST est retiré en TSK-04).
register_adapter("jira", build_queue_tracker)
