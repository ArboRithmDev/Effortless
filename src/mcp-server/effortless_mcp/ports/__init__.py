"""Ports d'adaptation d'Effortless vers des systèmes externes.

`tracker` expose l'abstraction agnostique de projection vers un tracker
(Jira, …) — contrat `Tracker` (Protocol), `NullTracker` par défaut et la
fabrique `resolve_tracker`. Aucune implémentation concrète ici (DEC-06).
"""

from effortless_mcp.ports.tracker import (
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

__all__ = [
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
]
