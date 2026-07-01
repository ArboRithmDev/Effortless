---
phase: A-specs
statut: En cours
type: cadrage-story
projet: Effortless
epic: 001-Epic-Projet
story: 001-Story-Story-Defaut-Progression-Projet
code: FNC-SPE
document: 05-FNC-SPE-specifications
tags:
  - cadrage/story
  - cadrage/001-epic-projet
  - cadrage/fnc-spe
---

# 📐 Spécifications fonctionnelles — Modèle Epic/Story/Task & couplage tracker

> Premier jet. Les points marqués **À RATIFIER** attendent une validation de Ben.

## SPEC-1 — Initialisation greenfield

1. `init` propose (sans l'imposer) de coupler un tracker. Réponses : oui / non.
2. Si **oui** : l'agent propose la taxonomie classique **Epic > Story > Task**, ou
   demande l'URL d'un projet existant à analyser pour en épouser la taxonomie.
3. Scaffold automatique de l'**Epic racine `[PROJET]`** + ses Stories méta
   (Pilotage, Cadrage global, Divers). Le cadrage global est lui-même une Story.
4. Le backlog MVP donne N **Epics fonctionnelles** (une par zone `[ZONE]`).
5. Si **non** : même modèle en local, identifiants `TSK-…` de repli.

## SPEC-2 — Initialisation brownfield (ladder N0–N3)

Chaque niveau est un palier stable ; l'utilisateur peut s'arrêter à tout moment.

| Niveau | Déclencheur | Sortie | Code touché |
|--------|-------------|--------|-------------|
| **N0 Observation** | `onboard --observe` | Carte + diagnostic (stack, topologie, smells, clusters, frontières) | aucun |
| **N1 Cadrage** | `onboard --frame` | Epics/Stories dérivées + docs de cadrage + backlog ; import Jira existant (read-mostly) | aucun |
| **N2 Refacto** | `onboard --migrate` | Backlog `[MIGRATION]` + refacto sur branche dédiée | incrémental |
| **N3 Adoption** | `onboard --adopt` | Projet Effortless-natif, projection Jira active | oui |

- L'import Jira (N1) reverse-mappe les issues existantes en contexte sans les
  réécrire (possédées par l'humain).
- La dérivation backlog est **proposée**, l'utilisateur **arbitre** le découpage.

## SPEC-3 — Cycle de vie d'une Story

1. `story_start` ouvre une Story sous une Epic (hérite le tag `[ZONE]`).
2. La Story porte sa propre position **OPALE** (Observer → Execute) et ses docs de
   cadrage Story-scopés.
3. `phase_next` avance l'OPALE **de la Story courante** uniquement.
4. La phase Execute lance l'**autonomous loop** (step machine) sur les tâches.
5. `story_close` clôt la Story (incrément livré).

## SPEC-4 — Tâches & projection tracker

1. `task_add` attache une tâche à la Story courante ; si tracker couplé →
   `createJiraIssue` (Sous-tâche), estimation poussée en **heures**
   (`timeoriginalestimate`). La clé `<CODE>-N` retournée **devient** l'ID de tâche.
2. Changement d'état (Todo/Doing/Done) → `transitionJiraIssue`.
3. **Rapport d'intervention** : à chaque rapport, worklog (temps) + **commentaire**
   sur la Sous-tâche. Cumul remonté à la Story.

## SPEC-5 — Recette & Xray (optionnel)

1. La recette OPALE repose sur tests + anti-drift. La projection **Xray** est
   **optionnelle**, activable par projet (principe validé — amende DEC-06).
2. Si activée : un **Test** par critère d'acceptation, groupés sous un **Test Plan**
   au niveau Story ; exécutions via **Test Execution** par passe de recette
   (cf. 06-TEC-API §Xray).

## SPEC-6 — Migration sans douleur

1. Toute transformation s'exécute sur une **branche dédiée**.
2. Découpage en autant de petites Stories de refacto que nécessaire (strangler-fig),
   chacune gardée par tests + anti-drift.
3. Filet de sécurité (tests de caractérisation) **dimensionné au ROI**.
4. Merge vers la principale **sur arbitrage de l'utilisateur**.
5. Rollback = branche + un commit par Story.

## SPEC-7 — Pattern store

1. À l'identification d'une stack, l'agent propose un pattern cible issu du **store**.
2. Le store est hydraté par **recherche web approfondie** par stack ; enrichissable.
3. `pattern_template` fournit un **gabarit à remplir** pour tout pattern fourni par
   un projet, un framework ou l'utilisateur. Ce gabarit EST le format standard.

## SPEC-8 — Comportements transverses

- **Idempotence** : le re-scan est rejouable ; toute divergence avec le backlog
  existant est exposée pour arbitrage, jamais fusionnée silencieusement.
- **Source de vérité** : Effortless ne pousse/possède que ce qu'il crée.
- **Symbiose vault** : chaque transition de phase synchronise `context.md` + archive.

## Ratification

Specs 1–4 et 6–8 **ratifiées**. SPEC-5 (Xray) **optionnelle** (principe validé).
SPEC-7 : gabarit de descripteur affinable depuis le framework maison de cadrage
technique multiplateforme.
