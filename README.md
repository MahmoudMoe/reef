<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.svg">
  <img src="assets/banner-light.svg" alt="Reef — agentic coding pipeline" width="100%">
</picture>

<p align="center">
  <img alt="version" src="https://img.shields.io/badge/version-0.3.0-D94F35?style=flat-square">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-0E7C7B?style=flat-square">
  <img alt="claude code" src="https://img.shields.io/badge/claude_code-plugin-182B33?style=flat-square">
  <img alt="status" src="https://img.shields.io/badge/status-pilot_(n%3D1)-B07C1F?style=flat-square">
</p>

# Reef

> *A coral reef grows one calcified layer at a time — each organism leaves a hard structure the next builds on. Reef works the same way: every task, ADR, and glossary line is a fossilized layer that outlives the session that wrote it.*

Token-frugal agentic coding pipeline for Claude Code. Pocock front (grilling, vertical slices, one seam thinking, TDD), Iusztin back (author≠verifier, retry caps, artifacts-as-memory) — thinned, and with the discipline moved from prose into mechanisms.

## Why (design record)
Full multi-agent setups burn tokens on ceremony; pure manual workflows have no safety rails. Reef's red-team-derived rules:
- **Every "hard" rule is code, and every gate has a test that shows it going red** (`tests/` — a gate never observed failing on the defect it exists to catch is decoration).
- **The cap advances as a side effect of the action, not of model discipline.** `scripts/reef-attempt` records failures as data in the task file (survives compaction/restart), and the PreToolUse guard independently refuses implementer dispatches on blocked/at-cap tasks and bumps a `dispatches:` odometer on every *allowed* dispatch (a denied one never bumps) — a model that "forgets" the script still cannot loop forever.
- **Author ≠ verifier, enforced.** Fresh-context judge on `design` tasks only; `scripts/reef-snapshot.sh` content-hashes HEAD+index+worktree around the judge's run (a porcelain status diff cannot see content edits). `mech` tasks skip the judge: gate + golden-output test — a convention the reef-task orchestrator requires, not code (2 of 4 judge runs in the pilot bought nothing).
- **A finding on a claimed AC = FAIL**, through the cap — never laundered into backlog. The runlog records escaped defects and real usage numbers, never self-reported memory.
- **No failing test = no task.** Slices that can't go red are padding — and `reef-plan-check` refuses a task whose criteria are all manual.
- **The human learns**: `design` tasks require the human to write the `## Decision` block themselves before code (the check strips comments, so the template placeholder does not count).

### Enforcement map — code vs prose (honesty ledger)
| Rule | Enforced by | Layer |
|---|---|---|
| Retry cap / same-failure-twice | `reef-attempt` (data) + `reef-guard.py` deny at dispatch + `dispatches:` odometer | **code** |
| Plan edited after approval → re-review | `reef-plan-check.py --verify-stamp`, re-checked by the guard at every implementer dispatch | **code** |
| Commit gate tests the index | `.githooks/pre-commit` (+ `pre-merge-commit`, same semantics): back up the index, set tracked files to it, run the gate, restore the exact index + unstaged patch — no stash, no `--3way`; a failed restore rejects the commit loudly (never a silent thinner tree). Merge state / intent-to-add / clean-filtered paths fall back to a LOUD in-place run | **code** |
| Push gate | none by design — a worktree gate at push time only false-rejects | **CI is the wall** |
| Bypass spellings (`--no-verify`, `-n`, `-c core.hookspath`, env smuggling, `rm .githooks`) | `reef-guard.py` (tokenizing PreToolUse hook) | **tripwire** — a blocklist over a shell surface is never complete; CI is the wall |
| Verifier didn't touch the tree | `reef-snapshot.sh` before/after | code hash, **prose trigger** (the orchestrator must run it) |
| Golden-output test on mech tasks | verifier contract | **prose** |
| "Never dispatch without reef-attempt" | guard denies the un-protocoled dispatch; the WHY (signatures) still needs the script called | code + prose |

## Install
```
/plugin marketplace add MahmoudMoe/reef
/plugin install reef@mahmoudmoe
```
Then in your project: `/reef-init` (detects stack, writes .reef/config.json, installs gates — after any fresh clone run `make setup`).

## Who runs what (routing)
| Stage | Runs as | Model / effort | Decided by |
|---|---|---|---|
| Grill / plan / gate | main session | session model | you |
| Implement `mech` (tiny diff) | main session inline | session model | reef-task §2 |
| Implement (normal) | `implementer` agent | printed by `reef-attempt`: attempt 1 = `roles.author` at the task's `effort:` base, after any FAIL = high | reef-attempt + .reef/config.json |
| Plan review | `scripts/reef-plan-check.py` (blocking) + `plan-reviewer` agent | free + fable | `reef-plan-review`; auto-invoked by reef-task on a stale stamp |
| Verify `mech` | no agent — gate + golden test | free | task frontmatter `verify: gate-only` |
| Verify `design` | `verifier` agent (fresh context) | opus (agent default) | task frontmatter `verify: judge` |
| Review (acceptance/diff) | main session, fresh-context passes | session model | reef-review |
Agent files carry a DEFAULT model (the ladder base) — but the dispatch-time model from `reef-attempt` always overrides it (per-call model > frontmatter). One source of truth for escalation: the script. Effort escalation travels in the dispatch prompt ("reasoning effort: high"), since agent frontmatter has no working effort key (red-team finding #5).

## Flow
`/reef-plan <spec>` → grill → vertical slices → ONE human gate → `/reef-plan-review` (deterministic checks + semantic review) → `/reef-task` (implement→verify→commit per task, mechanical caps) → `/reef-review` (push → PR → acceptance → diff review → CI, rollup tasks under the same caps) → you squash-merge.

## Layout
skills/ (init, plan, plan-review, task, verify, review) · commands/ (`/reef` status overview + `/reef-plan`, `/reef-task`, `/reef-review` wrappers) · agents/ (implementer, verifier, plan-reviewer — each carries a DEFAULT model; the dispatch-time model from reef-attempt overrides it) · scripts/ (reef-gate.sh, reef-attempt, reef-guard.py, reef-snapshot.sh, reef-plan-check.py) · hooks/hooks.json (PreToolUse guard, wired to reef-guard.py) · schemas/task.schema.json · templates/ (pre-commit, config, task, adr, glossary, runlog) · tests/ (sabotage suites: every gate shown red) · .github/workflows/ci.yml (runs the suites on ubuntu+macos)

## Acknowledgments
Reef is an original implementation, but its process ideas stand on two open projects:
- [iusztinpaul/squid](https://github.com/iusztinpaul/squid) (Apache-2.0) — the agent-team lifecycle, author/verifier separation, retry-cap concept, artifacts-as-memory.
- [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) — grilling, vertical-slice/tracer-bullet rules (a few planning heuristics in reef-plan closely paraphrase that repo's wording), spec/ticket discipline.
No code was copied from either project. Thanks to Paul Iusztin and Matt Pocock for publishing their work openly.
