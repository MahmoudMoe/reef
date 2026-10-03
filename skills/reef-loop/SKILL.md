---
name: reef-loop
description: Run the project loop — the outer graph. Take every ready queue row (planned before found, current batch only), run each through plan → plan review → the task graph → review → merge into the integration branch → close, in parallel where rows do not collide; stop only for the owner's decisions, a missing credential, a wrong spec, or the cap; batch the owner's questions. Use when the queue has rows, or the user says "/reef-loop".
argument-hint: <row id | empty = every ready row>
---

# Reef Loop — the outer graph

**Input:** `docs/queue.md` (`paths.queue`) and the task files. **Output:** rows merged into `branches.base`, closed in the same breath; a release PR into `branches.release` for the HUMAN; a rewritten `HANDOFF.md`.

You are the orchestrator: a MANAGER with a short context. Read `.reef/config.json`. State lives on disk (`scripts/reef-queue.py status`, `scripts/reef-graph.py status`, `git status`) — recover it, never remember it.

## 1. The ready rows — computed
`python3 scripts/reef-queue.py ready` — rows of the current batch whose `Depends` are merged, planned before found. If it prints only found rows, STOP and escalate: the roadmap is blocked, and a loop quietly doing findings looks identical to a loop choosing them. If `$ARGUMENTS` names a row, that row only. `scripts/reef-queue.py check` must pass first (orphan task files, duplicate ids, word ceilings).

## 2. Per ready row, in parallel where they do not collide (up to `graph.parallel`)
1. `/reef-plan <row>`: the task files are the spec, pushed before any code; `blocked-by`, `resources:`, `tier:` declared; ONE batched question set for everything that is the human's (approval, Design-tier Decisions, branch placement). `/reef-plan-review`.
2. `/reef-task <feature>`: the task graph, every ready task at once, each in its worktree; caps per task; the adversarial passes on `tier: design`.
3. `/reef-review <feature>`: PR into `branches.base`; acceptance; diff review (`code-excellence` as a subagent when the review-toolkit is installed — its prompt states "the owner owns this scope — run its declared gates"); `scripts/reef-ci-local.sh` as the feature gate (`ci.feature_gate: local`); one rollup under one cap; after GREEN only a claims-only commit. `merge.by: loop` → merge with `--delete-branch`, only after the agent's FINAL hand-back.
4. **Close in the same breath**, on `branches.base`, as its single writer: `scripts/reef-queue.py adr-number` (drafts numbered), the row and its footnotes moved to `docs/queue-archive.md`, the journal entry (rounds used, what was verified and how, what was not), the worktrees removed. Hold pushes to `branches.base` while a release PR's CI runs.
5. Back to step 1: the merge may have unblocked rows. End every reply with `in flight: … / waiting on: …`.

## 3. Stops — and only these
A decision that is the owner's (personal data leaving the system, a commercial claim, the look of his product, money, a rule change) — collected, not asked one at a time; a missing credential or quota; a spec found wrong (amend, push, resume); the cap (`caps.attempts`) on an item — blocker into the journal, the item parked, the rest of the loop continues. **The batch is frozen**: a finding goes to the next batch as a `found` row unless it loses a person's data, exposes a secret or personal data in merged code, or breaks the core journey — then it enters with its ground in `Admitted`, journaled.

## 4. The owner's questions — batched, with defaults
At fixed points only — the end of a merge wave, before a release, or when one blocks the critical path — ONE AskUserQuestion: each question 2–4 options, the recommended one first with "(Recommended)", one line of trade-off each. An unanswered question takes its default, except personal data, a commercial claim or a visible change to his product. His words go verbatim into a queue footnote. Design work: a full previewable page of every screen before any build.

## 5. Release
When the batch's rows are merged: the security pass over the batch's combined diff (`code-security`, `roles.security`); `gh pr create --base <branches.release> --head <branches.base>`; CI runs there, once; **the HUMAN merges**. Then rewrite `HANDOFF.md` whole from measured state and ask the human to `/clear` — a fresh orchestrator starts the next batch (a long orchestrator context was ~20% of a measured day's tokens).

## Re-entry
`scripts/reef-queue.py status` + `scripts/reef-graph.py status` + `gh pr list --base <branches.base>` + `git worktree list`. Continue every row from its furthest completed step; never re-plan a row with task files, never re-create a rollup, never reset a cap.
