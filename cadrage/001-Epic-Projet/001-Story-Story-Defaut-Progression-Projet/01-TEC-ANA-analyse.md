---
phase: O-analyse
statut: En cours
type: cadrage-story
projet: Effortless
epic: 001-Epic-Projet
story: 001-Story-Story-Defaut-Progression-Projet
code: TEC-ANA
document: 01-TEC-ANA-analyse
tags:
  - cadrage/story
  - cadrage/001-epic-projet
  - cadrage/tec-ana
---

# 🔎 Analyse — Modèle Epic/Story/Task & désambiguïsation « phase »

## Contexte

Le dogfood d'Effortless sur lui-même révèle un **trou structurel** doublé d'une
**dette sémantique** :

1. **Trou structurel** : entre le projet et la tâche, il manque une couche de
   décomposition. Le projet est aujourd'hui un seul gros passage OPALE avec une
   liste plate de tâches. Pas de regroupement intermédiaire.
2. **Dette sémantique** : le mot « phase » désigne deux objets distincts — la
   macro-étape méthodologique OPALE **et** l'itération de développement —, ce qui
   brouille les instructions passées à l'agent.

Les deux se résolvent ensemble en promouvant **Epic > Story > Task** au rang de
**modèle de domaine natif** (local d'abord, indépendant de tout tracker). Cette
couche comble le trou, et la **Story** fournit le nom propre de « l'itération de
développement » — ce qui libère « phase » pour désigner **exclusivement** OPALE.

## Le problème sémantique — deux sens de « phase »

| Concept | Sens actuel | Ancrage code |
|---------|-------------|--------------|
| **A — Phase OPALE** | Macro-étape méthodologique (Observer, Positionner, Articuler, Lancer, Execute) | `current_phase`, `Task.phase`, `effortless_phase_next`, `workflow.phases`, frontmatter `phase:`, `PhaseTimeline` |
| **B — Phase de développement** | Itération de réalisation (le cycle de travail qui produit un incrément) | partiellement `step` (`loop_state.json.step`) ; ailleurs appelée « phase » dans README/SKILL |

La collision est **sémantique et documentaire** : le code utilise déjà `step`
pour la boucle, mais la prose (README, SKILL, instructions agent) appelle « phase »
les deux concepts. Un agent qui lit « passe à la phase suivante » ne sait pas s'il
s'agit d'avancer dans OPALE ou de clore une itération de développement.

## La distinction à imposer — Story ≠ Phase OPALE

C'est le cœur de la clarification. **Story** et **phase OPALE** sont deux axes
**orthogonaux** :

- **La Story EST la « phase de développement »** (concept B). C'est le conteneur
  d'itération : un objectif de réalisation, son jeu de tâches, ses documents de
  cadrage propres. Identité = clé `<CODE>-N`.
- **La phase OPALE est une position méthodologique progressée À L'INTÉRIEUR d'une
  Story** (concept A). Une Story traverse Observer → Positionner → Articuler →
  Lancer → Execute.

| Axe | Objet | Question répondue | Avance via |
|-----|-------|-------------------|------------|
| **Itération** | Story | « Quel incrément je produis ? » | ouvrir / clore une Story |
| **Méthode** | Phase OPALE | « Où j'en suis dans le process de CETTE Story ? » | `phase_next` (scopé Story) |

**Règle de vocabulaire, non négociable** :

- « **phase** » ne désigne **JAMAIS** une Story ni une itération. Uniquement OPALE.
- « **Story** » désigne l'itération de développement (ex concept B).
- La boucle d'exécution automatique conserve « **step** » / « **état** » (state
  machine interne, encore un autre axe, orthogonal aux deux précédents).

Trois mots, trois axes, zéro recouvrement.

## État actuel — le singleton global

Aujourd'hui le projet porte **un** `workflow.current_phase` global et une liste de
tâches à plat. Conséquence : impossible de mener plusieurs itérations OPALE en
parallèle ou en série sur des périmètres différents ; le projet est traité comme
une itération unique. C'est exactement le trou que la couche Story comble.

## Référence terrain — projet IFX

Le projet Jira `IFX` ([IFX] Intégration Factur-X, catégorie « Projet cycle en V »)
sert de référence concrète. Hiérarchie et conventions observées :

```
Epic IFX-1  [PROJET]                              ← Epic racine = scaffold méta/PM
 ├─ Story IFX-2  [PROJET] Pilotage                       11h
 ├─ Story IFX-3  [PROJET] Analyse & spécifications        7,5h
 └─ Story IFX-4  [PROJET] Divers (init, déploiement…)
     ├─ Sous-tâche IFX-5 [PROJET] Déploiement
     └─ Sous-tâche IFX-6 [PROJET] Documentation
Epic IFX-7  [IRIS] …                              ← Epic fonctionnelle (zone MVP)
 ├─ Story IFX-13 [IRIS] Cadrage technique & archi         1,5h
 ├─ Story IFX-14 [IRIS] Déploiement socle infra           1,5h
 └─ … (5 Stories sous IFX-7)
Epic IFX-12 [IMPRESSION] …  (3 Stories)
```

Enseignement décisif : **même le cadrage global est une Story** (`[PROJET] Analyse
& spécifications`, sous l'Epic racine). Le modèle reste donc **uniforme** — tout
est Story, chaque Story run OPALE — sans phase projet spéciale.

Conventions retenues :

- **Clé** : `<CODE>-N`, séquentielle, portée projet. Identité unique.
- **Cardinalité** : `1 Epic : N Stories` (IFX-7 porte 5 Stories).
- **Tag `[ZONE]`** : préfixe hérité de l'Epic vers ses Stories et Sous-tâches.
- **Epic racine `[PROJET]`** : porte les Stories transverses (Pilotage, cadrage
  global, Divers). Scaffold généré automatiquement à l'initialisation.
- **Temps** : worklog en heures (format `0,5h`), `timeoriginalestimate` disponible.
- **Rang** : `customfield_10019` = LexoRank, géré par Jira, jamais saisi.
- **Types** : Epic / Story / Tâche / Sous-tâche, + **Xray** (Test / Test Set /
  Test Plan).

## Vision cible — modèle local-first, Jira en projection

Epic / Story / Task sont des **entités de domaine de premier rang**, persistées
**localement**, que Jira soit branché ou non. Le projet devient un **arbre fractal** :

```
Projet = ensemble d'Epics
  Epic [PROJET]   → Stories méta (cadrage global → produit les autres Epics, pilotage…)
  Epic [ZONE-x]   → Stories de livraison
    Story → run OPALE (Observer → Execute) + ses tâches + ses docs de cadrage
      Task → unité de travail ; miroir Jira (Sous-tâche) si couplage activé
```

**OPALE = process de Story** : la position OPALE n'est plus globale au projet,
elle est portée **par chaque Story**. Plus de singleton `current_phase` ; le projet
ne suit que la **Story courante** et l'arbre.

Jira est une **projection optionnelle** : quand il est couplé, chaque entité
locale est miroitée (Epic→Epic, Story→Story, Task→Sous-tâche). Sans Jira, le même
modèle vit en local avec des identifiants `TSK-…` de repli.

## Charte de nommage

| Élément Effortless | Jira | ID canonique | Summary |
|--------------------|------|--------------|---------|
| Composant MVP / zone | Epic | `<CODE>-N` | `[ZONE] <Verbe> <objet>` |
| Itération de dév (Story) | Story | `<CODE>-N` | `[ZONE] <résultat visé>` |
| Tâche | Sous-tâche | `<CODE>-N` | `[ZONE] <action>` |

Règle d'identité : quand Jira est couplé, l'ID Effortless **EST** la clé
`<CODE>-N` ; `TSK-…` n'est conservé qu'en mode local. Le tag `[ZONE]` est hérité
de l'Epic parente.

## Chaîne d'automatisation (projection Jira)

1. **Création de tâche** : `createJiraIssue` (Sous-tâche sous la Story courante),
   estimation poussée via `timeoriginalestimate` (heures) → la clé `<CODE>-N`
   retournée devient l'identifiant local de la tâche.
2. **Changement d'état** (Todo / Doing / Done) : `transitionJiraIssue` (mapping
   résolu à l'import via `getTransitionsForJiraIssue`).
3. **Rapport d'intervention** : `addWorklogToJiraIssue` (temps) + **commentaire**
   à chaque rapport, sur la Sous-tâche ; le cumul remonte à la Story.
4. **Recette** : la phase Execute/recette OPALE crée des **Tests Xray** rattachés
   à la Story et trace la couverture dans Jira.

## Architecture — cœur agnostique + adapter

Le cœur d'Effortless reste **agnostique du tracker**. Jira est branché via une
**couche d'adaptation** qui mappe le modèle interne (Epic / Story / Task) vers les
types réels de l'instance. Raisons : Jira optionnel ; autres trackers possibles
(GitLab, Linear, Azure DevOps) ; taxonomie custom à **découvrir**, pas supposer.

Sens de synchronisation : **Effortless = source de vérité**. Push vers Jira
(création, transition, worklog) ; pull **uniquement** à l'import initial. Pas de
réconciliation bidirectionnelle (évite la résolution de conflits).

## Onboarding brownfield — niveaux d'intégration

La reprise d'un projet non encore cadré par Effortless est un cas de premier plan,
traité comme une **échelle d'adoption à paliers stables** : l'utilisateur peut
s'arrêter à n'importe quel niveau.

| Niveau | Nom | Ce qui se passe | Code | S'appuie sur |
|--------|-----|-----------------|------|--------------|
| **N0** | Observation | Ingestion + reconstruction de contexte (archeo git, stack, topologie, smells / clusters / frontières) → carte + diagnostic | aucun | `mem-archeo`, `repo_analyzer`, wlReForge |
| **N1** | Cadrage (overlay) | Projet habillé du modèle : Epics / Stories dérivées de la structure + docs de cadrage + backlog ; import d'un Jira existant | aucun | modèle Story |
| **N2** | Refacto cadrée | Pattern cible identifié par stack → backlog `[MIGRATION]` (Epics / Stories propres), chaque Story = petite passe OPALE gardée par tests + anti-drift | incrémental réversible | migration_planner M-* |
| **N3** | Adoption complète | Projet Effortless-natif : refactor + nouveau passent par le modèle ; projection Jira | oui | tout |

### Migration = backlog auto-généré

La migration vers le pattern cible n'est pas un script monolithique : elle génère
ses **propres Epics et Stories** (`[MIGRATION]`), uniforme avec le modèle fractal.
Chaque Story de refacto est une petite passe OPALE, gardée par tests + anti-drift
(approche strangler-fig).

Philosophie « sans douleur » : on accepte **autant d'étapes que nécessaire** ;
Effortless décompose et orchestre, l'utilisateur n'orchestre rien
(« Effortless s'occupe de tout »).

### Dérivation structure → backlog

La structure découverte est projetée sur les trois niveaux. Pipeline :
`analyze_codebase` → clusters / frontières (Epics) → smells / use-cases / workflows
(Stories) → inventaire des éléments (Sous-tâches).

| Primitive découverte | Niveau | Exemple |
|----------------------|--------|---------|
| Cluster / frontière (contexte délimité) / zone cohésive | **Epic** `[ZONE]` | un module, un contexte délimité |
| Smell groupé / use-case à extraire / frontière à introduire / composant à migrer | **Story** | « extraire la couche d'accès données » |
| Édition concrète sur N éléments (`inventory`, `list_entities`, `field_lineage`) | **Sous-tâche** | toucher telles classes / procédures |

La dérivation est **proposée automatiquement** (heuristique), l'utilisateur
**arbitre** le découpage final.

### Pattern store

Le pattern cible par stack provient d'un **store de patterns** : un catalogue de
patterns de base proposé à l'utilisateur, **enrichissable** par un modèle fourni
par un projet, un framework ou l'utilisateur. Hydratation : identification des
stacks à scaffolder puis **recherche web approfondie** par stack pour alimenter le
store. Pour tout pattern fourni par l'utilisateur, une fonctionnalité fournit un
**modèle à remplir** — ce gabarit standardisé EST le format de descripteur. Synergie
identifiée avec le framework maison de cadrage technique multiplateforme de Ben.

### Coexistence avec un Jira existant

Si le legacy est déjà câblé à un projet Jira (Epics / Stories humaines) :

- **Import read-mostly** (N1) : Effortless reverse-mappe les issues existantes en
  contexte ; il ne les réécrit pas (elles restent possédées par l'humain).
- **Greffe** (N2) : le backlog de migration s'ajoute en Epic `[MIGRATION]` **dans
  le même projet Jira** → suivi du temps et reporting unifiés.
- Source de vérité : Effortless ne possède que ce qu'il **crée** (les issues de
  migration). Option alternative : projet Jira séparé pour la migration (isolation
  plus nette, reporting scindé).

### Isolation par branche

Toute transformation issue d'une migration est réalisée **sur une branche dédiée**.
Si la migration convient, **merge vers la branche principale sur arbitrage de
l'utilisateur**. Réversibilité : la branche (+ un commit par Story) est l'unité de
rollback. Worktree d'isolation envisageable pour mener plusieurs Stories sans
collision.

### Filet de sécurité dimensionné au ROI

Sur du legacy non testé, le filet de sécurité (tests de caractérisation / golden
master avant refacto) est **dimensionné au ROI** : effort proportionné au risque et
à la valeur, pas un golden master systématique.

## Décisions verrouillées (à formaliser en phase Positionner)

1. **Modèle natif** : Epic > Story > Task local d'abord, indépendant de Jira.
2. **OPALE = process de Story** : position OPALE portée par chaque Story ; plus de
   `current_phase` global. Arbre de Stories pur (l'Epic `[PROJET]` absorbe le
   cadrage global).
3. **Vocabulaire** : « phase » = OPALE uniquement ; « Story » = itération de
   développement ; « step »/« état » = boucle d'exécution. Trois axes orthogonaux.
4. **Sens de sync** : push + import ponctuel ; Effortless source de vérité.
5. **Grain du worklog** : sur la Sous-tâche, rollup automatique vers la Story.
6. **Xray** : intégré dès la v1 (la recette crée des Tests Xray).
7. **Estimation** : champ time-tracking en heures (`timeoriginalestimate`).
8. **Cardinalité** : 1 Epic : N Stories.
9. **Onboarding brownfield** : échelle de niveaux d'intégration N0–N3, paliers
   stables ; la migration génère ses propres Epics / Stories.
10. **Pattern store** : catalogue de patterns de base proposé, enrichissable
    (projet / framework / utilisateur), via un **format standard** de descripteur.
    Hydratation par recherche web approfondie + modèle à remplir pour patterns
    fournis par l'utilisateur. Synergie avec le framework maison de cadrage
    technique multiplateforme.
11. **« Sans douleur » = philosophie** « Effortless s'occupe de tout » : autant
    d'étapes que nécessaire, décomposées et orchestrées par Effortless.
12. **Dérivation & découpe** proposées automatiquement (clusters / smells /
    frontières), avec **arbitrage de l'utilisateur** sur le découpage final.
13. **Idempotence du re-scan** visée, **arbitrage de l'utilisateur** en cas de
    divergence (pas de réconciliation magique).
14. **Migration sur branche dédiée** ; merge vers la principale **sur arbitrage de
    l'utilisateur** ; rollback = branche + un commit par Story.
15. **Coexistence Jira** : import read-mostly des issues existantes ; migration
    greffée en Epic `[MIGRATION]` dans le même projet ; Effortless ne possède que
    ce qu'il crée.
16. **Filet de sécurité dimensionné au ROI** (pas de golden master systématique).
17. **Adaptation des outils existants** : `migration_planner` (variantes M-*) et
    `migrate_init` / `migrate_apply` adaptés au modèle Story-scopé ; la variante
    OPALE migration = process d'une Story de refacto.
18. **Évolution de wlReForge** : sa production doit matcher le modèle Effortless
    (Epic / Story / Task) ; wlReForge est lui-même un candidat à la migration.

## Questions ouvertes restantes (détail d'implémentation → Articuler)

- **Schéma du descripteur de pattern** : spécifier le gabarit standard du pattern
  store (s'appuyer sur le framework maison de cadrage technique multiplateforme).
- **Mapping Xray** : quelles entités créer (Test seul, ou Test + Test Execution +
  Test Plan) et comment les rattacher à la Story et aux états de recette ?
- **Mapping des transitions** : correspondance états Effortless ↔ workflow Jira du
  cycle en V (résolu par lecture des transitions réelles à l'import).
- **Contrat de sortie wlReForge → backlog** : forme précise de la projection
  primitives (clusters / smells / frontières) → niveaux Epic / Story / Sous-tâche.
- **Modèle de scoring ROI** du filet de sécurité (heuristique risque × valeur).
- **Authentification du serveur déployé** : le MCP Effortless déployé aura besoin
  de son propre client Jira (jeton, portée), distinct du connecteur de session.
  Décision de déploiement, hors périmètre fonctionnel.

## Impacts code anticipés

- **State model** : `ProjectState.current_phase` (global) → `Story.current_phase` ;
  le projet suit la Story courante + l'arbre Epic/Story.
- **Docs cadrage** : passage d'un dossier global (`cadrage/Phase-001/`) à des docs
  **par Story** ; `required_documents`, `resolve_phase_docs_dir` et le validateur
  deviennent Story-scopés.
- **MCP tools** : `effortless_phase_next` avance OPALE de la Story courante ;
  `task_add` s'attache à la Story ; nouveaux `epic_add` / `story_start` ; `status`
  affiche l'arbre + la phase par Story.
- **Boucle auto** : `session_loop` scope = compléter les tâches d'une Story.
- **Web UI** : `PhaseTimeline` par Story + vue arbre Epic/Story.
- **Purge documentaire** : toute occurrence de « phase » désignant l'itération de
  développement (README, SKILL) bascule vers « Story ».
