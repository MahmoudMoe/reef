---
name: reef-graph
description: Run the ready task graph as ONE Claude Code workflow (implementer → gate → verifier ‖ hunter per task, in fresh contexts, in the background) instead of one agent result per orchestrator turn — Reef's graph mode (workflow v2, phase 3). Gated: the first run on a machine proves reef-guard denies a workflow agent's forbidden write. Use when the tick's `dispatch now` holds several tasks, or the user says "/reef-graph".
---

# Reef Graph — the task graph as a workflow

Chat mode (`/reef-task`) costs the orchestrator one 90k-context turn per agent result (measured 2026-10-17: 25 turns, 49k for one task). Graph mode moves the per-task chain into a workflow script that `scripts/reef-graph-run.py` writes from the tick; the orchestrator makes three calls per batch of tasks and reads one summary. Every record and check stays: reef-attempt and the plan gate run at generation, the gate and the snapshot run as a `reef:mechanic` agent inside the pipeline, the judges are the same agents with the same budgets and write their report FILES, the report checks and the guard-pass record run at settle, and the merge stays with you, the single writer.

## 0. The gate — once per machine, fail closed
`python3 scripts/reef-graph-run.py probe` writes `.reef/graph/probe.js`. Call the **Workflow** tool with `scriptPath` set to it. Its one agent (`reef:mechanic`) tries `printf '{}' > .reef/approvals/graph-probe.json`. Save the tool's return value verbatim as JSON to `.reef/graph/probe-results.json` (not an evidence path), then `python3 scripts/reef-graph-run.py probe-check .reef/graph/probe-results.json`. `GATE OK` means PreToolUse hooks reach workflow agents here and `.reef/graph/gate.json` records it; `GATE FAILED` means a workflow is a way around the guard on this machine — graph mode stays OFF (`generate` refuses) and `/reef-task` keeps every guarantee. Say which to the owner in one line.

## 1. Generate
`python3 scripts/reef-graph-run.py generate [--tasks 101,102]` — for every task in the tick's `dispatch now`: the worktree (`reef-graph.py worktree`), `reef-attempt` (caps, models, budgets; exit 2 = parked, listed as `skipped`), the in-progress status, the dispatch count and the `.reef/inflight/<id>` marker (what the guard writes on a chat dispatch), then `.reef/graph/run-<hash>.js`. Read only its `graph:`, `skipped` and `next:` lines.

## 2. Run
Call the **Workflow** tool with `scriptPath` = the printed script. Do nothing else while it runs; the Stop hook's tick shows the tasks in flight. The workflow returns `{tasks: [...], skipped: n}`: per task the gate exit, the hand-back check line, the snapshot before and after the judges, each judge's verdict and report path. Save it verbatim as JSON to `.reef/graph/results-<hash>.json` (the `next:` line names the path).

## 3. Settle
`python3 scripts/reef-graph-run.py settle .reef/graph/results-<hash>.json` — per task: the gate must be 0, the hand-back check `ok`, the snapshot unchanged across the judges, every verdict PASS; the verifier's report is copied (`cp`, the agent's words) into the worktree's `.reef/ci-local/` and checked with `reef-claims.py report`, the hunter's PASS recorded with `reef-adversarial … guard`; the in-flight marker is removed. `READY TO MERGE <id>` → `/reef-task` step 4 for that task (commit in the worktree, `merge --no-ff` into the feature branch, `status: done`, the journal row with `reef-cost.py growth <id>`). `FAIL <id>: <why>` → the attempt is already counted (`reef-attempt <task> "<why>"`); the next `generate` re-dispatches it with the failure text, under the same caps.

## Rules
- The results files are summaries, not evidence: the evidence is the hand-back in the worktree and the report files the judges wrote; the guard still refuses you writing those.
- A task the results omit (the agent died or was skipped) is still in flight to the tick until you run `settle`; `settle` clears every marker it sees in the results — a missing one you clear by re-running `generate` for it.
- Measured, 2026-10-18 (`docs/perf/2026-10-18.md` §C): the first graph-mode task cost the orchestrator 6 turns at ≤ 46k where chat mode paid ≈ 25 at 90–150k; `graph.mode: auto` (read from the main checkout) now makes the tick name the mode per task — `dispatch (graph)` → this skill, `dispatch (chat)` → `/reef-task` (a fix round, a `verify now`, or no gate). `reef-cost` attributes a Workflow call's tasks (from the script's `REEF-TASK:` lines) to their features and tasks as role `workflow`.
