# DRAFT — adopting a project that already runs its own loop: who yields, init or assess?

Status: **draft, the owner decides**. Written 2026-10-24 from the first adoption on an existing project (ai-coach, item
11 of that brief). No code changes with this record; the implementation is a later queue row once the choice is made.

## 1. What happened

ai-coach already ran a loop of its own before Reef: a queue at `docs/loop/queue.md` (909 rows), a handoff at
`HANDOFF-FRESH.md`, Spec Kit under `.specify/` and `specs/*/spec.md`, and package scripts named `loop:*` that start,
close and number its work. `/reef-init` then wrote Reef's `docs/queue.md` and `HANDOFF.md` beside them, because init
knows a project's **stack** (package.json, pyproject) but nothing about a project's **process**. The result was two
queues and two handoffs, and every later session had to be told which one counts.

Init's one rule, "never overwrite a file you wrote", held: nothing of the project's was touched. The defect is the
opposite one — Reef created records that duplicate records the project already keeps.

## 2. Detection signals [Observed on ai-coach; to be confirmed on a second project]

A project runs its own loop when any of these exist in the checkout:

| Signal | Where it was on ai-coach | What it tells init |
|---|---|---|
| `docs/loop/` (or a directory whose name is `loop`, `backlog`, `queue`) holding a Markdown table with an id column | `docs/loop/queue.md` | a queue exists |
| `HANDOFF*.md` at the root other than Reef's `HANDOFF.md` | `HANDOFF-FRESH.md` | a handoff exists |
| `.specify/` | `.specify/memory/constitution.md` | Spec Kit: a constitution and specs exist |
| `specs/*/spec.md` | 7 specs | specs exist outside Reef's feature folders |
| package scripts whose names start with `loop:` or contain `handoff`, `adr`, `queue` | `loop:start`, `loop:close`, `loop:adr` | commands agents are told to run |
| an instruction file (`CLAUDE.md`, `AGENTS.md`, `.claude/commands/*.md`) that names any of the above | `CLAUDE.md`, `AGENTS.md`, `CLAUDE-CODE-PROMPT.md` | the agents read the old process first |

Detection is mechanical and cheap (file globs, one JSON read, one grep); it belongs in `reef-init.py detect()` next to the
stack facts, as a `facts["own_loop"]` list of the signals found, whichever option wins.

## 3. The two options

### A — init skips its process files; assess migrates

When a signal is found, init writes the **harness** (config, guard, gates, CI proposal, scripts, tiers) but not the
**records** it would duplicate: no `docs/queue.md`, no `HANDOFF.md`, no skeleton journal row. It prints one line per
skipped file: "skipped docs/queue.md — the project keeps its queue at docs/loop/queue.md; /reef-assess migrates it".
`/reef-assess` then owns the whole move: the old queue's open rows into Reef's queue, the handoff merged into
`HANDOFF.md`, readers repointed, under its one approval (the shape item 18 of the same brief describes).

- For: one owner of the migration, one approval, no duplicate records for even a minute; init stays what it is, a
  renderer that never guesses about process.
- Against: between init and assess the project has no Reef queue, so `/reef-loop` has nothing to run — acceptable,
  since assess is the documented next step on an existing project, but the gap must be said on init's screen.

### B — init writes its files; assess merges

Init writes everything as today, and `/reef-assess`'s plan gains "merge" actions: the old queue's open rows appended
to Reef's, the old handoff's content folded into `HANDOFF.md`, the originals archived.

- For: no change to init; a project that never runs assess still has a working Reef queue.
- Against: two queues exist from init until assess, and on ai-coach that interval was where sessions got confused;
  "merge" is harder than "migrate" because Reef's file may have been edited in the meantime (rows added by the first
  loop run), so the merge needs conflict rules, not just a copy.

## 4. Recommendation (the author's, not a decision)

**A.** The duplicate record is the defect; the cheapest fix is not to create it. The gap between init and assess is a
sentence on init's screen, and assess already has the one-approval shape to carry the migration. B keeps a known bad
state alive for an interval and adds merge logic Reef does not otherwise need.

Either way the detection table in §2 is the first row of work, and the instruction-layer signal (last row) is the one
that matters most: on ai-coach the agents obeyed `CLAUDE.md`, not the queue.

## 5. What the owner decides

1. A or B.
2. Whether a found signal makes init **skip silently with a line**, or **ask** (one AskUserQuestion: "this project runs
   its own loop (docs/loop/, HANDOFF-FRESH.md): write Reef's queue and handoff anyway?").
3. Whether `.specify/` alone (a constitution, no queue) counts as "own loop" or only as "existing constitution", which
   init already handles by pointing at it.

Implementation lands as one queue row after the decision; its tests: a fixture with each signal, init's output per
option, and a second run that stays idempotent.
