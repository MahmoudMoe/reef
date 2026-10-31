# Lightening — the duplication wiped, and kept from coming back

Written 2026-10-31 at the owner's request ("a comprehensive plan to wipe duplication, keep duplicate scripts from coming back, and
remove what has no use — to lighten Reef"), the day the hands-off plan's steps 0–3, 5 and 6 landed and the screen gained its log,
its responsiveness and `/reef-watch`. It continues `docs/design/consolidation.md` (steps 1–3 and 5 shipped; step 4 not), whose
numbers had grown back: the screen and the hands-off steps added what the consolidation had removed.

## 1. What was measured (main at 9d3e11d)

| | |
|---|---|
| Scripts (`scripts/reef-*`, `reef_common.py`, `reef`) | 38 · 19,639 lines |
| A function name defined in more than one script | 32 names, 64 definitions past the first — `die` ×13, `run` ×10, `git` ×8, `render` ×4, `script` ×3, `plan_check_module` ×3; 23 names in exactly two scripts |
| Scripts no skill, agent, hook, command, template or other script names | 0 |
| Tests | 37 files · 17,505 lines; `project` fixtures defined in 10 files, `git` helpers in 15 |
| Prose | README 12,542 words · CHANGELOG 35,504 · skills 17,103 · agents 7,334 · `commands/` 460 (fifteen three-line aliases of the skills) |
| Budget (`tests/size-budget.json`) | `script_lines` 17,989 · `prose_words` 24,437 · `config_keys` 96 · **`duplicate_defs` 64 · `orphan_scripts` 0** (new, step 0) |

## 2. The rule

**No behaviour change.** The suite is the proof: no assertion changes in a lightening step, only definitions move or go; every PR
ends with the same green. After each step the budget is set to the new measurement — lower. `duplicate_defs` and `orphan_scripts`
ratchet like the other three: a PR that adds a second definition of a name, or a script nothing names, has to raise the number in
`tests/size-budget.json` in the same diff, with its reason in the CHANGELOG — the raise is a reviewed line, never silent. The guard's
own copies of helpers other scripts own are the one standing exception (it must run when any other script is broken — the critical
path), named in the test, which also checks that each named helper is still the guard's.

## 3. The steps, one PR each, in this order

0. **The pins** (this PR). `tests/size-budget.json` gains `duplicate_defs` and `orphan_scripts` at today's numbers; the budget test
   measures them and names the offenders when one grows. Nothing else changes: the pins stop the debt from growing while the next
   steps pay it.
1. **The shared helpers, finished** (shipped 2026-10-31: `run` ×8, `git` ×7, `die` ×13, `plugin_root` and `plugin_version` ×2 → one
   shape each in `reef_common.py`, imported, the script's own defaults kept with `functools.partial`; five names that meant two things
   renamed — reef-init's `run` → `render_tree`, reef-attempt's `run` → `run_attempt`, reef-approval's `worktrees` → `all_checkouts`,
   reef-opencode's `frontmatter` → `split_frontmatter`, reef-factory's `say` → `note`; reef-merge-close's `fail` is `die` with its
   prefix. `duplicate_defs` 64 → 30; `script_lines` +6 — one home for ten shapes costs a few lines more than the thirty adapters it
   replaced. `gh` ×3 and `read_frontmatter` ×1 wait for step 2: three contracts under one name, and the guard's own copy.)
2. **The same name in two scripts** (shipped 2026-10-31: `duplicate_defs` 30 → 0; `script_lines` 17,995 →
   17,927). A true duplicate merged into `reef_common` — `load_sibling` (three `plan_check_module` loaders and reef-graph-run's
   `load_script`), `git_root` (two `root_of`), `reef_dir`, `section`, `slug_error` with `SLUG_RE`/`GENERIC_SLUGS`, `served_dirs`,
   `config_homes` with `HOME_KEYS`; a false one — two things under one name — renamed so a reader stops confusing them (reef-row's
   `queue_rows` → `queue_status`, reef-run's `release_hold` → `drop_session_hold`, reef-loop's `render` → `render_status_page`,
   reef-init's `render`/`detect` → `render_template`/`detect_stack`, reef-handoff's `render` → `render_handoff`, reef-recalibrate's
   `render_plan` → `render_moves`, reef-plan-check's `parse_args` → `parse_check_args`, reef-threat's `lint` → `lint_threat`,
   reef-factory's and reef-graph-run's `script` → `own_script`/`project_script`, reef-record's `gh` → `gh_text`, reef-repo's `gh` →
   `gh_rc3`, the screen's loader → `sibling_module`). The pin's definition narrowed by one rule, stated: a script's own `cmd_<verb>`
   handlers — one per CLI, by convention; the six pairs had six different bodies — are not counted.
3. **One fixture module for the tests** (consolidation step 4; shipped 2026-10-31: `tests/_fixtures.py` holds `write`, `git` in its
   four shapes (`git`, `git_checked`, `git_out`, `git_text`), `git_repo` and `load_script` once — 63 lines; fifteen `write`s and fifteen
   `git`s left the test files, and every suite's `project()` opens its repository through `git_repo()`. The test files went 17,590 →
   17,469 lines; with the module, 17,590 → 17,532: the plan's guess of −1,500 was wrong — the copies were four lines each; what is
   gone is the drift between them, not weight. test_entry's script loader moved too; the other ad-hoc loaders are a follow-up.)
4. **Orphans and aliases.** Whatever `orphan_scripts` names goes, or gains the one caller it was written for. `commands/`: fifteen
   three-line files that each invoke a skill, so every verb shows twice in Claude Code's menu (`/reef:plan` and `/reef:reef-plan`);
   every document, prompt and the runner name `/reef-plan`, which is the skill. Recommended: delete `commands/`; the owner types
   `/reef-plan` instead of `/reef:plan`. The owner's call, taken in this step.
5. **The prose.** CHANGELOG entries before 0.7 move to `docs/changelog-archive.md`, out of the budget (−25,000 words of the file);
   the "why" notes that skills carry as history ("2026-10-29, the owner: …") move to the CHANGELOG, the rule stays; the README leans
   on the site for what the site already says. Expected: `prose_words` 24,400 → about 18,000.
6. **Compatibility with projects before 0.6** (the "0.5 shape" criteria, the `gates.test` alias, `planned before 0.6`): a behaviour
   change, so out of this plan — 0.8, with a migration, by a decision of its own.

## 4. Scored

By §1 re-measured after step 5: scripts 19,639 → about 16,000 lines; `duplicate_defs` 64 → under 10; `orphan_scripts` 0;
tests −2,000 lines; `prose_words` → about 18,000; and the suite's green at every step.
