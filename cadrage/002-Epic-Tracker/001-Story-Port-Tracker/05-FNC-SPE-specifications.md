---
titre: Specifications
phase: A-specs
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 001-Story-Port-Tracker
code: FNC-SPE
document: 05-FNC-SPE-specifications
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/fnc-spe
---

# 📐 Spécifications fonctionnelles — Port Tracker (STO-TRACKER-01)

Périmètre : l'**abstraction agnostique** (contrat + NullTracker + modèle
d'identité + journal offline). L'implémentation Jira concrète relève de
STO-TRACKER-02 (DEC-06). Réfère aux décisions DEC-01 à DEC-06.

## Acteurs & contexte
- **Cœur Effortless** : appelle le port pour projeter le modèle local.
- **Adapter** : satisfait le port pour un tracker donné (Jira, …) ou `NullTracker`.
- **Agent** : orchestre l'adapter concret (Jira via tools MCP) et arbitre les
  mappings proposés.

## SPEC-1 — Couplage projet
- Le couplage est déclaré dans `effortless.json` : `settings.tracker = { type,
  project_id, project_url }`.
- Au couplage, l'ID et l'URL de l'espace projet sont persistés côté Effortless et
  propagés à SecondBrain (frontmatter namespacé). (DEC-02)
- Sans `settings.tracker`, le projet utilise `NullTracker` : tout fonctionne en
  local, aucune projection.

## SPEC-2 — Découverte de taxonomie
- `discover_taxonomy` s'exécute **au premier couplage**. (DEC-04)
- Il résout types d'issues, transitions (Todo/Doing/Done) et champs réels de
  l'instance, et les met en cache au niveau projet.
- Si la structure du projet tracker diffère du modèle canonique 4-niveaux, l'agent
  **propose un mapping** à l'utilisateur, qui l'arbitre. Le mapping retenu est
  persisté.

## SPEC-3 — Création (push sortant)
- À la création d'une entité locale (Epic / Story / Task), le port crée l'issue
  correspondante selon le mapping 4-niveaux : Epic↦Epic, Story↦Story|Task,
  Task↦Sub-Task. (DEC-01)
- La référence retournée (`tracker_id`, `tracker_url`) est persistée sur l'objet
  local. (DEC-02)
- Le niveau Project n'est pas créé (espace pré-existant) : seul son couplage est
  enregistré.

## SPEC-4 — Transition d'état
- Un changement de statut local (Todo / Doing / Done) déclenche `transition` vers
  la transition tracker correspondante, résolue via la taxonomie découverte.
- Si le mapping de transition est inconnu, l'opération locale réussit et la
  projection est consignée au journal (voir SPEC-7).

## SPEC-5 — Rapport d'intervention (worklog)
- `log_work` enregistre un temps (minutes) + un commentaire sur l'issue.
- Le grain de saisie est la Task ; le cumul (rollup) remonte vers la Story.

## SPEC-6 — Import (read-mostly)
- `import` lit une structure tracker existante et la reverse-mappe en contexte
  local. Les issues importées ne sont pas réécrites (possédées par l'humain).
- L'import est le **seul** flux entrant ; aucune réconciliation bidirectionnelle.

## SPEC-7 — Résilience hors-ligne
- Si le tracker est injoignable, l'opération **locale réussit toujours** ; la
  projection est consignée dans un **journal (outbox)**. (DEC-05)
- Chaque élément en attente est une **migration** rejouable, **flaggée jouée avec
  un timestamp** une fois appliquée. Le rejeu est idempotent et ordonné.

## SPEC-8 — NullTracker
- Adapter par défaut : retourne des références vides, ne pousse rien, ne consigne
  rien. Sert de comportement nominal hors couplage et de double de test.

## Règles transverses
- **Identité non optionnelle** : `tracker_id` + `tracker_url` font partie du schéma
  de chaque objet. (DEC-02)
- **Effortless = source de vérité** : push sortant + import initial uniquement.
- **Agnosticité** : le cœur ne dépend d'aucun tracker concret. (DEC-03)

## Hors périmètre (STO-TRACKER-02)
- Implémentation Jira réelle de `discover_taxonomy`, mapping fin des types/champs,
  estimation (`timeoriginalestimate`), transitions concrètes, projection Xray.

## Critères d'acceptation
- Un projet sans `settings.tracker` fonctionne intégralement (NullTracker), aucun
  appel réseau.
- Créer une entité couplée persiste `tracker_id` + `tracker_url` sur l'objet.
- Tracker injoignable → l'opération locale réussit et une migration outbox est
  créée ; à la reconnexion, elle est rejouée puis flaggée jouée + timestamp.
- `import` ne modifie aucune issue existante.
- Le contrat est satisfait par `NullTracker` sans héritage (conformité Protocol).
