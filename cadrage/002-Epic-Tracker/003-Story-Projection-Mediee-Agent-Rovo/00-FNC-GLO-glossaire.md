---
phase: O-analyse
statut: Validé
type: cadrage-story
projet: Effortless
epic: 002-Epic-Tracker
story: 003-Story-Projection-Mediee-Agent-Rovo
code: FNC-GLO
document: 00-FNC-GLO-glossaire
tags:
  - cadrage/story
  - cadrage/002-epic-tracker
  - cadrage/fnc-glo
---

# 📖 Glossaire — Projection médiée agent via Rovo (STO-TRACKER-03)

Bascule la projection Jira d'un **client REST + token côté serveur** vers une
**projection médiée par l'agent** : le serveur planifie, l'agent (qui possède le
connecteur Atlassian Rovo MCP) exécute, puis renvoie les refs.

## Termes du domaine

- **Projection médiée agent** : modèle où le serveur Effortless ne touche jamais
  Jira ; il produit un **plan** d'opérations, l'**agent** les exécute via Rovo MCP,
  puis **ack** les résultats au serveur. Révise DEC-03 (REST côté serveur).
- **Rovo MCP** : connecteur Atlassian (`mcp__…Rovo__createJiraIssue`,
  `getJiraProjectIssueTypesMetadata`, `transitionJiraIssue`…) disponible **côté
  agent/CLI uniquement**, jamais dans le process serveur.
- **Planificateur** : le serveur. Calcule *quoi* créer (arbre + payloads + liens
  parent par id local), sans aucun I/O réseau ni credential.
- **Exécuteur** : l'agent. Lit le plan, appelle Rovo, résout les clés réelles.
- **Outbox (`SyncJournal`)** : file rejouable (acquis STO-TRACKER-01) servant de
  transport des ops en attente entre serveur (enqueue) et agent (flush).
- **Op** : opération unitaire en attente `{op, local_id, level, title,
  parent_local_id?, labels?}`. Le `parent_local_id` référence un autre nœud du
  même plan (la vraie clé Jira n'existe pas encore à l'enqueue).
- **id local** : identifiant temporaire d'un nœud du plan, résolu en clé Jira
  réelle par l'agent à l'exécution (map `local_id → {key,url}`).
- **ack** : retour de l'agent au serveur avec la map des refs créées ; le serveur
  persiste l'identité (`tracker_id`/`url`) et marque l'outbox joué (idempotent).
- **QueueTracker** : adapter du type `jira` en mode médié — `create`/`discover`
  **enqueue** au lieu d'appeler le réseau. Remplace l'ancien `JiraTracker` REST.
- **Disclaimer Rovo** : message renvoyé par les outils tracker rappelant que le
  connecteur Rovo doit être déclaré côté CLI/App ; sinon l'agent ne peut pas flusher.
