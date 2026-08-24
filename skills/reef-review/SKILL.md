---
name: reef-review
description: Push the feature branch, create/update the PR, run acceptance + diff review, then drive CI green. Use after reef-task finishes a feature's tasks, or when the user says "/reef-review".
argument-hint: <feature-slug | PR number>
---

# Reef Review — push -> PR -> acceptance -> diff review -> CI

**Input:** a finished feature (`$ARGUMENTS`: slug or PR number; empty — infer from the current branch, confirm with the human).
**Output:** a validated PR (or reviewed local branch) ready for the HUMAN to merge + a NIT list. Never merges.

You are the orchestrator. You never fix code yourself; fixes route back through `/reef-task` as rollup tasks under the SAME cap machinery (`scripts/reef-attempt` on a rollup task file).

## 0. Preconditions
All the feature's tasks are in `tasks/done/` and the gate is green locally. If not, stop and say which task is pending/blocked.

## 1. Push + PR
`git push -u origin <branch>`. If `gh` is available and a remote exists: `gh pr create --fill` (or `gh pr view` if it exists — update, don't duplicate). No remote → skip PR steps, say so, and continue with local review.

## 2. Acceptance review (whole feature, user's perspective) — cap 3
Fresh-context review of the feature against the ORIGINAL grilled spec (not the task files — tasks can drift from intent):
- Walk the user-visible behavior end to end; run the actual entry point.
- Question: "would the human who wrote the spec accept this?" List gaps as concrete product issues.
- Issues found → bundle into ONE rollup task file (`tasks/R<NN>-<slug>.md`, template frontmatter with `id: R<NN>`, `complexity` judged fresh) → hand to `/reef-task` → re-run this step. THE SAME rollup file carries the whole loop — record every round's failure on it via `scripts/reef-attempt` so `attempts:` accumulates; a fresh file per round would reset the counter and launder the cap. 3 acceptance rounds max, then USER ACTION REQUIRED.

## 3. Diff review — cap 3
Fresh-context, diff-only (`git diff main...HEAD`): dead code, duplication, missing coverage, doc gaps, glossary nouns not in the glossary, perf on hot paths only (never micro-optimize one-off code). Tag each item BLOCKER or NIT.
- BLOCKERs → one rollup task → `/reef-task` → re-review. NITs → list them for the human, don't loop on them.

## 4. CI — cap 5 (skip if no CI/remote)
`gh run watch` (or `gh pr checks --watch`). Red CI → read the actual failing log (never guess from the test name), record it on the CI rollup task with `scripts/reef-attempt --cap 5 <rollup>` (the flag exists because this loop's cap is 5, not the default 3), `/reef-task` it, push, re-watch. Same rollup file across all rounds.

## 5. Hand off
Report: PR URL (or local branch), acceptance verdict, blockers fixed, NITs left, CI state. The HUMAN merges — never merge yourself. Append the runlog row.

## Re-entry
Invoked again after an interruption: read `git status`, `gh pr view`, open rollup tasks (`tasks/R*.md` not in done/), and CONTINUE from the furthest completed step — never restart from 0 and never re-create an existing rollup.
