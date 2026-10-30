---
name: reef-run
description: Run the loop in the background from Claude Code — scripts/reef-run.py starts /reef-loop in a fresh headless session whenever the last one fills its context, detached. Also shows or stops it. Use when the owner says "/reef-run", "run the loop in the background", or "stop the runner".
argument-hint: <empty | status | stop | the most sessions to run>
---

# Reef Run — the loop in the background

Not a long session moved to the background: that one re-reads a full context at every step, unwatched (2026-10-24: three days near the ceiling, then a collision on develop).

1. `python3 scripts/reef-run.py status`. A live runner, or `$ARGUMENTS` = `status`: report it and stop. A recorded wait in `.reef/loop.json` is not a reason to hold back (2026-10-28: the skill refused to start on a wait the owner had already answered): the runner's first session clears it and asks the row machine; only a live runner stops this step.
2. `$ARGUMENTS` = `stop`: `python3 scripts/reef-run.py stop` (it ends after its current session, never mid-merge). Report and stop.
2b. `$ARGUMENTS` = `autopilot`: `python3 scripts/reef-run.py --autopilot --detach` — the runner on its own under the approved `reef/proxy.md` (it refuses, naming the one approval question, when the contract is not approved); `autopilot off` is `stop`. Report the pid and stop.
3. No ok for auto mode in `.reef/run/gate.json`: `python3 scripts/reef-run.py probe --permission-mode auto` first; a failed probe stops here.
4. `python3 scripts/reef-run.py --detach` (`--max-iterations <n>` when `$ARGUMENTS` is a number). It refuses before detaching, or returns the runner's pid.
5. No loop work in this session afterwards: the runner's sessions hold the project.

The runner the owner starts IS the orchestrator (2026-10-28, the first night: three sessions burned on a hold a dead desktop session left): it takes a loop hold another session left and says so; two sessions ending on the same wait stop it as no progress. Every wait it prints names the terminal command that answers it — `python3 scripts/reef-approval.py --owner "<the exact question>"` for an approval, `reef-queue.py footnote … --row <id>` for a filed question — never a pointer to another session. From a terminal, `reef` is the owner's one entry point (`reef run`, `reef night start`, `reef status`, `reef doctor`, `reef update`, `reef setup prove`, `reef factory <row>`, `reef cost`); `reef --all` lists every script.

End with the pid, then `reef-run.py status`, `watch` (a terminal) and `stop`. A line the owner will type carries real values — the slug, the digest, read from `reef-row.py state <row> --json` — never a placeholder like `<slug>`.

## The factory (v3 phase 7) — rows built without the owner's machine
`reef-init` OFFERS `.github/workflows/reef-factory.yml` and never writes it: the owner reads its header (minutes, the model key as the repository secret `ANTHROPIC_API_KEY`, the six-hour limit) and places it with `reef-init --accept .github/workflows/reef-factory.yml`. Then a row's issue labelled `reef-ready` by an admin builds in the Actions sandbox through ONE command, `python3 scripts/reef-factory.py row --issue <#n> --actor <login>` (or `--row <id>` from `workflow_dispatch`): the labeler and the issue's author must be admins, the base branch protected; the row's feature branch is resumed from the forge; the guard must reach a headless session there (`reef-run.py probe`, fail closed); the owner's plan approval is read from an UNEDITED comment on the row's issue (`reef-approval.py --from-issue <row>` — exactly `Approve plan <slug> at <digest16>?`, by an admin); `reef-run.py --row <row>` runs with the plugin loaded (`REEF_CLAUDE_ARGS=--plugin-dir …`); the feature branch is pushed back and the row's state written as one label (`reef-queue.py label-state <row>`: `reef-building`, `reef-review`, `reef-waiting-owner`). The job's log and its `reef-run` artifact are the observability; the owner's questions reach them as `reef-question` issues. GITHUB_TOKEN pushes start no CI: keep `ci.feature_gate: local` there, or add a fine-grained `REEF_TOKEN` scoped to the repository.
