# Queue — {{name}}

One row per unit of work. **This file holds the work, not the record**: a row that closes moves whole to `queue-archive.md` beside this file. There is **no status column** — status is read from the row's task files (`python3 scripts/reef-queue.py status`), so a fact has one home. The owner's decisions are footnotes, in his words, numbered in one sequence across this file and the archive.

Current batch: 1

## Rules of the loop
1. Take the top row of the current batch with no unmet dependency: on issues the owner's priority label first (`p1`, then none or `p2`, then `p3`; a `p1` found row counts as planned), then a `planned` row before a `found` one. If no planned row is unblocked, stop and escalate — do not fall through to found work.
2. This file lives on `{{base}}` only (rows found while planning or building are committed there, never on a feature branch); `/reef-plan` writes the task files (the spec) on `feat/<slug>` and pushes them **before** any code; `/reef-plan-review`; `/reef-task` runs the graph; `/reef-review` opens the PR into `{{base}}`. Never `{{release}}`.
3. Fix rounds per item: `.reef/config.json` `caps.attempts`, across review, verification and CI together. At the cap: blocker into `{{journal_path}}`, escalate. After a GREEN verdict: a claims-only commit, a BLOCKER, or a new row — never a fourth round.
4. Decisions that close an alternative: a project-wide one as `{{adr_path}}/draft-<row>-<slug>.md`, a feature's own under its folder's `adr/`; unnumbered; the number is allocated on `{{base}}` at merge (two branches that each "checked first" take the same number).
5. Merge with `--delete-branch`, then close in the same breath: row → archive with its footnotes, draft ADR numbered, journal entry, worktree removed.
6. **The batch boundary is fixed** (constitution). Found work enters the next batch, with `Source: found` and the batch it entered; the fix-now exception is journaled with its ground.
7. A `found` row untouched after two batches is re-triaged: promoted once with a stated reason, merged into a design row, or deleted. Deletion is a first-class outcome. `python3 scripts/reef-queue.py triage` lists them as the owner's one question; `set-batch` and `drop-row --reason` carry his answer out.
8. Three findings in one module is one design row, not a third patch.
9. At most two open PRs into `{{base}}`.
10. Promotion to `{{release}}` is a pull request from `{{base}}`, after the batch's security pass; CI runs there; the owner merges it. Hold pushes to `{{base}}` while that PR's CI runs.
11. The owner's decisions are batched (AGENTS.md, "Owner decision points"); each answer is a footnote here, verbatim.

## Columns
`Id` (row × 100 + n reserves task ids: row 12 → tasks 1201, 1202) · `Item` (one line) · `Depends` (row ids) · `Source` (planned / found) · `Batch` (the batch the row entered) · `Admitted` (non-empty only for a found row admitted into a running batch, with its ground).

## Batch 1

| Id | Item | Depends | Source | Batch | Admitted |
|---|---|---|---|---|---|
| 1 | {{first_row}} | | planned | 1 | |

## Footnotes
{{footnotes}}
