---
phase: O-analyse
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 004-Story-Discover-Medie-Issue-Type
code: TEC-ANA
document: 01-TEC-ANA-analyse
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/tec-ana
---

# 🔍 Analyse — Discover médié + issue_type_id (STO-TRACKER-04)

## Déclencheur (DEC-07)
Validation live STO-TRACKER-03 : Rovo `createJiraIssue` rejette
`issueTypeName="Sous-tâche"` ; il faut forcer le type par **id**
(`additional_fields={"issuetype":{"id":"10095"}}`). Contournement manuel dans la
validation. À automatiser.

## Acquis (STO-TRACKER-03)
- `QueueTracker.create` enqueue `{local_id, level, issue_type_name, title,
  parent_local_id, labels}` ; ref `local:N`. Pas d'`issue_type_id`.
- Outils `couple` / `scaffold` / `pending` / `ack`. `SyncJournal` transport.
- `resolve_tracker(settings, root)` injecte `__root__`.

## Gap
- L'op ne porte pas `issue_type_id` → l'agent doit deviner/forcer l'id à la main.
- Le serveur ne peut pas découvrir la taxonomie (pas d'accès Rovo). Il faut un
  **discover médié** : l'agent résout `level→id`, le serveur le persiste.

## Cible
1. Nouvel outil `effortless_tracker_discover_ack(taxonomy_json)` : persiste
   `settings.tracker.taxonomy = {level: issue_type_id}`.
2. `build_queue_tracker(cfg)` lit `cfg["taxonomy"]` (via `settings.tracker.taxonomy`)
   et le passe à `QueueTracker`. `resolve_tracker` propage déjà la cfg tracker.
3. `QueueTracker.create` stampe `issue_type_id = taxonomy.get(level)` dans l'op.
4. `pending` expose `issue_type_id`. La procédure flush agent passe le type par id.

## Flux (médié, complet)
```
couple(jira, EFL)                          [serveur]
agent: getJiraProjectIssueTypesMetadata    [Rovo] -> {epic:10000, story:10007, task:10095}
discover_ack(taxonomy_json)                [serveur] persiste settings.tracker.taxonomy
scaffold(zone)                             [serveur] ops portent issue_type_id
pending() -> plan (avec issue_type_id)     [serveur -> agent]
agent: createJiraIssue(..., additional_fields={"issuetype":{"id":...},"labels":...})
ack(zone, refs)                            [serveur]
```

## Risques / notes
- Taxonomie absente (discover non fait) → `issue_type_id=null` ; le flush retombe
  sur le nom (best-effort) avec disclaimer. Discover recommandé avant scaffold.
- Tests hermétiques : la taxonomie est fournie en fixture (pas de Rovo en test).
