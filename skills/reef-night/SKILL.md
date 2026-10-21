---
name: reef-night
description: Super Reef — agree tonight's work with the owner's proxy (reef:mahmoud) and the owner, ONE approval, then the owner sleeps while scripts/reef-run.py --night runs the loop and Mahmoud decides inside the contract. Use when the owner says "/reef-night", "super reef", or wants to delegate a night.
argument-hint: <empty | the rows to drive tonight>
---

# Reef Night — delegate one night, approve once

**Before anything**: `.reef/run/gate.json` must say ok for the mode the owner will run (else `python3 scripts/reef-run.py probe` — a headless session the guard does not reach would be a way around every rule). Run one orchestrator at a time: no other `/reef-loop` or runner on this project tonight.

1. **The owner's profile** — `reef/owner.md`. Missing: `reef-run.py contract` (step 2) seeds it from the owner's personal profile, `~/.reef/owner.md` (who they are in every project), so a new project's first night starts from it. Missing both, or older than the newest queue footnote: dispatch `reef:mahmoud` (model `roles.proxy`) to draft or extend it into the scratchpad from the personal profile, the queue footnotes (verbatim decisions), the journal's owner decisions and `AGENTS.md`: principles, product taste, ethics, discipline, what they always keep for themselves. `cp` it to `reef/owner.md`.
2. **The contract** — dispatch `reef:mahmoud` to draft tonight's contract into the scratchpad from the tick and the queue (`$ARGUMENTS` narrows it): a `Rows: <ids>` line (the current batch's rows it will drive), the decisions it may take (plan approvals, design looks, product questions, holes after the hunter's rounds, found-row triage), and the hard limits it never crosses — at least: the release to `branches.release`, secrets and credentials, money and paid accounts, deleting data or branches, Reef's own guard and config, personal data leaving the system, any row not listed. Then `python3 scripts/reef-run.py contract --from <that file>`: it installs `.reef/night/contract.md` and prints the night digest and the exact question.
3. **The one approval** — ONE AskUserQuestion, its first question EXACTLY `Approve night <YYYY-MM-DD> at <digest16>?` (from step 2), options `Approve` / `Edit` / `Cancel`, the `Approve` description: the rows, the decisions delegated, the hard limits, one line each. The hook records `.reef/approvals/night.json` only on Approve at the current digest; an edit to the contract or the profile afterwards approves nothing. On Edit: Mahmoud amends, step 2 again.
4. **Hand over** — tell the owner, as the last line: `python3 scripts/reef-run.py --night` (in a terminal, in the project; `--max-iterations 2` for a first trial while awake). It prints one line per step; `python3 scripts/reef-run.py watch` follows them from any other terminal.

**During the night** (the runner's prompt carries this): every owner decision inside the contract goes to `reef:mahmoud`, never to `questions.md`. A plan approval: Mahmoud writes its report, you `cp` it to `.reef/ci-local/report-mahmoud-<slug>.md`, then `python3 scripts/reef-approval.py --proxy --feature <slug> --report <that file>` — it writes the approval `by: mahmoud (proxy)` only while the night runs, for a row the contract names, at the plan's current digest, with the plan check green. Any other decision: `python3 scripts/reef-queue.py footnote "Mahmoud (proxy, night <date>): <decision> — <why>" --row <id>` — the label first, never passed off as the owner's words. A `WAIT` goes to `questions.md` and the other rows keep moving.

**The morning** — the runner writes `.reef/night/report.md`: Mahmoud's approvals (undo: delete the record), his other decisions (undo: edit the footnote), the merges (undo: `git revert -m 1 <sha>` on `branches.base`), what waits for the owner, sessions and cost.

End with: the approval's result and the hand-over command. `in flight: … / waiting on: … / next: <command>`.
