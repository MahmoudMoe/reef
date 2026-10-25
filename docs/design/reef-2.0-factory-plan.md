# Reef 2.0 — a light software factory

Written 2026-10-25. For a fresh session to build from. Owner: mahmoudmoe. Status: approved direction, not started.

> **بالعربي في سطور:** Reef 2.0 مصنع خفيف. إنت بتتكلم مرة واحدة في الأول (grill → spec → tickets على GitHub)،
> وبعدها loop مكتوب كود (مش LLM) بيسحب الـ tickets الجاهزة، ويبني كل واحدة بـ TDD في worktree لوحدها بالتوازي،
> ويشغّل gate سريع، وبعده review على الكود مقابل الـ spec، وجولتين إصلاح بالكتير، وبعدها PR. ولو التالتة فشلت، ترجعلك.
> بالليل نفس الـ loop بحدود فلوس ووقت، والصبح تلاقي تقرير. مافيش agent بيقرأ الخطة.

## 0. Why 2.0 exists (evidence, not taste)

- Reef 1 is ~14k lines of scripts (35 files), 88 test files, 16 skills, 9 agents. On two real adoptions (2026-10-17,
  2026-10-24/25) it spent a day or more in planning rounds without building a row. Its own record:
  `docs/design/workflow-v2.md` §1 (first), the parked `docs/design/review-on-code-plan.md` (second, with door-by-door
  cause).
- Root causes: rigor was put on prose (plan-reviewer, plan hunter, digest re-approval) instead of code; the owner was
  asked during planning, not once before it; the loop was an LLM session that hit its context ceiling.
- Matt Pocock's skills reach the same conclusion from the other side: "For work that is truly AFK, a deterministic loop
  (Sandcastle, a shell script, a CI job) is faster, cheaper, and more reliable, because no agent makes the orchestration
  decisions." (`mattpocock/skills` `docs/engineering/implement-spec.md:64`).

## 1. Principles (each one traced)

1. **The loop is code; agents work inside it.** No LLM decides what runs next. (implement-spec.md:64)
2. **The human is at the edges.** Before: grill, spec, tickets (the quiz). After: the merge. Nothing in between but a
   ticket handed back as `ready-for-human`. (to-tickets step 4; jonbaldie `FACTORY_MERGE` off by default)
3. **No agent reviews a plan.** The spec and the tickets are checked by a script for shape; agents judge code and its
   behaviour against the spec. (review-on-code-plan.md L1; Pocock `code-review`: two axes, "Standards and Spec")
4. **A ticket is a tracer bullet**: a "narrow but COMPLETE path through every layer", "demoable or verifiable on its
   own", "sized to fit in a single fresh context window". (to-tickets SKILL.md:33)
5. **TDD at agreed seams only.** "Red before green"; "No test is written at an unconfirmed seam"; no tautological tests;
   "Refactoring is not part of the loop. It belongs to the review stage." (tdd SKILL.md:38)
6. **The runner owns git, labels and PRs; agents only edit and commit.** ("Do not push… Do not close the issue. Do not
   edit labels." sandcastle `agent-implement` prompt; jonbaldie "workflows own git")
7. **Everything is bounded**: dollars per stage, minutes per stage, `MAX_ROUNDS = 3` ("At most two automatic fix
   rounds, counting merge conflicts; a third rejected review hands the PR to you" — jonbaldie
   `factory-review.yml:6,40`), one run per issue at a time.
8. **Mechanical rules become checks, not prose.** (Pocock `retro`: a mechanical violation "gets a deterministic check,
   full stop.")
9. **Light**: hard size budgets (§9). A feature that needs more code than its budget is a design smell, not a raise.
10. **Stack-general**: the project's own commands, from config; nothing named after one stack or one project.

## 2. The flow

```
 HUMAN (chat, interactive skills)                 FACTORY (runner = code, headless claude -p per stage)
 ───────────────────────────────                  ─────────────────────────────────────────────────────
 /grill   → shared understanding                  poll: issues labelled ready-for-agent, unblocked, unclaimed
 /spec    → parent issue `spec` (never polled)    claim: assign + label agent:building  (one run per issue)
 /tickets → sub-issues, blocked-by, Touches,      worktree + setup
            quiz → label ready-for-agent          BUILD   (implementer, tdd skill)        → commits
 /triage  → outside issues → one state label      GATE    (runner runs gate.fast; no agent) red → FIX
                                                  REVIEW  spec-axis ‖ standards-axis (read-only, JSON verdict)
                                                  FIX     (implementer + findings)  rounds ≤ 2, 3rd → ready-for-human
                                                  PR      draft → ready; merge: human (default) or auto
                                                  CLOSE   issue closed by the merge; frontier recomputed
```

### 2.1 Labels — one state per issue (the state machine)

| Label | Set by | Meaning |
|---|---|---|
| `spec` | /spec | the parent; never picked up |
| `needs-triage`, `needs-info`, `wontfix` | /triage | Pocock's triage states |
| `ready-for-agent` | the owner (quiz approval) | the only gate into the factory |
| `ready-for-human` | runner | a decision or a 3rd rejection; factory stops touching it |
| `agent:building` | runner | claimed; worktree exists |
| `agent:review` | runner | gate green, judges running |
| `agent:fixing` | runner | round n of 2 |
| `agent:done` | runner | PR ready for merge (Pocock's missing `implemented` state, so it is never re-queued) |
| `agent:blocked` | runner | budget, timeout, setup failure, or `needs-info` from the build |
| `risk:high` | runner, by path | auth, money, personal data, migrations, the factory's own files → extra review axis + human merge |

Category labels (`bug`, `enhancement`) as in Pocock's `triage`. A human assignee pauses the factory on that issue.

### 2.2 Ticket body (written by /tickets, checked by script)

```
Parent: #<spec>
## What            one behaviour, user-visible or API-visible
## Acceptance      AC-1..AC-n, each testable, each citing a user story of the spec (US-n)
## Seams           where the tests go (agreed in the quiz)
## Touches         modules/paths this ticket edits (glob list) — the parallelism key
## Out of scope
```
Blocked-by uses GitHub's native issue dependencies. `factory check-ticket` (script) fails a ticket missing a section,
an AC without a US key, or a `Touches` that is empty.

## 3. Components

| Part | What | Size budget |
|---|---|---|
| `skills/grill` | Pocock's grilling: "Ask the whole frontier in one round", recommended answer each, facts found by sub-agent, decisions by the owner | ≤ 60 lines |
| `skills/spec` | parent issue: Problem, Solution, numbered user stories US-n, Implementation decisions (no file paths), Testing decisions (seams), Out of scope. "Do NOT interview the user" | ≤ 60 |
| `skills/tickets` | tracer-bullet sub-issues + blocked-by + Touches; quiz the owner on granularity and edges; on approval label `ready-for-agent` | ≤ 60 |
| `skills/triage` | outside issues → one category + one state; bugs need a red-capable repro or `needs-info` | ≤ 60 |
| `skills/tdd` | red → green at agreed seams; independent expected values; no refactor in the loop | ≤ 60 |
| `agents/implementer` | builds one ticket; never pushes, never edits labels or `.github/`; ends with JSON `{outcome, seams, slices, notes}` | ≤ 40 |
| `agents/review-spec` | read-only; the diff vs the ticket's ACs and the parent spec; runs the tests/entry point; JSON verdict | ≤ 40 |
| `agents/review-standards` | read-only; the diff vs `CODING_STANDARDS.md` + a smell baseline; JSON verdict | ≤ 40 |
| `agents/review-risk` | only on `risk:high`; "how can every check be green while the defect happens?" on the code | ≤ 40 |
| `factory` (runner) | Python 3 stdlib, one package: poll, claim, worktree, stages, gate, PR, merge, night, report, cost | ≤ 1,500 lines |
| `hooks/guard` | PreToolUse: deny `git push`, `gh` writes, edits under `.github/` and the factory's files, a gate piped into another command (hides the exit code); fail closed | ≤ 200 lines |
| `factory init` | adoption in place: config, labels, `CODING_STANDARDS.md` stub, CI template; never moves or edits project code | inside the runner |

Verdict rule for every judge: a BLOCKER is one of four kinds only — regression, correctness bug, failed AC,
security (carried from Reef 1's verifier). Everything else is a NIT in the PR, never a round.

## 4. The runner (deterministic)

- **Invocation of an agent:** `claude -p --output-format json --json-schema <stage schema> --max-turns N
  --max-budget-usd X --permission-mode dontAsk --allowedTools <stage list> --plugin-dir <factory> --append-system-prompt-file <stage prompt>`
  run with `cwd` = the ticket's worktree. Read `subtype`, `is_error`, `structured_output`, `total_cost_usd` from the JSON
  result — not only the exit code. (code.claude.com/docs/en/headless.md, cli-reference.md; `--json-schema`,
  `--max-budget-usd`, `--plugin-dir`, `--permission-mode dontAsk`, `--bare` confirmed in `claude --help` 2.1.310;
  `--max-turns` is in the docs but not in that `--help` — verify on the Mac's version in M2, else cap by timeout)
- Do **not** use `--bare`: it skips hooks, skills and plugins, and needs an API key. Load the factory with
  `--plugin-dir`; check the `system/init` event's `plugin_errors` and refuse to run on any. (headless.md)
- **Guard probe (carried from Reef 1, fail closed):** once per machine, one headless session tries a forbidden write;
  the runner refuses to start unless the guard denied it and no file exists.
- **Frontier:** open `ready-for-agent` sub-issues whose blockers are *merged* (computed from merged PRs, not GitHub's
  blocked-by count — "stale… mid-run", Pocock implement-spec.md), not claimed.
- **Parallelism:** run up to `parallel` tickets at once; two tickets run together only if their `Touches` globs do not
  overlap (Sandcastle's planner rule, "B and A modify overlapping files or modules", made deterministic). Branch names
  are deterministic: `factory/issue-<n>`.
- **Worktrees:** one per ticket under `.factory/worktrees/<n>`; run `commands.setup` there; re-run it when a lockfile
  changes. `-p` does not clean up: the runner removes the worktree after merge or block. (worktrees.md)
- **Rounds:** gate red or a BLOCKER verdict → `agent:fixing` with the findings; a merge conflict counts as a round;
  `MAX_ROUNDS = 3` total → `ready-for-human` with a comment: what failed, the last verdicts, the branch.
- **PR:** draft on first green gate; body carries Seams/Slices evidence from the implementer's JSON and both verdicts;
  `gh pr ready` after review approves. Merge: `merge: human` (default) or `auto` (squash, gate green, both axes approve,
  no `risk:high`).
- **Records:** one JSON line per stage in `.factory/runs.jsonl` (issue, stage, round, verdict, minutes, cost). No other
  state on disk: GitHub labels are the state; the runner is restartable from labels alone.
- **Budgets:** per stage dollars + timeout (defaults to tune, starting from jonbaldie's: triage 0.50, build 1.50,
  review 0.75 each axis, fix 1.00 USD; 20/15/20 min); per night total; stop after K consecutive blocks.

## 5. Night mode

`factory night --until 07:00 --budget <usd>`: the same loop, plus
- only tickets labelled `ready-for-agent` before the night started (the night is frozen);
- `merge: auto` only if the owner set it for the night; otherwise PRs wait ready;
- stops on the time, the budget, K consecutive blocks, or an empty frontier;
- the morning report: one GitHub issue `Night report <date>` — merged / ready PRs / handed to human (why) / cost /
  minutes per ticket; plus a `retro` pass that proposes environment fixes (a new lint rule, a standards line), never
  applies them.
- Scheduling on the Mac: `launchd` runs `factory poll` every N minutes in the day and `factory night` at a set hour.

## 6. CI — simple, fast, the same command everywhere

- One command, `commands.gate_fast` (lint + typecheck + unit, target < 5 min), run by the runner locally AND by the PR
  workflow. `commands.gate_full` (integration/e2e) runs on the PR only when `risk:high`, and nightly on the base.
- CI on `pull_request` only; the base branch is protected by that check; no second identical run on push to the base
  (the owner's complaint, 2026-10-25: 6/6 on the PR then 6/6 again on main).
- Security scanning (CodeQL etc.) on a schedule, not per push.

## 7. Carried from Reef 1 (proven lessons) / dropped

Carried: judges are fresh, read-only, evidence-required, never resumed ("a reviewer that re-reads its own verdict
defends it"); evidence is the agent's own file/JSON, never the orchestrator's summary; the gate runs once per verdict,
never piped; a guard that fails closed with a probe; adoption in place, nothing moved; proposals under the git dir;
stack facts as data (`reef-stacks.json` idea → `commands` in config); the factory's own code is never the project's
product; cost recorded per stage; the owner's answers in the owner's language.

Dropped: plan-reviewer, plan-pass hunter, digest-bound plan approval, queue.md and footnote ledger (GitHub issues and
comments are the record), tiers table (one `risk:high` label), the LLM orchestrator and HANDOFF/`/clear`,
recalibrate/structure/C4/threat/pentest from the core (optional later plugins).

## 8. Milestones — one PR each, each ends in a demo on a toy repo

| M | Delivers | Demo / done when |
|---|---|---|
| M0 | new repo `reef2` (Reef 1 stays frozen for current adoptions), package skeleton, a **fake `claude`** binary for tests (returns canned JSON per stage), CI on PR | `pytest` green on the skeleton |
| M1 | skills grill, spec, tickets, triage; `factory check-ticket`; `factory init` (labels, config, standards stub) | a spec issue + 3 tickets with blocked-by and Touches on a toy repo |
| M2 | runner, one ticket, sequential: claim → worktree → build → gate → draft PR; guard + probe | one real ticket becomes a draft PR unattended |
| M3 | review on two axes, fix rounds, `MAX_ROUNDS`, `ready-for-human`, `agent:done` | a planted bug is caught by review and fixed in round 1; a forced 3rd failure hands back |
| M4 | frontier, parallel by Touches, merge human/auto, conflict as a round, `risk:high` by path | 3 tickets, 2 in parallel, merged in dependency order |
| M5 | night mode, launchd, budgets, morning report, retro | one night on the toy repo with a report issue |
| M6 | adoption on a real project in place; Reef 1 rows → issues (Reef 1 has `reef-queue.py migrate-to-issues`) | first real ticket merged |
| M7 (optional) | the same stages on GitHub Actions via `anthropics/claude-code-action@v1` (automation mode, `prompt` + `claude_args`) | one ticket built in Actions |

Rule for every milestone: a test red before the change; size budgets checked by a test; no stage merges without its demo.

## 9. Size and speed budgets (tested)

- Runner ≤ 1,500 lines; guard ≤ 200; each skill ≤ 60 lines; each agent ≤ 40; total plugin prose ≤ 600 lines.
- A test (`test_budgets.py`) fails when any budget is exceeded. Raising a budget needs a line in the CHANGELOG with
  the reason.
- Targets to measure from M4 on (not promises): a small ticket from claim to ready PR in ≤ 30 min unattended; owner
  touches per ticket: 1 (merge) after the quiz; rounds per ticket median ≤ 1.

## 10. Decisions the owner makes at the start of the fresh session

1. Repo: new `mahmoudmoe/reef2` (recommended) vs a branch of `reef`.
2. Auth for headless runs: the subscription login on the Mac (no `ANTHROPIC_API_KEY` set; `-p` uses the key whenever
   it is present) vs an API key with a hard budget. The docs do not say whether unattended internal automation on a
   subscription is covered — check the current terms before night mode.
3. Merge default: `human` (recommended) or `auto`.
4. Runner language: Python stdlib (recommended: zero install, matches Reef 1) vs TypeScript + Agent SDK.

## 11. Kickoff prompt for the fresh session

```
Build Reef 2.0 from docs/design/reef-2.0-factory-plan.md (read it whole first). My decisions: <§10 answers>.
Work milestone by milestone (§8): one branch and one PR per milestone, a test red before each change, the fake
claude binary for runner tests, size budgets enforced by test. Before M1, run the grill skill's own rule on me:
one round of numbered questions with your recommended answers, only for what the plan leaves open.
Concise, recommendation first, reply in my language.
```

## Sources

- github.com/mattpocock/skills @5beb35b — `skills/engineering/{to-spec,to-tickets,implement,implement-spec,tdd,code-review,triage,diagnosing-bugs,wayfinder}`, `skills/productivity/grilling`, `docs/engineering/{implement-spec,triage,to-spec}.md`
- github.com/mattpocock/sandcastle @a53e227 — `src/templates/{simple-loop,sequential-reviewer,parallel-planner,parallel-planner-with-review}`, `.github/workflows/agent-*.yml`
- github.com/jonbaldie/software-factory @e894089 — `template/.github/workflows/factory-*.yml` (inspired by Pocock; not his)
- code.claude.com/docs/en/{headless,cli-reference,hooks,worktrees,github-actions,authentication}.md (fetched 2026-10-25)
- aihero.dev articles on Ralph/AFK: found by search, not opened — nothing here depends on them.
