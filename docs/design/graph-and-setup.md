# Reef as a graph executor, and `/reef-init` as the project setup

Status: design for 0.5.0, on 0.4.0 (`parallel-loop-compat`). Where this and `PROJECT-SETUP.md` differ, the owner's decisions win; what remains is listed at the end.

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

Locking: the decision and the `in-progress` write happen under **one lock for the whole task set** (`tempdir/reef-graph-<sha1 of tasks dir>`, never unlinked); two hooks fired by one orchestrator message race on it and exactly one wins the last slot. `reef-graph lock <resource> [--timeout S] -- cmd` holds one of N numbered slot files with Python `fcntl` (no `flock(1)` — macOS lacks it); the timeout is always in force, a stuck holder is exit 75, never a hang.

## 3. Isolation

`reef-graph worktree <task>` creates `.reef/worktrees/<id>` on `task/<id>-<slug>` from the current branch, runs the project's `worktree.setup` (`npm ci`, `uv sync`; each worktree its own generated client, never the shared one) and records `worktree:`. The implementer is dispatched with that directory and never touches `tasks/`: **task state lives only in the orchestrator's checkout**. Verification runs in the worktree (snapshot before/after). On PASS the orchestrator — the feature branch's single writer — merges `task/<id>` with `--no-ff`, moves the task file to `done/` and writes the runlog row in that same merge commit, then removes the worktree. The row is never written on the task branch (method §5). Two guard rules come from the same wave: `git stash` is denied (one stack serves every worktree), and a gate piped into `tail`/`grep` without `pipefail` is denied (the pipe hides the exit code).

## 4. Guard enforcement

`reef-guard.py` keeps its order — header → file → per-feature stamp → role model → blocked → cap → odometer — and adds the graph question, inside the graph lock and before the bump, importing the scheduler **from the plugin's own directory** (`rm scripts/reef-graph.py` in a project opens nothing). Denials name the reason (`blocked-by not done: 3 (pending)`, `resource 'db' held by task(s) 4`). A retry after a FAIL finds the task already `in-progress`: it is discounted from its own counts, so it never self-blocks. Model per role: when `roles.<role>` is set the Agent call must carry that `model` (`author`, `verifier`, `plan_reviewer`, `adversary`, `mechanic`); fable plans, opus writes, attacks, verifies and reviews, sonnet does mechanical work; each project overrides. Escalation goes up, never down.

## 4b. The adversarial stage and the claims

A `tier: design` task runs the `loophole-hunter` (`roles.adversary`) twice — on the plan before code, on the finished guard before close; never on mech. `scripts/reef-adversarial` records only a PASS without BLOCKER lines: `adversarial-plan: <hash of the plan content>` (the guard refuses the first implementer dispatch without it, or after a plan edit) and `adversarial-guard: <report>@<HEAD>` (the pre-commit refuses a design-tier task file entering `done/` without it). A BLOCKER goes back under the cap; a NEW-ROW becomes a queue row. Every fix round ends with a claims list; `scripts/reef-claims.py check` rejects a claim at a line the round did not add. After GREEN only a `claims-only` commit, a BLOCKER or a new row — never a fourth round (44% of measured fix rounds came after GREEN).

## 5. The outer loop

The project loop is the same graph one level up: `docs/queue.md` holds one row per item — `id · one line · depends · source · batch` — with **no status column**; `reef-queue.py` derives a row's state from its task files (`feature: <id>`) so a fact has one home. A row is ready when every `depends` is merged and it is in the current batch (frozen: found work waits for the next batch unless it loses a person's data, exposes a secret, or breaks the core journey). The `reef-loop` skill drives: row → `/reef-plan` (one batched question set) → `/reef-plan-review` → `/reef-task` over the feature graph → `/reef-review` (`merge.by: loop` merges into `branches.base`; `ci.feature_gate: local` runs the local gate) → close in the same breath (row archived, draft ADR numbered, journal entry, branch and worktree deleted) → next row. The release PR into `branches.release` is the owner's merge; a fresh orchestrator starts there. The loop stops only for: an owner decision, a missing credential, a spec found wrong, the cap.

## 6. What `/reef-init` generates

`scripts/reef-init.py` renders `templates/project/` with the detected stack (plan-check reads `AGENTS.md` as the brief when `CLAUDE.md` is a one-line pointer):

| file | holds | its one home for numbers |
|---|---|---|
| `.reef/config.json` | every setting and number | **here** |
| `AGENTS.md` | commands, layout, the loop, parallel rule, writing rule, "Owner decision points" (never "Open questions"), the lessons that are prose | config, queue, constitution |
| `.specify/constitution.md` | 8 starter articles, each "what it prevents"; version + ADR-to-amend | — |
| `docs/queue.md` | rules of the loop, columns, footnotes in the owner's words | task files for status |
| `docs/adr/README.md` | drafts `draft-<item>-<slug>.md`, `Status: Accepted (number at merge)`, numbered at merge | — |
| `docs/journal.md` (`paths.runlog`), `HANDOFF.md` | headers; rewrite-whole rule | — |
| `.github/workflows/ci.yml`, `.github/dependabot.yml` | PRs into the release branch only, cancel-in-progress, timeouts, cache; CI runs `scripts/reef-ci-local.sh` so local and CI are one list; Dependabot on `branches.base`, weekly, grouped | config |
| `scripts/reef-ci-local.sh` | `gates.full` + `gates.extra`, every exit code read, exit 2 = skipped ≠ success | config |
| `scripts/reef-tier.py` | recomputes `tier:` from the diff (allowlist, product lines, migrations, draft ADRs); only heavier | config `tiers` |
| `docs/day-zero.md` | the checklist, each line a command or a gate | — |
| `scripts/reef-queue.py` | status derived from task files, ready rows (current batch, planned first), consistency check, ADR numbering at merge | the queue, the task files |

Idempotence: absent → written; identical → skipped; **different → never overwritten** — the rendering goes to `.reef/proposed/<path>` with a printed diff; `--accept <path>` applies one. A second run with nothing changed writes nothing.

## 7. Migration

Zero-touch for execution: no `resources:` → no resource rule; no `graph` → parallel 10; new denials: an undone `blocked-by` (a correctly ordered plan never trips it), `git stash`, a piped gate, a wrong model once `roles.*` is set, a design-tier dispatch without its adversarial pass. Re-run `/reef-init` for the project files; nothing existing is overwritten.

## 8. What this cannot cover

- Launching every ready task is prose; the guard catches a wrong dispatch, not a missing one.
- The hook cannot see an agent's cwd: the worktree rule is `reef-graph worktree` + the skill.
- An undeclared resource is not serialised; the collision table is as complete as the plan.
- Running the claims and adversarial scripts is the orchestrator's duty; what they check is code.

## Left for the owner

1. `PROJECT-SETUP.md` §1 names `specs/NNN/spec.md` and Reef `tasks/`; here the spec is the task file(s), and the journal is `paths.runlog`.
2. `## Decision`: the method says the agent writes it except for the Design tier; Reef's prose now says the same, but `tier: design` is where the human writes.
3. The method's §13 "until Reef's X lands" clauses (merge, CI, rollup, stamp, `gates.fast`, `roles.*`) have all landed in 0.4/0.5 and can be cut.

---

# 0.6 — governance, spec, tiers, day zero, loop engine, one tree

Status: shipped in 0.6.0 on 0.5.0. The decisions are the eleven in the 0.6 handoff; this section records what each
became in code and where its red test lives. The README's ledger is the authoritative class per mechanism.

## 9. Governance is four questions answered by mechanism
*Authority*: the human approves a plan through `AskUserQuestion`; the PostToolUse hook `scripts/reef-approval.py`
turns the answer into `.reef/approvals/<slug>.json` bound to the plan's digest (`reef-plan-check.py --digest`), and
only that record lets the first dispatch through (`--verify-stamp`, the guard). *Evidence*: a review verdict is a
record bound to the forge head (`scripts/reef-record`), and `gh pr merge` under `merge.by: loop` is refused without a
GREEN record on that head (a clean base merge or claims-only commits are the only carry-overs). *Enforcement*:
every script carries `# CLASS: code|tripwire`, the ledger names the class, `tests/test_contracts.py` ties them.
*Record*: approvals and review records are machine state in the main checkout's `.reef/`, written by hooks and
scripts only (the guard denies hand-writes). The release stays the human's merge.

## 10. Four tiers
`critical | design | full | light`, a role table and an effort each (`tiers.<tier>`), resolved by `reef-attempt`
and enforced by the guard from the `REEF-TASK:`/`REEF-FEATURE:` line every role dispatch carries. Path classes
and `touches:` only raise a tier (`reef-tier.py`, `reef-plan-check.py`). An all-light plan needs no plan-reviewer
(`--needs-agent` exit 3). `tiers.light.roles.author` ships unset until the eval shows sonnet safe and cheaper.

## 11. The feature folder
One row = one branch = one PR = one folder `reef/features/<slug>/` (SPEC.md with `Row:` and layered `FR-n`/`SC-n`
keys, `specs/` for big features, `adr/`, `tasks/`). Plan-check validates the slug, the keys, the ACs' citations, the
structure and `plan.max_tasks`; the stamp digest covers the folder; `reef-queue.py index` generates the one page;
ADR numbers are one global sequence. The 0.5 flat layout keeps working from `paths.*`; `reef-migrate --layout`
moves it in one reviewed commit. Criteria are one declarative sentence with their proof in a `## Proof` row (old
shape still valid); `reef-converge` executes the rows before acceptance.

## 12. Day zero
New project: the architecture grill renders `reef/architecture/architecture.md` (C4 L1/L2), draft ADRs, the
footnotes and the walking-skeleton row (`reef-init.py --grill`); stack opinions distil into AGENTS.md; `reef-repo`
protects the forge. Existing project: `/reef-explore` fans out read-only Explore agents (locked by the guard),
`/reef-assess` writes the four observed sections and the harnessability score, `reef-recalibrate plan` lists every
document's fate, ONE approval, `--apply` converts decisions to ADRs with `Supersedes:`, specs to feature folders,
archives the rest with an index and rewritten links, in one revertable commit; `reef-structure --check` keeps it so.

## 13. Architecture and security as artifacts
`reef-c4.py` generates one Structurizr model from code with a proof per element and checks element-level drift as a
release gate; `reef-threat.py` lints the STRIDE table against the model's boundary crossings; unmitigated rows
become found queue rows; the hunter's `pass=system` attacks the threat model against a running worktree. The
dependency audit and the history secret scan are release gates, proposed on upgrade.

## 14. The loop engine
`reef-loop.py tick` is the one read of the world (under 30 lines); `.reef/inflight/` and `.reef/verifying/` are
the guard's markers; the Stop hook refuses an idle turn end once per tick state; identical ticks park the loop;
token budgets and the context ceiling (`reef-cost.py --live`, tail only) stop it; `reef-handoff` renders the
handoff whole; gates print the failing block, never the log; SessionStart injects the handoff head and the tick
under `writing.session_start_tokens`.

## 15. What this still cannot cover
- The Stop hook sees `background_tasks` but not a sub-agent's uncommitted work; the tick reads markers, not minds.
- A reviewer lock is a token match for writes (tripwire); the snapshot hash remains the backstop.
- `AskUserQuestion`'s result shape is schema-verified from the installed binary, not captured live (headless
  sessions exclude the tool); `reef-approval.py` reads `tool_response.answers` and falls back to `tool_input.answers`.
- The size ceiling (decision 10) was not met: ~3,850 net new script lines against 3,200 — see the CHANGELOG's
  Finishing section for the arithmetic and the cuts the owner can still order.
