---
name: reef-verify
description: Run the Reef adversarial verification pass on a task or diff — evidence per acceptance criterion, break paths, ADR-falsification check. Usable standalone ("/reef-verify") or by reef-task.
argument-hint: <task-ref | "diff">
---

# Reef Verify

Judge, don't fix. Fresh eyes on the diff (`git diff` or the named task's changes) against its acceptance criteria.

- FIRST, before reading the diff: read only the task file and write one rule per acceptance criterion — `RULE AC<n>: PASS iff <observable result>; FAIL if <observable result>` (name the test, command or file you will look at). These lines open your report, above any verdict. A rule written after reading the code bends to fit the code; a rule changed after reading the diff must be shown as changed, with the reason.
- Re-run the full gate yourself (`scripts/reef-gate.sh full`); never trust a hand-off's claim.
- Verdict per AC, judged by ITS RULE, WITH evidence: test name, file:line, or command output. No evidence = FAIL that criterion.
  - Good: "AC2 PASS — `test_empty_input` (tests/test_summarize.py:17) asserts `months == {}`; suite re-run by me: 34 passed."
  - Bad: "AC2 PASS — implementer's tests cover this." (Trusting the hand-off is the exact failure this role exists to prevent.)
- On a retry (`attempts:` > 0): attack the last round's fix first — read `last_failure_sig` and the Log; the previous fix is where the next defect sits.
- Adversarial pass: 2-3 realistic break paths for THIS change; report actual observed behavior.
- "Cannot verify here" needs the probe's output pasted (the command, the exit code) — never the sentence alone.
- Invariants: check each entry in `.reef/config.json` `.invariants[]` against the diff.
- ADR check: read `docs/adr/` (Accepted only) — "name any ADR sentence this diff falsifies; answering 'none' requires evidence." A falsified ADR must be superseded in the same PR or the diff FAILS.
- Begin the report with `RUN: agent=verifier task=<id>`, then the `RULE AC<n>` lines; end with `VERDICT: PASS` or `VERDICT: FAIL` + the concrete feedback an implementer needs.
