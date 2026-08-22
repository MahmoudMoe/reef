---
name: reef-plan
description: Turn a raw feature spec into an approved set of vertical-slice task files via grilling and ONE human gate. Use when the user has a feature to plan, or says "/reef-plan".
disable-model-invocation: true
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
- Each slice cuts a narrow but COMPLETE path through every layer it touches — vertical, never a horizontal layer.
- A completed slice is demoable or verifiable on its own.
- Each slice fits one fresh context window.
- THE RULE: **no failing test = no task** — every task names the test that would be red before work starts; if you can't, merge or delete the slice.
  - Good: "004 skip-and-warn — red test: bad row currently raises a traceback."
  - Bad: "003 multi-month — grouping already works, task adds a blank line." (This exact padding shipped in the pilot and cost a full round-trip.)
- Wide mechanical refactors are the exception: expand -> migrate-in-batches -> contract, each batch its own task.
Per task, draft the full file from `${CLAUDE_PLUGIN_ROOT}/templates/task.md` (schema: `${CLAUDE_PLUGIN_ROOT}/schemas/task.schema.json`):
- `complexity`: mech = a junior copies an existing example without one question; design = two people would produce materially different solutions.
- `verify`: design -> judge; mech -> gate-only.
- Effort above medium must be argued for in the plan.
Also draft: glossary additions, and at most ONE ADR (Nygard: Status/Context/Decision/Consequences) for the whole feature if it has non-obvious decisions.

## 3. Explain-back (design tasks)
For each `design` task the HUMAN writes the `## Decision` section in their own words — grill them to sharpen it; never write it for them. A design task with an empty Decision cannot be dispatched.

## 3.5 Quiz the human on the breakdown
Before the gate, show the numbered task list (title / blocked-by / what it delivers) and ask: does the granularity feel right (too coarse / too fine)? are the blocking edges real? merge or split anything? Iterate until they're satisfied — this is cheaper than discovering a wrong-shaped plan after the branch exists.

## 4. HUMAN GATE (one, blocking)
Show every task in full (scope, ACs, out-of-scope). AskUserQuestion: Approve / Edit / Cancel; on Approve also ask where the branch lives (worktree vs current tree). Only after Approve: write task files, glossary, ADR; create `feat/<slug>` branch.

## Re-entry
If tasks for this feature already exist (`tasks/NNN-*.md` matching the slug): do not re-plan from zero — show the existing plan, ask whether to extend, edit, or abandon it. Never overwrite an approved plan silently.
