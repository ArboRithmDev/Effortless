---
phase: A-specs
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 002-Story-Adapter-Jira-Concret
code: TEC-API
document: 06-TEC-API-contrat-api
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/tec-api
---

# 🔌 Contrat API — Adapter Jira concret (STO-TRACKER-02)

Interfaces précises à implémenter. S'aligne sur les types existants de
`ports/tracker.py` (`ObjectPayload`, `Taxonomy`, `TrackerRef`, `ProjectRef`,
`Tracker` Protocol).

## 1. `ports/adapters/jira_client.py` — frontière I/O

Toute communication réseau est ici. `JiraTracker` ne dépend que de cette interface.

```python
class JiraClient:                       # impl REST Jira Cloud v3
    def __init__(self, base_url: str, email: str, api_token: str): ...
    def get_issue_types(self, project_key: str) -> list[dict]:
        # -> [{"id","name","hierarchyLevel","subtask"}]
    def get_transitions(self, issue_key: str) -> list[dict]:
        # -> [{"id","to_status_id","to_status_name"}]
    def create_issue(self, *, project_key: str, issue_type_id: str, summary: str,
                     parent_key: str | None = None, assignee: str | None = None,
                     description: str | None = None,
                     labels: list[str] | None = None) -> dict:
        # -> {"key","id","url"}
    def search(self, jql: str, fields: list[str] | None = None) -> list[dict]:
        # -> [{"key", ...}]
    def transition_issue(self, issue_key: str, transition_id: str) -> None: ...   # post-MVP
    def add_worklog(self, issue_key: str, seconds: int, comment: str) -> None: ... # post-MVP
```

`FakeJiraClient(fixtures)` : même interface, store en mémoire. Seedé avec types +
transitions (fixtures EFL/IFX). `create_issue` génère une clé incrémentale
(`EFL-<n>`), enregistre parent + labels. `search` filtre par label. **Zéro réseau.**

## 2. `ports/adapters/jira.py` — adapter

```python
class JiraTracker:                      # satisfait le Protocol Tracker
    def __init__(self, client, project_key: str, taxonomy: Taxonomy | None = None): ...

    def discover_taxonomy(self, project: ProjectRef) -> Taxonomy:
        # client.get_issue_types + get_transitions ->
        #   issue_types: {level -> issue_type_id}   (epic/story/task ; task -> Sous-tâche)
        #   transitions: {LocalStatus -> transition_id}  (Todo/Doing/Done)
        # Divergence vs mapping canonique -> consignée (log), pas bloquant.

    def create(self, payload: ObjectPayload) -> TrackerRef:
        # type_id = taxonomy.issue_types[payload.level]
        # parent_key = payload.parent_ref.tracker_id if payload.parent_ref else None
        # r = client.create_issue(project_key, type_id, payload.title,
        #         parent_key=parent_key, assignee=None,
        #         description=payload.description, labels=payload.labels)
        # -> TrackerRef(r["key"], r["url"])

    def transition(self, ref, status):  raise NotImplementedError   # post-MVP
    def log_work(self, ref, minutes, comment):  raise NotImplementedError  # post-MVP
    def import_tree(self, project):  return []   # post-MVP

def build_jira_tracker(cfg: dict):       # factory enregistrée
    client = JiraClient(cfg["base_url"], cfg["email"], cfg["api_token"])
    return JiraTracker(client, cfg["project_id"])
# register_adapter("jira", build_jira_tracker)
```

> **Note** : `Taxonomy.issue_types` stocke l'**id** de type Jira (et non le nom) —
> `create_issue` cible `issuetype.id`. Précision vs commentaire d'origine de
> STO-TRACKER-01 (« nom de type »).

## 3. Extension de `ObjectPayload` (additive, port inchangé en nb d'ops)

```python
@dataclass(frozen=True)
class ObjectPayload:
    level: Level
    title: str
    parent_ref: Optional[TrackerRef] = None
    estimate_minutes: Optional[int] = None
    description: Optional[str] = None
    labels: Optional[List[str]] = None     # NOUVEAU — générique ; NullTracker ignore,
                                           # JiraTracker -> labels Jira. Porte le marqueur
                                           # d'idempotence du scaffold.
```

## 4. `services/scaffolder.py` — composer (agnostique)

```python
def scaffold_project_from_template(tracker, project_ref: ProjectRef, template: dict,
                                   zone: str, scaffold_state) -> dict:
    # 1. Idempotence (MVP) : si scaffold_state contient déjà la zone -> skip, retourne refs.
    # 2. Walk template (DFS) : create Epic racine avec labels=[f"effortless-scaffold:{zone}"],
    #    puis chaque enfant avec parent_ref = ref du parent créé. assignee=null, pas d'estimate.
    #    N'appelle QUE tracker.create() — aucun accès direct au client (agnosticité, DEC-01).
    # 3. Persiste les refs créées dans scaffold_state (zone -> {node_id: TrackerRef}).
    # -> {node_id: TrackerRef}
```

`scaffold_state` = abstraction de persistance locale
(`.effortless/scaffold_state.json`, zone → refs).

## 5. Template externalisé — `templates/jira_project_scaffold.json`

```json
{
  "zone_prefix": "PROJET",
  "root": {
    "level": "epic", "title": "[PROJET]",
    "children": [
      {"level": "story", "title": "[PROJET] Pilotage"},
      {"level": "story", "title": "[PROJET] Analyse et spécifications détaillées"},
      {"level": "story", "title": "[PROJET] Divers (Initialisation, déploiement, documentation)",
       "children": [
         {"level": "task", "title": "[PROJET] Déploiement"},
         {"level": "task", "title": "[PROJET] Documentation"}
       ]}
    ]
  }
}
```

Initialisé depuis l'observation d'IFX-1. Surchargeable par le paramètre
`template` de l'outil `effortless_tracker_scaffold`.

## 6. Config tracker (`settings.tracker` pour Jira)

```json
{"type": "jira", "project_id": "EFL",
 "project_url": "https://simondialtissus.atlassian.net/browse/EFL",
 "base_url": "https://simondialtissus.atlassian.net",
 "email": "<env>", "api_token": "<env>"}
```

`email`/`api_token` résolus depuis l'environnement (jamais en clair dans le repo).

## 7. Idempotence — sémantique précise

- **MVP (garde primaire)** : état local `scaffold_state.json` (zone → refs). Re-run →
  skip déterministe, zéro réseau.
- **Marqueur durable** : label `effortless-scaffold:<zone>` posé sur l'Epic racine
  à la création (visibilité externe + base d'un futur reconcile).
- **Reconcile Jira-as-truth** (re-`search` du label quand l'état local est perdu) :
  documenté, **hors MVP** (éviterait un re-scaffold après reset local). Suit la
  garde locale ; le label primera en cas de divergence une fois implémenté.

## 8. Plan de test (hermétique)

| Test | Cible |
|---|---|
| `discover_taxonomy` mappe types+transitions | `FakeJiraClient` seedé EFL |
| `create` Epic/Story/Sous-tâche + parent + label | `FakeJiraClient` |
| scaffolder crée l'arbre 6 nœuds, parents câblés | `FakeJiraClient` |
| scaffolder idempotent (re-run = 0 création) | `FakeJiraClient` + `scaffold_state` |
| `resolve_tracker({"type":"jira"})` → `JiraTracker` | `register_adapter` |
| projet non couplé → NullTracker, zéro I/O | settings vide |
