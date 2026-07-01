---
titre: Contrat api
phase: A-specs
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 004-Story-Discover-Medie-Issue-Type
code: TEC-API
document: 06-TEC-API-contrat-api
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/tec-api
---

# 🔌 Contrat API — Discover médié + issue_type_id (STO-TRACKER-04)

## 1. `QueueTracker` (modif)
```python
class QueueTracker:
    def __init__(self, journal, levelmap=None, taxonomy=None):
        # taxonomy: {level -> issue_type_id} (depuis settings.tracker.taxonomy)
        self._taxonomy = taxonomy or {}
        ...
    def create(self, payload):
        ...
        self._journal.enqueue("create", {
            "local_id": local_id,
            "level": payload.level,
            "issue_type_name": self._levelmap.get(payload.level, payload.level),
            "issue_type_id": self._taxonomy.get(payload.level),   # NOUVEAU (None si absent)
            "title": payload.title,
            "parent_local_id": parent_local,
            "labels": list(payload.labels or []),
        })
        return TrackerRef(f"local:{self._seq}", "")

def build_queue_tracker(cfg):
    from effortless_mcp.ports.sync_journal import SyncJournal
    return QueueTracker(SyncJournal(cfg.get("__root__") or "."),
                        taxonomy=cfg.get("taxonomy") or {})
```

## 2. Nouvel outil
```python
@mcp.tool()
def effortless_tracker_discover_ack(taxonomy_json: str) -> str:
    # taxonomy_json = '{"epic":"10000","story":"10007","task":"10095"}'
    # -> settings.tracker.taxonomy = parsed ; écrit effortless.json
    # validations : dict {str: str}, sinon erreur.
```

## 3. `effortless_tracker_couple` (message)
Ajoute une ligne : « Fournis la taxonomie via discover (agent :
getJiraProjectIssueTypesMetadata → effortless_tracker_discover_ack) avant scaffold. »

## 4. Procédure flush agent (mise à jour)
```
createJiraIssue(projectKey, issueTypeName=issue_type_name, summary=title,
    parent=map[parent_local_id],
    additional_fields={"issuetype": {"id": issue_type_id}, "labels": labels})
# si issue_type_id null -> omettre additional_fields.issuetype (fallback nom)
```

## 5. Tests
| Test | Cible |
|---|---|
| `discover_ack` persiste settings.tracker.taxonomy | tool + tmp project |
| QueueTracker(taxonomy).create stampe issue_type_id | unit |
| scaffold après ack → ops avec issue_type_id (task=10095) | tool flow |
| sans taxonomie → issue_type_id null, pas d'échec | unit |
| `discover_ack` rejette JSON invalide | tool |
