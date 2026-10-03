<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.svg">
  <img src="assets/banner-light.svg" alt="Reef — agentic coding pipeline" width="100%">
</picture>

<p align="center">
  <img alt="version" src="https://img.shields.io/badge/version-0.5.0-D94F35?style=flat-square">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-0E7C7B?style=flat-square">
  <img alt="claude code" src="https://img.shields.io/badge/claude_code-plugin-182B33?style=flat-square">
  <img alt="status" src="https://img.shields.io/badge/status-pilot_(n%3D1)-B07C1F?style=flat-square">
  <img alt="selftests" src="https://github.com/MahmoudMoe/reef/actions/workflows/ci.yml/badge.svg?branch=main">
</p>

# Reef

> *A coral reef grows one calcified layer at a time — each organism leaves a hard structure the next builds on. Reef works the same way: every task, ADR and journal line is a fossilized layer that outlives the session that wrote it.*

A Claude Code plugin that runs a software project as a **graph of gated work**: a queue of items, each planned into vertical-slice tasks with real dependency edges, executed in parallel by isolated implementers, verified by a fresh context, reviewed under one cap, merged by the loop into an integration branch, released by the human. The discipline is in **mechanisms** (scripts, a PreToolUse guard, git hooks), not in prose — and every mechanism ships with a test that shows it going red on the defect it exists to catch. Token-frugal: the model is matched to the job, the orchestrator's context stays short, nothing is written twice.

Arabic manual: [`docs/manual/ar/index.html`](docs/manual/ar/index.html). Design of the graph executor and the setup: [`docs/design/graph-and-setup.md`](docs/design/graph-and-setup.md).

## Install
```
/plugin marketplace add MahmoudMoe/reef
/plugin install reef@mahmoudmoe
```
Then, in a project, `/reef-init`:
- **New project** — it writes the whole setup from templates adapted to the stack it detects (package.json, pyproject/uv.lock, Cargo.toml, go.mod): `.reef/config.json` (every setting and number lives here, once), `AGENTS.md` (+ a one-line `CLAUDE.md` pointer), `.specify/constitution.md`, `docs/queue.md`, `docs/adr/README.md`, `docs/journal.md`, `HANDOFF.md`, `docs/day-zero.md`, a release-only `.github/workflows/ci.yml`, `.github/dependabot.yml` on the integration branch, the commit hooks, every `scripts/reef-*`, `tasks/`, `.gitignore` lines, a Makefile `setup:` target; then installs the hooks and commits.
- **Existing project** — the same command; **nothing you wrote is overwritten.** A file that exists and differs from the rendering is left alone: the rendering lands in `.reef/proposed/<path>` with a printed diff, and `python3 scripts/reef-init.py --accept <path>` applies the ones you choose. Config keys you have are kept; missing ones are added. Re-run after a plugin upgrade; a second run with nothing changed writes nothing (`test_init.py`).
- After any fresh clone: `make setup` (hooks are local git config). Not per worktree — `reef-graph worktree` runs `worktree.setup`.

**Upgrading to 0.5:** the role check fires on ANY subagent whose name contains `implementer`, `verifier`, `plan-reviewer`, `loophole-hunter` or `mechanic` — a project that ships its own agent under one of those names must pass `model=<roles.*>` on every dispatch, or leave that role unset in `roles.*`. Name no project agent `*implementer*`: the guard also demands its `REEF-TASK:` line. **From 0.3.x:** re-run `/reef-init` (scripts and hooks are proposed, accept them), add `tasks/.plan-review.json` to `.gitignore` (`git rm --cached` it if committed), run `/reef-plan-review` once — 0.3 stamps read as missing. Old configs keep working: `gates.test` is an alias of `gates.full`; every new key defaults to the old behaviour.

## The flow, as a graph
```
docs/queue.md ──row──▶ /reef-plan ──▶ /reef-plan-review ──▶ /reef-task ──▶ /reef-review ──▶ merge into branches.base ──▶ close
   (outer graph:           grill, slices,     deterministic         the TASK GRAPH:         PR, acceptance,        (merge.by: loop)          row archived,
    rows, Depends,         blocked-by,        checks + semantic     every ready task        diff review,                                     draft ADR numbered,
    current batch,         resources:, tier:  review, stamp         at once, each in        local gate or CI,                                journal row,
    planned before found)  one batched gate                         its own worktree        one rollup, one cap                              worktree deleted
                                                                                                                                                   │
                                                                     release PR branches.base → branches.release: CI once, the HUMAN merges ◀──────┘
```
`/reef-loop` drives the outer graph; `/reef-task` the inner one. Both are computed from disk by code (`scripts/reef-queue.py`, `scripts/reef-graph.py`), so a restart resumes where it was.

**Inside `/reef-task`:** `scripts/reef-graph.py ready` lists every task whose `blocked-by` are done, whose declared `resources:` (`port:3000`, `db`, `browser`, `heavy`) have a free slot, within `graph.parallel`. Each is dispatched at once: `reef-graph worktree` gives it `.reef/worktrees/<id>` on `task/<id>-<slug>` with its own `worktree.setup` (never the shared generated client); `reef-attempt` prints the model and effort; the implementer works there and never touches `tasks/`. Verify in the worktree (gate + golden test for `mech`; a fresh `verifier` whose tree is hash-checked for `design`), then the orchestrator — the feature branch's single writer — merges `task/<id>` with `--no-ff`, moves the task file to `done/` and writes the journal row in that same commit. A FAIL is recorded as data (`reef-attempt`), the retry keeps its worktree and slot, the cap holds. A blocked task parks; the graph continues around it.

## Enforcement map — code vs prose (honesty ledger)
| Rule | Enforced by | Layer |
|---|---|---|
| Retry cap / same-failure-twice | `reef-attempt` (data) + `reef-guard.py` deny at dispatch + `dispatches:` odometer | **code** |
| No implementer outside the READY SET (every `blocked-by` done, a free slot on every declared `resources:`, under `graph.parallel`; a broken graph has no ready set) | `scripts/reef-graph.py` computes it from the task files; the guard imports the plugin's own copy, takes one graph-wide lock, denies, and on allow marks the task `in-progress` | **code** — launching every ready task is reef-task prose; the guard catches a wrong dispatch, not a missing one |
| Each implementer in its own worktree, its own `worktree.setup` | `reef-graph worktree`; the hook cannot see an agent's cwd | **prose** trigger, code mechanism |
| Heavy commands share 2 slots | `reef-graph lock heavy -- cmd` (fcntl, numbered slot files, mandatory timeout → exit 75) | **code** when called |
| Plan edited after approval → re-review | `reef-plan-check.py --verify-stamp`, re-checked by the guard at every implementer dispatch, per feature, against the task file's own worktree; the stamp is never committed | **code** |
| Every role runs on its configured model | the guard denies a dispatch whose `model` ≠ `roles.<role>` (author, verifier, plan_reviewer, adversary, mechanic) when set | **code** |
| Adversarial pass on the PLAN before code (`tier: design`) | `scripts/reef-adversarial … plan` records the loophole-hunter's PASS bound to the plan's content; the guard denies a design-tier dispatch without it or after a plan edit; FAIL/BLOCKER never recorded; mech/light refused | **code** |
| Adversarial pass on the finished GUARD before close (`tier: design`) | `… guard` writes `adversarial-guard:`; the pre-commit refuses a design-tier task file staged into `done/` without it | **code** (presence) |
| `tier:` matches `complexity` (mech ⇔ light); the computed tier only gets heavier | `reef-plan-check.py`; `scripts/reef-tier.py` from the diff (allowlist, line ceiling, migrations, draft ADRs) | **code** when run |
| One cap per item after GREEN (acceptance + diff + CI share it) | one rollup file per feature, refused twice by `reef-attempt` and the guard | **code** |
| Nothing after GREEN but a claims-only commit, a BLOCKER, or a new row | `scripts/reef-claims.py claims-only <green>..HEAD` | **code** when run (reef-review prose) |
| A fix round ends with a claims list bound to its own diff | `scripts/reef-claims.py check` rejects a claim at a line the round did not add, and an empty list | **code** when run (reef-task prose) |
| Draft ADRs in parallel branches, numbered at merge | `reef-plan-check.py` exempts `draft-*.md` from the Proposed check; `reef-queue.py adr-number` | **code** |
| Queue status has one home (the task files) | `reef-queue.py status/ready/check` derive it; `check` fails an orphan task, a duplicate row, an unknown dependency, a journal/queue over its word ceiling | **code** |
| Commit gate tests the index | `.githooks/pre-commit` (+ `pre-merge-commit`): back up the index, run `reef-gate.sh fast`, restore exactly — no stash, no `--3way` | **code** |
| Local CI = CI, every exit code read | `scripts/reef-ci-local.sh`: `gates.full` + `gates.extra`, each exit code read directly, 77 = skipped → exit 2 (not success), `--require` makes a skip a failure, `--ci` never accepts one; the generated workflow runs this same script on PRs into `branches.release` only | **code** |
| `git stash` (one stack serves every worktree); a gate piped into `tail`/`grep` (hides the exit code) | `reef-guard.py` denies both (`list`/`show` and `pipefail` allowed) | **tripwire** |
| Bypass spellings (`--no-verify`, `-n`, `-c core.hookspath`, env smuggling, `rm .githooks`) | `reef-guard.py` (tokenizing PreToolUse hook) | **tripwire** — a blocklist over a shell surface is never complete; CI is the wall |
| Push gate | none by design — a worktree gate at push time only false-rejects | **CI is the wall** |
| Verifier didn't touch the tree | `reef-snapshot.sh` before/after (nested worktrees excluded) | code hash, **prose trigger** |
| Verifier writes its pass/fail rule per AC before reading the diff; attacks the last round's fix first; "cannot verify here" needs the probe pasted | reef-verify / verifier / loophole-hunter text; reef-task requires the `RULE AC<n>` lines | **prose** |
| Golden-output test on mech tasks | verifier contract | **prose** |
| `/reef-init` never overwrites, idempotent, one home per fact, release-only CI | `scripts/reef-init.py` (`test_init.py`: a user's file untouched, diff proposed, `--accept`, keys merged, second run writes nothing, generated prose points at `caps.attempts` instead of restating it, no `push:` trigger) | **code** |
| Merge only after the agent's final hand-back; never regenerate a shared generated file; the batch is frozen; a guard refuses by shape | the generated `AGENTS.md` (one line each) | **prose** |

## Who runs what (routing)
The model per job — the owner's routing, 2026-10-04 — lives in `.reef/config.json` `roles.*`, every role overridable per project, read at dispatch: `reef-attempt` / `reef-plan-check.py` print it, the orchestrator passes it as the Agent call's `model`, the guard refuses any other. This table replaces the old comment that called fable "the cheap model".

| Job | Model (`roles.*`) | Runs as |
|---|---|---|
| Grill, slice, plan; plan review; the design of a `tier: design` task | **fable** (`planner`, `plan_reviewer`) | main session; `plan-reviewer` agent after `reef-plan-check.py` passes |
| Write code: implementer, fix rounds | **opus** (`author`) — attempt 1 at the task's `effort:`, after any FAIL effort high (up, never down) | `implementer`, one per ready task, in its worktree; tiny `mech` diffs inline |
| Verify `design` (rules per AC before the diff) | **opus** (`verifier`) | `verifier`, fresh context, tree hash-checked |
| Verify `mech` | no model — full gate + golden test | — |
| Adversarial attack (plan, finished guard), code review, security review | **opus** (`adversary`, `reviewer`, `security`) | `loophole-hunter`; the review-toolkit's `code-excellence` / `code-security` when installed |
| Rebase, run gates, re-take records, evidence re-runs, archive/close edits | **sonnet** (`mechanic`) — writes no prose claims; checked by exit codes, `git range-diff`, digests | `mechanic` |
| Commit gate / feature-PR gate / release CI | free | `reef-gate.sh fast` · `reef-ci-local.sh` · the generated workflow |
| Merge | — | the loop into `branches.base` (`merge.by: loop`); the human into `branches.release`, always |

Agent files carry a DEFAULT model equal to the role's default; the dispatch-time model always overrides it. Effort travels in the dispatch prompt ("reasoning effort: high") — agent frontmatter has no working effort key.

## The adversarial stage
A `tier: design` task (a mechanism that failed twice, or anything touching privacy, money or a guard) runs the `loophole-hunter` twice — on the plan before code, on the finished guard before close — with one question: *how can every check be green while the defect happens?* It is read-only, cites file:line, ranks holes by whether they will happen here, and attacks the last round's fix first. BLOCKER (will happen, or a prose claim the code contradicts) fails the pass under the cap; NEW-ROW becomes a queue row. `scripts/reef-adversarial` records only a PASS without BLOCKER lines; the guard and the pre-commit read the records. Never on `mech`: that is the cost lesson. Full-tier tasks may run it; design-tier must.

## Settings (`.reef/config.json` — the one home for every number)
| Key | Default | Effect |
|---|---|---|
| `gates.fast` / `gates.full` / `gates.extra` | `""` / stack test / `{}` | commit gate (falls back to full) / verify, review, CI / the other gates `reef-ci-local.sh` runs (build, docs, secret scan…) |
| `caps.attempts` | `3` | fix rounds per task, and per item on its rollup |
| `graph.parallel` | `10` | tasks in flight at once (20 heavy agents drove one machine's load to ~90) |
| `resources.<name>.slots` | `1` (`heavy`: `2`) | holders of a declared resource at once; `reef-graph lock <name> -- cmd` for commands |
| `worktree.dir` / `worktree.setup` | `.reef/worktrees` / stack install | where task worktrees live; the command run in a new one (its own copy, never the shared one) |
| `roles.*` | author opus · verifier opus · plan_reviewer fable · planner fable · adversary opus · reviewer opus · security opus · mechanic sonnet | the model per job, enforced at dispatch |
| `merge.by` | `human` (`loop` when init is given two branches) | `loop`: reef-review merges feature PRs into `branches.base`; releases stay the human's |
| `ci.feature_gate` | `ci` (`local` with two branches) | `local`: feature PRs run `reef-ci-local.sh`; CI is watched only on PRs into `branches.release` |
| `branches.base` / `branches.release` | `main` / `main` (init: `develop` / `main`) | integration branch / release branch |
| `tiers.light.allow` / `max_lines` / `migrations` | `docs/**, README.md` / `80` / migration dirs | what may be light; `reef-tier.py` can only make a tier heavier |
| `writing.*` | task words light 600 / full 2500 / design 2500, hand-back 150, prompt 120, journal 40 000, queue 35 000 | `task_words.<tier>` is enforced by `reef-plan-check.py` (falls back to `plan.max_words`); `journal_words`/`queue_words` by `reef-queue.py check`; hand-back and prompt caps are prose |
| `paths.*` | tasks, adr, glossary, runlog = journal, queue | where things live |
| `plan.test_re` / `plan.max_words` | `""` / `0` | test-name convention override / task file word cap |

Pre-0.4 configs keep working: `gates.test` is an alias of `gates.full`; every new key defaults to the old behaviour.

## Layout
skills/ (init, loop, plan, plan-review, task, verify, review) · commands/ (`/reef` status + `/reef-init`, `/reef-loop`, `/reef-plan`, `/reef-task`, `/reef-review`) · agents/ (implementer, verifier, plan-reviewer, loophole-hunter, mechanic) · scripts/ (reef-init.py, reef-gate.sh [fast|full], reef-attempt, reef-guard.py, reef-graph.py [ready|status|check|worktree|lock], reef-adversarial [plan|guard], reef-claims.py [check|claims-only], reef-tier.py, reef-queue.py [status|ready|check|adr-number], reef-ci-local.sh, reef-snapshot.sh, reef-plan-check.py) · hooks/hooks.json (PreToolUse guard) · schemas/task.schema.json · templates/ (config, task, adr, glossary, runlog, pre-commit, project/) · docs/design/ · docs/manual/ar/ · tests/ (sabotage suites) · .github/workflows/ci.yml (the suites on ubuntu + macos)

## Selftests
`sh tests/run.sh` — 274 sabotage and contract tests (202 Python + 72 shell). Every mechanism in this plugin has a test here that shows it going RED on the defect it exists to catch (each suite is listed in `tests/run.sh`); CI runs them on ubuntu (dash — the honest POSIX check) and macos.

## Acknowledgments
Reef is an original implementation, but its process ideas stand on two open projects:
- [iusztinpaul/squid](https://github.com/iusztinpaul/squid) (Apache-2.0) — the agent-team lifecycle, author/verifier separation, retry-cap concept, artifacts-as-memory.
- [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) — grilling, vertical-slice/tracer-bullet rules (a few planning heuristics in reef-plan closely paraphrase that repo's wording), spec/ticket discipline.
No code was copied from either project. Thanks to Paul Iusztin and Matt Pocock for publishing their work openly. The reviewers Reef calls by name (`plan-review`, `code-excellence`, `code-security`) are [mahmoudmoe84/review-toolkit](https://github.com/mahmoudmoe84/review-toolkit).
