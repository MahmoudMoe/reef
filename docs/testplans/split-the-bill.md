# Test plan: Reef on a real product, end to end — "قسم الفاتورة" (Split the Bill), then Sophia

This is a plan for testing **Reef**, not the app. The app is the instrument: small enough to finish in a few rows,
real enough (money, several people, a shareable result) to make the tiers, the adversary and the review earn their
keep. Every number below is a measurement Reef already takes (`scripts/reef-cost.py`, `scripts/reef-eval`,
`scripts/reef-watch`); the plan says which to read, when, and what counts as a pass for Reef.

## 1. The product (the instrument)

**Split the Bill**: a web app where one person enters a bill (total, tax, tip, the items), adds friends, assigns items
to people (shared items split evenly), and gets a per-person amount plus a link to share so each friend sees "you owe
X". Arabic first, English second; mobile-first; no accounts in year one (a bill is a URL with an unguessable id).

Owner's day-zero answers (for `/reef-init`, the grill): host = one small VPS or a free-tier PaaS the owner names;
shape = `web-app`; scale = "a few hundred bills a month"; store = SQLite file (Postgres later if ever); auth = none in
year one, unguessable bill ids, a bill is deletable by whoever holds its link; non-goals = payments, bank sync, user
accounts, OCR of receipts.

Stack: TypeScript, Next.js (App Router), Prisma + SQLite, Vitest, Playwright for the browser evidence rows. This is
the stack Reef detects (`package.json`) and the one where the verifier's **browser evidence** rule (2.6) matters.

## 2. The rows (queue, batch 1)

| Row | Item | Tier Reef should pick | Why it tests Reef |
|---|---|---|---|
| 1 | Walking skeleton: one page end to end (create a bill with a total, see it), deployed | `full` | the skeleton rule from `/reef-init`; the first `/reef-plan` on a product row |
| 2 | Items and people: add items, add friends, assign items, shared items split evenly, per-person totals | `full` | the arithmetic that must be exact (minor units, rounding remainder goes to the payer): a `design`-shaped decision inside a `full` row — does the planner escalate the tier or hide it in prose? |
| 3 | Tax and tip: proportional split, the remainder rule, display | `design` (two people would build it differently) | the loophole-hunter's plan pass on a money rule; the Proof table with a golden test |
| 4 | Share link: unguessable id, read-only view for a friend, delete by link holder | `critical` (`touches: auth`-like boundary; the id IS the auth) | path-class rails (`touches:`), the threat model lint, the hunter's guard pass, `gates.release` on the release PR |
| 5 | Arabic/English, RTL, mobile layout | `light` or `full` | the verifier's browser evidence (`Not verified in a browser:` must appear when it is not), the `light` allowlist |
| 6 (found) | whatever the review finds | — | the batch boundary rule: found rows wait for batch 2 unless they lose data |

Expected: five rows, 10–14 tasks, two design-tier passes, one critical row, one release PR. If Reef plans more than
`plan.max_tasks` for a row, that is the split rule working, not a failure.

## 3. What to measure, and the pass line for Reef

| Measure | How | Pass for Reef |
|---|---|---|
| Rounds per task | `attempts:` in the done tasks; the journal | ≤ 1.5 average; no task at the cap without a journaled human decision |
| Orchestrator growth per `/reef-task` session, inside the dispatch span | `reef-cost.py <transcript> --repo .` → `rows` | < 60k per row (the 5.7 target as written for the graph) |
| Planning session growth | same, on the `/reef-plan` session | < 45k after the lean-read cut (measured 38k on a two-task row) |
| Session start | `reef-cost.py --session-start` | < 8k injected (the floor of ~48k is Claude Code's) |
| Judges' honesty | every verifier report has `RULE AC<n>` before the diff and evidence per AC; every hunter report cites file:line | `reef-claims.py report` exit 0 on every report; zero "verified" claims without a path |
| False stops | USER ACTION REQUIRED events that a human did not need | 0 beyond the two gates and `gh` |
| Governance | the human gates were exactly two per row (plan approval, release merge) | yes/no |
| Reef defects found | anything that needed a fix in the plugin | each becomes a found row in Reef's own queue with a red test |
| Cost | `total_cost_usd` per session (list price; subscription usage in practice) | reported, not gated; compare with the 0.7 dogfood: $16 for a two-task row |

Stop rules (the test stops and the owner decides): a cap reached without a journal entry; a guard denial the owner
cannot explain from the ledger; a merged task whose Proof row does not hold on `develop`; any write outside the
feature's scope.

## 4. Protocol

1. `git init` the app with its generator (`create-next-app`), commit, `/reef-init` with the answers above, push,
   `scripts/reef-repo` (protection, CODEOWNERS). Record: time to first green commit.
2. `/reef-loop` with the owner present for the two gates only. Record every USER ACTION REQUIRED verbatim.
3. After each row: `reef-cost.py` on that row's sessions (the loop's transcripts are under
   `~/.claude/projects/<slug>/`), the journal row, the found rows. `scripts/reef-watch --repo .` prints the same in one
   screen; run it after every merge wave.
4. After batch 1: the release PR into `main` with `gates.release` (C4 drift, threat lint, secret scan, audit); the
   owner merges. Record what the gates said.
5. Write `docs/perf/split-the-bill-<date>.md` in Reef with the table above filled; every Reef defect found goes into
   Reef's queue as a found row with the test that would have caught it.

Budget: about 5 rows × $15–25 at list prices (subscription usage in practice), two or three evenings of the owner's
time at the gates.

## 5. Then Sophia (the owner's existing project)

Sophia is the second instrument and the harder one: an **existing** project with its own documents and conventions.
The test there is `/reef-assess` → recalibration → one real row. What it tests that Split the Bill cannot:
- the four observed sections on a codebase nobody wrote for Reef (every claim Observed with a path, or Inferred);
- the harnessability score and what it does to `tiers.light.allow`;
- `reef-recalibrate plan` on real documents (ai-coach found four defects; Sophia will find the next ones), the
  owner's edit of the list, `--apply`, the revert;
- one row planned against the recalibrated SPECs and ADRs, with the project's own test command as `gates.full`.

Prerequisites before Sophia: `gh` authenticated on the owner's machine; the owner's answers for the recalibration
list (what is kept, what is archived); a release branch.

## 6. Who watches Reef when the owner is away

Nobody, today: a Reef session is observed only by the human in it. The measurements exist (journal, `.reef/loop.json`,
the transcripts, `reef-cost.py`, the judges' reports) but nothing reads them without a person. Three options, in
order of cost:

1. **A deterministic report, no model: `scripts/reef-watch`** (shipped with this plan). It reads the project's state
   from disk and prints one screen: the tick, journal rows since the last run, attempts used, blocked tasks, found rows,
   per-session growth from the transcripts (`rows`), cap breaches recorded in `.reef/loop.json`, and the judges'
   reports that `reef-claims.py report` rejects. A human reads it in a minute; a scheduled job can mail it. It cannot
   judge quality; it can show drift.
2. **A scheduled observer session (a Routine)**: every N hours a fresh Claude session clones the project, runs
   `reef-watch`, reads the new journal rows and reports, and posts a short verdict (push notification or email):
   "two rows merged, one task at 2/3 attempts, hunter rejected a plan twice, growth 41k/row". It can also open a found
   row in Reef's queue when it sees a defect in the plugin. Cost: one short session per run. It is the "monitoring
   agent" the owner asked about, built on the deterministic report so that it reads numbers rather than inventing
   them. It needs the owner's yes: which repository, which cadence, which channel.
3. **Reef watching itself harder**: the Stop hook already refuses an idle turn; the context ceiling already denies a
   runaway dispatch; the journal already records every merge. The gap is not inside a session but between sessions,
   and option 2 fills it.

Recommendation: option 1 now (it is code and tests), option 2 as soon as the owner names the repository and cadence,
and the owner reads the report at the two gates anyway.
