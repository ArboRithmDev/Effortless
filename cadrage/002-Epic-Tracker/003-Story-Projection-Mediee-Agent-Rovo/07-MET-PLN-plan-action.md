---
titre: Plan action
phase: L-plan
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 003-Story-Projection-Mediee-Agent-Rovo
code: MET-PLN
document: 07-MET-PLN-plan-action
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/met-pln
---

# 🚀 Plan d'action — Projection médiée agent (STO-TRACKER-03)

Refonte de l'adapter Jira vers le mode médié. Suite pytest hermétique à chaque tâche.

## Task Breakdown

| # | Tâche | Complexité | Dépend de |
|---|---|---|---|
| T1 | Disclaimer Rovo : constante partagée `ROVO_DISCLAIMER` (module ports) | simple | — |
| T2 | `QueueTracker` (create→enqueue, ref `local:N`, stubs) + `build_queue_tracker` ; re-`register_adapter("jira")` | simple | — |
| T3 | `resolve_tracker`/tools injectent `__root__` dans la cfg tracker (SyncJournal sait où écrire) | simple | T2 |
| T4 | Retrait `JiraClient` REST + `build_jira_tracker` + lecture `JIRA_*` + `JiraTracker` REST | simple | T2 |
| T5 | Tool `effortless_tracker_pending` (renvoie ops JSON + disclaimer) | simple | T2, T3 |
| T6 | Tool `effortless_tracker_ack(zone, refs_json)` (persiste refs + ScaffoldState + vide outbox) | simple | T2, T3 |
| T7 | Refonte `effortless_tracker_couple` (sans creds, disclaimer) + `effortless_tracker_scaffold` (enqueue + disclaimer) | simple | T2, T3 |
| T8 | Adapter les tests STO-02 (REST→queue) + nouveaux tests (enqueue, pending, ack, idempotence, non couplé, absence JiraClient) | simple | T4, T5, T6, T7 |
| T9 | Validation live EFL **via Rovo, sans token** : scaffold→pending→createJiraIssue→ack | complex | T7, T8 |

## Séquencement

1. **Socle queue** : T1 → T2 → T3 → T4 (adapter médié + nettoyage REST).
2. **Tools** : T5, T6, T7 (pending/ack/couple/scaffold refondus).
3. **Qualité** : T8 (tests hermétiques verts).
4. **Réel** : T9 (validation Rovo, zéro token).

## Notes d'exécution

- Recette : `src\mcp-server\.venv\Scripts\python.exe -m pytest src/mcp-server/tests -q`.
- T9 : l'agent flushe via Rovo (`createJiraIssue` parent+labels) — déjà validé live.
- `scaffolder.py` et `scaffold_state.py` **inchangés** (réutilisés).
- **MCP `effortless` à reconnecter** après les patchs `server.py` (T5/T6/T7).
- Disclaimer Rovo en tête de chaque sortie de tool tracker.
