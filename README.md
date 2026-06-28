<div align="center">

<img src="src/web-ui/public/favicon.svg" width="72" alt="Effortless logo" />

# Effortless

**An agnostic, AI-driven project-management framework — exposed as an MCP server and a set of Skills, so any LLM agent (or human) can run a project through a rigorous, phase-gated workflow.**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-3776AB.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/protocol-MCP-6d8bff.svg)](https://modelcontextprotocol.io/)
[![Version](https://img.shields.io/badge/version-0.3.0-success.svg)](https://github.com/ArboRithmDev/Effortless/releases)

</div>

---

## What is Effortless?

Effortless turns a vague intention ("build X", "migrate Y") into a disciplined, auditable engineering process. It is **language- and stack-agnostic**: it manages *how* a project advances, not *what* it is built with.

It combines three ideas:

- **OPAL phases** — every project flows through **O**bserver → **P**ositionner → **A**rticuler → **L**ancer → **E**xecute, with a **strict barrier** between phases: you cannot advance until the required documents exist, are well-formed, and all blocking questions are resolved.
- **A git-friendly database** — decisions, questions and tasks live as one JSON file per entity under `.effortless/`, with Markdown views rendered for humans. Diff-able, merge-friendly, team-ready.
- **An MCP control surface** — 18 tools an LLM agent calls to drive the project, plus an autonomous loop that delegates simple work to sub-agents and a live web dashboard.

Effortless is built on the storage/adapter philosophy of **[SecondBrain](https://github.com/SI-GMT/SecondBrain)** and the phase-sequencing rigor of **Orcha (OPAL)**, and it integrates back into a SecondBrain memory vault.

---

## Why use it?

- 🚦 **Phase gates that actually block.** No "we'll document it later" — the barrier is enforced before each transition.
- 🧩 **Decisions, questions and tasks as first-class, versioned artifacts.** Every ADR, every open question (BQO), every task is a file you can review in a PR.
- 🤖 **Autonomous execution loop with systematic delegation.** The orchestrating agent handles only the complex work and delegates simple, mechanical tasks to fresh sub-agents — cutting token use and wall-clock time.
- 🛡️ **Anti-drift guardrail.** A pre-commit hook refuses commits that touch code with no active task — keeping work tied to the plan.
- 🧠 **SecondBrain symbiosis.** Phase changes are mirrored (non-destructively) into your memory vault so a session can be resumed later.
- 🔌 **One install, every CLI agent.** Auto-deploys to Claude Code, Codex, Mistral Vibe, GitHub Copilot CLI and Antigravity.
- 📊 **Live dashboard.** A React UI backed by a JSON API shows the phase timeline, document checklist, task board, questions and decisions.

---

## How it works

```
                ┌─────────────────────────────┐
   LLM agent ──▶│  Effortless MCP server       │──▶  .effortless/   (JSON source of truth)
   (Claude,     │  18 tools • OPAL state mach.  │──▶  cadrage/       (generated Markdown views)
    Codex, …)   │  validation • anti-drift      │──▶  SecondBrain    (vault symbiosis)
                └─────────────────────────────┘
                          │
                          └──▶  /api/overview  ──▶  React dashboard
```

- **Source of truth** is the JSON DB in `.effortless/` (decisions, questions, tasks, state).
- **Markdown** under `cadrage/` is a *generated, read-only* rendering (it carries a "do not edit" banner).
- The server resolves the **current project** from its working directory (the project you opened the agent in), and resolves its own **install location** separately — so it works deployed onto any repo.

---

## Quick start

**Requirements:** Python 3.12+, `git`, and (optional, for the dashboard) Node.js.

```bash
git clone https://github.com/ArboRithmDev/Effortless.git
cd Effortless
./setup.sh
```

`setup.sh` will:

1. create the Python virtualenv and install the MCP server (uses [`uv`](https://github.com/astral-sh/uv), installed automatically if missing);
2. build the web dashboard (if `npm` is present);
3. auto-deploy the MCP server + Skill to every detected CLI agent;
4. install the anti-drift pre-commit hook.

Then **reconnect the MCP server** in your agent (e.g. `/mcp` → reconnect `effortless` in Claude Code) and start a project:

> "Initialise Effortless in this repo and show me the status."

The agent calls `effortless_init` then `effortless_status`. You're in the **Observer** phase.

---

## The workflow (OPAL)

Each phase requires a set of documents under `cadrage/`. The barrier checks, for the **current** phase, that every required document:

1. exists, 2. has valid YAML frontmatter with the right `phase`, 3. contains its mandatory sections, 4. has no unfilled placeholders — and that no **blocking** question is still open.

| Phase | Name | Produces |
|-------|------|----------|
| **O** | Observer | glossary, analysis of the existing, open-questions log (BQO) |
| **P** | Positionner | target architecture, decision register (ADR) |
| **A** | Articuler | functional & technical specifications, API contract |
| **L** | Lancer | action plan, task breakdown |
| **E** | Execute | implementation (driven by the autonomous loop) |

`effortless_status` tells you, at any time, what's missing and whether you may advance. `effortless_phase_next` performs the transition **only if** the barrier is clear.

---

## Feature reference

All capabilities are MCP tools. Below they are grouped to follow the functional flow. Examples are shown as the natural request you'd make to your agent, with the underlying tool call.

### 1 · Project lifecycle & phase gates

| Tool | Purpose |
|------|---------|
| `effortless_init` | Scaffold `effortless.json`, the `.effortless/` DB and the `cadrage/` tree. |
| `effortless_status` | Current phase, document checklist, open questions, and whether the next phase is reachable. |
| `effortless_phase_next` | Validate the barrier and transition to the next phase (also mirrors to SecondBrain). |

```text
You: "Set up Effortless here for project 'Delta'."
   → effortless_init(project_name="Delta")

You: "Are we ready to move past Observer?"
   → effortless_status()
   ❌ NO — `cadrage/Phase-001/01-TEC-ANA-analyse.md` missing; Q-01 (Blocker) unresolved.

You: "Advance to the next phase."
   → effortless_phase_next()   # blocked until the checklist is green
```

### 2 · Decisions (ADR)

| Tool | Purpose |
|------|---------|
| `effortless_decision_add` | Record an architecture decision (context, decision, consequences, rejected alternatives). Stored as `DEC-NN` and rendered into the decision register. |

```text
You: "Record our decision to use SQLite for the cache."
   → effortless_decision_add(
        title="Cache store = SQLite",
        context="Need an embedded, zero-config store",
        decision="Use SQLite via the stdlib driver",
        consequences=["No server to operate", "Single-writer limitation"],
        rejected_alternatives=["Postgres (ops overhead)"])
```

### 3 · Open questions (BQO)

| Tool | Purpose |
|------|---------|
| `effortless_question_ask` | Log an open question with an `impact` of `Blocker`, `Structuring` or `Minor`. A `Blocker` left unresolved **stops phase transition**. |
| `effortless_question_resolve` | Answer a question; records the answer and date. |

```text
You: "Open a blocking question: when do we run the Qt purge?"
   → effortless_question_ask(question="When to run the Qt purge?",
                             context="Affects release timing", impact="Blocker")

You: "Resolve Q-01: purge runs in the pre-release step."
   → effortless_question_resolve(question_id="Q-01",
                                 answer="Runs in the pre-release step")
```

### 4 · Tasks

| Tool | Purpose |
|------|---------|
| `effortless_task_add` | Create a task in the active phase, with optional `depends_on` and a `complexity` (`simple`/`complex`). |
| `effortless_task_update` | Move a task between `Todo` / `Doing` / `Done` (enforces dependencies). |
| `effortless_task_classify` | Set/repair a task's `complexity` after creation. |

```text
You: "Add a task to implement the auth middleware, it's complex."
   → effortless_task_add(title="Implement auth middleware", complexity="complex")

You: "Start TSK-E-01."
   → effortless_task_update(task_id="TSK-E-01", status="Doing")
```

### 5 · Autonomous loop & systematic delegation

| Tool | Purpose |
|------|---------|
| `effortless_loop_init` | Start an autonomous execution session with a goal. |
| `effortless_loop_step` | Advance the state machine: pick a task → **delegate / decompose / triage** → run tests → auto-commit on green. |

The loop is a state machine — `Plan → Implementation → Acceptance (tests + anti-drift) → Delivery` — with a built-in **delegation doctrine**:

- a **simple** task → consign to **delegate** it to a fresh sub-agent (its verbose output never pollutes the main context);
- a **complex** task → consign to **decompose** it into simple sub-tasks;
- an **unclassified** task → a one-time **triage** to classify it.

It also stops safely: tests run under a timeout, repeated failures abort after a bounded number of attempts, and dependencies are respected.

```text
You: "Run the project to completion. Tests: 'cd src/mcp-server && pytest -q'."
   → effortless_loop_init(goal="Finish the backlog")
   → effortless_loop_step(test_command="cd src/mcp-server && pytest -q")
   📋 [DELEGATE] TSK-E-01 selected — delegate to a sub-agent, return a compact result.
```

### 6 · Anti-drift

| Tool | Purpose |
|------|---------|
| `effortless_drift_check` | Report whether source files changed without an active (`Doing`) task. |
| `effortless_drift_hook_install` | Install a git pre-commit hook that blocks drifting commits. |

```text
You: "Did we drift?"
   → effortless_drift_check()
   ⚠️ Code under src/ changed but no task is 'Doing'.
```

### 7 · SecondBrain symbiosis

| Tool | Purpose |
|------|---------|
| `effortless_secondbrain_sync` | Push the project state + decisions into your SecondBrain vault (updates `context.md`, creates a timestamped archive). |

The sync is **non-destructive**: it writes only Effortless-namespaced frontmatter keys (`effortless_phase`, `effortless_last_sync`) and never overwrites fields owned by your memory vault.

> **SecondBrain** is a separate open-source project — persistent cross-session memory for LLM CLIs (Claude Code, Gemini CLI, Codex, Mistral Vibe), stored as a local Markdown vault you can browse in Obsidian. Repo: <https://github.com/SI-GMT/SecondBrain>

### 8 · Migrating an existing repository

| Tool | Purpose |
|------|---------|
| `effortless_migrate_init` | Analyse an existing repo (stack, frameworks, docs) and scaffold Effortless with adapted migration tasks. |
| `effortless_migrate_apply` | Physically reorganise docs/code per the migration plan. |

```text
You: "Onboard the repo at /path/to/legacy into Effortless."
   → effortless_migrate_init(target_path="/path/to/legacy")
   → effortless_migrate_apply(target_path="/path/to/legacy")
```

### 9 · Deployment & dashboard

| Tool | Purpose |
|------|---------|
| `effortless_deploy` | (Re)deploy the MCP server + Skill to all detected CLI agents. |
| `effortless_web_ui_launch` | Start the embedded HTTP server and open the live dashboard. |

```text
You: "Open the dashboard."
   → effortless_web_ui_launch()
   Dashboard started at http://localhost:53124 (API: /api/overview)
```

---

## The dashboard

`effortless_web_ui_launch` serves a React app backed by `GET /api/overview`. It shows, live (auto-refreshing):

- the **OPAL phase timeline** (done / current / upcoming);
- the **document checklist** for the current phase;
- a **Todo / Doing / Done** task board, with a per-task **complexity** badge;
- the **open-questions (BQO)** list with impact and resolution state;
- the **decision (ADR)** records.

The dashboard is read-only and degrades gracefully when the project is uninitialised or the API is unreachable.

---

## Architecture & storage

```
your-project/
├── effortless.json            # project config + OPAL workflow definition
├── .effortless/               # git-friendly database (source of truth)
│   ├── state.json             # current phase, completed phases
│   ├── decisions/DEC-*.json
│   ├── questions/Q-*.json
│   └── tasks/TSK-*.json
└── cadrage/                   # generated Markdown views (do not edit)
    └── Phase-00N/...
```

- **One file per entity** → minimal merge conflicts in team mode.
- **Markdown is generated** from JSON on every mutation (and carries a "generated — do not edit" banner), so the human-readable docs never drift from the data.
- **Install vs. project** are cleanly separated: the framework's code/venv/dashboard live in the Effortless install, while project data is addressed by the agent's working directory — which is what makes Effortless deployable onto any repo.

---

## Multi-client support

A single `effortless_deploy` (run by `setup.sh`) registers the MCP server with every project-aware CLI agent it finds:

**Claude Code · Codex · Mistral Vibe · GitHub Copilot CLI · Antigravity (Gemini).**

GUI clients without a project working directory (e.g. Claude Desktop) are intentionally excluded — Effortless is project-scoped and would have no project to act on there.

---

## Development

```bash
cd src/mcp-server
source .venv/bin/activate
pytest -q                 # run the test suite
effortless-mcp            # run the MCP server directly (stdio)
```

The repository dogfoods itself: it is managed by Effortless (see `.effortless/`) and protected by its own anti-drift pre-commit hook.

---

## License

Licensed under the **Apache License 2.0** — see [LICENSE](LICENSE).

Copyright 2026 ArboRithmDev.
