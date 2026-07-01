---
titre: Contrat api
phase: A-specs
statut: En cours
type: cadrage-story
projet: Effortless
epic: 001-Epic-Projet
story: 001-Story-Story-Defaut-Progression-Projet
code: TEC-API
document: 06-TEC-API-contrat-api
tags:
  - cadrage/story
  - cadrage/001-epic-projet
  - cadrage/tec-api
---

# 🔌 Contrat d'API — Ports, schémas & mappings

> Premier jet. Niveau contrat (signatures, schémas, mappings). Les blocs **À
> RATIFIER** sont des strawmen à valider.

## Modèle de domaine

```jsonc
// Epic
{ "id": "IFX-7", "zone": "IRIS", "title": "Création du composant Factur-X",
  "stories": ["IFX-13", "IFX-14"], "kind": "functional|root|migration" }

// Story  (porte sa propre position OPALE)
{ "id": "IFX-13", "epic": "IFX-7", "zone": "IRIS",
  "title": "Cadrage technique & architecture",
  "opale_phase": "O-analyse|P-cadrage|A-specs|L-plan|E-execute",
  "tasks": ["IFX-30"], "branch": "story/IFX-13" }

// Task  (projetée en Sous-tâche)
{ "id": "IFX-30", "story": "IFX-13", "zone": "IRIS", "title": "…",
  "state": "Todo|Doing|Done", "estimate_h": 2.0, "spent_h": 1.5 }
```

Sans tracker : `id` = `TSK-<n>` ; avec tracker : `id` = clé native `<CODE>-N`.

## Port `Tracker`

```
create_epic(zone, title) -> key
create_story(epic_key, zone, title) -> key
create_task(story_key, zone, title, estimate_h) -> key
transition(key, state)                     // Todo|Doing|Done -> statut natif
log_work(key, spent_h, comment)            // worklog + commentaire (Sous-tâche)
import_project(url) -> {epics, stories, tasks}   // read-mostly
discover_taxonomy(url) -> issue_type_tree
```

Implémentation Jira (via MCP Atlassian) :

| Opération | Appel Jira |
|-----------|-----------|
| create_* | `createJiraIssue` (issuetype Epic/Story/Sous-tâche) |
| transition | `transitionJiraIssue` (+ `getTransitionsForJiraIssue` au mapping) |
| log_work | `addWorklogToJiraIssue` + commentaire worklog |
| import_project | `searchJiraIssuesUsingJql` |
| discover_taxonomy | `getJiraProjectIssueTypesMetadata` |

### Mapping des champs

| Domaine | Champ Jira |
|---------|-----------|
| zone (`[ZONE]`) | préfixe du summary (hérité de l'Epic) |
| estimate_h | `timeoriginalestimate` (heures) |
| spent_h | worklog (`timeSpent`) |
| rang | `customfield_10019` (LexoRank, lecture seule) |

### Mapping des transitions — ✅ ratifié

Workflow cycle en V (affiné à l'import via `getTransitionsForJiraIssue`) :

| État Effortless | Statut Jira |
|-----------------|-------------|
| Todo | A faire |
| Doing | En cours |
| Done | Terminé |

## Port `Discovery`

```
scan(path) -> {stack, topology, smells[], clusters[], boundaries[], use_cases[]}
```

Implémentations : `wlReForge` (PC Soft), `archeo`, `repo_analyzer`.

### Contrat de sortie wlReForge → backlog — ✅ ratifié

| Primitive | Niveau | Règle de dérivation |
|-----------|--------|---------------------|
| cluster / boundary | **Epic** | 1 contexte cohésif = 1 Epic `[ZONE]` |
| smell groupé / use_case / composant à migrer | **Story** | 1 transformation cohérente = 1 Story |
| entity / élément (`inventory`) | **Sous-tâche** | 1 édition concrète = 1 Sous-tâche |

→ Tâche d'évolution wlReForge : émettre ce format nativement (DEC-18).

## Port `PatternStore`

```
resolve(stack) -> PatternDescriptor | null
template() -> PatternDescriptor (gabarit vide à remplir)
hydrate(stack)    // recherche web approfondie -> ajoute au store
```

### Schéma `PatternDescriptor` — ✅ ratifié (affinable depuis le framework maison)

```yaml
id: hexagonal-python            # slug
stack: [python]                 # stacks cibles
intent: "Isoler le domaine des I/O"
layers:                         # structure cible
  - name: domain
    rules: ["aucune dépendance sortante"]
  - name: adapters
    rules: ["implémentent les ports du domaine"]
smells_resolved: [god-object, leaky-abstraction]
steps:                          # gabarit de découpe en Stories
  - "extraire les ports"
  - "déplacer la logique métier"
acceptance: ["tests verts", "anti-drift no-drift"]
source: builtin|web|user|framework
```

## Port `MigrationEngine`

```
plan(level, discovery, pattern) -> {epics[], stories[]}   // niveau N0..N3
run_story(story)        // branche dédiée, passe OPALE, anti-drift
roi_score(target) -> float   // risque × valeur -> dimensionne le filet
```

Réutilise `migration_planner` (variantes M-*) adapté au scope Story (DEC-17).

### Heuristique ROI — ✅ ratifié

```
roi = (risque × impact_métier) / coût_filet
risque   = f(complexité, couplage, absence de tests)
décision = filet complet si roi ≥ seuil_haut
           filet ciblé  si seuil_bas ≤ roi < seuil_haut
           aucun        si roi < seuil_bas
```

## Mapping Xray — optionnel (principe validé)

Projection **optionnelle**, activable par projet (amende DEC-06). Si activée :

| Concept recette | Entité Xray | Rattachement |
|-----------------|-------------|--------------|
| critère d'acceptation | **Test** | lié à la Story |
| campagne de la Story | **Test Plan** | 1 par Story |
| passe de recette | **Test Execution** | agrège les Tests |

## Surface MCP — évolutions

| Tool | Évolution |
|------|-----------|
| `effortless_phase_next` | scope **Story courante** |
| `effortless_task_add` | attache à la Story + projette en Sous-tâche |
| `effortless_status` | arbre Epic/Story + phase par Story |
| **nouveaux** | `effortless_epic_add`, `effortless_story_start`, `effortless_story_close`, `effortless_onboard`, `effortless_pattern_template` |
| `effortless_migrate_*` | adaptés au scope Story (DEC-17) |

## Récap — ratification

Blocs 1–4 **ratifiés** (transitions, contrat wlReForge→backlog, `PatternDescriptor`,
heuristique ROI). Projection **Xray optionnelle** (principe validé, activable par
projet). `PatternDescriptor` affinable ultérieurement depuis le framework maison.
