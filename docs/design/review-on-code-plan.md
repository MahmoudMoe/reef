# No agent on the plan — review the code and its output against the SPEC

Status: **Parked** (2026-10-25). Not started. Resume after the current adoption merges its first row; re-measure first.
Owner's words (2026-10-25): "مشكلتى البطىء و بنلف حوالين نفسنا فى نفس النقطه" (slowness; circling the same point);
"نهلى بلان ريفيو و لوب هانتر و دايجست حاجة واحده قلل الايجنت و الخطوات" (plan review, hunter and digest as one thing —
fewer agents, fewer steps); "خلى فيه ريفيو على الكود و الناتج مقابل ال spec مش على البلان" (review the code and the output
against the spec, not the plan).
Reviewed adversarially (fresh context) on 2026-10-25; its verdict and corrections are folded in (§9).

## 1. Evidence — the same failure twice

| Adoption | What happened | Source |
|---|---|---|
| first (2026-10-17) | three planning sessions, three approved plans, no code | `docs/design/workflow-v2.md` §1 |
| second (2026-10-24/25) | ~1.5 days; rows 1, 3, 12 in planner/review rounds, owner rulings ⁵⁵–⁶¹, a hunter's found row 40, row 6 queued behind row 3; zero rows built | the owner's pasted loop status (not in this repo) |

v2 capped the hunter and moved the gate last. The circle came back through other doors:

1. **Any agent that reads the plan finds something.** An owner Edit re-runs the machine review "fresh"
   (`skills/reef-plan/SKILL.md` §4); the reviewer's input is the whole plan (`agents/plan-reviewer.md`). The stop rule —
   "a second round of the same blocking finding is a STOP" (`skills/reef-plan-review` step 3) — is prose, nothing
   compares findings across rounds, and a fresh reader finds a *different* finding.
2. **A post-gate HALT re-runs the full review** (`reef-plan-review` steps 3, 3b).
3. **The digest is voided for non-semantic reasons**: a stale `scripts/` in a worktree computes a different digest
   (`skills/reef-task` §0), re-running approval and review.
4. **The gate invites Edits**: "Show every task in full" (`reef-plan` §4) puts the owner on task prose, not the SPEC.
5. **Planning breeds planning**: plan-pass hunter NEW-ROWs become found rows that re-enter planning (row 40).
6. **No WIP limit on planning**: `reef-loop` §2 plans rows in parallel where modules differ; owner rulings scale with
   rows in planning, and the owner is one person.
7. **The orchestrator is an LLM session**: context ceiling, `/clear`, re-entry.
8. **The planner's declared tier is unverified.** `scripts/reef-tier.py` computes the tier from the diff, but nothing
   runs it (`git grep reef-tier`: docs, schema, tests, and `reef-init.py` copying it). Path classes therefore never
   raise a tier; plan-check enforces only `touches:`.

## 2. The field (2026-10-25)

| | Matt Pocock's skills / label factories | Reef today |
|---|---|---|
| Owner time | before `ready`: `grill-me` → `to-spec` → `to-tickets` | grill, gate, rulings during plan rounds |
| Rigor on | code: `tdd` red-green per vertical slice; `code-review` on the diff "on two axes, standards and spec" | the plan: planner, plan-reviewer, hunter, digest |
| Rounds | "At most two automatic fix rounds… a third rejected review hands the PR to you" | resets on every owner Edit |
| Loop driver | labels as a state machine; plain code; fresh runner per stage | an LLM orchestrator session |

"The rate of feedback is your speed limit" (mattpocock/skills README). A test settles; a reading of prose does not.
Sources: github.com/mattpocock/skills, github.com/mattpocock/sandcastle, github.com/jonbaldie/software-factory (built
after Pocock's GitHub Actions post; the post itself not located).

## 3. Principle

**The owner decides once, on the SPEC. The plan gets a script, not a reader. Agents judge the code and what it does,
against the SPEC.**

Most of the code side exists already (verified on origin/main): `agents/acceptance.md` judges the feature against
`SPEC.md` FR/SC keys, "not its task files, which can drift", running the entry point; `scripts/reef-converge` executes
every Proof row; the verifier judges each task's ACs with evidence; the hunter attacks the finished guard; `reef:security`
runs per feature with a design/critical task. plan-check already requires every AC to cite an FR/SC key defined in its
folder. So this change is mostly a deletion.

## 4. Changes — one PR each, each with a test red on main

| # | Change | Enforced by |
|---|---|---|
| L1 | **No agent on the plan.** Delete the plan-reviewer agent and the plan-pass hunter. The deterministic `reef-plan-check.py` stamps every tier. Add FR coverage to it: every FR-n cited by ≥ 1 AC (the reviewer's "ADR coverage / scope gaps" made deterministic). The approval at the digest stays; it now means "plan-check green and approved". | Delete `review_state`'s PASS requirement and `--needs-agent` (`reef-plan-check.py`), `reef-record plan-review`, `reef-adversarial plan` (+`--decided`, `adversarial-plan:`), the guard's design-task-without-plan-pass deny and plan round cap, `hunter.plan_rounds/plan_pass`; delete `agents/plan-reviewer.md`, `skills/reef-plan-review`; `reef-plan` §3.5 removed; `reef-task` §0 approval-only. A test per deletion that the dispatch is allowed with approval alone. |
| L2 | **The verifier's yardstick is the SPEC.** Before writing each `RULE AC<n>`, the verifier reads the FR/SC keys the AC cites in `SPEC.md` and writes the rule from the key; an AC that drifted from its FR fails at the task, not at acceptance. Acceptance unchanged; its `unrequested` finding becomes a found row, not a blocker. | `reef-claims.py report` requires each RULE line to name its key; contract test on `agents/verifier.md`, `skills/reef-verify`. |
| L3 | **The gate is the SPEC.** The owner approves `SPEC.md` + the one-line task list; task text on request. An owner Edit is a footnoted ruling: the planner applies it, plan-check green, re-approve — no review round exists. The digest is computed by the approval hook and never shown (the `--summary` line stays the owner's evidence). | `reef-approval.py` question regex relaxed, digest at record time; two records stay (approval written only by the hook, verdicts by `reef-record` — one file would let the orchestrator forge an approval). |
| L4 | **The tier is checked against the diff.** At hand-back, before the judges, `reef-tier.py` runs on the task worktree's working tree vs base (the implementer's work is uncommitted until `reef-merge-close`; `base...HEAD` is empty there). A computed tier above the declared one is recorded (`.reef/ci-local/tier-<id>.json`); `reef-attempt` and the guard resolve roles from `max(declared, computed)`. The task file is not rewritten (`tier:` is inside the digest). A raised tier needs the guard hunter only. | `reef-tier.py --worktree`; `reef-attempt` reads the record; `reef-merge-close` refuses without it. |
| L5 | **A WIP limit on planning.** `loop.plan_ahead` (default 1): rows between `plan:` and merge, beyond the one building. Before the project's first merged row the limit is 0 (prove the build path once). A blocked or parked WIP row does not hold the limit (no deadlock when the first row waits on `merge.by: human` or hits its cap). | `reef-loop.py tick` names no further `plan:`; the guard on planner dispatch. |
| L6 | **No owner question between Approve and merge** except the listed stops (credential, cap, a HALT in code, a data/security decision). | Measure: AskUserQuestion count per `REEF-FEATURE` span in `reef-cost`; enforce later if the measure fails. |

Order: L1 → L2 → L3 → L4 → L5 → L6. L1 alone removes the circle. Every prose change in a skill/agent gets a contract
test in `tests/test_contracts.py`; skills stay ≤ 60 lines.

## 5. What does not change

Deterministic gates; the guard; approval bound to the digest; the verifier with its snapshot; the hunter on finished
code (`adversarial-guard:` + pre-commit); `reef-converge`; acceptance against the SPEC; `reef:security`; the GREEN
record; the owner's rulings ledger.

## 6. Out of scope (separate decision)

- **The loop as code on issue labels** (`queue.home: issues` already models rows, priorities, batches and questions as
  issues): a runner advancing labels, a fresh session per stage, no orchestrator context.
- GitHub Actions as the runner.

## 7. Done when (measured with `reef-cost` and the journal)

- Zero agent turns between plan-check green and the gate.
- A `full` row: approval to merged PR in one session; ≤ 2 owner question sets (grill, gate).
- Planning tokens per `full` row below the first adoption's 66k (`docs/design/plan-cost.md`).
- No task merged at a tier below its computed one.

## 8. Risks

- A task↔ADR contradiction (the old HALT) surfaces as a verifier FAIL after one implementation round, not before; bounded
  by `caps.attempts` (3). Reef's own measure supports the trade: the real hole of the first adoption came in prose round 4,
  and the diff review would have caught it at a third of the cost (`workflow-v2.md` D2).
- A `critical` plan whose ACs omit a defect class entirely is no longer attacked before code; the guard hunter states the
  defect from the task Scope and may file a missing AC as a NEW-ROW; `reef:security` per feature stays.
- The WIP limit lowers throughput for independent rows until the first merge; it is a config value.
- L4 adds a script step per task, no agent.

## 9. Adversarial review (2026-10-25) — what changed because of it

- First draft's "delta review" (BLOCKING cited inside changed hunks) dropped: not mechanically checkable — the reviewer
  may cite quotes, not lines; invariant findings cite code, never plan hunks.
- First draft's round budget and tier-gated plan review replaced by L1: with no plan reader there is no round to count;
  gating only `--needs-agent` would have deadlocked on `review_state`.
- "Wide critical paths inherit ceremony" corrected: paths never apply today (door 8).
- L4: diff the working tree; no plan-pass requirement on a raised tier (else a fix-round deadlock).
- L5: count rows between `plan:` and merge; blocked/parked rows release the limit.
- One record file rejected: two writers (hook, orchestrator) must stay two files.
- Doors 2–5 added.

## 10. Rejected

- More caps on the hunter: v2 did that; the circle moved to the reviewer.
- One merged plan-critic agent: still a reader of prose; for `critical` it blends the fair reviewer and the adversary.
- Patching an adopted project's copy of Reef's scripts: `reef-update` overwrites them.
