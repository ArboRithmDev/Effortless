---
phase: O-analyse
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 001-Story-Port-Tracker
code: FNC-GLO
document: 00-FNC-GLO-glossaire
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/fnc-glo
---

# 📖 Glossaire — Port Tracker (STO-TRACKER-01)

Vocabulaire de la couche d'adaptation entre le modèle fractal local
(Epic / Story / Task) et un tracker externe. Hérite des décisions de cadrage
du projet (EPIC-PROJET / STO-PROJET-01) : cœur agnostique, Jira en projection.

## Termes du domaine

- **Tracker** : système de suivi externe (Jira, GitLab, Linear, Azure DevOps…).
  Optionnel : Effortless fonctionne sans tracker branché.
- **Port Tracker** : contrat d'abstraction (interface) que le cœur appelle, sans
  rien savoir du tracker concret. Objet de CETTE Story.
- **Adapter** : implémentation concrète d'un Port pour un tracker donné
  (ex. adapter Jira). Mappe le modèle interne vers les types réels de l'instance.
- **Projection** : le tracker est une *vue miroir* du modèle local, jamais
  l'inverse. Effortless = source de vérité.
- **Taxonomie** : ensemble des types d'issues, transitions et champs propres à une
  instance de tracker. **Découverte**, jamais supposée.
- **Mapping** : correspondance entre une entité Effortless et son équivalent
  tracker (Epic→Epic, Story→Story, Task→Sous-tâche) et entre statuts internes
  (Todo/Doing/Done) et transitions du tracker.
- **Clé canonique** : quand un tracker est couplé, l'ID Effortless **EST** la clé
  d'issue (`<CODE>-N`). Identité unique des deux côtés.
- **Worklog** : temps passé loggé sur une issue (en heures). Cumulé (rollup) de la
  Sous-tâche vers la Story.
- **Rollup** : agrégation ascendante (worklog d'une Task → total Story → Epic).
- **Source de vérité** : Effortless possède ce qu'il **crée**. Push sortant
  (création, transition, worklog) ; pull entrant **uniquement** à l'import initial.
  Pas de réconciliation bidirectionnelle.
- **Import read-mostly** : reverse-mapping d'issues existantes en contexte, sans
  les réécrire (elles restent possédées par l'humain).
- **Xray** : extension Jira de gestion de tests (Test / Test Set / Test Execution).
  Projection optionnelle, activable par projet.

## Opérations du Port (surface visée)

- **create** : matérialiser une entité locale comme issue dans le tracker ;
  retourne la clé canonique.
- **transition** : faire avancer l'état d'une issue (mapping statut → transition).
- **log_work** : enregistrer temps + commentaire d'intervention sur une issue.
- **import** : lire une structure tracker existante et la reverse-mapper en
  contexte local (read-mostly).
- **discover_taxonomy** : interroger l'instance pour résoudre types, transitions et
  champs réels, afin de ne rien supposer.
