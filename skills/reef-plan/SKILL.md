---
name: reef-plan
description: Turn a raw feature spec into an approved set of vertical-slice task files via grilling and ONE human gate. Use when the user has a feature to plan, or says "/reef-plan".
argument-hint: <feature spec | path/to/spec.md>
---

# Reef Plan — spec -> approved tasks

**Input:** a raw feature spec (`$ARGUMENTS`: free-form text, a path, or empty — if empty, ask the human for one and stop until they answer).
**Output:** approved task files on a feature branch + optional ADR/glossary additions — exactly what `/reef-task` consumes. Nothing else.

You are the orchestrator: grill, draft, gate, write. You do not implement. Read `.reef/config.json` for paths.

## 1. Grill
One question at a time, each with a recommended answer. Only ask what the codebase cannot answer (explore first). Stop when scope, edge cases, non-goals, and ADR-worthy decisions are clear.

## 1b. The feature folder and its SPEC (0.6)
One feature = one queue row = one folder `<paths.features>/<feature-slug>/` (default `reef/features`; a 0.5 project keeps flat `tasks/` until `--layout`). The slug is 2–5 descriptive kebab-case words (`csv-export-for-orders`), never a number or a generic word (`reef-queue.py check` refuses it). Write `SPEC.md` from `${CLAUDE_PLUGIN_ROOT}/templates/spec.md` first: `Row: <id>`, the grill as Q/A, scope, non-goals, `## Already shipped` (grep the repository for the row's nouns, search merged PRs for the row id; `none` is an answer), requirements `FR-n` each tagged `[infra|data|backend|frontend]`, success criteria `SC-n`, owner decisions, `## Architecture impact`. Child specs `specs/<part>.md` (`Parent: FR-n`) only for a big feature; the feature's ADR under `adr/` (one by default, `## Diagram` in Mermaid); tasks under `tasks/`. Nothing else goes in the folder. An existing constitution or spec directory (`.specify/`, `specs/*/spec.md`) is read as input and its keys carried; it is never duplicated.

## 2. Draft (nothing written to disk)
Split into vertical slices:
- A slice goes ALL THE WAY THROUGH: it touches every layer its behavior needs (schema to output), thin but end-to-end — never "the database part" alone.
- Done means showable: you can run the slice and point at what changed.
- Sized for one clean context: if an agent needs to be reminded mid-way, the slice is too big.
- THE RULE: **no failing test = no task** — every task names the test that would be red before work starts; if you can't, merge or delete the slice.
  - Good: "004 skip-and-warn — red test: bad row currently raises a traceback."
  - Bad: "003 multi-month — grouping already works, task adds a blank line." (This exact padding shipped in the pilot and cost a full round-trip.)
- Wide mechanical refactors are the exception: expand -> migrate-in-batches -> contract, each batch its own task.
Per task, draft the full file from `${CLAUDE_PLUGIN_ROOT}/templates/task.md` (schema: `${CLAUDE_PLUGIN_ROOT}/schemas/task.schema.json`):
- Criteria (0.6 shape): `AC-n (FR-m)` is ONE declarative sentence under 50 words citing the keys it delivers, no test name, no command; the `## Proof` table maps each `AC-n` to its test name or a command that exits 0 iff it holds. Sentences everywhere under 25 words (`writing.sentence_words`). A feature over `plan.max_tasks` (12) is split into dependent queue rows, each with its own folder.
- `touches:` names the risk classes (`pii`, `money`, `auth` force `critical`; `migration` forces at least `design` and a `Rollback:` line in `## Decision`).
- `complexity`: mech = a junior copies an existing example without one question; design = two people would produce materially different solutions.
- `tier`: light (mech only: allowlisted paths, no privacy/money/auth/data path, no migration, no ADR) / full (default) / design (replaces a mechanism that failed twice, or touches privacy, money or a guard — the `loophole-hunter` runs on the plan before code and on the finished guard after). `scripts/reef-plan-check.py` refuses a tier that does not match the complexity.
- `verify`: design -> judge; mech -> gate-only.
- `blocked-by`: only REAL edges — the graph runs every task whose edges are done in parallel, so a decorative edge costs wall-clock, and a missing one lets two tasks collide.
- `resources`: every shared thing the task holds while running — a fixed port (`port:3000`), the database (`db`), the one browser, `heavy` for a full suite or build; the scheduler serialises them (slots in `.reef/config.json`). Name it or two tasks will hold it at once.
- Effort above medium must be argued for in the plan.
Also draft: glossary additions, and at most ONE ADR (Nygard: Status/Context/Decision/Consequences) for the whole feature if it has non-obvious decisions. In a parallel loop, where ADR numbers would collide across branches, write it as `docs/adr/draft-<item>-<slug>.md` and number it at merge — reef-plan-check exempts `draft-*.md` from the "no Proposed ADR" rule (a placeholder or missing Status still fails).

## 3. Explain-back (design tasks)
For each `tier: design` task the HUMAN writes the `## Decision` section in their own words — grill them to sharpen it; never write it for them. For other `design` tasks the orchestrator may draft it, marked `decided by: agent` on its first line, and it joins the question set at the gate. A design task with an empty Decision cannot be dispatched.

## 3.5 Quiz the human on the breakdown
Before the gate, show the numbered task list (title / blocked-by / what it delivers) and ask: does the granularity feel right (too coarse / too fine)? are the blocking edges real? merge or split anything? Iterate until they're satisfied — this is cheaper than discovering a wrong-shaped plan after the branch exists.

## 3.6 Adversarial pass on the plan (tier: design only)
Before the gate, spawn the `loophole-hunter` agent on the drafted plan: "how can every check be green while the defect happens?" Record its verdict with `scripts/reef-adversarial <task-file> plan <report>`; a BLOCKER is fixed in the draft before the gate. The guard refuses to dispatch a `tier: design` task without this record.

## 4. HUMAN GATE (one, blocking — batched)
Show every task in full (scope, ACs, out-of-scope, resources, tier). Write the drafted task files and ADRs to disk first (the plan is what is on disk, not what is in the chat), run `scripts/reef-plan-check.py --digest --feature <slug>` and take the first 16 hex of the digest. ONE question set (AskUserQuestion) holding everything that is the human's, its first question with EXACTLY this text — `Approve plan <slug> at <digest16>?` — and the options `Approve` / `Edit` / `Cancel` (header `Plan`), plus the Design-tier Decisions and where the branch lives (worktree vs current tree), each with a recommended default. Never one question at a time. The approval is a RECORD, not a sentence: the PostToolUse hook (`scripts/reef-approval.py`) writes `.reef/approvals/<slug>.json` only when that exact question is answered `Approve` with the current digest — a timeout, an `Edit`, a hand-written file (the guard denies it) or an edit of the plan afterwards approves nothing, and the guard refuses the first dispatch. After Approve: glossary, ADR (drafts: `draft-<slug>.md`, `Status: Accepted (number at merge)`); create `feat/<slug>` branch. On Edit: change the files, recompute the digest, ask again.

## Re-entry
The tick (`python3 scripts/reef-loop.py tick`) names the row; if its feature folder (or `tasks/NNN-*.md` matching the slug) already exists, do not re-plan from zero — show the existing plan, ask whether to extend, edit, or abandon it. Never overwrite an approved plan silently.
