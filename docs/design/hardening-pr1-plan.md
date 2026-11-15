# Hardening PR-1 — deterministic gates for the implementer's round

Two lines of `agents/implementer.md` ask the model to behave: "failing test first (show the red)" and "Touch only what the
task scope names". Nothing checks either. This PR turns both into a check that refuses with a non-zero exit and one line.

## What

`python3 scripts/reef-claims.py round <task-file> [--base REV] [--repo DIR]` — the implementer's round, judged on the
worktree that holds it (the task's work is uncommitted there: the implementer never commits). Exit 0 ok · 1 refused (one
`round: REFUSED — <reason>` line per failure) · 2 usage/git error.

- **(a) red first.** The named tests of the task's `## Proof` table (cells matching `plan.test_re`, default the plan
  check's `DEFAULT_TEST_RE`) must FAIL on the base with the round's test files in place, and PASS on the round's tree.
- **(b) declared files.** Every path the round changed (tracked changes vs the base, and untracked files) must match the
  task's `files:` frontmatter list.

## Where it is wired (no parallel pipeline)

- `scripts/reef-merge-close` — the one close both paths go through — runs the round check on the task's uncommitted work
  before it stages anything (fast path: the feature worktree, base `HEAD`; critical path: the task worktree, base the
  merge-base of its branch with the feature branch). A refusal is exit 2, nothing changed. This is the enforcement: a close
  cannot skip it.
- `skills/reef-task/SKILL.md` step 3 runs the same command right after the hand-back check, so a refused round goes back to
  the implementer (`reef-attempt <task> "<the refusal>"`) before any judge is spawned.
- `agents/implementer.md`: the two prose lines point at the check instead of asking.

## Design decisions (flagged for the owner)

1. **`touches:` is NOT a file list.** In this codebase `touches:` is a list of risk classes (`pii|money|auth|migration`,
   `schemas/task.schema.json`, `reef-plan-check.py` TOUCHES, `reef-tier.py`); it forces a tier. Reusing it for paths would
   break the plan check (it rejects any value outside the four classes) and mix two meanings. So the declared files are a
   NEW frontmatter key, `files:`, a bracket list like `blocked-by:`.
   **Owner decision (2026-11-15): `files:` is REQUIRED for new plans.** `reef-plan-check.py` fails an unfinished task
   without a non-empty `files:` when its feature is planned under this rule: the feature is recorded in the stamp's new
   `files_rule` list, or it is absent from the previous stamp's `planned_under` and has no approval record in the main
   checkout (a plan being written now). A feature already stamped before this rule, or already approved (a stampless task
   worktree of an approved plan), keeps closing: its tasks get a `warning:` line, never a failure. Not a layout bump: a
   feature's `planned_under` is written only after its first passing check, so a version compare would let a planner's
   first run pass without `files:`. A 0.5 project (no `.reef/version`, no feature folder) only warns, as for every 0.6 rule.
   The round check itself stays as it was: a task without `files:` (an old plan) is not scope-checked there.
   An entry that matches every path (`*`, `**`, `**/*`, `./`, `/`, `.`, empty) fails the plan check: it would make the
   scope check a no-op.
2. **Path matching.** An entry ending in `/` is a directory prefix (`src/export/` covers everything under it); any other
   entry is an `fnmatch` glob on the repo-relative path (`src/*.py`; an entry without metacharacters is an exact path; `*`
   crosses `/`, as in Python's `fnmatch`). The task folder (the directory holding the task file, `done/` included) is
   always allowed: the close itself edits it. Nothing else is implicit — the tests a task adds are declared too
   (`tests/test_export.py` or `tests/`).
3. **How "fails on the base" is run.** A named test exists only in the round's diff, so "on the base" means: the base's
   code with the round's TEST files in place. The check sets every changed non-test file back to the base in place
   (backup and a recovery manifest under `<git-dir>/reef-red-<id>/` first; restored in `finally`, and by the next run if a
   kill cut it off), runs the test, and restores. In place, not a fresh worktree: a fresh checkout has no installed
   dependencies (`node_modules`, a venv) and every test would fail for that reason — a red that proves nothing. A path is a
   test file when a segment is `test`, `tests`, `__tests__`, `spec` or `specs`, or its name is `test_*`, `*_test.*`,
   `*.test.*` or `*.spec.*`.
4. **The command.** `gates.one`, a new optional config key: a command with `{test}`, run once per named test (the name is
   shell-quoted). Without it, the fast gate (`scripts/reef-gate.sh fast`) is the command, once: it must pass on the round's
   tree and fail on the base with the tests in place (the base passed the commit gate, so the added tests are what fails).
   A run that times out (exit 124) is a refusal, never counted as red.
5. **Skipped, with one line each, never refused:** `kind: refactor` (behaviour preserved, `refactor-preserved` is its
   check), a rollup `R<NN>` task, a task whose Proof names no test (commands and HUMAN rows only), no `## Proof` table.
6. **No escape hatch.** A task whose test already passes on the base is refused; the owner decides (re-plan, or the
   unblock). An earlier rule made an out-of-scope touch a NIT for the judges; with `files:` declared it is now a refusal
   at the round, before the judges.

## Tests (each red before the change, green after)

New file `tests/test_round_gate.py`, real git repos in temp dirs:
- red: a task whose new test fails on the base passes the round check (exit 0).
- red: a task whose named test already passes on the base is refused (exit 1, `does not fail on the base`), and the
  worktree's code is back as it was after the check.
- red with `gates.one`: the per-test command is used, `{test}` substituted.
- scope: a change to a file outside `files:` is refused naming the file; a directory prefix and a glob are honoured; an
  untracked new file outside the list is refused; the task folder is always allowed.
- scope: a task without `files:` is not scope-checked (one `scope: not declared` line, exit 0).
- plan check: a catch-all entry (`files: ["*"]`, `[**]`, `[./]`) fails the check.
- plan check: a new feature's task without `files:` fails the check; with `files:` it passes; a feature already in the
  stamp before the rule (or approved) only warns.
- skip: `kind: refactor` and a Proof with no test name skip the red check.
- recovery: a manifest left by a killed run is restored by the next run.
- merge-close: a fast-path close of a round whose test passes on the base is refused (exit 2) with nothing committed.
- contracts: `agents/implementer.md` names `reef-claims.py round`; `skills/reef-task/SKILL.md` step 3 runs it.

## Out of scope

- command Proof rows (`<command that exits 0 iff …>`): not run on the base in this PR.
- the plan check validating that `files:` paths exist (only presence and list shape are checked).
- the graph runner (`reef-graph-run.py`) beyond what merge-close already covers; the verifier/reviewer NIT prose.
- any refactor of merge-close, the gate or the claims checker.
