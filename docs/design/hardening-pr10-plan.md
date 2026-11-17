# Hardening PR-10 — the owner reads names, not bare ids

The owner (2026-11-17): the reports use ids nobody explained. `row 12 (process): …`, `L1 harness`, `task 403 is marked in
flight`, `rows: 3, 12` — each id means something only to whoever has the queue open. Rule (from mattpocock/skills'
wayfinder, "refer by name"): a name wraps its id, never a bare id.

## The rule

- A row, task, lesson or ADR id the owner reads carries its name: **`row 7 (add CSV export)`**, `task 403 (wire the
  export button)`, `lesson L1 (name every file the round touches)`.
- The form is `<kind> <id> (<name>)`, parentheses, not an em dash (decision D1). The ` — ` is already a field separator in
  the lines that carry these ids: Mahmoud's `DECIDE <question> — <answer> — <why>` (parsed by `reef-approval.py:333`), the
  questions file's `— recommended:`, the report's `— undo:`. An em-dash name inside a DECIDE question would split it.
- A list names each id: `rows 3 (login page), 12 (CSV export)`.
- A name the code cannot find says so: `row 7 (not in the queue)`, `task 403 (no task file)`, never a bare id (D3).
- A name is plain text (control characters out, `reef_common.plain`), at most 60 characters, a cut marked `…` (D4).

## Where the owner reads ids today (main, e5d2197)

| # | output | file:line | bare ids today |
|---|---|---|---|
| 1 | night / autopilot report (`.reef/night/report.md`, `.reef/run/autopilot.md`) | `scripts/reef-run.py:1265` `morning_report` | the proxy's day decisions `- row 12 (process): …` (:1304); `## Lessons` via `reef-lessons.py:401` `report_lines` (`L1`, `from task 101`); `## Waiting for you` = `.reef/questions.md` raw (`- row 7: …`, :1318); the footnotes, verbatim (they may say `row 12`, :1296) |
| 2 | the runner's wait, in the terminal and the live log | `scripts/reef-run.py:1060` `owner_wait_lines` | `waiting on you — {wait}`: the loop's wait text (`row 46: …`, `reef-loop.py:356,404,411,558`) |
| 3 | the night contract the owner approves (`reef-run.py contract`; `/reef-night` puts its `rows:` line in the Approve description) | `scripts/reef-run.py:1151` `cmd_contract` | `rows: 3, 12`, `WARN ready rows not in tonight's contract …: 7` |
| 4 | the `reef` screen's inbox | `scripts/reef:297` `inbox` | `row 9: Approve plan …` (:315), `lesson: Approve lesson L1 …` (:322), `row 7 (#90): …` (:328, :333), `task 403 is marked in flight …` (:345), the parked text (:351) |
| 5 | Mahmoud's decision report → the queue footnote the owner reads in (1) | `agents/mahmoud.md` § Report | `DECIDE row <id> …` |
| 6 | the plan approval (`/reef-plan` gate) | `skills/reef-plan/SKILL.md:46` | none: the question names the slug; the description is `reef-plan-check.py --summary`, which names files |
| 7 | the lesson approval | the inbox (4) and the report (1) | the question `Approve lesson L1 at …?` is exempt; the text around it is (1)/(4) |
| 8 | the board (WORK, PLAN views) | `scripts/reef:1002, 1081, 813` | each line is `row 7 … <its Item>`: named on its own line. `waits: row 8` sits in a 22-character cell — see D5 |

## What changes

**One formatter, by code** — `scripts/reef_common.py`:
- `names(root)` → `{"row": {id: Item}, "task": {id: title}, "lesson": {id: text}}`, read once per render: rows from the
  queue file and its archive through `reef-queue.py parse_table` (on an issues queue, the synced `.reef/queue.json`, no
  network); tasks from the `# <id> — <title>` heading of every task file under `<features>/*/tasks/` and `tasks/done/` in
  every checkout (a task in flight lives in its feature worktree); lessons from the ledger (`reef-lessons.py state`).
- `named(kind, id, names)` → `row 7 (add CSV export)`.
- `name_refs(text, names)` → the same text with every bare reference named — for text an agent or the loop wrote (the wait,
  a question, a footnote) at the point the owner reads it. Never on disk: the queue, `questions.md`, `loop.json` keep their
  format.
- `bare_refs(text)` → the bare references left: the check.

**The writers call it** — (1) `morning_report`: the day decisions by `named`, the footnotes and the questions by
`name_refs`; `reef-lessons.py report_lines`: `lesson L1 (<its text>) — harness …`, `from task 101 (<title>)` (the text moves
into the name: it is not said twice). (2) `owner_wait_lines`: the wait line by `name_refs`; the commands below it untouched.
(3) `cmd_contract`: `rows: 3 (…), 12 (…)` and the WARN line. (4) `inbox`: every item's `text` by `named` / `name_refs`; the
item's `cmd`/`argv` untouched. (5) `agents/mahmoud.md`: `DECIDE row <id> (<its Item>) …`, and "an id you write carries its
name: `reef_common.named`'s form".

**Enforced by code** — `tests/test_names.py`: a fixture project (a queue with Items, task files with titles, a landed and a
proposed lesson, a proxy day decision, a filed question, a wait naming two rows, a task in flight) renders the report, the
autopilot report, the wait lines, the contract and the inbox, and asserts `bare_refs` finds nothing. The red: the same
assertions on main's renderers, the bare ids listed. Plus the detector's own cases (below).

## The detector (`bare_refs`) — what counts as bare

- A reference: `row|rows|task|tasks|lesson|ADR` + an id (`7`, `12a`, `R07`, `L1`, `0003`), and a list after a plural
  (`rows 3, 12 and 14`); a bare `L<n>` (a lesson id without its word). Case-insensitive on the word.
- Named = the id is followed by ` (` (the formatter's form). Anything else is bare.
- Exempt spans (machine-read, or the owner's own command): an `APPROVE_Q` question verbatim (`Approve plan … at …?`,
  `Approve lesson L1 at …?` — the hook matches it exactly); a backtick span; a command to the end of its line (`python3 …`,
  `gh …`, `git …`, `sh …`); a line starting `RUN:`, `VERDICT`, `summary:`, or a frontmatter `key:` line.
- Not a reference: `#90` (an issue or PR number — the forge's id, shown beside a name), a digest, a sha, `Row:` in a SPEC.

## Exempt, stated (out of scope)

- Agent-to-agent formats: the tick's text in `loop.json`, `questions.md`, the queue footnotes on disk, RUN/VERDICT lines,
  hand-backs, task frontmatter. Named where the owner reads them, never rewritten where an agent parses them.
- The replies of a command the owner typed with the id (`reef-approval.py --owner …`, `reef-queue.py footnote --row 7`,
  `reef approve 9`, `reef-row.py state 9`): the owner just typed the id; not changed here.
- The board (D5).
- ADR names: no in-scope output prints an ADR id today; the detector still flags one, so a future writer has to name it.

## Decisions (flagged — conservative default taken; the owner may overrule)

- **D1** form `row 7 (add CSV export)`, parentheses (why above). The brief's example used an em dash.
- **D2** name sources: a row's queue `Item`; a task's heading title; a lesson's own text (a candidate not drafted yet:
  `not drafted yet`).
- **D3** a name not found is said: `(not in the queue)`, `(no task file)`, `(no such lesson)`.
- **D4** 60 characters, cut marked `…`.
- **D5** the board is exempt: every board line already carries its row's Item beside the id, and its 22-character status
  cell (`waits: row 8`) has no room for a name — row 8 is a line of the same table. The inbox, the report, the wait lines
  and the contract are not exempt.
- **D6** agent-written prose (the wait, questions, footnotes) is named at render by `name_refs`, not at its source: the
  source formats are agent-to-agent (out of scope) and parsed (`QUESTION_LINE`, the tick).

## Limits

- `name_refs` names what it can recognise: `row 7`, not "the seventh row" or "item 7".
- The test renders from fixtures; a new owner-facing writer is covered only once a test renders it. `tests/test_names.py`
  says so in its docstring and lists the writers it covers.

## Steps

1. This plan, pushed.
2. Red: `tests/test_names.py` — the renders on main, the bare ids printed.
3. Green: the formatter, the writers, `agents/mahmoud.md`; the existing tests whose expected strings name ids updated to the
   named form (listed in the PR).
4. CHANGELOG, bump-version, size budget; `sh tests/run.sh` + stress; rebase on main; PR.
