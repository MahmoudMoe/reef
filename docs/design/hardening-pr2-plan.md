# Hardening PR-2 — dead ends: a FAIL carries what was expected, what was seen, the fence and every dead end

Today `reef-attempt <task> "<failure text>"` records a FAIL as one `## Log` line (`- attempt N FAIL: <text[:300]> · at <UTC>`), and
the next round sees only the LAST such line: graph mode puts `fail[:400]` in the implementer's prompt
(`reef-graph-run.py` `task_item`), chat mode leaves it to the orchestrator's memory. Round N+2 never sees round N's failure, and
nothing says what the criterion required, what must not be touched, or which approach already failed.

## What

1. **Recording (fail closed).** The failure text is LABELLED: lines starting `EXPECTED:`, `SAW:`, `FENCE:`, `DEAD END:`. An
   unlabelled line continues the field above it (verbatim output spans lines). The arguments after the task file are joined
   by newlines (one argument per field works: `reef-attempt <task> "EXPECTED: …" "SAW: …"`). Refused with exit 2, the task file
   unchanged, like every other unusable input of the script:
   - no `EXPECTED:` or no `SAW:`, or one of them empty;
   - text before the first label (a free-text failure, the old form).
2. **Fields the code fills when the recorder gives none** (each marked `(derived)`):
   - `FENCE (derived)`: the task's `files:` list (the round check refuses any other file) and the criteria the failure does not
     name (`AC-n`: keep them passing); neither known → `keep what passed: change only what SAW shows`.
   - `DEAD END (derived)`: the claims lines of the round's hand-back (`.reef/ci-local/handback-<id>.md` beside the task file's
     checkout, the file `reef-attempt` names; at most 5) — the approach the round says it took; none →
     `attempt N's approach (no hand-back claims to name it)`.
3. **Storage: the task file's `## Log`, under the FAIL line it belongs to.** The Log is outside every digest
   (`reef-plan-check.py` cuts the stamp at `## Log`, and the word caps say "the Log does not count"), so recording a FAIL does not
   void the approval — exactly as the FAIL line today. Only the orchestrator's `reef-attempt` writes it; the implementer never edits
   a task file. Not a `.reef/ci-local/` file: that folder is the implementer's own worktree scratch (it writes its hand-back there),
   and it does not travel with the task file to `tasks/done/`.
4. **Reading back: every later dispatch prints all of them.** `reef-attempt <task>` (the dispatch call) prints a `dead-ends:` block
   of EVERY structured FAIL record in the Log, oldest first — a human reset (`attempts: 0`) does not drop them: an approach that
   failed is still a dead end. A FAIL line from before this format is printed as its one line (`SAW (before the four fields)`).
   No FAIL in the Log → no block.
5. **Who passes it on.** Graph mode: `reef-graph-run.py` puts the block verbatim in the fix round's implementer prompt (code, no
   prose). Chat mode: `/reef-task` step 2 already says "use EXACTLY what it prints"; one clause names the block.
   `agents/implementer.md` gets one line pointing at it: meet EXPECTED, stay inside every FENCE, retry no DEAD END.
6. **Graph-mode settle records the four fields itself**: `EXPECTED: gate exit 0, the hand-back check ok, every judge PASS`,
   `SAW:` one line per reason (and the failing tests the gate's log names, verbatim). Without this its call would now be
   refused and the FAIL lost.

## Format (exact)

In the task file, appended at the end of `## Log` (CRLF kept, as `append_log` already does):

```
- attempt 2 FAIL: <SAW, whitespace collapsed, first 300 chars> · at 2026-11-15T10:00:00.123456Z
  - EXPECTED: AC-2 the export refuses an empty name with exit 2
  - SAW: FAILED tests/test_export.py::test_empty_name - AssertionError: 0 != 2
  - SAW: 1 failed, 14 passed in 0.31s
  - FENCE: only tests/ and src/export.py; AC-1 passes — keep it
  - DEAD END (derived): Empty names are rejected in parse_name — true at src/export.py:12
```

- the one-line summary is the SAW (what the old free text was), so every existing reader of `- attempt N FAIL:` lines
  (`rejudge`, the tick's `FAIL_AT`, graph-run's `last_failure` and its `verifier report rejected` test) reads what it read before.
- `SAW` keeps each line verbatim (trailing spaces cut, blank lines dropped), at most 20 lines of 200 characters, then
  `  - SAW: … (+K more lines trimmed)`. The other fields: whitespace collapsed, 300 characters.
- every sub-line starts `  - <FIELD>`: a verbatim line can never sit at column 0 (no `## ` heading, no `- attempt N FAIL:`).
- the signature (the "same failure twice" guard) hashes EXPECTED + SAW, normalized as before — not FENCE or DEAD END, which are
  the recorder's words and would let a reworded fence hide a repeat.
- `rejudge` reads the named criteria from the last FAIL line AND its sub-lines (an `AC-n` in EXPECTED is named).

On dispatch, after `hand-back:`:

```
dead-ends: 2 recorded — pass every line through `dead-ends: end` to the implementer verbatim: meet EXPECTED, stay inside FENCE, retry no DEAD END
  #1 attempt 1 EXPECTED: …
  #1 attempt 1 SAW: …
  #1 attempt 1 FENCE (derived): …
  #1 attempt 1 DEAD END: …
  #2 attempt 2 EXPECTED: …
  …
dead-ends: end
```

## The round check (PR-1) and dead ends

A round refused by `reef-claims.py round` is a FAIL; its `round: REFUSED — …` lines are the SAW, verbatim. Decision (the
conservative one): no direct feed in this PR — `/reef-task` names the form
`reef-attempt <task> "EXPECTED: reef-claims.py round exits 0 (the Proof test red on the base, only files:)" "SAW: <its REFUSED lines>"`.
A `--from-round` flag that runs or reads the check itself is a later choice for the owner.

## Tests (each red on the unchanged code first)

`tests/test_attempt.py`, new class:
- a FAIL without `EXPECTED:` is refused, exit 2, the task file byte-identical; the same without `SAW:`; a free-text FAIL is refused.
- a FAIL with the four fields writes them as sub-lines under its FAIL line; the approval digest
  (`reef-plan-check.py --digest`'s task digest) is the same before and after.
- the dispatch after one FAIL prints the `dead-ends:` block with its EXPECTED, SAW, FENCE and DEAD END.
- after three rounds (cap 5), the dispatch still prints round 1's dead end (N+2 sees N); after a human reset too.
- FENCE and DEAD END derived when absent: from `files:`, the unnamed criteria, the hand-back's claims.
- SAW trimmed to 20 lines, verbatim; a SAW line that reads `## Proof` or `- attempt 9 FAIL:` stays indented.
- `tests/test_graph_run.py`: the fix round's implementer prompt carries every dead end (round 1's too); settle's FAIL records
  EXPECTED and SAW.
- `tests/test_contracts.py`: `agents/implementer.md` names the `dead-ends:` block; `/reef-task` names the labelled form.

Existing tests that record a FAIL with free text are moved to the labelled form (`EXPECTED: …` + `SAW: <the same text>`): the
behaviour they test (cap, signature, lock, CRLF, stamps) is unchanged, only the input form.

## Out of scope

- the guard refusing a chat-mode implementer dispatch whose prompt lacks the `dead-ends:` block (flagged for the owner: it is the
  enforcement for chat mode; today the prose and graph mode's code carry it).
- checking that SAW is really verbatim output (a paraphrase is not detectable by code).
- the verifier's and hunter's prompts (they already read the Log on a retry).
- a direct feed from `reef-claims.py round` (above); any refactor of reef-attempt, graph-run or the claims checker.
