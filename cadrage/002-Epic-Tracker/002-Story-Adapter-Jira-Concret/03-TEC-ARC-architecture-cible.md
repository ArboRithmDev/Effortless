---
phase: P-cadrage
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 002-Story-Adapter-Jira-Concret
code: TEC-ARC
document: 03-TEC-ARC-architecture-cible
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/tec-arc
---

# 🏗️ Architecture cible — Adapter Jira concret (STO-TRACKER-02)

## Vue d'ensemble (couches)

```
server.py (task_add / task_update)        ← cœur, appelle le Port via integration.py
        │
        ▼
ports/integration.py  ── resolve_tracker(settings) ──►  Tracker (Protocol, 5 ops)
        │                                                      ▲
        │                                          ┌───────────┴───────────┐
        ▼                                          │                       │
services/scaffolder.py                        NullTracker            JiraTracker (adapter)
 scaffold_project_from_template()             (no-op)                      │
   itère le template → tracker.create()                          JiraClient (REST injecté)
        ▲                                                                  │
        │                                                          Jira Cloud REST v3
   templates/ (config externalisée)
```

## Principe directeur

- Le **Port reste 5 primitives agnostiques** (`create / transition / log_work /
  import / discover_taxonomy`). Aucun ajout.
- Le **scaffold est un service domaine** au-dessus du Port (DEC-01 de cette Story),
  qui n'appelle que `create`. Réutilisable par tout futur adapter.
- L'adapter Jira ne parle JAMAIS aux MCP Atlassian (capacité côté agent, indispo
  dans le process serveur). Il dépend d'un **client REST injecté** → testable
  hors-ligne, réseau isolé derrière une frontière nette.

## 🧩 Key Components

| Module | Rôle |
|---|---|
| `ports/adapters/jira.py` | `JiraTracker(Tracker)` : mappe le modèle fractal vers les types/transitions découverts. Enregistré via `register_adapter("jira", factory)`. |
| `ports/adapters/jira_client.py` | `JiraClient` (REST Jira Cloud v3, auth token) + `FakeJiraClient` pour les tests. Méthodes : `get_issue_types(project)`, `get_transitions(issue)`, `create_issue(payload)`, `search(jql)`, `add_label(issue, label)`. |
| `services/scaffolder.py` | `scaffold_project_from_template(root, tracker, template, zone)` : boucle template → `create` Epic→Stories→Sous-tâches, câble les parents, pose le label idempotent. |
| `templates/jira_project_scaffold.json` | Template `[PROJET]` externalisé (init depuis IFX-1), versionné dans le repo, surchargeable. |

## JiraTracker — réalisation des ops (périmètre MVP)

- **`discover_taxonomy(project)`** → `JiraClient.get_issue_types` +
  `get_transitions`. Construit `Taxonomy` (map type Effortless→id Jira, map
  statut→transitionId). Appelé systématiquement au couplage (ids variables par
  instance — DEC). Propose un mapping si divergence.
- **`create(payload)`** → `JiraClient.create_issue` : pose `issuetype`, `parent`
  (Epic→Story, Story→Sous-tâche), `summary`, `assignee=null`. Retourne
  `TrackerRef(id, url)`, persisté dans l'identité de l'objet local.
- `transition` / `log_work` / `import` : **hors MVP** (no-op ou `NotImplementedError`
  documenté), implémentés dans les stories suivantes du backlog M2.

## Injection du client (clé de testabilité)

```
register_adapter("jira", lambda cfg: JiraTracker(client=build_client(cfg)))
# build_client(cfg) → JiraClient REST (base_url, email, token depuis cfg/env)
# tests → JiraTracker(client=FakeJiraClient(fixtures))   # zéro réseau
```

Frontière : tout I/O réseau est dans `JiraClient`. `JiraTracker` et `scaffolder`
sont purs (logique de mapping + orchestration), testés contre `FakeJiraClient`.

## Composer de scaffold — algorithme

1. Charger le template (JSON externalisé) → arbre typé (Epic, Stories, sous-tâches).
2. Garde idempotence : `JiraClient.search` du label `effortless-scaffold:<zone>`
   dans le projet cible ; si présent → skip (DEC). Sinon, court-circuit local si
   tracker_id déjà persisté.
3. `create` l'Epic racine (label posé), puis chaque Story (`parent`=Epic), puis
   chaque sous-tâche (`parent`=Story). `assignee=null`, pas d'estimation (DEC).
4. Persister les `TrackerRef` retournés dans l'identité locale.

## Mapping Effortless ↦ Jira (référence, résolu dynamiquement à l'exécution)

| Effortless | Jira (IFX/EFL) | id type |
|---|---|---|
| Epic | Epic | 10000 |
| Story | Story | 10007 |
| Task (racine) | Tâche | 10002 |
| Task (enfant) | Sous-tâche | 10095 |

Statuts : `Todo→A faire(10079)` · `Doing→En cours(10066/trans 5)` ·
`Done→Terminé(10063/trans 9)`. **transitionId résolus via `get_transitions`,
jamais codés en dur** (variables par instance).

## Invariants

- Sans couplage (`settings.tracker=None`) → `NullTracker`, zéro I/O (inchangé).
- Échec réseau → outbox `SyncJournal` (acquis STO-01), jamais bloquant pour le cœur.
- Tests hermétiques : aucun appel réseau réel dans la suite pytest.
