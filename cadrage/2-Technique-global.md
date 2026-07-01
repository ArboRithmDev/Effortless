---
type: cadrage-projet
document: 2-technique-global
titre: Effortless — Technique global
projet: Effortless
statut: versionné
version: 1
maj: 2026-07-01
tags:
  - cadrage/projet
  - cadrage/technique
---

# Effortless — Analyse et spécification technique globale (document 2)

> Détermine les axes de travail et les stacks qui cadrent les phases de
> développement de chaque Epic. **Révisable par version** (snapshots datés).

**Version 1 — baseline — 2026-07-01**

## Architecture

- Serveur **MCP** en Python (fastmcp) exposant les outils `effortless_*`.
- Architecture **hexagonale** : un port `Tracker` agnostique, des adaptateurs
  concrets (`NullTracker`, `QueueTracker` Jira médié).
- **Projection médiée** : le serveur planifie (zéro I/O, zéro secret), l'agent
  exécute via le connecteur Rovo. Transport = outbox `SyncJournal`
  (`.effortless/tracker_outbox/`).
- **Modèle fractal** persistant sous `.effortless/` (state, epics/stories/tasks,
  décisions, questions) ; cadrage documentaire sous `cadrage/`.

## Stack

- Python 3.12+, `pytest` (suite hermétique), `fastmcp`.
- Persistance fichier (JSON pour l'état, Markdown pour le cadrage).
- Intégrations : Jira via Rovo MCP (médié), SecondBrain (mémoire), Git (hook
  anti-dérive pre-commit).

## Principes

- Aucun credential ni appel réseau côté serveur (projection médiée).
- Idempotence des projections (garde Jira-as-truth avant création).
- Tests hermétiques : pas de dépendance réseau, `tmp_path`/monkeypatch.
- Encodage vault et fichiers : UTF-8 sans BOM, fins de ligne LF.

## Axes de travail par Epic

- **Core** — modèle fractal, phases, boucle, drift, mémoire, migration.
- **Tracker** — outbox + adaptateur médié, taxonomie découverte, réconciliation,
  hygiène outbox.
- **Cadrage** — scaffolding des documents projet, état JSON versionné
  (`backlog.json`, `evolutions.json`), deux modes d'init, nomenclature
  `<NNN>-Epic-<Périmètre>` / `<NNN>-Story-<Périmètre>`, outils de clôture.

## Contraintes d'exécution

- Tests : `src/mcp-server/.venv/Scripts/python.exe -m pytest src/mcp-server/tests -q`
  (`PYTHONIOENCODING=utf-8`).
- Reconnecter le MCP `effortless` après tout patch de `server.py`.
- `.effortless/`, `cadrage/`, `effortless.json` sont gitignorés.

## Historique des versions

- v1 (2026-07-01) — baseline initiale.
