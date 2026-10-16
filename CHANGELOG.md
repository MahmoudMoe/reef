# Changelog

## 0.6.0 — governance, spec, tiers, day zero, loop engine, one tree

### Phase 0 — verify first, then measure
- **0.0 Verified hook payloads** from a live Claude Code 2.1.301 session: `tests/fixtures/payloads/` (PreToolUse
  inside a sub-agent carries `agent_id` + `agent_type`; Stop carries `stop_hook_active`; SessionStart carries
  `source`; `hooks.json` accepts `timeout` and `onFailure: block`; AskUserQuestion's answers live in
  `tool_response.answers` — schema-derived, headless sessions exclude the tool). Findings and consequences per
  item: `docs/perf/payloads-2026-10-16.md`.
- **0.1 `scripts/reef-cost.py`** — turns, context per turn (mean/p50/p90/max), compactions, cache writes vs reads,
  context share by category, sub-agent transcripts, fix rounds per feature; `--session-start`; `--live` reads the
  last 256 KB only. Tests: `tests/test_cost.py` (known counts exact; boundary+summary = one compaction; 50 MB
  `--live` under 3 s).
- **0.2 Baseline** on a real session: `docs/perf/baseline-2026-10-16.md` (first turn 91k tokens; 43% of context is
  attachments, 31% raw Bash output).
- **0.3 `scripts/reef-eval`** + frozen corpus `tests/eval/corpus/{verifier,hunter,plan-reviewer}.json` (6/6/5 real
  diffs with ground truth, each building to a GREEN gate); live `run` via `claude -p` in a fresh worktree per run,
  mechanical `score` (VERDICT / BLOCKER / `AC<n> FAIL` lines), `compare` (catch-rate and approve-precision must not
  drop). Tests: `tests/test_eval.py` (parser, comparison rule, fixture replay: trusting the hand-off drops the
  catch-rate and is refused; every corpus entry builds green and passes plan-check where the reviewer needs it).
- **0.4 Baseline evals** k=3: `docs/perf/eval-baseline-2026-10-16.md`.

### Phase 1 — foundations and trust binding
- **1.0 Version marker and four tiers.** `reef-init` writes `.reef/version`; `tier: critical | design | full | light`
  (`schemas/task.schema.json`, `touches:`); the tier table `tiers.<tier>.{roles,effort,paths}` in
  `templates/config.json` (critical: fable judges, opus author, effort high; light: `plan_reviewer: none`);
  `reef-attempt` resolves `author:`/`verifier:`/`adversary:` through it (effort only rises); `reef-plan-check.py`
  gains `critical`, `--needs-agent` (exit 3 on an all-light plan), `--digest`; the guard resolves the tier from
  the `REEF-TASK:`/`REEF-FEATURE:` line every role dispatch carries, treats critical like design for the
  adversarial pass, maps `Explore → mechanic`; the pre-commit closes critical like design. Tests:
  `tests/test_tiers_lock.py::FourTiers` (light with opus → DENY; critical with sonnet → DENY; critical without
  `adversarial-plan` → DENY; one full task still needs the reviewer; an unset table is exactly 0.5),
  `tests/test_hooks.sh` (critical into done/ without `adversarial-guard:` → rejected).
- **1.1 Review records bound to the forge SHA.** `scripts/reef-record <feature> <verdict>` writes
  `.reef/review/<feature>.json` from `gh pr view` / `gh api …/git/commits`; under `merge.by: loop` the guard
  refuses `gh pr merge` / `gh api …/merge` unless a GREEN record names the forge head — a clean base merge
  (`git merge-tree --write-tree`, git ≥ 2.38) or claims-only commits are the only carry-overs; gh under its own
  deadline, fail closed. Tests: `tests/test_record.py` (push after GREEN → DENY; gh fails/slow → DENY; clean
  base merge → allow; rebase → DENY; old git → DENY; merge.by human → nothing gated).
- **1.2 Human-only plan approval.** `/reef-plan` asks `Approve plan <slug> at <digest16>?`; the PostToolUse hook
  `scripts/reef-approval.py` writes `.reef/approvals/<slug>.json` only on `Approve` with the current digest (a
  timeout, another label or a stale digest writes nothing); `--verify-stamp` and the guard require it for
  features planned under 0.6 (`planned_under` in the stamp), warn for older ones; hand-written records are denied
  (Bash writes and the new `Edit|Write|MultiEdit` matcher). Tests: `tests/test_tiers_lock.py::HumanOnlyApproval`.
- **1.3 Reviewer lock.** `agent_type` in the payload (class code, verified live): verifier, loophole-hunter,
  plan-reviewer and Explore get no mutating git, no Bash write, no CI wait; `.reef/verifying/<id>` (written on an
  allowed judge dispatch) locks typeless sub-agent calls too; `gh pr checks --watch`, `gh run watch`, `sleep ≥ 60`
  denied for every sub-agent. Tests: `tests/test_tiers_lock.py::ReviewerLock`.
- **1.4 Fail-closed guard with a deadline.** `timeout` + `onFailure: block` on every matcher (schema verified);
  `signal.alarm` deadline inside the guard (`REEF_GUARD_DEADLINE`); `scripts/reef-guard-profile.py` →
  `docs/perf/guard-profile-2026-10-16.md` (timeout ≥ 5 × p95, floor 10 s); no python3 → a dispatch is denied.
  Tests: `tests/test_tiers_lock.py::Deadline`, `tests/test_contracts.py::LedgerClasses::test_hook_timeouts_match_the_profile`,
  `tests/test_hooks.sh` (no python3 → exit 2).
- **1.5 The guard guards itself.** `scripts/reef-*`, `.githooks/*`, `hooks/hooks.json` and the
  `roles|caps|gates|tiers` keys of `.reef/config.json` change only under a `critical` task in flight
  (`.reef/inflight/<id>`, written by the guard on an allowed implementer dispatch) or inside Reef's own
  repository (`CLAUDE_PLUGIN_ROOT`); `reef-init --accept` stays allowed. Tests: `tests/test_tiers_lock.py::GuardGuardsItself`.
- **1.6 `# CLASS: code|tripwire` headers** on every script and the pre-commit; `tests/test_contracts.py::LedgerClasses`
  ties README ledger rows to a script of that class; `.github/workflows/ci.yml` job `code-change-needs-a-test`.

## 0.5.0 — the graph executor and the full project setup

- **Task graph executed, not just declared.** `scripts/reef-graph.py` computes the ready set from
  `blocked-by`, `resources:` and `graph.parallel`; `/reef-task` dispatches every ready task in
  parallel, each in its own worktree (`reef-graph worktree`); the guard refuses any implementer
  dispatch outside the ready set and marks the task `in-progress` on allow, under one graph-wide
  lock. `reef-graph lock <resource> -- cmd` serialises heavy commands (2 slots by default).
- **Guard rules from a measured merge wave:** `git stash` denied (one stack serves every worktree);
  a gate piped into another command without `pipefail` denied (the pipe hides the exit code).
- **`tier:`** (light / full / design) on tasks; plan-check refuses a tier that does not match the
  complexity (mech ⇔ light). `resources:` is plan content; `worktree:` and `in-progress` are
  execution state the stamp ignores.
- **The adversarial stage.** `agents/loophole-hunter.md` ("how can this be green while the defect happens?"),
  mandatory twice on `tier: design` — on the plan before code (the guard refuses the first dispatch
  without `adversarial-plan:` bound to the plan's content) and on the finished guard before close (the
  pre-commit refuses a design-tier task entering `done/` without `adversarial-guard:`); never on mech.
  `scripts/reef-adversarial` records only a PASS without BLOCKER lines.
- **Claims bound to the round.** `scripts/reef-claims.py check` rejects a claim at a line the round did
  not add; `claims-only` is the one commit allowed after GREEN. Verifier and hunter attack the last
  round's fix first; "cannot verify here" needs the probe pasted.
- **`/reef-init` is the full project setup.** `scripts/reef-init.py` renders `templates/project/`
  (AGENTS.md, constitution, queue, ADR convention, journal, handoff, day-zero checklist, release-only
  CI, Dependabot on the integration branch, the hooks and every Reef script) adapted to the detected
  stack — idempotent: absent → written, identical → skipped, different → never overwritten (the
  rendering lands in `.reef/proposed/` with a diff; `--accept` applies it). Config keys are merged,
  never changed. `scripts/reef-ci-local.sh` (every gate, every exit code, 2 = skipped ≠ success; CI
  runs the same script), `scripts/reef-tier.py` (a tier only gets heavier), `scripts/reef-queue.py`
  (status derived from task files, ready rows, consistency, ADR numbering at merge). plan-check reads
  AGENTS.md as the brief when CLAUDE.md is a pointer. `/reef-loop` drives the outer graph.
- **Expensive measurements once per release** (project rules, `templates/project/AGENTS.md`): screenshots of
  every page, printed documents bound to the tree run on the frozen integration branch, in parallel lanes, not on
  every feature branch; a feature branch merges with them stale only when its other gates are green, stale told
  apart from failing by test name, never by file; a failure names the merge that caused it and holds the release.
- **The hunter ranks holes by real cost** (`agents/loophole-hunter.md`): it stops when the remaining holes' worst
  case is below the cost of another pass — no 100% mechanical guarantee for a guard whose worst case is cosmetic.
- Arabic user manual: `docs/manual/ar/index.html`.
- Model per role read at dispatch (`roles.*`, the guard refuses another model); `agents/mechanic.md`.
- Defaults: `graph.parallel` 10, `resources.heavy.slots` 2, `worktree.setup` per project.
- Version 0.5.0 (0.4.0 was `parallel-loop-compat`: merge setting, one cap per item, draft ADRs,
  per-feature stamp, fast/full gates, model per role, rule-first verifier).
