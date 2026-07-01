---
titre: Architecture cible
phase: P-cadrage
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 001-Story-Port-Tracker
code: TEC-ARC
document: 03-TEC-ARC-architecture-cible
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/tec-arc
---

# 🏛️ Architecture cible — Port Tracker (STO-TRACKER-01)

Abstraction agnostique entre le modèle fractal local (Project / Epic / Story /
Task) et un tracker externe. Le cœur appelle le port ; un adapter concret
(Jira, …) le satisfait. Formalise les décisions DEC-01 à DEC-06.

## Principes directeurs

- **Cœur agnostique** : aucune dépendance tracker dans le noyau (DEC-03).
- **Effortless = source de vérité** : push sortant ; pull au seul import initial.
- **Identité partagée et persistée** : chaque objet connaît son équivalent distant
  (DEC-02). Mapping canonique à 4 niveaux (DEC-01).
- **Résilience** : projection best-effort, jamais bloquante ; rejeu garanti (DEC-05).

## Key Components

### 1. `Tracker` (typing.Protocol)
Contrat unique, métier commun aux 4 niveaux. Cinq opérations :

```python
class Tracker(Protocol):
    def discover_taxonomy(self, project_ref: ProjectRef) -> Taxonomy: ...
    def create(self, level: Level, payload: ObjectPayload) -> TrackerRef: ...
    def transition(self, ref: TrackerRef, status: str) -> None: ...
    def log_work(self, ref: TrackerRef, minutes: int, comment: str) -> None: ...
    def import_tree(self, project_ref: ProjectRef) -> list[ImportedObject]: ...
```

- `Level` ∈ {project, epic, story, task} — les 4 niveaux canoniques (DEC-01).
- Aucune classe de base imposée : toute impl satisfaisant la signature convient.

### 2. `NullTracker`
Adapter par défaut (no-op testable) : retourne des refs vides, ne pousse rien.
Actif tant qu'aucun tracker n'est configuré → fonctionnement local intact.

### 3. Modèle d'identité
- Champs canoniques `tracker_id` + `tracker_url` ajoutés à `epic.json`,
  `story.json`, `task.json` (DEC-02, non optionnels).
- Niveau projet : `settings.tracker = { type, project_id, project_url }` dans
  `effortless.json` ; propagé à SecondBrain (frontmatter namespacé).
- Règle d'identité : quand couplé, l'ID Effortless EST la clé d'issue.

### 4. `Taxonomy` + cache
- `discover_taxonomy` résout types / transitions / champs réels au premier
  couplage (DEC-04).
- Résultat persisté `.effortless/tracker_taxonomy.json` (cache projet,
  invalidation manuelle). Mapping Todo/Doing/Done → transitions résolu ici.
- Divergence de structure → l'agent propose un mapping (arbitrage utilisateur).

### 5. `SyncJournal` (outbox rejouable)
- Toute projection échouée (tracker injoignable) est consignée comme **migration**
  en attente (DEC-05).
- Rejeu idempotent dès reconnexion ; chaque migration est **flaggée jouée + timestamp**.
- Stockage `.effortless/tracker_outbox/` (une migration par fichier, ordonnée).

### 6. Résolution de l'adapter (fabrique)
- `resolve_tracker(settings) -> Tracker` : lit `settings.tracker.type`, instancie
  l'adapter correspondant ou `NullTracker` si absent.
- L'adapter Jira concret est orchestré côté agent via les tools MCP Atlassian
  (createJiraIssue, transitionJiraIssue, addWorklogToJiraIssue, …).

## Mapping canonique 4 niveaux (DEC-01)

| Effortless | Jira (base) | Opération de création |
|------------|-------------|-----------------------|
| Project | Project | (espace, pré-existant) |
| Epic | Epic | create(epic) |
| Story | Story / Task (niv.3) | create(story) |
| Task | Sub-Task | create(task) |

## Flux principaux

1. **create** : payload local → `create(level, …)` → `TrackerRef` (id+url)
   persistée sur l'objet.
2. **transition** : changement Todo/Doing/Done → `transition(ref, status)` via
   mapping de taxonomie.
3. **log_work** : rapport d'intervention → `log_work(ref, minutes, comment)` ;
   cumul (rollup) Task → Story.
4. **import** : `import_tree(project_ref)` reverse-mappe une structure existante
   (read-mostly, non réécrite).
5. Tout push échoué → `SyncJournal` → rejeu ultérieur.

## Limites de périmètre (DEC-06)

Cette Story livre le **contrat + NullTracker + modèle d'identité + SyncJournal**
(tous agnostiques). L'**implémentation Jira réelle** (discover_taxonomy effectif,
mapping fin des champs, estimation `timeoriginalestimate`, transitions concrètes)
est portée par **STO-TRACKER-02**.
