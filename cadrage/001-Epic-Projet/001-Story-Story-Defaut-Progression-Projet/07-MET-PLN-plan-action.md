---
titre: Plan action
phase: L-plan
statut: En cours
type: cadrage-story
projet: Effortless
epic: 001-Epic-Projet
story: 001-Story-Story-Defaut-Progression-Projet
code: MET-PLN
document: 07-MET-PLN-plan-action
tags:
  - cadrage/story
  - cadrage/001-epic-projet
  - cadrage/met-pln
---

# 🚀 Plan d'action — Implémentation du modèle Epic/Story/Task & couplage tracker

Le backlog ci-dessous est exprimé dans le **nouveau modèle** (dogfood) : il devient
les premières Epics/Stories de la feature. Découpe par Epic `[ZONE]`, chaque Story =
une passe OPALE livrable.

## Séquencement

1. **[CORE]** d'abord (le modèle conditionne tout le reste).
2. **[TRACKER]** et **[MIGRATION]** en parallèle une fois le Core posé.
3. **[PATTERN]** alimente [MIGRATION] (N2).
4. **[TOOLING]** suit l'évolution des ports.
5. **[DOGFOOD]** wlReForge = premier client réel du ladder.

## Task Breakdown

### Epic [CORE] — Modèle de domaine & gate Story-scopé

- **Story** Entités Epic/Story/Task de premier rang + persistance `.effortless/`.
- **Story** Migration du state model : `current_phase` global → `Story.opale_phase`.
- **Story** Docs de cadrage Story-scopés (`resolve_phase_docs_dir`, `required_documents`).
- **Story** Gate de phase **impact-aware** (finding dogfood : statut BQO vs impact).
- **Story** Vocabulaire : purge « phase » au sens itération → « Story » (README, SKILL).

### Epic [TRACKER] — Adapter Jira (projection)

- **Story** Port `Tracker` (create/transition/log_work/import/discover_taxonomy).
- **Story** Implémentation Jira (mapping types, champs, `[ZONE]`, estimation heures).
- **Story** Mapping des transitions (cycle en V, affiné à l'import).
- **Story** Worklog + commentaire sur Sous-tâche, rollup Story.
- **Story** Import read-mostly + coexistence (greffe Epic `[MIGRATION]`).
- **Story** (option) Projection Xray activable par projet.

### Epic [MIGRATION] — Onboarding ladder N0–N3

- **Story** Port `Discovery` + agrégation archeo / repo_analyzer / wlReForge.
- **Story** Dérivation structure → backlog (proposée, arbitrage utilisateur).
- **Story** `MigrationEngine` : `plan(level)` + `run_story` sur branche dédiée.
- **Story** Filet de sécurité dimensionné au ROI (`roi_score` + seuils).
- **Story** Idempotence du re-scan + exposition des divergences.

### Epic [PATTERN] — Pattern store

- **Story** Schéma `PatternDescriptor` + `template()` (gabarit à remplir).
- **Story** Hydratation par recherche web approfondie par stack.
- **Story** Résolution `resolve(stack)` + enrichissement projet/framework/utilisateur.

### Epic [TOOLING] — Surfaces

- **Story** Nouveaux tools MCP : `epic_add`, `story_start`, `story_close`, `onboard`,
  `pattern_template`.
- **Story** `status` → vue arbre Epic/Story + phase par Story.
- **Story** Web UI : `PhaseTimeline` par Story + vue arbre.

### Epic [DOGFOOD] — wlReForge

- **Story** Faire évoluer la production wlReForge vers le format Epic/Story/Task.
- **Story** wlReForge comme premier projet migré via le ladder (preuve end-to-end).

## Jalons

- **M1** : Core posé (modèle + gate Story-scopé) → Effortless tourne en arbre.
- **M2** : Tracker Jira fonctionnel (push + import) sur un projet pilote.
- **M3** : Ladder N0–N1 (observe + frame) opérationnel.
- **M4** : N2 refacto cadrée + pattern store sur wlReForge.
- **M5** : N3 adoption + surfaces complètes.

## Dépendances & risques

- [CORE] bloque tout : prioriser la migration du state model.
- `PatternDescriptor` affinable depuis le framework maison (non bloquant pour M1–M3).
- Migration des projets existants à plat : prévoir un chemin (Effortless early-stage,
  cassure acceptable).
