---
name: reef-review
description: Push the feature branch, create/update the PR, run the ONE review (the spec, the diff, every criterion against its named test in the evidence), then drive the CI or local gate green; merge only when merge.by says the loop merges. Use after reef-task finishes a feature's tasks, or when the user says "/reef-review".
argument-hint: <feature-slug | PR number>
---

# Reef Review — push -> PR -> one review -> CI -> hand off / merge

**Input:** a finished feature (`$ARGUMENTS`: slug or PR number; empty — infer from the current branch, confirm with the human).
**Output:** a validated PR (or reviewed local branch) + a NIT list — handed to the HUMAN, or merged by the loop when `merge.by` is `loop` (step 5).

You are the orchestrator. You never fix code; fixes route back through `/reef-task` on the feature's rollup task under the SAME cap (`scripts/reef-attempt`).

Read `.reef/config.json` first (absent keys take these defaults):
- `branches.base` (default `main`) — the branch feature PRs target. `branches.release` (default `main`) — a PR into it is ALWAYS merged by the human.
- `ci.feature_gate` (default `ci`) — `ci`: watch CI on every PR; `local`: on PRs into `branches.base` run the full local gate instead, CI only for PRs into `branches.release`.
- `merge.by` (default: `loop` when `ci.feature_gate` is `ci` and `branches.base` ≠ `branches.release`, else `human`) — `human`: the human merges every PR; `loop`: the loop merges feature PRs into `branches.base`, the human still merges releases (`reef-plan-check.py` refuses `loop` when base == release).

## 0. Preconditions
The feature's files are at `<paths.features>/<slug>/` (`SPEC.md`, `tasks/`, `tasks/done/`, `adr/`; `paths.features` default `reef/features`) in the feature worktree `<worktree.dir>/<slug>` — read them there, search for nothing. Every task is in `tasks/done/` and `scripts/reef-gate.sh full` is green locally; if not, stop and say which task is pending or blocked.

## One rollup, one cap
A rollup gets no hunter plan pass, whatever its tier: the feature's guard pass (4b) reads its diff before GREEN. Every finding from steps 2 and 4 goes on ONE rollup per feature, `tasks/R<NN>-<feature>.md` (template frontmatter, `id: R<NN>`, `feature:` this feature, `complexity` judged fresh). Every round that sends work back is recorded with `scripts/reef-attempt <rollup> "<findings>"`, so `attempts:` counts review and CI rounds TOGETHER against `caps.attempts` (default 3) — never a cap per step, never `--cap`. `reef-attempt` and the guard refuse a second rollup for the feature (it would reset the counter). A rollup already in `tasks/done/`: `git mv` it back to `tasks/`, set `status: pending`, and append the new scope to Scope under a dated `## Round N` line — `attempts:` carries over. At the cap: USER ACTION REQUIRED, stop.

## A GREEN stage is over
After GREEN from any step, the only commit before the next step is claims-only: `scripts/reef-claims.py claims-only <green-sha>..HEAD` exits 0 (docs, comments, blank lines). A code should-fix after GREEN is the reviewer's BLOCKER (the rollup, under the cap) or a new queue row — never a fourth round. A re-review attacks the last round's fix first.

## 1. Push + PR
`git push -u origin <branch>`; with `gh` and a remote, `gh pr create --fill --base <branches.base>` (or `gh pr view` when it exists — update, never duplicate). No remote: skip the PR steps, say so, review locally.

**Records (0.6).** A verdict is a RECORD bound to the forge's commit — after the review, always record it: `${CLAUDE_PLUGIN_ROOT}/scripts/reef-record <feature> GREEN --report <the reviewer's report, copied to .reef/ci-local/review-<feature>-<sha12>.md>` (or `FAIL`) reads the PR head from `gh`, refuses a report that does not name that head or says FAIL, and writes `.reef/review/<feature>.json`. Under `merge.by: loop` the guard refuses `gh pr merge` unless a GREEN record names the PR's current head (a clean base merge, one that leaves the feature's change identical, or a claims-only commit carries it over; anything else is a fresh review and report, never a re-record); under `merge.by: human` it is the journal's evidence. Never write that file by hand.

## 2. The review — ONE reviewer (v3): the spec, the diff, the evidence
First the mechanical half: `scripts/reef-converge <feature>` runs every Proof row against the branch (headless: a runner job from the row's worktree, `python3 scripts/reef-run.py job converge-<row> -- sh -c 'cd <worktree> && python3 scripts/reef-converge <feature>'`, then end the turn — /reef-loop § Long work; from the base checkout it exits 2). `missing` and `contradicts` go on the rollup; `Converged` = every proof holds. Then dispatch `reef:acceptance` (model `roles.reviewer`) with the PR head's 12 hex, the feature folder and a scratchpad report path: a fresh-context review against `SPEC.md` (its FR/SC keys, not the conversation), the diff against the base, every criterion against its named test in the evidence; `unrequested` work is its finding.
- It walks the user-visible behaviour end to end on the actual entry point: "would the human who wrote the spec accept this?" — gaps as concrete product issues.
- A diff over `review.split_lines` (default 4000 changed lines), or refused as too large: split by TASK (each `Closes-task:` commit range, plus one part for the base's merges), never by file.
- Read its report through `python3 scripts/reef-claims.py verdict <report>` (it opens with `HEAD: <PR head sha12>`, ends with `VERDICT: GREEN|FAIL`). Issues → `${CLAUDE_PLUGIN_ROOT}/scripts/reef-record <feature> FAIL --report <copy>`, the rollup → `/reef-task` → this step again. Passed → `${CLAUDE_PLUGIN_ROOT}/scripts/reef-record <feature> GREEN --report <copy>`.
- **What blocks (0.6):** a regression, an outside-actor code-execution or approval bypass, a correctness bug, a failed acceptance criterion. Everything else (style, naming, a missing comment, an out-of-scope touch, a weak-but-passing test) is a NIT: listed for the human, never a round. A real finding that is not this feature's is a found row, `scripts/reef-queue.py add-row --item … --source found` on `branches.base`; one that may never happen and touches no security, privacy, money or data loss is a note, `scripts/reef-queue.py note "…" --row <row>`.

## 4. CI or local gate (skip CI without CI or a remote)
- A PR into `branches.release`, or `ci.feature_gate` = `ci`: never park on `gh pr checks --watch` / `gh run watch` (the guard denies them for every sub-agent) — poll `gh pr checks` from a Monitor or a scheduled wake-up and keep dispatching other work. Red CI: read the failing block through `scripts/reef-gate.sh --failures` or in the CI log.
- `ci.feature_gate` = `local` and the PR targets `branches.base` (≠ `branches.release`): `scripts/reef-gate.sh full` in the feature worktree is this step; do not wait on CI.
Red → `scripts/reef-attempt <rollup> "<failing output>"`, `/reef-task`, push, re-check — the same rollup and cap as step 2.

## 4b. The critical path: the guard pass and security, once per feature
When `hunter.guard_pass` is `feature` and the feature is on the critical path (`python3 scripts/reef-tier.py path <its task files>`: a task of tier `design` or `critical` (its `tier:`, not its `complexity:`); a risk touch forces one; the record is per such task), the hunter's guard pass ran on no task and runs ONCE here, before the GREEN record: a fresh `loophole-hunter` (model from the heaviest task's tier table), the prompt starting with `REEF-TASK: <that task's file>` and `REEF-FEATURE: <slug>`, `pass=guard` on `git diff <branches.base>...HEAD` in the feature worktree (read-only, snapshot-checked). Its PASS: `scripts/reef-adversarial --feature <slug> guard <report>` (every design/critical task takes the record; `reef-record … GREEN` refuses while one lacks it); a BLOCKER → the rollup → `/reef-task` → again. The same condition — the critical path — dispatches `reef:security` (model `roles.security`) on that feature diff before the GREEN record, its report read through `reef-claims.py verdict`, a FAIL → the rollup; `review.security_per_item: off` in `.reef/config.json` opts a project out. The fast path gets neither: the one reviewer, CI and the release pass are its net.

## 5. Hand off — or merge
Report: PR URL (or branch), the verdict, blockers fixed, NITs left, CI/gate state. The runlog rows go in at the row's close, on the base (`reef-queue.py journal <slug>`), never on the feature branch. When the feature added dependencies, run `worktree.setup` in the MAIN checkout right after the merge, before the close-out commit.
- `merge.by` = `human`: the HUMAN merges — never you.
- `merge.by` = `loop`: only when the PR's base is `branches.base`, acceptance passed, no BLOCKER is open, and step 4 is green on a head containing the base's tip (`scripts/reef-merge-base` in the feature worktree, push) — merge **through `gh pr merge`** (`--squash --delete-branch`, or the repository's configured merge method), never a local `git merge`+push: only that path has the guard check the GREEN record, the base's tip and the green evidence. A PR into `branches.release` is never the loop's: the release merge stays the human's.
- Run it as one bare command, `gh pr merge <n> --squash --delete-branch`: no `cd`, no pipe, nothing chained; read the result with `gh pr view <n> --json state,mergeCommit` in its own call. Under auto mode the owner authorizes loop merges once with `Bash(gh pr merge *)` in the project's `.claude/settings.local.json` (it matches only a bare command; the GREEN record stays the gate). A merge still refused waits for the owner with the command, never another route.

## Re-entry
The tick (`python3 scripts/reef-loop.py tick`) lists the PR to review and the returned-but-unmerged work; the rollup (`R*.md` in `tasks/` or `done/`) holds the rounds so far. CONTINUE from the furthest completed step — never restart from 0, never a second rollup.
