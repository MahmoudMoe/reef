# Cost benchmark: Reef vs spec-kit vs Squid — 2026-11-04

The question: is Reef expensive? The test: the same two small features on the same tiny Python project, built by each
tool, measured in dollars per feature and per shipped line.

## Result

| | Reef (autopilot) | spec-kit 1.1.4.dev0 | Squid 1.1.7 (6e6f77c) |
|---|---|---|---|
| Total $ | **$5.99** | **$5.17** | **$8.53** |
| $ per feature (2 features) | $2.99 | $2.59 | $4.26 |
| Production lines added (`src/`) | 38 (3 removed) | 46 (2 removed) | 71 (2 removed) |
| Test lines added (`tests/`) | 126 | 245 | 246 |
| $ per production line | $0.158 | $0.112 | $0.120 |
| $ per shipped line (prod + test) | $0.037 | $0.018 | $0.027 |
| Tests passing at the end | 19 / 19 | 47 / 47 | 47 / 47 |
| Claude sessions | 7 (13 runner ticks) + 1 killed | 9 (one per command) | 2 conversations (4 invocations) |
| Agent time | ~18 min of session time; ~33 min elapsed without the owner's overnight wait | 11.0 min | 26.8 min |
| Review | Acceptance reviewer per row (sonnet), full local gate per row, PR per row on GitHub, merged by the loop | None. Only its own plan → tasks → implement; `/speckit-analyze` is optional and was not run | Tester per task, PA acceptance + PR-Reviewer per feature, blocks fixed. No PR or CI (no remote; see limits) |
| Security | Release security pass over the batch (2 HIGHs filed as rows) | None | None |
| Non-code artifacts | Queue, plans, evidence, journal (process files) | ~1,300 lines of spec/plan/tasks/contracts markdown | Task files with review logs |

Per feature, Reef is **16% above spec-kit and 30% below Squid**. Per line it looks worst only because it wrote the least
code for the same behaviour: 38 production lines against 46 and 71.

## Verdict

Reef is not expensive. About $3 per small feature puts it within 16% of spec-kit and well under Squid. The extra buys
work spec-kit skips entirely: a review per row, a gated merge through a real PR, and a release security pass that found
two real issues. Squid did similar review work and cost more. "$ per line" goes against Reef, but that reflects Reef's
smaller diffs, not waste: the same features in fewer lines. The real waste is narrow and fixable. About $0.79 (13%) went
to three runner ticks that only re-reported an owner wait (sessions 5bf59afc, ee2287ba, 24593f87), and the autopilot's
own report showed $11.34 until PR 323 fixed the resume double count. Stop ticking while the only wait is on the owner,
and Reef's cost per feature drops to about spec-kit's.

## Method

- **Project.** `tally`, the `~/reef-live` word-counter at commit `7adf444` (`pyproject.toml`, `src/tally/__init__.py`
  with `words()`, `tests/test_words.py`, 22 lines). Each tool worked on its own clone under `~/bench-cost-2026-11-04/`,
  with no remote.
- **Same spec text for all three.** This is `~/reef-live`'s queue rows 2 and 3, verbatim:
  1. `count: a top(text, n) function returning the n most frequent words as (word, count) pairs, ties broken alphabetically, and a 'python3 -m tally top N' CLI reading stdin`
  2. `punctuation: words() strips leading and trailing punctuation (keeps apostrophes inside words like don't), so top() counts 'end.' and 'end' as one word`
- **Reef.** This is the measured live autopilot run on `~/reef-live` (2026-11-03, plugin 0.7.4-dev.15). Mahmoud (the
  proxy) approved plans and answered grill questions, and the loop merged PRs #3 and #4 and ran the release security
  pass. It was not re-run: a fresh run needs the owner's `reef-approval.py --owner` on the proxy contract and a GitHub
  remote, and the existing run already covers these exact two rows.
  - Cost comes from `.reef/run/run.log`, taking the **max `cost_usd` per session id**. A resumed conversation reports its
    running total, so summing per tick double-counts; that is why the autopilot report said $11.34.
  - Lines come from `git diff --numstat 7adf444 HEAD -- src tests`.
- **spec-kit.** `specify init --here --integration claude` (free, a local scaffold), committed as the baseline. Then one
  headless `claude -p --model opus` session per command:
  - `/speckit-constitution` once ($0.33).
  - Per feature: `/speckit-specify <row text>` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`.
  - Feature 1 cost $2.45 and feature 2 $2.40. Every session was fresh, so the sum is exact.
- **Squid.** Loaded with `--plugin-dir` from a clone at 6e6f77c. The baseline is a hand-written 6-line `AGENTS.md` that
  sets `TRACKER_MODE: file`; it stands in for `/squid-scaffold`, which is interactive.
  - Per feature: `/squid:squid-plan <row text>`, then the same conversation resumed with `/squid:squid-implement-night`.
  - Each conversation is counted once, at its last total. That this total is a running one is confirmed: the Fable cost
    of the plan step, $0.193, reappears unchanged in the resumed total.
  - Feature 1 cost $5.95, with 8 SWE and 5 Tester dispatches, i.e. rework loops. Feature 2 cost $2.58.
- **Headless answers.** spec-kit and Squid each got one appended line: no human is available, so take your own
  recommended answer at each question or gate. Squid was also told to approve the plan, use local task files and the
  current tree, and skip push/PR/CI but still run PA acceptance and the PR-Reviewer. This plays the part Mahmoud played
  for Reef.
- **Environment.**
  - The same Mac, the same Claude Code 2.1.317, and an Opus main model in all three.
  - The Reef plugin was disabled in the spec-kit and Squid sessions (`enabledPlugins` override), so its guard did not
    interfere. The `init` event confirmed this.
  - Permissions were acceptEdits plus a scoped Bash allowlist.
- **Files.**
  - Ledger: `~/bench-cost-2026-11-04/logs/ledger.jsonl`.
  - Full stream logs: `~/bench-cost-2026-11-04/logs/*.jsonl`.
  - Drivers: `~/bench-cost-2026-11-04/{run-step.sh,speckit.sh,squid.sh}`.

## What the numbers mean, and their limits

- **One run each.** There is no variance estimate, and Squid's feature-1 rework loop alone cost about $3. A second run
  could move any column by ±30%.
- **Squid ran all-Opus, against its design.** The first Product Architect dispatch hit the account's Fable usage limit
  (HTTP 429). The orchestrator then re-dispatched every agent with `model: opus`, including the Tester, which Squid
  designs as sonnet. As designed (Fable PA/reviewer, sonnet Tester), Squid would likely cost less. This is not measured.
- **Reef was measured a day earlier, on 0.7.4-dev.15**, with a real GitHub remote, PRs and the local CI gate. Today's
  main is 0.7.4-dev.19+.
- **What Reef's $5.99 includes:**
  - the release security pass (session 1f1272e1, $0.65);
  - $0.79 of idle owner-wait ticks.
- **What Reef's $5.99 leaves out:**
  - one killed tick (iteration 3, 89 s, rc −9, no cost recorded); estimate $0.3–0.9;
  - the interactive `/reef-init` (one-time setup, not logged).

  spec-kit's one-time constitution ($0.33) is included.
- **Wall time is not comparable as elapsed time.** Reef waited about 13 hours overnight for the owner to add a remote,
  and ~10 min for a `main` branch. The figure in the table is agent time. spec-kit and Squid ran unattended end to end.
- **Squid did no push, PR or CI** because the clone had no remote. On-Call (sonnet, CI-driving) would add cost on a real
  repo. spec-kit has no such step at all.
- **Lines are a weak unit.** Squid's CLI is 52 lines against Reef's 23 for the same command, and spec-kit and Squid each
  wrote about twice Reef's test lines. More lines means a lower $ per line without more value, so read **$ per feature**
  first.
- **Behaviour differs slightly.**
  - spec-kit strips any non-word edge character (`[\W_]`, Unicode included).
  - Reef strips ASCII `string.punctuation`, by the proxy's recorded decision.
  - All three pass their own suites. None was run against the others' tests.
