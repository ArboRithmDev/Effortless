"""Adapter Jira médié par l'agent (STO-TRACKER-03, DEC-01/03).

Mode médié : `QueueTracker.create` **enqueue** une op dans l'outbox (`SyncJournal`)
au lieu d'appeler le réseau, et retourne une ref placeholder `local:N`. L'agent
(connecteur Rovo MCP) flushe via Rovo puis ack les vraies refs. Aucun credential,
aucun I/O réseau côté serveur. Le chemin REST + token de STO-TRACKER-02 est retiré.
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
    register_adapter,
)

# Niveau canonique -> nom de type Jira (passé à createJiraIssue côté agent).
_LEVELMAP = {"epic": "Epic", "story": "Story", "task": "Sous-tâche"}


class QueueTracker:
    """Adapter Jira médié. `create` enqueue une op et retourne `local:N` ; l'agent
    résout les vraies clés via Rovo puis ack."""

    def __init__(self, journal, levelmap: Optional[dict] = None, taxonomy: Optional[dict] = None):
        self._journal = journal
        self._levelmap = levelmap or dict(_LEVELMAP)
        # taxonomy: {level -> issue_type_id} (médiée, persistée dans settings.tracker.taxonomy).
        # Vide tant que le discover médié n'a pas été acké → issue_type_id=None (fallback nom).
        self._taxonomy = taxonomy or {}
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
            "issue_type_id": self._taxonomy.get(payload.level),  # id autoritaire (None si pas de discover)
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
    """Fabrique du type « jira » (mode médié). Le SyncJournal écrit sous la racine
    projet injectée par `resolve_tracker(..., root)` sous `__root__`. Fallback cwd
    pour les usages où seule la résolution de type importe (ex. is_coupled)."""
    from effortless_mcp.ports.sync_journal import SyncJournal
    # `taxonomy` (level→id) vient de settings.tracker.taxonomy (discover médié, STO-TRACKER-04).
    return QueueTracker(SyncJournal(cfg.get("__root__") or "."), taxonomy=cfg.get("taxonomy") or {})


# Effet de bord d'import : « jira » résoluble en mode médié.
register_adapter("jira", build_queue_tracker)
