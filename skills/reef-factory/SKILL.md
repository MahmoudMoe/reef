---
name: reef-factory
description: Build a queue row on GitHub Actions — accept the offered workflow, set the token, label a row `reef-ready`, read the job's state. Use when the owner says "/reef-factory" or wants rows built without the laptop.
argument-hint: <empty | a row id | status <id> | log <id>>
---

# Reef Factory — a row built in the Actions sandbox

The factory is ONE job per row: `.github/workflows/reef-factory.yml` runs `python3 scripts/reef-factory.py row`, which checks who asked, proves the guard in the sandbox, resumes the row's branch from the forge, reads the owner's approval from the issue, runs the row's state machine, pushes the branch back and writes the row's state as a label. This skill is the owner's side of it. Read `.reef/config.json` (`branches.base`, `queue.home` must be `issues`).

## `$ARGUMENTS` empty — status, one screen
1. The workflow: `ls .github/workflows/reef-factory.yml`. Missing → `python3 scripts/reef-init.py` prints `OFFERED  .github/workflows/reef-factory.yml`; then `python3 scripts/reef-init.py --accept .github/workflows/reef-factory.yml`, commit it on `branches.base`, push. Say so and stop here if it is missing.
2. The token: `gh secret list`. One of `ANTHROPIC_API_KEY` (an API key, billed per token) or `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`, a Claude subscription). Neither → name the two choices and the command `gh secret set <NAME>`; the OWNER sets it, in their terminal, never the agent, never a value in the chat.
3. The base is protected: `gh api repos/{owner}/{repo}/branches/<base>/protection`. An error → the factory refuses to run; say that the owner protects the branch in the repository settings.
4. The trigger label exists: `gh label create reef-ready --force --color 0052cc` (the colour `reef-queue.py` uses; the job creates the state labels itself).
5. The last runs: `gh run list --workflow reef-factory.yml --limit 5`.
Print the five lines, each with its fix when red, and stop.

## `$ARGUMENTS` = a row id — build it there
1. `python3 scripts/reef-queue.py row-issue <id>` → the issue number. No issue → the row is not on GitHub; `/reef-loop` plans it first.
2. `gh issue edit <#n> --add-label reef-ready`. The labeler must have ADMIN permission on the repository, and so must the issue's author (the body is the planner's spec); the job refuses otherwise and says why in its log.
3. `gh run list --workflow reef-factory.yml --limit 1` → the run that started. Print its id and `gh run watch <run-id>` for a terminal.

## `$ARGUMENTS` = `status <id>` | `log <id>` — where it stands
1. `gh issue view <#n> --json labels` → one of `reef-building` (a job is on it), `reef-review` (at the review or the merge), `reef-waiting-owner` (needs you).
2. `log`: the latest run's log, last 40 lines: `gh run list --workflow reef-factory.yml --limit 1 --json databaseId` then `gh run view <run-id> --log | tail -40` (redirect to a file first if the guard objects to the pipe). The `reef-run` artifact holds `run.log` and `gate.json`.
3. `reef-waiting-owner` with a plan to approve: `git fetch origin` then `python3 scripts/reef-row.py state <id>` — the plan is on the pushed branch and the detail line carries the question, exactly `Approve plan <slug> at <digest16>?`. The owner writes it as a comment on the row's issue, UNEDITED, then re-labels `reef-ready`; the next job records it (`reef-approval.py --from-issue`: the newest admin comment decides, an edited one is refused, a stale digest is refused). Any other wait is a `reef-question` issue: answer it, re-label.

## Say once, at the end
Pushes made with `GITHUB_TOKEN` start no CI: keep `ci.feature_gate: local` (the job's full gate is the evidence) or add a fine-grained `REEF_TOKEN` scoped to this repository (contents, issues, pull requests), never a classic PAT. Minutes count on a private repository, and every job installs the project from scratch. A job ends after six hours; the next one resumes from the pushed branch. No schedule drains `reef-ready` rows yet: one label, one job.
