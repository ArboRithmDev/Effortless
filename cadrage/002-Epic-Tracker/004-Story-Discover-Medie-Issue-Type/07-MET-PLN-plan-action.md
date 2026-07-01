---
titre: Plan action
phase: L-plan
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 004-Story-Discover-Medie-Issue-Type
code: MET-PLN
document: 07-MET-PLN-plan-action
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/met-pln
---

# 🚀 Plan d'action — Discover médié + issue_type_id (STO-TRACKER-04)

## Task Breakdown

| # | Tâche | Complexité | Dépend de |
|---|---|---|---|
| T1 | `QueueTracker` accepte `taxonomy` (level→id) + stampe `issue_type_id` ; `build_queue_tracker` passe `cfg["taxonomy"]` | simple | — |
| T2 | Outil `effortless_tracker_discover_ack(taxonomy_json)` (persiste settings.tracker.taxonomy) + ligne guide dans `couple` | simple | — |
| T3 | Tests : discover_ack persiste, QueueTracker stampe id, scaffold→ops avec issue_type_id, sans taxo=null, JSON invalide | simple | T1, T2 |
| T4 | Validation live EFL via Rovo : couple→discover(metadata)→discover_ack→scaffold→pending→flush (id auto, sous-tâches sans forçage)→ack | complex | T2, T3 |

## Séquencement
T1 → T2 → T3 (socle + tests verts) → T4 (validation live, zéro token).

## Notes
- Recette : `src\mcp-server\.venv\Scripts\python.exe -m pytest src/mcp-server/tests -q`.
- Rétro-compat : `issue_type_name` conservé. Sans taxonomie → `issue_type_id=null`.
- **MCP à reconnecter** après patch server.py (T2).
