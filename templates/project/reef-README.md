# {{name}} — where Reef keeps things

Rendered by `reef-init` and refreshed on every run; edit it and `reef-init --keep <this file>` keeps your version.
This is the map a person needs when the tree looks wrong: the plan is not where you expected, there are two
`AGENTS.md`, there are untracked folders you did not create.

## Branches

| Branch | What lives there |
|---|---|
| `{{release}}` | What ships. The loop never pushes here except through the release PR at a batch's end. |
| `{{base}}` | The integration branch and the only home of the records: `{{queue_path}}`, its archive, `{{journal_path}}`, `{{adr_path}}/`, `HANDOFF.md`. |
| `{{feature_prefix}}<slug>` | One per queue row. The plan (`{{features_path}}/<slug>/SPEC.md`, `tasks/`, `adr/`) lives here until the row's PR merges into `{{base}}`. Until then an editor open on `{{base}}` shows no plan: that is expected, not lost work. |
| `task/<id>-<slug>` | One per task, branched from the feature branch and merged back into it by the loop. |

## Worktrees (`{{worktrees_dir}}/`)

- `{{worktrees_dir}}/<slug>`: a full checkout of a feature branch, with its own dependencies and its own copy of
  every file, `AGENTS.md` included. Two `AGENTS.md` means two checkouts, not two sources of truth.
- `{{worktrees_dir}}/<id>`: a task's checkout, removed when the row closes.
- Never edit there by hand. Never `git add -A` anywhere: an untracked `?` entry is usually the loop's uncommitted
  plan or a worktree.

## Records — written once, never rewritten by Reef

`{{queue_path}}` and its archive · `{{journal_path}}` · `HANDOFF.md` · `{{constitution_path}}` · `{{adr_path}}/*` ·
`{{glossary_path}}` · `.reef/approvals/` and `.reef/review/` (written by the approval hook and `reef-record` only).

## Rendered — Reef's own, refreshed by `reef-init`

`AGENTS.md` (your blocks inside the markers survive) · this file · `.github/workflows/ci.yml` · `.githooks/*` ·
`scripts/reef-*`. A rendering that would change a file you edited lands in `.git/reef/proposed/` instead; accept it with
`python3 scripts/reef-init.py --accept <path>` or keep yours with `--keep <path>`.

## The loop's state (`.reef/`, per machine, gitignored)

`loop.json` (active · wait · stop) · `inflight/` and `verifying/` (who is working) · `ci-local/` (hand-backs and
judges' reports) · `cost/` (orchestrator cost per task and per feature) · `status.html` (the page the Stop hook
refreshes; open it in a browser).

## What you type

`/reef-loop` to run · `/clear` when the loop asks · `/reef-doctor` when something looks off ·
`python3 <plugin>/scripts/reef-update.py --commit` to pull a new Reef into this project.
