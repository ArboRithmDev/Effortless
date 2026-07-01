---
type: cadrage-projet
document: 0-mvp
titre: Effortless — MVP
projet: Effortless
statut: figé
version: 1
maj: 2026-07-01
tags:
  - cadrage/projet
  - cadrage/mvp
---

# Effortless — MVP (document 0)

> Traduction du besoin. Corps **figé** après le démarrage de la première Epic.
> Vivant **par addition seule** : addenda datés en fin de document, jamais de
> réécriture rétroactive du corps.

## Besoin

Piloter un projet logiciel de bout en bout avec un agent, sans quitter la
conversation, en gardant à tout instant une trace structurée de l'intention, des
décisions et de l'avancement — et en projetant ce pilotage vers l'outil de suivi
de l'équipe (Jira) sans jamais manipuler de secret côté serveur.

## Proposition de valeur

- Un modèle de projet **fractal** (Projet → Epic → Story → Task) qui porte la
  méthode Opale (phases Opale / cycle en V).
- Une **projection médiée** vers Jira : le serveur planifie, l'agent exécute via
  son connecteur Rovo. Zéro token, zéro appel réseau côté serveur.
- Un garde-fou **anti-dérive** : impossible de committer sans tâche active.
- Une **mémoire** persistante (SecondBrain) pour reprendre à froid.

## Périmètre MVP

- Modèle fractal + phases Opale + registres tâches / décisions / questions.
- Projection Jira médiée : scaffold, transition, temps passé, import, Xray.
- Boucle de développement itérative + hook anti-dérive.
- Cadrage projet (documents 0 à 4) et cadrage par Epic.

## Hors périmètre (MVP)

- Exécution directe Jira avec credentials côté serveur.
- Intégrations tierces autres que Jira/Rovo et SecondBrain.
- Interface graphique dédiée (au-delà de l'UI web existante).

## Critères de succès

- Un projet peut être cadré, découpé en Epics/Stories/Tasks, et projeté dans
  Jira sans intervention manuelle sur les clés d'issue.
- Le pilotage reste lisible et reprenable après interruption.
- Effortless se pilote lui-même (dogfood) sans dette de suivi.

---

## Addenda (append-only)

_(aucun pour l'instant — première baseline 2026-07-01)_
