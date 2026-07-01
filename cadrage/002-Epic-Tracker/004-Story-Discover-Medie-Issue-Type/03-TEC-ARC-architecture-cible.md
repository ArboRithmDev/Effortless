---
titre: Architecture cible
phase: P-cadrage
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 004-Story-Discover-Medie-Issue-Type
code: TEC-ARC
document: 03-TEC-ARC-architecture-cible
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/tec-arc
---

# 🏗️ Architecture cible — Discover médié + issue_type_id (STO-TRACKER-04)

Incrément sur le modèle médié de STO-TRACKER-03. Le serveur reste planificateur ;
l'agent fournit la taxonomie (level→id) via un ack, le serveur stampe les ops.

## 🧩 Key Components

| Composant | Rôle |
|---|---|
| `server.py::effortless_tracker_discover_ack(taxonomy_json)` | Persiste `settings.tracker.taxonomy = {level: issue_type_id}` (fourni par l'agent après `getJiraProjectIssueTypesMetadata`). |
| `ports/adapters/jira.py::QueueTracker` | Reçoit `taxonomy` (level→id) ; `create` stampe `issue_type_id = taxonomy.get(level)` dans l'op. |
| `ports/adapters/jira.py::build_queue_tracker` | Lit `cfg.get("taxonomy")` (propagé par `resolve_tracker` depuis `settings.tracker`) et le passe à `QueueTracker`. |
| `server.py::effortless_tracker_pending` | Expose `issue_type_id` dans chaque op (déjà générique : flatten des args). |
| `server.py::effortless_tracker_couple` | Message enrichi : invite l'agent à fournir la taxonomie via discover avant scaffold. |

## Flux
```
couple → [agent Rovo getJiraProjectIssueTypesMetadata → {level:id}] → discover_ack
  → scaffold (ops portent issue_type_id) → pending → [agent createJiraIssue id] → ack
```

## Invariants
- Taxonomie absente → `issue_type_id=null`, flush retombe sur le nom (best-effort).
- Aucun I/O réseau serveur. Tests : taxonomie en fixture.
- Rétro-compat : `issue_type_name` conservé dans l'op (lisibilité + fallback).
