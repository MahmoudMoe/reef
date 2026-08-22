---
name: reef-verify
description: Run the Reef adversarial verification pass on a task or diff — evidence per acceptance criterion, break paths, ADR-falsification check. Usable standalone ("/reef-verify") or by reef-task.
argument-hint: <task-ref | "diff">
---

# Reef Verify

Judge, don't fix. Fresh eyes on the diff (`git diff` or the named task's changes) against its acceptance criteria.

- Re-run the test gate yourself (`scripts/reef-gate.sh`); never trust a hand-off's claim.
- Verdict per AC WITH evidence: test name, file:line, or command output. No evidence = FAIL that criterion.
  - Good: "AC2 PASS — `test_empty_input` (tests/test_summarize.py:17) asserts `months == {}`; suite re-run by me: 34 passed."
  - Bad: "AC2 PASS — implementer's tests cover this." (Trusting the hand-off is the exact failure this role exists to prevent.)
- Adversarial pass: 2-3 realistic break paths for THIS change; report actual observed behavior.
- Invariants: check each entry in `.reef/config.json` `.invariants[]` against the diff.
- ADR check: read `docs/adr/` (Accepted only) — "name any ADR sentence this diff falsifies; answering 'none' requires evidence." A falsified ADR must be superseded in the same PR or the diff FAILS.
- Begin the report with `RUN: agent=verifier task=<id>`; end with `VERDICT: PASS` or `VERDICT: FAIL` + the concrete feedback an implementer needs.
