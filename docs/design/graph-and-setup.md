# Reef as a graph executor, and `/reef-init` as the project setup

Status: design for 0.5.0, on top of 0.4.0 (`parallel-loop-compat`). Where this and `PROJECT-SETUP.md` differ, the owner's decisions win; what remains is listed at the end.

## 1. Invariant

**No implementer runs on a task outside the ready set, and the ready set is computed by code from state on disk.** A task is ready iff: `status` is `pending` or `in-progress`; every id in `blocked-by` is `done`; `attempts < cap`; each resource it declares has a free slot once its own holding is discounted; and the number of *other* `in-progress` tasks is below `graph.parallel`. The PreToolUse guard denies any implementer dispatch of a non-ready task and, on allow, marks it `in-progress` under one graph-wide lock — the state advances as a side effect of the dispatch. The cap and odometer stay per task, the stamp still gates the plan, the verifier stays a fresh, hash-checked context.

## 2. Scheduler: `scripts/reef-graph.py`

Data — the task files' front matter only, so a restart recomputes everything:

| key | written by | meaning |
|---|---|---|
| `blocked-by: [ids]` | planning | edges; plan-check and the scheduler both refuse cycles, dangling and duplicate ids — a broken graph has no ready set |
| `resources: [names]` | planning | what the task holds while `in-progress`: `port:3000`, `db`, `browser`, `heavy`; slots from `resources.<name>.slots` (default 1, `heavy` 2) |
| `tier: light\|full\|design` | planning | effort matched to risk; plan-check refuses `light` on a `design` task and `full`/`design` on `mech` |
| `status` | guard → `in-progress`; reef-attempt → `blocked`; merge → `done` | the only execution state the scheduler reads |
| `worktree:` | `reef-graph worktree` | the task's worktree; stripped from the stamp like `status` |

`ready` loads every task under `tasks/` and `tasks/done/`, validates the DAG, applies §1, prints the ready tasks in id order (`--json`); `check <file>` is the guard's question (0 ready, 2 not, 1 broken graph); `status` shows every task's state and reason. `graph.parallel` defaults to 10 (20 heavy agents drove one machine to load ~90); a nonsense setting denies rather than defaulting.

Locking: the decision and the `in-progress` write happen under **one lock for the whole task set** (`tempdir/reef-graph-<sha1 of tasks dir>`, never unlinked); two hooks fired by one orchestrator message race on it and exactly one wins the last slot (tested with eight). `reef-graph lock <resource> [--timeout S] -- cmd` holds one of N numbered slot files with Python `fcntl` (no `flock(1)` — macOS lacks it); the timeout is always in force, a stuck holder is exit 75, never a hang.

## 3. Isolation

`reef-graph worktree <task>` creates `.reef/worktrees/<id>` on `task/<id>-<slug>` from the current branch, runs the project's `worktree.setup` (`npm ci`, `uv sync`; empty = nothing — each worktree its own generated client, never the shared one) and records `worktree:`. The implementer is dispatched with that directory and never touches `tasks/`: **task state lives only in the orchestrator's checkout**. Verification runs in the worktree (snapshot before/after). On PASS the orchestrator — the feature branch's single writer — merges `task/<id>` with `--no-ff`, moves the task file to `done/` and writes the runlog row in that same merge commit, then removes the worktree. The row is never written on the task branch (method §5). Two guard rules come from the same wave: `git stash` is denied (one stack serves every worktree), and a gate piped into `tail`/`grep` without `pipefail` is denied (the pipe hides the exit code).

## 4. Guard enforcement

`reef-guard.py` keeps its order — header → file → per-feature stamp → role model → blocked → cap → odometer — and adds the graph question, inside the graph lock and before the bump, importing the scheduler **from the plugin's own directory** (`rm scripts/reef-graph.py` in a project opens nothing). Denials name the reason: `blocked-by not done: 3 (pending)`, `resource 'db' held by task(s) 4`, `parallel cap 10 reached`. A retry after a FAIL finds the task already `in-progress`: it is discounted from its own counts, so it never self-blocks. Model per role: when `roles.<role>` is set the Agent call must carry that `model` (`author`, `verifier`, `plan_reviewer`, `adversary`, `mechanic`); fable plans, opus writes, attacks, verifies and reviews, sonnet does mechanical work — each project overrides. Escalation goes up (effort high after a FAIL), never down.

## 4b. The adversarial stage and the claims

A `tier: design` task runs the `loophole-hunter` (model `roles.adversary`) twice — on the plan before code, on the finished guard before close; never on mech. `scripts/reef-adversarial` records only a PASS without BLOCKER lines: `adversarial-plan: <hash of the plan content>` (the guard refuses the first implementer dispatch without it, or after a plan edit) and `adversarial-guard: <report>@<HEAD>` (the pre-commit refuses a design-tier task file entering `done/` without it). A BLOCKER goes back under the cap; a NEW-ROW becomes a queue row. Every fix round ends with a claims list; `scripts/reef-claims.py check` rejects a claim at a line the round did not add. After GREEN, `claims-only` is the one commit allowed (docs, comments, blank lines); else a BLOCKER or a new row — never a fourth round (44% of measured fix rounds came after GREEN).

## 5. The outer loop

The project loop is the same graph one level up: `docs/queue.md` holds one row per item — `id · one line · depends · source · batch` — with **no status column**; `reef-queue` (PR-B) derives a row's state from its task files (`feature: <id>`) so a fact has one home. A row is ready when every `depends` is merged and it is in the current batch (frozen: found work waits for the next batch unless it loses a person's data, exposes a secret, or breaks the core journey). The `reef-loop` skill drives: row → `/reef-plan` (one batched question set: approval, Design-tier Decisions, branch placement) → `/reef-plan-review` → `/reef-task` over the feature graph → `/reef-review` (`merge.by: loop` merges into `branches.base`; `ci.feature_gate: local` runs the local gate) → close in the same breath (row archived, draft ADR numbered, journal entry, branch and worktree deleted) → next row. The release PR into `branches.release` is the owner's merge; a fresh orchestrator starts there. The loop stops only for: an owner decision, a missing credential, a spec found wrong, the cap.

## 6. What `/reef-init` generates (PR-B)

`scripts/reef-init.py` renders `templates/project/` with the detected stack:

| file | holds | its one home for numbers |
|---|---|---|
| `.reef/config.json` | gates, caps, roles, graph, resources, worktree, tiers, writing caps, branches | **here** |
| `AGENTS.md` | commands, layout, the loop, parallel rule, writing rule, "Owner decision points" (never "Open questions"), the lessons that are prose | config, queue, constitution |
| `.specify/constitution.md` | 8 starter articles, each "what it prevents"; version + ADR-to-amend | — |
| `docs/queue.md` | rules of the loop, columns, footnotes in the owner's words | task files for status |
| `docs/adr/README.md`, `templates/adr.md` | `draft-<item>-<slug>.md`, `Status: Accepted (number at merge)`; numbered on the integration branch at merge | — |
| `docs/journal.md` (`paths.runlog`), `HANDOFF.md` | headers; rewrite-whole rule | — |
| `.github/workflows/ci.yml`, `.github/dependabot.yml` | PRs into the release branch only, cancel-in-progress, timeouts, cache; CI runs `scripts/reef-ci-local.sh` so local and CI are one list; Dependabot on `branches.base`, weekly, grouped | config |
| `scripts/reef-ci-local.sh` | `gates.full` + `gates.extra[]`, every exit code read, never piped; exit 2 = skipped ≠ success | config |
| `scripts/reef-tier.py` | recomputes `tier:` from the diff (allowlist globs, product-line count, migration, ADR); can only make it heavier | config `tiers` |
| `docs/day-zero.md` | the checklist, each line a command or a gate | — |

Idempotence: absent → written; identical → skipped; **different → never overwritten**: the rendering goes to `.reef/proposed/<path>` with a printed diff, and `--accept <path>` applies one after the human says so. A second run with nothing changed writes nothing.

## 7. Migration

Zero-touch for execution: no `resources:` → no resource rule; no `graph` → parallel 10; new denials: an undone `blocked-by` (a correctly ordered plan never trips it), `git stash`, a piped gate, a wrong model once `roles.*` is set, a design-tier dispatch without its adversarial pass. Re-run `/reef-init` for the project files; nothing existing is overwritten.

## 8. What this cannot cover

- Launching every ready task is prose; the guard catches a wrong dispatch, not a missing one.
- The hook cannot see an agent's cwd: the worktree rule is `reef-graph worktree` + the skill.
- An undeclared resource is not serialised; the collision table is as complete as the plan.
- A human's shell is not guarded; CI is the wall.
- Running the claims and adversarial scripts is the orchestrator's duty; what they check is code.

## Left for the owner

1. `PROJECT-SETUP.md` §1 names `specs/NNN/spec.md` and Reef `tasks/`; here the spec is the task file(s), and the journal is `paths.runlog`.
2. `## Decision`: the method says the agent writes it except for the Design tier; Reef's prose now says the same, but `tier: design` is where the human writes.
3. Plan-check prefers `CLAUDE.md` over `AGENTS.md` as the brief when both exist; init writes a one-line `CLAUDE.md` pointer. Proposal: prefer `AGENTS.md`.
