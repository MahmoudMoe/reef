---
name: reef-watch
description: The runner's live log inside Claude Code — the last lines now, or follow it for a bounded while (`/reef-watch follow`); never an unbounded tail in a session. Use when the owner says "/reef-watch", "show me the log", "what is the runner doing", or "is autopilot moving".
argument-hint: <empty | follow | the lines to show>
---

# Reef watch

The runner writes one line per step to `.reef/run/live.log` (`→` an agent or a job started, `←` returned with its verdict, the orchestrator's own words, a decision, a merge). This skill shows it from a session; the screen (`reef` in a terminal) carries the last eight lines under the WORK table and the whole log on `w`.

1. `$ARGUMENTS` empty, or a number N: `python3 scripts/reef-run.py watch --tail <N, else 40> --for 0` — the last lines and the runner's state, at once. Show them as they are, one line each; add nothing.
2. `$ARGUMENTS` = `follow`: `python3 scripts/reef-run.py watch --for 100` — new lines for a hundred seconds, then it returns and says the runner still runs; run it again to keep following. NEVER run `watch` here without `--for`: a session's tool holds until the command returns, and an unbounded watch returns when the runner ends.
3. Exit 2 means the loop waits on the owner: the output's last line names it; `python3 scripts/reef` (the screen) shows every wait with its command. Start nothing from here: the runner is the orchestrator.
