---
titre: Analyse
phase: O-analyse
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 001-Story-Port-Tracker
code: TEC-ANA
document: 01-TEC-ANA-analyse
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/tec-ana
---

# 🔍 Analyse de l'existant — Port Tracker (STO-TRACKER-01)

## Périmètre de la Story

STO-TRACKER-01 = **le contrat du Port Tracker** : l'abstraction que le cœur
appelle pour projeter le modèle fractal vers un tracker, plus un adapter de
référence minimal. L'implémentation Jira complète (mapping fin des types, champs,
estimation) est une Story distincte du plan (`Implémentation Jira`). Voir BQO Q-06.

Cinq opérations : `create`, `transition`, `log_work`, `import`, `discover_taxonomy`.

## État du code actuel

- **Aucun port ni adapter tracker** dans `src/mcp-server/effortless_mcp/`
  (grep `tracker|jira|xray|worklog` → vide). Greenfield.
- Le cœur manipule Epic / Story / Task en JSON local sous `.effortless/` ; aucune
  dépendance à un système externe pour le fonctionnement nominal.
- **Précédent d'adaptation externe** : `services/secondbrain.py` (symbiose
  SecondBrain) — pattern « le cœur reste agnostique, une couche écrit vers
  l'extérieur de façon non destructive ». Sert de modèle d'architecture pour le
  Port Tracker (couche optionnelle, side-effect contrôlé, namespacé).
- Modèles concernés (`models/`) : `epic.py`, `story.py`, `task.py` — aucun n'a de
  champ d'identité tracker aujourd'hui (cf. BQO Q-03).

## Outils Atlassian disponibles (MCP Rovo, côté client)

La projection Jira s'appuiera sur les tools déjà exposés :

- Création / édition : `createJiraIssue`, `editJiraIssue`, `createIssueLink`.
- États : `transitionJiraIssue`, `getTransitionsForJiraIssue`.
- Temps / suivi : `addWorklogToJiraIssue`, `addCommentToJiraIssue`.
- Lecture / import : `getJiraIssue`, `searchJiraIssuesUsingJql`,
  `getJiraIssueRemoteIssueLinks`.
- Découverte de taxonomie : `getVisibleJiraProjects`,
  `getJiraProjectIssueTypesMetadata`, `getJiraIssueTypeMetaWithFields`,
  `getIssueLinkTypes`, `lookupJiraAccountId`.

Conséquence : l'adapter Jira est **orchestré côté agent** (le port décrit l'intention,
l'agent appelle les tools MCP). À confirmer en cadrage (BQO Q-02).

## Contraintes héritées (décidées au cadrage projet — NON à re-litiger)

- Cœur **agnostique** ; le tracker est une couche d'adaptation enfichable.
- L'adapter **découvre** la taxonomie réelle, ne la suppose pas.
- **Effortless = source de vérité** : push sortant (create / transition / worklog) ;
  pull **uniquement** à l'import initial ; pas de sync bidirectionnelle.
- Quand couplé, **ID Effortless = clé d'issue** (identité partagée).
- **Xray** = projection optionnelle activable par projet.

## Hiérarchie canonique — 4 niveaux (Jira de base)

Jira **de base** expose **4 niveaux** (le 5e niveau est réservé aux versions
supérieures / Advanced Roadmaps — hors périmètre). Au niveau 3, Jira **Story** et
**Task** sont des objets du **même rang, interchangeables** ; Effortless retient le
terme **« Story »** (moins ambigu). Les 4 adaptateurs du port mappent ces 4 niveaux :

| # | Effortless | Jira (base) |
|---|------------|-------------|
| 1 | Project | Project |
| 2 | Epic | Epic |
| 3 | **Story** | Story **ou** Task (niveau 3, interchangeables) |
| 4 | **Task** | Sub-Task |

Attention : Effortless `Task` (niveau 4) ↦ Jira **Sub-Task**, à NE PAS confondre
avec le Jira « Task » de niveau 3 (qui, lui, correspond à une Story Effortless).

## Référence terrain — projet IFX

Cycle en V, déjà mappé au cadrage projet :

- Hiérarchie : Epic → Story → Sous-tâche (cardinalité 1 Epic : N Stories).
- Mapping : Epic→Epic, Story→Story, Task→Sous-tâche.
- Temps : worklog en heures (`0,5h`) ; `timeoriginalestimate` disponible.
- Rang : `customfield_10019` (LexoRank), géré par Jira, jamais saisi.
- Types : Epic / Story / Tâche / Sous-tâche (+ Xray Test / Test Set / Execution).

## Chaîne d'automatisation visée (rappel)

1. `create` → `createJiraIssue` (Sous-tâche sous la Story), estimation via
   `timeoriginalestimate` ; la clé retournée devient l'ID local.
2. `transition` → `transitionJiraIssue` (mapping Todo/Doing/Done résolu à l'import
   via `getTransitionsForJiraIssue`).
3. `log_work` → `addWorklogToJiraIssue` + `addCommentToJiraIssue` sur la Sous-tâche ;
   cumul remonté à la Story.
4. `import` → `searchJiraIssuesUsingJql` / `getJiraIssue` reverse-mappés en contexte.

## Zones d'incertitude → arbitrage (voir 02-BQO)

- Forme technique du port (ABC / Protocol / module).
- Mode d'injection de l'adapter.
- Stockage du mapping ID local ↔ clé tracker.
- Déclenchement et cache de `discover_taxonomy`.
- Politique d'erreur / hors-ligne.
- Périmètre exact de CETTE Story (contrat seul vs impl Jira).
