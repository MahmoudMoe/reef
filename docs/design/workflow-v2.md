# Workflow v2 — the owner's gate is last

Written 2026-10-17, after the first full day of Reef on a real project (qassimha, batch 2). Three planning sessions
(12:00 → 18:19, three `/clear`s) produced three approved plans and no code. The transcript shows where the hours
went, and the field review (`usability-autopilot-plan.md` §2, plus apexyard, Superpowers, spec-kit, OpenSpec, BMAD,
GSD, ccpm) shows what the rest of the world does. This is the workflow that follows from both, the decisions behind it,
and the phases that deliver it. Each phase has a measure; the measure, not the impression, re-scores it.

## 1. What the first day measured

| Where the time went | Evidence | Root cause |
|---|---|---|
| Hunter rounds on prose | row 13: 5 rounds, row 2: 4, both later 6 | the two-round cap was a sentence in a skill |
| Edits after the owner's approval | ADR `Status: Accepted`, sentence trimming, 28 advisories "fixed now" | the approval sat in the MIDDLE of the pipeline; every later finding voided it and re-ran hunter + review |
| Plan review after approval | row 11 FAIL and row 13 HALT arrived after the gate | same |
| Word-ceiling fixes after approval | five long sentences in 1302 found after Approve | the approval hook did not require a green plan-check |
| Orchestrator turns | 52–71 API turns per session at ~90k context | every agent result and every bookkeeping step is one turn |
| Owner questions | 4 question sets + 3 re-approvals pending | advisories, HALT, WILL BITE all reached the owner separately |

Not in the measurement: the owner's own latency between question sets; it is real and invisible in the transcript.

## 2. Principles

1. **The owner touches a plan twice**: the grill (intent) and the gate (approval of an exact digest). Everything else
   that reaches the owner is a HALT or a USER ACTION, never a "may I".
2. **Machines before the human.** The hunter and the plan reviewer run in parallel on the same digest before the
   owner sees the plan, so no finding voids an approval.
3. **The truth is in the code, not the prose.** Two hunter rounds on a plan, enforced by the recorder; a hole still
   open after that is the owner's decision at the gate or an AC the code proves. The hunter's pass on the finished
   code stays.
4. **Small tasks.** A task is one slice a verifier judges in one sitting: `plan.max_acs` (8). Superpowers plans 2–5
   minute tasks; 1302 carried 21 criteria.
5. **The graph runs outside the chat** (phase 3): the orchestrator supervises summaries; it is not a queue that
   receives one agent result per 90k-context turn.
6. **Ceremony sized to the row** (phase 2): a `found` row touching one file is `light`.
7. **Everything measured**: planning cost per feature and per task, before and after each change, with `reef-cost`.
8. **Records do not move**: approval and verdict bound to the plan digest, merge bound to the commit, a guard that
   denies, judges with fresh context and a snapshot. These are what nobody in the field has; they are not traded.

## 3. The workflow

Per batch:

| # | Stage | Who | Output |
|---|---|---|---|
| 1 | **grill**, once for every row of the batch | owner | queue footnotes |
| 2 | **draft**, in the row's worktree from the first line | `reef:planner` (lean) | SPEC, tasks (≤ `plan.max_acs` criteria each), draft ADR, `reef-plan-check.py` green before it returns |
| 3 | **machine review** | `loophole-hunter` ‖ `plan-reviewer`, fresh | one fix round by the planner (BLOCKING, hunter BLOCKERs, `WILL BITE`), plain advisories into `## Reviewer notes`, one fresh re-check; only a HALT reaches the owner |
| 4 | **gate**, last | owner | ONE question set: `Approve plan <slug> at <digest16>?` per plan, Design decisions, any hunter hole open after round 2. After Approve, only a HALT ruling edits the plan (`reef-adversarial … --decided <mark>` re-stamps) |
| 5 | **build** as a graph | implementer → (verifier ‖ hunter guard) → merge, each task in its worktree | journal row with the orchestrator's cost |
| 6 | **review** the PR into `branches.base` | acceptance + diff review by task | GREEN record; found rows via `add-row` |
| 7 | **close** | scripts | archive, ADR numbering, `triage` when found rows are stale |
| 8 | **release** to `main` at the batch's end | security pass, threat model, C4 | `reef-repo` protects main |

Rows that touch the same module are planned one at a time; everything else in parallel.

## 4. Decisions (ADR form)

### D1. The owner approves last
**Context.** Every finding after the gate (review FAIL, HALT, advisories, word ceilings, ADR status) voided the
approval and re-ran the hunter and the review: a whole session (16:17–18:19) without code.
**Decision.** The gate follows the machine review. `reef-loop.py tick` names the machine review before the approval;
`reef-approval.py` refuses to record while `reef-plan-check.py` fails; the ADR `Status:` line and `## Reviewer notes`
are outside the digest. After Approve only a HALT ruling or an owner decision edits the plan, footnoted and re-stamped.
**Consequences.** The owner sees the plan later, after the machines. If the owner cancels, 15–20 minutes of agent
time are lost. The owner's answers to the grill still shape the plan before any machine runs.

### D2. Two hunter rounds on a plan, enforced
**Context.** Rows 2 and 13 reached round 6; the real hole (owner scoping on row 2's store methods) came in round 4 and
the code review on the diff would have caught it at a third of the cost. The later rounds argued about
`pg_stat_activity` pid syncs and pooler timeouts on code that did not exist.
**Decision.** `reef-adversarial` refuses to record a plan pass whose round exceeds `hunter.plan_rounds` (2). A hole
open after round 2 is the owner's decision at the gate (fix as drafted / accept as a found row / drop the task) or an
AC with a Proof row the code proves. The hunter's guard pass on the finished code is unchanged.
**Consequences.** Less assurance on prose for `critical` rows; the verifier, the code hunter and the diff review keep
their roles. The cap is a config value: a project that wants three rounds sets it.

### D3. A task is at most `plan.max_acs` criteria
**Context.** 1302 carried 21 criteria; a verifier judging 21 criteria in one sitting is the expensive, inaccurate
case, and parallelism is as wide as the number of tasks.
**Decision.** `reef-plan-check.py` fails a task over `plan.max_acs` when set (template 8), warns above 8 when unset.
The planner splits; the reviewer never does.
**Consequences.** More tasks, more worktrees, more merges; each one cheaper to verify and to fail.

## 5. Phases and measures

| Phase | Items | Done when (the measure) |
|---|---|---|
| 0 (2026-10-17, shipped) | quiet commands, status line, cost in the record, triage, notes outside the digest, approval hook requires green plan-check, evidence is the agent's, in-flight across worktrees, `reef:planner` | PRs #39–#45 merged |
| 1 (this PR) | D1, D2, D3; hunter ‖ reviewer; verifier ‖ hunter guard; worktree first; skills reordered | three rows plan in one session; ≤ 2 question sets; zero re-approvals caused by a review |
| 2 | `reef-cost` attributes planning roles to the feature; `reef-update`, `/reef:doctor`, `status.html`, `reef/README.md`; `found` one-file rows are `light` | planning a found row under 10k; the owner never types `--accept`/`--keep` unprompted |
| 3 | graph mode spike (shipped 2026-10-17 as `/reef-graph`): `reef-graph-run.py probe / generate / settle`; the gate is the probe's recorded denial, fail closed; a workflow script has no filesystem, so the mechanical steps run as a `reef:mechanic` agent inside the pipeline and at generate/settle; the merge stays with the orchestrator | one feature both ways, cost and wall time by `reef-cost` (`growth <id>`, role `workflow`); decision by the numbers — **decided 2026-10-18** (`docs/perf/2026-10-18.md` §C: 6 orchestrator turns at ≤ 46k against ≈ 25 at 90–150k): `graph.mode: auto` |
| 4 | external runner `reef-run` if the workflow is not enough; release drill to `main`; verifier FAIL drill | a batch runs to its owner questions with zero `/clear`; a release lands |

What the five phases do not change: the price of one orchestrator turn. Only phase 3 moves that.
