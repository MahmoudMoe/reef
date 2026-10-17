# Usability and autopilot maturity — the plan after first contact

Written 2026-10-17, after two days of running Reef on a real project (qassimha: one feature closed by the loop,
batch 2 in planning; PRs #13–#36 fixed what first contact found). Two dimensions scored lowest in the owner's
review: **ease of use** (weak → medium) and **autopilot maturity** (unproven → proven for one row). This is the plan
for both: what we observed, what the field does, and the changes in order, each with the mechanism and the measure.

## 1. What we observed

### Ease of use — where the owner got lost or did busywork
| Moment | What happened | Root cause |
|---|---|---|
| "Where is the feature on develop?" | The plan and code live on `feat/<slug>` until the PR merges; VS Code showed an empty `reef/features/` | Nothing on disk explains the branch/worktree/record layout to a human |
| "Why two AGENTS.md?" / "What is `.reef/worktrees/102`?" | Every worktree is a full checkout | Same |
| Pull dance after every Reef fix | `git pull` + `/plugin marketplace update` + `/reload-plugins` + `reef-init` + commit, with an `--accept` step that sometimes applies and sometimes says "nothing proposed" | No single `update` command; the plugin clone doubled as a working tree |
| `reef-init` proposals that would revert work | ci.yml, glossary, AGENTS.md owner text | Fixed in #27/#32; the general shape ("a rendered file becomes the project's") needed `--keep` |
| 28 advisories as questions; hunter 5 rounds; approvals voided by cosmetics | Sessions spent on planning, no code | Fixed in #33/#35; no round caps existed |
| `Exit code 1` after `ls` of a missing dir | Looks like a failure | Orchestrator command hygiene |
| "What do I run next?" | Owner asked after every stop | The tick's `next command:` is there but buried; the orchestrator's last message varies |
| `/clear` every 150k | The owner is the loop's restart button | No external runner; the chat session is the orchestrator |

### Autopilot — what is proven and what is not
Proven: one row through plan → review → task graph → review → merge → close, zero fix rounds; re-entry after
`/clear` from disk four times; the guard's denials; the reserve. Unproven: a real verifier FAIL and the attempt
counter; three features building in parallel; the release to `main` (security pass, `reef-repo`, `/reef-threat`,
`/reef-c4`); found-row triage (18 of 26 open rows are `found`); any session that did not need the owner to `/clear`.

## 2. What the field does (October 2026)

- **quantum-loop** (closest shape): brainstorm → PRD → DAG in one `quantum.json` → `ql-execute`; an **external
  shell runner** (`quantum-loop.sh --max-iterations --parallel`) spawns a fresh Claude Code instance per iteration, so
  context never needs a human reset; stories have five states and a `staleThresholdMinutes` auto-reset; per-story
  worktrees under `.ql-wt/`; waves exclude stories sharing file paths; auto-generated `docs/post-mortems/`. No token
  accounting. ([repo](https://github.com/andyzengmath/quantum-loop))
- **Ralph Wiggum** (official plugin): a Stop hook re-feeds the prompt until done; progress in files and git; fresh
  context on restart; `--max-iterations`; run it sandboxed. ([technique](https://claudefa.st/blog/guide/mechanics/ralph-wiggum-technique),
  [VentureBeat](https://venturebeat.com/ai/how-ralph-wiggum-went-from-the-simpsons-to-the-biggest-name-in-ai-right-now))
- **claude-code-harness**: `/harness-progress` renders a **progress page** that refreshes every 60 s, with an
  acceptance view (criteria passed / failed / unverified); `--resume latest`; a documented small first request as
  onboarding. ([repo](https://github.com/Chachamaru127/claude-code-harness))
- **GitHub spec-kit**: constitution → specify → plan → tasks → implement; 30+ integrations, v0.10 hooks per event;
  ~111k stars — adoption through simplicity and docs, not through guards. ([overview](https://themenonlab.blog/blog/github-spec-kit-spec-driven-development-ai-coding))
- **BMAD v6**: personas and story files; "scale-adaptive planning" (ceremony sized to the work). ([guide](https://redreamality.com/garden/notes/bmad-method-guide/))
- **Superpowers**: brainstorm → write-plan → execute-plan with review checkpoints; skills activate on their own;
  worktree isolation and TDD. ([install docs](https://www.mintlify.com/obra/superpowers/installation/claude-code))
- **Claude Code itself (2.1.29x–2.1.302)**: dynamic workflows (`/workflows`: a JS script orchestrating many
  subagents in the background, resumable), agent teams, `/loop` paced by `ScheduleWakeup`, `-w`/`--worktree`
  sessions with `WorktreeCreate`/`WorktreeRemove` hooks, `autoCompactWindow` per subagent, idle compaction,
  `onFailure: block` hooks, `/advisor`, auto mode with a classifier. ([changelog](https://code.claude.com/docs/en/changelog),
  [dynamic workflows](https://alexop.dev/posts/claude-code-workflows-deterministic-orchestration))

What Reef has that none of these have: approvals and verdicts as **records bound to digests and commits**, a guard
that **denies** rather than instructs, snapshot-checked judges, an adversarial pass on plans and guards, caps that
stop and escalate, and measured cost per task and role. What Reef lacks that several have: an external runner, a
human-readable progress page, a guided first run, and a one-command update.

## 3. The plan

Each item: the problem → the change → **prose** (a skill line) or **mechanism** (a script, a hook, a check) → the measure.
Mechanisms are preferred; prose is the fallback until measurement says the prose is not enough.

### Track A — ease of use

**A1. One command to update, one to diagnose.** `scripts/reef-update` (plugin): `git pull` the plugin clone,
`reef-init` the project with the pinned name, show the one-line summary, and print the two Claude Code commands to
run. `/reef:doctor`: plugin vs project script versions, the plugin clone's branch (must be `main`), worktrees and
their branches, `gh auth status`, Docker, the queue's home, open proposals. Mechanism. Measure: the owner never
types a `--accept` or a `--keep` without the doctor naming it first.

**A2. A progress page for humans.** `reef-watch --html` writes `.reef/status.html` (tick, rows with state, what is
waiting on the owner, sessions and their max context, found-row count against the triage rule) and `/reef:watch`
opens it; refreshed by the Stop hook. Mechanism. Measure: the owner stops asking "where are we" in chat.

**A3. The next command is always one line.** The tick's `next command:` becomes the orchestrator's mandatory last
line in every reply (the Stop hook already reads the tick; it can refuse a turn whose last line is not that
command). Mechanism. Measure: zero "what do I run now" questions per batch.

**A4. A map on disk.** `reef-init` renders `reef/README.md`: this project's branches, where a plan lives before and
after merge, what `.reef/worktrees/` holds and when it is removed, which files are records, which are rendered,
which are the project's own (`--keep`). Rendered with the project's real paths. Mechanism (template). Measure: the
"why two AGENTS.md" class of question goes away.

**A5. Quiet commands.** `reef-init` prints the summary and the non-`skipped` lines only (`--verbose` for all);
`reef-plan-check` prints FAIL/WARN and the digest only; the task skill forbids `ls x 2>&1` probes that print
`Exit code 1` to the owner. Mechanism for the scripts, prose for the probe. Measure: `tool_result:Bash` share.

**A6. Fewer, better questions.** Done: batched grill, advisories as a list, hunter round cap, no cosmetic edits after
approval. Add: when several plans reach the gate together, ONE question with "Approve all / pick" plus one line per
plan. Prose. Measure: owner questions per planned row ≤ 3.

**A7. A guided first run.** `/reef:start`: on an empty repo, runs init with a tiny sample row ("a page that says
hello") through the whole loop in one sitting with explanations at each stop — the way claude-code-harness
documents a small first request, but driven. Prose + a sample. Measure: a new owner reaches a merged row in one
session without asking for help.

### Track B — autopilot maturity

**B1. An external runner (the owner is not the restart button).** `scripts/reef-run` (Ralph-style): loops
`claude -p "/reef:loop" --permission-mode auto` with a fresh context per iteration, `--max-iterations`, reading
`.reef/loop.json` between iterations: stops on `stop`, on a `wait` that names the owner (a question, USER ACTION
REQUIRED), on the cap; otherwise re-enters from `HANDOFF.md`. Each iteration is one session, so the 150k ceiling
becomes an iteration boundary, not an interruption. Sandboxed by default (a container or `--worktree`). Mechanism.
Measure: a batch runs to its owner questions with zero `/clear` typed.

**B2. The loop as a dynamic workflow (spike).** Reef's tick is already deterministic data; a workflow script
(`/workflows`) could run each step as a fresh agent in the background with the orchestrator's state in files, not in
a chat window. Research preview: prototype one feature end to end, compare cost and wall time against B1. Decide by
measurement. Mechanism (if adopted).

**B3. Stale work resets itself.** `inflight_stale_minutes` already surfaces "returned, unmarged"; add the policy:
a task in flight past the threshold with no hand-back is re-dispatched once with the previous attempt's log, then
blocked. Mechanism. Measure: no task waits on a dead agent for more than one threshold.

**B4. Prove the unproven paths with drills on the trial project.** (a) A verifier FAIL: inject a failing Proof row
and watch `reef-attempt` count, the same-signature block, and the human unblock. (b) Three features in parallel:
batch 2 as planned, with `graph.parallel` and the collision table. (c) A release: `develop → main` with the security
pass, `reef-repo`, `/reef-threat`, `/reef-c4` on the trial, GitGuardian dismissed. Each drill ends with the numbers
in `docs/perf/`. Measure: every row of §1's "unproven" list has a dated run.

**B5. Found-row triage as a command.** `reef-queue.py triage`: rows `found` and untouched for two batches, grouped
by module, with the rule-7 options (promote once with a reason, merge into a design row, delete) as ONE owner
question. Mechanism. Measure: found rows open ≤ planned rows at the start of each batch.

**B6. Cost in the record.** The close-out writes `orchestrator growth` per task (from `reef-cost.py`) into the
journal; `caps.task_growth` warns in the Stop hook when a task exceeds it. Mechanism. Measure: the number exists for
every merged task; the cap comes from the median × 2 after ten tasks, not from a guess.

**B7. Ceremony sized to the row.** Tiers exist; check the defaults do what BMAD calls scale-adaptive: a `light`
row has no hunter and no semantic plan review (true today), a `full` row has no hunter on the plan (true), and a
`found` row whose fix is one file defaults to `light` unless the path classes say otherwise. Mechanism (`reef-tier`).
Measure: planning cost per `found` row under 10k.

## 4. Order and milestones

| Milestone | Items | Done when |
|---|---|---|
| M1 (this week) | A3, A5, A6, B4a, B6 | batch 2 closes with the numbers in `docs/perf/`; a FAIL drill recorded |
| M2 | A1, A2, A4, B5 | `reef-update`, `/reef:doctor`, `status.html`, `reef/README.md`, `triage` shipped and used on the trial |
| M3 | B1, B4b, B4c | a batch runs under `reef-run` to its owner questions; a release lands on `main` |
| M4 | B2, A7, B3, B7 | the workflow spike measured; `/reef:start` tried by someone who is not the author |

The measures in §3 are the acceptance criteria; the owner's review table (ease of use, autopilot maturity) is
re-scored after each milestone with `reef-cost` and `reef-watch` numbers, not impressions.
