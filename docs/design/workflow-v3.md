# Workflow v3 — risk decides the path, evidence once per commit

Written 2026-10-25, at the owner's request ("the workflow needs to be redesigned fully: cut the time by half at least, keep
quality and security, keep every good feature, throw away what wastes time"). It follows `workflow-v2.md` (the owner's gate
last) and two field reviews written by the orchestrating session of the first adoption on an existing project (a Next.js,
Prisma and Vitest codebase with its own earlier loop). Approved by the owner as the design; each phase below still ships as
its own PR with a test that is red first, and each phase is re-scored by its measure, not by impression.

## 1. What the first adoption measured

| Where the time went | Evidence (measured in one session) | Root cause |
|---|---|---|
| The full suite ran three times on one commit | head `b1bc9971b5f4`: the gate, then two Proof rows, each a full build and vitest | proofs written as shell; the gate's per-snapshot cache is bypassed by a shell proof, and the verifier reruns by rule (0.7.1) |
| Three judges, no blocker | one row: acceptance 47k tokens, security 54k, a third judge; about 195k in all, every verdict GREEN/PASS | every row runs every judge whose angle overlaps the others |
| A five-line docs fix waited behind four steps | review → rollup → the plan stamp stale → a plan-check failure on finished tasks → a plugin fix | the rollup treated as a re-plan; a checker bug on done tasks |
| Proofs misread | a cell named `test` run as shell; `scripts/heavy.sh` read as a file name; two false `missing` | proofs are shell one-liners inside markdown tables |
| Every task worktree is costly | `npm ci`, generate, typegen and build each time, or about 60 tests go red | one worktree per task |
| False `contradicts` | build and vitest racing for the CPU | proofs run outside the resource lock |
| The orchestrator hit 105k of 150k after one review | a `/clear` and a handoff every few hours | an LLM drives every step of the row |
| More process than product | a whole session with no product line; footnotes at ⁷⁴ | the loop generates work about itself |

The structure every row ran, whatever its risk: grill → planner → hunter ‖ plan-reviewer (up to two rounds) → the owner's
approval → per task: worktree + setup → implementer → gate → verifier → merge-close → converge → mechanic → acceptance →
diff review → hunter guard pass → security → record → the owner's merge → close → security again at release.

## 2. The principles

1. **Risk decides the path.** The tier already exists and is decided by script from paths and `touches`; v3 makes it decide
   the whole pipeline, not only the models. Most rows take the fast path; auth, personal data, money, migrations and
   security upgrades take the critical path.
2. **One trusted result per commit.** The suite runs once per commit, on a machine the author cannot touch (CI), and every
   judge reads that result. Nobody reruns a build or the full suite on a commit that already has a result.
3. **One fresh judge per concern.** The author never judges its own work (the constitution holds), but two judges never
   look at the same thing from overlapping angles.
4. **Proofs are named tests.** An acceptance criterion is proven by a test with a name, run by the project's runner with a
   name filter. Shell in a markdown cell is the exception, tagged.
5. **Small batches, finish before starting.** At most two rows in flight; a row is closed before a third starts.
6. **Scripts orchestrate, models judge.** Merging, closing, records and the handoff are scripts; the language model plans,
   writes code and judges.
7. **Measure the pipeline.** Lead time, suite runs, tokens and rework per row are in the morning report, beside the
   previous batch's.

## 3. The v3 pipeline

**Fast path** (tiers `light` and `full`):

```
planner + plan-check (script) → the owner's approval (one question set per batch)
→ one worktree for the row → implementer, task by task in order, TDD, the pre-commit fast gate on every commit
→ the full suite once on the final commit: the CI result (or the guarded local record)
→ one reviewer: acceptance + diff + every criterion against its named test, reading that result
→ merge-close, then the loop merges into the integration branch after the merged commit's gate is green
```

**Critical path** (tiers `design` with `touches` auth/pii/money/migration, and `critical`): the same spine, plus the
hunter on the plan (one round; a second only on a blocker), a verifier per task, and the hunter's guard pass and the
security agent once per feature, all reading the same result.

**Unchanged:** the guard, approvals bound to the plan's digest, review records bound to the commit, CI, the release
branch's security pass and scanners, and the owner's merge into the release branch.

## 4. Keep, throw, and what catches what was thrown

| Removed or merged | What catches what it caught |
|---|---|
| a verifier per task on the fast path | the CI result for the commit, and the one reviewer's check of every criterion against its named test |
| the plan-reviewer agent and plan rounds on the fast path | `reef-plan-check` (deterministic) now, the reviewer's spec check at the end |
| the hunter's plan pass on the fast path | kept on the critical path, one round |
| `reef-converge` as a shell runner, the mechanic | named tests run by the project's runner; `[mechanic]` stays only for a proof that must write files |
| the separate diff review | folded into the one reviewer |
| security per item on `design` rows | security per item on the critical path, plus the release pass |
| a worktree per task | one worktree per row; rows in flight capped at two |
| the verifier and converge rerunning the suite | the CI result (or the guarded record) for the same commit |
| the owner's merge into the integration branch | the loop merges after a green gate on the merged commit; the owner merges the release |
| a rollup treated as a re-plan | a rollup is a fix round: no plan pass, no new stamp (already the rule; the checker bug on done tasks is fixed) |
| the hand-written handoff | `reef-handoff --write` at every wait |
| the grill on a row whose spec has no open question | the planner asks only what the spec leaves open, in the batch's one question set |

**Kept, all of it:** the guard and the author/judge split; digest-bound approvals; records bound to the commit; tiers by
path and `touches`; `reef-plan-check`; TDD; SPEC keys (FR/SC); ADRs and the journal; the queue on issues with priorities
and triage; the measured baselines (sizes, boundaries, raw SQL, structure) where only the new fails; the size-budget
ratchet; the threat model; the release wall (security pass, secret scan, dependency audit, semgrep, CI, the owner);
`reef-doctor` and `reef-update`; the owner's proxy for a delegated night.

## 5. Against how mature software factories work

| Practice | v3 |
|---|---|
| One trusted test result per commit, made by a server | yes once feature PRs run CI (`ci.feature_gate: ci`); the guarded local record is the fallback for a project without CI |
| Test the merged result, not the branch as written | the second row in flight is gated after `reef-merge-base`, on the merged commit (a merge queue of two) |
| Review effort tiered by the risk of the paths changed | the tier, by script, from paths and `touches` |
| Small batches, a work-in-progress limit | two rows in flight, `queue.batch_max` |
| A protected release path with scanning | the release pass, scanners and the owner's merge |
| Deterministic pipeline, people (models) only for judgment | phase 5: the row as a script-driven state machine |
| Metrics that show whether the pipeline improved | phase 1: lead time, suite runs, tokens, rework per row |
| Work items as tickets, labels as triggers, a sandbox per job | issues and labels since 0.7.1; the trigger and the sandbox are phase 7 |

The design is weaker than a factory in one place until phase 2 lands with CI on feature PRs: a result produced on the
author's machine. The guard protects the local record from an agent, not from a person.

## 6. The number

Counted from the skills for a three-task row: on the fast path agent dispatches go from 10–11 to 3, full-suite runs from
8–9 to 2, worktree setups from 4 to 1; on the critical path dispatches go from 15 to 11 and suite runs from 8–9 to 4. If
four rows in five take the fast path, cutting the time by half or more is plausible. That is an estimate: no wall-clock
per row has been measured yet, which is why phase 1 comes first.

## 7. The phases (one PR each, red first, in this order)

| # | Phase | Changes (main files) | Measure that re-scores it |
|---|---|---|---|
| 0 | The adopted project's config (the owner, no code) | `ci.feature_gate: ci`, `review.diff_review: off`, `converge.test_cmd` with a name filter, `caps.feature_tokens`, `gates.resources` + `resources.heavy.slots: 1`, a complete `worktree.setup` | the batch's baseline in the morning report |
| 1 | Measure the pipeline | `reef-cost.py` per row (lead time from the plan's first commit to the merge, tokens, suite runs from the gate's logs, rollups and reverts); the morning report's table gains them and the product-to-process commit ratio | the numbers exist for one batch before phase 2 ships |
| 2 | Evidence once per commit | `reef-gate.sh` writes `.reef/evidence/<snapshot>.json` (the guard denies any other writer, like `.reef/review/`); with CI on, `reef-record` and every judge read the check-runs for the commit; `reef-converge` runs a named-test proof through `converge.test_cmd`, reads the evidence for a whole-suite proof, runs a command proof under `gates.resources`; `reef-plan-check` refuses an untagged shell proof over 120 characters; the verifier agent and `/reef-verify` read the evidence and run fresh only when it is absent | suite runs per row ≤ 2 plus CI |
| 3 | The fast path | `reef-tier.py` names the path; `/reef-plan`: the plan-reviewer agent and the hunter's plan pass only on the critical path, one round, a second on a blocker; `/reef-task` + `reef-graph.py`: one worktree per row, tasks in order, no per-task verifier on the fast path; the guard accepts a fast-path task's close without a verifier report and still requires one on the critical path; `/reef-review` + `agents/acceptance.md`: one reviewer (acceptance + diff + criteria), security per item on the critical path only | dispatches per three-task fast row ≤ 4; lead time per fast row ≤ half of phase 1's |
| 4 | Finish before starting, a merge queue of two | `loop.rows_in_flight` (default 2) in the tick; the loop merges into the integration branch only after `reef-merge-base` and a green gate on the merged commit; `merge.by: loop` the default when `ci.feature_gate` is `ci` | no row waits on the owner for an integration merge; rework per batch not above phase 1's |
| 5 | Scripts orchestrate | the row as a state machine (`reef-run.py` + graph mode as a Workflow): plan → approval → build → evidence → review → merge → close, agents only for plan, code and judgment; `reef-handoff --write` at every wait | the orchestrator's context per row; no hand-written handoff |
| 6 | Process decisions to the proxy by day (the owner decides whether at all) | the proxy's contract extended from the night to process and wording questions in the day loop; product, money, data and look stay the owner's | the owner's questions per batch |
| 7 | The factory on GitHub Actions (optional, after 5) | a workflow template `reef-init` proposes: a row's issue labelled `reef-ready` starts a job that runs phase 5's state machine headless in the Actions sandbox (the plugin and its guard installed there, the model key as a repository secret), opens the PR, and labels the issue with its state (`reef-building`, `reef-review`, `reef-waiting-owner`); a scheduled job replaces the local night runner; the job's log is the observability | rows built per day without the owner's machine; minutes and tokens per row |

**Where GitHub Actions already is and is not in Reef.** Issues as the work items, labels for source and priority, and
Actions as CI are in Reef since 0.7.1. Not yet: a label that starts the agent, an agent running in the Actions sandbox
instead of on the owner's machine, labels written back as the loop's state, a scheduled run. Phase 7 adds them, and only
after phase 5, because an Actions job must run a deterministic script, not a conversation. Costs and limits to weigh then:
minutes on a private repository, the model key as a secret, a job's six-hour limit (the state machine must resume across
jobs), and a bot that merges only under branch protection and the guard's records.

**The quality guard on the whole plan.** Rework (rollups, reverts, defects the release pass or CI on the release branch
finds) per batch must not rise above phase 1's baseline over two batches. If it does, the phase that loosened a check is
reverted, not argued.

## 8. Risks

- One reviewer may miss what three judges caught. Nothing measured that any of them caught anything on the fast path's
  rows; the release pass, CI and the rework guard above are the net, and phase 1 makes the miss visible.
- A model's verdict varies; deterministic checks (tests, gates, scanners, `reef-plan-check`, the baselines) carry the
  weight, the reviewer carries the judgment.
- CI minutes on a private repository cost money past the free allowance; the guarded local record is the fallback.
- The guard is `critical` tier: phase 3's guard change ships with its sabotage tests first, in Reef's own repository.
