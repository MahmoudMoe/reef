# Hardening PR-12 — the round check leaves no byte-code behind

Found in PR-6's review (`hardening-pr6-plan.md`, "Found while testing"): `reef-claims.py round` runs the project's tests in
the task worktree (`round_run`, twice per named test: the round's tree, then the base), and since PR-6 `reef-merge-close`
runs it on every unmerged task branch. Python writes `__pycache__/*.pyc` next to every module the tests import. In a project
whose `.gitignore` does not ignore them (`/reef-init` adds `__pycache__/` only when it detects the python stack), that
byte-code is a new untracked file in the task worktree.

## What it breaks today (main, e5d2197)

`round_changes` = `git diff --name-only <base>` + `git ls-files --others --exclude-standard`: **untracked files count**. It is
read *before* the runs, so the check's own byte-code is not judged by the run that made it — but by everything after it:

1. **dirty close** — `dirty` is decided before the check; after it, `git add -A` stages the check's `src/__pycache__/*.pyc`
   and `tests/__pycache__/*.pyc` into the task commit: **byte-code merged into the feature branch**.
2. **clean close** (work committed on the branch, PR-6's new path) — nothing stages it, so after the merge
   `git worktree remove` refuses (untracked files): `task/… is merged but its worktree stays … — fix that and re-run`.
3. **a re-run after a refused close** — the first check's byte-code is now an untracked change of the round: with a narrow
   `files:` (`[src/, tests/test_calc.py]`) the scope check refuses `outside the task's files: tests/__pycache__/…`; a
   hand-off check is not tripped (it only looks at consumed paths), but the same byte-code is swept into the commit as in 1.

Other caches checked: `.pytest_cache/` writes its own `.gitignore` (`*`, measured with pytest 9.2.0) and `git worktree
remove` ignores ignored files (measured, git 2.43) — not a problem. `.mypy_cache/`, `.ruff_cache/` do the same. Coverage
data, `node_modules/`, `target/` are the project's own config, not something the round's runs add by themselves.

## The fix (the smallest correct one)

- `round_run` runs every command with `PYTHONDONTWRITEBYTECODE=1` in its environment. Python (and pytest's assertion
  rewriter, which honours `sys.dont_write_bytecode`) then writes no byte-code: the check creates no file to clean up.
- `reef-merge-close` sets the same variable for itself (`os.environ`), so the commands it spawns in the task worktree — the
  round check, the task worktree's commit and the merge commit, whose `.githooks` gate runs the tests — write none either
  (flagged **D2**).

Why this and not a filter or a sweep:
- **It cannot hide a real change.** `round_changes`, the scope check and the hand-off check are untouched: a `.pyc` or a
  `__pycache__/` that is committed on the branch or written by the implementer still counts and is still checked (a test
  holds it). Filtering cache-named paths out of `round_changes` would hide exactly that.
- **It deletes nothing.** Sweeping "untracked files that appeared during the runs" would delete whatever else a test or a
  person wrote into the worktree meanwhile — files Reef did not make (flagged **D1**: not done).
- Cost: Python re-compiles in memory on each run (no cache read either). The round is two test runs per close; measured
  noise, not a slowdown worth a cache.

Limits, stated: byte-code the implementer's own test runs left before the close is the implementer's (and the project's
`.gitignore`'s), not the check's — unchanged; a non-Python runner that writes an un-ignored cache into the tree is not
covered (none of the stacks Reef detects does by default).

## Tests (each red before the change, green after)

`tests/test_round_gate.py`, a critical-path close (task worktree on `task/101-add`, real git), the project's `.gitignore`
**without** `__pycache__/`:
- the round committed on the branch, red first holds → closes (exit 0), and the task worktree is removed (red today: exit 2,
  `merged but its worktree stays`).
- the round uncommitted (dirty) → closes, and no `__pycache__/` path is in the merged tree (red today: the `.pyc` files are
  merged).
- the check run twice on the same round (a re-run after any refusal), `files: [src/, tests/test_calc.py]` → the second
  run's scope check passes (red today: `outside the task's files: tests/__pycache__/…`).
- not hidden: a `.pyc` the round adds on purpose (`src/__pycache__/keep.pyc`, committed), with `files: [src/calc.py, tests/]` → still
  refused `outside the task's files: src/__pycache__/keep.pyc`.

## Decisions (flagged for the owner; the most conservative choice is implemented)

- **D1** prevent, don't clean: no sweep of files that appear during the runs, no cache filter on `round_changes`.
- **D2** `reef-merge-close` sets `PYTHONDONTWRITEBYTECODE=1` for everything it spawns (the gate hooks of its commits too),
  not only the round check's runs.

## Out of scope

The `.gitignore` lines `/reef-init` writes; `reef-gate.sh`; the glossary part another PR adds to `round`; any refactor of
`round_changes`, `cmd_round` or merge-close.
