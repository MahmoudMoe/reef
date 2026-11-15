# Hardening PR-5 — honest edges

`blocked-by: [101]` says "wait for 101" and nothing else. An edge can be ordering by habit (a decorative wait that costs
wall-clock) or hide a hand-off nobody wrote down (the downstream needs a file 101 never declared it would produce). The
owner's goal: **reef-plan-check refuses a blocked-by without the artifact it consumes.**

## What

A new task frontmatter key, `consumes:`, a bracket list of `<id>: <artifact>` entries — one or more per blocked-by id:

```yaml
blocked-by: [101, 102]
files: [src/export/report.py, tests/test_report.py]
consumes: [101: src/export/csv.py, 102: src/api/orders.py#list_orders]
```

- `<id>` is a blocked-by id. `<artifact>` is the concrete thing that task produces and this one reads: a repo path,
  optionally `path#symbol` (the symbol is documentation; it is not checked against code). A table or an endpoint is named
  by the file that creates it (the migration, the route file) — **paths only** (owner ruling 1, below).
- One line, like `blocked-by:` and `files:` (the frontmatter parser is a one-line-per-key subset). An artifact holds no
  comma.

`scripts/reef-plan-check.py` adds one FAIL line per defect, on the authoring rules' voice (silent on a finished task, and
for another feature under `--feature`):

1. **missing artifact** — a blocked-by id with no `consumes:` entry: `<task>: blocked-by 101 consumes nothing — name the
   artifact 101 produces that this task reads (`consumes: [101: <path>]`), or drop the edge`.
2. **not produced upstream** — an entry whose artifact the upstream task does not produce (the check below).
3. **stray entry** — a `consumes:` entry for an id not in `blocked-by` (a hand-off with no edge lets the two run at once).
4. **malformed** — `consumes:` not a list, an entry not `<int>: <artifact>`, an empty artifact, an artifact with a glob
   metacharacter (`*?[`) or one that names every path (`.`, `./`, `/`) — a consumed artifact is one thing, not a pattern —
   or one whose path holds whitespace (`GET /orders` is not a repo path).

## How "produces" is checked (the mechanical part, and its limits)

**At plan time** (`reef-plan-check.py`): an entry `101: <artifact>` holds only when the artifact's path part (before `#`)
matches an entry of the upstream task's `files:` with the round check's matcher (`dir/` a prefix, else `fnmatch`). PR-1's
round check refuses 101's round if it changes anything outside `files:`, so the path is a file 101 is allowed — and
declared — to write. Anything else (a path outside 101's `files:`, a bare table or endpoint name, an upstream with no
`files:`) is `not produced`.

**At close time** (owner ruling 2): `reef-claims.py round` — the check `reef-merge-close` runs on both paths before it
stages anything, and `/reef-task` step 3 runs after the hand-back — gets a third part, **(c) hand-offs**. For every OPEN
task (not under `done/`, not a rollup) in the closing task's own tasks folder whose `consumes:` names the closing task's
id, each consumed path:
- must **exist** on the closing tree (the worktree the round is judged in); and
- if it did **not exist on the base** (`git cat-file -e <base>:<path>` fails), must be **among the round's changes** (the
  tracked diff vs the base plus untracked, not-ignored files — the same list the scope check reads).
A path that existed on the base and that the round leaves unchanged is accepted (the conservative reading of the ruling:
it is there for the downstream, and the upstream's `files:` still names it — e.g. a task that only adds to a table its
migration already created). In practice the second clause catches a file that exists but is **ignored** (a build output
under `.gitignore`): it is on disk in the worktree and never reaches the commit, so the downstream would not see it.
A failure is a `round: REFUSED — <downstream task file> consumes <id>: <path> — <missing on the closing tree | not
changed by this round (ignored, or made by something else)>` line; merge-close turns it into exit 2, nothing changed.

Limits, stated plainly:

- Plan time proves 101 **may** write the path; close time proves it **exists and came from this round** (or was already
  there). Neither checks a `#symbol` against the code — the judges see the diff.
- The close-time scan covers downstream tasks in the closing task's own tasks folder (a feature folder's `tasks/`, or
  the flat `tasks/`). A downstream in another feature's folder is checked at plan time only.
- On the critical path the round check runs on a dirty task worktree only (as PR-1 does): a task whose work was already
  committed on its branch is not re-checked at the close.
- The check does not prove an edge is *needed* — only that it carries a named, upstream-declared, delivered hand-off.

## Gating (like PR-1's `files:` rule; never breaks an approved plan)

- A feature is **under the rule** when it is in the stamp's new `edges_rule` list, or it is new now (absent from the
  previous stamp's `planned_under` and no approval record in the main checkout — the same "new plan" test PR-1 uses). Its
  stamp records it in `edges_rule` after the first passing check, so the rule keeps holding while the planner iterates.
- **Rule 1 (missing artifact) is the gated one**: under the rule it FAILs; otherwise a `warning:` line, never a failure.
  A feature already stamped or approved before this PR (including one already in PR-1's `files_rule`) only warns.
  `files_rule` is not reused: a plan drafted after PR-1 and approved before PR-5 has `files:` and no `consumes:`, and it
  must keep closing.
- **Rules 2–4 judge a `consumes:` that is present**, on every authored task, gated or not. No plan before this PR carries
  the key, so no existing plan can fail them; a planner who writes the key gets it checked.
- A 0.5 project (no `.reef/version`, no feature folder) only warns, as for every 0.6 rule.

## Special task kinds

- **Rollup `R<NN>`**: exempt from all four rules (it is written by the review, not the planner, and takes no dependents —
  same as `files:`). Its blocked-by keeps the existing "refers to missing task id" check.
- **Finished tasks** (under `tasks/done/`): the authoring rules do not run on them, so they are never refused. As an
  upstream, a finished task of an older plan with no `files:` produces nothing the check can see: an edge onto it cannot
  name an artifact, so the planner drops that edge (the upstream is done; the wait it expressed is already satisfied).
- **`kind: refactor`**: no exemption. A refactor that waits on a task reads what that task wrote, same as any other.
- **An upstream with an unparseable or missing file**: rule 1's existing sibling ("blocked-by refers to missing task
  id(s)") already fails; the consumes checks skip that id.

## Where it must appear

- `templates/task.md`: `consumes: []` after `files: []`.
- `schemas/task.schema.json`: `consumes` — array of `<id>: <artifact>` strings, described.
- `agents/planner.md` and `skills/reef-plan/SKILL.md`: one line each naming the key next to `files:` and blocked-by.
- `reef-plan-check.py --rules`: one line.
- The digest: `consumes:` is plan text (not execution state), so it is hashed like `files:` — no change needed.

## Tests (each red before the change, green after)

`tests/test_feature_spec.py` (`Rails`, the same fixtures as PR-1's `files:` tests), a two-task feature, 1202 blocked by
1201:
- a new plan whose 1202 has `blocked-by: [1201]` and no `consumes:` FAILs `consumes nothing`; with
  `consumes: [1201: src/export.py]` (in 1201's `files:`) it passes.
- an artifact outside 1201's `files:` FAILs `does not produce`; `path#symbol` inside it passes; a bare
  `orders.total_cents` FAILs even when 1201's Scope names it (paths only).
- a `consumes:` entry for an id not in blocked-by FAILs `not in blocked-by`.
- malformed: `consumes: [x: a]`, `[1201: src/*]`, `[1201: ]` FAIL.
- gating: the same plan with the feature already in `planned_under` (an older plan) only warns `consumes nothing`, exit 0.
- a rollup with a blocked-by and no consumes is not refused.

`tests/test_round_gate.py` (real git repos): the round of 1201, with an open 1202 consuming `1201: src/calc.py` /
`1201: src/new.py`:
- refused when the consumed path is missing on the closing tree; refused when it is new and ignored (exists, not in the
  round's changes); passes when the round creates it; passes when it existed on the base and is unchanged.
- merge-close (fast path): a close whose open downstream consumes a path the round did not produce is refused, exit 2,
  nothing committed; the same close with the path produced closes.

## Fixture churn

Any test fixture that writes a NEW plan with a non-empty blocked-by needs a `consumes:` line; listed in the PR body.

## Out of scope

- checking a `#symbol` against the code; checking the artifact exists on disk for an unfinished upstream.
- the guard and the graph runner — the edge's ordering semantics are unchanged.
- any refactor of the plan check.

## Owner rulings (2026-11-15, relayed by the orchestrator)

1. **Paths only.** The `## Scope` code-span route for non-file artifacts, drafted first, is dropped: every artifact is a
   repo path matching the upstream's `files:`; `#symbol` is documentation; a bare non-path artifact fails.
2. **Close-time check, in this PR.** When an upstream task closes, each path an open downstream consumes from it must exist
   on the closing tree and be changed by its round unless it existed on the base (above, "At close time").
