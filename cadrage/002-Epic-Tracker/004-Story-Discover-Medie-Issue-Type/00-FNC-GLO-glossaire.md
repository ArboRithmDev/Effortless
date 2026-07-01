---
phase: O-analyse
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 004-Story-Discover-Medie-Issue-Type
code: FNC-GLO
document: 00-FNC-GLO-glossaire
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/fnc-glo
---

# 📖 Glossaire — Discover médié + issue_type_id (STO-TRACKER-04)

- **Discover médié** : résolution de la taxonomie côté agent (Rovo
  `getJiraProjectIssueTypesMetadata`), renvoyée au serveur via un ack et persistée
  dans `settings.tracker.taxonomy`. Le serveur ne découvre jamais lui-même.
- **Taxonomy (level→id)** : map `{epic: "10000", story: "10007", task: "10095"}`
  des niveaux canoniques vers les **ids** de type Jira de l'instance couplée.
- **issue_type_id** : id Jira du type d'issue, désormais porté par chaque op du
  plan. Autorité du flush (≠ nom) — indispensable pour les sous-tâches (DEC-07).
- **discover_ack** : nouvel outil par lequel l'agent persiste la taxonomie résolue
  (`effortless_tracker_discover_ack(taxonomy_json)`).
- **Flush automatique** : l'agent passe le type par id (depuis l'op), sans forçage
  manuel — clôt le contournement observé en validation live de STO-TRACKER-03.
