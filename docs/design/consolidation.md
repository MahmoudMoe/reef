# Consolidation — lighter, one home per helper, no behaviour change

Written 2026-10-28 at the owner's request, after the first day of Workflow v3 on the current adoption ("so many locks and
guardrails … stopping me from normal rounds", then: "clean and lighten, without changing behaviour — plan first"). Approved as a
plan; each step below ships as its own PR, red first where a test can be red, and is scored by the numbers in §1.

## 1. What was measured (main at 56ba4ad)

| | |
|---|---|
| Scripts under `scripts/reef-*` | 38 · 17,354 lines |
| The same helper defined in several scripts | `main_checkout` ×13 · `run` ×10 · `git` ×7 · `config` ×4 · `read_config` ×3 · `repo_root` ×3 · `process_alive` ×3 |
| Scripts no skill, agent, command or hook names | 6 — three are called by other scripts (`reef-handoff`, `reef-migrate`, `reef-opencode.py`), three only by tests (`reef-eval`, `reef-guard-profile.py`, `reef-watch`) |
| The four largest | `reef-guard.py` 1,710 · `reef-recalibrate` 1,500 · `reef-plan-check.py` 1,425 · `reef-queue.py` 1,383 |
| Tests | 38 files · 14,916 lines, with repeated fixtures (`repo`, `write`, `git`) |
| Budget (`tests/size-budget.json`) | `script_lines` 17,354 · `prose_words` 22,576 · `config_keys` 95 |

## 2. The rule

**No behaviour changes.** The 722 tests are the proof: no assertion changes, only files move; every PR ends with the same
green (the Python suite, `tests/test_hooks.sh`, `tests/test_ci_local.sh`, the six CI checks). After each PR the budget is
set to the new measurement — lower after a step that removes files or copies; a step that only makes one definition of
several (step 3) may add the docstring and the normalisation the copies never had, and is scored by §1's helper column,
not by lines. A refactor that needs a test changed is not a
refactor and goes back to the plan.

## 3. The steps, one PR each, in this order

1. **One shared module.** `scripts/reef_common.py` holds one definition of each helper in §1 (`main_checkout`, `run`,
   `git`, `config`/`read_config`, `repo_root`, `process_alive`, `read`), with the strictest existing signature; each
   script imports it from its own folder (`sys.path.insert(0, dirname(__file__))`, as the guard's import of the plan check
   already does) and deletes its copy. `reef-init` copies the module with the scripts; `reef-update` stages it; the budget
   counts it (`scripts/reef_common.py` joins the `script_lines` glob explicitly). Expected: −300 to −400 lines.
2. **The three orphans.** `reef-watch` goes (`reef-run.py status` and `.reef/status.html`, rendered at every tick, replaced it); `reef-guard-profile.py`
   goes (its one measurement is `docs/perf/guard-profile-2026-10-16.md`); `reef-eval` moves under `tests/` as a test tool,
   since only `tests/run.sh` runs it. Each with its tests. Expected: −600 to −900 lines.
3. **One definition inside the big four.** `reef-plan-check.py` computes "open task" and "rollup" twice; the guard, the
   runner and the doctor each read the loop hold; `reef-queue.py` parses the row table in two places. Each becomes one
   function. No file is split: splitting the guard is a critical-tier change for no weight saved.
4. **One fixture module for the tests.** `tests/_fixtures.py` holds `repo`, `write`, `git`, `task`, `config` once; the
   38 files import them. Not in the budget; it is the maintenance half of the same debt.
5. **The entry point's screen.** `reef` alone opens a live screen (stdlib `curses`, falling back to today's menu when the
   terminal cannot): the banner and status line; **the inbox** — every wait Reef has recorded, as a numbered item carrying
   the exact command the row machine names, so one key runs it (an approval, a footnote answer, a look to confirm); the
   runner's last ten steps; the doctor's warnings; keys `r` run · `n` night · `s` stop · `d` doctor · `c` cost · `q`.
   The screen knows nothing the scripts do not: every key runs a command the owner could type. Built on step 1.

Out of this plan, because it changes behaviour: the compatibility paths for pre-0.6 projects (the "0.5 shape" criteria,
the `gates.test` alias, `planned before 0.6`). They leave in 0.8 with a migration, by a decision of their own.

## 4. When, and how it is scored

Step 1 starts after the current adoption's row 6 — the first row v3 plans from scratch — has gone from plan to merge with
the owner answering questions only. Until then the freeze holds: bugs the owner hits, nothing else.

Scored by §1 re-measured after step 4: scripts 38 → 35, lines 17,354 → about 15,500 (−10%), every helper in §1 → 1
definition, the test fixtures → 1 module; and by the suite's green at every step. Step 5 is scored by the owner's rounds:
a round where every stop was answered from the screen, no terminal line typed.
