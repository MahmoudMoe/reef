---
name: reef-plan-review
description: Check an approved Reef plan before implementation — deterministic structural checks, then a fresh-context semantic review of invariants, brief, ADRs, and tasks. Use between plan approval and reef-task, or when the user says "/reef-plan-review".
argument-hint: <feature-slug | empty = current plan>
---

# Reef Plan Review — approved plan -> reviewed plan

Between "the human approved the plan" and "start implementing" there is otherwise no check. This closes it: a blocking script layer, then a bounded agent layer. Read `.reef/config.json` for paths.

1. Run `scripts/reef-plan-check.py`. Exit 1 = STOP; print its failing lines. It is deterministic; never argue with it, never work around it.
2. Only if it passed: spawn the `plan-reviewer` agent (this plugin), fresh context, model fable.
3. On BLOCKING findings: the ORCHESTRATOR applies the fix — always in the direction of the approved plan, never against it. Only the brief and `.reef/config.json` are ever corrected; task files and ADRs are authoritative and are never edited to make a finding go away. The fix touches documentation only — never code, never a task file. Then re-run the script and re-dispatch the agent once. A second round of the same blocking finding is a STOP for the human, not a third attempt.
3b. A HALT (two authoritative sources contradicting each other) is NOT a fix you may apply. Relay it verbatim and stop. An acknowledgment — "ok", "proceed", "looks good" — does not resolve it; only the human naming which source wins AND why does, with the losing side amended in the same change. Dispatching an implementer before that is a violation.
4. On ADVISORY findings: present them to the human and stop. Never act on them alone — they concern the plan itself, which only the human may change.
5. Re-entry: state lives in `<tasks>/.plan-review.json` (written by the script on success), not in memory.

## Called from reef-task
reef-task runs `scripts/reef-plan-check.py --verify-stamp` before its first dispatch. Non-zero exit = the plan changed since the last review, so this skill runs first and its result is shown to the human before any implementer is spawned.
