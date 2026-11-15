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
  optionally `path#symbol`; or a non-path artifact (a table, an endpoint) named the way the upstream task names it.
- One line, like `blocked-by:` and `files:` (the frontmatter parser is a one-line-per-key subset). An artifact holds no
  comma.

`scripts/reef-plan-check.py` adds one FAIL line per defect, on the authoring rules' voice (silent on a finished task, and
for another feature under `--feature`):

1. **missing artifact** — a blocked-by id with no `consumes:` entry: `<task>: blocked-by 101 consumes nothing — name the
   artifact 101 produces that this task reads (`consumes: [101: <path>]`), or drop the edge`.
2. **not produced upstream** — an entry whose artifact the upstream task does not produce (the check below).
3. **stray entry** — a `consumes:` entry for an id not in `blocked-by` (a hand-off with no edge lets the two run at once).
4. **malformed** — `consumes:` not a list, an entry not `<int>: <artifact>`, an empty artifact, or an artifact with a glob
   metacharacter (`*?[`) or one that names every path (`.`, `./`, `/`): a consumed artifact is one thing, not a pattern.

## How "produces" is checked (the mechanical part, and its limits)

An entry `101: <artifact>` holds when ANY of:

- (a) **the path is in 101's `files:`** — the artifact's path part (before `#`) matches an entry of the upstream task's
  `files:` with the round check's matcher (`dir/` a prefix, else `fnmatch`). This is the strong case: PR-1's round check
  refuses 101's round if it changes anything outside `files:`, so the path is a file 101 is allowed — and declared — to
  write.
- (b) **101's `## Scope` names it** — the whole artifact appears in the upstream task's `## Scope` section as a code span
  (`` `orders.total_cents` ``, `` `GET /orders` ``). For artifacts that are not files.
- (c) **101 is finished and declares no `files:`** (an older plan, under `tasks/done/`) and the path exists in the repo:
  the thing is already there.

Limits, stated plainly:

- (a) proves 101 **may** write the path, not that it does; a `#symbol` suffix is not checked against the code (the plan
  check reads plans, not code). The round check and the judges are what see the diff.
- (b) is a string match on 101's scope: it proves the planner wrote the artifact down on both ends of the edge, not that
  101 builds it. Weaker than (a); it exists so a table or an endpoint can be a hand-off at all.
- The check does not prove a blocked-by edge is *needed* — only that it carries a named, upstream-declared hand-off. A
  planner can still name a real file the downstream does not read. That is the plan reviewer's call, now on a concrete line.

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
- **Finished tasks** (under `tasks/done/`): the authoring rules do not run on them, so they are never refused; as an
  upstream they are judged by (a), (b) or (c).
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
- an artifact outside 1201's `files:` and not in its Scope FAILs `does not produce`; one named as a code span in 1201's
  Scope passes.
- a `consumes:` entry for an id not in blocked-by FAILs `not in blocked-by`.
- malformed: `consumes: [x: a]`, `[1201: src/*]`, `[1201: ]` FAIL.
- gating: the same plan with the feature already in `planned_under` (an older plan) only warns `consumes nothing`, exit 0.
- a rollup with a blocked-by and no consumes is not refused.

## Fixture churn

Any test fixture that writes a NEW plan with a non-empty blocked-by needs a `consumes:` line; listed in the PR body.

## Out of scope

- checking a `#symbol` against the code; checking the artifact exists on disk for an unfinished upstream.
- the guard, the graph runner, the round check — the edge's ordering semantics are unchanged.
- any refactor of the plan check.
