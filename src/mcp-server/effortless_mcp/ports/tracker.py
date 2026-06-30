"""Port Tracker — abstraction agnostique (STO-TRACKER-01).

Contrat que le cœur appelle pour projeter le modèle fractal (Project / Epic /
Story / Task) vers un tracker externe, sans rien savoir du tracker concret.

Décisions de référence :
- DEC-01 : 4 niveaux canoniques (Project/Epic/Story/Task ↦ Project/Epic/Story|Task/Sub-Task).
- DEC-03 : Protocol agnostique + NullTracker par défaut.
- DEC-06 : ce module ne contient AUCUNE implémentation concrète (Jira = STO-TRACKER-02).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Literal, Optional, Protocol, runtime_checkable

# Les 4 niveaux canoniques (DEC-01). « task » ↦ Sub-Task ; « story » ↦ Story|Task niv.3.
Level = Literal["project", "epic", "story", "task"]
LocalStatus = Literal["Todo", "Doing", "Done"]


@dataclass(frozen=True)
class TrackerRef:
    """Référence d'un objet distant : clé d'issue + URL absolue (DEC-02)."""
    tracker_id: str
    tracker_url: str


@dataclass(frozen=True)
class ProjectRef:
    """Référence de l'espace projet du tracker (DEC-02)."""
    project_id: str
    project_url: str


@dataclass(frozen=True)
class ObjectPayload:
    """Charge utile pour créer un objet distant à un niveau donné."""
    level: Level
    title: str
    parent_ref: Optional[TrackerRef] = None
    estimate_minutes: Optional[int] = None
    description: Optional[str] = None


@dataclass(frozen=True)
class Taxonomy:
    """Taxonomie réelle découverte sur une instance (DEC-04)."""
    issue_types: Dict[str, str] = field(default_factory=dict)   # level -> nom de type
    transitions: Dict[str, str] = field(default_factory=dict)   # statut local -> id transition
    fields: Dict[str, str] = field(default_factory=dict)        # alias logique -> champ tracker


@dataclass(frozen=True)
class ImportedObject:
    """Objet reverse-mappé lors d'un import read-mostly."""
    level: Level
    ref: TrackerRef
    title: str
    parent_id: Optional[str] = None


@runtime_checkable
class Tracker(Protocol):
    """Contrat agnostique — métier commun aux 4 niveaux (DEC-03).

    Cinq opérations. Une implémentation satisfait ce Protocol par simple
    conformité de signatures (pas d'héritage imposé)."""

    def discover_taxonomy(self, project: ProjectRef) -> Taxonomy: ...
    def create(self, payload: ObjectPayload) -> TrackerRef: ...
    def transition(self, ref: TrackerRef, status: LocalStatus) -> None: ...
    def log_work(self, ref: TrackerRef, minutes: int, comment: str) -> None: ...
    def import_tree(self, project: ProjectRef) -> List[ImportedObject]: ...


class NullTracker:
    """Adapter par défaut : aucun effet de bord, aucun I/O, aucun réseau.

    Comportement nominal hors couplage et double de test (DEC-03)."""

    def discover_taxonomy(self, project: ProjectRef) -> Taxonomy:
        return Taxonomy()

    def create(self, payload: ObjectPayload) -> TrackerRef:
        return TrackerRef(tracker_id="", tracker_url="")

    def transition(self, ref: TrackerRef, status: LocalStatus) -> None:
        return None

    def log_work(self, ref: TrackerRef, minutes: int, comment: str) -> None:
        return None

    def import_tree(self, project: ProjectRef) -> List[ImportedObject]:
        return []


# Registre des adapters concrets. Peuplé par les Stories d'implémentation
# (ex. « jira » en STO-TRACKER-02 via register_adapter). Vide ici → tout type
# retombe sur NullTracker.
_ADAPTERS: Dict[str, Callable[[dict], Tracker]] = {}


def register_adapter(type_name: str, factory: Callable[[dict], Tracker]) -> None:
    """Enregistre une fabrique d'adapter pour un `type` de tracker."""
    _ADAPTERS[type_name] = factory


def resolve_tracker(settings: Optional[dict]) -> Tracker:
    """Résout l'adapter depuis `settings['tracker']['type']`.

    Type absent, vide ou inconnu → `NullTracker` (no-op sûr). Quand un adapter
    concret est enregistré pour ce type, sa fabrique est appelée avec la config
    tracker."""
    cfg = (settings or {}).get("tracker") or {}
    factory = _ADAPTERS.get(cfg.get("type") or "")
    if factory is None:
        return NullTracker()
    return factory(cfg)
