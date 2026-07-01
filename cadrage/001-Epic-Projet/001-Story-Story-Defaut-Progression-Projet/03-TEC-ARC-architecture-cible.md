---
titre: Architecture cible
phase: P-cadrage
statut: En cours
type: cadrage-story
projet: Effortless
epic: 001-Epic-Projet
story: 001-Story-Story-Defaut-Progression-Projet
code: TEC-ARC
document: 03-TEC-ARC-architecture-cible
tags:
  - cadrage/story
  - cadrage/001-epic-projet
  - cadrage/tec-arc
---

# 🏛️ Architecture cible — Modèle Epic/Story/Task & couplage tracker

## Principe directeur

Un **cœur de domaine agnostique** possède le modèle (Epic / Story / Task, OPALE
par Story). Tout le reste — Jira, analyse de code, recherche web, boucle
d'exécution, symbiose vault — est branché en **périphérie** via des ports, sans
que le domaine ne connaisse leurs détails. Effortless reste pleinement fonctionnel
en local, sans aucun connecteur externe.

## Vue en couches

```
            ┌─────────────────────────────────────────────┐
            │              Surfaces                        │
            │   MCP tools · CLI · Web UI · Anti-drift hook │
            └───────────────────┬─────────────────────────┘
                                │  (appels de cas d'usage)
            ┌───────────────────▼─────────────────────────┐
            │           Cœur de domaine (agnostique)       │
            │  Epic · Story · Task · Phase OPALE (/Story)  │
            │  Gate de phase · Registres (décisions, BQO)  │
            └───┬───────┬──────────┬──────────┬────────────┘
                │       │          │          │   (ports)
        ┌───────▼─┐ ┌───▼────┐ ┌───▼─────┐ ┌──▼──────────┐
        │ Tracker │ │Discovery│ │ Pattern │ │  Migration  │
        │ adapter │ │ adapter │ │  store  │ │   engine    │
        │ (Jira)  │ │(wlReForge│ │         │ │ (ladder)    │
        │         │ │ archeo) │ │         │ │             │
        └─────────┘ └─────────┘ └─────────┘ └─────────────┘
                │
        ┌───────▼─────────┐   ┌──────────────────┐
        │  Sync engine    │   │ Autonomous loop  │
        │ (push / import) │   │  (step machine)  │
        └─────────────────┘   └──────────────────┘
                                       │
                            ┌──────────▼──────────┐
                            │ SecondBrain symbiose│
                            └─────────────────────┘
```

## Key Components

### 1. Cœur de domaine (Core)

Entités de premier rang **Epic / Story / Task**, persistées localement
(`.effortless/`). Porte la position **OPALE par Story** (plus de `current_phase`
global), les registres (décisions, BQO) et le **gate de phase** Story-scopé.
Aucune dépendance sortante : ne connaît ni Jira ni le système de fichiers de cadrage
autrement que par des ports.

- Réf. décisions : DEC-01 (modèle natif), DEC-02 (OPALE/Story), DEC-08 (1 Epic:N).

### 2. Tracker adapter (port + implémentation Jira)

Port `Tracker` (créer / transitionner / logger / importer) ; implémentation Jira en
première cible. Mappe le modèle interne vers les types réels de l'instance
(découverts, non supposés). Jira est une **projection** : Epic→Epic, Story→Story,
Task→Sous-tâche, worklog+commentaire sur la Sous-tâche (rollup Story), estimation
en heures, Tests Xray à la recette.

- Réf. : DEC-04 (push+import), DEC-05 (worklog), DEC-06 (Xray), DEC-07 (estimation),
  DEC-15 (coexistence Jira). Ports ouverts à d'autres trackers (GitLab, Linear, ADO).

### 3. Discovery adapter (analyse de code)

Port `Discovery` alimenté par `archeo`, `repo_analyzer` et **wlReForge** (à faire
évoluer pour produire directement le format Epic/Story/Task). Fournit la matière du
niveau N0 (carte, stack, topologie, smells, clusters, frontières) et la dérivation
du backlog.

- Réf. : DEC-12 (dérivation auto + arbitrage), DEC-18 (évolution wlReForge).
- Dérivation : cluster/frontière → **Epic** ; smell/use-case/composant → **Story** ;
  élément concret → **Sous-tâche**.

### 4. Pattern store

Catalogue de patterns cibles par stack. Hydraté par **recherche web approfondie**
par stack identifiée ; enrichissable. Expose un **gabarit standard** (modèle à
remplir) qui sert de format de descripteur pour tout pattern fourni par un projet,
un framework ou l'utilisateur.

- Réf. : DEC-10 (store + format). Synergie avec le framework maison de cadrage
  technique multiplateforme.

### 5. Migration engine (ladder N0–N3)

Orchestre l'onboarding brownfield à paliers stables (Observation / Cadrage / Refacto
cadrée / Adoption). Au N2, génère un backlog `[MIGRATION]` (Epics/Stories propres),
chaque Story = petite passe OPALE gardée par tests + anti-drift, sur **branche
dédiée**, merge sur arbitrage. Réutilise `migration_planner` (variantes M-*) adapté
au scope Story. Filet de sécurité dimensionné au ROI.

- Réf. : DEC-09 (ladder), DEC-11 (philosophie), DEC-13 (idempotence), DEC-14
  (branche), DEC-16 (ROI), DEC-17 (adaptation migration_planner).

### 6. Sync engine

Applique la politique **push + import ponctuel** : pousse les créations/transitions/
worklogs vers le tracker ; importe (read-mostly) à l'initialisation brownfield.
Effortless ne possède que ce qu'il crée.

- Réf. : DEC-04, DEC-15.

### 7. Autonomous loop

State machine `step` (Plan → Implementation → Recette → Correction → …), **scopée à
une Story** : son objectif est de compléter les tâches de la Story active. Vit dans
la phase Execute d'OPALE.

- Réf. : DEC-03 (axe « step » orthogonal), DEC-02.

### 8. Gate de phase & validation

Valide les documents de cadrage requis **par Story**, les placeholders, les sections,
et l'état des questions (impact-aware). Note de cadrage : le statut du BQO doit
devenir impact-aware (finding dogfood — story `[CORE] gate phase`).

### 9. SecondBrain symbiose

À chaque transition de phase, synchronise `context.md` + crée une archive datée dans
le vault. Déjà opérationnel (observé à la transition O→P).

## Flux principaux

- **Greenfield + Jira** : cadrage OPALE (Stories méta de l'Epic [PROJET]) → backlog
  → scaffold Epics MVP → par Story : run OPALE → tasks → projection Jira.
- **Brownfield** : N0 discovery → N1 cadrage + import Jira → N2 backlog [MIGRATION]
  + refacto branchée → N3 adoption.
- **Exécution** : Autonomous loop sur la Story active → push d'état/worklog au fil
  de l'eau.

## Frontières & ports (contrats à spécifier en Articuler)

- `Tracker` : create/transition/worklog/import (impl. Jira).
- `Discovery` : scan → primitives structurelles (impl. wlReForge/archeo).
- `PatternStore` : résoudre(stack) → descripteur cible.
- `MigrationEngine` : planifier(niveau) → Epics/Stories.

Ces contrats, le schéma du descripteur de pattern, le mapping Xray et le mapping des
transitions Jira sont les livrables de la phase **Articuler**.
