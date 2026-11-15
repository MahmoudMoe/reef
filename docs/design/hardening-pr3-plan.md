# Hardening PR-3 — the learning edge: a failure the loop survived becomes one approved line, measured

PR-2 made every FAIL a record (EXPECTED, SAW, FENCE, DEAD END, the signature) in the task's `## Log`. Nothing learns from
them: the same failure class costs a round on the next task, and the one after. This PR adds the edge, every step by code
except the one sentence:

trigger (code) → facts (code) → the model drafts ONE line tagged LAYER → code checks its shape → the owner approves it in the
report → code lands it in the layer's file → code counts the class's recurrence → code proposes retirement; the owner approves;
code removes it (kept in the history).

## The layers and the files they own

A lesson changes what one reader does next time. The layer is that reader; its file is read at that reader's entry point.

| layer | what it means | who reads it | the file | delivered by |
|---|---|---|---|---|
| `harness` | the task's round: what the implementer is told and the checks around it (PR-1's round, PR-2's dead ends) | the implementer, every dispatch | `reef/lessons/harness.md` | **code**: `reef-attempt`'s dispatch prints a `lessons:` block (after `dead-ends:`); graph mode passes it into the implementer's prompt verbatim, as the dead ends |
| `loop` | the orchestration: the order of steps, waits, closes, the questions (`/reef-loop`, `/reef-task`) | the orchestrator, every session | `reef/lessons/loop.md` | **code**: `reef-loop.py tick --session-start` (the SessionStart context) carries it |
| `graph` | the plan's shape: the task split, `files:`, `depends_on`, resources (the planner's output) | the planner, every plan | `reef/lessons/graph.md` | **the guard** (owner decision 2): a `planner` Agent dispatch is refused when its prompt lacks any line of the `lessons:` block of the graph file (`reef-lessons.py lessons graph` prints it), compared by content like PR-2's dead-ends check; `agents/planner.md` names the block |

The files are the PROJECT's (`reef/lessons/` in the main checkout), not the plugin's `agents/*.md` or `skills/*`: the plugin's
files are reinstalled on every update and the guard protects them; a lesson learned in a project belongs to it.

A line is DELIVERED only when its approval record matches it (`.reef/approvals/lesson-<id>.json`, the digest of the landed line):
a line added or edited by hand is not passed on, and the report names it (`not approved — edited by hand`).

## 1. Triggers (code)

- **(a) GREEN after a failed round**: `reef-merge-close`, after a successful close (both paths: the fast path in place, the task
  branch merge), when the task's `## Log` holds ≥1 FAIL record → a candidate, trigger `green-after-fail`, facts from the LAST FAIL.
- **(b) same-failure escalation**: `reef-attempt`, when the same signature twice blocks the task → a candidate, trigger
  `same-failure`, facts from that FAIL. The cap (`retry cap reached`) is not a trigger (the owner named the same-failure one).
- Every FAIL `reef-attempt` records and every close `reef-merge-close` makes is also appended to the ledger (the recurrence count
  reads them).
- A trigger never fails its host: an error in the lesson step prints `lesson: not recorded — <why>` and the close or the block
  goes on as before. One candidate per (task, trigger, signature): a re-run close or a second block of the same task adds none.
- Graph-mode settle and row mode both close through `reef-merge-close` and record through `reef-attempt`, so they need no call.

## 2. Facts (code) — the model gets facts, not a transcript

`reef-lessons.py facts <id>` (also printed by the trigger):

```
lesson L3: candidate (green-after-fail) — draft ONE line: python3 scripts/reef-lessons.py draft L3 "<harness|loop|graph>: <the lesson>"
  task: 101 (feature demo) · rounds: 2 FAIL before GREEN · class: round-not-red · sig: 0f3a9c1d2b4e
  files: [src/a.py, tests/]
  #1 attempt 1 EXPECTED: …
  #1 attempt 1 SAW: …
  #1 attempt 1 FENCE (derived): …
  #1 attempt 1 DEAD END: …
lesson L3: end
```

The record lines are PR-2's `dead-ends:` lines (reef-attempt's `dead_end_lines`), every FAIL of the task, oldest first.

**The failure class** (code, `reef-lessons.py` `classes()`), a fixed vocabulary read from the record so a class recurs across tasks:
- EXPECTED is the round check's (PR-2 `--from-round`): one class per `round: REFUSED` line — `round-scope` (outside `files:`),
  `round-not-red` (does not fail on the base), `round-not-green` (does not pass on the round's tree), `round-no-test` (ran no
  test), `round-timeout`, `round-files-shape`, else `round-other`.
- EXPECTED is graph settle's: one class per reason line — `gate-red`, `handback-rejected`, `report-rejected`, `verifier-fail`,
  `hunter-fail`, `tree-moved`, `guard-pass`, `task-missing`, else `settle-other`.
- any other EXPECTED (a recorder's own words): `expected-<sha8 of the normalized EXPECTED>` — the same requirement failing again.
- the candidate's class is its record's FIRST class; a FAIL recurs a class when ANY of its classes is that class.

## 3. Draft (the model) and its shape check (code)

`reef-lessons.py draft <id> "<layer>: <lesson>"` — refused with exit 2, nothing written, when:
- the id is not a candidate, or is already landed or retired;
- the text has a newline (one line), or a control character;
- the tag is not `harness`, `loop` or `graph` (`LAYER: …`, lowercase or not);
- the lesson is under 20 or over 160 characters (after the tag), or starts with `#`, `-`, `>` or `|` (it is landed as a bullet).
A new draft of a candidate not yet approved replaces the old one (the approval binds the draft's digest, so an approval of the
old draft is stale).

## 4. Approve in the report (a record, the owner's)

- The question is `Approve lesson <id> at <digest16>?` — digest16 = the first 16 hex of sha256 over `land`, id, layer, lesson,
  class. Retirement: `Approve retiring lesson <id> at <digest16>?` (sha256 over `retire`, id, layer, lesson).
- Answered exactly `Approve` through the existing AskUserQuestion hook or `reef-approval.py --owner "<question>"` in the owner's
  terminal — `reef-approval.py` takes the two new questions beside the plan/night/day ones; the record is
  `.reef/approvals/lesson-<id>.json` (`{action, digest16, digest, approved_at, by: owner}`), under the guarded records folder.
  The guard already refuses an agent running `reef-approval.py` without `--proxy`, and no `--proxy` path takes a lesson:
  **the proxy (Mahmoud) never approves a lesson** (the owner's words: "I approve").
- A stale digest (a redraft since), an unknown id, or another answer: nothing written.
- **Where it appears**: the report the owner reads — the night/autopilot report (`reef-run.py` `morning_report`) gets a
  `## Lessons` section, and the `reef` screen's inbox an `approve` item per question (`APPROVE_Q` learns both questions, so
  the existing `already_approved` and `reef-approval.py --owner` plumbing carries them). Both read `reef-lessons.py`'s
  `report_lines()` / `questions()`: one source.

## 5. Land (code)

On the approval, in the same call: `reef/lessons/<layer>.md` (created when missing) gets, under its fixed `## Lessons` section:

```
- L3 · class round-not-red · sig 0f3a9c1d2b4e · landed 2026-11-15 · <the lesson>
```

and the ledger a `landed` event. **The cap** (`lessons.cap`, default 10, per layer file): a layer already holding `cap` lessons
refuses the landing — nothing written, not even the approval record — `layer harness holds 10/10 lessons — retire one first`.

**The commit (owner decisions 5 and 6)**: the approval (hook or `--owner`, one path) only writes the layer file (and on a
retirement `reef/lessons/history.md`), the record and the ledger event — never a commit and never the pre-commit gate inside
the AskUserQuestion hook, which has a 30 s timeout. The commit is the next **`reef-loop.py tick`**'s (it runs on every
orchestrator turn, chat mode and the runner's sessions alike; the runner's own between-session script sync is runner-only):
`commit_pending` takes the landed/retired events not yet followed by a `committed` event, commits exactly their files in the
main checkout under the pre-commit gate (`git commit -- <paths>`, like `commit_plan` in #370) —
`reef: lessons L3 landed, L1 retired — committed on the tick (the owner's approvals)` — and appends `committed`. Idempotent: a
file already committed is marked without a new commit. A refused commit leaves the files as written and appends
`commit-refused {why}`; the night/autopilot report's `## Lessons` and the `reef` inbox name it (`not committed: <files> — <why>`)
until a tick commits them. Never silent. The lesson is landed (and delivered) from its approval on.

## 6. Measure (code)

For each landed lesson, from the ledger:
- **recurred**: FAIL events after `landed_at` whose classes include the lesson's class;
- **quiet rows**: distinct features closed (close events) after `landed_at` — zero recurrences over them is the deletion test.
The report shows `L3 harness · round-not-red · landed 2026-11-15 · recurred 1 · 4 rows since`.

## 7. Pruning (the owner's addition)

- the cap above forces it;
- the report proposes retirement, with the question: recurred ≥ `lessons.recur` (default 2) → `does not work — turn it into a
  code check, or retire it`; zero recurrences over ≥ `lessons.quiet_rows` (default 10) rows → `the deletion test — retire it`;
- any landed lesson can be retired by its question (a full layer must be able to make room);
- on the retire approval code removes its line from the layer file and appends to `reef/lessons/history.md`:
  `- 2026-11-20 retired L3 (harness, class round-not-red, recurred 0 over 10 rows, landed 2026-11-15): <the lesson>` — never
  silently deleted. The ledger gets a `retired` event.

## Records

- `.reef/approvals/lessons.jsonl` — the ledger (guarded folder; written only by scripts), one JSON line per event:
  `fail {at, task, feature, attempt, sig, classes}`, `close {at, task, feature}`, `candidate {id, at, trigger, task, feature,
  sig, class, facts}`, `draft {id, at, layer, lesson}`, `landed {id, at, layer, digest16}`, `retired {id, at}`. State is the fold;
  ids `L<n>` are allocated under an flock on the ledger.
- `.reef/approvals/lesson-<id>.json` — the owner's approval (land; `lesson-<id>-retire.json` for a retirement).
- `reef/lessons/{harness,loop,graph}.md`, `reef/lessons/history.md` — the landed lessons and the retired ones (tracked).
- config: `lessons.cap` 10, `lessons.recur` 2, `lessons.quiet_rows` 10 (templates/config.json: `config_keys` +3).

## Tests (each red on the unchanged code first) — `tests/test_lessons.py` unless named

- trigger (a): a close of a task whose Log holds a FAIL writes one candidate with its facts; a close with no FAIL writes none;
  a second close run writes no second one (`tests/test_merge_close.py`).
- trigger (b): the same signature twice blocks AND writes a candidate (`same-failure`); a cap block alone writes none
  (`tests/test_attempt.py`).
- every FAIL recorded appends a `fail` event with its classes; the class vocabulary on a round refusal, a settle reason, a free EXPECTED.
- facts: the facts block carries every dead-end line of the task, the class, the signature and the round count.
- shape: two lines, no tag, a bad tag, too short, too long, a leading `#` — each exit 2, the ledger unchanged; a good one recorded.
- approval: `--owner "Approve lesson L1 at <d16>?"` writes the record and lands; a stale digest (after a redraft) writes nothing;
  the guard refuses an agent running it (already, a test pins it for the lesson question).
- landing: the line in `reef/lessons/<layer>.md` under `## Lessons` with id, class, signature and date.
- cap: an approval past `lessons.cap` refuses, nothing written, the file unchanged.
- recurrence: a FAIL of the class after landing counts 1; one before landing or of another class counts 0; quiet rows count
  distinct features closed since.
- retirement proposal: recurred ≥ N → proposed (code check or retire); 0 recurrences over ≥ M rows → proposed; neither → none.
- retirement: the approved question removes the line, appends to `history.md`, frees a cap slot.
- the guard (decision 2): a planner dispatch without the graph block is refused, naming the first missing line; with only the header refused; with the block allowed; no graph lesson, no block needed (`tests/test_lessons.py`, the guard as a subprocess).
- the commit (decisions 5, 6): approving (hook or `--owner`) runs no pre-commit gate and makes no commit; the next tick commits exactly the pending lesson files (another changed file stays out), a second tick commits nothing; a retirement's tick commits the layer file and history.md; a refused commit leaves the files, and the report and the inbox name it; once the gate is green the next tick commits.
- delivery: the dispatch prints the `lessons:` block of the harness file's approved lines; a hand-edited line is not printed;
  graph mode's implementer prompt carries it (`tests/test_graph_run.py`); the session-start context carries the loop lines
  (`tests/test_loop.py`).
- report: the night/autopilot report's `## Lessons` lists the draft's question, landed lessons with counts, the retirement
  proposals (`tests/test_night.py`); the `reef` inbox shows the approve item (`tests/test_entry.py` or the screen's suite).
- contracts: `agents/implementer.md` names the `lessons:` block, `agents/planner.md` the graph file, `/reef-task` the draft step.

## Out of scope

- the guard refusing an implementer dispatch without the `lessons:` block (PR-2 did that for dead ends; a follow-up if wanted).
- checking that a lesson is TRUE or useful (only its shape is code); the model drafting it unprompted at other moments.
- turning a lesson into a code check (the report proposes it; a person writes the check).
- any refactor of reef-attempt, merge-close, graph-run, the approval script or the report.

## Owner decisions (ruled 2026-11-15, relayed by the orchestrator; all implemented in this PR)

1. **Project-side layer files** `reef/lessons/<layer>.md`, not the plugin's agent/skill prose — yes, as planned.
2. **Graph lessons are enforced by the guard** on the planner dispatch, by content (every line of the graph `lessons:` block in
   the planner's prompt), the PR-2 dead-ends pattern — not prose only. (Planned conservative choice was prose.)
3. **Defaults**: cap 10 per layer, N = 2 recurrences, M = 10 rows (a row = a feature closed); trigger (b) only the same-signature
   block, not the retry cap — yes.
4. **Owner only**: the proxy never approves or retires a lesson, not even under the autopilot — yes.
5. **Code commits** the landed or retired layer file and history.md, like `commit_plan` (#370). (Planned conservative choice was
   no commit.)
6. **The commit is not in the hook** (ruled after the PR opened, on the 30 s hook timeout): the approval writes; the next
   `reef-loop.py tick` commits; a refusal is reported in the report and the inbox, never silent.
