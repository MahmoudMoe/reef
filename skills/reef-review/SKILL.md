---
name: reef-review
description: Push the feature branch, create/update the PR, run acceptance + diff review, then drive the CI or local gate green; merge only when merge.by says the loop merges. Use after reef-task finishes a feature's tasks, or when the user says "/reef-review".
argument-hint: <feature-slug | PR number>
---

# Reef Review — push -> PR -> acceptance -> diff review -> CI -> hand off / merge

**Input:** a finished feature (`$ARGUMENTS`: slug or PR number; empty — infer from the current branch, confirm with the human).
**Output:** a validated PR (or reviewed local branch) + a NIT list — handed to the HUMAN to merge, or merged by the loop when `merge.by` is `loop` (step 5).

You are the orchestrator. You never fix code yourself; fixes route back through `/reef-task` on the feature's rollup task under the SAME cap machinery (`scripts/reef-attempt`).

Read `.reef/config.json` first (absent keys take these defaults — today's behaviour):
- `branches.base` (default `main`) — the branch feature PRs target (the integration branch in a parallel loop).
- `branches.release` (default `main`) — the release branch; a PR into it is ALWAYS merged by the human.
- `ci.feature_gate` (default `ci`) — `ci`: watch CI on every PR; `local`: on PRs into `branches.base` run the full local gate instead, and watch CI only for PRs into `branches.release`.
- `merge.by` (default `human`) — `human`: the human merges every PR; `loop`: the loop merges feature PRs into `branches.base`, the human still merges releases into `branches.release`. `scripts/reef-plan-check.py` refuses `loop` when `branches.base` == `branches.release`.

## 0. Preconditions
All the feature's tasks are in `tasks/done/` and the full gate is green locally (`scripts/reef-gate.sh full`). If not, stop and say which task is pending/blocked.

## One rollup, one cap
Every finding from steps 2, 3 and 4 goes on ONE rollup task file per feature: `tasks/R<NN>-<feature>.md` (template frontmatter, `id: R<NN>`, `feature:` = this feature, `complexity` judged fresh). Every round that sends work back is recorded on that file with `scripts/reef-attempt <rollup> "<findings>"`, so `attempts:` counts acceptance, diff and CI rounds TOGETHER against the one cap (`caps.attempts`, default 3) — never a separate cap per step, never `--cap` to raise it. `reef-attempt` and the dispatch guard both refuse a second rollup file for the same feature: a fresh file would reset the counter and launder the cap. If the rollup already sits in `tasks/done/` from an earlier round, `git mv` it back to `tasks/`, set `status: pending`, append the new scope under a dated `## Round N` line in Scope — `attempts:` carries over. At the cap: USER ACTION REQUIRED, stop.

## 1. Push + PR
`git push -u origin <branch>`. If `gh` is available and a remote exists: `gh pr create --fill --base <branches.base>` (or `gh pr view` if it exists — update, don't duplicate). No remote → skip PR steps, say so, and continue with local review.

## 2. Acceptance review (whole feature, user's perspective)
Fresh-context review of the feature against the ORIGINAL grilled spec (not the task files — tasks can drift from intent):
- Walk the user-visible behavior end to end; run the actual entry point.
- Question: "would the human who wrote the spec accept this?" List gaps as concrete product issues.
- Issues found → the feature's rollup (above) → `/reef-task` → re-run this step.

## 3. Diff review
Fresh-context, diff-only against the PR's base (`git diff <branches.base>...HEAD`): dead code, duplication, missing coverage, doc gaps, glossary nouns not in the glossary, perf on hot paths only (never micro-optimize one-off code). Tag each item BLOCKER or NIT.
- BLOCKERs → the feature's rollup → `/reef-task` → re-review. NITs → list them for the human, don't loop on them.

## 4. CI or local gate (skip CI if no CI/remote)
- PR into `branches.release`, or `ci.feature_gate` = `ci`: `gh pr checks --watch` (or `gh run watch`). Red CI → read the actual failing log (never guess from the test name).
- `ci.feature_gate` = `local` and the PR targets `branches.base` (≠ `branches.release`): run `scripts/reef-gate.sh full` in the feature's worktree as this step; do not wait on CI.
Red → record it on the feature's rollup with `scripts/reef-attempt <rollup> "<failing output>"`, `/reef-task` it, push, re-check. Same rollup, same cap as steps 2–3.

## 5. Hand off — or merge
Report: PR URL (or local branch), acceptance verdict, blockers fixed, NITs left, CI/gate state. Append the runlog row.
- `merge.by` = `human` (default): the HUMAN merges — never merge yourself.
- `merge.by` = `loop`: only when the PR's base is `branches.base` AND acceptance passed, no BLOCKER is open, and step 4 is green — merge it (`gh pr merge --squash --delete-branch`, or the repository's configured method). A PR whose base is `branches.release` is never merged by the loop: the release merge stays the human's.

## Re-entry
Invoked again after an interruption: read `git status`, `gh pr view`, the feature's rollup (`tasks/R*.md`, or in `done/`), and CONTINUE from the furthest completed step — never restart from 0 and never create a second rollup.
