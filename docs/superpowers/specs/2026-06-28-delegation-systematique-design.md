# Spec — Délégation systématique dans le flux d'exécution Effortless

- **Date** : 2026-06-28
- **Statut** : Validé (design), prêt pour plan d'implémentation
- **Auteur** : Ben + Claude
- **Phase Effortless** : Phase-003-E-execute

## 1. Problème & objectif

Le flux d'exécution actuel fait porter à l'agent invocateur (Claude, Codex, …)
**tout** le travail : raisonnement complexe ET tâches mécaniques. Conséquences :
contexte de l'agent principal pollué par des détails (lectures de fichiers,
logs, essais), forte consommation de tokens, temps d'exécution allongé.

**Objectif** : l'agent principal traite uniquement le complexe (raisonnement,
architecture, arbitrages) et **délègue systématiquement** le simple/mécanique à
un sous-agent à contexte frais. Le gain principal est que l'output verbeux du
travail simple reste **hors du contexte principal** — seule une conclusion
compacte remonte.

Objectif mesurable visé : réduction de la consommation de tokens et du temps
d'exécution sur un cycle de boucle autonome (constaté dans d'autres projets avec
la même architecture).

## 2. Contrainte d'architecture fondamentale

**Effortless ne spawn pas de sous-agents.** C'est un serveur MCP + des Skills.
La délégation est exécutée par l'agent invocateur via son propre outil d'agents
(Agent/Task). Le rôle d'Effortless est donc **d'instruire et de structurer** la
délégation, pas de l'exécuter. Toute la feature consiste à :

1. classer la complexité des tâches (donnée),
2. émettre des consignes de boucle déterministes (DÉLÉGUER / DÉCOMPOSER / TRIAGE),
3. porter la doctrine dans `SKILL.md` pour que l'agent l'applique hors boucle aussi.

## 3. Décisions de design

| # | Décision | Raison |
|---|----------|--------|
| D1 | Taxonomie **binaire** `simple` / `complex` | `trivial` et `simple` mènent à la même action (déléguer) → 3e niveau inutile |
| D2 | Classée par l'agent **à la création** | Quasi-gratuit : l'agent a déjà le raisonnement en tête → 0 tour LLM en plus |
| D3 | Triage **une seule fois** si non classée | Un triage systématique par étape ajouterait un aller-retour LLM → contraire au but |
| D4 | Outil dédié `effortless_task_classify` | Garde `task_update` focalisé sur le statut |
| D5 | `complex` → décomposer en sous-tâches `simple`, puis parent `Done` | Évite un champ `parent` et une hiérarchie persistée (YAGNI) |
| D6 | Pas de nouveau statut, pas de champ `parent` | Schéma minimal ; la décomposition se résout via les outils existants |

## 4. Composants

### 4.1 Modèle `Task` (`models/task.py`)
- Ajouter `complexity: Optional[str] = None`.
- Valeurs : `"simple"`, `"complex"`, ou `None` (non classée).
- Rétro-compatible : les tâches existantes sans le champ sont lues comme `None`.

### 4.2 Outils MCP (`server.py`)

`effortless_task_add(title, description=None, depends_on=None, complexity=None)`
- Nouveau paramètre optionnel `complexity`.
- Validation **avant écriture** : si fourni et ∉ `{simple, complex}` → message
  d'erreur, aucune écriture.
- Stocké tel quel sur la tâche.

`effortless_task_classify(task_id, complexity)` — **nouvel outil**
- Valide `complexity ∈ {simple, complex}`.
- Charge la tâche, échoue proprement si introuvable / projet non initialisé.
- Pose `complexity`, `save_entity`, renvoie une confirmation (str).

### 4.3 Boucle autonome (`session_loop.py`)

Branchement dans l'étape **PLAN**, après sélection de la tâche éligible
(`next_task`), AVANT de la passer en `Doing` :

```
c = next_task.get("complexity")
if c is None:
    → consigne TRIAGE : « Tâche {id} non classée. Classe-la simple|complex via
      effortless_task_classify, puis relance effortless_loop_step. »
    return  (aucun changement d'état : la tâche reste Todo)

if c == "complex":
    → consigne DÉCOMPOSER : « Tâche complexe. Découpe-la en sous-tâches SIMPLES
      via effortless_task_add(complexity="simple"), avec depends_on si ordre
      requis, puis marque {id} Done via effortless_task_update. Relance ensuite. »
    return  (la tâche reste Todo ; l'agent crée les enfants et clôt le parent)

# c == "simple" : flux nominal d'exécution, avec délégation imposée
next_task.status = "Doing" ; save ; step = Implementation
→ consigne DÉLÉGUER : « Délègue cette tâche à un sous-agent (outil Agent),
  prompt fermé et borné ; récupère un résultat compact ; n'implémente pas
  toi-même. Une fois fait, relance pour la recette. »
```

Notes :
- TRIAGE et DÉCOMPOSER **ne font pas avancer** la machine (pas de passage en
  `Doing`/`Implementation`) : la boucle est agent-driven, l'agent agit puis
  relance ; au prochain PLAN l'état a changé (classée, ou parent Done + enfants
  Todo).
- Idempotence : si l'agent ne décompose pas, la boucle ré-émet la même consigne
  (pas de blocage dur, pas de doublon d'état).
- L'étape **Recette** (tests + anti-drift + commit) reste **inchangée**.

### 4.4 Doctrine (`skills/effortless/SKILL.md`)
Ajouter une section « Délégation systématique » :
- L'agent principal traite le complexe (raisonnement, archi, arbitrages).
- Il délègue **systématiquement** le simple/mécanique à un sous-agent : prompt
  fermé et borné, résultat compact attendu ; il garde la conclusion, pas les
  détails (l'output verbeux ne doit pas entrer dans le contexte principal).
- Décrit la classification binaire et les outils `task_add(complexity=…)` /
  `task_classify`.
- S'applique aussi hors boucle autonome (mode OPAL manuel).

### 4.5 Web UI (`server.py` + `web-ui`)
- `build_project_overview` renvoie déjà la tâche entière → `complexity` est
  disponible côté front sans changement serveur.
- `App.jsx` : afficher un petit badge `simple` / `complex` (ou « ? » si non
  classée) sur la carte de tâche. Coût quasi nul.

## 5. Flux de données

```
Agent crée tâche ──(complexity)──▶ Task JSON (.effortless/tasks/)
                                         │
boucle PLAN lit complexity ──▶ branch ──┤ None    → consigne TRIAGE  → task_classify
                                         │ complex → consigne DÉCOMPOSER → task_add(simple) + parent Done
                                         │ simple  → Doing + consigne DÉLÉGUER → sous-agent
overview ──▶ /api/overview ──▶ badge complexity (dashboard)
```

## 6. Gestion d'erreur
- `complexity` invalide (`task_add` ou `task_classify`) → message d'erreur,
  **aucune écriture partielle**.
- Tâche non classée → consigne TRIAGE, jamais de crash.
- `task_classify` sur ID inconnu / projet non initialisé → message d'erreur clair.
- Décomposition sans enfant créé → la boucle ré-émet DÉCOMPOSER (idempotent).

## 7. Tests (pytest)
- `task_add(complexity="simple")` stocke le champ ; valeur invalide rejetée.
- `effortless_task_classify` pose la complexité ; rejette valeur invalide ;
  erreur sur ID inconnu.
- Boucle : tâche `None` → sortie contient `TRIAGE` ; `complex` → `DÉCOMPOSER` ;
  `simple` → `DÉLÉGUER` + passage en `Implementation`.
- Rétro-compat : tâche legacy sans `complexity` lue comme `None` (déclenche TRIAGE).

## 8. Hors scope (YAGNI)
- Champ `parent` / hiérarchie de tâches persistée.
- 3e niveau de complexité (`trivial`).
- Triage répété à chaque étape.
- Effortless qui spawn lui-même des sous-agents (impossible : c'est un MCP server).
- Métriques de tokens intégrées (mesure manuelle hors scope).

## 9. Critères d'acceptation
- Une tâche peut être créée avec `complexity`, reclassée via un outil dédié.
- La boucle autonome émet la bonne consigne (TRIAGE / DÉCOMPOSER / DÉLÉGUER)
  selon la complexité, de façon déterministe et idempotente.
- `SKILL.md` porte la doctrine de délégation systématique.
- Le dashboard affiche la complexité des tâches.
- Tests verts ; aucune régression sur le flux de boucle existant.
