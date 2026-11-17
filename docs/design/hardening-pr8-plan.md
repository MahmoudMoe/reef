# Hardening PR-8 — an agent reads only the ADRs that touch its task's files

Today `agents/implementer.md` and `agents/planner.md` tell the agent to read EVERY Accepted ADR (the feature's `adr/`,
`reef/architecture/adr/`, the legacy `paths.adr`). The load grows with every ADR the project accepts, and most of them govern
code the task never touches. This PR makes an ADR declare the paths it governs and lets CODE choose which ADRs a dispatch
carries — the "single source of truth" idea (mattpocock/skills), applied to the ADR load.

## Today (main, e5d2197)

| reader | what it reads | chosen by |
|---|---|---|
| implementer | every Accepted ADR of the feature + project + legacy | prose (`implementer.md:11`) |
| planner | every Accepted ADR of the feature + `reef/architecture/adr/` | prose (`planner.md:11`) |
| verifier | `docs/adr/` only (the legacy path; 0.6 ADRs never read) | prose (`skills/reef-verify/SKILL.md`) |

## What changes

### 1. An ADR declares its paths — a `Paths:` line (templates/adr.md)

- One line under `Status:`: `Paths: src/auth/, src/session.py, tests/test_auth*.py`.
- Each entry is a `files:` pattern, the SAME matcher PR-1's round check uses (`reef-claims.py round`): `dir/` is a prefix, else an
  `fnmatch` glob. `Paths: *` = cross-cutting (every task loads it).
- A line, not frontmatter: the template and every ADR already carry `Status:` as a plain line; one more plain line keeps the
  shape (and the plan digest, which strips only the Status line, covers it — a Paths edit voids the approval like any edit).
- No `Paths:` line, an empty one, or the template's `<…>` placeholder = **undeclared**: the ADR is still loaded for every task
  (conservative — a missing declaration never drops a decision), and `reef-plan-check.py` prints a `WARN` naming it.
- `reef-init`'s draft ADRs (shape/host/store/auth: the whole project) get `Paths: *`, so a fresh project starts warning-free.

### 2. Code selects — `scripts/reef-adrs.py` (CLASS: code, new)

- `task <task-file>`: the implementer's block. Candidates: the Accepted ADRs of the task's feature `adr/`, of
  `reef/architecture/adr/` and of `paths.adr`. Kept: an ADR whose Paths meet the task's `files:`, and every undeclared ADR.
- `feature <slug>`: the planner's list — every Accepted ADR of the feature's own `adr/`, plus the project ADRs whose Paths meet
  the UNION of the feature's tasks' `files:` (and the undeclared). A feature with no task carrying `files:` yet (a fresh plan)
  gets every project ADR: before the split nothing can be scoped.
- `paths <path>…`: the verifier's list — the Accepted ADRs whose Paths match any of the given repo paths (the diff's names), plus
  the undeclared.
- "Meet" for two patterns (a task's `files:` entry is a pattern, not a path): a concrete path is checked with the round's
  matcher; two globs meet when one's literal prefix (up to the first `*?[`) starts the other's. Sound: a path matching both
  starts with both prefixes. It may over-include, never under-include.
- No `files:` on the task (legacy plans; PR-1 requires it on new ones): every Accepted ADR, and the header says why.
- Superseded / Proposed ADRs are not candidates (as today: "every Accepted ADR").

The block (printed by `task`, by `reef-attempt` at dispatch, after `lessons:`):

```
adrs: 2 of 5 Accepted ADRs touch this task's files: — read each, nothing else; pass every line through `adrs: end` verbatim
  reef/architecture/adr/0003-auth.md (Paths: src/auth/)
  reef/features/demo/adr/draft-demo-store.md (Paths: not declared — loaded for every task)
adrs: end
```

No Accepted ADR in the project: no block (nothing to carry, as `dead-ends:` with no FAIL). ADRs exist but none match: the header
says `0 of 5` and the block is the header and `adrs: end` — the implementer is told to read none.

### 3. Delivered by code

- `reef-attempt <task>` prints the block (after `dead-ends:` and `lessons:`, before `REEF-TASK:`).
- `reef-graph-run.py` copies it verbatim into the implementer prompt, as it does `dead-ends:` and `lessons:`.
- `skills/reef-task/SKILL.md` step 2 names it with the other blocks.
- `agents/implementer.md:11`: "the ADRs your prompt's `adrs:` block lists (code chose them by your `files:`) — no other".

### 4. The guard enforces presence (recommended; OWNER DECISION A)

- `reef-guard.py`, on an implementer dispatch (next to PR-2's `check_dead_ends`): every line of the block `reef-adrs.py task`
  computes, from the plugin's own directory, must be in the prompt — by content, so a header alone or a dropped ADR is refused.
- Why yes: without it the block is advice the orchestrator can drop, and the implementer then reads either nothing (a settled
  decision violated) or everything (today's load). PR-2 and PR-3 made the same call for their blocks.
- Cost: one more refusal path on the dispatch; a hand-built dispatch must run `reef-attempt` (it already must for `dead-ends:`).
- Conservative default while the owner decides: enforced. Dropping it is deleting one call.

### 5. The planner and the verifier

- Planner (`agents/planner.md:11`): "the ADRs `python3 scripts/reef-adrs.py feature <slug>` lists". Prose, not the guard: the
  planner runs it itself (it has Bash); the guard has no task file to compute from at plan time. OWNER DECISION B: guard it
  too? Recommended no for now — the planner writes the paths, so it must see the decisions broadly; the scoping there is a
  saving, not a safety rail.
- Verifier (`skills/reef-verify/SKILL.md`, the ADR check): over every Accepted ADR touching the DIFF —
  `git diff --name-only <base> | xargs python3 scripts/reef-adrs.py paths` — not only `docs/adr/` (today's line misses every 0.6
  ADR). The falsification rule is unchanged.

## Measure

- The repo has no plan with ADRs of its own (no `reef/` tree, no `docs/adr/`; the eval corpus carries no ADR). So the measure is
  the test fixture `tests/test_adrs.py` builds — a project of 5 Accepted ADRs (3 scoped elsewhere, 1 matching, 1 undeclared) and a
  task: before 5 ADR files loaded, after 2. Reported in the PR body from the test's own output. No real-project number is claimed.

## Tests first (red before the code)

- `tests/test_adrs.py` (new): the matcher (dir prefix, glob, glob-vs-glob, no overlap), undeclared kept, Superseded/Proposed
  dropped, no `files:` = all, `feature` union and fresh-plan rule, `paths` on concrete names, the 5 → 2 measure.
- `tests/test_attempt.py`: the dispatch prints the `adrs:` block before `REEF-TASK:`; none without ADRs.
- `tests/test_guard.py`: an implementer dispatch lacking a line of the block is refused; with it, allowed; no ADRs, no block needed.
- `tests/test_graph_run.py`: the implement prompt carries the block.
- `tests/test_plan_check.py`: an ADR without `Paths:` is a WARN, not a FAIL.

## Not in this PR

- Other lines of `implementer.md` ("Then refactor") and `skills/reef-plan/SKILL.md`'s ADR-criteria sentence (another session's).
- Back-filling `Paths:` into existing projects' ADRs (the WARN asks; the owner adds them).
- The hunter's ADR reads (`loophole-hunter.md`): unchanged.

## Owner decisions (open)

- **A** — the guard refuses an implementer dispatch without the `adrs:` block. Built as YES (recommended).
- **B** — the guard also checks the planner's list. Built as NO (recommended).
