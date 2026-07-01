---
type: cadrage-projet
document: 4-evolutions
titre: Effortless — Registre des évolutions
projet: Effortless
statut: vivant
source: .effortless/evolutions.json
maj: 2026-07-01
tags:
  - cadrage/projet
  - cadrage/evolutions
---

# Effortless — Registre des évolutions (document 4)

> Rendu dérivé de `.effortless/evolutions.json` (source de vérité) — ne pas éditer à la main. Découvertes (finding) et besoins issus des échanges.

| Id | Type | Titre | État | Epic | Résolution |
|---|---|---|---|---|---|
| EVO-001 | finding | Pollution de l'outbox par un projet couplé à lui-même | Résolu | — | STO-TRACKER-11 : outbox_status + outbox_purge (discard honnête). Résiduel (décision produit sur le gate d'enqueue dogfood) tracé en PQ-001, gradué en BQO de 002-Epic-Tracker (STO-CADRAGE-06). |
| EVO-002 | finding | Scaffold dupliqué (3 arbres [PROJET]) | Résolu | — | STO-TRACKER-12 : garde confirm_absent, vérification d'absence Jira (label) avant création. |
| EVO-003 | finding | Pas d'outil de clôture Story/Epic ni d'amorçage d'Epic N+1 | Résolu | — | STO-CADRAGE-01 : effortless_epic_start + effortless_story_complete + effortless_epic_complete (106 tests). Reste : les exiger dans la boucle/phase. |
| EVO-004 | besoin | Cadrage projet (documents 0-4 + deux modes d'init) | Résolu | — | EPIC-CADRAGE (003, Done). Documents 0-4 créés en dogfood ; deux modes d'init livrés (STO-CADRAGE-05 : service init_modes agile/v-cycle, param mode). |
| EVO-005 | besoin | Nomenclature des répertoires de cadrage | Résolu | — | STO-CADRAGE-02 : service+outil effortless_migrate_nomenclature (dry-run/apply, phases, robuste). Arbre live migré (001-Epic-Projet/002-Epic-Tracker/003-Epic-Cadrage). Générateurs livrés : epic_start/story_start naissent en nouvelle forme + seq (nomenclature.py). |
| EVO-007 | finding | Migration nomenclature : robustesse (lock Windows + ordre getctime fragile) | Résolu | — | apply en phases (modèle critique / cadrage best-effort), _robust_move (retries + shutil.move), plan priorise un seq explicite avant getctime. seq stampé dans epic.json. Backup avant apply. |
| EVO-006 | besoin | Cadrage prêt pour Obsidian (frontmatter sur tous les docs) | Résolu | — | Docs projet à la racine + frontmatter. Migration frontmatter des docs Story existants faite. STO-CADRAGE-04 : service cadrage_frontmatter — le scaffold génère le frontmatter Obsidian pour les NOUVEAUX docs (init/story_start) + outil de backfill effortless_cadrage_docs_scaffold. |
| EVO-008 | besoin | Config Obsidian embarquée dans le scaffold init | En cours | 005-Epic-Obsidian | — |
| EVO-009 | besoin | Web-UI de suivi augmenté (parcours + stats + projection on-track) | En cours | 006-Epic-Webui | — |
| EVO-010 | finding | Durcissement du process (anti-dérive cadrage, dispatch évolutions, rendu dérivé, validation) | En cours | 004-Epic-Process | — |
| EVO-011 | finding | Nomenclature Story trop pauvre : id dérive du périmètre Epic, pas du sujet de la Story | En cours | 007-Epic-Nomenclature | — |
| EVO-012 | finding | Pas d'outil pour ré-activer une Story/Epic existante | Planifié | — | — |

## Détails

- **EVO-001** — task_add/task_update d'un projet dogfood couplé Jira enqueue des ops jamais flushées (44 accumulées, collisions local:1 pré-fix, transitions malformées pré-fix).
- **EVO-002** — Idempotence reposant sur ScaffoldState local (gitignored, perdu entre sessions) → 3 arbres [PROJET] créés (EFL-1/7/13).
- **EVO-003** — Les stories restaient 'Doing' après livraison du code (05-12), faute d'outil de clôture. Et aucun moyen d'amorcer un Epic N+1 (bootstrap).
- **EVO-004** — Manque la couche de cadrage au-dessus des Epics : MVP, fonctionnel global, technique global, backlog global, registre d'évolutions. Deux modes d'initialisation (agile / cycle en V).
- **EVO-005** — Préfixer les répertoires : <NNN>-Epic-<Périmètre> et <NNN>-Story-<Périmètre> (id = forme, séquence de création) pour l'ordre et le confort de lecture.
- **EVO-007** — Premier apply live échoué : lock transitoire Windows sur un rename de cadrage → état partiel (non transactionnel). Puis un rollback par cp a réécrit les ctimes → getctime a faussé la séquence de création.
- **EVO-006** — Ouvrir cadrage/ comme vault Obsidian. Frontmatter enrichi sur tous les documents de cadrage (projet + Epic/Story). Les 5 documents projet à la racine de cadrage/.
- **EVO-008** — Le scaffold effortless_init ne déploie pas de .obsidian/. Tweaker la config live pour un suivi optimal du cadrage (dashboards Bases+Dataview 6-Suivi.base/6-Suivi-stats.md, enum statut canonique À rédiger→En cours→Rédigé→Validé, graph colorisé) puis l'embarquer (miroir complet cadrage/.obsidian) dans le scaffold init. Normalisation statut (42 docs) déjà appliquée, à régulariser sous cet Epic.
- **EVO-009** — Adapter la Web-UI pour parcourir tout le projet (éléments passés, en cours, à venir) : vue contrôlée et augmentée du suivi d'implémentation, enrichie de statistiques utiles et d'une projection on-track / off-track.
- **EVO-010** — Cause racine de la dérive du 2026-07-01 : travail cadrage/config exécuté hors process (pas d'Epic/Story/task). Défauts : (1) anti-dérive ne couvre que les commits git — cadrage/ gitignored → hook jamais déclenché ; (2) pas de moteur de rendu dérivé → 3-Backlog.md/4-Evolutions.md dérivent du JSON à la main (EVO-007 était absent du md) ; (3) pas d'outils evolution_add/graduate ; (4) pas de gate validation-proposition ni de scaffold anticipé. Parts 2+3+4 (dispatch+render+graduate) livrées en 001-Story-Process ; restent P1 (anti-dérive cadrage) et P3 (validation-proposition).
- **EVO-011** — format_story_id(seq, perimetre) réutilise le périmètre de l'Epic (perimetre_of de la zone) pour toutes ses Stories → 001-Story-Process, 002-Story-Process… indistinguables dans Obsidian. Le slug de Story devrait dériver du TITRE de la Story (sujet propre) : 001-Story-&lt;SujetDeLaStory&gt;. story_start doit slugifier le titre (ou accepter un slug explicite). Concerne aussi TSK-NN (moins critique : tâches hors vault). Migration de l'existant à décider (comme EVO-005/007).
- **EVO-012** — Après story_complete/epic_complete, state.active_story_id reste figé sur la Story clôturée (Done, éventuellement sous un Epic Done). Aucun moyen in-process de basculer l'actif sur une Story existante non terminée pour reprendre le travail (story_start ne fait que CRÉER). Manque effortless_story_activate(story_id[, epic_id]) — même famille que le gap bootstrap EVO-003. Bloque la reprise de la Story P1 (002-Story-Anti-Derive-Etendu-Travail sous 004-Epic-Process).
