---
phase: O-analyse
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 002-Story-Adapter-Jira-Concret
code: FNC-GLO
document: 00-FNC-GLO-glossaire
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/fnc-glo
---

# 📖 Glossaire — Adapter Jira concret (STO-TRACKER-02)

Vocabulaire de l'**implémentation Jira** du Port Tracker défini en STO-TRACKER-01.
Cette Story rend le contrat agnostique opérant contre une vraie instance Jira, et
introduit la première capacité d'application : le **scaffold** d'un projet depuis
un template.

## Termes du domaine

- **Adapter Jira** : implémentation concrète du `Tracker` Protocol pour Jira Cloud,
  enregistrée via `register_adapter("jira", factory)`. Traduit le modèle fractal
  (Epic / Story / Task) vers les types réels de l'instance.
- **Taxonomie** : ensemble des types d'issues + schéma de transitions d'un projet
  Jira donné. Résolue à l'exécution par `discover_taxonomy` (jamais devinée).
- **Type d'issue** : Epic (niveau 1), Story / Tâche / Bug… (niveau 0),
  Sous-tâche (niveau -1). Mapping canonique : Effortless `Task` ↦ Jira **Sous-tâche**.
- **Transition** : passage d'un statut à un autre dans le workflow. Identifiée par
  un `transitionId` (≠ id de statut). `transition(ref, statut)` résout le bon
  transitionId pour atteindre le statut cible.
- **Cycle en V** : workflow de la catégorie projet "Projet cycle en V" observée sur
  IFX. Statuts : *A faire → Gestion de projet / ANALYSE / En cours → Terminé*
  (+ *Annulé(e)*).
- **Template `[PROJET]`** : structure-type d'amorçage d'un projet, observée sous
  l'Epic IFX-1 : 1 Epic, 3 Stories, 2 sous-tâches, tout en *A faire*, **non affecté**.
- **Scaffold (de projet)** : création en lot, dans un projet cible, de l'arbre
  décrit par le template. **Workflow composite**, non primitif : il itère sur les
  nœuds du template et appelle `create` pour chacun en câblant le parent.
- **Composer de scaffold** : service domaine `scaffold_project_from_template` qui
  porte cette boucle. Vit **au-dessus** du Port (agnostique) — PAS une 6e op du Port.
- **Template config externalisé** : description versionnée du template (fichier
  sous Effortless), initialisée depuis l'observation d'IFX-1, modifiable sans code.
- **Projet cible** : projet Jira recevant le scaffold. Pour les tests propres :
  **EFL** (vide, dédié). **IFX** = référence en lecture seule (source du template).
- **Parent ref** : lien hiérarchique (Epic→Story via `parent`, Story→Sous-tâche
  via `parent`) posé à la création pour reconstituer l'arbre côté Jira.
- **timeoriginalestimate** : champ Jira d'estimation initiale (secondes). Cible de
  la projection d'estimation Effortless quand renseignée.
