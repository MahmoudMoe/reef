---
name: reef-plan
description: Turn a raw feature spec into an approved set of vertical-slice task files via grilling and ONE human gate. Use when the user has a feature to plan, or says "/reef-plan".
argument-hint: <feature spec | path/to/spec.md>
---

# Reef Plan — spec -> approved tasks

**Input:** a raw feature spec (`$ARGUMENTS`: free-form text, a path, or empty — if empty, ask the human for one and stop until they answer).
**Output:** approved task files on a feature branch + optional ADR/glossary additions — exactly what `/reef-task` consumes. Nothing else.

You are the orchestrator: grill, draft, gate, write. You do not implement. Read `.reef/config.json` for paths.

## 1. Grill
One question at a time, each with a recommended answer. Only ask what the codebase cannot answer (explore first). Stop when scope, edge cases, non-goals, and ADR-worthy decisions are clear.

## 2. Draft (nothing written to disk)
Split into vertical slices:
- A slice goes ALL THE WAY THROUGH: it touches every layer its behavior needs (schema to output), thin but end-to-end — never "the database part" alone.
- Done means showable: you can run the slice and point at what changed.
- Sized for one clean context: if an agent needs to be reminded mid-way, the slice is too big.
- THE RULE: **no failing test = no task** — every task names the test that would be red before work starts; if you can't, merge or delete the slice.
  - Good: "004 skip-and-warn — red test: bad row currently raises a traceback."
  - Bad: "003 multi-month — grouping already works, task adds a blank line." (This exact padding shipped in the pilot and cost a full round-trip.)
- Wide mechanical refactors are the exception: expand -> migrate-in-batches -> contract, each batch its own task.
Per task, draft the full file from `${CLAUDE_PLUGIN_ROOT}/templates/task.md` (schema: `${CLAUDE_PLUGIN_ROOT}/schemas/task.schema.json`):
- `complexity`: mech = a junior copies an existing example without one question; design = two people would produce materially different solutions.
- `tier`: light (mech only: allowlisted paths, no privacy/money/auth/data path, no migration, no ADR) / full (default) / design (replaces a mechanism that failed twice, or touches privacy, money or a guard — the `loophole-hunter` runs on the plan before code and on the finished guard after). `scripts/reef-plan-check.py` refuses a tier that does not match the complexity.
- `verify`: design -> judge; mech -> gate-only.
- `blocked-by`: only REAL edges — the graph runs every task whose edges are done in parallel, so a decorative edge costs wall-clock, and a missing one lets two tasks collide.
- `resources`: every shared thing the task holds while running — a fixed port (`port:3000`), the database (`db`), the one browser, `heavy` for a full suite or build; the scheduler serialises them (slots in `.reef/config.json`). Name it or two tasks will hold it at once.
- Effort above medium must be argued for in the plan.
Also draft: glossary additions, and at most ONE ADR (Nygard: Status/Context/Decision/Consequences) for the whole feature if it has non-obvious decisions. In a parallel loop, where ADR numbers would collide across branches, write it as `docs/adr/draft-<item>-<slug>.md` and number it at merge — reef-plan-check exempts `draft-*.md` from the "no Proposed ADR" rule (a placeholder or missing Status still fails).

## 3. Explain-back (design tasks)
For each `tier: design` task the HUMAN writes the `## Decision` section in their own words — grill them to sharpen it; never write it for them. For other `design` tasks the orchestrator may draft it, marked `decided by: agent` on its first line, and it joins the question set at the gate. A design task with an empty Decision cannot be dispatched.

## 3.5 Quiz the human on the breakdown
Before the gate, show the numbered task list (title / blocked-by / what it delivers) and ask: does the granularity feel right (too coarse / too fine)? are the blocking edges real? merge or split anything? Iterate until they're satisfied — this is cheaper than discovering a wrong-shaped plan after the branch exists.

## 3.6 Adversarial pass on the plan (tier: design only)
Before the gate, spawn the `loophole-hunter` agent on the drafted plan: "how can every check be green while the defect happens?" Record its verdict with `scripts/reef-adversarial <task-file> plan <report>`; a BLOCKER is fixed in the draft before the gate. The guard refuses to dispatch a `tier: design` task without this record.

## 4. HUMAN GATE (one, blocking — batched)
Show every task in full (scope, ACs, out-of-scope, resources, tier). ONE question set (AskUserQuestion) holding everything that is the human's: Approve / Edit / Cancel, the Design-tier Decisions, where the branch lives (worktree vs current tree), each with a recommended default. Never one question at a time. Only after Approve: write task files, glossary, ADR (drafts: `draft-<slug>.md`, `Status: Accepted (number at merge)`); create `feat/<slug>` branch.

## Re-entry
If tasks for this feature already exist (`tasks/NNN-*.md` matching the slug): do not re-plan from zero — show the existing plan, ask whether to extend, edit, or abandon it. Never overwrite an approved plan silently.
