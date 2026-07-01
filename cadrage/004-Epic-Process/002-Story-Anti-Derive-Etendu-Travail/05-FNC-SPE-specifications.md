---
titre: Specifications
phase: A-specs
statut: Rédigé
type: cadrage-story
projet: Effortless
epic: 004-Epic-Process
story: 002-Story-Anti-Derive-Etendu-Travail
code: FNC-SPE
document: 05-FNC-SPE-specifications
tags:
  - cadrage/story
  - cadrage/004-epic-process
  - cadrage/fnc-spe
---

# Anti-dérive étendu au travail cadrage — Spécifications

## Problème (cause racine)

La dérive du 2026-07-01 (travail de cadrage exécuté hors process, sans Epic/Story/task)
n'a jamais été bloquée parce que **deux verrous manquaient** :

1. **`cadrage/` était gitignored** → le hook pre-commit ne voyait aucune édition de
   cadrage (rien à committer, donc rien à valider).
2. **`check_project_drift` ne flague que `src/`** + extensions code (`.py/.js/.ts/.tsx`).
   Même versionné, un changement dans `cadrage/` ne compte pas comme « travail » exigeant
   une tâche `Doing`.

## Exigences

### E1 — Versionner `cadrage/`
`cadrage/` sort du `.gitignore` (fait à la main pour bootstrap). Restent ignorés :
`.effortless/` (état runtime + registres maîtres locaux), `effortless.json` (config
locale), `cadrage/.obsidian/` (config Obsidian personnelle — l'embed curé relève d'EVO-008).

### E2 — Le scaffold gère le `.gitignore` cible
`effortless_init` doit écrire/mettre à jour un bloc `.gitignore` **idempotent** dans le
projet cible :
- **ignore** `.effortless/` (au minimum `loop_state.json`, `scaffold_state.json`,
  `tracker_outbox/`) ;
- **ne versionne PAS** `cadrage/` (aucune entrée `cadrage/` en ignore) ;
- ignore `cadrage/.obsidian/` par défaut.
Bloc délimité par des marqueurs (`# >>> effortless` / `# <<< effortless`) pour rester
idempotent et non destructif du `.gitignore` existant.

### E3 — Élargir la détection de drift à `cadrage/`
`check_project_drift` détecte le drift sur l'**union** :
- fichiers `src/` d'extension code (comportement actuel) ;
- **plus** tout fichier sous `cadrage/` **hors** `cadrage/.obsidian/`.

Règle inchangée : drift = fichiers de travail modifiés **et** zéro tâche `Doing`.

**Rendus dérivés (`3-Backlog.md`, `4-Evolutions.md`, `5-Questions.md`, `1-Stories.md`,
`2-BQO.md`, stubs de phase) :** ils changent lors d'opérations d'outil légitimes. On
**ne les exclut pas** : committer du cadrage (dérivé compris) exige une tâche `Doing`
active — c'est précisément la discipline visée. La régénération se fait toujours pendant
une Story ayant une tâche active ; sinon, l'absence de tâche `Doing` est un signal correct.

## Hors périmètre (autres stories de l'Epic Process)
- Gate **validation-proposition** (P3) — proposer avant d'agir.
- Extension éventuelle du drift aux **registres maîtres** `.effortless/*.json` si on
  décide de les versionner (décision ouverte, non tranchée ici).

## Critères d'acceptation
- `cadrage/` apparaît dans `git status` ; `cadrage/.obsidian/` non.
- Un `effortless_init` sur un repo neuf produit un `.gitignore` conforme à E2 (idempotent).
- `check_project_drift` retourne `is_drifting=True` quand un `.md` de `cadrage/`
  (hors `.obsidian`) est modifié sans tâche `Doing` ; `False` avec une tâche `Doing`.
- Tests hermétiques couvrant E2 (idempotence du bloc) et E3 (union src+cadrage, exclusion
  `.obsidian`).
