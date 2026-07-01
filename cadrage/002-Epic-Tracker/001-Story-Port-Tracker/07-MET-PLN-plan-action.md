---
phase: L-plan
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 001-Story-Port-Tracker
code: MET-PLN
document: 07-MET-PLN-plan-action
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/met-pln
---

# 🚀 Plan d'action — Port Tracker (STO-TRACKER-01)

Découpe en tâches atomiques (vertes par tests) de l'abstraction agnostique
(DEC-06). Implémentation dans un nouveau package `effortless_mcp/ports/` +
champs additifs sur les modèles. Aucune dépendance Jira (impl = STO-TRACKER-02).

## Séquencement
1. Types + contrat (fondation, sans I/O).
2. Identité (champs entités + couplage projet).
3. Journal offline (outbox migrations).
4. Câblage aux points de mutation du cœur.
5. Tests transverses.

## Task Breakdown

### TSK-02 — `ports/tracker.py` : types de base
Définir `Level`, `LocalStatus`, `TrackerRef`, `ProjectRef`, `ObjectPayload`,
`Taxonomy`, `ImportedObject` (dataclasses frozen). Aucun I/O. **simple**.

### TSK-03 — `Tracker` Protocol + `NullTracker`
Protocol à 5 méthodes (create/transition/log_work/import_tree/discover_taxonomy)
+ `NullTracker` no-op conforme. **simple**. Dépend de TSK-02.

### TSK-04 — Fabrique `resolve_tracker(settings)`
Lit `settings.tracker.type` → instancie l'adapter ou `NullTracker` (type absent/
inconnu). **simple**. Dépend de TSK-03.

### TSK-05 — Identité sur les modèles
Ajouter `tracker_id: str = ""` + `tracker_url: str = ""` à `models/epic.py`,
`story.py`, `task.py`. Back-compat (valeur vide). **simple**.

### TSK-06 — Couplage projet + schéma config
Schéma `settings.tracker = {type, project_id, project_url}` dans `effortless.json` ;
persistance de l'identité d'espace ; propagation à SecondBrain (frontmatter
namespacé). **complex**. Dépend de TSK-04.

### TSK-07 — `ports/sync_journal.py` : outbox rejouable
Écrire/lire `.effortless/tracker_outbox/` (1 fichier/migration, `seq`, `op`,
`args`, `created_at`, `played`, `played_at`). Fonction `replay()` idempotente
ordonnée par `seq`, flag `played` + timestamp. **complex**. Dépend de TSK-02.

### TSK-08 — Câblage du port au cœur
Aux points de mutation (création d'entité, `task_update` de statut, worklog),
appeler le port résolu via `resolve_tracker` ; tracker injoignable → consigner
une migration outbox ; persister `TrackerRef` sur l'objet. Gardé par NullTracker
(no-op si non couplé). **complex**. Dépend de TSK-04, TSK-05, TSK-07.

### TSK-09 — Tests transverses
Conformité `NullTracker` au Protocol ; `resolve_tracker` (null/inconnu/typé) ;
persistance identité à la création ; `replay()` idempotent + flag timestamp ;
projet non couplé = zéro I/O. **simple**. Dépend de TSK-08.

## Dépendances & risques
- Le câblage (TSK-08) touche des chemins existants (création d'entités, transitions) :
  rester additif et garder NullTracker comme défaut → aucun changement de
  comportement hors couplage.
- `timeoriginalestimate`, mapping fin des champs, transitions concrètes : hors
  périmètre (STO-TRACKER-02).
