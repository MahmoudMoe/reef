---
name: reef-task
description: Execute one or more approved Reef tasks through the implement->verify->commit loop with mechanical retry caps. Use when groomed tasks are ready to build, or the user says "/reef-task".
argument-hint: <task-ref | list>
---

# Reef Task — the loop

**Input:** one or more approved task files (`$ARGUMENTS`: task refs or a feature slug; empty — list pending tasks and ask which).
**Output:** one commit per passed task on the current branch (no push — that is `/reef-review`'s job) + runlog rows.

You are the orchestrator: a MANAGER. You never write production code, never verify, and never accept a report on faith. Read `.reef/config.json`.

## 0. Plan review — before the FIRST dispatch only
Run `scripts/reef-plan-check.py --verify-stamp`. Exit 0 = the plan is unchanged since its last
review; proceed. Non-zero = never reviewed, or edited since — invoke the `reef-plan-review` skill,
show the human its result, and only then continue. A plan the human edited after approval is an
unreviewed plan; the stamp is what knows that, not you.

Per task, in `blocked-by` order:

## 1. Dispatch — mechanical, not from memory
Run `scripts/reef-attempt <task-file>`. Exit 2 = blocked -> print its USER ACTION REQUIRED and STOP the pipeline. Otherwise use EXACTLY what it prints: pass its model as the Agent call's model parameter (overrides the frontmatter default), and state its effort in the dispatch prompt (e.g. "reasoning effort: high") — frontmatter effort keys are inert. Never dispatch without it; never repeat a model+effort after a failure (the script enforces the ladder).

## 2. Implement
Spawn the `implementer` agent (this plugin) with the task file, resolved model/effort, and working directory. mech tasks with a tiny expected diff (<~40 lines): the orchestrator MAY implement inline in the main session instead — record that in the Log. Design tasks: refuse if `## Decision` is empty (send the human back to /reef-plan step 3).

## 3. Verify
- `verify: gate-only` (mech): run the gate (`scripts/reef-gate.sh`) + require a golden-output test for user-visible output. No judge subagent — that is the cost lesson; do not "helpfully" add one.
- `verify: judge` (design): record `git rev-parse HEAD` + hash of `git status --porcelain`. Spawn the `verifier` agent fresh. After it returns, re-hash: ANY tree difference = automatic FAIL regardless of verdict. Require the `RUN:` header line and evidence per AC.
- **A finding on a claimed AC = FAIL** — run `scripts/reef-attempt <task-file> "<failure text>"` and loop to step 1. Never launder findings into backlog tasks; only genuinely out-of-scope findings become new tasks, recorded in the runlog's "Escaped defects" column.

## 4. Commit (on PASS only)
Stage specific files (never `git add -A`), set `status: done`, `git mv` the task file to `tasks/done/` in the SAME commit, Conventional Commits subject, trailer `Closes-task: NNN-slug`. The pre-commit gate tests the index; do not bypass it (no `--no-verify`, ever). Append the runlog row from the RUN: line + harness usage numbers verbatim — never from memory.

## 5. Next task
Failure of the pipeline is a STOP, not an improvisation point.

## Trust nothing without evidence (applies to every step)
When a sub-agent reports success, verify the evidence is real before advancing: the named tests exist (`grep` them), the claimed output reproduces (run the command yourself once), the diff touches only the task's scope (`git diff --stat`). A hand-off without evidence is treated as a FAIL report, re-dispatched once with "evidence required" feedback — that re-dispatch does NOT consume an attempt (the work may be fine; the report wasn't).

## Re-entry (session died / compaction / interruption mid-task)
State lives on disk, not in your memory — recover it, don't guess:
1. `git status` + `git log --oneline -5` — is there uncommitted implementer work?
2. The task file's frontmatter — `attempts:`/`status:` say exactly where the cap stands (reef-attempt owns them).
3. Uncommitted work present + task not done → do NOT re-implement; go straight to the verify step for that work.
4. `status: blocked` → USER ACTION REQUIRED, stop. Never reset attempts yourself — that is a human edit.

## Notes on shape
This file owns ONLY the per-task loop and its caps. Planning lives in reef-plan; push/PR/acceptance/CI live in reef-review; the verification contract lives in reef-verify; the cap arithmetic lives in scripts/reef-attempt. Edit those, not this. Do not add mid-loop human gates — the human gates are plan approval and final merge.
