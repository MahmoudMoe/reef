---
name: reef-assess
description: Day zero for an EXISTING project — understand it (how it works, how it was written, how it was pushed, what documents exist; every claim with a proving path), score how well a harness can hold it, then recalibrate its documents into Reef's one tree under ONE batched approval, archiving and never deleting. Use after /reef-init on an existing repository, or when the user says "/reef-assess".
argument-hint: <empty | areas to read first>
---

# Reef Assess — understand, then recalibrate

Sub-agents here run on the `critical` tier table (`tiers.critical.roles`); the main session is the owner's model. Nothing moves before the owner approves the plan.

## 1. Understand — four observed sections, every claim with a proving path
Use `/reef-explore` (one message, N `Explore` agents, each with a file budget, cheapest sources first: configs, CI, lockfiles, `git log --stat`; code samples per directory second) on these questions, then write the answers as **Observed** (file:line or command) or **Inferred**:
- **How it works** → `reef/architecture/architecture.md`: entry points, runtime, build, data stores, external services, environment variables. Feeds `scripts/reef-c4.py` and `gates.full`.
- **How it was written** → `reef/architecture/conventions.md`: lint and formatter config, type strictness, test framework and style, error handling, logging, naming, module layout. This is the input to the constitution — written from existing reality, never from the template alone — and to the glossary.
- **How it was pushed** → `python3 scripts/reef-recalibrate history` (mechanical: branches, commit convention share, merge style, tags, CI triggers) → `branches.*`, `ci.*`, `merge.by` and the commit-format expectation in `.reef/config.json` are derived from the history, not assumed.
- **Documents and structure** → every document and decision record in any format classified decision / spec / runbook / stale / duplicate (the plan below does this mechanically), plus the folder tree with what each directory holds.

Then the five-dimension harnessability score into `reef/day-zero.md`: type safety, module boundaries, framework opinionation, test signal, lint baseline — `high` 5/5, `moderate` 3–4, `low` ≤ 2 (or none + weak). On `low`, set `tiers.light.allow` to `[]` in `.reef/config.json`: nothing is light until the baseline exists.

## 2. Recalibrate — Reef's structure only, old documents archived
1. `python3 scripts/reef-recalibrate plan` writes `reef/recalibration.md`: every document with create / convert / move / keep and a reason per line; `keep` for README, LICENSE, CONTRIBUTING, SECURITY, CHANGELOG, CODEOWNERS, docs a docs build serves, anything referenced from code or CI.
2. ONE AskUserQuestion: approve all / edit the list / cancel (recommended first). An edit changes the `action` column of `.reef/recalibration.json`; a `keep` line moves only when the owner changes it. Nothing moves before the answer.
3. `python3 scripts/reef-recalibrate --apply` — one commit: the layout written where absent, decision records converted to ADRs with `Supersedes:` (a feature's decision lands in its folder's `adr/` when a feature folder exists for it, a project-wide one under `reef/architecture/adr/`), specs for open work turned into feature folders with keys and a queue row, glossary terms merged, everything else `git mv`-ed to `reef/archive/<date>/<original path>` with `reef/archive/README.md` as the index, relative links rewritten, the apply refused and the tree restored on a broken link. A Reef-style `README.md` is proposed under `.reef/proposed/`, never written over the owner's. Undo: `git revert` of that commit. Deleting `reef/archive/` is a later queue row.
4. `python3 scripts/reef-structure --check` passes afterwards and joins `gates.extra` (`"structure"`), so a process document cannot drift back outside the layout.

## 3. Hand off
`reef/day-zero.md` lists what is still open; the first queue row is a walking skeleton or the smallest open spec; `/reef-loop` from there. End with `in flight: … / waiting on: …`.
