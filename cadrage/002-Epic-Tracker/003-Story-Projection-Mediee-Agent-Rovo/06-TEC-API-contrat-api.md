---
phase: A-specs
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 003-Story-Projection-Mediee-Agent-Rovo
code: TEC-API
document: 06-TEC-API-contrat-api
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/tec-api
---

# 🔌 Contrat API — Projection médiée agent (STO-TRACKER-03)

## 1. `QueueTracker` (ports/adapters/jira.py — remplace JiraTracker REST)

```python
class QueueTracker:                      # satisfait le Protocol Tracker
    def __init__(self, journal, levelmap=None):
        self._journal = journal          # SyncJournal (outbox)
        self._levelmap = levelmap or {"epic":"Epic","story":"Story","task":"Sous-tâche"}
        self._seq = 0

    def create(self, payload: ObjectPayload) -> TrackerRef:
        self._seq += 1
        local_id = f"local:{self._seq}"
        parent_local = payload.parent_ref.tracker_id if payload.parent_ref else None
        self._journal.enqueue("create", {
            "local_id": local_id,
            "level": payload.level,
            "issue_type_name": self._levelmap.get(payload.level, payload.level),
            "title": payload.title,
            "parent_local_id": parent_local,    # référence une op antérieure
            "labels": list(payload.labels or []),
        })
        return TrackerRef(tracker_id=local_id, tracker_url="")

    def discover_taxonomy(self, project): return Taxonomy()   # médié agent (hors enqueue MVP)
    def transition(self, ref, status):   raise NotImplementedError   # post-MVP
    def log_work(self, ref, minutes, comment): raise NotImplementedError
    def import_tree(self, project):      return []

def build_queue_tracker(cfg: dict) -> QueueTracker:
    from effortless_mcp.ports import SyncJournal
    return QueueTracker(SyncJournal(cfg["__root__"]))
# register_adapter("jira", build_queue_tracker)
```

> `cfg["__root__"]` : le `resolve_tracker` doit injecter la racine projet dans la
> config (le SyncJournal écrit sous `<root>/.effortless/tracker_outbox/`).
> Adapter `resolve_tracker`/`couple` pour fournir `__root__`.

## 2. Op (entrée d'outbox)

```json
{"seq": 1, "op": "create", "played": false,
 "payload": {"local_id":"local:1", "level":"epic", "issue_type_name":"Epic",
             "title":"[PROJET]", "parent_local_id": null,
             "labels":["effortless-scaffold:PROJET"]}}
```

Tri d'exécution : par `seq` croissant ⇒ parent toujours avant enfant (le scaffolder
crée en DFS pré-ordre).

## 3. Tools MCP

```python
@mcp.tool()
def effortless_tracker_pending() -> str:
    # Lit l'outbox (SyncJournal(root).pending()) -> JSON des ops non jouées + disclaimer.

@mcp.tool()
def effortless_tracker_ack(zone: str, refs_json: str) -> str:
    # refs_json = {"local:1": {"tracker_id":"EFL-1","tracker_url":"…"}, ...}
    # - ScaffoldState(root).set(zone, refs)
    # - SyncJournal(root).replay(lambda e: None)  # marque tout joué (idempotent)
    # - retourne un récap "{n} refs persistées, outbox vidé".
```

`effortless_tracker_couple` (refondu) : écrit `settings.tracker={type,project_id,
project_url}` (sans secret), préfixe le **disclaimer Rovo**.

`effortless_tracker_scaffold` (refondu) : ScaffoldState guard → sinon
`scaffold_project_from_template(QueueTracker, …)` (enqueue) → retourne disclaimer +
nombre d'ops + invite à `tracker_pending`.

## 4. Disclaimer (constante partagée)

```
⚠️ Projection médiée : nécessite le connecteur Atlassian Rovo MCP déclaré dans ta
CLI/App. Absent ? Ajoute-le — sinon l'exécution Jira (flush) est impossible.
```

## 5. Boucle d'exécution agent (consigne, hors code serveur)

```
scaffold(zone) -> pending() -> [pour chaque op, ordre seq]
   Rovo.createJiraIssue(projectKey=project_id, issueTypeName=issue_type_name,
       summary=title, parent=map[parent_local_id], additional_fields={"labels":labels})
   map[local_id] = {tracker_id: key, tracker_url: url}
-> ack(zone, map)
```

## 6. Retraits

- `ports/adapters/jira_client.py::JiraClient` (REST) supprimé ; `FakeJiraClient` gardé.
- `build_jira_tracker` + lecture `JIRA_*` supprimés.
- `JiraTracker` (REST) remplacé par `QueueTracker`.
- Tests REST de TSK-12 (STO-02) adaptés au mode queue.

## 7. Plan de test (hermétique)

| Test | Cible |
|---|---|
| `QueueTracker.create` enqueue op + ref local:N | SyncJournal(tmp) |
| scaffolder via QueueTracker → 6 ops, parent_local_id corrects | SyncJournal(tmp) |
| `tracker_pending` renvoie les ops triées | tool + tmp project |
| `tracker_ack` persiste refs + vide outbox | tool + ScaffoldState |
| re-scaffold idempotent → 0 op | ScaffoldState |
| non couplé → NullTracker, 0 op | settings vide |
| `JiraClient` REST absent du module | import/grep |
