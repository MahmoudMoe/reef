---
name: reef-plan
description: Turn a raw feature spec into an approved set of vertical-slice task files via grilling and ONE human gate. Use when the user has a feature to plan, or says "/reef-plan".
disable-model-invocation: true
argument-hint: <feature spec | path/to/spec.md>
---

# Reef Plan — spec -> approved tasks

You are the orchestrator: grill, draft, gate, write. You do not implement. Read `.reef/config.json` for paths.

## 1. Grill
One question at a time, each with a recommended answer. Only ask what the codebase cannot answer (explore first). Stop when scope, edge cases, non-goals, and ADR-worthy decisions are clear.

## 2. Draft (nothing written to disk)
Split into vertical slices. THE RULE: **no failing test = no task** — every task names the test that would be red before work starts; if you can't, merge or delete the slice. Wide mechanical refactors are the exception: sequence them expand -> migrate-in-batches -> contract.
Per task, draft the full file from `${CLAUDE_PLUGIN_ROOT}/templates/task.md` (schema: `${CLAUDE_PLUGIN_ROOT}/schemas/task.schema.json`):
- `complexity`: mech = a junior copies an existing example without one question; design = two people would produce materially different solutions.
- `verify`: design -> judge; mech -> gate-only.
- Effort above medium must be argued for in the plan.
Also draft: glossary additions, and at most ONE ADR (Nygard: Status/Context/Decision/Consequences) for the whole feature if it has non-obvious decisions.

## 3. Explain-back (design tasks)
For each `design` task the HUMAN writes the `## Decision` section in their own words — grill them to sharpen it; never write it for them. A design task with an empty Decision cannot be dispatched.

## 4. HUMAN GATE (one, blocking)
Show every task in full (scope, ACs, out-of-scope). AskUserQuestion: Approve / Edit / Cancel; on Approve also ask where the branch lives (worktree vs current tree). Only after Approve: write task files, glossary, ADR; create `feat/<slug>` branch.

## Re-entry
If tasks for this feature already exist (`tasks/NNN-*.md` matching the slug): do not re-plan from zero — show the existing plan, ask whether to extend, edit, or abandon it. Never overwrite an approved plan silently.
