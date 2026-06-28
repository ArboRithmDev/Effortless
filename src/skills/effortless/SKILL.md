---
name: effortless
description: Agent-first project management methodology discipline for initialising, validating and executing development phases.
---

# 🛠️ Skill Effortless

This Skill teaches the agent how to use the **Effortless** protocol and methodology to structure its development work without skipping steps.

---

## 📋 Behavioural Directives

### 1. Initial contact (Context Analysis)
As soon as you start work on a project that has an `effortless.json` file or a `.effortless/` folder:
1. **Immediately run** the `effortless_status` tool to learn the active phase and the required-document checklist.
2. **Do not begin any development** if the project is in one of the scoping phases (`O-analyse`, `P-cadrage`, `A-specs`, `L-plan`). Focus exclusively on writing and validating the required documents for the current phase.

---

## 🔄 Lifecycle Management (Workflow)

### Step A: Observation (`O-analyse`)
* Fill in the Glossary and the Comparative Analysis.
* If business uncertainties arise, raise a question using the `effortless_question_ask` tool with the appropriate impact (`Blocker` if it prevents progress, `Structuring` or `Minor`).
* Do not attempt to guess the answers: explicitly request arbitration from the user.

### Step B: Decision Scoping (`P-cadrage`)
* Lock in the technical choices and the target architecture.
* For each finalised architecture decision (context, decision, rejected alternatives), record it using the `effortless_decision_add` tool.

### Step C: Specifications (`A-specs`)
* Write the detailed functional specifications and API contracts.
* Verify that all required documents are complete and valid.

### Step D: Action Plan (`L-plan`)
* Write the development plan and break the work down into atomic tasks.
* Declare the development tasks via MCP or the backlog system.

### Step E: Execution (`E-execute`)
* Before starting a task, set its status to `Doing` with `effortless_task_update`.
* When the task is complete and tested, move it to `Done`.

---

## 🚦 Golden Rule of Transitions
Only move to the next phase (via `effortless_phase_next`) when `effortless_status` reports `Eligibility for the next phase: ✅ YES`. 

If blocked, resolve the indicated reasons first (missing/invalid documents or unresolved blocking BQO questions).

## ⚡ Systematic Delegation

Effortless does not launch sub-agents itself: it is **you**, the invoking agent,
who delegates via your agent tool.

Rule: **handle only the complex** (reasoning, architecture, trade-offs) and **delegate the simple/mechanical systematically** to a fresh-context sub-agent.

- Classify each task at creation: `effortless_task_add(..., complexity="simple"|"complex")`.
  An already-created task is classified via `effortless_task_classify(task_id, complexity)`.
- `simple` = mechanical, requires no reasoning (targeted edits, boilerplate, renaming,
  running tests, doc generation) → **delegate** to a sub-agent: a closed, bounded prompt,
  compact result expected. Keep the conclusion, not the details:
  verbose output must not enter your context.
- `complex` = reasoning/architecture/trade-off → **decompose** into simple sub-tasks
  (then delegate those), or handle directly the part that genuinely requires your reasoning.

In the autonomous loop (`effortless_loop_step`), these instructions are emitted
automatically: `🔎 [TRIAGE]` (classify), `🧩 [DECOMPOSE]` (decompose), `📋
[DELEGATE]` (delegate). Outside the loop (manual OPAL mode), apply the same doctrine.
