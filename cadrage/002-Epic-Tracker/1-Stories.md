---
type: cadrage-epic-registre
document: 1-stories
projet: Effortless
epic: 002-Epic-Tracker
statut: vivant
tags:
  - cadrage/epic
  - cadrage/registre
---

# Adapter Jira (projection) — Registre des stories

> Rendu dérivé (régénéré) depuis `epic.json` + chaque `story.json`. Ne pas éditer à la main.

| Seq | Id | Titre | Statut |
|---|---|---|---|
| 1 | 001-Story-Port-Tracker | Port Tracker (create/transition/log_work/import/discover_taxonomy) | Done |
| 2 | 002-Story-Adapter-Jira-Concret | Adapter Jira concret (implementation du Port Tracker) | Done |
| 3 | 003-Story-Projection-Mediee-Agent-Rovo | Projection médiée par l'agent via Rovo MCP (retrait REST/token) | Done |
| 4 | 004-Story-Discover-Medie-Issue-Type | Discover médié + issue_type_id dans le plan (flush scaffold automatique) | Done |
| 5 | 005-Story-Transition-Mediee-Enqueue-Transition | Transition médiée (cycle en V) — enqueue transition + flush agent transitionJiraIssue + ack | Done |
| 6 | 006-Story-Log-Work-Medie-Enqueue | Log_work médié — enqueue worklog (addWorklogToJiraIssue) + flush agent ; rollup natif Jira | Done |
| 7 | 007-Story-Import-Read-Mostly-Medie | Import read-mostly médié — reconcile Jira-as-truth (JQL label → import_ack → ScaffoldState) | Done |
| 8 | 008-Story-Option-Xray-Enqueue-Creation | Option Xray (MVP médié) — enqueue création Test Xray + lien Story ; discover taxonomie Xray | Done |
| 9 | 009-Story-Reconcile-Task-Registry-Rewrite | Reconcile task registry — rewrite local:N → clé Jira réelle après flush create (ferme gap ordering) | Done |
| 10 | 010-Story-Validation-Live-Rovo-M2 | Validation live Rovo M2 — flush bout-en-bout contre EFL (reconcile, transition, log_work, import, Xray) | Done |
| 11 | 011-Story-Hygiene-Outbox-Primitive-Purge | Hygiène outbox — primitive de purge (discard) distincte de flush_ack (marquer joué) | Done |
| 12 | 012-Story-Scaffold-Idempotent-Jira-Truth | Scaffold idempotent Jira-as-truth — garde d'absence (confirm_absent) avant création [PROJET] | Done |
