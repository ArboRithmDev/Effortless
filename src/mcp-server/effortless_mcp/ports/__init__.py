"""Ports d'adaptation d'Effortless vers des systèmes externes.

`tracker` expose l'abstraction agnostique de projection vers un tracker
(Jira, …) — contrat `Tracker` (Protocol), `NullTracker` par défaut et la
fabrique `resolve_tracker`. Aucune implémentation concrète ici (DEC-06).
"""

from effortless_mcp.ports.tracker import (
    ROVO_DISCLAIMER,
    Level,
    LocalStatus,
    TrackerRef,
    ProjectRef,
    ObjectPayload,
    Taxonomy,
    ImportedObject,
    Tracker,
    NullTracker,
    register_adapter,
    resolve_tracker,
)
from effortless_mcp.ports.sync_journal import SyncJournal

# Effet de bord d'import : enregistre les adapters concrets (« jira ») dans le
# registre _ADAPTERS, pour que resolve_tracker les résolve. Importé après tracker
# (register_adapter défini) → pas de cycle.
from effortless_mcp.ports.adapters import jira as _jira_adapter  # noqa: F401,E402

__all__ = [
    "ROVO_DISCLAIMER",
    "Level",
    "LocalStatus",
    "TrackerRef",
    "ProjectRef",
    "ObjectPayload",
    "Taxonomy",
    "ImportedObject",
    "Tracker",
    "NullTracker",
    "register_adapter",
    "resolve_tracker",
    "SyncJournal",
]
