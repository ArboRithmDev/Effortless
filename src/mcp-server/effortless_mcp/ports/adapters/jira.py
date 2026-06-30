"""Adapter Jira concret (STO-TRACKER-02).

`JiraTracker` satisfait le Protocol `Tracker` en déléguant tout I/O à un client
(`FakeJiraClient` en test, `JiraClient` REST en réel). Périmètre MVP (DEC-02) :
`discover_taxonomy` + `create`. `transition` / `log_work` / `import` sont des
stubs documentés, implémentés dans les stories suivantes du backlog M2.
"""

from __future__ import annotations

from typing import List, Optional

from effortless_mcp.ports.tracker import (
    ImportedObject,
    LocalStatus,
    ObjectPayload,
    ProjectRef,
    Taxonomy,
    TrackerRef,
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
            ("epic", lambda t: not t.get("subtask") and t.get("hierarchyLevel") == 1),
            ("story", lambda t: not t.get("subtask") and t.get("name", "").lower() == "story"),
            ("task", lambda t: bool(t.get("subtask"))),
        ):
            match = next((t for t in types if predicate(t)), None)
            if match:
                issue_types[level] = match["id"]

        # Transitions : résolues depuis n'importe quelle issue du projet si dispo,
        # sinon depuis le ProjectRef (le client peut renvoyer le schéma projet).
        sample = next(iter(getattr(self._client, "issues", {}) or {}), project.project_id)
        raw = self._client.get_transitions(sample)
        transitions = {}
        for status, target_id in _STATUS_TARGET.items():
            tr = next((t for t in raw if t.get("to_status_id") == target_id), None)
            if tr:
                transitions[status] = tr["id"]

        self._taxonomy = Taxonomy(issue_types=issue_types, transitions=transitions)
        return self._taxonomy

    # --- create (TSK-05) ---
    def create(self, payload: ObjectPayload) -> TrackerRef:
        raise NotImplementedError("JiraTracker.create — implémenté en TSK-05.")

    # --- Hors MVP (stories suivantes M2) ---
    def transition(self, ref: TrackerRef, status: LocalStatus) -> None:
        raise NotImplementedError("JiraTracker.transition — hors MVP (story suivante).")

    def log_work(self, ref: TrackerRef, minutes: int, comment: str) -> None:
        raise NotImplementedError("JiraTracker.log_work — hors MVP (story suivante).")

    def import_tree(self, project: ProjectRef) -> List[ImportedObject]:
        return []
