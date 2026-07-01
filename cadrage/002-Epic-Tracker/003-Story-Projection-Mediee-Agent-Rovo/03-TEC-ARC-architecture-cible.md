---
titre: Architecture cible
phase: P-cadrage
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 003-Story-Projection-Mediee-Agent-Rovo
code: TEC-ARC
document: 03-TEC-ARC-architecture-cible
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/tec-arc
---

# 🏗️ Architecture cible — Projection médiée agent (STO-TRACKER-03)

## Principe

Serveur = **planificateur** (zéro I/O, zéro secret). Agent = **exécuteur** via Rovo
MCP. Transport = **outbox `SyncJournal`**. Révise DEC-03 (STO-TRACKER-01).

## 🧩 Key Components

| Composant | Rôle |
|---|---|
| `ports/adapters/jira.py::QueueTracker` | Adapter type `jira` en mode médié. `create` **enqueue** une op dans l'outbox et retourne `TrackerRef("local:N","")`. `discover_taxonomy` enqueue une demande (ou retourne la taxonomie déjà ackée). Plus aucun appel réseau. |
| `register_adapter("jira", build_queue_tracker)` | Fabrique sans credentials. Reçoit `root` (chemin outbox) via cfg. |
| `services/scaffolder.py` | **Inchangé** : appelle `tracker.create()`. En mode queue, les refs placeholder câblent `parent_local_id`. |
| `services/scaffold_state.py` | **Inchangé** : idempotence locale (garde primaire). |
| `ports/sync_journal.py::SyncJournal` | Transport : `enqueue(op, payload)` / `pending()` / `replay(fn)`. **Réutilisé**. |
| `server.py::effortless_tracker_pending` | Tool : renvoie les ops en attente (JSON) = le plan à exécuter par l'agent. |
| `server.py::effortless_tracker_ack` | Tool : reçoit `{local_id:{tracker_id,tracker_url}}`, persiste l'identité, marque l'outbox joué (idempotent). |
| `server.py::effortless_tracker_couple/scaffold` | Refondus : produisent un plan (enqueue), plus d'I/O réseau. En-tête **disclaimer Rovo**. |

## Retraits (DEC)

- `ports/adapters/jira_client.py::JiraClient` (REST) — **supprimé**. `FakeJiraClient`
  conservé pour les tests (simule l'exécuteur agent).
- `build_jira_tracker` + lecture `JIRA_*` env / token — **supprimés**.

## Flux scaffold (médié)

```
1. effortless_tracker_scaffold(zone)         [serveur]
   - ScaffoldState.has(zone) ? -> skip (refs connues)
   - scaffolder(QueueTracker) -> enqueue N ops {local_id, level, title,
     parent_local_id, labels} dans l'outbox
   - retourne : "N ops en attente. ⚠️ Rovo requis. Appeler tracker_pending."
2. effortless_tracker_pending()              [serveur -> agent]
   - retourne le plan JSON (ops triées parent-avant-enfant)
3. agent : pour chaque op (ordre topo)        [agent via Rovo]
   - createJiraIssue(projectKey, issueTypeName/levelmap, summary,
       parent=map[parent_local_id], additional_fields.labels)
   - map[local_id] = {key, url}
4. effortless_tracker_ack(zone, map)          [agent -> serveur]
   - persiste tracker_id/url, ScaffoldState.set(zone, map), outbox.replay -> played
```

## Flux discover (médié)

Le serveur ne découvre pas. `couple` enregistre `settings.tracker={type:"jira",
project_id, project_url}` et demande à l'agent de fournir la taxonomie :
l'agent appelle `getJiraProjectIssueTypesMetadata`, puis
`effortless_tracker_ack` (variante taxonomie) persiste la `Taxonomy`.
MVP : la taxonomie n'est pas strictement requise pour le scaffold côté agent
(l'agent passe les noms de type via le levelmap du template).

## Disclaimer Rovo

Chaque tool tracker préfixe sa sortie de :
> ⚠️ Projection médiée : nécessite le connecteur **Atlassian Rovo MCP** déclaré
> dans ta CLI/App. Absent ? Ajoute-le, sinon le flush Jira est impossible.

La consigne agent (CLAUDE.md / skill) impose de vérifier la présence de Rovo
avant `tracker_pending`/flush.

## Invariants

- Serveur sans secret, sans réseau Jira. Token nulle part.
- `NullTracker` inchangé (projet non couplé = no-op).
- Tests hermétiques : `FakeJiraClient` joue l'exécuteur agent en mémoire.
