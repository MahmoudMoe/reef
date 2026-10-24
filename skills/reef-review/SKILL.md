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
The feature's files are at `<paths.features>/<slug>/` (`SPEC.md`, `tasks/`, `tasks/done/`, `adr/`; `paths.features` from `.reef/config.json`, default `reef/features`) in the feature worktree `<worktree.dir>/<slug>` — read them there, search for nothing (2026-10-18: every review start ran `find` over the repository for files whose path the config states). All the feature's tasks are in `tasks/done/` and the full gate is green locally (`scripts/reef-gate.sh full`). If not, stop and say which task is pending/blocked.

## One rollup, one cap
A rollup gets no hunter plan pass, whatever its tier: the feature's guard pass (4b) reads its diff before GREEN. Every finding from steps 2, 3 and 4 goes on ONE rollup task file per feature: `tasks/R<NN>-<feature>.md` (template frontmatter, `id: R<NN>`, `feature:` = this feature, `complexity` judged fresh). Every round that sends work back is recorded on that file with `scripts/reef-attempt <rollup> "<findings>"`, so `attempts:` counts acceptance, diff and CI rounds TOGETHER against the one cap (`caps.attempts`, default 3) — never a separate cap per step, never `--cap` to raise it. `reef-attempt` and the dispatch guard both refuse a second rollup file for the same feature: a fresh file would reset the counter and launder the cap. If the rollup already sits in `tasks/done/` from an earlier round, `git mv` it back to `tasks/`, set `status: pending`, append the new scope under a dated `## Round N` line in Scope — `attempts:` carries over. At the cap: USER ACTION REQUIRED, stop.

## A GREEN stage is over
After a GREEN verdict from any step below, the only commit allowed before the next step is one claims-only commit: `scripts/reef-claims.py claims-only <green-sha>..HEAD` must exit 0 (docs, comments, blank lines — nothing else). A code should-fix after GREEN is either the reviewer's BLOCKER (it goes on the rollup, under the cap) or a new queue row — never a fourth round. Measured: 44% of the pilot's fix rounds came after GREEN. The reviewer of a re-review attacks the last round's fix first.

## 1. Push + PR
`git push -u origin <branch>`. If `gh` is available and a remote exists: `gh pr create --fill --base <branches.base>` (or `gh pr view` if it exists — update, don't duplicate). No remote → skip PR steps, say so, and continue with local review.

**Records (0.6).** A verdict is a RECORD bound to the forge's commit, not a sentence in the chat: after the acceptance review and after the diff review run `scripts/reef-record <feature> GREEN --report <the reviewer's report, copied to .reef/ci-local/review-<feature>-<sha12>.md>` (or `FAIL`), which reads the PR head from `gh`, refuses a report that does not name that head or says FAIL, and writes `.reef/review/<feature>.json`. Under `merge.by: loop` the guard refuses `gh pr merge` unless a GREEN record names the PR's current head (a clean base merge, a base merge that leaves the feature's own change identical, or a claims-only commit on top is the carry-over; anything else is a fresh review and a new report, never a re-record); under `merge.by: human` the record is the journal's evidence and gates nothing. Never write that file by hand (the guard denies it).

## 2. Acceptance review (whole feature, user's perspective)
First the mechanical half: `scripts/reef-converge <feature>` executes every Proof row against the branch — `missing` and `contradicts` land on the rollup under the cap; `Converged` means every proof holds. Then dispatch `reef:acceptance` (model `roles.reviewer`) with the PR head's 12 hex and a scratchpad report path: the fresh-context review of the feature against its `SPEC.md` (the intent, FR/SC keys — not the task files, which can drift, and not the conversation); `unrequested` work is this review's finding against the spec:
- Walk the user-visible behavior end to end; run the actual entry point.
- Question: "would the human who wrote the spec accept this?" List gaps as concrete product issues.
- Read the reviewer's report through `python3 scripts/reef-claims.py verdict <report>` (verdict, blockers, failed criteria, new rows, notes). Issues found → the feature's rollup (above) → `/reef-task` → re-run this step. Passed → `scripts/reef-record <feature> GREEN --report <copy>`; the reviewer's report opens with `HEAD: <PR head sha12>` and ends with `VERDICT: GREEN|FAIL`.
- **What blocks (0.6):** a BLOCKER is only one of four kinds — a regression, an outside-actor code-execution or approval bypass, a correctness bug, or a failed acceptance criterion. Everything else (style, naming, a missing comment, an out-of-scope touch, a weak-but-passing test) is a NIT and never starts a round.

## 3. Diff review — only when `review.diff_review` is `on` (default `off`)
Off by default (0.7, 2026-10-18: one feature review ran six diff reviewers over code the verifier and the hunter had judged; the acceptance review above is the review that answers the spec). When `on`: fresh-context, diff-only against the PR's base (`git diff <branches.base>...HEAD`): dead code, duplication, missing coverage, doc gaps, glossary nouns not in the glossary, perf on hot paths only (never micro-optimize one-off code). Tag each item BLOCKER or NIT. ONE reviewer over the whole diff by default; when it is over `review.split_lines` (default 1500 changed lines) or the reviewer refuses it as too large, split it by TASK (each `Closes-task:` commit range, plus one part for the merge commits from the base) and run the parts in parallel — never by file, and never a part without the task file it implements (first contact: a 2300-line diff was refused whole and split ad hoc).
- BLOCKERs (the four kinds above, nothing else) → the feature's rollup → `/reef-task` → re-review. NITs → list them for the human, don't loop on them. A finding that is real but not this feature's becomes a found row: `scripts/reef-queue.py add-row --item … --source found` on `branches.base`; one that may never happen, touching no security, privacy, money or data loss, a note: `scripts/reef-queue.py note "…" --row <row>`. Passed → `scripts/reef-record <feature> GREEN --report <copy>`.

## 4. CI or local gate (skip CI if no CI/remote)
- PR into `branches.release`, or `ci.feature_gate` = `ci`: never park on `gh pr checks --watch` / `gh run watch` (the guard denies them for every sub-agent): poll `gh pr checks` from a Monitor or a scheduled wake-up and keep dispatching other ready work meanwhile. Red CI → read the actual failing log through `scripts/reef-gate.sh --failures` / the CI log's failing block (never guess from the test name, never paste the whole log).
- `ci.feature_gate` = `local` and the PR targets `branches.base` (≠ `branches.release`): run `scripts/reef-gate.sh full` in the feature's worktree as this step; do not wait on CI.
Red → record it on the feature's rollup with `scripts/reef-attempt <rollup> "<failing output>"`, `/reef-task` it, push, re-check. Same rollup, same cap as steps 2–3.

## 4b. The feature's guard pass (`hunter.guard_pass: feature`)
When `.reef/config.json` sets `hunter.guard_pass` to `feature` and the feature has a task of tier `design` or `critical` (its `tier:`, not its `complexity:`), the loophole-hunter's guard pass ran on NO task; it runs ONCE here, before the GREEN record: a fresh `loophole-hunter` (model from the heaviest task's tier table), prompt starting with `REEF-TASK: <that task's file>` and `REEF-FEATURE: <slug>`, `pass=guard` on the whole feature diff (`git diff <branches.base>...HEAD` in the feature worktree, read-only, snapshot-checked). Record its PASS with `scripts/reef-adversarial --feature <slug> guard <report>` (every design/critical task of the feature takes the record; `scripts/reef-record <feature> GREEN` refuses while one lacks it). A BLOCKER → the feature's rollup → `/reef-task` → re-run. Measured 2026-10-18: two judges cost 96k on a 20-line task; the hunter's floor is paid once per feature instead. The same condition — a task of tier `design` or `critical` — dispatches `reef:security` (model `roles.security`) on that feature diff before the GREEN record, its report read through `reef-claims.py verdict`, a FAIL → the rollup; `review.security_per_item: off` in `.reef/config.json` opts a project out. The release pass alone reached ai-coach's access-control and money code once per release, never per change (2026-10-24, item 22).

## 5. Hand off — or merge
Report: PR URL (or local branch), acceptance verdict, blockers fixed, NITs left, CI/gate state. The runlog rows go in at the row's close, on the base (`reef-queue.py journal <slug>`), never on the feature branch. When the feature added dependencies, run `worktree.setup` in the MAIN checkout right after the merge, before the close-out commit — its pre-commit gate runs there (first contact: `pg` missing on develop, the close commit failed until `npm ci`).
- `merge.by` = `human` (default): the HUMAN merges — never merge yourself.
- `merge.by` = `loop`: only when the PR's base is `branches.base` AND acceptance passed, no BLOCKER is open, and step 4 is green — merge it **through `gh pr merge`** (`--squash --delete-branch`, or the repository's configured method), never through a local `git merge`+push: the guard checks the GREEN record against the forge head only on that path. A PR whose base is `branches.release` is never merged by the loop: the release merge stays the human's.
- Run it as one bare command, `gh pr merge <n> --squash --delete-branch`: no `cd` before it, no pipe, nothing chained after; read the result with `gh pr view <n> --json state,mergeCommit` in its own call. Under auto mode the owner authorizes loop merges once with the rule `Bash(gh pr merge *)` in the project's `.claude/settings.local.json`, which matches only a bare command; the GREEN record stays the gate. A merge still refused waits for the owner with the command, never another route.

## Re-entry
Invoked again after an interruption: the tick (`python3 scripts/reef-loop.py tick`) lists the PR to review and the returned-but-unmerged work; the feature's rollup (`R*.md` in its `tasks/`, or in `done/`) holds the rounds so far. CONTINUE from the furthest completed step — never restart from 0 and never create a second rollup.
