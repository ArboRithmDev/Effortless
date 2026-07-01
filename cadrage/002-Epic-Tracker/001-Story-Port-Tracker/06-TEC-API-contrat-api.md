---
titre: Contrat api
phase: A-specs
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 001-Story-Port-Tracker
code: TEC-API
document: 06-TEC-API-contrat-api
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/tec-api
---

# 🔌 Contrat API — Port Tracker (STO-TRACKER-01)

Contrat technique de l'abstraction agnostique. Cible : `effortless_mcp/ports/`
(nouveau package) + champs additifs sur les modèles existants. Réfère DEC-01→06.

## Types de base

```python
from typing import Protocol, Optional, Literal
from dataclasses import dataclass

Level = Literal["project", "epic", "story", "task"]  # 4 niveaux (DEC-01)
LocalStatus = Literal["Todo", "Doing", "Done"]

@dataclass(frozen=True)
class TrackerRef:
    tracker_id: str            # clé d'issue (ex. IFX-42)
    tracker_url: str           # URL absolue de l'objet distant

@dataclass(frozen=True)
class ProjectRef:
    project_id: str            # id/clé de l'espace projet
    project_url: str

@dataclass(frozen=True)
class ObjectPayload:
    level: Level
    title: str
    parent_ref: Optional[TrackerRef]   # None pour epic sous projet
    estimate_minutes: Optional[int] = None
    description: Optional[str] = None

@dataclass(frozen=True)
class Taxonomy:
    issue_types: dict[Level, str]              # level -> nom de type tracker
    transitions: dict[LocalStatus, str]        # statut local -> id transition
    fields: dict[str, str]                     # alias logique -> champ tracker

@dataclass(frozen=True)
class ImportedObject:
    level: Level
    ref: TrackerRef
    title: str
    parent_id: Optional[str]
```

## Contrat `Tracker` (Protocol — DEC-03)

```python
class Tracker(Protocol):
    def discover_taxonomy(self, project: ProjectRef) -> Taxonomy: ...
    def create(self, payload: ObjectPayload) -> TrackerRef: ...
    def transition(self, ref: TrackerRef, status: LocalStatus) -> None: ...
    def log_work(self, ref: TrackerRef, minutes: int, comment: str) -> None: ...
    def import_tree(self, project: ProjectRef) -> list[ImportedObject]: ...
```

- Métier commun aux 4 niveaux : `create` discrimine via `payload.level`.
- Toute implémentation satisfaisant ces signatures convient (pas d'héritage).

## `NullTracker` (adapter par défaut)

```python
class NullTracker:
    def discover_taxonomy(self, project): return Taxonomy({}, {}, {})
    def create(self, payload): return TrackerRef("", "")
    def transition(self, ref, status): return None
    def log_work(self, ref, minutes, comment): return None
    def import_tree(self, project): return []
```

- Aucun effet de bord, aucun appel réseau. Double de test et comportement nominal
  hors couplage.

## Fabrique

```python
def resolve_tracker(settings: dict) -> Tracker:
    """Lit settings['tracker']; instancie l'adapter par 'type' ou NullTracker."""
```

- `type` absent ou inconnu → `NullTracker`.
- `type == "jira"` → adapter Jira (STO-TRACKER-02 ; orchestré côté agent via MCP).

## Schéma de configuration (`effortless.json`)

```json
"settings": {
  "tracker": {
    "type": "jira",
    "project_id": "IFX",
    "project_url": "https://simondialtissus.atlassian.net/browse/IFX"
  }
}
```

- `tracker` absent → projet non couplé (NullTracker).

## Champs additifs sur les entités (DEC-02)

Ajoutés à `models/epic.py`, `story.py`, `task.py` — non optionnels dans le schéma,
valeur vide tant que non couplé :

```python
tracker_id: str = ""    # clé d'issue distante
tracker_url: str = ""   # URL absolue distante
```

- Règle d'identité : quand couplé, `tracker_id` == ID canonique Effortless.

## Journal de synchronisation (outbox — DEC-05)

Répertoire `.effortless/tracker_outbox/`, un fichier JSON par migration, ordonné
par séquence :

```json
{
  "seq": 1,
  "op": "create | transition | log_work",
  "args": { "...": "..." },
  "created_at": "2026-06-30T19:00:00Z",
  "played": false,
  "played_at": null
}
```

- À la reconnexion, les entrées `played == false` sont rejouées par `seq` croissant,
  puis `played = true` + `played_at = <timestamp>`. Rejeu idempotent.

## Modèle d'erreur

- Échec réseau / tracker injoignable → l'appel local n'échoue pas ; une migration
  outbox est créée (best-effort différé).
- Erreur de conformité (payload invalide) → exception levée à l'appelant (fail-fast
  applicatif, distinct de l'indisponibilité réseau).
