---
titre: Analyse
phase: O-analyse
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 002-Story-Adapter-Jira-Concret
code: TEC-ANA
document: 01-TEC-ANA-analyse
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/tec-ana
---

# 🔍 Analyse de l'existant — Adapter Jira concret (STO-TRACKER-02)

## Périmètre de la Story

STO-TRACKER-02 = **rendre le Port Tracker opérant contre Jira** + livrer la
première capacité d'application : **scaffolder un projet** depuis un template.

MVP retenu (slice vertical, prouvé bout-en-bout contre EFL) :
`register_adapter("jira")` + `discover_taxonomy` + `create` + **composer de
scaffold**. Reste repoussé en stories suivantes : `transition`, `log_work`,
`import`, option Xray.

## État du code (acquis STO-TRACKER-01)

- `ports/tracker.py` : types 4 niveaux, `Tracker` Protocol (5 ops primitives :
  `create / transition / log_work / import / discover_taxonomy`), `NullTracker`,
  `resolve_tracker` + registre `register_adapter`. **Point d'extension prêt** :
  aucun adapter concret encore enregistré.
- `ports/integration.py` : `couple_project` / `tracker_project_ref`, projection
  best-effort `project_task_created` / `project_task_transitioned`.
- `ports/sync_journal.py` : `SyncJournal` (outbox rejouable idempotent) pour le mode
  offline.
- Identité `tracker_id` / `tracker_url` portée par Epic / Story / Task.
- `settings.tracker = None` aujourd'hui (projet non couplé → NullTracker, zéro I/O).

## Observation Jira (référence IFX, instance simondialtissus.atlassian.net)

cloudId : `0be82b83-bf18-4056-b095-99c7bd7bac5a` · projet IFX id `10309`,
catégorie **"Projet cycle en V"**.

### Taxonomie des types
| Effortless | Jira | id | hierarchyLevel |
|---|---|---|---|
| Epic | Epic | 10000 | 1 |
| Story | Story | 10007 | 0 |
| Task | Tâche | 10002 | 0 |
| Task (enfant) | **Sous-tâche** | 10095 | -1 |
| — | Bug / Amélioration / Nouvelle fonctionnalité | 10005 / 10001 / 10004 | 0 |
| — | Xray Test / Test Set / Test Plan | 10033 / 10034 / 10035 | 0 |

### Template `[PROJET]` (Epic IFX-1, tout *A faire*, assignee `null`)
```
[PROJET]                                           Epic        IFX-1
├── [PROJET] Pilotage                              Story       IFX-2
├── [PROJET] Analyse et spécifications détaillées  Story       IFX-3
└── [PROJET] Divers (Init, déploiement, doc)       Story       IFX-4
    ├── [PROJET] Déploiement                        Sous-tâche  IFX-5
    └── [PROJET] Documentation                      Sous-tâche  IFX-6
```
Hiérarchie : Epic→Story et Story→Sous-tâche via `parent`. Le préfixe `[PROJET]`
est le marqueur de zone, paramétrable au scaffold.

### Workflow "cycle en V" (transitions réelles, depuis IFX-1)
| statut | id statut | catégorie | transitionId |
|---|---|---|---|
| A faire | 10079 | new | `2` (global) |
| Gestion de projet | 10308 | new | `3` (A gérer) |
| ANALYSE | 10309 | indeterminate | `6` (A analyser) |
| En cours | 10066 | indeterminate | `5` (A réaliser) |
| Terminé | 10063 | done | `9` (Terminé) |
| Annulé(e) | 10312 | done | `12` (Annulé(e)) |

Mapping minimal Effortless ↦ Jira (suffit au MVP, hors périmètre transition mais
consigné) : `Todo→A faire(10079)` · `Doing→En cours(10066/trans 5)` ·
`Done→Terminé(10063/trans 9)`. Les `transitionId` sont **par instance** → toujours
les résoudre via `getTransitionsForJiraIssue`, jamais coder en dur.

## Décision d'architecture candidate (→ P-cadrage)

**Le scaffold n'est PAS une 6e op du Port.** Les 5 ops sont des primitives
atomiques agnostiques ; le scaffold est un **workflow composite** (boucle template
→ N×`create` + câblage parent), lui-même agnostique. Le mettre dans le Port
forcerait chaque futur adapter à redupliquer la boucle. Il vit donc dans un
**service domaine** `scaffold_project_from_template(root, tracker, template)`
au-dessus du Port, qui n'appelle que `create`.

## Gaps / cible

- Aucun adapter Jira concret (registre vide) → à écrire (`JiraTracker`).
- `discover_taxonomy` réel : `getJiraProjectIssueTypesMetadata` +
  `getTransitionsForJiraIssue`. Mapping proposé si divergence (DEC-04 STO-01).
- `create` réel : `createJiraIssue` (type + parent + estimation), retour
  `TrackerRef(id, url)` persisté dans l'identité de l'objet.
- Composer de scaffold + **template config externalisé** (initialisé depuis IFX-1).
- Cible d'écriture des tests propres = **EFL** (vide). IFX = lecture seule.
- Tests hermétiques : adapter testé contre un faux client Jira (fixtures
  taxonomie/refs), zéro réseau ; Jira réel branché en bout de chaîne.

## Risques

- `transitionId` et ids de types **variables par instance/projet** → tout résoudre
  dynamiquement.
- Team-managed vs company-managed : mécanique de `parent` (Epic link) et
  disponibilité des sous-tâches peut différer → à vérifier sur EFL.
- Idempotence du scaffold (re-run) : éviter les doublons d'arbre. Voir BQO.
