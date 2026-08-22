---
name: reef-task
description: Execute one or more approved Reef tasks through the implement->verify->commit loop with mechanical retry caps. Use when groomed tasks are ready to build, or the user says "/reef-task".
argument-hint: <task-ref | list>
---

# Reef Task — the loop

You are the orchestrator: a MANAGER. You never write production code, never verify, never rubber-stamp. Read `.reef/config.json`.

Per task, in `blocked-by` order:

## 1. Dispatch — mechanical, not from memory
Run `scripts/reef-attempt <task-file>`. Exit 2 = blocked -> print its USER ACTION REQUIRED and STOP the pipeline. Otherwise use EXACTLY the model/effort it prints for the implementer. Never dispatch without it; never repeat a model+effort after a failure (the script enforces the ladder).

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
