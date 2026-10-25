---
name: reef-assess
description: Day zero for an EXISTING project — understand it (how it works, how it was written, how it was pushed, what documents exist; every claim with a proving path), score how well a harness can hold it, then recalibrate its documents into Reef's one tree under ONE batched approval, archiving and never deleting. Use after /reef-init on an existing repository, or when the user says "/reef-assess".
argument-hint: <empty | areas to read first>
---

# Reef Assess — understand, then recalibrate

Sub-agents here run on the `critical` tier table (`tiers.critical.roles`); the main session is the owner's model. Nothing moves before the owner approves the plan.

## 0. Prerequisite — `/reef-init` ran here
`test -f scripts/reef-recalibrate && test -f .reef/config.json` or STOP: "run /reef-init first". This skill runs the project's own `scripts/reef-recalibrate` and `scripts/reef-structure`, which only init installs (ai-coach, 2026-10-24: assess ran first and found neither).

## 1. Understand — four observed sections, every claim with a proving path
Use `/reef-explore` (one message, N `Explore` agents, each with a file budget, cheapest sources first: configs, CI, lockfiles, `git log --stat`; code samples per directory second) on these questions, then write the answers as **Observed** (file:line or command) or **Inferred**:
- **How it works** → `reef/architecture/architecture.md`: entry points, runtime, build, data stores, external services, environment variables. Feeds `scripts/reef-c4.py` and `gates.full`.
- **How it was written** → `reef/architecture/conventions.md`: lint and formatter config, type strictness, test framework and style, error handling, logging, naming, module layout. This is the input to the constitution — written from existing reality, never from the template alone — and to the glossary.
- **How it was pushed** → `python3 scripts/reef-recalibrate history` (mechanical: branches, commit convention share, merge style, tags, CI triggers) → `branches.*`, `ci.*`, `merge.by` and the commit-format expectation in `.reef/config.json` are derived from the history, not assumed.
- **Documents and structure** → every document and decision record in any format classified decision / spec / runbook / stale / duplicate (the plan below does this mechanically), plus the folder tree with what each directory holds.

Then `python3 scripts/reef-recalibrate measure` — counts, not judgments, into `reef/day-zero.md` `## Measured`: the largest product files, product vs test LOC, raw SQL by directory, functions and triggers per migration, the linter, the project's existing guard tests (reuse them before adding a gate) — and the five-dimension harnessability score into `reef/day-zero.md`, module boundaries and lint baseline read from those counts: type safety, module boundaries, framework opinionation, test signal, lint baseline — `high` 5/5, `moderate` 3–4, `low` ≤ 2 (or none + weak). On `low`, set `tiers.light.allow` to `[]` in `.reef/config.json`: nothing is light until the baseline exists.

## 2. Recalibrate — Reef's tree beside the project's documents, which stay in place
1. `python3 scripts/reef-recalibrate plan` writes `reef/recalibration.md`: every document with its action and a reason. The project's documents stay in place (`keep`, with what `plan --move` would do); only the old process converts — the old queue's open rows → Reef rows, a second handoff → `HANDOFF.md`, the old loop's commands archived.
2. Run `python3 scripts/reef-recalibrate plan --measure` first: it applies the plan in a scratch worktree, runs `gates.full` and every check-family command (`check`, `check:*`, `check-*`, from any task runner) there and writes the error and red-test counts into the plan. ONE AskUserQuestion showing those numbers: approve all / edit the list / cancel — recommend the smallest plan with zero errors. Moving a document into Reef's tree is a later queue row (`plan --move`, one folder at a time, after its readers are retired; ai-coach, 2026-10-24: the full move caused 603 errors and 4 red tests). An edit changes the `action` column of `.reef/recalibration.json`. Nothing moves before the answer.
3. `python3 scripts/reef-recalibrate --apply` — one commit: Reef's layout written where absent, the old process converted. Under `plan --move` also: decision records → ADRs in `paths.adr` with `Supersedes:`, open specs → feature folders with a queue row, glossary terms merged, the rest `git mv`-ed to `reef/archive/<date>/` with `reef/archive/README.md` as the index, relative links rewritten, the apply refused and the tree restored on a broken link. A Reef-style `README.md` is proposed under `.git/reef/proposed/`, never written over the owner's. Undo: `git revert` of that commit.
4. `python3 scripts/reef-structure --check` passes afterwards and joins `gates.extra` (`"structure"`), so a process document cannot drift back outside the layout.

## 3. Hand off
The apply's last line is the hand-off: "Reef's tree is complete", or "partial: N documents outside it — rows #a–#b, blocked by …" — never ask to push or merge before that line, and name the holds it printed from the project's own handoff and runbooks (a hold outranks Reef's merge default). The plan refuses while the old loop has work in flight (an unmerged branch its queue names): finish those branches first, or `--apply --park-in-flight`. `reef/day-zero.md` lists what is still open; the first queue row is a walking skeleton or the smallest open spec; `/reef-loop` from there. End with `in flight: … / waiting on: …`.
