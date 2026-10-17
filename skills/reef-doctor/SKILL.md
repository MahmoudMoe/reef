---
name: reef-doctor
description: One screen on what is wrong with this project's Reef and the command that fixes each thing — the plugin clone's branch and freshness, project scripts behind the plugin, the queue's home, worktrees, the loop's state, gh and Docker, waiting proposals. Use when the owner asks "what's wrong", "why two AGENTS.md", "where is the plan", or before pulling a new Reef, or says "/reef-doctor".
---

# Reef Doctor

Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/reef-doctor.py --repo . --plugin ${CLAUDE_PLUGIN_ROOT}` and show its lines as they are (OK / WARN / FAIL, the fix on the same line). Add `--fetch` when the owner asks whether the plugin is up to date. Do not run the fixes yourself unless the owner says so: the point of the screen is that the owner never types `--accept`, `--keep`, a checkout or a pull without the doctor naming it first.

- A `FAIL` on the queue's home (a feature worktree carrying queue edits) is the loop's own mistake to undo, with the printed command, on the next `/reef-loop`.
- `WARN scripts:` means the project's copies are behind the plugin: the fix is `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/reef-update.py --repo . --commit`, which pulls the plugin clone, refreshes the project and commits Reef's own files only — then `/plugin marketplace update <marketplace>` and `/reload-plugins`.
- The map of the tree (branches, worktrees, records, rendered files) is `reef/README.md` (or `docs/REEF.md` on a 0.5 layout); point the owner there for the "why does it look like this" questions.
- `status page:` names `.reef/status.html`, refreshed by the Stop hook on every tick; the owner opens it in a browser instead of asking "where are we" in chat.
