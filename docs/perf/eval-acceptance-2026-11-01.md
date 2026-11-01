# Acceptance-reviewer eval — 2026-11-01

Step 1 of the Squid adoption plan: the row's one reviewer (`agents/acceptance.md`) gets an eval, so a change to it or to
its model can be measured (decision 4). `python3 tests/eval/reef-eval run acceptance --k 3` on
`tests/eval/corpus/acceptance.json`, each run `claude -p` headless with this plugin loaded and the agent file appended,
in a fresh repository whose feature is a committed branch (`feat/csv-export`) over `main`. Scored by `reef-eval score`.

## The corpus
One feature (CSV export of monthly totals: FR-1 sorted rows with two decimals, FR-2 an empty dict exports the header
alone) and six PR heads, every one behind a green gate:

| entry | truth | what is in it |
|---|---|---|
| export-correct | PASS | both requirements met; stdlib `csv`; the existing `format_amount` reused |
| empty-drops-header | FAIL | FR-2 failed; `test_export_empty` asserts `""` and mirrors the bug |
| comma-parsing-regressed | FAIL | `parse_amount` stops accepting `1,234.50`; the proving test deleted, `test_report`'s input changed to hide it |
| overbuilt-exporter | PASS + NIT | an abstract `Exporter`, a registry and a factory for one format the spec rules out others for |
| reimplemented-helper | PASS + NIT | `_two_decimals` copies `ledger.util.format_amount` line for line |
| hand-rolled-csv | PASS + NIT | hand-written CSV quoting where the `csv` module does it |

`nit_rate` = the share of NIT entries' runs that end GREEN with NIT lines naming the over-built thing (the truth
regex). A blocker there is a false FAIL.

## Results (k=3, 18 runs each)

| run | brief | model | catch-rate | approve-precision | false-FAIL | nit_rate | cost (18 runs) | per run |
|---|---|---|---|---|---|---|---|---|
| baseline | main's `acceptance.md` | opus | **1.00** | **1.00** | 0.00 | **1.00** | $5.97 | $0.29–0.51 |
| ladder | + the NIT for code the task did not need (step 2) | opus | **1.00** | **1.00** | 0.00 | **1.00** | $5.69 | $0.29–0.52 |
| ladder | the same | sonnet | **1.00** | **1.00** | 0.00 | **1.00** | $2.59 | $0.13–0.24 |

`reef-eval compare`: baseline → ladder (opus) ok; ladder opus → ladder sonnet ok.

Beyond the metric, on the nine over-built runs: a NIT line that says what to use instead (`use`, `reuse`,
`instead`, `replace`, `delete the`): baseline 3/9, ladder opus 5/9, ladder sonnet 6/9. Words in all 18 reports:
5,227 · 5,012 · 3,858.

## What it says, and what it cannot
- **The corpus is at the ceiling.** The baseline catches every blocker and names every over-built thing already, so
  this corpus can refuse a regression but cannot show an improvement, and two runs scoring alike here is not proof
  that two reviewers are alike on harder diffs. The next entries should be ones the baseline misses: a regression
  with no deleted test (behaviour changed through a shared helper), a Proof test that passes for the wrong reason,
  an unrequested change that is also a security hole.
- **The scorer was wrong once, and fixed before any comparison.** The first baseline score read nit_rate 0.89: one
  report wrote `NIT: unrequested` as a heading with the finding (`_quote`, never reached) in bullets under it, and
  the scorer read the NIT line alone. `nit_lines` now reads a NIT's bullets as it reads a BLOCKING section's
  (pinned in `tests/test_eval.py`); all three runs were re-scored with it.
- **Sonnet held every metric at 43% of Opus's cost** (per run $0.14 vs $0.32), with shorter reports. It ran the gate
  once, quoted the evidence and named file:line in every FAIL. Under the ceiling caveat above, that is evidence the
  `full` tier's reviewer can be Sonnet; `design` and `critical` stay on Opus.

Reports and scores: the session scratchpad of 2026-11-01 (machine state, not committed).
