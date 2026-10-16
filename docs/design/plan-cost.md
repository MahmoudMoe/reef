# Where `/reef-plan`'s context goes, and the cuts (0.7 analysis)

Measured 2026-10-16 on a real row (`ledger`, row 1: two tasks, one ADR, one SPEC; `docs/perf/dogfood-2026-10-16.md`
stage 2): the orchestrator's context grew by **65,748 tokens** over 17 turns, max 113,880. The 5.7 target names 60k
for a whole row, so planning alone breaks it, and the plan's own rule makes it the next cut. This note attributes the
growth from the transcript (`scripts/reef-cost.py` categories, then per tool call, chars/4) and proposes the cuts.
It changes nothing: the grill and the drafting are design decisions, and decision 4 forbids a skill change without the
measurement before and after.

## Attribution

| Source | tokens | share of growth | what it was |
|---|---|---|---|
| Bash results | 24,685 | 38% | see the breakdown below |
| Tool-call inputs | 8,269 | 13% | the SPEC, two task files and the ADR written inline through heredocs; a Python snippet that re-implemented the sentence counter |
| The prompt and the owner's answers | 2,540 | 4% | fixed |
| Assistant text | 904 | 1% | the gate question and the summary |
| Session floor (not growth) | 48,132 | — | the system prompt, the plugin's skill text and attached files, before the first turn |

The Bash results, by command:

| tokens | command (abridged) | why it ran |
|---|---|---|
| 4,541 | `sed -n 30,90p scripts/reef-plan-check.py && sed -n 440,520p …` | reading the checker's source to learn the rules |
| 3,882 | `cat AGENTS.md && cat .reef/config.json && find . -type f …` | the project read |
| 3,782 | `cat reef/queue.md && cat reef/constitution.md && …` | the project read |
| 3,544 | `sed -n 520,640p scripts/reef-plan-check.py && sed -n 225,250p scripts/reef-queue.py` | reading the checker's source |
| 2,218 | `grep -n 'FAIL\|fail(' scripts/reef-plan-check.py; grep -n -i slug …` | reading the checker's source |
| 1,356 | `sed -n 300,345p scripts/reef-plan-check.py && sed -n 380,440p …` | reading the checker's source |
| 1,318 | `cat templates/spec.md && cat templates/task.md` | the templates (needed) |
| 1,089 | `git rev-parse main develop; ls .git/hooks; sed -n 1,40p scripts/…` | branch state + more source |
| 1,024 | a Python heredoc re-implementing the 25-word sentence check | the planner built its own lint |
| 571 | `wc -l scripts/reef-*` | source again |

**12,700 tokens, a fifth of the growth, went to reading `reef-plan-check.py`'s source** (four `sed` windows, a `grep`
over its FAIL lines, a `wc`) plus a hand-rolled copy of its sentence lint. The planner wanted to know the rules
before writing, and the only home of the rules is the checker's code. The project read (7.7k) and the templates
(1.3k) are the legitimate cost of planning; the writes (8.3k) are the plan itself.

## The cuts, with expected savings

1. **`reef-plan-check.py --rules`** (mechanism, ~40 lines, one red test): print the rules the checker enforces, with
   their numbers from `.reef/config.json`, in under 40 lines (slug shape, SPEC keys, AC shape and the 50/25-word caps,
   Proof rows, tier/complexity/verify pairs, `touches:` rules, `plan.max_tasks`, ADR Status). The skill's step 2 says
   "run `--rules` once; never read the checker". One home for the rules stays the code; the printout is generated from
   the same constants. Expected: −12k of the 66k (the source reads and the home-made lint disappear).
2. **Write, check, fix; never pre-validate by hand.** The skill already says the plan is what is on disk. Make the
   loop explicit: write the files from the templates, run `reef-plan-check.py`, fix each FAIL line, repeat; the checker
   is the oracle. Expected: the Python lint (1k) and the second read of the queue script go away; more important, the
   planner stops reasoning about rules in prose.
3. **The project read through `reef-loop.py tick` + `reef-queue.py ready` + `AGENTS.md` head only.** The planner read
   the whole queue, constitution and config and ran `find . -type f`. The constitution is enforced by code (the README
   says so) and need not be read to plan a `full` task; the queue is read by `ready`. Expected: −3 to −5k, more on a
   project with a long queue or constitution.
4. Not a cut, a note: the inline heredoc writes (8.3k) are the plan's own text and are the right shape (the digest
   covers what is on disk). A script that renders a task file from flags would move the tokens, not remove them.

Together: roughly −17k to −20k on this row, from 66k to about 47k, under the 60k that the target names for a whole
row only if `/reef-task` is also measured inside its dispatch span (34–40k measured) rather than as a whole session.
The honest reading: the 60k target was written for the task graph; a whole row across five sessions is 246k today
and will stay far above 60k. The owner decides whether the target names the graph (achievable now), the planning
session (achievable with cuts 1–3), or the row (a different design: fewer sessions, or a target per stage).

## How to measure the cut

Same recipe as the dogfood: a fresh sample project, `reef-init` with the grill answers in the prompt, `/reef-plan 1`
headless (`claude -p --plugin-dir`), `scripts/reef-cost.py <transcript> --repo .`; compare `growth` and the Bash
share before and after. Decision 4 applies to the skill text: the planner has no eval corpus yet, so the measurement
is the cost script's, and the plan-check's exit code on the produced plan is the quality floor.
