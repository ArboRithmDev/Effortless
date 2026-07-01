---
phase: A-specs
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 003-Story-Projection-Mediee-Agent-Rovo
code: FNC-SPE
document: 05-FNC-SPE-specifications
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/fnc-spe
---

# 📐 Spécifications fonctionnelles — Projection médiée agent (STO-TRACKER-03)

## Capacités (MVP)

### 1. Coupler (sans token)
`effortless_tracker_couple(type="jira", project_id, project_url)` :
écrit `settings.tracker` (type/project_id/project_url). **Aucun base_url/email/token.**
Sortie préfixée du **disclaimer Rovo**.

### 2. Planifier le scaffold
`effortless_tracker_scaffold(zone="PROJET", template_name=...)` :
- Garde idempotence `ScaffoldState` : zone déjà faite → skip.
- Sinon enqueue N ops dans l'outbox (1 Epic + 3 Stories + 2 sous-tâches), liens par
  `parent_local_id`. **Aucun I/O Jira.**
- Retourne : disclaimer + « N ops en attente — appelle `effortless_tracker_pending` ».

### 3. Lire le plan
`effortless_tracker_pending()` : renvoie la liste d'ops en attente (JSON), triées
parent-avant-enfant : `{seq, op, local_id, level, title, parent_local_id, labels}`.

### 4. Exécuter (agent, via Rovo)
L'agent, pour chaque op : `createJiraIssue(projectKey, issueTypeName=levelmap[level],
summary=title, parent=map[parent_local_id], additional_fields={labels})`, puis
`map[local_id] = {tracker_id: key, tracker_url: url}`.

### 5. Acker
`effortless_tracker_ack(zone, refs_json)` : reçoit `{local_id:{tracker_id,
tracker_url}}`. Persiste l'identité, `ScaffoldState.set(zone, refs)`, marque les
ops outbox jouées (idempotent).

## Comportements

| Situation | Comportement |
|---|---|
| Projet non couplé | NullTracker : tools tracker no-op, zéro op enqueue. |
| Rovo absent côté agent | Disclaimer affiché ; l'agent ne doit pas flusher (impossible). |
| Scaffold zone neuve | Enqueue N ops ; agent exécute ; ack persiste refs. |
| Scaffold zone existante | Skip (ScaffoldState) ; retourne refs connues, 0 op. |
| ack partiel / interrompu | Outbox rejouable : re-pending renvoie les ops non ackées. |

## Mapping niveau → type Jira (levelmap)

`{"epic":"Epic", "story":"Story", "task":"Sous-tâche"}` — noms passés à
`createJiraIssue.issueTypeName`. (Le template porte déjà `level` par nœud.)

## Hors périmètre (stories suivantes)

- `transition` / `log_work` médiés (cycle en V complet, worklog).
- Reconcile Jira-as-truth (search label agent-side avant flush).
- Détection automatique de la présence de Rovo (discipline agent en MVP).

## Critères d'acceptation

1. `scaffold` zone neuve enqueue exactement 6 ops avec liens `parent_local_id`
   cohérents (Epic→Stories, Story Divers→2 sous-tâches).
2. `pending` renvoie les 6 ops triées parent-avant-enfant.
3. `ack` persiste les 6 refs dans ScaffoldState et vide l'outbox.
4. Re-`scaffold` même zone → 0 op (idempotent).
5. Projet non couplé → 0 op, no-op.
6. Aucun `JIRA_*` / token lu nulle part ; `JiraClient` REST supprimé.
7. Suite pytest hermétique (FakeJiraClient simule l'exécuteur agent), zéro réseau.
8. Validation live : scaffold → pending → exécution **via Rovo** → ack, arbre
   `[PROJET]` recréé dans EFL **sans token**.
