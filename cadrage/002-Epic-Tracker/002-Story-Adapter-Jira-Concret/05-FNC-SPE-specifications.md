---
titre: Specifications
phase: A-specs
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 002-Story-Adapter-Jira-Concret
code: FNC-SPE
document: 05-FNC-SPE-specifications
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/fnc-spe
---

# 📐 Spécifications fonctionnelles — Adapter Jira concret (STO-TRACKER-02)

## Capacités livrées (MVP)

### 1. Coupler un projet Effortless à un projet Jira
Nouvel outil MCP `effortless_tracker_couple(type, project_id, project_url)`.
- Écrit `settings.tracker = {type, project_id, project_url, ...}` (via `couple_project`).
- Pour `type="jira"` : exécute `discover_taxonomy` et stocke la taxonomie résolue
  (types + transitions) ; signale toute divergence avec le mapping canonique attendu.
- Sans adapter enregistré pour le `type` → reste sur NullTracker (no-op).

### 2. Scaffolder l'arbre [PROJET] dans le projet couplé
Nouvel outil MCP `effortless_tracker_scaffold(zone="PROJET", template=None)`.
- Charge le template externalisé (défaut : `jira_project_scaffold.json`).
- Crée dans le projet Jira couplé : 1 Epic + 3 Stories + 2 sous-tâches, câblés en
  arbre (Epic→Story, Story→Sous-tâche), tous **non affectés**, **sans estimation**.
- Pose un label `effortless-scaffold:<zone>` sur l'Epic racine.
- **Idempotent** : un re-run sur une zone déjà scaffoldée ne recrée rien.
- Retourne la table des refs créées (clé + URL Jira par nœud).

### 3. Projection best-effort sur create (acquis câblé)
À la création d'une Task Effortless dans un projet couplé Jira, `create` projette
l'issue (type Sous-tâche, parent câblé) et persiste `tracker_id`/`tracker_url`.
Échec réseau → consigné à l'outbox `SyncJournal` (jamais bloquant).

## Comportements attendus

| Situation | Comportement |
|---|---|
| Projet non couplé | NullTracker : tous les outils tracker = no-op, zéro I/O. |
| Couplage Jira | `discover_taxonomy` obligatoire ; mapping proposé si divergence. |
| Scaffold zone neuve | Crée l'arbre complet, pose le label, persiste les refs. |
| Scaffold zone existante | Skip (garde idempotence locale + label Jira), retourne refs connues. |
| Réseau indisponible | Opération locale OK ; projection consignée à l'outbox. |
| Type non-MVP (`transition`/`log_work`/`import`) | `NotImplementedError` documenté, capté best-effort par `integration`. |

## Hors périmètre (stories suivantes M2)

- `transition` (mapping cycle en V complet), `log_work` (worklog + rollup),
  `import` read-mostly, option Xray.
- Projection d'estimation (`complexity` → `timeoriginalestimate`).
- Reconcile Jira-as-truth complet (re-scan par label quand l'état local est perdu)
  au-delà de la garde locale + label posé — voir contrat API §Idempotence.

## Critères d'acceptation

1. Couplage EFL : `discover_taxonomy` renvoie une `Taxonomy` non vide (types +
   transitions résolus depuis EFL).
2. Scaffold EFL : l'arbre [PROJET] (6 issues) est créé, parents câblés, label posé,
   refs persistées. Vérifiable par `search` du label.
3. Re-run scaffold EFL : aucune issue supplémentaire créée (idempotence).
4. Suite pytest **hermétique** : tout passe via `FakeJiraClient`, zéro réseau réel.
5. Projet non couplé : aucun changement de comportement, zéro I/O tracker.
