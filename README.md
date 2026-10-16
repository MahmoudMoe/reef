<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.svg">
  <img src="assets/banner-light.svg" alt="Reef — agentic coding pipeline" width="100%">
</picture>

<p align="center">
  <img alt="version" src="https://img.shields.io/badge/version-0.6.0-D94F35?style=flat-square">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-0E7C7B?style=flat-square">
  <img alt="claude code" src="https://img.shields.io/badge/claude_code-plugin-182B33?style=flat-square">
  <img alt="status" src="https://img.shields.io/badge/status-pilot_(n%3D1)-B07C1F?style=flat-square">
  <img alt="selftests" src="https://github.com/MahmoudMoe/reef/actions/workflows/ci.yml/badge.svg?branch=main">
</p>

# Reef

> *A coral reef grows one calcified layer at a time — each organism leaves a hard structure the next builds on. Reef works the same way: every spec, task, ADR and journal line is a fossilized layer that outlives the session that wrote it.*

A Claude Code plugin that runs a software project as a **graph of gated work**: a queue of rows, each planned into a feature folder (a keyed `SPEC.md`, its decisions, its vertical-slice tasks with real dependency edges), executed in parallel by isolated implementers in worktrees, verified by a fresh context, reviewed under one cap, merged by the loop into an integration branch, released by the human. The discipline is in **mechanisms** (scripts, a tokenizing PreToolUse guard, git hooks, a Stop hook), not in prose — and every mechanism ships with a test that shows it going red on the defect it exists to catch. Governance is four questions answered by mechanism: *authority* (who may decide), *evidence* (what proves it), *enforcement* (code on structured state, a tripwire on command text, or prose), *record* (where it is written down). Token-frugal: the model is matched to the job by tier, the orchestrator reads one tick instead of the world, and nothing is written twice.

Arabic manual: [`docs/manual/ar/index.html`](docs/manual/ar/index.html). Design: [`docs/design/graph-and-setup.md`](docs/design/graph-and-setup.md). Measurements: [`docs/perf/`](docs/perf/).

## Install
```
/plugin marketplace add MahmoudMoe/reef
/plugin install reef@mahmoudmoe
```
Then, in a project, `/reef-init`:
- **New project** — one batched question set: the branches and the **architecture grill** (host, shape, scale, store, auth boundary, one-year non-goals). The script renders the one tree (below) from templates adapted to the detected stack: `.reef/config.json` (every number, once) and `.reef/version`, `AGENTS.md` (+ a one-line `CLAUDE.md` pointer; the stack's conventions distilled in), `reef/constitution.md`, `reef/queue.md` with batch 1 row 1 = **the walking skeleton**, `reef/architecture/architecture.md` (intent, C4 L1/L2) and the draft ADRs for host/store/auth, `reef/features/`, journal, glossary, day-zero, a release-only CI with the release gates, Dependabot, the hooks, every `scripts/reef-*`; then `scripts/reef-repo` protects the release branch on the forge.
- **Existing project** — the same command, then `/reef-assess`. **Nothing you wrote is overwritten**: a differing rendering lands in `.reef/proposed/<path>` with a diff and `python3 scripts/reef-init.py --accept <path>` applies the ones you choose; an existing constitution (`.specify/…`) or spec-kit `specs/*/spec.md` is pointed at, never duplicated; the 0.5 layout is kept until you run `python3 scripts/reef-migrate --layout`; the security gates arrive as a proposal, never as a red CI. `/reef-assess` reads how the project works, was written and was pushed (every claim Observed with a proving path, or Inferred), scores how well a harness can hold it, and recalibrates its documents into the tree under ONE batched approval — archive, never delete, undo with one `git revert`.
- After any fresh clone: `make setup` (hooks are local git config).

**Upgrading to 0.6:** re-run `/reef-init`. `scripts/reef-migrate` runs first and adds only keys (the tier table, `paths.*` at their 0.5 locations, `writing.*`, `caps.*`, `loop.*`, `context.*`), keeps `gates.test` as the alias it is, writes `.reef/version`. Every check new in 0.6 **warns** on content planned under 0.5 and fails only on content planned under 0.6 (a feature folder, or a feature first stamped after the marker). Accept the proposed scripts (they are Reef's). The flat `tasks/`/`docs/` layout keeps working; `--layout` moves it in one reviewed commit when you want the tree. `tiers.light.roles.author` ships **unset** (opus): the eval and the baseline did not yet show a sonnet author safe and cheaper, so the key waits for that measurement.

## The flow, as a graph
```
reef/queue.md ──row──▶ /reef-plan ─────────▶ /reef-plan-review ───▶ /reef-task ─────────▶ /reef-review ──────────▶ gh pr merge ─────▶ close
 (outer graph: rows,    reef/features/<slug>/     deterministic checks    the TASK GRAPH: every     scripts/reef-converge      (merge.by: loop; the      row archived, draft
  Depends, batch,       SPEC.md (FR/SC keys),     + the semantic review   ready task at once, each  (Proof rows executed),     guard checks a GREEN      ADR numbered in ONE
  planned before found) adr/, tasks/; ONE human   (none for an all-light  in its worktree, on its   acceptance against         record bound to the       global sequence,
                        gate — the approval is a  plan); stamp over the   tier's models (guard-     SPEC.md, diff review,      forge head)               journal row with
                        RECORD bound to the       whole folder            enforced); judges are     one rollup, one cap;                                 per-AC status
                        plan's digest                                     read-only by the guard    scripts/reef-record                                      │
                                                                                                                                                             │
  python3 scripts/reef-loop.py tick = the one read of the world; the Stop hook refuses a turn that leaves ready work idle; ◀───────────────────────────────┘
  release PR branches.base → branches.release: gates.release (C4 drift, threat lint, secret scan, audit) run there once, the HUMAN merges; handoff rendered whole, /clear
```
`/reef-loop` drives the outer graph; `/reef-task` the inner one. Both are computed from disk by code (`reef-loop.py tick`, `reef-queue.py`, `reef-graph.py`), so a restart resumes where it was — from the handoff head and the tick, nothing else.

## Enforcement map — code vs prose (honesty ledger)
Classes: **code** decides on structured state the agent cannot author · **tripwire** matches command text (a blocklist over a shell surface is never complete; CI is the wall) · **prose** lives in a skill or agent file. Every `scripts/reef-*` carries `# CLASS:` in its header and `tests/test_contracts.py` ties each row below to a script of that class.

| Rule | Enforced by | Layer |
|---|---|---|
| Retry cap / same-failure-twice | `reef-attempt` (data) + `reef-guard.py` deny at dispatch + `dispatches:` odometer | **code** |
| No implementer outside the READY SET — one graph across every feature folder (`blocked-by`, `resources:` slots, `graph.parallel`) | `scripts/reef-graph.py` computes it; the guard imports the plugin's own copy, takes one lock keyed on `paths.features`, denies, and on allow marks `in-progress` and writes `.reef/inflight/<id>` | **code** — launching every ready task is reef-task prose; the Stop hook catches the missing dispatch at turn end |
| The missing dispatch (loop active, ready work, nothing in flight, no wait, no stop reason) refuses the turn's end — once per tick state | `hooks.json` Stop → `reef-guard.py` → `scripts/reef-loop.py tick --assert-no-idle`; `stop_hook_active` honoured | **code** (at turn end) |
| Every role runs on its TIER's model (`tiers.<tier>.roles.<role>`, then `roles.*`); an all-light plan needs no plan-reviewer | `reef-attempt` prints `author:`/`verifier:`/`adversary:`; `reef-plan-check.py --needs-agent`; the guard resolves the tier from the `REEF-TASK:`/`REEF-FEATURE:` line on every dispatch and denies a mismatch | **code** |
| Plan approval is the HUMAN's, bound to the plan's digest; an edit afterwards approves nothing | `/reef-plan` asks `Approve plan <slug> at <digest16>?`; the PostToolUse hook `scripts/reef-approval.py` writes `.reef/approvals/<slug>.json` only on `Approve` with the current digest; `reef-plan-check.py --verify-stamp` and the guard require it (0.6-planned features; older ones warn) | **code** (the result shape is schema-verified: headless sessions exclude AskUserQuestion, see `docs/perf/payloads-2026-10-16.md`) |
| Nobody writes an approval or a review record by hand | `reef-guard.py` denies Bash writes and Edit/Write/MultiEdit under `.reef/approvals/`, `.reef/review/` | **tripwire** |
| Review verdicts are RECORDS bound to the forge head; `gh pr merge` only against a GREEN record (clean base merge or claims-only commits are the only carry-overs; rebase, code push, slow or failed gh deny) — `merge.by: loop` only | `scripts/reef-record` (`gh pr view`, `gh api …/git/commits`); `reef-guard.py` on `gh pr merge` / `gh api …/merge` under its own gh deadline | **code** (presence) |
| Judges are read-only: verifier, loophole-hunter, plan-reviewer, Explore get no mutating git, no Bash write, no CI wait; a typeless sub-agent is locked while `.reef/verifying/<id>` exists; no sub-agent waits on CI or sleeps a minute | `reef-guard.py` reads `agent_type`/`agent_id` from the payload (verified live, 0.0); the snapshot hash is the backstop | **code** + **tripwire** (the write detection is a token match) |
| A hung guard denies; no python3 denies a dispatch | `signal.alarm` deadline inside the guard; `timeout` + `onFailure: block` on every PreToolUse matcher (`scripts/reef-guard-profile.py` sets them at ≥ 5 × p95) | **code** |
| The guard's own files and the `roles|caps|gates|tiers` keys change only under a `critical` task in flight or inside Reef's own repository | `reef-guard.py` Edit/Write/MultiEdit matcher (JSON diff of the protected keys) and Bash write detection; `reef-init --accept` stays allowed | **code** for the keys, **tripwire** for the Bash shapes |
| Plan edited after approval → re-review; the stamp covers the WHOLE feature folder (spec, child specs, ADRs, tasks) | `reef-plan-check.py --verify-stamp`, per feature, re-checked by the guard at every dispatch against the task file's own worktree | **code** |
| A feature folder is well-formed: a descriptive slug, `SPEC.md` with `Row:` and layered `FR-n` keys, child specs with `Parent:`, ACs citing keys of their own folder, ≤ `plan.max_tasks` tasks, nothing else inside | `reef-plan-check.py`; `reef-queue.py check` (structure, slug); `reef-structure --check` | **code** |
| Criterion and proof split (new shape): one declarative sentence ≤ `writing.criterion_words`, its proof in the `## Proof` row; old shape stays valid; sentences ≤ `writing.sentence_words` | `reef-plan-check.py` (fails under 0.6, warns older); the claimed-twice check reads Proof rows | **code** |
| Every Proof row holds on the branch before acceptance (`missing` / `contradicts` under the one cap) | `scripts/reef-converge <feature>` | **code** when run (reef-review prose) |
| A tier only gets heavier: path classes (`tiers.design.paths`, `tiers.critical.paths`) and `touches:` (pii/money/auth → critical, migration → design + `Rollback:`) | `scripts/reef-tier.py` from the diff; `reef-plan-check.py` on the declaration; `reef-init` lists older tasks the rails would move | **code** when run |
| Adversarial pass on the PLAN before code and on the finished GUARD before close (`design` and `critical`) | `scripts/reef-adversarial` records a PASS bound to the plan's content; the guard refuses a dispatch without it; the pre-commit refuses a design/critical task entering `done/` without `adversarial-guard:` | **code** |
| A critical `touches: auth|pii|money` task needs a threat model at least as new as the architecture | `reef-plan-check.py`; `scripts/reef-threat.py lint|fresh` (every boundary crossing has a mitigated or accepted STRIDE row) | **code** |
| The architecture model is generated from code with a proof per element; drift is element-level, once per release | `scripts/reef-c4.py generate|lint|--diff` as `gates.release.c4`; `reef-ci-local.sh --release` | **code** |
| Hand-backs ≤ `writing.handback_words` with a claims list; judge reports carry `RUN:`, one `RULE AC<n>` per criterion citing its Proof row, evidence per AC; a fix round's claims point inside its own diff; after GREEN only claims-only commits | `scripts/reef-claims.py check --handback` / `report` / `check <range>` / `claims-only` | **code** when run (reef-task prose) |
| One cap per item after GREEN (acceptance + diff + CI share it); one rollup per feature | `reef-attempt` and the guard refuse a second rollup | **code** |
| Draft ADRs in parallel branches, numbered at merge in ONE global sequence across `reef/architecture/adr/` and every feature `adr/` | `reef-queue.py adr-number`; `reef-plan-check.py` exempts `draft-*.md` | **code** |
| Queue status has one home (the task files, a folder's `SPEC.md Row:` links slug to row); `reef/features/README.md` is generated | `reef-queue.py status|ready|check|index` | **code** |
| Context ceiling: a dispatch over `caps.context_tokens` is denied ("checkpoint, then /clear"); from `caps.context_warn` the hook warns the model | `reef-guard.py` on Task/Agent via `scripts/reef-cost.py --live` on the payload's `transcript_path` (tail only) | **code** (defaults 0 = off until set from the baseline) |
| No-progress parking (`loop.no_progress_ticks` identical ticks, nothing in flight) and token budgets (`caps.feature_tokens`, `caps.batch_tokens`) | `scripts/reef-loop.py tick` | **code** |
| Reports, never raw material: the exit code plus the failing block (`context.failure_lines`), the whole log on disk | `reef-gate.sh --failures`, `reef-ci-local.sh` (truncation inside the gate keeps the exit code) | **code** |
| Session start under `writing.session_start_tokens`: the handoff head + the tick + the next command, nothing else read | `hooks.json` SessionStart → `reef-loop.py tick --session-start --hook`; `AGENTS.md` ≤ 80 lines and the skills' re-entry sections (contracts) | **code** for the cap, **prose** for what the model then reads |
| Commit gate tests the index | `.githooks/pre-commit` (+ `pre-merge-commit`) | **code** |
| Local CI = CI, every exit code read; a skip is exit 2, not success; `gates.release` run on release-branch PRs only | `scripts/reef-ci-local.sh [--ci] [--release]` | **code** |
| Repository protection (release branch protected, push protection, CODEOWNERS), idempotent | `scripts/reef-repo` | **code** when run |
| Documents live in the layout; recalibration archives, never deletes, in one revertable commit with links rewritten | `scripts/reef-recalibrate plan|--apply|history`; `scripts/reef-structure --check` (both layouts) | **code** |
| Migrations are versioned and idempotent; a gap refuses | `scripts/reef-migrate` + `migrations/<from>-to-<to>.py` | **code** |
| `git stash`; a gate piped into `tail`/`grep`; bypass spellings (`--no-verify`, `-n`, hooksPath, env smuggling, `rm .githooks`) | `reef-guard.py` (tokenizing) | **tripwire** — CI is the wall |
| Push gate | none by design — a worktree gate at push time only false-rejects | **CI is the wall** |
| Verifier didn't touch the tree | `reef-snapshot.sh` before/after (nested worktrees excluded) | code hash, **prose trigger** |
| Verifier writes its pass/fail rule per AC before reading the diff; attacks the last round's fix first; the four kinds that fail (regression, bypass, correctness, failed AC — all else NIT); browser evidence or `Not verified in a browser:`; "cannot verify here" needs the probe | reef-verify / verifier / loophole-hunter text, under the eval (`scripts/reef-eval`) | **prose** (measured: `docs/perf/eval-baseline-2026-10-16.md`) |
| Explore agents label every claim Observed (with a proving path) or Inferred | reef-explore / reef-assess text; the lock above is the mechanism | **prose** |
| `/reef-init` never overwrites, idempotent, one home per fact, release-only CI | `scripts/reef-init.py` (`test_init.py`) | **code** |

## Who runs what (tiers and routing)
Four tiers, each a model per role and an effort, resolved at dispatch by `scripts/reef-attempt` and refused by the guard on mismatch — `tiers.<tier>` in `.reef/config.json`, every key overridable; an unset table is exactly the 0.5 `roles.*` behaviour.

| Tier | Meaning | planner / plan_reviewer / adversary / verifier / reviewer / security | author | effort | verify |
|---|---|---|---|---|---|
| `critical` | first-time analysis, architecture, constitution, threat model, `touches: money|pii|auth`, the guard paths | fable | opus (set fable per project) | high | judge; adversary on plan and on guard |
| `design` | two people would build it differently; a mechanism that failed twice | fable / fable / opus / opus / opus / opus | opus | high | judge; adversary twice |
| `full` | the default | fable / fable / opus / opus / opus / opus | opus | medium | judge |
| `light` | allowlisted paths, no risk path, under the line ceiling | plan_reviewer **none** (the deterministic check alone stamps) | opus (**sonnet not shipped**: unproven by the eval) | low | gate + golden test, no judge |

Agent files carry a DEFAULT model equal to the role's default; the dispatch-time model always overrides it. Effort travels in the dispatch prompt. Every role dispatch starts with the `REEF-TASK:` (or `REEF-FEATURE:`) line, so the guard knows the tier; `Explore` runs as `mechanic`.

## The adversarial stage
A `design` or `critical` task runs the `loophole-hunter` twice — on the plan before code, on the finished guard before close — with one question: *how can every check be green while the defect happens?*; once per release it runs `pass=system` against the threat model and a running worktree. Read-only by the guard, cites file:line, ranks holes by whether they will happen here and by their real cost, attacks the last round's fix first. BLOCKER fails the pass under the cap; NEW-ROW becomes a queue row. `scripts/reef-adversarial` records only a PASS without BLOCKER lines. Never on `mech`.

## Settings (`.reef/config.json` — the one home for every number)
| Key | Default | Effect |
|---|---|---|
| `gates.fast` / `gates.full` / `gates.extra` / **`gates.release`** | `""` / stack test / `{}` / c4 drift + gitleaks + the stack's audit (new project; proposed on upgrade) | commit gate / verify, review, CI / other gates / release-branch gates (`reef-ci-local.sh --release`; a missing tool is exit 77 = skipped = exit 2) |
| `caps.attempts` | `3` | fix rounds per task, and per item on its rollup |
| **`caps.context_tokens` / `caps.context_warn`** | `150000` / `100000` (new project); `0` / `0` (off) on a migrated 0.5 project | the dispatching session's context ceiling / warning. Set from the measured rows (`docs/perf/dogfood-2026-10-16.md` §E): session maxima 58k–159k, p90 148k, so the warning fires late in a planning or critical-row session and the ceiling only on a runaway; a 60%-of-window ceiling would have cut the critical row in two. Tighten per project if its rows are smaller |
| **`caps.feature_tokens` / `caps.batch_tokens`** | `0` / `0` (off) | token budgets the tick checks; over one, the feature or batch parks |
| **`tiers.<tier>.roles` / `.effort` / `.paths`** | the table above; design paths auth/crypto/secrets/migrations; critical paths `.githooks/**`, `scripts/reef-*`, `hooks/**`, `.reef/config.json` | model per role, effort, path classes that force the tier |
| `tiers.light.allow` / `max_lines` / `migrations` | `docs/**, README.md` / `80` / migration dirs | what may be light |
| `graph.parallel` · `resources.<name>.slots` · `worktree.dir` / `worktree.setup` | `10` · `1` (`heavy` 2) · `.reef/worktrees` / stack install | as in 0.5 |
| `roles.*` | author opus · verifier opus · plan_reviewer fable · planner fable · adversary opus · reviewer opus · security opus · mechanic sonnet | the fallback when the tier table does not name the role |
| `merge.by` · `ci.feature_gate` · `branches.base` / `branches.release` | `human` · `ci` · `main` / `main` (init: `develop` / `main`) | as in 0.5; `ci.check_name` (`every gate, once`) names the required check for `reef-repo` |
| **`paths.features`** · `paths.tasks` / `adr` / `glossary` / `runlog` / `queue` | `reef/features` (0.6 tree) · 0.5 locations for a 0.5 project, `reef/…` for a 0.6 one | where things live; the loaders accept either shape |
| `plan.test_re` / `plan.max_words` / **`plan.max_tasks`** | `""` / `0` / `12` | test-name override / task word cap / split a feature above this |
| `writing.task_words.<tier>` · `handback_words` · `prompt_words` · **`report_words`** · `journal_words` / `queue_words` · **`sentence_words`** / **`criterion_words`** · **`session_start_tokens`** | 600/2500/2500/2500 · 150 · 120 · 0 (unmeasured: warn only) · 40 000 / 35 000 · 25 / 50 · 8 000 | caps; `task_words`, the sentence and criterion rules fail only under 0.6 |
| **`loop.inflight_stale_minutes` / `loop.no_progress_ticks`** | `90` / `3` | an in-flight marker older than this is "returned"; identical ticks before the loop parks |
| **`context.failure_lines` / `context.read_lines_max` / `context.explore_files`** | `60` / `300` / `40` | the failing block's cap; (the Read tripwire was cut — the key is reserved); an Explore agent's file budget |
| **`converge.test_cmd`** | `""` | how `reef-converge` runs one named test (`{name}`); empty = the full gate once |

0.5 configs keep working: `gates.test` is an alias of `gates.full`; every new key defaults to the old behaviour; `scripts/reef-migrate` adds the keys once.

## Measured
- `docs/perf/payloads-2026-10-16.md` — the hook payloads 0.6 relies on, captured from a live Claude Code 2.1.301 session (what was and was not verified).
- `docs/perf/baseline-2026-10-16.md` — a real session through `scripts/reef-cost.py`: first turn 91k tokens, 43% of context attachments, 31% raw Bash output; the targets 6.2 (< 8k at start) and 5.7 (< 60k per row) are set against it.
- `docs/perf/eval-baseline-2026-10-16.md` — `scripts/reef-eval` on the frozen corpus, k=3: every true blocker caught by every agent; precision was the weakness; the four-kind bar took the verifier's false-FAIL rate from 0.33 to 0.00 with nothing dropped; the corpus's own PASS fixtures were wrong twice and the agents were right.
- `docs/perf/guard-profile-2026-10-16.md` — p95 per matcher (≤ 130 ms); every hook timeout ≥ 5 × p95.

## Layout
One tree, grouped by feature; machine state in `.reef/`; three files at the root; tooling where git and CI expect it.
```
AGENTS.md  CLAUDE.md (pointer)  HANDOFF.md                 # root: the three files every agent meets first
.reef/                                                      # config and machine state
  config.json  version                                      #   committed
  loop.json  inflight/  verifying/  review/  approvals/  worktrees/  proposed/  ci-local/  .plan-review.json   # gitignored
reef/                                                       # every committed Reef artifact
  constitution.md  queue.md  queue-archive.md  journal.md  glossary.md  day-zero.md  recalibration.md
  architecture/   architecture.md  conventions.md  workspace.dsl  context.md  container.md  threat-model.md
                  adr/NNNN-<slug>.md                        # project-wide decisions only (stack, hosting, boundaries)
  features/       README.md                                 # generated index of features (never hand-edited)
    <feature-slug>/                                         # one folder per queue row, named by the feature
      SPEC.md                                               #   the intent, end to end, FR keys by layer
      specs/<part>.md                                       #   child specs, big features only
      adr/NNNN-<slug>.md                                    #   this feature's decisions, with diagram
      tasks/NNNnn-<slug>.md   tasks/done/                   #   the plan; ids global; rollup lives here too
  archive/<date>/
scripts/reef-*   .githooks/   .github/workflows/ci.yml      # tooling where git and CI expect it
```
Plugin: skills/ (init, assess, explore, loop, plan, plan-review, task, verify, review, c4, threat) · commands/ · agents/ (implementer, verifier, plan-reviewer, loophole-hunter, mechanic) · scripts/ (`reef-init.py`, `reef-migrate`, `reef-loop.py` [tick|start|stop|wait], `reef-handoff`, `reef-gate.sh` [fast|full|--failures], `reef-attempt`, `reef-guard.py`, `reef-approval.py`, `reef-record`, `reef-graph.py`, `reef-plan-check.py` [--digest|--needs-agent|--verify-stamp], `reef-converge`, `reef-adversarial`, `reef-claims.py` [check|--handback|report|claims-only], `reef-tier.py`, `reef-queue.py` [status|ready|check|adr-number|index], `reef-structure`, `reef-recalibrate`, `reef-repo`, `reef-c4.py`, `reef-threat.py`, `reef-ci-local.sh` [--ci|--release], `reef-snapshot.sh`, `reef-cost.py`, `reef-eval`, `reef-guard-profile.py`) · hooks/hooks.json (PreToolUse Bash · Task|Agent · Edit|Write|MultiEdit; PostToolUse AskUserQuestion; Stop; SessionStart) · migrations/ · schemas/task.schema.json · templates/ (config, task, spec, adr, glossary, runlog, pre-commit, stacks/, project/) · tests/eval/ (the corpus) · tests/fixtures/payloads/ · docs/perf/

## Selftests
`sh tests/run.sh` — 401 sabotage and contract tests (312 Python + 89 shell, as the suite runs them). Every mechanism in this plugin has a test here that shows it going RED on the defect it exists to catch (each suite is listed in `tests/run.sh`); CI runs them on ubuntu (dash — the honest POSIX check) and macos, and a change to a `CLASS: code` script without a `tests/` change fails the PR. The live eval (`scripts/reef-eval run`) needs the CLI and credentials and never runs in CI; its fixture replay does.

## Acknowledgments
Reef is an original implementation, but its process ideas stand on two open projects:
- [iusztinpaul/squid](https://github.com/iusztinpaul/squid) (Apache-2.0) — the agent-team lifecycle, author/verifier separation, retry-cap concept, artifacts-as-memory.
- [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) — grilling, vertical-slice/tracer-bullet rules (a few planning heuristics in reef-plan closely paraphrase that repo's wording), spec/ticket discipline.
No code was copied from either project. Thanks to Paul Iusztin and Matt Pocock for publishing their work openly. The reviewers Reef calls by name (`plan-review`, `code-excellence`, `code-security`) are [mahmoudmoe84/review-toolkit](https://github.com/mahmoudmoe84/review-toolkit).
