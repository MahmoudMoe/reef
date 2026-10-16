# Changelog

## 0.7 (unreleased)
- **`reef-approval.py`: the digest is computed where the plan lives.** The hook computed it in the main checkout;
  with the plan moved to a feature worktree and `develop` holding no feature files, an `Approve` matched nothing and
  wrote nothing (first contact, 2026-10-16). Now every checkout of the repository that holds the feature is a
  candidate, the question's digest must match one of them, and the record still lands in the main checkout where
  `reef-plan-check.py --verify-stamp` and the guard read it (`tests/test_tiers_lock.py::ApprovalInAWorktree`).
- `reef-init.py`: records are written once — `HANDOFF.md`, the journal, the queue and its archive are never
  re-rendered nor proposed after birth (a re-run offered their blank templates; accepting would have erased the owner's
  gate decision); the `--accept` hint names the script that is running (the project has no `reef-init.py` copy).
- `reef-loop.py tick --session-start`: the dead session's `STOP=context ceiling` line is stripped from the injected
  handoff head, and when `CLAUDE_PLUGIN_ROOT` is set the project's `scripts/reef-*` copies are compared with the
  plugin's — `reef: N project script(s) behind the plugin (…) — run /reef-init and accept scripts/*`. The project's
  copies had been a day behind and nobody could tell.
- `templates/project/constitution.md`: the journal path is the layout's (`{{journal_path}}`), not `docs/journal.md`.
- **`reef-init.py`: another tool's block rides along.** `<!-- BEGIN:x --> … <!-- END:x -->` blocks in a file Reef renders
  (Next.js's agent rules in `AGENTS.md`, re-added by `next dev`) are neither Reef's nor the owner's: a re-render keeps
  them whole (`updated  AGENTS.md (+1 foreign block(s) kept)`), the manifest hashes the file without them, and a
  proposal carries them too. First contact: every re-init proposed dropping the block and it was re-appended by hand.
- `scripts/reef-repo`: the branch-protection payload file is removed after the call (it was left behind on a 403).
- `reef-cost.py`: attachments by type (`attachment:file`, `attachment:queued_command`, `attachment:skill_listing` …) —
  the real planning session had 54% of its context under one bucket.
- `reef-guard.py`: the ceiling denial is an order (`/clear NOW … do nothing else in this session`); the warn names the
  room left and that Bash is not refused at the ceiling. The real session kept going 80k past it.
- `skills/reef-plan`: the grill batches independent questions (up to four per set), one at a time only when the answer
  decides the next question; budget two sets plus two singles per row (twelve sequential questions planned one row).
- **`reef-guard.py`, re-entry false positives**: `ls .reef/approvals 2>/dev/null` was denied as a hand-written approval
  record and a judge's `tar -xzO 2>/dev/null` as a write — `2>/dev/null` is no write (`/dev/null`, `/dev/stdout`,
  `/dev/stderr`, `/dev/tty` are never targets), and the record-dir and judge checks now look at the write TARGETS
  (`write_targets`), like the guard-file check. A judge may write to its own scratch space (the session scratchpad,
  the temp dir): it never mutates the project, and unpacking a tarball to read it is judging (`tests/test_guard.py::JudgeScratch`).
- **`reef-loop.py tick --session-start` clears a dead session's context-ceiling stop.** The stop belongs to the
  session that hit the ceiling; the one starting now is fresh. After `/clear` the tick still said
  `STOP=context ceiling: 164970 tokens` from the previous session. Other stops (USER ACTION REQUIRED) stay.
- **`reef-loop.py tick`: a ready task of an unapproved or unreviewed plan is `awaiting`, not `dispatch now`.** The tick
  now runs the guard's own `reef-plan-check.py --verify-stamp --feature` per feature of the ready set and holds the
  feature back with the reason (`approval`, `re-approval (plan edited after approval)`, `plan review`); the handoff and
  the SessionStart injection inherit the line. First contact (2026-10-16): the ceiling handoff told the next
  orchestrator "dispatch now: 101" for a plan nobody had approved or reviewed; the guard would have refused the
  dispatch, but the one read of the world was a lie (`tests/test_loop.py`, the fixture now carries a stamp and an
  approval record, as a dispatchable plan does).
- **`reef-init.py`: its own untouched rendering is replaced without a question.** `.reef/init-manifest.json` records
  the sha256 of every file init placed (written or `--accept`ed). On a later run, a differing file whose current bytes
  still match the manifest is Reef's own draft that nobody touched: it is `updated` in place. One byte of anyone's
  edit, a file another generator rewrote, or a file the manifest does not know (a clone from before 0.7) is proposed
  under `.reef/proposed/` exactly as before. First contact (2026-10-16): four files init wrote on an empty repo came
  back as four questions minutes later when the stack arrived (`tests/test_init.py`, two tests).
- `skills/reef-init`: step 4b, the empty repository — the gate's loud failure is the signal to run the stack's generator
  as the start of row 1 (one question: which generator), re-run init so the gate fills from the detected stack, then
  commit init and the skeleton together. First contact (2026-10-16): the orchestrator improvised exactly this, then asked
  the owner to set the gate by hand; neither should depend on improvisation.
- **`reef-init.py`, three first-contact fixes** (an empty repo, then a Next.js scaffold, 2026-10-16):
  - a config value init itself left EMPTY (`gates.full`, `gates.extra`, `worktree.setup` before the stack existed)
    is filled when a later run detects the stack; a tuned value is still never changed. Before, the owner had to
    hand-edit a guarded file to set the gate (`test_a_gate_init_left_empty_is_filled_when_the_stack_arrives`);
  - no stack no longer renders the `github-actions` Dependabot ecosystem twice — the stack entry exists only when
    there is a stack (`test_unknown_stack_leaves_gate_empty_and_says_so`);
  - the grill writes a fourth draft ADR, `draft-1-shape.md`: one deployable, a modular monolith, microservices and
    per-feature functions rejected with the reason, a split later being a queue row opened by a measured need. The
    decision everyone argues about in a year was implicit in the C4 diagram
    (`test_grill_renders_architecture_adrs_and_the_skeleton_row_once`).
- **`reef-guard.py`: first-contact false positives fixed, one bypass closed.** On the first real project (an empty
  repo, 2026-10-16) the guard denied `cat > .reef/grill.json <<'EOF' … EOF` followed on the next line by
  `python3 …/scripts/reef-init.py`, and then `python3 …/reef-init.py … >/dev/null`, both as "Bash write to
  reef-init.py". Cause: a newline was whitespace to the tokenizer (one segment), heredoc bodies were read as shell,
  and any guarded path in a segment with a redirect counted as its target. Now a bare newline is an operator,
  heredoc bodies are stripped (`strip_heredocs`), and only the redirect's target and a write head's arguments are
  targets (`write_targets`). Closed on the way: `echo x⏎cp evil.py scripts/reef-guard.py` was allowed before (the
  `cp` hid behind `echo` in the merged segment) and is denied now. `tests/test_guard.py`: four allow shapes, five
  deny shapes.
- `reef-plan-check.py`: `adr/README.md` (written by `reef-init` on every fresh 0.6 project) is the directory's
  explainer, not an ADR without a Status — the first plan check of a new project no longer fails on it
  (`tests/test_plan_check.py::test_adr_readme_is_not_an_adr`, red before the fix). Found while running the 5.7
  measurement row on Reef itself.
- `reef-plan-check.py`: on a fresh 0.6 project there is no `tasks/` yet, and the stamp's home is
  `<paths.tasks>/.plan-review.json`; the check now creates that directory instead of dying with ENOENT after
  reporting zero failures (`tests/test_feature_spec.py::test_fresh_06_project_without_tasks_dir_gets_its_stamp`,
  red before the fix). Same measurement row.
- `reef-adversarial`: a live PASS report that says `BLOCKER: none.` was refused as "a BLOCKER line with VERDICT: PASS",
  so a design-tier row could not be dispatched without re-running the hunter for wording; and a hole written in
  markdown bold (`**BLOCKER:** …`, also seen live) was NOT read as a blocker. Both fixed: the bold is stripped and the
  words are read (`tests/test_adversarial.py::test_blocker_none_is_no_blocker`, red before; the bold case joins the
  refusal cases). Found recording the hunter's round-7 PASS on the measurement row.
- `reef-queue.py adr-number`: the draft title `reef-init` writes (`# ADR draft-1-x — …`) became `# ADR ADR 0001 — …`,
  and a path citation (`adr/draft-1-x.md`) became the dead `adr/ADR 0001.md`; the ledger dogfood's close fixed four
  spots by hand. The title keeps one `ADR`, a path citation becomes the new filename
  (`tests/test_tier_queue.py::test_adr_number_title_and_path_citations`, red before the fix).
- **`templates/pre-commit` (and the pre-merge-commit it also renders): the gate runs outside git's hook environment.**
  git exports `GIT_DIR`, `GIT_INDEX_FILE`, `GIT_WORK_TREE`, `GIT_PREFIX` to a hook; a test suite that runs its own
  `git init` / `git commit` in temp dirs then acts on the real repository. Seen live: Reef's own suite, run by the
  commit gate on the Reef-on-itself row, re-initialised the clone as bare, created three fixture branches and moved
  the task branch 17 commits; the orchestrator restored everything from the reflog, refused to touch a critical path
  outside its plan, and stopped with USER ACTION REQUIRED. The gate now runs in a subshell with those four variables
  unset (`tests/test_hooks.sh`: two checks, red before the fix; 72 hooks checks).
- `reef-claims.py report`: a loophole-hunter report has its own shape (DEFECT / BLOCKER / NEW-ROW / NONE / VERDICT) and
  never carries `RULE AC<n>` lines, yet `/reef-task` sends it through the same check, which rejected every live hunter
  report. The hunter shape is now checked on its own terms: a DEFECT line, a FAIL needs a cited BLOCKER
  (`tests/test_feature_spec.py::test_hunter_report_has_its_own_shape`, red before the fix).
- **Row 1 delivered: `reef-cost.py` reports per-feature context growth** (`rows`: feature, first and last turn,
  growth as the sum of positive context deltas across the span, compactions in span, turns, dispatches; text, md and
  json). Built by Reef on itself as queue row 1 of the dogfood clone (tier critical: plan pass 7 rounds, implementer
  opus one round, verifier fable PASS, hunter guard pass PASS), then carried onto this branch. Six tests in
  `tests/test_cost.py` (`test_rows_*`). Live: the ledger task-graph session reads one row, growth 39,665 over 4
  dispatches; the Reef row session 34,098 over 3; a session that launched roles through `claude -p` reads `rows: []`.
- **Row 1, second half: the context caps are set from the measurement.** `templates/config.json`
  `caps.context_warn: 100000`, `caps.context_tokens: 150000` for a NEW project (session maxima measured 58k–159k,
  p90 148k: the warning fires late in a planning or critical-row session, the ceiling only on a runaway); a migrated
  0.5 project keeps `0` / `0` (off), decision 11 (`tests/test_layout.py::Migrations` pins it;
  `tests/test_init.py::test_fresh_init_sets_the_measured_context_caps` pins the new default). The README settings
  row says why the default is wider than the 40/60 rule of thumb.
- **Row 6: `writing.report_words` set from measured reports** — four real judge reports (two verifiers on `ledger`,
  the verifier and the hunter on the Reef row) ran 538–706 words for 6–7 criteria, about 95 words per criterion; the
  template's cap is now `900` (30% above the largest) and `reef-claims.py report` rejects over it instead of warning
  (`tests/test_feature_spec.py::test_report_words_cap_is_set_and_enforced`, red before: the template said 0). A
  migrated project gains the key with the other `writing.*` caps.
- **The 5.7 breaker, cut.** `reef-plan-check.py --rules` prints every rule the checker enforces with the project's
  numbers in under 40 lines (`tests/test_plan_check.py::test_rules_prints_the_projects_numbers_in_under_40_lines`);
  `skills/reef-plan` reads lean (the tick, `ready`, the head of `AGENTS.md`, the templates, `--rules` once; never the
  checker's source, never a home-made lint, never the whole queue or constitution). Measured on the same project and
  prompt: planning growth 65,748 → 38,441 tokens (−42%), Bash results −58%, cost −26%, the plan still 19 checks /
  0 failed (`docs/design/plan-cost.md`).
- **`reef-recalibrate` on a real project (ai-coach, 839 Markdown files)** found two defects: (a) a moved document's
  link to a sibling the plan KEPT (referenced from code) was left dead and the whole apply refused — links of a moved
  file are now resolved from where it came from (`tests/test_dayzero.py::test_moved_spec_keeps_its_link_to_a_kept_sibling`);
  (b) the "referenced from code" exemption counted `.reef/recalibration.json` (which names every document) and CI logs,
  so `reef-structure --check` printed ok over 800+ stray documents and a second `plan` would have kept everything —
  Reef's own plan, `*.log` and `*.txt` no longer count as references
  (`tests/test_dayzero.py::test_structure_check_is_not_fooled_by_the_plan_file_or_logs`). Run record in the dogfood report.
- `reef-cost.py` rows: a background agent's notification also arrives as an `attachment` of type `queued_command`;
  found by the acceptance review of the feature itself on the Reef row session (growth read 34,098 for a true 40,840)
  (`tests/test_cost.py::test_rows_span_ends_at_an_attachment_notification`, red before).
- `reef-recalibrate`, two more from the real project: a feature slug never starts with an id token (`014a-…`), and two
  specs with one title get distinct feature slugs instead of the second overwriting the first's SPEC.md
  (`tests/test_dayzero.py::test_slugs_drop_id_tokens_and_never_collide`); a link dead before the apply is listed, not
  a refusal (`test_a_link_broken_before_the_apply_does_not_block_it`; the old refusal test now asserts the new rule).
- **The guard writes the checkpoint at the context ceiling.** `reef-guard.py` runs `scripts/reef-handoff --write`
  (the project's copy, else the plugin's) before denying the over-ceiling dispatch, so a session cut at the ceiling
  never leaves the next one without `HANDOFF.md`; the denial now says it was written (`tests/test_loop.py`, the
  ceiling test asserts the file). Prose-guarded-by-code became code.
- **`scripts/reef-watch`** — one screen on a project's Reef state from disk, no model: the tick, tasks by status and
  attempts (AT CAP, BLOCKED named), journal rows since a date, found rows, stops and waits from `.reef/loop.json`,
  sessions since a date with per-feature growth from `reef-cost rows` (flagged over `caps.context_warn`), judge
  reports `reef-claims.py report` rejects. Deterministic, under 60 lines, `--json`. For the human who was not in the
  room and for a scheduled observer session. `tests/test_watch.py`.
- **`reef-claims.py assess [<root>]`** — `/reef-assess`'s output as data: `architecture.md` has its "How it works today"
  section and `conventions.md` its eight (lint, type strictness, tests, errors, logging, naming, module layout, how it was
  pushed); every top-level bullet in an observed section is `Observed — <path:line | path | command>` or `Inferred — …`
  (proposals under Open / Gap to target / "should take" are exempt); `day-zero.md` carries `## Harnessability — level (N/5)`
  with the five dimensions scored 0/1, an Observed cell each, the sum equal to N and the level consistent (5 high, 3–4
  moderate, else low). The fixture under `tests/fixtures/assess/ledger/` is the real report from the ledger dogfood
  (19 turns, growth 78,090, 4 Explore sub-agents, moderate 3/5); `tests/test_assess.py` replays it and each lie.
- **Row 2, the hunter's scope discipline.** Corpus entry `scope-names-later-rows` (truth PASS: a sound path guard whose
  Scope names its three known holes as later rows). `agents/loophole-hunter.md`: the Scope draws the BLOCKER/NEW-ROW
  line, an out-of-scope hole is a NEW-ROW even when it will happen or is a regression (marked `regression`). Measured,
  k=3 over the whole corpus (21 runs): catch 1.00 → 1.00, precision 1.00 → 1.00, false-FAIL 0.33 → 0.17
  (`sound-guard` 2/3 → 1/3; the remaining FAIL is a quoted-heredoc hole the hunter argues is in scope);
  `reef-eval compare` ok. Details: `docs/perf/eval-baseline-2026-10-16.md` §0.7.

## 0.6.0 — governance, spec, tiers, day zero, loop engine, one tree

### Finishing
- README: the flow as a graph, the honesty ledger with a class per mechanism (`tests/test_contracts.py::LedgerClasses`),
  the tier table, every new setting with its default, "Measured", the one tree, 387 selftests.
- Templates: AGENTS (≤ 80 rendered lines, the stack's conventions, the tick), constitution with the admission article
  (VIII), queue with the walking-skeleton row and footnotes, journal with per-AC status, CI with `--ci --release` and the
  auditor/gitleaks setup steps, `spec.md`, `stacks/`; `docs/design/graph-and-setup.md` §9–15.
- Version 0.6.0 in `plugin.json`, both fields of `marketplace.json`, the README badge, `test_one_version_everywhere`.
- Guard profile re-run on the final guard (`docs/perf/guard-profile-2026-10-16.md`): p95 ≤ 130 ms, every timeout 10 s.
- Eval at k=3 on the final agent files: verifier after 2.3/2.6 (false-FAIL 0.33 → 0.00, nothing dropped), hunter after 4.4
  (nothing dropped; false-FAIL 0.33 → 0.67 on the one PASS entry, recorded), plan-reviewer unchanged (baseline stands).
- **Forced deviations, recorded:** (a) *branching* — this session was bound to one branch (`claude/new-session-4u0edl`),
  so the phases are seven commits on it, not seven PRs into `main`; (b) *decision 10, the size ceiling* — net new script
  lines are ~3,850 against the 3,200 ceiling (docstrings already compacted); per phase: 0 ≈ 460/500, 1 ≈ 775/700,
  2 ≈ 580/500, 3 ≈ 740/800, 4 ≈ 480/500, 5 ≈ 500/500, 6 ≈ 320/600. Applying the whole fixed cut order (4.1 Mermaid
  export ≈ 35, 3.2 `reef-repo` ≈ 125, 3.1b ≈ 20, 3.4 `--apply` ≈ 140, 4.1 `--diff` ≈ 45; 5.6's Read tripwire and
  2.4's `unrequested` were never built; 4.4 is prose) would remove ≈ 365 lines and still leave ≈ 3,480 — over the
  ceiling, and the two phases over budget (1 and 2) hold none of the listed items. Nothing was cut beyond the Read
  tripwire; every mechanism ships with its red test. The owner can order any cut in one line; each is one file.
  **Owner decision (2026-10-16, at merge): no cuts; the ceiling is reset to what 0.6 measured — 3,850 net new script
  lines in all, per phase 0 = 460, 1 = 775, 2 = 580, 3 = 740, 4 = 480, 5 = 500, 6 = 320. The 3,200 figure is history;
  0.7 budgets start from these numbers.**
  (c) *5.7* — no project row ran in this session, so per-row growth is documented as a target and a command, not a number.
- Cuts taken: **5.6 Read tripwire** (first in the cut order; `context.read_lines_max` stays reserved). Not built by
  design: 2.4 `unrequested` as a script (it is the acceptance review's finding).
- **At merge (PR #9 CI):** `test_absolute_path_accepted` dispatched from a hardcoded `/somewhere/else`, which only a
  root sandbox could create — now a fresh temp dir (`tests/test_guard.py`). CodeQL: `ci.yml` gets `permissions:
  contents: read`; the `SECRET_SCAN` constant is renamed `GITLEAKS_GATE` (its value is a command, not a secret —
  the alert was its name); the manifest dependency regex in `reef-c4.py` is rewritten as line matching with
  identical results (`tests/test_c4_threat.py`) so it no longer reads as an HTML filter.

### Phase 0 — verify first, then measure
- **0.0 Verified hook payloads** from a live Claude Code 2.1.301 session: `tests/fixtures/payloads/` (PreToolUse
  inside a sub-agent carries `agent_id` + `agent_type`; Stop carries `stop_hook_active`; SessionStart carries
  `source`; `hooks.json` accepts `timeout` and `onFailure: block`; AskUserQuestion's answers live in
  `tool_response.answers` — schema-derived, headless sessions exclude the tool). Findings and consequences per
  item: `docs/perf/payloads-2026-10-16.md`.
- **0.1 `scripts/reef-cost.py`** — turns, context per turn (mean/p50/p90/max), compactions, cache writes vs reads,
  context share by category, sub-agent transcripts, fix rounds per feature; `--session-start`; `--live` reads the
  last 256 KB only. Tests: `tests/test_cost.py` (known counts exact; boundary+summary = one compaction; 50 MB
  `--live` under 3 s).
- **0.2 Baseline** on a real session: `docs/perf/baseline-2026-10-16.md` (first turn 91k tokens; 43% of context is
  attachments, 31% raw Bash output).
- **0.3 `scripts/reef-eval`** + frozen corpus `tests/eval/corpus/{verifier,hunter,plan-reviewer}.json` (6/6/5 real
  diffs with ground truth, each building to a GREEN gate); live `run` via `claude -p` in a fresh worktree per run,
  mechanical `score` (VERDICT / BLOCKER / `AC<n> FAIL` lines), `compare` (catch-rate and approve-precision must not
  drop). Tests: `tests/test_eval.py` (parser, comparison rule, fixture replay: trusting the hand-off drops the
  catch-rate and is refused; every corpus entry builds green and passes plan-check where the reviewer needs it).
- **0.4 Baseline evals** k=3: `docs/perf/eval-baseline-2026-10-16.md`.

### Phase 6 — lean start and one tree
- **6.1 One tree, feature-based.** `reef-graph.py` loads every `<paths.features>/*/tasks/{,done}` and the flat
  `paths.tasks` into ONE graph (ready set, resources and `graph.parallel` global) and keys the lock on
  `paths.features`; plan-check, reef-queue (status, index, global ADR numbering), the guard and reef-attempt are
  folder-aware; `reef-migrate --layout` moves a 0.5 project to the tree in one reviewed commit with link rewriting
  (the mover shared with reef-recalibrate); `reef-structure --check` knows both layouts. Tests:
  `tests/test_layout.py` (two features form one ready set with shared `resources:` slots; a 0.5 flat project untouched
  passes every check; `--layout` moves everything, rewrites links, a second run moves nothing).
- **6.2 Lean session start.** `SessionStart` entry runs `reef-loop.py tick --session-start --hook`: the handoff head
  (≤ 40 lines), the tick (≤ 30) and the next command as `additionalContext`, capped by
  `writing.session_start_tokens` (8,000; truncated with a note); nothing for a directory without `.reef/config.json`;
  the generated AGENTS.md stays ≤ 80 lines; every skill's re-entry section names only the handoff head and the
  tick. Tests: `tests/test_loop.py::HandoffAndSessionStart`, `tests/test_contracts.py::LeanStart`.
- **6.3 Versioned migrations.** `scripts/reef-migrate` walks `migrations/<from>-to-<to>.py` (idempotent, exit 0/1/2,
  refuses a gap); `/reef-init` runs it before rendering; `0.5.0-to-0.6.0.py` adds only additive keys (the tier
  table, `paths.*` at their 0.5 locations, `writing.*`, `caps.*`, `loop.*`, `context.*`), keeps `gates.test`, writes
  `.reef/version`, offers `--layout`. Tests: `tests/test_layout.py::Migrations`.

### Phase 5 — loop engine and context budget
- **5.1 `scripts/reef-loop.py tick`** — one read of the queue, the task files, the worktrees, `.reef/inflight/`,
  `.reef/verifying/` and the open PRs; the next-action set as data under 30 lines; in flight is the guard's marker
  (stale after `loop.inflight_stale_minutes` → returned); `start | stop | wait | clear-wait` in `.reef/loop.json`.
  Tests: `tests/test_loop.py::Tick`.
- **5.2 The missing dispatch becomes mechanical at turn end.** A `Stop` entry in `hooks/hooks.json` runs the guard,
  which dispatches on `hook_event_name` and calls `tick --assert-no-idle`: refused only when the loop is active, no
  wait, ready tasks, nothing in flight, no stop reason — the same tick hash is never refused twice;
  `stop_hook_active` and `background_tasks` honoured. Tests: `tests/test_loop.py::StopHook`.
- **5.3 No-progress parking and budgets.** K identical ticks (`loop.no_progress_ticks`) with nothing in flight park
  the loop; `caps.feature_tokens` / `caps.batch_tokens` (0 = off) checked through `reef-cost.py --live`. Tests:
  `tests/test_loop.py::Tick::test_no_progress_parks…`, `test_budget_ceiling_parks`.
- **5.4 Context ceiling** on Task/Agent dispatches: `reef-cost.py --live` on the payload's `transcript_path` against
  `caps.context_tokens` (deny: "checkpoint, then /clear", stop reason recorded) and `caps.context_warn` (the hook
  warns through `additionalContext` — verified possible in 0.0). Defaults 0 (off). Tests: `tests/test_loop.py::ContextCeiling`.
- **5.5 Checkpoint and clear.** `scripts/reef-handoff --write` renders HANDOFF.md whole from the tick, the journal
  tail and the open questions (deterministic, no clock); the loop skill lists the ceiling among its stops. Tests:
  `tests/test_loop.py::HandoffAndSessionStart`, `tests/test_contracts.py`.
- **5.6 Reports, never raw material.** `reef-gate.sh --failures` and `reef-ci-local.sh` print the exit code plus the
  failing block (`context.failure_lines`, 60) from the log in `.reef/ci-local/`; truncation inside the gate keeps
  the exit code. The optional Read tripwire was CUT (first in the cut order). Tests: `tests/test_hooks.sh`
  (a 5,000-line failing log → a block under 60 lines with the exit code).
- **5.7 Measured target**: see `docs/perf/baseline-2026-10-16.md` (per-row growth measured at Finishing).

### Phase 4 — architecture and security
- **4.1 `scripts/reef-c4.py`.** Detection (manifests, infrastructure files, dependencies, routes) → persons,
  containers, stores, external systems (cap 9, the most similar pair collapsed and reported) → `reef/architecture/
  workspace.dsl` (Structurizr: one model, L1/L2 views, `# proof:` per element, `Inferred` tags) and the generated
  Mermaid `context.md` / `container.md`; a dependency-free lint; `--diff` is element-level (`missing`, `contradicts`,
  `inferred`; a hand-edited export is drift). Tests: `tests/test_c4_threat.py::C4Model`.
- **4.2 `/reef-c4`** (`skills/reef-c4/SKILL.md`, 16 lines) and `gates.release`: `reef-ci-local.sh --release` runs them
  after the other gates; the generated workflow passes `--ci --release` (release-branch PRs only). Tests:
  `tests/test_ci_local.sh` (`--release` runs them; without it, not).
- **4.3 `/reef-threat`** + `scripts/reef-threat.py`: trust-boundary crossings from the DSL must each have a STRIDE row
  naming mitigation and proof or `accepted: <reason>`; `rows` prints unmitigated ones as found queue rows with
  `touches:`; `fresh`; plan-check demands a fresh threat model for a critical `touches: auth|pii|money` task. Tests:
  `tests/test_c4_threat.py::ThreatLint`.
- **4.4 Adversary system pass** `pass=system` in `agents/loophole-hunter.md` (threat model + a running worktree,
  rows mapped to threat IDs). Eval before/after: `docs/perf/eval-baseline-2026-10-16.md`.
- **4.5 Security gates as proposals.** A new project gets `gates.release` (C4 drift, history secret scan, the stack's
  dependency audit — a missing tool is exit 77, reported as a skip = exit 2); an existing project gets them under
  `.reef/proposed/gates.release.json`, never as a red CI; the CI template installs the auditor and gitleaks.
  Tests: `tests/test_c4_threat.py::SecurityGatesAsProposals`.

### Phase 3 — day zero
- **3.1 Architecture grill in `/reef-init`.** One batched question set (host, shape, scale, store, auth boundary,
  one-year non-goals); `reef-init.py --grill answers.json` renders `reef/architecture/architecture.md` (intent, C4
  L1/L2 in Mermaid, the answers verbatim), draft ADRs for host/store/auth, the queue footnotes in the owner's words
  and batch 1 row 1 = the walking skeleton. A fresh project gets the 0.6 one tree (`reef/…`, `paths.*` follow); an
  existing 0.5 layout is kept and the choice is sticky through `paths.queue`. Tests: `tests/test_init.py::DayZero`
  (the fixture answers render the files; a second run writes nothing; the legacy layout is kept).
- **3.1b Stack opinions** `templates/stacks/{node,python,rust,go}.md` (≤ 10 lines each) distilled into AGENTS.md's
  `## Conventions` at init, never copied. Tests: `test_init.py` (a Node fixture gets Node, not Python).
- **3.2 `scripts/reef-repo`** — gh-based, idempotent: private repository on `--create` (asks), release-branch
  protection (PR required, the CI check required, no force-push, no deletion), secret-scanning push protection,
  `.github/CODEOWNERS`; queries first, writes only on a difference. Tests: `tests/test_dayzero.py::RepoProtection`
  (a mocked gh records the exact calls; a second run issues none).
- **3.3 `/reef-explore`** (`skills/reef-explore/SKILL.md`, `commands/explore.md`): N `Explore` agents in one message,
  Observed/Inferred with a proving path; locked by 1.3. Tests: `tests/test_dayzero.py::ExploreLock`.
- **3.4 `/reef-assess` + `scripts/reef-recalibrate` + `scripts/reef-structure`.** `plan` classifies every document
  (decision → ADR with `Supersedes:` and the one-line statement; spec for open work → feature folder with FR keys and
  a queue row; glossary → merged; runbook/stale/duplicate → `reef/archive/<date>/<path>` with its index; README,
  LICENSE, CONTRIBUTING, SECURITY, CHANGELOG, CODEOWNERS, docs a docs build serves and anything referenced from
  code or CI are kept) into `reef/recalibration.md`; `--apply` is ONE commit with relative links rewritten and a
  broken link refusing and restoring; `history` derives `branches.*`, `merge.by`, the commit convention, merge style,
  tags and CI triggers; `reef-structure --check` fails a process document outside the layout (both layouts) and joins
  `gates.extra`. Tests: `tests/test_dayzero.py::Recalibrate` (the fixture yields Reef ADRs with `Supersedes:`, the
  archive tree with its index, zero broken links; a file referenced by mkdocs.yml or code stays; a second apply moves
  nothing; `git revert` restores the fixture byte for byte; the structure check fails on a stray document; derived
  branches match a develop → main history).
- **3.5 Existing spec tooling is read, not duplicated.** `reef-init` detects `.specify/constitution.md`,
  `.specify/memory/constitution.md` and `specs/*/spec.md`, points AGENTS.md at them and writes no second
  constitution. Tests: `test_init.py::DayZero::test_existing_constitution_is_pointed_at_never_duplicated`.

### Phase 2 — spec and quality
- **2.1 The feature folder and its spec.** `<paths.features>/<slug>/{SPEC.md, specs/, adr/, tasks/}` (0.6 projects;
  a 0.5 project keeps flat `tasks/`): `templates/spec.md` (Row, grill, scope, non-goals, Already shipped, `FR-n [layer]`,
  `SC-n`, owner decisions, Architecture impact); plan-check validates the slug (2–5 kebab words, no number, no
  generic word), SPEC keys and layer tags, child specs' `Parent:`, ACs citing keys of their own folder, the
  structure, `plan.max_tasks` (12 → split); the stamp covers the whole folder; `reef-queue.py check` runs the
  structure and slug checks, `index` generates `reef/features/README.md`, `adr-number` numbers one global sequence
  across `reef/architecture/adr/` and every feature `adr/`. Tests: `tests/test_feature_spec.py::FeatureFolder`
  (missing key → fail; spec edit → stale stamp; 13 tasks → split; bad slugs refused; stray Markdown → fail;
  pre-0.6 → warning).
- **2.2 Criterion and proof split, dual-shape.** `templates/task.md`: `AC-n (FR-m)` one sentence, `## Proof` table;
  plan-check enforces the new shape only when the table exists (old shape stays valid), reads Proof rows for the
  claimed-twice check; prose lints `writing.sentence_words` 25 / `writing.criterion_words` 50 fail under 0.6, warn
  older; journal rows carry per-AC statuses (`reef-queue.py check`). Tests: `tests/test_feature_spec.py::ProofSplit`.
- **2.3 Four-kind blocking bar** in `agents/verifier.md` and `skills/reef-review/SKILL.md` (regression, bypass,
  correctness, failed AC; all else NIT). Eval before/after: `docs/perf/eval-baseline-2026-10-16.md`.
- **2.4 `scripts/reef-converge <feature>`** executes the Proof table: `missing` / `contradicts` appended to the one
  rollup, `Converged` writes nothing. Tests: `tests/test_feature_spec.py::Converge`.
- **2.5 Path-class rails.** `tiers.design.paths`, `tiers.critical.paths`, `touches:` (pii/money/auth → critical,
  migration → design + `Rollback:`); `reef-tier.py` computes design/critical and only raises; `reef-init` lists
  older tasks the rails would move. Tests: `tests/test_feature_spec.py::Rails`.
- **2.6 Browser evidence** in `agents/verifier.md` (observed in a browser, or `Not verified in a browser:`).
- **2.7 Hand-back and report checks as code.** `reef-claims.py check --handback <file>` (150 words, a claims list),
  `reef-claims.py report <file> --task <task>` (RUN header, `RULE AC<n>` per criterion citing its Proof row,
  evidence per AC, `writing.report_words` warn-only until measured). Tests: `tests/test_feature_spec.py::HandbackAndReport`.

### Phase 1 — foundations and trust binding
- **1.0 Version marker and four tiers.** `reef-init` writes `.reef/version`; `tier: critical | design | full | light`
  (`schemas/task.schema.json`, `touches:`); the tier table `tiers.<tier>.{roles,effort,paths}` in
  `templates/config.json` (critical: fable judges, opus author, effort high; light: `plan_reviewer: none`);
  `reef-attempt` resolves `author:`/`verifier:`/`adversary:` through it (effort only rises); `reef-plan-check.py`
  gains `critical`, `--needs-agent` (exit 3 on an all-light plan), `--digest`; the guard resolves the tier from
  the `REEF-TASK:`/`REEF-FEATURE:` line every role dispatch carries, treats critical like design for the
  adversarial pass, maps `Explore → mechanic`; the pre-commit closes critical like design. Tests:
  `tests/test_tiers_lock.py::FourTiers` (light with opus → DENY; critical with sonnet → DENY; critical without
  `adversarial-plan` → DENY; one full task still needs the reviewer; an unset table is exactly 0.5),
  `tests/test_hooks.sh` (critical into done/ without `adversarial-guard:` → rejected).
- **1.1 Review records bound to the forge SHA.** `scripts/reef-record <feature> <verdict>` writes
  `.reef/review/<feature>.json` from `gh pr view` / `gh api …/git/commits`; under `merge.by: loop` the guard
  refuses `gh pr merge` / `gh api …/merge` unless a GREEN record names the forge head — a clean base merge
  (`git merge-tree --write-tree`, git ≥ 2.38) or claims-only commits are the only carry-overs; gh under its own
  deadline, fail closed. Tests: `tests/test_record.py` (push after GREEN → DENY; gh fails/slow → DENY; clean
  base merge → allow; rebase → DENY; old git → DENY; merge.by human → nothing gated).
- **1.2 Human-only plan approval.** `/reef-plan` asks `Approve plan <slug> at <digest16>?`; the PostToolUse hook
  `scripts/reef-approval.py` writes `.reef/approvals/<slug>.json` only on `Approve` with the current digest (a
  timeout, another label or a stale digest writes nothing); `--verify-stamp` and the guard require it for
  features planned under 0.6 (`planned_under` in the stamp), warn for older ones; hand-written records are denied
  (Bash writes and the new `Edit|Write|MultiEdit` matcher). Tests: `tests/test_tiers_lock.py::HumanOnlyApproval`.
- **1.3 Reviewer lock.** `agent_type` in the payload (class code, verified live): verifier, loophole-hunter,
  plan-reviewer and Explore get no mutating git, no Bash write, no CI wait; `.reef/verifying/<id>` (written on an
  allowed judge dispatch) locks typeless sub-agent calls too; `gh pr checks --watch`, `gh run watch`, `sleep ≥ 60`
  denied for every sub-agent. Tests: `tests/test_tiers_lock.py::ReviewerLock`.
- **1.4 Fail-closed guard with a deadline.** `timeout` + `onFailure: block` on every matcher (schema verified);
  `signal.alarm` deadline inside the guard (`REEF_GUARD_DEADLINE`); `scripts/reef-guard-profile.py` →
  `docs/perf/guard-profile-2026-10-16.md` (timeout ≥ 5 × p95, floor 10 s); no python3 → a dispatch is denied.
  Tests: `tests/test_tiers_lock.py::Deadline`, `tests/test_contracts.py::LedgerClasses::test_hook_timeouts_match_the_profile`,
  `tests/test_hooks.sh` (no python3 → exit 2).
- **1.5 The guard guards itself.** `scripts/reef-*`, `.githooks/*`, `hooks/hooks.json` and the
  `roles|caps|gates|tiers` keys of `.reef/config.json` change only under a `critical` task in flight
  (`.reef/inflight/<id>`, written by the guard on an allowed implementer dispatch) or inside Reef's own
  repository (`CLAUDE_PLUGIN_ROOT`); `reef-init --accept` stays allowed. Tests: `tests/test_tiers_lock.py::GuardGuardsItself`.
- **1.6 `# CLASS: code|tripwire` headers** on every script and the pre-commit; `tests/test_contracts.py::LedgerClasses`
  ties README ledger rows to a script of that class; `.github/workflows/ci.yml` job `code-change-needs-a-test`.

## 0.5.0 — the graph executor and the full project setup

- **Task graph executed, not just declared.** `scripts/reef-graph.py` computes the ready set from
  `blocked-by`, `resources:` and `graph.parallel`; `/reef-task` dispatches every ready task in
  parallel, each in its own worktree (`reef-graph worktree`); the guard refuses any implementer
  dispatch outside the ready set and marks the task `in-progress` on allow, under one graph-wide
  lock. `reef-graph lock <resource> -- cmd` serialises heavy commands (2 slots by default).
- **Guard rules from a measured merge wave:** `git stash` denied (one stack serves every worktree);
  a gate piped into another command without `pipefail` denied (the pipe hides the exit code).
- **`tier:`** (light / full / design) on tasks; plan-check refuses a tier that does not match the
  complexity (mech ⇔ light). `resources:` is plan content; `worktree:` and `in-progress` are
  execution state the stamp ignores.
- **The adversarial stage.** `agents/loophole-hunter.md` ("how can this be green while the defect happens?"),
  mandatory twice on `tier: design` — on the plan before code (the guard refuses the first dispatch
  without `adversarial-plan:` bound to the plan's content) and on the finished guard before close (the
  pre-commit refuses a design-tier task entering `done/` without `adversarial-guard:`); never on mech.
  `scripts/reef-adversarial` records only a PASS without BLOCKER lines.
- **Claims bound to the round.** `scripts/reef-claims.py check` rejects a claim at a line the round did
  not add; `claims-only` is the one commit allowed after GREEN. Verifier and hunter attack the last
  round's fix first; "cannot verify here" needs the probe pasted.
- **`/reef-init` is the full project setup.** `scripts/reef-init.py` renders `templates/project/`
  (AGENTS.md, constitution, queue, ADR convention, journal, handoff, day-zero checklist, release-only
  CI, Dependabot on the integration branch, the hooks and every Reef script) adapted to the detected
  stack — idempotent: absent → written, identical → skipped, different → never overwritten (the
  rendering lands in `.reef/proposed/` with a diff; `--accept` applies it). Config keys are merged,
  never changed. `scripts/reef-ci-local.sh` (every gate, every exit code, 2 = skipped ≠ success; CI
  runs the same script), `scripts/reef-tier.py` (a tier only gets heavier), `scripts/reef-queue.py`
  (status derived from task files, ready rows, consistency, ADR numbering at merge). plan-check reads
  AGENTS.md as the brief when CLAUDE.md is a pointer. `/reef-loop` drives the outer graph.
- **Expensive measurements once per release** (project rules, `templates/project/AGENTS.md`): screenshots of
  every page, printed documents bound to the tree run on the frozen integration branch, in parallel lanes, not on
  every feature branch; a feature branch merges with them stale only when its other gates are green, stale told
  apart from failing by test name, never by file; a failure names the merge that caused it and holds the release.
- **The hunter ranks holes by real cost** (`agents/loophole-hunter.md`): it stops when the remaining holes' worst
  case is below the cost of another pass — no 100% mechanical guarantee for a guard whose worst case is cosmetic.
- Arabic user manual: `docs/manual/ar/index.html`.
- Model per role read at dispatch (`roles.*`, the guard refuses another model); `agents/mechanic.md`.
- Defaults: `graph.parallel` 10, `resources.heavy.slots` 2, `worktree.setup` per project.
- Version 0.5.0 (0.4.0 was `parallel-loop-compat`: merge setting, one cap per item, draft ADRs,
  per-feature stamp, fast/full gates, model per role, rule-first verifier).
