---
name: reef-run
description: Run the loop in the background from Claude Code — scripts/reef-run.py starts /reef-loop in a fresh headless session whenever the last one fills its context, detached. Also shows or stops it. Use when the owner says "/reef-run", "run the loop in the background", or "stop the runner".
argument-hint: <empty | status | stop | the most sessions to run>
---

# Reef Run — the loop in the background

Not a long session moved to the background: that one re-reads a full context at every step, unwatched (2026-10-24: three days near the ceiling, then a collision on develop).

1. `python3 scripts/reef-run.py status`. A live runner, or `$ARGUMENTS` = `status`: report it and stop.
2. `$ARGUMENTS` = `stop`: `python3 scripts/reef-run.py stop` (it ends after its current session, never mid-merge). Report and stop.
3. No ok for auto mode in `.reef/run/gate.json`: `python3 scripts/reef-run.py probe --permission-mode auto` first; a failed probe stops here.
4. `python3 scripts/reef-run.py --detach` (`--max-iterations <n>` when `$ARGUMENTS` is a number). It refuses before detaching, or returns the runner's pid.
5. No loop work in this session afterwards: the runner's sessions hold the project.

End with the pid, then `reef-run.py status`, `watch` (a terminal) and `stop`.

## The factory (v3 phase 7) — rows built without the owner's machine
`reef-init` OFFERS `.github/workflows/reef-factory.yml` and never writes it: the owner reads its header (minutes, the model key as the repository secret `ANTHROPIC_API_KEY`, the six-hour limit) and places it with `reef-init --accept .github/workflows/reef-factory.yml`. Then a row's issue labelled `reef-ready` builds in the Actions sandbox: the job proves the guard reaches a headless session there (`reef-run.py probe`, fail closed), records the owner's plan approval from a comment on the row's issue (`reef-approval.py --from-issue <row>` — exactly `Approve plan <slug> at <digest16>?`, by an admin), runs `reef-run.py --row <row>` with the plugin loaded (`REEF_CLAUDE_ARGS=--plugin-dir …`), and writes the row's state back as one label (`reef-queue.py label-state <row>`: `reef-building`, `reef-review`, `reef-waiting-owner`); the nightly schedule runs every ready row. The job's log and its `reef-run` artifact are the observability; the owner's questions reach them as `reef-question` issues.
