---
name: reef-task
description: Execute an approved Reef feature as a task GRAPH — every task whose dependencies are done is dispatched in parallel, each in its own worktree, through the implement->verify->merge loop with mechanical retry caps. Use when groomed tasks are ready to build, or the user says "/reef-task".
argument-hint: <feature-slug | task-ref | list>
---

# Reef Task — the graph

**Input:** approved task files (`$ARGUMENTS`: a feature slug, task refs; empty — run `scripts/reef-graph.py status` and ask which).
**Output:** one merge per passed task into the feature branch (no push — that is `/reef-review`'s job) + journal rows.

You are the orchestrator: a MANAGER. You never write production code, never verify, and never accept a report on faith. Read `.reef/config.json`.

## 0. Plan review — before the FIRST dispatch only
Run `scripts/reef-plan-check.py --verify-stamp --feature <slug>` in the task's own worktree (the
stamp is per-worktree and per-feature). Exit 0 = this feature's plan is unchanged since its last
review; proceed. Non-zero = never reviewed, or edited since — invoke the `reef-plan-review` skill,
show the human its result, and only then continue. A plan the human edited after approval is an
unreviewed plan; the stamp is what knows that, not you.

## 1. The ready set — computed, never remembered
Run `scripts/reef-graph.py ready --json`. It lists every task whose `blocked-by` are done, whose declared `resources:` have a free slot, within `graph.parallel`. A broken graph (cycle, missing id) is exit 1 — STOP; it is a plan defect. **Dispatch every ready task now, in one message, not one at a time** — serial execution of a parallel-ready set is the waste this skill exists to remove. The guard enforces the same rule from the other side: it refuses a dispatch of a task outside the ready set, so a wrong dispatch cannot run; a missing one is on you. End each turn with one line: `in flight: … / waiting on: …`.

## 2. Dispatch — mechanical, not from memory (per ready task)
1. `scripts/reef-graph.py worktree <task-file>` — creates (or reuses) `.reef/worktrees/<id>` on `task/<id>-<slug>` from the feature branch and runs the project's `worktree.setup` (its own `node_modules`/generated client — never the shared one). The implementer works THERE; the task file stays in your checkout — implementers never touch `tasks/`.
2. `scripts/reef-attempt <task-file>`. Exit 2 = blocked -> print its USER ACTION REQUIRED and park that task (the rest of the graph continues). Otherwise use EXACTLY what it prints: its model as the Agent call's model parameter, its effort in the prompt, and START THE PROMPT with the `REEF-TASK: <task-file>` line it printed. The PreToolUse guard refuses any implementer dispatch without that line, any blocked/at-cap task, a stale stamp, and any task outside the ready set — and on allow marks the task `in-progress` and advances its `dispatches:` odometer. The cap holds even if you forget a step.
3. Spawn the `implementer` agent with the task file, the worktree path as its working directory, resolved model/effort. Prompt ≤ 120 words: the stable brief lives in the agent file. mech tasks with a tiny expected diff (<~40 lines): you MAY implement inline in the main session instead — record that in the Log. Design tasks: refuse if `## Decision` is empty.

## 3. Verify (in the task's worktree)
- `verify: gate-only` (mech): run the full gate there (`scripts/reef-gate.sh full`; heavy suites through `scripts/reef-graph.py lock heavy -- <cmd>`) + require a golden-output test for user-visible output. No judge subagent — that is the cost lesson; do not "helpfully" add one.
- `verify: judge` (design): record `scripts/reef-snapshot.sh` in the worktree (a CONTENT hash over HEAD + index + worktree). Spawn the `verifier` agent fresh with that directory, passing the model from the `verifier: model=` line `reef-attempt` printed (roles.verifier). After it returns, re-run the snapshot: ANY difference = automatic FAIL regardless of verdict. Require the `RUN:` header line, a `RULE AC<n>` line per criterion ABOVE the verdicts (written before the verifier read the diff), and evidence per AC. On a retry (`attempts > 0`) the verifier attacks the last round's fix first.
- `tier: design`: the `loophole-hunter` agent runs on the finished guard before the merge (its first pass, on the plan, ran before code); a BLOCKER is a FAIL.
- **A finding on a claimed AC = FAIL** — `scripts/reef-attempt <task-file> "<failure text>"` and re-dispatch (step 2, same worktree — the task is already `in-progress` and keeps its slot). Never launder findings into backlog tasks; only genuinely out-of-scope findings become new tasks, recorded in the runlog's "Escaped defects" column.

## 4. Merge (on PASS only) — you are the feature branch's single writer
In the worktree: stage specific files (never `git add -A`), commit with a Conventional Commits subject and trailer `Closes-task: NNN-slug`; the pre-commit gate tests the index — no bypass, ever. Then in YOUR checkout: `git merge --no-ff task/<id>-<slug>`; in that same merge commit set `status: done`, `git mv` the task file to `tasks/done/`, append the runlog row (`paths.runlog`) from the RUN: line — written here, at the merge, never on the task branch, never from memory; `git worktree remove .reef/worktrees/<id>` and delete the branch. Merge only after the agent's FINAL hand-back, never on seeing its report. Then go to step 1: the merge may have unblocked more of the graph.

## 5. Stop conditions
A blocked task parks itself; the graph continues around it. The pipeline STOPS when nothing is ready and nothing is in flight: all done (hand to `/reef-review`) or only blocked/parked tasks remain (USER ACTION REQUIRED, list them). Failure is a STOP, not an improvisation point.

## Trust nothing without evidence (applies to every step)
When a sub-agent reports success, verify before advancing: the named tests exist (`grep`), the claimed output reproduces (run it once, in the worktree), the diff touches only the task's scope (`git diff --stat`). A hand-off without evidence is a FAIL report, re-dispatched once with "evidence required" — that re-dispatch does NOT consume an attempt.

## Re-entry (session died / compaction / interruption)
State lives on disk — recover it, don't guess:
1. `scripts/reef-graph.py status` — what is in-progress (holding a worktree and resources), ready, waiting, blocked.
2. For each `in-progress` task: `git -C .reef/worktrees/<id> status` — uncommitted implementer work present → do NOT re-implement; go to step 3 for it.
3. `status: blocked` → USER ACTION REQUIRED. Never reset attempts yourself — the human unblock is THREE fields: `attempts: 0`, `status: pending`, `last_failure_sig: ""`.

## Notes on shape
This file owns ONLY the per-feature graph loop. Planning lives in reef-plan; push/PR/acceptance/CI live in reef-review; the verification contract in reef-verify; the ready-set arithmetic in scripts/reef-graph.py; the cap arithmetic in scripts/reef-attempt. Edit those, not this. Do not add mid-loop human gates — the human gates are plan approval and the release.
