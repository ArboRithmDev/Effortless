---
titre: Specifications
phase: A-specs
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 004-Story-Discover-Medie-Issue-Type
code: FNC-SPE
document: 05-FNC-SPE-specifications
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/fnc-spe
---

# 📐 Spécifications — Discover médié + issue_type_id (STO-TRACKER-04)

## Capacités

### 1. Persister la taxonomie médiée
`effortless_tracker_discover_ack(taxonomy_json)` : reçoit
`{"epic":"10000","story":"10007","task":"10095"}` (level→id), résolu par l'agent
via `getJiraProjectIssueTypesMetadata`. Écrit `settings.tracker.taxonomy`.

### 2. Stamper issue_type_id sur les ops
`QueueTracker.create` ajoute `issue_type_id` (depuis la taxonomie) à chaque op.
`pending` l'expose.

## Comportements
| Situation | Comportement |
|---|---|
| Taxonomie ackée | ops portent `issue_type_id` ; flush agent passe le type par id. |
| Taxonomie absente | `issue_type_id=null` ; flush retombe sur le nom (best-effort) + disclaimer. |
| Re-discover | `discover_ack` écrase la taxonomie (idempotent). |

## Critères d'acceptation
1. `discover_ack` persiste `settings.tracker.taxonomy`.
2. Après ack, `scaffold` enqueue des ops avec `issue_type_id` correct (task→10095).
3. `pending` expose `issue_type_id`.
4. Sans taxonomie, `issue_type_id=null` (pas d'échec).
5. Tests hermétiques (taxonomie en fixture).
6. Validation live : couple→discover(Rovo)→discover_ack→scaffold→pending→flush
   (id auto, **sous-tâches sans forçage manuel**)→ack.
