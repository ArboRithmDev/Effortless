---
titre: Plan action
phase: L-plan
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 002-Story-Adapter-Jira-Concret
code: MET-PLN
document: 07-MET-PLN-plan-action
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/met-pln
---

# 🚀 Plan d'action — Adapter Jira concret (STO-TRACKER-02)

Découpage en tâches d'implémentation, ordonné par dépendances. Chaque tâche est
livrable et testable isolément (suite pytest hermétique via `FakeJiraClient`).

## Task Breakdown

| # | Tâche | Complexité | Dépend de |
|---|---|---|---|
| T1 | Étendre `ObjectPayload` avec `labels: Optional[List[str]]` (additif) + propager dans `NullTracker` (ignore) | simple | — |
| T2 | `ports/adapters/jira_client.py` : `FakeJiraClient` (store mémoire : types/transitions seedés, `create_issue` clé incrémentale, `search` par label) + interface documentée | simple | — |
| T3 | `ports/adapters/jira.py` : `JiraTracker.discover_taxonomy` (mappe types+transitions → `Taxonomy`, ids de type) | complex | T2 |
| T4 | `JiraTracker.create` (résout type_id, câble parent, pose labels, retourne `TrackerRef`) + stubs `transition`/`log_work`/`import` (NotImplementedError/[]) | complex | T1, T3 |
| T5 | `build_jira_tracker(cfg)` + `register_adapter("jira", …)` au chargement du module ports | simple | T4 |
| T6 | `templates/jira_project_scaffold.json` (arbre [PROJET], init depuis IFX-1) + loader | simple | — |
| T7 | `services/scaffolder.py` : `scaffold_project_from_template` (walk DFS, create + parent, idempotence via `scaffold_state`) | complex | T4, T6 |
| T8 | Persistance `scaffold_state` (`.effortless/scaffold_state.json`, zone → refs) | simple | — |
| T9 | `JiraClient` REST réel (Jira Cloud v3, auth token env) — même interface que Fake | complex | T2 |
| T10 | Outils MCP `effortless_tracker_couple` + `effortless_tracker_scaffold` dans `server.py` (couple + discover + scaffold) | complex | T5, T7 |
| T11 | Tests hermétiques : discover, create+parent+label, scaffold 6 nœuds, idempotence, `resolve_tracker→JiraTracker`, non couplé=NullTracker | simple | T7, T10 |
| T12 | Validation end-to-end contre **EFL** (réseau réel, hors pytest) : couple + scaffold + re-run idempotent | complex | T9, T10 |

## Séquencement

1. **Socle agnostique** : T1 → T2 → T3 → T4 → T5 (adapter complet côté contrat,
   testable au Fake).
2. **Scaffold** : T6 → T8 → T7 (composer + template + état local).
3. **Exposition** : T10 (outils MCP) → T11 (tests hermétiques) — barrière qualité.
4. **Réel** : T9 (client REST) → T12 (validation EFL live).

## Notes d'exécution

- Recette : `src\mcp-server\.venv\Scripts\python.exe -m pytest src/mcp-server/tests -q`
  (PYTHONIOENCODING=utf-8). Reste verte à chaque tâche.
- Chaque tâche `complex` est décomposée en sous-tâches `simple` par la boucle
  autonome (`effortless_loop_step` → DECOMPOSE) avant délégation.
- Hook anti-drift : une tâche `Doing` story-scopée requise pour committer.
- T9/T12 (réseau réel) isolés en fin de chaîne — la suite pytest reste hermétique.
- **MCP `effortless` à reconnecter** après les patchs `server.py` (T10).
