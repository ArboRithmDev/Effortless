---
titre: Analyse
phase: O-analyse
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 003-Story-Projection-Mediee-Agent-Rovo
code: TEC-ANA
document: 01-TEC-ANA-analyse
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/tec-ana
---

# 🔍 Analyse de l'existant — Projection médiée agent (STO-TRACKER-03)

## Déclencheur

STO-TRACKER-02 a livré l'adapter Jira via `JiraClient` REST + token. Coût révélé :
l'utilisateur doit gérer un **token Atlassian** (expirant), et un token est passé
dans un transcript de session. Décision Ben : **l'agent DOIT passer par le
connecteur Rovo MCP** ; le serveur ne détient aucun secret.

## État du code (acquis STO-TRACKER-02)

- `ports/adapters/jira_client.py` : `FakeJiraClient` (conservé, tests) + `JiraClient`
  REST (**à retirer**).
- `ports/adapters/jira.py` : `JiraTracker` (discover+create REST) + `build_jira_tracker`
  (creds env) + `register_adapter("jira", …)` (**à refondre**).
- `services/scaffolder.py` : `scaffold_project_from_template` (agnostique, appelle
  `tracker.create`) — **réutilisable tel quel** si `create` enqueue.
- `services/scaffold_state.py` : idempotence locale — **conservé**.
- `ports/sync_journal.py` : `SyncJournal` outbox rejouable — **pivot du transport**.
- `server.py` : `effortless_tracker_couple` / `effortless_tracker_scaffold`
  (**à refondre** : plus de discover/scaffold réseau côté serveur).

## Contrainte structurante

Le **process serveur ne peut pas appeler les MCP** (capacité côté agent). Donc
ni `discover_taxonomy`, ni `create`, ni `transition` ne peuvent toucher Jira
depuis le serveur. Tout I/O Jira **doit** être fait par l'agent via Rovo.

## Capacités Rovo MCP disponibles (côté agent)

| Besoin | Outil Rovo |
|---|---|
| Découverte types | `getJiraProjectIssueTypesMetadata` |
| Transitions | `getTransitionsForJiraIssue` |
| Création issue (+ parent, labels) | `createJiraIssue` (param `parent`, `additional_fields.labels`) |
| Transition statut | `transitionJiraIssue` |
| Recherche (idempotence externe) | `searchJiraIssuesUsingJql` |

> Vérifié en live cette session : `createJiraIssue` câble bien `parent`
> (Epic→Story, Story→Sous-tâche) et les labels sur EFL.

## Architecture cible (planificateur / exécuteur)

```
Serveur (PLANIFICATEUR)                        Agent (EXÉCUTEUR, a Rovo)
─────────────────────────                      ─────────────────────────
scaffold → QueueTracker.create()  ─enqueue→    effortless_tracker_pending()
   ops {local_id, level, title,                   → lit les ops (plan)
        parent_local_id, labels}                exécute via Rovo createJiraIssue
   dans SyncJournal                                (résout parent via map local→key)
                                               effortless_tracker_ack(refs_map)
persiste tracker_id/url + marque        ◄──ack──   {local_id: {key,url}}
l'outbox joué (idempotent)
```

- `discover_taxonomy` : idem médié — l'agent appelle `getJiraProjectIssueTypesMetadata`,
  renvoie la `Taxonomy` au serveur (persistée dans `settings.tracker`).
- `scaffolder` inchangé : il appelle `tracker.create()` ; en mode queue, `create`
  enqueue et retourne une ref **placeholder** portant le `local_id` (sert de
  `parent_ref` aux enfants → encode `parent_local_id`).

## Gaps / cible

- Retirer `JiraClient` REST + `build_jira_tracker` creds + tout usage de token.
- Nouveau `QueueTracker` (type `jira`) : `create`/`discover` = enqueue.
- 2 tools : `effortless_tracker_pending` (renvoie le plan d'ops) +
  `effortless_tracker_ack` (enregistre refs + persiste identité + marque outbox).
- Refondre `couple`/`scaffold` : produisent un plan, plus d'I/O réseau serveur.
- **Disclaimer Rovo** dans chaque tool tracker + consigne agent (CLAUDE.md/skill).
- Tests hermétiques inchangés sur le principe (FakeJiraClient → ici, faux outbox/agent).

## Risques

- Le serveur ne peut pas vérifier que l'agent a Rovo → disclaimer + discipline agent.
- Ordre d'exécution : parents avant enfants (tri topologique du plan) — porté côté agent.
- Idempotence : garde locale `ScaffoldState` + (option) `searchJiraIssuesUsingJql`
  du label côté agent avant flush.
