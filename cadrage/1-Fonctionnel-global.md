---
type: cadrage-projet
document: 1-fonctionnel-global
titre: Effortless — Fonctionnel global
projet: Effortless
statut: versionné
version: 1
maj: 2026-07-01
tags:
  - cadrage/projet
  - cadrage/fonctionnel
---

# Effortless — Analyse et spécification fonctionnelle globale (document 1)

> Cadre fonctionnel de l'ensemble du projet. Distingue les périmètres dont
> naissent les Epics. **Révisable par version** (snapshots datés) — l'histoire
> des révisions est conservée ; les évolutions ponctuelles vivent dans le
> document 4, les révisions structurantes créent une nouvelle version ici.

**Version 1 — baseline — 2026-07-01**

## Vision fonctionnelle

Effortless est un framework de conduite de projet opéré par un agent. Il
transforme une intention (document 0) en un arbre de travail exécutable et
projeté vers un outil de suivi, tout en gardant la direction du projet visible.

## Acteurs

- **Utilisateur (pilote)** : porte l'intention, tranche les questions ouvertes,
  valide les jalons.
- **Agent** : analyse, cadre, découpe, exécute, projette vers Jira via Rovo,
  archive la mémoire.
- **Outil de suivi (Jira)** : source de vérité du suivi côté équipe, alimentée
  par projection médiée.

## Périmètres fonctionnels → Epics

- **Core** — modèle fractal, phases Opale, registres (tâches, décisions,
  questions), boucle itérative, anti-dérive, mémoire. _(livré)_
- **Tracker** — projection médiée Jira : scaffold, transition, temps passé,
  import read-mostly, Xray, réconciliation. _(livré)_
- **Cadrage** — cadrage projet (documents 0–4), deux modes d'initialisation
  (agile / cycle en V), nomenclature des répertoires, outils de clôture
  Story/Epic. _(à venir)_

## Parcours clés

1. **Initialisation** — projet vierge (pilotage agile) ou repris de Jira
   (pilotage en V). Produit les documents 0–4 et amorce la première Epic.
2. **Cadrage d'une Epic** — analyse, questions bloquantes (BQO), spécifications,
   plan, dans `cadrage/<Epic>/<Story>/`.
3. **Exécution** — tâches en boucle, projection Jira à chaque mutation, clôture
   Story puis Epic.
4. **Reprise** — rechargement de la mémoire pour continuer à froid.

## Règles fonctionnelles

- Le document 0 (MVP) est figé, enrichi par addition seule.
- Les questions ouvertes de niveau projet graduent en BQO d'Epic.
- Une Story ne se committe qu'avec une tâche active (anti-dérive).
- Le backlog global (document 3) est la vérité maître ; les Epics en sont des
  projections délimitées par ce document.

## Historique des versions

- v1 (2026-07-01) — baseline initiale.
