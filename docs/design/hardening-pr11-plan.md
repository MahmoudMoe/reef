# Hardening PR-11: three prompt changes, measured first

Three lines taken from mattpocock/skills. The owner's rule for this PR: measure on the evals first. A change lands only
with the measurement that supports it, or with a plain statement that no harness can measure it yet.

## The changes (the only lines this PR touches)

| # | file:line (main e5d2197) | today | after |
|---|---|---|---|
| 1 | `skills/reef-plan/SKILL.md:37` | "…at most ONE ADR … for the feature, only if it has non-obvious decisions" | "…only for a decision that is all three: hard to reverse, surprising without its context, and the result of a real trade-off (an ADR may be 1–3 sentences)" |
| 2 | `agents/implementer.md:14` (the TDD line) | ends "Never cut validation, error handling or a test. Then refactor." | the same line without "Then refactor." (refactoring is the review's call, not the red→green loop's; smaller diffs, and it fits PR-1's `files:` check) |
| 3 | `agents/acceptance.md`, one new bullet after the `## Proof` bullet (line 22) | (none) | a tautological test (the expected value recomputed the way the code computes it, or a constant compared with itself) passes by construction; expected values come from an independent source. On a Proof row: that criterion FAILs. Elsewhere: a NIT |

Not touched (other sessions own them): `templates/adr.md`, `agents/implementer.md:11`, `agents/planner.md:11`,
`agents/acceptance.md:21`, `mahmoud.md`.

### Change 3: NIT or BLOCKER? Both, by where the test sits
`acceptance.md` already has the rule. A BLOCKER is one of four kinds, and "a criterion whose test does not test it: FAIL".
- If a Proof row names a tautological test, nothing tests that criterion. The criterion FAILs, which is the
  "failed requirement" BLOCKER kind. A NIT there would let GREEN stand on a test that cannot go red.
- If the tautological test is extra (on no Proof row), nothing depends on it. It is not one of the four kinds, so it is
  a NIT ("this test proves nothing; use an independent expected value").

### No-op check (only the lines touched)
- **1**: today's "non-obvious decisions" is a weaker filter, and the models we use tend to write an ADR whenever a
  decision exists. The three-part test narrows that. It is not a no-op, but nothing in Reef can measure it (see below).
- **2**: a deletion. Removing an instruction cannot be a no-op in the "already obeyed" sense. The risk runs the other
  way: models refactor unasked anyway, so the deletion may change little. Unmeasured.
- **3**: this may be a near no-op. Two existing lines already cover it in general terms: "a criterion whose test does
  not test it: FAIL", and the guard pass's "a test that cannot go red (name the mutation)". The eval decides it (below).
  If the baseline already catches the new corpus entry and names the tautology in every run, the line is a no-op and I
  will say so in the PR. The owner then decides whether it still lands as a named pattern.

## What can be measured here, and what cannot

The harness is `tests/eval/reef-eval`. It has corpora for `verifier`, `hunter` and `acceptance` only. A live run is
`claude -p` headless, with the agent file appended. Live calls work in this session, checked with a $0.003 haiku call.

| change | harness | measured here? |
|---|---|---|
| 3 acceptance | `reef-eval run acceptance` | **yes, live.** A new corpus entry plus a regression run of the whole corpus |
| 2 implementer | none: no implementer corpus, and `reef-eval` has no implementer agent | **no.** Contract test only |
| 1 reef-plan ADR | none: no planner corpus | **no.** Contract test only |

### Change 3: the measurement
- **New corpus entry `proof-recomputes-expected`** in `tests/eval/corpus/acceptance.json` (10th entry; the suite allows
  five to ten). Same csv-export feature. `export_csv` sorts and formats with `f"{total:.2f}"`, which rounds half-even
  through Decimal's context. The owner's decision says half up, and `format_amount` exists for that. AC-1's Proof test
  builds its expected string with the same `f"{t:.2f}"` expression, so it passes by construction, even on the half case
  it feeds (`1002.505` → `1002.50`; half up is `1002.51`). The gate is green.
  - truth: FAIL. Blocker regex: AC-1/FR-1, rounding, `1002.5`, `format_amount`, or the tautology named.
  - a second number beyond the metric: how many runs name the tautology itself (`recomput|tautolog|by construction|same
    expression…|independent`), against how many only spot the rounding.
- **Runs** (model `opus`, the agent's frontmatter default; budget $1.5 a run):
  - A (main's `acceptance.md`): the new entry ×3 + the other nine entries ×1
  - B (with change 3): the same
  - `reef-eval score acceptance <dir> --json`, then `reef-eval compare A.json B.json` (it must not refuse)
  - expected cost: about $0.35 a run × 24 runs ≈ $8–10
- **What confirms it**: B catches the new entry at least as often as A, B names the tautology in more runs than A, and
  `compare` says ok on the nine old entries.
- **What refutes it**: `compare` refuses (catch-rate, precision or the NIT rate dropped), or B false-FAILs a PASS
  entry by calling a test with a hand-written literal tautological.
- **What makes it a no-op**: A already catches and names the tautology 3/3.
- k=1 on the old nine is a smoke check, not a ranking. The 2026-11-02 report says that corpus sits at the ceiling.

### Changes 1 and 2: for the owner to run before merge (nothing in Reef measures them today)
- **2 (implementer)**: dispatch `reef:implementer` on the same groomed task (one with an obvious tidy-up nearby), k=3
  with the line and k=3 without, then compare:
  - `git diff --stat` lines changed
  - the number of files outside `files:`, which `reef-claims.py round` refuses
  - whether the gate is green

  Confirms: a smaller diff, or the same, with the gate still green. Refutes: worse code that the review then bounces
  (a NIT count at acceptance). Building an implementer corpus is a separate row, not this PR.
- **1 (ADR)**: run `/reef-plan` on two rows, k=3, before and after. One row has a reversible, obvious choice; the other
  a hard-to-reverse trade-off. Count the ADRs drafted. Confirms: no ADR on the first, one ADR on the second.

## Tests (red first)
`tests/test_contracts.py`, one test per change:
- `implementer.md` no longer contains "Then refactor", and the TDD line still keeps "failing test first" and "Never cut
  validation, error handling or a test"
- `reef-plan/SKILL.md` names the three ADR criteria (hard to reverse · surprising without its context · a real
  trade-off) and no longer says "non-obvious decisions"
- `acceptance.md` names tautological tests, an independent source for expected values, and both severities (the Proof
  row FAILs, elsewhere a NIT)
- the corpus entry is held by `tests/test_eval.py`'s existing "every entry builds and its gate is green"

## Housekeeping
- `python3 .github/bump-version.py` (agents/ and skills/ changed)
- a CHANGELOG line in the house style
- `tests/size-budget.json` `prose_words` raised only by what these lines add (+77 measured; the plan guessed +45). Before reporting ready:
  rebase on `origin/main`, re-bump, re-run the suites.

## Owner decisions (flagged; conservative default in place)
- D1: if change 3 proves a no-op on the eval, does it still land as a named pattern? Default: land it. It costs one
  line, and the corpus entry stays as a regression guard either way. The PR says which way the data fell.
- D2: changes 1 and 2 land unmeasured (contract tests only), with the protocol above for the owner. Default: land them.
  Both are small, and the owner approved them from the source.

## Results (2026-11-17, live, about $6.20 in total)

| run | model | new case `proof-recomputes-expected` | other nine cases (k=1) | cost |
|---|---|---|---|---|
| A: main's `acceptance.md` | opus | caught 3/3; names the recomputed expected value 3/3 | catch 1.00 · precision 1.00 · false-FAIL 0.00 · NIT 1.00 | $2.80 |
| B: with change 3 | opus | caught 3/3; names it 3/3 (says "tautological" 3/3) | the same; `reef-eval compare A B`: ok | $2.51 |
| A | sonnet | caught 3/3; names it 3/3 | not run | $0.40 |
| B | sonnet | caught 3/3; names it 3/3 | not run | $0.40 |

- I read every report on the new case by hand. A keyword grep missed one baseline report that writes "the same
  `f"{t:.2f}"` expression", with backticks in the middle of the phrase.
- Report words on the new case: opus 1,140 (A) vs 1,044 (B); sonnet 818 vs 763. That is within noise at k=3.
- **Verdict: change 3 is a no-op on this corpus, for both models.** The existing lines ("a criterion whose test does
  not test it: FAIL", the guard pass's "a test that cannot go red") already produce the behaviour. This is evidence
  for D1's alternative: drop the line and keep the case. The default stays "land" until the owner rules.
- Changes 1 and 2: not measured. No harness exists; the protocol above stands.
