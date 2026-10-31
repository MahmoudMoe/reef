# Changelog

## 0.7.4 (unreleased)
- **An approval binds the plan's full digest, not its first 16 hex** (the security review of #259). A plan approval (`.reef/approvals/<slug>.json`) and a plan review (`.reef/review/plan-<slug>.json`) bound the plan by `digest16`, a 64-bit prefix an agent writing both plans could collide in ~2^32 tries. Every writer (the hook and `--owner`, `--proxy`, `--from-issue`, `reef-record plan-review`) stores the full `digest` too, and `record_binds` in `reef-plan-check.py` compares it in full for the guard's check, the review and the row; the owner still reads and types 16 hex. When two checkouts' plans share the question's 16 hex, the hook approves neither. A record written before (no `digest`) is read at its 16 hex in 0.7.4 only — a contract test goes red once the plugin passes 0.7.4 with that fallback still in. A STALE line names the full digests. tests/size-budget.json raised: `script_lines` 17,959 → 17,967 (the one comparison, its STALE wording, the hook's refusal).
- **An approval and a stamp run the plugin's own plan check** (the security review of #259). `reef-approval.py` (the hook, `--proxy`, `--from-issue`), the guard's stamp check and `reef-record plan-review` ran `<checkout>/scripts/reef-plan-check.py`, so a modified copy could print any digest, a green check or a forged `files` map and the hook or the guard believed it. Each runs the plan check beside itself now, as the guard already did for `reef-graph.py` (so the hook and the guard run the plugin's; a copy run from a checkout reads its sibling, which the guard protects as it protects itself); the tick's plan hold and the row's digest do the same, the copy only marks a Reef layout, and a stamp check that cannot run denies. tests/size-budget.json: unchanged (nothing grew).
- **Lightening step 5b: `/reef-plan` says the same in fewer words.** 2,150 → 1,738 words; every rule kept (a fresh old-against-new read found seven small ones, all folded: a HALT stops the review, the gate opens on a passed review, granularity is judged at the gate, the re-review is fresh; and four wording fixes). tests/size-budget.json lowered: `prose_words` 23,291 → 22,879.
- **An approval binds to the plan of record** (the owner's project, row 187: Mahmoud approved the amended plan and `reef-approval.py --proxy` refused it — a task worktree branched before the amendment held the older plan and `git worktree list` named it first). `--proxy` and `--from-issue` read the plan from the feature's own worktree, `<main>/.reef/worktrees/<slug>` by its exact path, as the row machine does, else the main checkout — never the first checkout that holds a copy; an approval of an older copy is stale wherever that copy lives, and a refusal names every checkout's digest. tests/size-budget.json raised: `script_lines` 17,937 → 17,959.
- **Lightening step 5b: `/reef-loop` says the same in fewer words.** 2,229 → 1,828 words; every rule kept (a fresh old-against-new read found one that mattered, folded: a CHALLENGE amends the plan as an Edit, never an owner question; and six low-risk clauses restored). tests/size-budget.json lowered: `prose_words` 23,692 → 23,291.
- **Lightening step 5b: `/reef-task` says the same in fewer words.** 2,291 → 1,686 words, 52 lines; every rule kept (a fresh old-against-new read found none lost; its two small ones folded: the hunter is snapshot-checked like the verifier, and `reef-merge-base` runs before each wave). tests/size-budget.json lowered: `prose_words` 24,297 → 23,692.
- **Lightening step 5a: the prose carries rules, not history.** The dated notes in the skills and agents ("the owner's go, 2026-10-24", "measured 2026-10-17", …) are gone; where a note held a rule, the rule stays ("once, never a loop", the report's one home, `ready --with-found`). The releases before 0.7 moved to `docs/changelog-archive.md`. Pinned by `ProseCarriesRulesNotHistory`. tests/size-budget.json lowered: `prose_words` 24,538 → 24,297.
- **The verbs tell one story** (the CLI review, 2026-10-31, the third group): Enter on the autopilot panel records the day contract's approval when it has none (the one line the owner had to type) and starts it when it has; `reef --help`, `-h` and `help` are the menu; `reef night` without a contract says where one comes from (`/reef-night`) and seeds nothing; `reef screen --once` prints the board and the inbox as text, no keys, and exits 2 outside a Reef project; `probe` and `resume` are verbs of `reef`; `reef status` exits 2 on an owner wait, as `watch` does, and says so; the skills and the overview name `reef approve <row>`, `reef answer <row> "<text>"` and the screen. tests/size-budget.json raised: `prose_words` 24,437 → 24,538, `script_lines` 17,930 → 17,937.
- **The pages and the keys** (the CLI review, 2026-10-31, the second group): PLAN draws its selection and shows the panel, so ↑↓, a digit, Enter and a verb there act on what is seen; `d` shows the doctor's FAIL and WARN lines first (the panel kept its last twelve, the warnings were its first); q and Esc on the help and the autopilot panel go back to the page they were opened from; Esc never quits and arrives at once (`set_escdelay`); the tabs line names the board's age only when a reading is overdue, and the help names the real intervals (inbox 10 s, board 2 min, doctor 15 min); `s` asks `y/N` before stopping the runner; the keys line wraps between keys, never inside one. tests/size-budget.json: unchanged (nothing grew).
- **The screen stays smooth** (the CLI review, 2026-10-31, its top findings): a command runs in its own thread and its lines stream into the panel as they come (`u` used to freeze the screen for minutes and was killed mid-step past 900 s); after a successful update the panel keeps the update's last word, no reading is spawned, and the next key restarts the screen; Enter on a row that is yours opens INBOX on its item, on any other row shows the row from the board — no subprocess; the box says `yours: <the command>` or `the runner's next: …`; after a command the doctor's lines stay until the new reading lands. tests/size-budget.json: unchanged (nothing grew).
- **The screen after the owner's walk** (2026-10-31 19:00): an approval the owner already gave (its record in `.reef/approvals/` at the question's digest) no longer sits in the inbox until the runner wakes; Tab, i, p and w work from every page (LOG and help included — Tab from LOG starts the cycle again at WORK); the log page answers t (oldest), b (newest, following), [ and ] (a page) beside Home/End/PgUp/PgDn a Mac keyboard lacks; every sub-page's first line says `q back`, and the help says where q quits and where it goes back. tests/size-budget.json: unchanged (nothing grew).
- **Lightening step 4 — orphans and aliases** (`docs/design/lightening.md`; the owner, 2026-10-31: "/reef-plan and /reef:plan — that
  is duplication too", his call: delete). `commands/` held fifteen three-line files that each invoked a skill, so every verb showed
  twice in Claude Code's menu (`/reef:plan` and `/reef:reef-plan`); every document, prompt and the runner name `/reef-<verb>`, which
  is the skill. The fifteen are gone; `commands/reef.md` — the overview, which has no skill — stays. The OpenCode host writes its
  command stubs from the skills now (one per `SKILL.md`, plus the overview); the doctor's stop line and the project README template
  say `/reef-<verb>`; the budget test pins it: the folder holds the overview alone and no Reef text names a `/reef:<verb>` alias.
  `orphan_scripts` was already 0 — nothing else to remove. tests/size-budget.json: unchanged (nothing grew).
- **The screen restarts itself after an update** (the owner, 2026-10-31 18:50: `u` inside the screen applied a new Reef, then the
  screen crashed — `ImportError: cannot import name 'die' from 'reef_common'`). The process kept the old code in memory while the
  files on disk were new; the next lazy load of a sibling script (reef-run.py, for the autopilot panel) imported the new file against
  the old module. After a successful `reef update` run inside the screen, the screen ends curses and runs the same command again in a
  fresh process (`restart_screen`); a failed update leaves its output on the screen and restarts nothing. tests/size-budget.json: unchanged (nothing grew).
- **Lightening step 3 — one fixture module for the tests** (`docs/design/lightening.md`; consolidation step 4). `write(root, rel,
  text)` was defined in twelve test files and a `git(d, *a)` helper in fifteen, in four shapes; `tests/_fixtures.py` holds each once —
  `write`, `git` (the CompletedProcess, `check` on request), `git_out` (stdout), `git_text` (stripped), `git_repo` (a temporary repository
  with its branch and config), `load_script` — and a file imports the shape it used under the name it used, so its tests read as
  before; a suite's own `project()` stays, it is that suite's world. The budget test pins it: no test file carries its own copy. The
  plan's guess of −1,500 test lines was wrong — the copies were four lines each; what is gone is the drift between them. tests/size-budget.json: unchanged (nothing grew).
- **Lightening step 2 — the same name in two scripts** (`docs/design/lightening.md`). After step 1, thirty definitions still
  shared a name across scripts. A true duplicate merged into `reef_common` — `load_sibling` (the three `plan_check_module` loaders
  and reef-graph-run's `load_script`), `git_root` (the two `root_of`), `reef_dir`, `section`, `slug_error` with `SLUG_RE` and
  `GENERIC_SLUGS`, `served_dirs`, `config_homes` with `HOME_KEYS`; a false one — two things under one name — renamed so a reader
  stops confusing them (reef-row's `queue_rows` → `queue_status`, reef-run's `release_hold` → `drop_session_hold`, reef-loop's
  `render` → `render_status_page`, reef-init's `render`/`detect` → `render_template`/`detect_stack`, reef-handoff's `render` →
  `render_handoff`, reef-recalibrate's `render_plan` → `render_moves`, reef-plan-check's `parse_args` → `parse_check_args`,
  reef-threat's `lint` → `lint_threat`, reef-factory's and reef-graph-run's `script` → `own_script`/`project_script`, reef-record's
  `gh` → `gh_text`, reef-repo's `gh` → `gh_rc3`, the screen's loader → `sibling_module`). A script's own `cmd_<verb>` handlers —
  one per CLI, by convention — the pin no longer counts. `duplicate_defs` 30 → 0. tests/size-budget.json: unchanged (nothing grew).
- **Lightening step 1 — the shared helpers, finished** (`docs/design/lightening.md`). Every local `run` (eight scripts), `git`
  (seven), `die` (thirteen), `plugin_root` and `plugin_version` (two each) was a two-to-four-line adapter over `reef_common`'s
  `run()`/`git()` or a copy; each is one shared shape now — `run_rc`, `run_rc3`, `run_out`, `run_all`, `git_rc`, `git_out`,
  `git_checked`, `git_text`, `die(msg, code, prefix)`, `plugin_root`, `plugin_version` in `scripts/reef_common.py` — imported, the
  script's own defaults kept with `functools.partial`, every call site and every message unchanged. Five names that meant two
  different things were renamed so a reader stops confusing them (reef-init's `run` → `render_tree`, reef-attempt's `run` →
  `run_attempt`, reef-approval's `worktrees` → `all_checkouts`, reef-opencode's `frontmatter` → `split_frontmatter`, reef-factory's
  `say` → `note`); reef-merge-close's `fail` is `die` with its prefix. `duplicate_defs` 64 → 30. tests/size-budget.json: unchanged (nothing grew).
- **Lightening step 0 — the pins** (`docs/design/lightening.md`, new; the owner, 2026-10-31: "a comprehensive plan to wipe
  duplication, keep duplicate scripts from coming back, and remove what has no use"). `tests/size-budget.json` gains two numbers
  that ratchet like the other three: `duplicate_defs` — a function name defined in more than one script, each definition past the
  first (64 today: `die` ×13, `run` ×10, `git` ×8 …; the guard's own copies of shared helpers are the one exception, by design) — and
  `orphan_scripts` — a script no skill, agent, hook, command, template or other script names (0 today). The budget test measures
  both and names the offenders when one grows; a planted tree with one more `def run` in a script nothing names moves each by one.
  The plan's steps 1–5 (the shared helpers finished, the same name in two scripts, one fixture module for the tests, orphans and the
  `commands/` aliases, the prose) each ship as their own PR with no behaviour change and a lower budget. tests/size-budget.json: unchanged (nothing grew).
- **Graph mode is for the sessions you run yourself; the gate's record is guarded; the doctor says where graph mode runs** (the
  owner, 2026-10-31: "does the autopilot have graph mode? why was it off, who turned it off?" — nobody: graph mode is fail-closed
  behind a probe that proves the guard reaches workflow agents, the probe lives in `/reef-graph`, and on his project nobody had run
  it; a live probe the same day settled the rest: a headless `claude -p` session has no Workflow tool at all — "The Workflow tool
  isn't available to me" — so the runner, the autopilot and a night can never run graph mode). The loop's tick now picks chat mode
  under the runner (`REEF_RUNNER`) whatever the gate says, instead of asking a headless session for a workflow it does not have; the
  doctor prints `graph gate: GATE OK` / `FAILED (<why>)` / `none — /reef-graph once, in a session, proves it … the runner's sessions
  build in chat mode either way`; the README's `/reef-graph` row says the same. `.reef/graph/gate.json` joins the records the guard
  lets only scripts write (a planted record would let a workflow the hooks do not reach run); `probe-check` believes the guard's own
  words in the probe's output, never the agent's flag alone, and records a missing result as FAILED with its cause, the leaked file
  removed either way. tests/size-budget.json raised: `script_lines` 17,942 → 17,989.
- **`/reef-watch` and the autopilot by name** (the owner, 2026-10-31: "add reef-watch so I can see the log from inside Claude Code",
  "I have not seen a /reef:autopilot command"). `python3 scripts/reef-run.py watch` takes two bounds — `--tail N` (the last N lines)
  and `--for S` (follow S seconds, then one line says the runner still runs and how to follow on; `0` returns at once) — because a
  session's tool holds until a command returns; the terminal's `reef watch` stays unbounded. The `reef-watch` skill shows the last
  forty lines, or `follow`s for a hundred seconds, never an unbounded tail. `/reef-run`'s description and argument hint name
  `autopilot` (the same as `reef autopilot` and `a` on the screen). tests/size-budget.json raised: `prose_words` 24,146 → 24,437, `script_lines` 17,928 → 17,942.
- **The screen answers at once** (the owner, 2026-10-31 12:30, on an issues queue: "the CLI is heavy and hangs today — I press
  something and nothing happens"). A key pressed before the board landed had waited up to five seconds and been re-queued — every key
  felt dead while the row machine asked GitHub about eight rows — and the board stayed "reading the rows … 3/8" until the last row
  landed. Now no key waits: it acts on what is there (Tab, `i`, `w`, the verbs, `q` at once; a digit or Enter needs its list). The
  board is read in two steps: the queue first, at once — every open row listed with a `…` mark, its id and item visible — then the row
  machine, four rows at a time, each row's state filled in the moment it lands. The inbox is read every ten seconds and the board every
  two minutes (`INBOX_SECONDS`, `BOARD_SECONDS`; any command reads both again): each row's state is a subprocess that may talk to the
  forge, and that was the heat. tests/size-budget.json: unchanged (nothing grew).
- **The log is on the screen** (the owner, 2026-10-31: "when I open the log it should appear in a big box under the screen, with
  navigation"). The WORK board carries the runner's last eight live-log lines under the table, colored by what they say (cyan an agent
  or a job started, green returned, red a failure in its verdict, yellow a wait), shed first on a short terminal; the LOG page scrolls
  by line and by page (`PgUp`/`PgDn`), jumps to the ends (`Home`/`End`), finds a line (`/`, the hit as the page's last line; `n` the
  next older) and is colored the same way; its header says where the page is. Two lines from the same morning's autopilot log: a
  runner job is started from the row's worktree (the task and review skills; a converge from the base checkout exited 2 — no task
  files there — and cost a session), and Mahmoud's day report path is under the session's scratchpad (the loop skill; a prompt that
  named none had him asked twice). tests/size-budget.json raised: `prose_words` 24,060 → 24,146.
- **The update is Reef's too** (`docs/design/owner-hands-off.md` step 6; the owner, 2026-10-31: after every merge in Reef a person told
  him to run `reef update`, then two Claude Code commands). The screen's doctor reading now fetches the plugin clone itself (`--fetch`),
  every fifteen minutes in its thread; the doctor's lines about a new Reef — the clone behind its upstream (`plugin: a new Reef, 3
  commit(s) since your copy: <the newest subject>`), the version, the scripts (`scripts/reef` compared too) — name ONE verb where the
  project has `scripts/reef` (`python3 scripts/reef update`), so the inbox holds one item of kind `update` and both headers say `a new
  Reef waits (u)`. `u`, or Enter on the item, runs `reef update` inside the screen: the plugin pulled, the copies refreshed, one commit
  pushed, the setup re-proved when its digest changed — and now the Claude Code marketplace refreshed by Reef (`claude plugin
  marketplace update <market>`), the plugin enabled again if that left it disabled (the 2026-10-28 incident), and a done line that hands
  the owner no step (the runner's next session runs the new Reef; `/reload-plugins` is named once for a window already open).
  `reef-update.py --no-reload-line` leaves the last word to its caller; `reef screen --once --fetch` asks the forge too. tests/size-budget.json raised: `prose_words` 24,020 → 24,060, `script_lines` 17,901 → 17,928.
- **Long work is the runner's** (`docs/design/owner-hands-off.md` step 3; the owner, 2026-10-31 04:30, "I really want autopilot on":
  twice that night a headless session ended its turn while a background converge of its own ran on, the process waited for it and
  the runner for the process — forty idle minutes). `python3 scripts/reef-run.py job <name> -- <command…>` starts the command
  detached under the runner (output in `.reef/run/jobs/<name>.log`, its rc in `<name>.json`); the session records
  `wait "job: <name> — …"` and ends its turn; the runner waits for the job (a live line every two minutes, the screen's runner line
  names it) and starts the next session with `JOBS DONE … <name> rc=<rc>`. A job's command is judged by the guard exactly as if the
  session typed it, and the job runner's own verb is never typed. The headless prompt and the loop, task and review skills say so.
  **The loop's merge is pre-allowed where the config says the loop merges** (`merge.by: loop`, or the default rule): Claude Code's
  auto-mode classifier had refused `gh pr merge` inside headless sessions and handed every merge back to the owner; the runner now passes
  `--allowedTools "Bash(gh pr merge:*)"` (and the job verb); the guard still requires the GREEN record. tests/size-budget.json raised: `prose_words` 23,854 → 24,020, `script_lines` 17,704 → 17,901.
- **The screen reads at a glance** (the owner, 2026-10-31 04:35, a batch of ready rows: "colors vanished", "REEF is black and white,
  small, not visible", "spaces, order"). The palette follows the state the eye looks for: green can start · cyan building · yellow
  yours · red blocked · dim done; the REEF banner is in color; a line of air sits between the tabs and the table; the selected row is
  the highlight alone, no second arrow beside its mark. tests/size-budget.json: unchanged (nothing grew).
- **The board's task counts are the row machine's** (the owner's first working board, 2026-10-31 03:57: every row said `tasks 0/0`
  while rows 4 and 7 had finished theirs — the plan's files live in the row's feature worktree until it merges, and the board had
  counted the main checkout). `reef-row.py state --json` now carries `tasks: {done, total}`, counted where the folder is, and the
  board takes it (the main checkout's folder is the fallback). The autopilot line counts Mahmoud's plan approvals of the day
  (`.reef/approvals/<slug>.json`, `by: mahmoud (proxy)`) beside his day decisions; the runner's start shows as a clock time. tests/size-budget.json raised: `script_lines` 17,701 → 17,704.
- **The screen never freezes** (the owner, 2026-10-31 03:05, the first run of the fourth screen on an issues queue: "nothing works
  and still in black and white" — the board had asked the row machine about every row, one subprocess after another, on the UI
  thread; the first frame stayed for minutes and the keys were dead). Every reading — the inbox, the board, the doctor — now runs
  in a background thread; the screen draws and the keys answer meanwhile; the first frame counts the rows as they arrive (`reading
  the rows … 3/7`), the row machine is asked about four rows at a time, and a key pressed before the first reading landed waits
  for it briefly instead of being dropped (`q` never waits). After a command the last good board stays until the new one lands. tests/size-budget.json: unchanged (nothing grew).
- **The README and the two sites, reworked** (the owner, 2026-10-31: "rework readme.md and the arabic/english site — simplicity and
  smartness"). The story first: *you write the work, Reef does it, you decide twice*; then **three ways to run it** — the screen
  (`reef`), the autopilot (`reef autopilot`, Mahmoud deciding inside your contract), a night (`/reef-night`), by hand — one table;
  the screen described as it is (WORK, the inbox, PLAN, LOG, the autopilot panel, the runner line that says what the session is
  doing); Mahmoud as the project's CTO in the roles table and on both sites; the autopilot in the situations table, in "What you
  accept", in "When it stops" and in the status; the English site's hero and a first "Hands off" tab; the Arabic manual's lead,
  its autopilot and screen entries, its asks table. Every pinned sentence kept. tests/size-budget.json: unchanged (nothing grew).
- **The reef screen, fourth design** (the owner, 2026-10-31: "before I choose anything I want to see what is pending, what I can
  start with, what can go in parallel and what cannot, the progress; then I choose the order, start the autopilot, and it shows
  me what it will finish and which issues it closes"). `reef` opens on **WORK**: the current batch's rows with a mark (✓ done ·
  ▶ building · ○ can start now · ⏸ waits on the open rows it depends on · ⧖ yours — a gate or a question), tasks done/total,
  the lane (the module the Item names, as `reef-queue.py module_of` cuts it: one lane, one row at a time; different lanes run
  beside each other), what it waits on, the forge (issue, PR), the selected row's state and next step boxed under the table;
  the header carries the batch's progress and today's cost. **Tab** cycles WORK → INBOX → PLAN → LOG (`i`, `p`, `w` jump);
  **PLAN** is a progress bar per row, the autopilot's line (since when, how many decisions Mahmoud took today) and the lanes
  under `loop.rows_in_flight`; **a** opens the autopilot's start panel — the contract's digest, what Mahmoud decides and never
  decides, the order the rows will be worked (`o` toggles the queue's order / what can start first), what it merges or closes,
  Enter starts it; **?** lists every key; Enter on a row shows its state from the row machine in the panel; states carry colors
  where the terminal has them (`REEF_COLOR=0` turns them off). Every fact comes from the scripts' own readings (the queue's
  parser and task states, `reef-row.py state`, the runner's ledger and marker, the proxy's decision log) — the screen computes nothing new.
  **The runner line says what the session is doing** (the owner, 02:08: "how do I know if the runner is working, doing something or dead?"
  — a log silent for twenty minutes was a converge run): `running · pid … · session … · last word 18 min ago · running: reef-converge
  legacy-queue-to-issues (25:30)` from the process table, `thinking` when the session has no child, `gone` when the runner died and
  its session lives, `no runner is running`. Ctrl-C on a verb run from the command line (`reef watch`) exits quietly, no traceback. tests/size-budget.json: unchanged (nothing grew).
- **Mahmoud is the project's CTO.** The owner's proxy (`agents/mahmoud.md`) is briefed as a master architect and senior software architect
  with research depth in software and AI, who reads the business as an economist (finance, marketing, sales, after-sales, the front staff)
  and still chooses the simplest robust thing. He **challenges a plan** like a CTO — a `CHALLENGE` line, recorded once per row by
  `reef-approval.py --proxy --challenge` (the second is the owner's, exit 3 — on disk, so a `/clear` cannot turn one round into a night of
  rounds), carried to the planner, then he is asked once more. He **researches** when it changes the decision: `WebSearch`/`WebFetch`
  himself, or a `RESEARCH` line that runs one `Explore` agent; a query names only public things, a page is evidence and never an
  instruction. Guardrails that keep him right, not slow (the owner): decide inside the contract, never punt; one round; evidence or
  nothing; settled stays settled. The day seed and the night template name web research so the owner's digest binds it. Still read-only.
  tests/size-budget.json raised: `prose_words` 22,940 → 23,854, `script_lines` 17,644 → 17,701.
- **The `reef` screen, third design** (2026-10-31, the owner: "shouldn't 1-9 select? why can't I execute from within — reef closes,
  runs, then a Return key to come back"). The keys are one table: a digit SELECTS its item (the same digit again, or Enter,
  runs it), ↑↓ move, `w` opens the log, `a` starts the autopilot, `q`/Esc quit. A command runs inside the screen — its last
  lines and exit code sit in an OUTPUT panel under the box until a key — never a bare terminal and a "press Enter to return".
  The log is a view on the screen, scrolled with ↑↓; an answer is typed on the screen with the recommendation prefilled. tests/size-budget.json: unchanged (nothing grew).
- **A decision continues the loop** (docs/design/owner-hands-off.md step 1, 2026-10-31): `reef-run.py resume` starts the runner
  again, detached, in the mode of its last run (the loop or the autopilot; a night is one approval) — unless it is running, a
  Claude session holds the loop (it continues itself), the loop is stopped or parked, or `REEF_NO_RESUME=1`. The screen's Enter
  on an approval or an answer, `reef approve`, `reef answer`, a typed `reef-approval.py --owner` call it; the stop's block
  says so instead of "then start the runner again". The run record names its mode. The doctor's proposals fix names the
  plugin's `reef-init.py --root <root> --accept <file>` — a project has no `scripts/reef-init.py` (the owner pressed it). tests/size-budget.json raised: `script_lines` 17,541 → 17,644.
- **The runner never stops dead** (docs/design/owner-hands-off.md step 2; 2026-10-30, the owner: task 403's 85-minute run died
  with its session and the runner stopped "so nothing runs twice", naming no way out). The guard's in-flight marker names the
  session's process; at a session's end the runner releases a dead session's marker itself ("released in-flight 403 … the task
  retries") and goes on; a live one, or a marker from before this change, is the owner's — the stop names `reef-run.py release
  <task>` (new) and `--detach`, and the desk is told. "No progress" (the same `/clear` wait twice) files a question the screen
  shows and tells the desk, instead of a silent exit 3. `/reef-run autopilot` starts the autopilot from a session. tests/size-budget.json raised: `prose_words` 22,900 → 22,940, `script_lines` 17,476 → 17,541.
- **The `reef` screen on the owner's project** (2026-10-30, his first look after the update: "nothing works, no list, too much
  old runner log"): the lines were cut at a third of the width — curses' counted write measures bytes and the banner and rules
  are three-byte glyphs — so the screen draws by characters; an idle runner's log is a tail of five steps and when the run
  ended, not the screen; and the inbox holds the runner's own waits — a task left in flight by the last run (`reef-run.py
  release <task>`) and a loop that is active with no runner (`reef run`).
- **Autopilot** (2026-10-30, the owner: "I need the runner autopilot to really work on its own — I give it work for the next 5–6
  hours and it finishes bulk work; I don't want to babysit it"). `reef-run.py --autopilot` (`reef autopilot`) is the night's
  machinery as a standing mode: `reef/proxy.md` is the contract, approved once (`Approve proxy by day at <digest16>?`); its
  `Decides:` line may now name `plan`, `question`, `hole` and `triage` beside `process` and `wording`; every decision of a named
  kind goes to Mahmoud — a plan approval through `reef-approval.py --proxy --feature`, now allowed by day while `.reef/run/autopilot`
  marks the run and the contract names `plan` — and a session that still ends on an owner wait is not the end: the next one
  decides it; the same wait twice is the owner's (outside the contract, or a hard limit), with the desk told. The report is
  `.reef/run/autopilot.md`: his plan approvals since the start, his other decisions on record, the waits, the sessions and
  their cost; each decision is undone by deleting its record. `reef autopilot off` stops it. tests/size-budget.json raised: `prose_words` 22,847 → 22,900, `script_lines` 17,390 → 17,476.
- **The `reef` screen, second design** (2026-10-30, the owner's first look: "no reef written word, no proper selector, empty huge
  space then a few sections"): the block-letter banner with the project, the loop, the runner and the base beside it; **the inbox**
  as a list — ↑↓ (or j/k) move, Enter runs the selected item, a digit runs by number — with the chosen item's whole command in a box
  under the list (wrapped, never cut); the runner's steps fill what is left; the doctor's top three warnings; the keys last. The
  screen is a model (`screen_model`) rendered for a width and a height (`render`): never more lines than the terminal, the selection
  scrolled into view, redrawn on resize (a 32-row block sat in a 66-row window). An answer item opens a prompt with the
  recommendation prefilled (Enter keeps it). `screen --once` lists every item with its command, as before. tests/size-budget.json: unchanged (nothing grew).
- **`reef update`'s last line names the marketplace** (2026-10-30, the owner's update: the step's own line said `mahmoudmoe`,
  the done line said `<marketplace>` — a placeholder in a command the owner types). The done line is built from the name on
  disk (`reef-update.marketplace_name`); without one it says the reload alone. tests/size-budget.json: unchanged (nothing grew).
- **A runner's stop on the owner is never silent** (2026-10-30, the owner, twice: the runner stopped on his approval, printed the
  commands to `runner.out` alone, and `watch` sat on a dead tail under "session ended"). The run's last word — the wait block with
  the exact commands, a stop, a park, no progress — goes to the terminal, to `live.log` (so `watch` and `status` show it) and,
  when it waits on the owner, to the desk (macOS's notification center through osascript, notify-send elsewhere; `REEF_NOTIFY=0`
  keeps a suite quiet); the block names `python3 scripts/reef`, the screen with every wait. `watch` follows while a runner runs
  and returns when it ends — 2 when the loop waits on the owner. tests/size-budget.json raised: `script_lines` 17,331 → 17,390.
- **A filed question on an issues queue is answered by its issue** (2026-10-30, the current adoption: the loop filed #90–#93 as
  `reef-question` issues; the runner's wait, the `reef` screen and `reef answer` named the file-queue footnote, which closes no
  issue, so the next session read the same four open questions and ended on the same wait). `reef-queue.py ask` writes the
  issue's number on its line (`- row 7 #90: …`); the one command for a question is `reef_common.answer_command` —
  `reef-queue.py answered <#> '<the recommended answer>'` on issues, the footnote on a file queue, the recommendation filled in
  so no command carries a placeholder; `answered` clears the question's line; `reef answer '#<issue>' "<text>"` picks one of a
  row's several questions. The question line has one parser (`reef_common.questions`), used by the runner, the screen and the
  approval's clearing. tests/size-budget.json raised: `prose_words` 22,820 → 22,847, `script_lines` 17,228 → 17,331.
- **Consolidation step 3 — one definition inside the big four** (docs/design/consolidation.md, 2026-10-30): the loop's
  hold is read by `reef_common.read_hold` and dropped by `drop_hold` — the guard, the runner, the doctor and the loop had
  four readers of `.reef/run/orchestrator.json` and two `HOLD_MINUTES`; the plan check says `in_done`, `is_finished` and
  `is_rollup` once each where eleven lines spelled them three ways; `table_cells` splits a markdown row once, for
  reef-queue.py's three sites and the six other scripts that carried the same line. `write_hold` beside them: the record's three fields have one home. No behaviour the suite
  describes changes; a malformed hold record now reads the same in all four (a test pins it). tests/size-budget.json raised against main: `script_lines` 17,186 → 17,228 (+42) — the one definition
  carries the docstring and the normalisation four copies never had; the plan's §2 says a one-definition step is scored by
  its helper column, not by lines.
- **The plan review has a round cap** (2026-10-30, row 7 on the current adoption: the reviewer and the planner traded blockers
  for five rounds; the hunter's plan pass has `hunter.plan_rounds`, the reviewer had none). `reef-record plan-review` counts the
  rounds in `.reef/review/plan-<slug>.json`; the guard refuses a `plan-reviewer` dispatch after `review.plan_rounds` FAILED
  rounds (default 2: the review, one fix, one re-review; 0 = no cap) and names the owner's line — the open findings become his
  `reef-queue.py ask` questions, his footnote rules, and a PASS is recorded on it. The template and the skill say so. tests/size-budget.json raised: `config_keys` 95 → 96, `prose_words` 22,721 → 22,775, `script_lines` 17,092 → 17,174.
- **The orphan test's fake session survives a runner that dies before its first word** (2026-10-30, CI's macOS leg a
  third time, after #216 and #219): the fake printed its first event before it ignored the dead pipe, so on a slow
  start, with the runner already killed, that print ended it — no handler yet, no breadcrumb. Every print is
  guarded now, the first included; the fake also names any other signal that ends it in `.fake-died`.
- **A line number in a criterion or a decision fails the plan check** (2026-10-30, row 7 on the current adoption: rounds 4 and
  5 of the plan review were one criterion citing `AGENTS.md:74` where the sentence had moved to `:75` — every plan that touches
  a file another row edits paid a round). `reef-plan-check.py` refuses a `path:line` citation inside `## Acceptance Criteria`
  or `## Decision` and says to name the content (a symbol, a sentence, a heading); `## Read first` keeps its ranges — its check
  greps the symbol when lines move. The plan skill and the planner brief say so. The reviews: `## Scope` is covered too, bare `Makefile`/`Dockerfile` and more
  extensions count, the match is bounded, the docstring lists the rule. tests/size-budget.json raised: `prose_words` 22,721 → 22,762, `script_lines` 17,092 → 17,100.
- **Consolidation step 5 — the `reef` screen** (docs/design/consolidation.md, 2026-10-30): `reef` alone on a terminal opens
  a live screen (stdlib `curses`, the menu where the terminal cannot): one status line (the loop, the runner), **the inbox**
  — every wait Reef recorded, numbered, each with the exact command the row machine names (an approval, a filed question,
  a parked loop's restart, an orphaned session's stop, a doctor's fix), the runner's last steps, the doctor's warnings; a
  number runs the item, `r n s d c u` run the verbs, `g` refreshes, `q` quits. `reef screen --once` prints it and exits.
  Two verbs for what the owner types most: `reef approve <row>` (the row's approval at its current digest, from the row
  machine) and `reef answer <row> "<text>"` (the footnote the loop reads; the question line cleared). The screen knows
  nothing the scripts do not: it reads loop.json, questions.md, the handoff's tick, the runner's own view, the doctor's
  lines, and every key runs a command you could type. A doctor's fix is read as the last dash-separated part of its line and
  never shown with a placeholder; the doctor prints the plugin's real path in its two lines that said `<plugin>`.
  The reviews: no shell between a key and a command — every item is an argv, the approval question must match the
  hook's own regex (shared in reef_common with the runner), a row is digits, a doctor fix with prose or shell syntax is not an
  item; the doctor's unlock line is a bare command.
  tests/size-budget.json raised for the screen: `script_lines` 16,945 → 17,077.
- **Consolidation step 2 — the three orphans** (docs/design/consolidation.md, 2026-10-30): `scripts/reef-watch` is gone
  (`reef-run.py status` and `.reef/status.html`, rendered at every tick, replaced it), `scripts/reef-guard-profile.py` is
  gone (its one measurement, `docs/perf/guard-profile-2026-10-16.md`, stays and the hook timeouts still rest on it),
  `scripts/reef-eval` lives at `tests/eval/reef-eval` beside its corpus — a test tool, run by tests only. With their tests;
  the README, the site, the manual and the site plan say so; history (CHANGELOG, docs/perf) keeps its words. The reviews: the
  ledger row claims what the two surfaces show (growth and the journal's rows are `reef-cost.py rows`), the contract test
  reads skills, agents, hooks, commands, templates and scripts too, the plan names the replacement the commit chose. tests/size-budget.json SET to the measurement: `script_lines` 17,501 → 16,945, `prose_words` 22,721 → 22,721.
- **A project's linters are told to leave Reef's scripts alone** (2026-10-29, an adoption: the project's ruff flagged
  1,725 style errors in the copied `scripts/reef-*.py` and its CI went red; mypy followed). The scripts are rendered by
  reef-init and replaced on every upgrade, so their style is Reef's own. `reef_common.lint_gaps` reads `pyproject.toml`
  (`[tool.ruff]`, `[tool.mypy]`), `ruff.toml` and `.ruff.toml`; `reef-init` prints `LINT: <file> <section> scans Reef's
  scripts — add <the line>` when nothing excludes them (`scripts/reef-*` alone no longer does: `scripts/reef_common.py`),
  and `reef-doctor` warns with the same line, OK when the project excludes them. No file of the project's is edited. The
  reviews: the ruff line is `extend-exclude` (`exclude` would replace ruff's defaults), a key the file has is extended,
  never duplicated; only the values of exclude keys are read, continuation lines included; a non-utf-8 config is no crash. tests/size-budget.json raised: `script_lines` 17,501 → 17,555.
- **`reef update`'s two owner lines carry real values** (2026-10-29, the owner's update after the night's PRs: the last line
  read `/plugin marketplace update <marketplace>` — a placeholder in a command the owner types — and when his push was
  rejected because the loop had pushed meanwhile, the hint said `git push`, which fails the same way). The marketplace's
  name is read from `~/.claude/plugins` (the entry whose location is the plugin clone, else `reef@<name>` among the
  installed plugins; none → `/reload-plugins` alone, said so); a rejected push prints
  `git pull --rebase --autostash origin <branch> && git push` with the branch filled in — autostash because the tick's
  `HANDOFF.md` rendering is always unstaged (an autostash that does not re-apply stays in `git stash list`). The reviews:
  the hint only on a non-fast-forward rejection, the branch quoted for the shell (a ref admits `;`), a detached checkout
  told to check out its branch; a marketplace key outside `[A-Za-z0-9._-]` is never rendered; a plugins file of another
  shape is no crash. tests/size-budget.json raised: `script_lines` 17,501 → 17,540.
- **The orphan test's fake session says why it ended** (2026-10-30, CI's macOS leg still red on the test after #216: the fake
  died before the assertion and nobody could see why — its output went to the dead runner's pipe). The fake ignores SIGHUP
  and SIGPIPE as a session should, treats any OSError on its one write as the pipe being gone, and on any other end writes
  `.fake-died` with the traceback, which the assertion prints; a kill by signal leaves no crumb and the message says so.
- **`reef-run.py` refuses an unknown argument** (2026-10-29, the owner: `python3 scripts/reef-run.py --status`, a typo for the
  verb `status`, fell through to a run and started a loop session on the project without a word). Every argument is checked
  first: a verb (`watch`, `status`, `stop`, `probe`, `contract`, first position only), a flag with its value (`--repo`,
  `--permission-mode`, `--host`, `--max-iterations`, `--row`, `--from`) or a bare flag (`--night`, `--detach`, `--day`); anything
  else prints the usage block and exits 1 (refused; 2 is "waiting on the owner", which the factory reads as built — the
  review) before anything runs — a flag without its value, or a `--max-iterations` that is not a count, too. tests/size-budget.json raised: `script_lines` 17,401 → 17,429.
- **The orphan test's fake session survives its runner's death** (2026-10-29, CI's macOS leg on PR 215: the fake wrote its
  one event into the dead runner's pipe and died on it, so the "orphan" the test asserts was gone — the real `claude`
  kept running its gate). The fake swallows the broken pipe like the real one; the test waits past that step first.
- **Consolidation step 1 — one shared module** (docs/design/consolidation.md, 2026-10-29): `scripts/reef_common.py` holds the
  one body of `main_checkout`, `run`, `git`, `config`/`read_config`, `repo_root`, `process_alive` and `read`; every script
  imports it beside a `sys.path.insert` of its own folder and loses its copy, keeping at most a one-shape adapter where its
  callers expect another return. No assertion changed. `reef-init` copies the module, `reef-update` stages it, the guard
  protects it like `scripts/reef-*`, the doctor compares it, `reef --all` lists commands only. tests/size-budget.json SET to the measurement: `script_lines` 17,587 → 17,471 `prose_words` 22,721 → 22,721 (the ceiling only comes down).
- **A dead runner leaves no orphan** (2026-10-29, the owner: the runner died when its stdout pipe closed, its `claude -p
  /reef-loop` session lived on running gates at full CPU with no window anywhere, and `reef-run.py stop` said "no runner
  is running" — `pkill` was the only way). The runner records the session it is in (`.reef/run/session.pid`: pid and
  start) and removes it when the session ends; `status` says `runner gone, session <pid> still running since <time>`;
  `stop` ends that session (TERM, KILL after 10 s), clears the lock and the record, and stops the loop with the reason
  (`reef-loop.py stop "<reason>"`, which now takes one) so `.reef/loop.json` agrees, exit 0. The runner's own exit path
  ends its session — normal, an exception, TERM, INT or a closed pipe (session()'s `finally`, TERM/INT handlers that
  unwind, an atexit). The reviews: the session runs in its own process group and is ended as a group (the gates it
  spawned are grandchildren, which outlive a kill of `claude` alone); `stop` kills only the process the runner recorded
  (session.pid carries the ps start time and must still match — a reused pid or a record an agent wrote is refused);
  the record's text is validated before it is printed; no SIGPIPE handler (a broken pipe unwinds as BrokenPipeError). tests/size-budget.json raised: `script_lines` 17,419 → 17,511.
- **An implementer never edits a task file** (2026-10-29, row 9 on the current adoption: the implementer refreshed the
  line numbers in its task's `## Read first` and the next task's, every close carried the edit, the plan's digest moved
  and the owner re-approved an unchanged plan three times). The guard refuses an implementer's Edit, Write or MultiEdit
  to a task file under `paths.features` or the legacy `tasks/` (the mechanic's close and the orchestrator's amendments
  are not implementers); the brief says a moved line goes in the hand-back, never into the task. The reviews: the rule
  covers the whole feature folder (the digest does: SPEC, ADRs, every task), the Bash route too (`sed -i`, a redirect,
  `tee`, `git mv|rm`), anchored to the project's roots from any worktree; a ledger row names it (tripwire). tests/size-budget.json raised: `prose_words` 22,672 → 22,710, `script_lines` 17,401 → 17,419.
- **A task's close moves no plan digest** (2026-10-29, row 9 on the current adoption: a planner's task file has no `## Log`,
  so `reef-merge-close` wrote the journal block at the end of the body, where the digest hashed it — three closes in a
  row, three re-approvals of a plan nobody had changed, each a stop for the owner). The digest strips the
  `<!-- journal -->…<!-- /journal -->` block like it strips the Log and the status keys; a task without that block
  hashes exactly as before, so every current approval stands. The reviews: the close appends after the body's own last
  bytes and the digest strips exactly that, at the end of the file only; a journal block holding anything but table rows,
  or sitting anywhere else, fails the plan check (the criteria readers would see it; the digest must too). tests/size-budget.json raised: `script_lines` 17,387 → 17,392.
- **An approval hold in the tick names the exact owner command** (2026-10-29, row 9 on the current adoption: the tick said
  `awaiting: <row> (re-approval (plan edited after approval))` and `next:` echoed it, so the owner's own loop session wrote
  the wait as "run reef-approval.py --owner for <row> at <digest> in a terminal"). The hold now ends with
  `python3 scripts/reef-approval.py --owner "Approve plan <slug> at <digest16>?"`, the digest read from the same check,
  for a missing and for a stale approval alike. tests/size-budget.json raised: `script_lines` 17,387 → 17,401.
- **The slot lock is re-entrant** (2026-10-28, row 6 on the current adoption: `reef-gate.sh` holds `gates.resources`
  for its whole run, and the task skill and the mechanic told agents to put heavy suites through `reef-graph.py lock
  heavy` as well — the inner lock waited the whole timeout for its own holder, then exited 75, and the session read it
  as a deadlock). A slot a parent of the process already holds (`REEF_SLOTS_HELD`, keyed like the slot files) is not
  taken twice: the command runs inside it; another resource still takes its own slot. The token names its holder's pid and
  counts only while that process lives (the reviews: inherited alone it outlived the gate, and a server or a session
  started under it would have skipped every later lock); a resource name on the command line is `[A-Za-z0-9._-]+`, as
  the gate already filters it. The two prose lines say the gate
  holds its resources itself and the lock is for a heavy command outside the gate. tests/size-budget.json raised: `prose_words` 22,646 → 22,672, `script_lines` 17,354 → 17,365.
- **The loop unparks itself when the tick changes; the park names its command** (2026-10-28, row 46 on the current
  adoption: the loop parked for "no progress" while a fix round was being built in a worktree the tick did not see,
  then told the owner only he could unpark it and named `unlock`, the session-hold command). A tick that differs
  from the one that parked is progress: the park clears on its own; while parked, the line says `reef-loop.py start`.
  tests/size-budget.json raised: `script_lines` 17,347 → 17,354.
- **A recorded approval clears its own question** (2026-10-28, the owner's first round alone: the loop filed "re-approve
  row 46's plan at <digest>", the owner approved in his terminal, and three runner sessions re-read the filed question,
  believed it, and recorded the same wait). `reef-approval.py` removes the row's approval questions from
  `.reef/questions.md` and closes their `reef-question` issue when it writes the record; the runner's sessions are told
  a filed question is answered when the row's state moved past it. tests/size-budget.json raised: `script_lines` 17,307 → 17,347.
- **`/reef-run` starts the runner on a recorded wait; no placeholder reaches the owner** (2026-10-28, the owner's first
  round alone: the skill read the loop's recorded wait, decided the runner would stop at once, refused to start it, and
  told the owner to approve `<slug>`). A recorded wait is the runner's to clear — its first session asks the row machine;
  only a live runner stops the step — and a line the owner will type carries real values from `reef-row.py state`.
  tests/size-budget.json raised: `prose_words` 22,576 → 22,646.
- **The runner's wait asks the row machine for its command; `reef update` pushes** (2026-10-28, the owner's first round
  alone). The loop wrote its wait as "re-approve row 46's plan at <digest>", not the exact question, and the runner
  offered a footnote command for an approval. For every row the wait or the questions file names, the runner now reads
  `reef-row.py state <row> --json` and prints the command that state carries (the approval line at the gate), a
  footnote only when the row has none. `reef update` pushes the commit it makes, or says to push. tests/size-budget.json
  raised: `script_lines` 17,292 → 17,307.
- **A feature's digest covers the ADRs it owns or cites, not every decision in the project** (2026-10-28, the current
  adoption, two rows in flight: row 3's close amended two ADRs on the base; merging the base into row 46's branch moved
  row 46's digest and voided its approval with nothing of its plan changed — the owner re-approved by hand). The
  approval binds to the plan: its task files, its folder, its drafts in the ADR home (`draft-<row>-…`, or the slug in
  the name) and the numbered ADRs its SPEC, specs and tasks name; an unrelated ADR's edit stales nothing. The ADR
  checks themselves (Status, placeholders) still run over every ADR. The review folded: a draft nobody owns stays in
  every digest (never outside all of them), a draft is owned by its whole name (`draft-<slug>…`, `draft-<row>-…`), and
  citations are read from the plan text only — a Log line binds nothing. tests/size-budget.json raised: `script_lines` 17,239 → 17,292.
- **A normal round: the runner the owner starts is the orchestrator, every stop names its command, `reef` is the one entry
  point** (2026-10-28, the owner after the first night: "so many locks and guardrails … stopping me from normal rounds" — seven
  stops that day, each a message without the one command; three night sessions burned on a hold a dead desktop session
  left). `reef-run.py` takes a loop hold another session left and says so; two sessions ending on the same wait stop it
  (no progress) instead of a tenth session; its owner waits print the terminal command for each part — `reef-approval.py
  --owner "<question>"` for an approval, a `reef-queue.py footnote … --row <id>` for a filed question — and a missing
  night approval prints `contract` + the approval line with the digest. `reef-row.py`: the approval state names the
  terminal command; a review FAIL at the head names the ROLLUP (never a new plan). `reef-doctor.py` checks the hold
  (dead → `reef-loop.py unlock`), the runner's probe, the setup proof and whether the plugin is ENABLED in Claude Code.
  New `scripts/reef` (copied by `reef-init`, staged by `reef-update`): the banner, one status line, the owner's verbs with
  a line each (status, doctor, run, night, watch, stop, setup, update, factory, cost); `reef update` = plugin pull +
  project update commit + the setup proof when the digest changed; `--all` lists every script's purpose. Bugs the
  morning report exposed: `reef-cost.py rows --since <date>` read the date at the current time of day (git fills it) and
  missed the morning's merge — a bare date is UTC midnight; the report lists squash merges (`(#n)` subjects) under
  merges with their undo; `reef-setup.py` quotes a runner's FAIL marker before a sentence with the word "failed". A
  contract test forbids "interactive session" anywhere in Reef. The reviews folded: `scripts/reef` is a guard file (the
  own-files rule required the dash) and a sub-agent never runs the runner's writing verbs or `reef-loop.py unlock`; the
  runner takes over only a DEAD or stale hold (idle past the guard's 30 min) and otherwise refuses naming `unlock` — the
  check runs before detaching so the caller sees it; no progress is the same STATE twice (the base's head, the handoff,
  the questions, the wait), not the same wait text (the loop's merge waves end on the bare `/clear requested`); `reef`'s
  verbs are one shape and resolve a script the project lacks (`reef-doctor.py`) from the plugin clone, found by the
  marketplace's `installLocation` and Reef's plugin name; the night hint prints the digest only when both files exist.
  tests/size-budget.json raised: `prose_words` 22,459 → 22,576, `script_lines` 17,053 → 17,239.
- **0.7.3 released** (2026-10-28): plugin.json, the marketplace, reef-init's version, the README badge and status, the site
  and the manual read 0.7.3; migrations/0.7.2-to-0.7.3.py is a no-change step so .reef/version walks with no gap.

## 0.7.3 — Workflow v3: risk decides the path, evidence once per commit, one reviewer, the loop merges, the factory on Actions
- **`reef-run.py contract --from` the installed contract no longer crashes** (2026-10-28, the current adoption:
  re-running the contract against `.reef/night/contract.md` itself raised `shutil.SameFileError` as a traceback).
  The same file is left in place; any other copy failure is one `reef-run:` line. `script_lines` 17,048 → 17,053.
- **The worktree setup is proven once per change, never by a row's red** (2026-10-28, the current adoption). A fresh row
  worktree had install, generate and typegen but no built app; 60 tests went red for reasons unrelated to the row, the
  orchestrator guessed a build and the full suite ran twice per row — the design's phase 0 had left "a complete
  worktree.setup" to the owner's hand. New `scripts/reef-setup.py`: `prove` makes a scratch worktree of the base, runs
  `worktree.setup`, then `gates.full` ONCE as a plain command (no evidence, no snapshot cache: a tree lacking its setup is no
  result about the base), records `.reef/ci-local/setup-<digest16>.json` and removes the worktree; `state` reads the record
  for the digest of the setup command, the full gate and every lockfile — proven (0), unproven (3), INCOMPLETE (1) with the
  failing lines. `reef-row.py next` names `prove` before a build and waits on the owner while INCOMPLETE; `reef-graph.py
  worktree` refuses a task worktree on the same terms; `/reef-plan` starts the setup only on a proven state. `reef-init`
  copies the script and derives `worktree.setup` from the stack profile's new `setup` entries (`scripts/reef-stacks.json`:
  for Next, the route types and, when a build script exists, the built app the tests read), each only when its
  dependency is present. The reviews folded: `worktree` joins the guard's protected config keys (the setup is a command
  the proof runs unseen by the hook) and a read-only judge never runs `prove`/`apply`; the proof is named before
  `/reef-plan` makes the row's worktree, not only before the build; `apply` runs the proven setup in a worktree once per
  digest (marker `.reef/ci-local/setup.digest`), so a worktree set up under an older digest is re-set, and
  `reef-graph.py worktree` sets a new task worktree up through it; the digest follows the manifests too; a `gates.full`
  that names `reef-gate.sh` is refused (it would write the base's evidence); the INCOMPLETE line names the log; older
  digests' records are pruned; the Next entry is the build alone (`next typegen` is version-bound and `next build`
  writes the types). tests/size-budget.json raised: `prose_words` 21,799 → 21,825, `script_lines` 16,754 → 17,048.
- **`/reef-factory`: the factory as one command; a subscriber token or an API key; the factory on the README, the site
  and the manual** (2026-10-28, the owner: "can tickets fire an agent on GitHub, and is there a shortcut inside Reef?"). The
  factory (phase 7) had no skill and its four setup steps lived only in a workflow header. New `skills/reef-factory/SKILL.md`:
  empty → status (the accepted workflow, the one secret, branch protection, the labels, the last runs, each with its fix);
  a row id → `reef-queue.py row-issue`, `gh issue edit --add-label reef-ready`, the run that starts; `status|log <id>` → the
  row's label, the run's log, and the approval comment to write when `reef-waiting-owner`. The workflow's model step passes
  `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token`, a Claude subscription) as well as `ANTHROPIC_API_KEY`; the header names the
  choice. The README gains *The factory on GitHub Actions* and the row; the site's keeping-it-running panel and the Arabic
  manual's section 5 and command table say the same. tests/size-budget.json raised: `prose_words` 21,799 → 22,433.
- **A finished task is not re-judged by today's authoring rules; `--feature` scopes them** (2026-10-28, the current
  adoption, rows 3 and 46). `reef-plan-check.py` ran the v3 proof rule and the read-first checks on tasks under
  `tasks/done/` — shipped, judged and merged under the rules of their time — and no plan in the project could be
  approved (nine FAILs on the base, all on closed rows; `--feature` scoped only the stamp). A finished task (under
  `tasks/done/` with `status: done`) keeps the structural checks only — schema, id, folder and status, blocked-by,
  duplicates, section order, the test-name ledger — and `--feature <slug>` scopes the authoring rules (proof shape,
  read first, word and criteria caps, keys) to that feature's tasks; another feature's structural defect still
  fails (the graph is one). The reviews folded: the stamp records which tasks were finished at review time and a
  finished task open again under `tasks/` is STALE until a re-review judges it by today's rules (the digest keys by
  basename and strips status, so a task written under `done/` and moved back would have kept its approval); a
  `--feature` run writes only that feature's digest, the others carry over; `--summary` counts finished tasks apart;
  HUMAN AC on a finished mech task is not judged. tests/size-budget.json raised: `prose_words` 21,773 → 21,799, `script_lines` 16,713 → 16,754.
- **The README, the site and the Arabic manual say today's Reef** (workflow v3 phases 1–7; 2026-10-28). The three surfaces
  still described the v2 pipeline — every task verified by a fresh judge on every row, the hunter and the plan reviewer on
  every plan, the owner merging the feature PR, nine roles. Now each says, in its own register: risk decides the path (the
  fast path for `light` and `full`, the critical path for `design` touching auth, pii, money or a migration, and `critical`);
  one worktree per row and at most `loop.rows_in_flight` rows between plan and close; proofs are named tests
  (`converge.test_cmd`); the suite runs once per commit and every judge reads that result (`.reef/evidence/<snapshot>.json`
  or the commit's check-runs, `reef-evidence.py`); one reviewer per row (`reef:acceptance`); the loop merges a feature on green
  evidence of the merged commit; the row is a state machine on disk (`reef-row.py next`) and every wait renders the handoff;
  the batch's numbers (`reef-cost.py rows`); the runner files questions instead of asking (`.reef/questions.md`, issues labelled
  `reef-question`, `--row`); the proxy by day (`contract --day`, `Approve proxy by day at <digest16>?`); the offered factory
  (`reef-factory.yml`, `reef-ready`, the state labels). The README's roles table gains the acceptance reviewer and narrows the
  verifier, the hunter and the plan reviewer to the critical path; its ledger gains the v3 rows (evidence once, the loop's
  merge, the row's state from disk, the proxy's day footnote, the factory's checks); its layout names `.reef/evidence/`,
  `reef/proxy.md`, the offered workflow and the new scripts; "Status" tells v3's story. `tests/test_contracts.py::WorkflowV3Docs`
  reads the three surfaces. tests/size-budget.json: unchanged (nothing grew).
- **Rows build without the owner's machine: the factory on GitHub Actions** (workflow v3, phase 7; 2026-10-26). `reef-init`
  OFFERS `.github/workflows/reef-factory.yml` — rendered under the proposals dir, never written unasked (minutes, the model
  key as the secret `ANTHROPIC_API_KEY`, the six-hour limit are the owner's call; `reef-init --accept` places it, then it is
  refreshed like every Reef file). A row's issue labelled `reef-ready` starts a job that installs Claude Code and the Reef
  plugin at the commit the project's scripts came from, proves the guard reaches a headless session there (`reef-run.py
  probe`, fail closed), records the owner's plan approval from the row's issue (`reef-approval.py --from-issue <row>`: a
  comment that is exactly `Approve plan <slug> at <digest16>?`, by a collaborator with admin permission, at the current
  digest), runs `reef-run.py --row <row>` (every session's prompt `/reef-loop <row>`; `REEF_CLAUDE_ARGS` loads the plugin
  with `--plugin-dir`), and writes the row's state back as one label (`reef-queue.py label-state <row>`: `reef-waiting-owner`,
  `reef-building`, `reef-review`; `reef-ready` is consumed; `reef-queue.py issue-row <#n>` names the row); the nightly schedule
  runs every ready row; the job's log and its `reef-run` artifact are the observability. tests/size-budget.json raised: The reviews folded: the job runs ONE command, `scripts/reef-factory.py row` — the labeler and the issue's author must be
  admins, the base branch protected, the row's branch resumed from the forge and pushed back, the approval read only from an
  UNEDITED admin comment (newest admin comment decides), `--paginate --slurp`; no schedule until it drains `reef-ready` rows.
  `prose_words` 21,573 → 21,773, `script_lines` 16,328 → 16,713.
- **The proxy decides process and wording by day, inside a contract the owner approves once; the owner's questions per
  batch are counted** (workflow v3, phase 6; 2026-10-26). `python3 scripts/reef-run.py contract --day` seeds `reef/proxy.md`
  (its `Decides:` line: `process`, `wording`; its `Never:` line: product, money, data, look, security, the release, a plan
  approval) and prints `Approve proxy by day at <digest16>?` — one AskUserQuestion, recorded as `.reef/approvals/day.json`;
  an edit to `reef/proxy.md` or `reef/owner.md` voids it. In the day loop a question of those kinds goes to `reef:mahmoud`
  first; `python3 scripts/reef-approval.py --proxy --day --kind <kind> --row <id> --report .reef/ci-local/report-mahmoud-day-<row>.md`
  writes his decision as the footnote `Mahmoud (proxy, day <date>, <kind>): <answer> — <why>` and logs it in
  `.reef/approvals/day-decisions.jsonl`; a `WAIT` is the owner's (`reef-queue.py ask`); the guard refuses that label typed into
  `reef-queue.py footnote`. `reef-cost.py rows` counts the owner's footnotes and the proxy's day decisions per batch; the
  morning report shows both beside the last night's. tests/size-budget.json raised: `prose_words` 21,373 → 21,573, `script_lines` 16,094 → 16,328.
- **One Workflow per row: the orchestrator makes three calls per row, not three per task plus the review's own**
  (workflow v3, phase 5b; 2026-10-26). `python3 scripts/reef-graph-run.py row <row>` writes `.reef/graph/row-<slug>-<hash>.js`:
  the row's open tasks in id order, each implemented, gated, judged on the critical path and closed in place by the mechanic
  (`reef-merge-close`) before the next starts; then the full gate and `reef-converge` once, `reef-merge-base` + push + PR, the
  critical path's guard pass and security, and the one reviewer (`reef:acceptance`). `settle` checks every close on disk,
  re-reads the evidence, copies and records the reports (`reef-record`, `reef-adversarial --feature … guard`) and prints
  `ROW <id> READY TO MERGE … gh pr merge <n> --squash --delete-branch` — the one bare command the orchestrator runs, where the
  guard checks the record, the base tip and the evidence (a script's merge would pass no hook) — or `ROW <id> WAITS <state>`.
  Refused at the owner's steps (plan, approval), the scripts' (merge, close), with a task in flight, or while graph mode is
  off. `/reef-graph` "The row" and `/reef-loop` step 2 send a row in build to it. tests/size-budget.json raised: `prose_words` 21,143 → 21,373, `script_lines` 15,777 → 16,094.
- **Scripts orchestrate: the row is a state machine on disk, every wait renders the handoff, nobody writes one by hand**
  (workflow v3, phase 5; 2026-10-26). The first adoption's orchestrator held the row's state in its context — 105k of
  150k after one review, a `/clear` and a hand-written handoff every few hours, a whole session with no product line.
  New `scripts/reef-row.py state|next <row>` reads a row's state from disk and the forge — plan → approval → build →
  evidence → review → merge → close → closed — and prints the ONE next command (the approval digest to ask for, the open
  tasks, the gate to run, the review, the merge, the close); `/reef-loop` dispatches the agent the step names and never
  decides the step. `reef-loop.py wait` renders `HANDOFF.md` from measured state before recording the wait, and the
  guard refuses a hand-written `HANDOFF.md` from the main session and every agent (Bash, Write, Edit; the plugin's
  template is not a project's handoff); its ceiling message no longer suggests writing one by hand. `reef-init` copies
  the row script. The design spike for the rest of phase 5 — a Workflow that drives a row's states without the chat
  orchestrator — is in the PR body, not built. A fresh review of the change, folded in: a row is read from the worktree on
  ITS branch, else the main checkout — never from another row's worktree, which holds the folder too once the base was
  merged in; a squash-merged row reads as merged offline through the PR number in its review record against the base's
  subjects; the handoff rule sees a copy INTO a directory and `$PWD`, and no longer refuses a scratch HANDOFF.md after a
  `cd`; `reef-loop.py wait` says when the handoff script is missing or failed and still records the wait.
  tests/size-budget.json: `script_lines` 15,499 → 15,777; `prose_words` lowered 21,156 → 21,143 (the loop skill lost five
  asides and gained the row script).
- **Finish before starting, a merge queue of two** (workflow v3, phase 4; 2026-10-26). The first adoption had rows waiting
  on the owner for an integration merge, and a batch that started every ready row at once. The tick now plans a new row
  only while fewer than `loop.rows_in_flight` (new key, default 2; 0 = no cap) rows are between plan and close — building,
  or done and awaiting close — and names the held rows on its `rows to plan` line. Under `merge.by: loop` the guard refuses
  `gh pr merge` unless the PR head CONTAINS the base's current tip (`scripts/reef-merge-base` in the feature worktree, then a
  push) and the merged commit has green evidence (`reef-evidence.py`: CI's check-runs, or the gate's record) — the gate runs
  on the merged result, never on the branch as written; a clean base merge still carries the GREEN record over. `merge.by`
  defaults to `loop` when `ci.feature_gate` is `ci` and `branches.base` differs from `branches.release` (CI gates every
  feature PR, so the loop may merge), else `human`; the template no longer pins `human` (`reef-init` already wrote `loop` on
  two-branch projects), and `reef-plan-check.py` says which default applied. One contract test changed on purpose
  (`tests/test_contracts.py`: the template's merge default). A security review of the change: the keys the merge gate
  reads (`merge`, `ci`, `branches`) and the loop's cap (`loop`) join the guard's protected config keys — an agent could
  have edited them and disarmed the gate it is subject to; under `ci.feature_gate: ci` the loop merge waits for CI's result
  and never takes the gate's local record (the author's machine); `gh pr merge -R` names another repository and is refused;
  `reef-plan-check.py` validates `loop.rows_in_flight` and warns when an absent `merge.by` resolves to `loop`. CI then caught a fixture whose raw `git merge` ran
  without an identity (none on the runner): no merge commit, so the new check refused a head that did not contain the base — the
  fixture passes the identity now.
  tests/size-budget.json: `script_lines` 15,448 → 15,499; `prose_words` lowered 21,170 → 21,156; `config_keys` unchanged
  (one key in, one out).
- **The fast path builds in one worktree per row, in order, with no judge per task** (workflow v3, phase 3b; 2026-10-26).
  The first adoption paid a worktree per task (`npm ci`, generate, typegen, build each time, or about 60 tests red) and a
  verifier per task on rows whose risk the tier had called ordinary. `scripts/reef-attempt` now prints the row's `path:`;
  on the fast path (a 0.6 feature folder, every task light or full, no risk touch) `reef-graph.py worktree` answers the
  FEATURE worktree instead of making one, the ready set lets a fast row's tasks run one at a time in id order, and
  `reef-attempt` prints `verifier: none` for a judged task (graph mode reads it the same). `scripts/reef-merge-close`
  closes a fast-path task in place: the work committed on the feature branch with the `Closes-task:` trailer through the
  commit gate, `status: done`, the file moved — no task branch, no merge. The full gate runs once after the last task and
  writes the evidence the one reviewer reads. The critical path keeps a worktree and a verifier per task, and its close
  now REQUIRES the verifier's PASS report at `.reef/ci-local/report-<id>.md` — the skill asked for it before, nothing
  checked. The flat `tasks/` layout (pre-0.6) keeps a worktree per task. A fresh review of the change found the fast close never
  running in the real layout — the `worktree:` key names the FEATURE worktree there, and read as a task worktree it sent the
  close down the merge flow, which removes the worktree and its branch; the close is now decided by the path alone, checks
  its destination before touching anything and restores on a refused `git mv`; a fast row offers ONE task to the ready set;
  a PASS report older than the last hand-back is stale; a feature folder is one under `paths.features`. tests/size-budget.json:
  `script_lines` 15,238 → 15,448; `prose_words` lowered 21,190 → 21,170 (the skill gained the fast path and lost five
  history asides).
- **One reviewer per row: the spec, the diff, and every criterion against its named test in the evidence** (workflow v3,
  phase 3c; 2026-10-25). The first adoption paid three judges on one row with no blocker — acceptance 47k tokens,
  security 54k, a third — each looking at the same code from an overlapping angle; the 0.7 diff review had already been
  switched off for the same reason. `reef:acceptance` is now the row's ONE reviewer: the feature against its `SPEC.md`, the
  diff against the base (dead code, duplication, missing coverage, doc gaps — BLOCKER only by the four kinds), and every
  `## Proof` row against the evidence (`reef-evidence.py`, read, never re-run: the named test exists and tests its
  criterion). The separate diff review and `review.diff_review` are gone; `review.split_lines` (4000) is the one
  reviewer's split-by-task threshold. The hunter's guard pass and `reef:security` run once per feature on the critical
  path (`reef-tier.py path`: a design/critical task, or a risk touch) — the set `hunter.guard_pass: feature` already
  named, now said by the path — the record stays per design/critical task, which a risk touch forces; the fast path's net is
  the one reviewer, CI and the release pass. A fresh review of the change: the reviewer is told the PR head, the base branch
  and what red or pending evidence means (red: report it, never re-run; pending: the verdict waits); the diff checklist lives
  in the agent file only; the slash command's description and the Arabic manual's config row no longer name the removed
  step. tests/size-budget.json: `config_keys` lowered 96 → 95 (`review.diff_review` gone), `prose_words` lowered 21,210 →
  21,190 (a step, a key and three history sentences removed).
- **The tier names the path, and on the fast path the deterministic check is the plan review** (workflow v3, phase 3a;
  2026-10-25). The first adoption ran the plan-reviewer agent on every row heavier than light — one more judge, about 50k
  tokens and minutes of wall-clock, on rows whose risk the tier had already called ordinary. `scripts/reef-tier.py path
  <task files>` prints the path: `fast` when every task is light or full and none touches auth, pii, money or migration;
  `critical` otherwise. `reef-plan-check.py --verify-stamp` says `review: not required` on the fast path and requires the
  plan-reviewer's record only on the critical path; `--needs-agent` exits 3 on the fast path; the guard refuses a
  plan-reviewer dispatch for a fast-path feature. The hunter's plan pass was already gated to critical tasks
  (`hunter.plan_pass`), and its cap (`hunter.plan_rounds` 2) already means one pass and one re-check only after a
  finding — both unchanged. `/reef-plan` names the path before the review and asks in the grill only what neither the
  codebase nor the spec answers. One test changed on purpose: a full-tier feature with no risk touch no longer needs the
  plan-reviewer agent (`tests/test_tiers_lock.py`), and two in `tests/test_plan_check.py` that pinned the model line on a
  light-only plan. A fresh review of the change found three readers of the same plan that could differ on `touches: auth`
  written without brackets — the check ignored it, the guard read it as a risk, `reef-tier.py` read it as none; now the
  check fails a bracketless `touches:`, and the path has ONE rule, `reef-plan-check.py`'s `feature_path`, called by
  `reef-tier.py path` and the guard. tests/size-budget.json: `script_lines` 15,146 → 15,238; `prose_words` lowered
  21,222 → 21,210 (the skill says less).
- **Scripts read the evidence too: converge, the GREEN record and the plan check** (workflow v3, phase 2b; 2026-10-25).
  The first adoption's two Proof rows were each a full build and vitest run as shell, racing the gate for the CPU (a
  false `contradicts`), and the orchestrator recorded GREEN on a head whose suite nobody had seen. `scripts/reef-converge`
  now reads `.reef/evidence/<snapshot>.json` for a whole-suite proof and runs the gate once only when there is none; a named
  test still runs by name through `converge.test_cmd`; every command and named test runs holding `gates.resources`
  (`reef-graph.py lock`), its wait counted against `gates.timeout_s`. `scripts/reef-record <feature> GREEN` refuses without
  green evidence for the PR head — CI's check-runs when the project runs CI on feature PRs (red: refused; still running:
  "record when it is done"), else the gate's record for the commit's tree — and the record carries the evidence's source; a
  FAIL needs none. `scripts/reef-plan-check.py` fails an untagged shell proof over 120 characters: a proof is a test the
  project's runner runs by name, or a script named by its path; `[mechanic]` only for a proof that must write files. A fresh
  review of the change found, fixed with red tests: a `gates.resources` slot held past `gates.timeout_s` read as a red test
  (now `BUSY`, exit 3, nothing written); converge's own evidence reader trusted a file by its name (now the one reader,
  `reef-evidence.py`, which checks the record's snapshot and head); CI's green stood in for a dirty tree at HEAD (now a dirty
  HEAD skips CI and says so), a head not fetched locally never reached the forge (now asked), and the plan check measured a
  proof only up to its first pipe (now the whole row). CI then showed one more: importing `reef-evidence.py` wrote
  `scripts/__pycache__/` into the tree whose snapshot it was about to read (bytecode is off on the author's machine, on on
  the runner) — the snapshot now leaves Reef's own byte-code out, and the loaders write none. tests/size-budget.json raised:
  `script_lines` 15,043 → 15,146.
- **Evidence once per tree: the full gate writes it, the guard protects it, judges read it** (workflow v3, phase 2a;
  2026-10-25). The first adoption ran the full suite three times on one commit — the gate, then two proofs, then the
  verifier "once and fresh" by the 0.7.1 rule, which existed because a cached green could have been planted by the
  implementer. `scripts/reef-gate.sh full` now writes `.reef/evidence/<snapshot>.json` in the MAIN checkout on every real
  run (exit, the suite's counts, its last lines, head, branch, command, seconds, time; a worktree's run lands in the main
  checkout, the same tree the same file), and the guard denies every other writer — Bash, Write, Edit, a judge, the main
  session — as it does for `.reef/review/`: a hand-written evidence file would be a suite run that never happened. New
  `scripts/reef-evidence.py [<commit>]` READS the one result and never makes it: with `ci.feature_gate: ci` and gh reaching
  the forge, the commit's check-runs (a machine the author cannot touch); else the gate's record, found by this checkout's
  live snapshot or by the snapshot a clean checkout at that commit has; exit 0 green, 1 red, 3 pending, 2 none. Its one line
  carries `exit 0` or `exit 1` and stands as a report's `GATE:` line. `agents/verifier.md` and `skills/reef-verify/SKILL.md`
  read the evidence and run the gate only when there is none — the 0.7.1 "once and fresh" rule is retired, because the
  evidence is now written only by the gate or by CI, under the guard. `reef-init` ignores `.reef/evidence/`. A security review
  of the change found, and this entry fixes with red tests: a dirty tree inherited HEAD's record (now: the live snapshot only, and
  a record counts only when its own `snapshot` and `head` say so); a skipped or neutral CI check read as green (now: not a suite
  result — `ci.check_name`, the required check, alone decides when the commit has it, else every check must be green); and the guard missed
  `.reef/Evidence/` on a case-insensitive disk, `dd of=`, a records folder copied, synced or unpacked into `.reef/`, and the
  deletes that take it along (`rm -rf .reef`, `find -delete`, `git clean`). An interpreter writing the path from inside stays
  the guard's known tripwire gap (its header says so). tests/size-budget.json: `script_lines` 14,809 → 15,043;
  `prose_words` lowered 21,227 → 21,222 (the verifier and reef-verify say less).
- **The pipeline is measured per merged row, and the morning report shows it beside the last batch** (workflow v3, phase 1;
  2026-10-25). The first adoption's field review counted by hand — the full suite three times on one commit, about 195k judge
  tokens on a row with no blocker, a five-line fix behind four steps — and nothing in Reef could say whether the next change
  made it better. `scripts/reef-gate.sh` now appends one line per REAL run to the main checkout's `.reef/ci-local/runs.jsonl`
  (at, mode, snapshot, head, branch, exit, seconds; a cached answer is not a run; a task worktree's run lands in the main
  checkout because the worktree is gone at the merge). `scripts/reef-cost.py rows [--since ISO] [--format text|md|json]` reads
  the pipeline per row merged into `branches.base`: lead time in three spans (the plan's first commit → the approval record →
  the merge; the forge's PR through `gh` when it reaches it, since a squash merge erases the branch, else git), tokens from
  `.reef/cost/features.json`, full-suite runs from the run log, rollups and reverts; per batch the process-to-product commit
  ratio (a commit is process when every path it touches is Reef's own: `.reef/`, `reef/`, `scripts/reef-*`, `.githooks/`,
  `.claude/`, the instruction files, the queue and journal, whatever `paths.*` names) and the security FAILs. The morning
  report's table gains six rows from it, kept in `history.jsonl` so each batch stands beside the last. Read on the first
  adoption's last six days: nine rows, plan → merge median 6h42m, of it after the approval 55m, tokens median 54k, process :
  product commits 84 : 12, three rollups, no revert — the baseline every later v3 phase is scored against; suite runs count
  from this change on. tests/size-budget.json raised: `script_lines` 14,516 → 14,809.
- **Workflow v3, the design** (the owner's go, 2026-10-25): `docs/design/workflow-v3.md`. The first adoption measured the
  full suite three times on one commit, three judges spending about 195k tokens on one row with no blocker, a five-line fix
  behind four steps, proofs misread as shell, and an orchestrator at its context ceiling every few hours. v3: the tier decides
  the whole pipeline (a fast path for most rows, the current rigor on the critical path), one trusted result per commit that
  every judge reads, one fresh judge per concern, proofs as named tests, two rows in flight, scripts orchestrating; every
  removed step names what catches what it caught. Seven phases, one PR each, measured first (phase 1) and guarded by a
  rework ceiling. Design only, no code; tests/size-budget.json: unchanged.
- **The guard never says HANDOFF.md was written when it was not** (2026-10-25, the first adoption). At the context
  ceiling the guard runs `reef-handoff --write` and denied with "HANDOFF.md written from measured state" whatever the
  script returned; on the Mac's Python 3.9 it was a SyntaxError, so the next session would have started from a handoff
  hours old (the orchestrator noticed and rewrote it by hand). The denial now says written only on exit 0, and otherwise
  "HANDOFF.md NOT written (reef-handoff exit N: <its last line>)" with what to do. The old test passed because its fixture
  already held a HANDOFF.md; it now checks the file was replaced, and a failing reef-handoff has its own test. tests/size-budget.json
  raised: `script_lines` 14,509 → 14,516 (the guard reads the script's exit code and says why).
- **Reef runs on the Python a Mac ships** (2026-10-25, the first adoption: macOS's `/usr/bin/python3` is 3.9).
  `reef-merge-close` and `reef-handoff` were SyntaxErrors there — an f-string with a backslash, and one nesting its own
  quotes, both legal only from 3.12 — so a finished task could not merge without another Python, and the guard's
  checkpoint wrote no HANDOFF.md. CI never saw it: both legs ran 3.12+. Both lines rewritten without the 3.12 forms (no
  size change); `tests/test_python_floor.py` compiles every Reef Python file under the running interpreter and, on 3.12+,
  refuses an f-string expression with a backslash or its own quote; the macOS CI leg now runs `/usr/bin/python3`. Under
  3.9 the whole suite passed but for these two scripts.
- **Reef's own scripts are never the project's product code** (2026-10-25, found by running the adoption on two public
  repositories: a Go service and a FastAPI + TypeScript template). After `reef-init`, the measure counted `scripts/reef-*`
  as the project's code: the largest "product" file was `scripts/reef-queue.py`, Reef's scripts were listed as the
  project's sensitive files, and `reef/size-baseline.json` held them — the size gate would then have flagged a
  `reef-update` that grows a Reef script. The measure and `reef-structure --sizes` skip Reef's code (`scripts/reef-*`,
  `.githooks/*`). tests/size-budget.json raised: `script_lines` 14,505 → 14,509.
- **No adopted project is named in Reef's code or prose** (the owner's decision, 2026-10-25). 44 history notes in scripts
  and skills named the first project Reef adopted; they now say "the first adoption" (#117 did the same for the trial
  project). `tests/test_generality.py` fails on the name anywhere in scripts, hooks, skills, agents, commands or templates,
  comments included; the generality baseline is empty. The CHANGELOG keeps the record. tests/size-budget.json: unchanged.
- **Adoption keeps an existing project's documents in place** (the owner's decision, 2026-10-25). Moving decisions, specs
  and stray documents into Reef's tree was the riskiest and least valuable part of adoption: every guess about who reads a
  file was a broken check somewhere (ai-coach: 603 `check:docs` errors from the first full plan; `docs/adr` moved under a
  script that reads it). `reef-recalibrate plan` now keeps every such document where it is (`keep`, "in place (<what it
  would do>: <why>; `plan --move` proposes the move)"); the old process still converts — the old queue's open rows → Reef
  rows, a second handoff → `HANDOFF.md`, the old loop's commands archived. `plan --move` gives the full move, as a later
  row, a folder at a time. `reef-structure --check` counts a document kept in place as the baseline (green on day one, a
  new stray document still fails); `plan --measure` runs the project's checks even when nothing moves. The reef-assess
  skill says so (and names `.git/reef/proposed/` and the check family from any task runner). tests/size-budget.json
  raised: `script_lines` 14,493 → 14,505.
- **One stack's tools live in data: `scripts/reef-stacks.json`** (the owner's rule, 2026-10-25). Raw SQL, the database
  client, the layer-boundary tool and the session and permission vocabulary were node + Prisma + Next.js + dependency-cruiser
  in Reef's code; another stack got nothing, or a sentence naming Prisma. Now each stack is a profile: the files that detect
  it, where its dependencies are declared, its code files and comment markers, its raw-SQL rule (unsafe and safe calls, the
  fix), its boundary tool (a config template and rules, or an ADR draft), its session and permission words, its generated
  code. `node` holds exactly what the code held; `python` is new: SQL built with an f-string, `%` or `.format()` is measured,
  proposed as `assess.raw_sql_allow` and gated by `reef-structure --raw-sql`; `request.session`, `login_required`,
  `Depends(get_current_user)` are sensitive. A stack with no profile is told "no stack profile" and offered no other
  stack's tool. The gate switches on exactly as the measure did (the stack and the dependency its rule names), so day one is
  green. reef-init copies the file with the scripts; the guard protects it by its name. Reef's code holds no stack name now
  (generality baseline: only three skills' "ai-coach" notes left). tests/size-budget.json raised: `script_lines` 14,324 → 14,493.
- **An instruction file's process rules are found by their shape, not by one project's command names** (the owner's rule,
  2026-10-25). The patterns named one adopted project's commands (`/loop-start`, `npm run loop:close`, `loop:adr`,
  `docs/loop/`): on another project the plan found almost no rule to rewrite. A rule is now a slash command, a task-runner
  command (npm, pnpm, yarn, bun, make, just, task, poe, pdm, hatch, tox, invoke, rake, composer) or a namespaced script
  whose name means start, close or ADR; a sentence about numbering ADRs; a queue or backlog file outside `reef/`. The
  old names left the code (generality baseline lowered). tests/size-budget.json raised: `script_lines` 14,312 → 14,324.
- **The project's own commands come from whichever task runner it uses** (the owner's rule, 2026-10-25). `plan --measure`
  ran `gates.full` and `package.json` `check:*` scripts only, and the old loop's commands were found only among
  `package.json` scripts: a project on make, just, task, tox or a pyproject runner was invisible. `project_commands()`
  reads package.json scripts, Makefile targets, justfile recipes, Taskfile tasks, tox environments and pyproject
  poe/pdm/hatch scripts; the measure runs every check-family command (`check`, `check:*`, `check-*`) and its table row
  shows the command that ran (`npm run check:docs`, `make check-docs`); an old loop's `loop*`, `handoff*` and `adr*`
  commands are listed for the owner from any runner. tests/size-budget.json raised: `script_lines` 14,277 → 14,312.
- **The guard knows a gate on any stack** (the owner's rule, 2026-10-25). Piping a gate hides its exit code; the guard knew
  npm, pytest, vitest, jest, cargo and go — and one adopted project's `npm run ci:local` by name. Now a gate is a command
  the project configured in `.reef/config.json` `gates.*` (each `&&` part; lint and typecheck count when configured), a
  task runner's test, check, ci, verify or spec target (npm, pnpm, yarn, bun, make, just, task, composer, deno, mix, dotnet,
  maven, gradle), or a common test runner (rspec, phpunit, tox, nox, ctest, mocha besides the old ones). `npm run lint |
  tail` stays allowed when lint is not a configured gate. The project's name left the guard: the generality baseline drops
  `ci:local`. tests/size-budget.json raised: `script_lines` 14,249 → 14,277.
- **Reef works on any project and any stack: two guards** (the owner's rule, 2026-10-25). (1) `tests/test_generality.py`
  `GeneralityRatchet`: names of one adopted project or one stack's tools in Reef's code and agent-facing prose (comments and
  docstrings are history and do not count) are listed in `tests/generality-baseline.json` — 40 hits in 7 files today
  (`ci:local` in the guard, the old loop's command names and Prisma, Next.js and dependency-cruiser in reef-recalibrate,
  "ai-coach" in three skills) — and the list only shrinks: a new hit is red, a removed one is red until the baseline is
  lowered with it. (2) `AnyStack`: a node + Next.js + Prisma project, a python + FastAPI + SQLAlchemy project, a go project
  and a ruby project (no stack profile) each run reef-init → measure → plan → apply → structure → doctor; every step
  finishes and the project's own check, which reads its ADR folder by directory, still passes. No script changed.
- **Reef's proposals live under the git dir, never in the work tree** (ai-coach, 2026-10-25; the owner's go). The project's
  `server-context.test.ts` walks the disk (`readdirSync`, skipping only `node_modules`, `.git`, `.next`, `.claude`) and
  failed locally on Reef's git-ignored `.reef/proposed/`: `.dependency-cruiser.cjs` counted as a seventh JS file and
  `.reef/proposed/.claude/` as a nested skipped folder. Every tool, test runner and linter skips `.git`: reef-init's
  proposals now live in `<git common dir>/reef/proposed/` and the recalibration plan's in
  `<git common dir>/reef/recalibration/proposed/` (a linked worktree sees the same ones; outside a git repository,
  `.reef/` as before). `reef-init` (so `reef-update`) moves an older `.reef/proposed/` and `.reef/recalibration/proposed/`
  there once; the doctor, `reef-update`, `--accept`, the plan's `git diff --no-index` lines and the boundaries section
  point there. The apply now refuses before moving anything when a planned rewrite is missing (it was skipped silently),
  and removes an applied rewrite only when it commits — `plan --measure`'s scratch apply now applies the rewrites too and
  never deletes them. README, the site, the Arabic manual, the reef-init skill and two templates say where to look.
  tests/size-budget.json raised: `script_lines` 14,195 → 14,249.
- **The ADR home is `paths.adr`; a document under any configured `paths.*` home stays** (ai-coach, 2026-10-25). The apply
  wrote converted ADRs to `reef/architecture/adr/` whatever `paths.adr` said, and moved a configured `docs/adr/` there as well,
  while `reef-structure` has counted the configured folders as the layout since 0.7.2. On ai-coach the owner moved
  `docs/adr/` back (the project's `check:docs` reads it); the next apply would have split the ADRs across two homes. Now
  the plan keeps a document under a `paths.*` home ("already in the layout"), converted ADRs and numbered records land in
  `paths.adr` (default `reef/architecture/adr`), numbering counts both homes, and a clash names the record and the one in
  the home. **Changed:** item 21's test expected a configured `docs/adr/` to move into `reef/architecture/adr/`; it now
  expects it to stay. tests/size-budget.json raised: `script_lines` 14,176 → 14,195.
- **`reef-migrate --layout` leaves in place what the project's code reads by name** (ai-coach, 2026-10-25). The layout move
  took all 196 ADRs out of `docs/adr/` and set `paths.adr` to `reef/architecture/adr`; `scripts/check-docs.ts` reads
  `readdirSync("docs/adr")`, so `npm run check:docs` (gate 1 of the project's CI) failed with ENOENT while `npm test`, which
  never reads the folder, stayed green. Before each move the layout now asks the recalibration's reader checks — the file's
  path, the ADR folder as a folder; instruction files and Reef's own scripts are not readers — and a source something reads
  stays, with its `paths.*` key, printed as `kept: <path> (read by …)`. Everything else moves as before.
  tests/size-budget.json raised: `script_lines` 14,154 → 14,176.
- **Reef's own code is never the project's reader** (ai-coach, 2026-10-25). After `reef-init`, `scripts/reef-*` sit in the
  project and name `specs/`, `docs/`, `docs/loop/queue.md`, `docs/glossary.md` and `HANDOFF-FRESH.md` in their comments and
  code. The plan counted them as the project's readers: `specs/*` and the glossary kept ("read by scripts/reef-claims.py"),
  the old queue retired behind four reef-* scripts (the hand-off stayed "partial"), and the apply repointed paths inside
  `scripts/reef-recalibrate` itself, then refused on a "broken link" in its regex. A file under `scripts/reef-*` or
  `.githooks/` (the shape the guard locks and `reef-update --commit` stages) no longer counts as a reader, by exact path or
  by directory. tests/size-budget.json raised: `script_lines` 14,150 → 14,154.
- **The recalibration plan's proposals no longer land in reef-init's `.reef/proposed/`** (ai-coach, 2026-10-25). The plan
  wrote its instruction-layer rewrites (item 19) and the dependency-cruiser config and baseline (item 13) under
  `.reef/proposed/`, reef-init's directory: the AGENTS.md rewrite overwrote init's own AGENTS.md proposal, `reef-update` and
  the doctor listed the plan's files as renderings waiting for `reef-init --accept`, and that advice was destructive —
  accepting AGENTS.md recorded the rewrite as Reef's rendering, so the next `reef-update` replaced AGENTS.md with the template
  (the product text and the project's own rules gone); accepting the archived CLAUDE-CODE-PROMPT.md put it back at the root.
  The plan now writes to `.reef/recalibration/proposed/` (ignored by reef-init's `.gitignore` lines), the `git diff
  --no-index` lines and the boundaries section point there, and the apply removes each rewrite it applied (only after the
  apply succeeded: a refused apply keeps them). tests/size-budget.json raised: `script_lines` 14,144 → 14,150.
- **`structure` can be switched on the day of the adoption** (ai-coach, 2026-10-25; the owner's go). After the apply,
  `reef-structure --check` found 507 process documents outside the layout — 443 under `specs/` and 64 under
  `design_handoff/` — every one of them KEPT by the recalibration plan because the project's own checks read those
  directories (item 16's rule), so the gate could not join `gates.extra` without turning every row red. The check now reads
  `.reef/recalibration.json`: a document kept for a reader (a directory read, a code or instruction-file reference, a reader
  still to retire, an in-flight edit) is the baseline and is counted in a note, not failed; a document the plan never saw,
  or kept for another reason, still fails. Like `sizes` and `boundaries`: baseline first, only the new fails. tests/size-budget.json raised: `script_lines` 14,118 → 14,144.
- **Four adoption defects from the first real run of 0.7.2** (ai-coach, 2026-10-25). (1) `main`, the release branch, was reported
  "in flight under the old loop" because the word sat in `docs/loop/queue-archive.md`: the check now skips `branches.base` and
  `branches.release` and matches a branch name only inside an OPEN row of an old queue (or the old handoff), never anywhere in a
  file. (2) When the scratch apply of `plan --measure` failed, every gate still ran on the unchanged worktree and the table meant
  nothing: the measure now stops there, prints the apply's reason and skips the gates; an exit 127 is labelled "command not
  found: not on sh's PATH". (3) 220 of 517 test files were listed as "guard tests" because "never" or "rules" appeared in their
  first 30 lines: a guard test is now one whose NAME says so or whose docblock's first lines forbid something. (4) A second
  `measure` counted `.reef/proposed/.dependency-cruiser.cjs` as product code: Reef's own `.reef/` (and `.git/`) are never
  product. tests/size-budget.json raised: `script_lines` 14,107 → 14,118.

## 0.7.2 — the first adoption on an existing project: measure, recalibrate safely, adopt whole, deterministic checks
- **0.7.2** (the owner's go, 2026-10-25): `plugin.json`, the marketplace, `reef-init`'s version, the README badge and status,
  the site and the manual read 0.7.2; `migrations/0.7.1-to-0.7.2.py` is a no-change step so `.reef/version` walks to 0.7.2
  with no gap. The 21 entries below came from one adoption on an existing project (ai-coach), in order, one PR each.
- **The one-orchestrator hold belongs to a process, not a session id** (ai-coach, 2026-10-25; the owner's go). After
  `/clear` the same Claude process carries a new session id and was refused by its own hold for 30 minutes; a session that
  ended without `reef-loop.py wait` held the project as long, and the owner had to `unlock` by hand. The guard now records
  the holder's process (the hook's parent) in `.reef/run/orchestrator.json`: a hold from the same process is the same owner
  and is re-keyed to the new session; a hold whose process has ended holds nothing; a hold from another live process is
  still refused, now naming the pid. A hold written before this change (no pid) keeps the 30-minute rule.
  tests/test_lock.py `OneOrchestrator`. tests/size-budget.json raised: `script_lines` 14,086 → 14,107.
- **The design tier reaches the project's real sensitive code** (ai-coach, 2026-10-24, item 22). `tiers.design.paths`
  (auth, crypto, secrets, migrations globs) matched 0 of the 21 files that hold access control, tenant isolation and money
  (`session-access.ts`, `visibility*.ts`, `scoped-client*.ts`, `*tenant*`, `usage*.ts`, `metering*.ts`,
  `app/api/sign-in/**`): a change there ran as an ordinary `full` task, and Reef's security agent ran once per release
  while the project's own loop reviewed each risky item. Now (1) `reef-recalibrate measure` lists sensitive files BY
  CONTENT, Observed with file:line — session, cookie or token handling; `set_config`, RLS and tenant scoping; permission
  predicates; payment, usage, metering or cap code; secret reads; sign-in routes; and the files
  `reef/architecture/threat-model.md` names as mitigations; (2) the plan's `## Proposed tiers.design.paths` shows today's
  globs and the exact globs to add (a directory when it is mostly sensitive, else the file), each with the count of files
  it matches from `git ls-files`; the owner approves it with the plan and edits `.reef/config.json` — the apply never
  writes it; (3) `/reef-review` dispatches `reef:security` (model `roles.security`) on the feature diff of a `design` or
  `critical` task before the GREEN record, opt-out per project with `review.security_per_item: off` (new key, default
  `on`). tests/size-budget.json raised: `config_keys` 95 → 96, `prose_words` 21,165 → 21,227, `script_lines` 13,999 → 14,086.
- **Recalibration keeps the project's existing ADR numbers** (ai-coach, 2026-10-24, item 21). 193 numbered ADRs in
  `docs/adr/`, cited 456 times as `ADR NNNN` in src and scripts, would each have taken a new number after the highest
  existing one, breaking every citation: every `convert-adr` took `nxt`. An ADR whose filename already carries a
  4-digit number is now the same record, `git mv`ed into Reef's ADR home with its text intact and no `Supersedes:`;
  only unnumbered decision documents are converted and numbered from the next free number, which counts the kept
  ones. A number clash with an ADR already in Reef's home refuses the apply and names both files; links are rewritten
  as before. The plan says "the same record, its number kept" on such lines. tests/size-budget.json raised: `script_lines` 13,979 → 13,999.
- **`add-row` on issues no longer hands out duplicate ids** (ai-coach, 2026-10-24, item 20). Six `add-row` calls in a row
  created issues titled `[3] [3] [4] [4] [5] [5]` with wrong `Depends:`, because the next id came from GitHub's issue
  list, which lags a just-created issue. Now the last allocated id is kept in `.reef/queue.json` under a file lock and
  counts like a row's (the snapshot's re-read carries it over); after `issue create` the open rows are re-read and, if
  another issue carries the same `[id]`, the newer one is retitled to the next free id and the change printed; new
  `add-rows --file rows.json` creates a chain in one pass, `@prev` in a row's depends resolving to the id just
  allocated. tests/test_queue_issues.py `RowIds`, with a fake gh whose list lags one create. tests/size-budget.json raised: `script_lines` 13,904 → 13,979.
- **Assess does the whole adoption and says what it did not** (ai-coach, 2026-10-24, item 18). The owner approved a
  reduced recalibration (32 documents archived); `specs/`, `docs/adr/`, a 909-row old queue and a second handoff stayed
  because the project's own tools read them, and assess asked to push and merge without saying the replacement was
  deferred or in what order it had to happen. The plan now carries the adoption as one ordered list — the old queue's
  open rows become Reef rows (`add-row`, planned) and the file is archived with its closed rows; the old handoff is
  merged into `HANDOFF.md` under `## Carried over from …` and archived; every reader of a moved document is repointed
  (an exact path, rewritten in place at apply) or retired (a directory read: a found row with the blocker, the documents
  under it wait); the old loop's commands and agents are archived and its package scripts listed for the owner; the
  instruction layer is rewritten (item 19) — all in ONE commit. Precondition, checked by the plan and the apply: the old
  loop has nothing in flight — an unmerged local branch its queue or handoff names refuses the migration and is named;
  `--apply --park-in-flight` re-admits each as a Reef row and migrates. `plan --measure` runs the whole adoption in a
  scratch worktree (item 16d). The apply ends with "hand-off: Reef's tree is complete" or "partial: N documents outside
  it — rows #a–#b, blocked by …", and names the holds the project's own handoff and runbooks state ("nothing merges into
  develop until promotion 11"); the skill never asks to push or merge before that line. Ships after item 19, whose
  instruction-layer functions it uses. tests/size-budget.json raised: `prose_words` 21,089 → 21,165, `script_lines` 13,701 → 13,904.
- **The project's instruction layer no longer points agents at the old process** (ai-coach, 2026-10-24, item 19).
  `CLAUDE.md`, `AGENTS.md` and `CLAUDE-CODE-PROMPT.md` told every session to read `HANDOFF-FRESH.md` and
  `docs/loop/queue.md` first, start with `/loop-start`, close with `npm run loop:close`, number ADRs with `loop:adr`, route
  models by their own table and run up to 15 agents; after adoption a fresh session obeyed them, not Reef. Two causes:
  the reference search excluded every `*.md`, so the files agents read first never counted as readers; and when the owner
  kept their own AGENTS.md nothing reconciled its process sections. Now (1) `CLAUDE*.md`, `AGENTS.md`, `GEMINI.md`,
  `.cursorrules`, `.github/copilot-instructions.md`, `.claude/commands/**` and `.claude/agents/**` are readers (a
  document only they name is kept, "referenced by CLAUDE.md"); (2) the plan writes `reef/instruction-layer.md`: per file
  every pointer to a process document and every conflicting rule (start and close commands, ADR numbering, round and
  agent caps, model routing, handoff file) with file:line — Observed — and flags a duplicate CLAUDE file; (3) each such
  file's rewrite is proposed under `.reef/proposed/` and applied in the recalibration's one commit: product content
  verbatim, process sections replaced by one pointer to Reef's tree, another tool's `<!-- BEGIN:… -->` block byte-identical,
  the duplicate merged into the primary and archived; (4) a project rule that contradicts a Reef default ("there is
  deliberately no linter") is surfaced, never overridden. Outside an approved recalibration init's never-overwrite rule
  still holds. tests/size-budget.json raised: `script_lines` 13,526 → 13,701.
- **`reef-structure` accepts the layout `reef-init` itself chose** (ai-coach, 2026-10-24, item 17). After init and assess
  the check reported about 700 lines, `docs/adr/` among them — the ADR home init had written into `.reef/config.json`
  (`paths.adr: docs/adr`): init picks the legacy layout for a project with `.specify/`, `docs/queue.md` or `docs/adr`,
  but also writes `.reef/version`, and the check accepted the legacy places only without that file. It now reads
  `paths.*` (adr, queue, runlog, glossary, tasks, features, day_zero) and accepts those locations whatever the
  version; the hard-coded 0.5 tuple is the fallback only when no paths are configured. tests/size-budget.json raised: `script_lines` 13,512 → 13,526.
- **The recalibration plan no longer moves what the project's tools read** (ai-coach, 2026-10-24, item 16). The full
  plan moved 735 documents; applied in a scratch worktree it caused 603 `check:docs` errors, 4 red tests, archived a
  font licence and conflicted with 4 in-flight branches. Four causes, four rules: (a) a reference search by exact path
  missed every tool that reads a DIRECTORY or a glob — every ancestor directory (`docs/loop/`, `docs/loop`, `specs/`) is
  now grepped in code, CI and package.json as a directory read (never a file inside it), and a hit keeps every document
  under it, reason "directory … read by …"; (b) `KEEP` matched exact basenames — any `licen[cs]e|copying|notice|ofl`
  file anywhere is kept, and so is every document beside an asset's licence (fonts, images, binaries); (c) a document
  changed on a local branch not merged into `branches.base` is kept, reason "edited on unmerged branch …"; (d)
  `plan --measure` applies the plan in a scratch worktree, runs `gates.full` and every package.json `check:*` script
  there, prints exit codes, error lines and red tests into the plan, and removes the worktree — the tree is untouched.
  The assess skill's one question shows those numbers and recommends the smallest plan with zero errors; on an existing
  project "archive the stray docs, keep folders the project's tools read" is the default. tests/size-budget.json raised: `prose_words` 21,020 → 21,089, `script_lines` 13,388 → 13,512.
- **A `refactor` task kind with a behaviour-preservation proof** (ai-coach, 2026-10-24, item 15). ai-coach's largest
  product files need splitting, and a split's only promise is that nothing changes; Reef had no way to state or check
  that. Optional frontmatter `kind: refactor` with `splits: <file>[, <file>] under <N> lines`: `reef-plan-check`
  refuses a refactor task without the files it splits and the size they end under (and any other `kind`); `reef-converge`
  adds the deterministic criterion — in the branch's diff against `branches.base` no EXISTING test file changes an
  assertion line (`expect(`, `assert`, `should`; moved lines and imports allowed, new test files allowed, renamed paths
  followed), and the full gate is green. The implementer's brief says the rule; the task template names the field.
  Rows from the measure's findings (items 10 and 14) are created with this kind. tests/size-budget.json raised: `prose_words` 20,992 → 21,020, `script_lines` 13,338 → 13,388.
- **Big files only shrink: the size ratchet** (ai-coach, 2026-10-24, item 14). Nothing stopped a 2,000-line file from
  growing. `reef-structure --sizes` reads `reef/size-baseline.json` (written by `reef-recalibrate measure`: product
  files only, the same excludes — tests, declarations, generated and data directories, `assess.exclude`): a baselined
  file may not grow past its baseline, a new file may not exceed `structure.new_file_lines` (default 400), and a file that
  shrank lowers its baseline in the same run, to be committed with the change. Only files changed since HEAD are read:
  2,000 product files with one change take 0.10 s on this machine, so the gate is charged to every tier. It joins
  `gates.extra` as `"sizes"` once the owner approves it in the recalibration plan; day one is green because the baseline
  is today's sizes. tests/size-budget.json raised: `config_keys` 94 → 95, `script_lines` 13,273 → 13,338.
- **Layer boundaries get a proposed gate with a baseline** (ai-coach, 2026-10-24, item 13). Nothing enforced that a
  component never imports the database client or that an API route reaches it only through `lib/`. On node,
  `reef-recalibrate measure` now derives a dependency-cruiser config from the observed layout (the client is the file
  with `new PrismaClient(`; `tsconfig` path aliases resolved), writes it with today's violations as the known-violations
  baseline under `.reef/proposed/`, and the plan's `## Proposed gate — boundaries` names the two rules, the baseline's
  size, and the `gates.extra` line (`npx depcruise … --ignore-known src`) the owner adds on approval — day one is green,
  only a NEW violation fails, and once a baseline is committed the measure lists what is new since it. Python gets an
  ADR draft (import-linter) only; other stacks nothing yet. tests/size-budget.json raised: `script_lines` 13,157 → 13,273.
- **SQL injection has a deterministic check** (ai-coach, 2026-10-24, item 12). Only the security agent's judgment stood
  between an `$executeRawUnsafe` and the release; `gates.release` had gitleaks and the stack audit, nothing for
  injection. (A) A release gate per stack, proposed on upgrade like the other release gates and written for a new
  project: `command -v semgrep >/dev/null 2>&1 || exit 77; semgrep scan --config p/owasp-top-ten --config p/<stack>
  --error` (`p/typescript`, `p/python`, `p/rust`, `p/golang`); the CI template installs semgrep like gitleaks; a missing
  scanner is exit 77, which `reef-ci-local` reports as a skip, never a pass. (B) `reef-structure --raw-sql` (node +
  Prisma, for `gates.extra`) fails on `$queryRawUnsafe`/`$executeRawUnsafe` in a file outside `assess.raw_sql_allow` —
  the files the measure found holding one, a baseline, not a cleanup — with comment lines ignored; the measure's
  proposal reuses the project's own equivalent guard test when it has one instead of adding this. tests/size-budget.json raised: `script_lines` 13,076 → 13,157.
- **A draft decision record on adopting a project that runs its own loop** (ai-coach, 2026-10-24, item 11; design only).
  Init wrote `docs/queue.md` and `HANDOFF.md` beside ai-coach's `docs/loop/queue.md` and `HANDOFF-FRESH.md`: two
  queues, two handoffs. `docs/design/existing-loop-adoption.md` lists the detection signals (`docs/loop/`, `HANDOFF*.md`,
  `.specify/`, `specs/*/spec.md`, loop-like package scripts, instruction files naming them) and the two options — init
  skips its records and assess migrates, or init writes and assess merges — with a recommendation; the owner decides and
  the implementation is a later row. No code. tests/size-budget.json: unchanged (nothing grew).
- **Assess measures architecture instead of scoring it by feel** (ai-coach, 2026-10-24, item 10). `/reef-assess` scored
  "module boundaries" by judgment; nothing was counted. On ai-coach the largest files were tests and an i18n dictionary
  (2,613 lines of data), the `$executeRawUnsafe` hits were mostly comments, the tagged `$queryRaw` calls were
  parameterised, and four migrations defined triggers. New `reef-recalibrate measure [--json]` writes `## Measured` into
  `reef/day-zero.md` (replaced on a re-run): the 10 largest product files (tests, `*.d.ts`, generated and data
  directories `i18n|locales|interface|translations` left out, plus `assess.exclude`), product vs test LOC, raw SQL by
  directory as tagged vs Unsafe with comment lines ignored (node/Prisma; other stacks "not measured"), `CREATE
  FUNCTION`/`CREATE TRIGGER` per migration (Observed; classification is Inferred, by Explore), linter present with its
  file, and the project's existing guard tests (test files whose name or docblock forbids something) so later gates
  reuse them. `reef/size-baseline.json` (product files only, the same excludes) is written for the size ratchet. Files
  over `assess.large_file` (default 800) become candidate `kind: refactor` rows under `## Proposed rows (refactor)` in
  `reef/recalibration.md` — proposed with the plan, never created. New config keys `assess.exclude`, `assess.large_file`.
  The assess skill runs it before scoring; a contract test asserts the sentence. tests/size-budget.json raised: `config_keys` 92 → 94, `prose_words` 20,940 → 20,992, `script_lines` 12,924 → 13,076.
- **`reef-doctor` names a local `.env` the gate reads and CI does not** (ai-coach, 2026-10-24, item 9). Prisma loads the
  checkout's `.env`; with two keys set, the base branch failed 21 tests that pass in CI, and nothing said why. When
  `.env` exists and `gates.full` is set, one line names the keys (names only, never values) and the one command to
  compare: `KEY= … <gates.full>`. No automatic double run. tests/size-budget.json raised: `script_lines` 12,916 → 12,924.
- **Init recommends the project's own files over Reef's renderings on an existing project** (ai-coach, 2026-10-24,
  item 8). Accepting Reef's ci.yml, AGENTS.md and dependabot.yml broke 62 of ai-coach's tests in 11 files. The skill's
  step 3 now says: on an existing project the recommended answer for every proposed file is "keep yours"; before
  recommending an accept, run `gates.full` with that proposal applied in a scratch worktree and report the result; when
  the project keeps its own ci.yml, name the missing Reef release step (`sh scripts/reef-ci-local.sh --ci --release`);
  when its AGENTS.md lacks the `.reef/**` exclusions, say so. A contract test asserts both sentences. tests/size-budget.json raised: `prose_words` 20,868 → 20,940.
- **`reef-repo` says why branch protection fails on a private repository** (ai-coach, 2026-10-24, item 7). The protection
  PUT came back 403 with no explanation; the cause was the GitHub plan, not a permission. On a 403 with
  `gh api repos/{nwo} --jq .private` true the screen adds: branch protection on a private repository needs GitHub
  Pro/Team — until then CI and the local gate are the only wall. A public repository keeps the old message. tests/size-budget.json raised: `script_lines` 12,912 → 12,916.
- **`/reef-assess` stops before `/reef-init` ran** (ai-coach, 2026-10-24, item 5). Assess calls the project's own
  `scripts/reef-recalibrate` and `scripts/reef-structure`, which only init installs, and had no prerequisite step. Step 0:
  `test -f scripts/reef-recalibrate && test -f .reef/config.json` or STOP with "run /reef-init first"; a contract test
  asserts the sentence and its place before any reading. tests/size-budget.json raised: `prose_words` 20,828 → 20,868.
- **`gates.fast` is no longer always empty** (ai-coach, 2026-10-24, item 4). `reef-init` initialised the fast gate to
  `""` and nothing set it, so every commit ran the full suite (66 s on ai-coach). For node it is now built from
  package.json, joined with `&&`, each part only when present: `npm run lint` (`scripts.lint`), `npm run typecheck`
  (`scripts.typecheck`, else `npx tsc --noEmit` with a `typescript` dependency and a `tsconfig.json`), `npx vitest run
  --changed` (a `vitest` dependency). Empty when none; never an invented script. A tuned value is never changed.
  tests/test_init.py `FastGate`. tests/size-budget.json raised: `script_lines` 12,899 → 12,912.
- **`worktree.setup` generates as well as installs** (ai-coach, 2026-10-24, item 3). Task worktrees got a stale Prisma
  client and `.next` types: about 14 test files failed for reasons unrelated to the task, because `reef-init` set
  `worktree.setup` to the install command alone. For node it is now `npm ci && npm run generate` when `scripts.generate`
  exists, else `npm ci && npx prisma generate` when `prisma` or `@prisma/client` is a dependency, else `npm ci`; never
  `scripts.setup` or anything that migrates a database. An existing value is still never changed (the merge rule).
  tests/test_init.py `WorktreeSetup`. tests/size-budget.json raised: `script_lines` 12,892 → 12,899.
- **The guard refuses `git push --no-verify` when the repository has a pre-push hook** (ai-coach, 2026-10-24, item 2).
  ai-coach chained its push guard into `.githooks/pre-push`; any agent could skip it, since the guard caught the bypass on
  commit and merge but not on push. Now the long form is denied when `.githooks/pre-push` exists at the git root of the
  command's directory; without that file it stays allowed (nothing to skip), and `push -n` is `--dry-run`, not a bypass.
  tests/test_guard.py `PushBypass`. tests/size-budget.json raised: `script_lines` 12,879 → 12,892.
- **The pre-commit hook no longer takes a stale `REBASE_HEAD` for a rebase in progress** (ai-coach, 2026-10-24, item 1).
  A leftover `.git/REBASE_HEAD` with no rebase running made every commit gate the worktree instead of the index — the
  very mistake the index dance exists to avoid. A running rebase is its directory, `rebase-merge/` or `rebase-apply/`;
  the hook now tests those. `MERGE_HEAD` and `CHERRY_PICK_HEAD` are read as before. tests/test_hooks.sh: a stale file
  with a good index and a broken worktree commits the index; a conflicted rebase still gates in place. tests/size-budget.json: unchanged (nothing grew).
- **A task's merge and close-out is one command** (the owner's go, 2026-10-24, item 4). At every passed task the
  orchestrator ran eight commands by hand — the commit in the task worktree, the `--no-ff` merge, `status: done`, the
  `git mv` to `tasks/done/`, the journal block, `worktree.setup` after a lockfile, the worktree and branch removal — each
  a chance to skip one (2026-10-17: a task under `done/` still in-progress; 2026-10-18: a Prisma client older than its
  migration until `npm ci`). New `scripts/reef-merge-close <task-file> --subject "<subject>" --journal <file>`, run in the
  feature worktree: stages every change in the task's worktree (printed; a `.env*`, `.pem` or `.key` file refused — the
  implementer's worktree holds only its work; the owner may narrow this) and commits with the `Closes-task:` trailer,
  merges `--no-ff --no-commit`, runs `worktree.setup` first when the merge touches a lockfile (`package.json`, the npm,
  pnpm, yarn, poetry, uv, Cargo, Go and Bundler lockfiles, `pyproject.toml`, `requirements.txt`, `prisma/schema.prisma`),
  puts `status: done`, the journal file's text between `<!-- journal -->` markers and the move to `tasks/done/` in that
  merge commit, then removes the worktree and the branch. A conflict or a gate refusal aborts the merge and restores the
  task file as it was (exit 2); a re-run resumes from the step left. The guard counts it as a loop write (one orchestrator
  at a time); `/reef-task` step 4 is the one call under a long Bash timeout. tests/size-budget.json: `prose_words`
  20,864 → 20,828 (the step got shorter), `script_lines` 12,722 → 12,879.
- **A queue row's author must be a collaborator** (the owner's go, 2026-10-24, item 9). On a public repository anyone can
  open an issue, and `admit` turned it into a row in place: the author kept editing their own issue's body, whose `Depends:`,
  `Admitted:` and `Item:` lines every reader parses. Now `admit` on an issue by a non-collaborator (or when the list is
  unknown) copies it into an issue of the owner's — the original's text quoted, so none of its lines reads as a field —
  and closes the original with a link; the sync records each row issue's author, reads the collaborators
  (`gh api repos/{owner}/{repo}/collaborators`) into the snapshot, excludes an open row by an outsider from the queue and
  warns about it (`check` too; the id still counts). An unreadable list (a 403: the token lacks push access) keeps the
  last good one, said on stderr; a repository where none was ever read runs no trust check and says so.
  tests/size-budget.json raised for items 7 to 10 together: `prose_words` 20,843 → 20,864, `script_lines` 12,602 → 12,722.
- **A question for the owner is a command, and on issues an issue** (the owner's go, 2026-10-24, item 7). The headless
  runner's questions were lines appended to `.reef/questions.md` by hand, each session in its own words. `reef-queue.py
  ask "<question>" --row <id> --recommended "<answer>"` writes the line and, on `queue.home: issues`, opens an issue
  labelled `reef-question` assigned to the owner; `answered <#n> "<answer>"` closes it with the answer. The runner's prompt
  and `/reef-loop`'s headless rule use them.
- **A noted risk is an issue, never a row** (the owner's go, 2026-10-24, item 8). On `queue.home: issues` the noted risks
  stayed in a file beside a queue that had moved. `note` opens an issue labelled `reef-note`; `demote` relabels the row's
  own issue to a note; `promote-note #N` relabels the note back into a found row (`Depends` its row, the note's number in
  the title); `triage` prints the open-note count.
- **A read-only view of the queue** (the owner's go, 2026-10-24, item 10). With the queue on issues, nothing in the
  checkout showed it. Every sync writes `.reef/queue-view.md`, a table sorted by batch, priority and id with each row's
  issue number, gitignored by `reef-init` so it never drifts into a second queue: read it offline, edit the issues.
- **The acceptance review is a lean judge, not a general-purpose agent** (the owner's go, 2026-10-24, item 6). The
  feature's acceptance review ran in a general-purpose agent that started at about 17,000 tokens of context, against
  about 7,500 for Reef's own agents. New `reef:acceptance` (model `roles.reviewer`): read-only like the verifier, it judges
  the feature against its `SPEC.md` from the user's side, one PASS/FAIL with evidence per FR/SC key, `unrequested` work a
  finding, and writes a report that opens with `HEAD:`, carries `RUN: agent=acceptance feature=<slug>` and ends with
  `VERDICT: GREEN | FAIL`, read through `reef-claims.py verdict`. The guard locks it (no project writes, the model from
  `roles.reviewer`); the OpenCode host maps and judges it the same way; `/reef-review` dispatches it. tests/size-budget.json
  raised: `prose_words` 20,474 → 20,843.
- **The orchestrator reads a judge's verdict, not its report** (the owner's go, 2026-10-24, item 5: the trial night's
  orchestrator read 64,000 characters of full judge reports, each re-read at every later step). `reef-claims.py verdict
  <report>` prints the RUN line, the verdict, every BLOCKER, failed criterion, NEW-ROW and NOTED line, and the report's
  length (exit 0 PASS/GREEN, 1 FAIL, 2 no verdict); `/reef-task`, `/reef-loop`, `/reef-plan` and `/reef-review` read
  reports through it and open the full file only for a blocker's detail. tests/size-budget.json raised: `prose_words`
  20,406 → 20,474, `script_lines` 12,581 → 12,602.
- **The morning report counts the night** (the owner's go, 2026-10-24, item 3: "how do I know the factory gets better").
  A new "night in numbers" table: PRs merged into the base, tasks finished on any branch (a file arriving under
  `tasks/done/`), the first-pass share (a finished task whose `attempts` stayed 0), the stalls (a wait on the owner, a
  stop, a park), the cost and the cost per merged row, beside the previous night's from `.reef/night/history.jsonl`, which
  each report appends to. tests/size-budget.json raised: `prose_words` 20,385 → 20,406, `script_lines` 12,540 → 12,581.
- **A gate run holds the project's shared resources** (the owner's go, 2026-10-24, item 1). On the trial a full gate went
  red on three tests while a verifier's test run used the same test database; re-run alone it passed 273/273. New
  `gates.resources` (default none): the gate holds each named resource for its whole run through `reef-graph.py lock`,
  and its timeout doubles to cover the wait. The lock's slots are now keyed on the main checkout, so a task worktree and
  the main checkout share one resource (they each had their own). The implementer, the verifier and the hunter run their
  own test commands on such a resource under the same lock. tests/size-budget.json raised: `config_keys` 91 → 92,
  `prose_words` 20,292 → 20,385, `script_lines` 12,522 → 12,540.
- **An existing project's queue survives `/reef-assess`** (the owner's go, 2026-10-24; found while preparing AI coach).
  `reef-init` treated any repository without a Reef config as new and moved its queue to issues; `/reef-assess` then
  appended its converted specs' rows to the queue file, numbered from 1, where issues mode no longer reads them. Now:
  `reef-init` moves a first-time repository with tracked files only on `--queue issues` (otherwise it says to run
  `/reef-assess` first, then `migrate-to-issues`); `reef-queue.py next-id` gives the next id in either mode and
  `reef-recalibrate` numbers from it; on issues, after the move's own revertable commit, the new `import-rows --apply`
  makes the rows issues (ids kept, an id that is already an issue refused) in a commit of its own; `check` warns of rows
  left in the file. tests/size-budget.json raised: `script_lines` 12,432 → 12,522.
- **A cached gate shows its evidence; a judge runs the gate once** (the owner's go, 2026-10-24). On the trial night the
  verifiers ran the gate 25 times across 6 verdicts, 16 of them forced fresh, because a cached run said only "exit 0".
  The gate now keeps a green run's log beside its marker, with the run's last lines in the marker, and a cached run
  prints both; the output still streams. The verifier (agent and `reef-verify`) runs the gate once and fresh per verdict,
  quotes its last lines, and never re-runs a red gate until it passes: it reports it with its log. One fresh run stays:
  nothing stops an implementer from planting a marker, so a judge does not take a cached green as its own evidence.
  tests/size-budget.json raised: `prose_words` 20,203 → 20,292, `script_lines` 12,412 → 12,432.

## 0.7.1 — the queue on GitHub issues, priority and triage, one orchestrator at a time
- **0.7.1** (the owner's go, 2026-10-24, option 2: the lock, `/reef-run` and the checker fixes first): `plugin.json`,
  the marketplace, `reef-init`'s version, the README badge and status, the site and the manual read 0.7.1;
  `migrations/0.7.0-to-0.7.1.py` is a no-change step so `.reef/version` walks to 0.7.1 with no gap.
- **The guard pass is counted by tier, and says so** (the owner's go, 2026-10-24). On the trial's row 18 the orchestrator
  read "a design task" as `complexity: design` (task 1801 was tier full), found the guard pass unrecordable and filed a
  found row against the project. `/reef-review` now says "a task of tier `design` or `critical` (its `tier:`, not its
  `complexity:`)", and `reef-adversarial --feature … guard` refuses a feature without one by saying no guard pass is
  required. tests/size-budget.json raised: `prose_words` 20,194 → 20,203, `script_lines` 12,411 → 12,412.
- **reef-converge reads a Proof cell as written** (the owner's go, 2026-10-24; the trial's row 18, note n45: four false
  `missing` lines). A note in parentheses after a test name is commentary (backticks inside it allowed; a parenthesis
  inside a backticked command is the command's own); `` `cmd` prints `N` `` runs the command and compares its output
  (a different value is `contradicts`); a cell of prose names no test or command and is listed as not run, never
  reported missing. tests/size-budget.json raised: `script_lines` 12,359 → 12,411.
- **A note in parentheses is not an AC status** (the owner's go, 2026-10-24). Twice on the trial, the journal check
  read "AC1…AC5 achieved (AC3, AC4 rendered on the server by their Proof tests, not a browser)" as the status
  "rendered", and the agent rewrote the honest caveat as "achieved via server-rendered HTML" to pass. `reef-queue.py
  check` now drops parenthesized notes from the ACs cell before reading statuses; a bad status outside them still fails.
  tests/size-budget.json raised: `script_lines` 12,357 → 12,359.
- **`/reef-run`: the runner from Claude Code, and a clean stop** (the owner's go, 2026-10-24: "a command for the
  runner instead of the terminal"). A long session moved to the background had run the trial's loop for three days near
  its context ceiling, unwatched. `/reef-run` shows a live runner or starts one detached (the probe first when the mode
  has none), and `/reef-run stop` runs the new `reef-run.py stop`: a request the runner reads between sessions, so it
  never kills a headless session mid-merge; a fresh run clears an old request. Before, `reef-run.py stop` was an unknown
  word and started a runner. tests/size-budget.json raised: `prose_words` 19,994 → 20,194, `script_lines` 12,330 → 12,357.
- **One orchestrator at a time** (the owner's go, 2026-10-24). A terminal session and a background one, forked by
  Claude Code from an older conversation, ran the trial project's loop together and collided on develop; only the
  runner held a lock. The guard now lets the first main session that dispatches an agent or writes the loop's state
  (the tick, a merge, a record, a queue write, a push) hold the project in `.reef/run/orchestrator.json`; another
  session is refused while the holder acted in the last 30 minutes, subagents pass. `reef-loop.py wait` and `stop`
  release the hold (the /clear hand-over), `reef-loop.py unlock` is the owner's takeover, and the runner releases the
  hold of a session it ran. tests/size-budget.json raised: `prose_words` 19,960 → 19,994, `script_lines` 12,259 → 12,330.
- **The site, the Arabic manual and the README describe the issues queue** (the owner's go, 2026-10-24, batch A item 4):
  a row as an issue titled `[<id>]`, a batch as a milestone, the `p1`/`p2`/`p3` labels, `admit`, triage with
  `set-priority`/`demote`, the journal copied at the row's close, `queue.home` and `queue.batch_max`. Docs only.
- **`scripts/__pycache__/` is ignored** (the owner's go, 2026-10-24, batch A item 3). The Python byte-code of the copied
  scripts showed up untracked in every `git status` of the trial project; `reef-init` appends the line, so a refresh or
  `reef-update` adds it to an existing project. Size budget unchanged.
- **A feature branch never edits the journal** (the owner's go, 2026-10-24, batch A item 2). On the trial night two
  features both appended to the journal; their PRs conflicted on it, and the hand-resolved conflict ended in a GREEN
  re-recorded with no review. Git's union merge keeps both sides locally and in the guard's `merge-tree`, but GitHub's PR
  merge does not honor it (a 2016 report, unverified today), so the journal moves instead: at the task merge each task's
  journal block goes into its task file's `## Log` between `<!-- journal -->` markers (the Log is outside the plan digest),
  and `reef-queue.py journal <slug>` copies every block into `paths.runlog` on the base at the row's close, once.
  `/reef-task`, `/reef-review`, `/reef-loop` and the graph runner's hint say so. tests/size-budget.json raised:
  `prose_words` 19,872 → 19,960, `script_lines` 12,232 → 12,259.
- **A GREEN record carries its review; a base merge that leaves the feature unchanged carries over** (the owner's go,
  2026-10-24). On the trial night a journal conflict moved a PR's head, the guard said "re-review and re-record", and
  the orchestrator re-recorded GREEN with no review. `reef-record <feature> GREEN` now needs `--report`: the reviewer's
  report naming the PR head (its first 12 hex) with its `VERDICT:` line; a FAIL report, another head or no report is
  refused, and the record keeps the report's hash. The guard's carry-over also accepts a base merge whose resolution
  leaves the feature's own change identical (the patch-id of a zero-context diff against the base each side sits on), so
  that case needs no re-record at all; code slipped into the resolution is still a fresh review. tests/size-budget.json
  raised: `prose_words` 19,813 → 19,872, `script_lines` 12,198 → 12,232.
- **A new project's queue starts on GitHub issues** (the owner's go, 2026-10-24: no on-device queue unless clearly told).
  `/reef-init` asks where the queue lives and passes `--queue issues|file`. A new project whose own repository has a
  GitHub `origin` and a gh login moves to issues at the end of the init (`migrate-to-issues --apply`); without them it
  stays a file and says how to move later. An existing project moves only on `--queue issues`, so a refresh or
  `reef-update` never moves a queue; a folder inside another checkout never takes that checkout's remote.
  tests/size-budget.json raised: `prose_words` 19,790 → 19,813, `script_lines` 12,167 → 12,198.
- **Triage every finding, weekly and at each batch boundary** (the owner's go, 2026-10-24: 82 found rows piled up behind
  a 10-row batch, and the triage command only flagged rows two batches old). On issues, a found row with no priority
  label is untriaged, and giving it a priority is the decision. `triage` lists every untriaged row by module with four
  outcomes (keep with a priority, merge into a design row, drop with a reason, note); `triage --count` exits 1 once one
  has waited more than 7 days, so the tick names it; `/reef-loop` asks at every batch boundary. `demote ID` makes a
  queued finding that may never happen a note and closes its issue as not planned (security, privacy, money and data
  loss stay rows). `check` warns when the current batch holds more open rows than `queue.batch_max` (default 10).
  tests/size-budget.json raised: `config_keys` 90 → 91, `prose_words` 19,761 → 19,790, `script_lines` 12,103 → 12,167.
- **Priority labels the loop respects** (the owner's go, 2026-10-24: companies rank the backlog, Reef ordered rows by id).
  On issues, `p1`, `p2` and `p3` labels order `ready`: priority first (none counts as `p2`), then planned before found,
  then id; a found row labelled `p1` counts as planned, the owner having promoted it. `set-priority ID p1|p2|p3|none`;
  `add-row` and `admit` take `--priority`; the migration creates the three labels. Rows without a label keep their old
  order. tests/size-budget.json raised: `prose_words` 19,741 → 19,761, `script_lines` 12,075 → 12,103.
- **The migration skips the template's placeholder row** (the owner's go, 2026-10-24). On a fresh `/reef-init` project
  with no architecture grill, `migrate-to-issues` made the queue template's `<the first planned row, one line>` issue [1].
  A row whose Item is all angle brackets is skipped and named; a grilled first row (the walking skeleton) still moves.
  tests/size-budget.json raised: `script_lines` 12,072 → 12,075.
- **A Proof cell with two names checks each** (the owner's go, 2026-10-24). The trial's row 5 rollup reported a test
  missing that existed: `reef-converge` read the cell `` `a`, `b` `` as one name, "a`, `b". A cell holding only backticked
  spans joined by commas, semicolons or "and" is now one proof per span, each a test or a command as before.
  tests/size-budget.json raised: `script_lines` 12,068 → 12,072.
- **The queue on the project's GitHub issues, part 2: the readers and the loop** (the owner's go, 2026-10-24). The
  night runner's open-rows check and `reef-watch` read the snapshot `.reef/queue.json` under `queue.home: issues`, no
  network (after a migration the queue file has no table, and an empty set would refuse every night contract);
  `reef-init` gitignores the snapshot; the config template carries `queue.home: file`; `/reef-loop` closes a row with
  `reef-queue.py close <id> --pr <n>`, leaves an unadmitted issue to the owner's `admit`, and after the release the
  owner closes the batch's milestone. A gh read waits 15 s (`REEF_GH_READ_TIMEOUT`), then the snapshot answers; a write
  waits 60 s. tests/size-budget.json raised: `config_keys` 89 → 90, `prose_words` 19,695 → 19,741, `script_lines`
  12,054 → 12,068.
- **The queue on the project's GitHub issues, part 1: the queue script** (the owner's go, 2026-10-24). `queue.home:
  issues` makes a row an issue labelled `reef-row`, titled `[<id>] <item>` (Reef's id kept, so task ids, `Row:` lines
  and footnotes stay valid), its `Depends:` and `Admitted:` in the body, `planned` or `found` as a label; a batch is a
  milestone `Batch N`, the current batch the lowest open one; a closed issue is archived, one closed as not planned is
  dropped (its dependents dangle, as in the file queue). Every read syncs `.reef/queue.json` (a failing gh: the last
  snapshot); every write goes to gh and fails closed. New: `close ID --pr N`, `admit <issue>` (a plain issue becomes
  the next row), `migrate-to-issues [--apply]`. Footnotes, notes and the archive file stay files. Rehearsed on a copy of
  the trial project's queue: 92 open rows and the ready list identical before and after. A file-mode project sees no
  change. tests/size-budget.json raised: `script_lines` 11,822 → 12,054.
- **Read first: the planner hands the implementer its ranges** (the owner's go, 2026-10-24, a trial on one row of his
  pick). Implementers explored a median 17.5 tool calls before their first edit (38 runs on the trial project), reading 54,000
  characters and 15,000 of git history; the planner had already read that code. A task's optional `## Read first` lists
  at most 8 ranges, `path:start-end` (symbol) — why; the plan check fails an entry whose path is missing, outside the
  project or a dependency path, whose range leaves the file, or whose range does not hold its symbol. The implementer
  starts there and reports `extra reads` in its hand-back. Measured against that baseline: extend or drop.
  tests/size-budget.json raised: `prose_words` 19,612 → 19,695, `script_lines` 11,788 → 11,822.
- **The plan check reads each task's own feature folder** (the owner's go, 2026-10-24). A trial project row could not
  go green: the key check took the folder of the LAST task file (a stale loop variable), so every feature's citations
  were checked against the last-sorted folder, 15 false FAILs on other features' tasks, and a key defined only there
  passed anywhere. Each task now carries its own path into the second loop. Size budget unchanged.

## 0.7.0 — the delegated night, the outer runner, the security pass, OpenCode in early support
- **0.7.0** (the owner's go, 2026-10-24): `plugin.json`, the marketplace, `reef-init`'s version, the README badge, the site
  and the manual read 0.7.0; `migrations/0.6.0-to-0.7.0.py` is a no-change step so `.reef/version` walks to 0.7.0
  with no gap; the site's changelog card, the manual's lead and the reef-init skill name 0.7.0 too. The size budget is
  unchanged. Everything below shipped in 0.7.
- **A review rollup gets no plan hunter** (the owner's go, 2026-10-24, item 4 option A). The trial project's review rollup, the
  feature review's findings, took three hunter plan rounds before its fix could start, and the round cap landed on the
  owner. `reef-adversarial` `plan_pass_tiers` returns no tier for a rollup file (`R<NN>-…`), so the guard does not
  require its plan pass, and the plan check's hunter line skips it; reef-review says the feature's guard pass (4b) reads
  the rollup's diff before GREEN. tests/size-budget.json raised: `prose_words` 19,592 → 19,612, `script_lines` 11,782 → 11,788.
- **The guard refuses a hunter round above the cap before it runs** (the owner's go, 2026-10-24). `reef-adversarial`
  refused a plan report above `hunter.plan_rounds` only after the round had been dispatched and paid for. A plan-pass
  hunter's prompt now carries `pass=plan round=<n>` (the plan skill says so), and the guard refuses the dispatch when
  n is above the main checkout's cap, pointing to the owner's gate. A tripwire: the round is the orchestrator's label.
  tests/size-budget.json raised: `prose_words` 19,567 → 19,592, `script_lines` 11,770 → 11,782.
- **A dispatch marks the plan's own copy of a task** (the owner's go, 2026-10-24). The trial project's re-dispatch of a task named
  the task file inside its task worktree, so the guard and the graph runner marked that copy in-progress; the feature
  worktree's copy, which the tick reads, stayed pending, so the tick offered the task again after it was built, and the two
  copies' edits stood in the way of the merge. `reef-graph.py` `plan_home` resolves a task worktree's path to the same
  file in its feature worktree; the guard runs every dispatch check on that copy and marks it, and so does the graph
  runner. tests/size-budget.json raised: `script_lines` 11,733 → 11,770.
- **`--help` is never data** (the owner's go, 2026-10-24). The trial project's loop ran `reef-queue.py footnote --help` and got a
  footnote reading "--help", three times; `note -h` would write a note and `add-row --item --help` a row, and
  `reef-loop.py wait --help` would record "--help" as the loop's wait. `reef-queue.py`, `reef-loop.py` and
  `reef-record` now print their usage on `-h`/`--help` anywhere in the arguments and write nothing. The other
  scripts only read, or refuse a missing file. tests/size-budget.json raised: `script_lines` 11,724 → 11,733.
- **The docs say how the night works now** (the owner's go, 2026-10-24). The README, the site and the Arabic manual
  still told the owner to start the night by hand in a terminal. All three now say: `/reef-night` starts the runner
  itself, detached; `reef-run.py status` follows it; the contract's rows default to every ready row, found ones
  too; preview looks are Mahmoud's by default unless a footnote keeps one; an approval holds 16 hours (a new stops
  row for the refusal); a night draws on a subscription's usage, the logged cost is the API-price equivalent, not a
  bill, and `caps.batch_tokens` caps it. Docs only; budget unchanged.
- **`/reef-night` starts the night itself** (the owner's go, 2026-10-24: "why don't I have /reef-night instead of a
  manual thing in the terminal?"). `reef-run.py --detach` runs every check first (a refusal prints to the caller),
  then leaves the session that started it (fork, `setsid`, fork; output to `.reef/run/runner.out`) and returns the
  runner's pid, so the runner outlives that Claude session or terminal; `reef-run.py status` shows running or not,
  the night, the last steps and the last session, from anywhere. The night skill runs `--night --detach` on the
  owner's Approve and hands over. One orchestrator: the runner's sessions carry `REEF_RUNNER`, and while a live runner
  holds the lock the Stop hook no longer demands that any other session dispatch the ready work. Proved live: a real
  `claude -p` session in auto mode ran the command and exited after 13 s, and the runner worked on. tests/size-budget.json
  raised: `prose_words` 19,508 → 19,567, `script_lines` 11,656 → 11,724.
- **A night drives every ready row of the batch, found ones too** (the owner's go, 2026-10-23). Queue rule 1, a
  planned row before a found one, made `reef-queue.py ready` hide every found row while a planned one was ready: the
  tick never offered a found row, the trial project's 89 found rows waited, and a night with its planned rows blocked had
  nothing to do. Now `ready --with-found` lists every ready row, planned first; at night (`.reef/night/active`) the
  tick uses it and keeps only the contract's `Rows:`, so found rows the contract names move and nothing outside it
  does; `reef-run.py contract` warns of a ready row the contract leaves out; the night skill drafts `Rows:` from it by
  default. By day rule 1 is unchanged. tests/size-budget.json raised: `prose_words` 19,458 → 19,508, `script_lines`
  11,631 → 11,656.
- **One odd stream event no longer kills the runner** (2026-10-23, the trial project's night: `AttributeError: 'str' object
  has no attribute 'get'` in `steps`, two minutes in; the runner died and its headless session ran on unwatched,
  with no night marker, so Mahmoud's approvals would be refused). `steps` skips a `message` or a content entry that
  is not an object, and the session loop turns any parse error into one live line instead of dying, on Claude Code
  and OpenCode. tests/size-budget.json raised: `script_lines` 11,620 → 11,631.
- **Mahmoud approves a preview look at night by default** (the owner's go, 2026-10-23: "not a night mode, a lot
  of intervention"). Every trial project night kept the look for the owner, since the project's AGENTS.md says "the look
  of his own product", and a row blocked on a look waited all night. The night skill now delegates a preview look by
  default (the approved contract is the owner delegating it); Mahmoud judges it from the preview's code against the
  spec, the footnotes and the profile, it is written as his footnote, and the owner undoes it by editing that
  footnote. A footnote or profile line keeping a named look still holds it back. tests/size-budget.json raised:
  `prose_words` 19,349 → 19,458.
- **A project carries `scripts/reef-approval.py`** (the owner's go, 2026-10-23). The night prompt tells the
  orchestrator to record Mahmoud's plan approval with `python3 scripts/reef-approval.py --proxy`, but reef-init never
  copied that script into a project: the trial project's night contract had to name the plugin's copy, and without it the found
  rows would have stopped at approval. reef-init now copies it (the hook still runs the plugin's copy), and the test
  that every project path a skill names is copied also reads the runner's prompts. tests/size-budget.json raised:
  `script_lines` 11,618 → 11,620.
- **The docs for two hosts, step B** (the owner's go, 2026-10-23). The README's Hosts table fills OpenCode's column:
  status "early: built and verified live; no feature built on it yet", the install (`reef-init.py --root .`, then
  `reef-opencode.py install`), `provider/model` roles, the plugin guard, a new row for plan and night approval (the
  owner's `reef-approval.py --owner`), the runner's `--host opencode`; the ledger's `portable` now names the adapter.
  The site and the Arabic manual say the same, and the manual's install step gains the OpenCode commands. Both
  plans mark the step done. Cut: the site's host switch on the install box (the Hosts table already shows both).
  Docs only; budget unchanged.
- **The runner drives OpenCode** (the owner's go, 2026-10-23; portability phase 2, part 2). `reef-run.py --host
  opencode` runs each session as `opencode run --format json --command reef-loop <the runner's guidance>`; its live
  lines come from OpenCode's events (a `task` call arrives once, completed, with the sub-agent's verdict; the
  orchestrator's words; a decision or merge command), its cost from the summed `step_finish` costs, its session id
  from the events. The probe and its gate are per host (`probe --host opencode`), so a Claude Code GATE OK never lets
  OpenCode loop; the waiting line names the host to answer in. Verified live on OpenCode 1.19.3: GATE OK, and one
  `/reef-loop` iteration that ended in an honest owner wait (`docs/perf/opencode-e2e-2026-10-23.md`).
  tests/size-budget.json raised: `script_lines` 11,559 → 11,618.
- **Reef installs into OpenCode** (the owner's go, 2026-10-23: "work on finalizing open code"; portability phase 2,
  part 1). `scripts/reef-opencode.py install` writes `.opencode/`: the guard plugin (caller from `chat.params`, the
  normalized input of #93, any non-zero exit or a timeout blocks, a tool not known to be read-only goes to the guard),
  `reef:<name>` agents from `agents/*.md` with `roles.<role>` as their model and `edit: deny` on every judge, links to
  the skills, `/reef-*` commands, and host notes read through `opencode.json` `instructions`. It warns on a role that is
  no provider/model id and on a tier table that varies a role's model (one agent file, one model). The plugin lives
  inside the script so the size budget and the code-needs-a-test check see it. Where no approval hook exists the owner
  approves in their own terminal: `reef-approval.py --owner "Approve plan <slug> at <digest16>?"` (or the night
  question) takes the hook's own path. And a hole closed on both hosts: piping a made-up answered question into
  `reef-approval.py` approved a plan, and the guard let any agent run it; now an agent runs it only with `--proxy`.
  The host notes give a judge's scratch by its literal path: a live run's `mkdir -p $TMPDIR/opencode/reef` was
  refused, since the guard cannot read a variable. tests/size-budget.json raised: `script_lines` 11,334 → 11,559 (the
  installer and plugin 197, the owner command and guard rule 28).
- **A night contract is for one night** (the owner's go, 2026-10-21). `reef-run.py --night` checked only the
  contract's digest: last night's approval (two rows, both closed since) still passed at 21:23, and the night ran
  one 29-second session and waited. `night_ok`, used by the runner and by the proxy's approval, now also refuses an
  approval older than 16 hours ("another night's") and a contract none of whose rows is open in the queue; both say
  "run /reef-night for tonight". The 16 hours run from the owner's approval, so a contract approved in the afternoon
  covers a night until the next morning. tests/size-budget.json raised: `script_lines` 11,305 → 11,334.
- **The hunter's round cap stops rounds, not passes** (the owner's go, 2026-10-21: "fix why this hunter thing keeps
  coming"). the trial project's review rollup passed the hunter on round 3 and `reef-adversarial` refused to record it above
  `hunter.plan_rounds` 2; the cap's own message pointed to `--decided`, which refused a plan the hunter had never
  passed; the only exit was a config change the guard rightly keeps from the loop, so it landed on the owner. A FAIL
  was already refused at every round, so the cap check could only ever discard a PASS. Now: a PASS is recorded at any
  round (with a notice above the cap); a FAIL at or above the cap gets the cap message, the owner's decision at the
  gate; `--decided` on a plan the hunter never passed needs the owner's ruling as a footnote in the main checkout's
  queue (with a pass on record it works as before). The cap's meaning moves from "no record above the cap" to "no
  further round after a FAIL at the cap". Not changed: the guard still lets a hunter round above the cap be
  dispatched. tests/size-budget.json raised: `script_lines` 11,283 → 11,305.
- **`reef-update --commit` commits what reef-init rewrote in place** (the owner's go, 2026-10-21). The trial project's update
  rewrote AGENTS.md with the bullets rule (Reef's untouched rendering, updated in place) and committed only the
  manifest and the scripts; AGENTS.md sat modified. The commit now also takes a tracked managed file whose manifest
  entry reef-init moved, when it had no uncommitted change before the run: never a new file, never an owner's edit.
  The printed accept line named `scripts/reef-init.py`, which a project does not carry; it now names the plugin's
  `reef-init.py --root <repo>`. tests/size-budget.json raised: `script_lines` 11,266 → 11,283.
- **A judge's scratchpad under `~/.claude/jobs/<id>/tmp` is scratch** (the owner's go, 2026-10-21). The trial
  project's session put its scratchpad there; the guard took only `/tmp`, `/private/tmp` and `/var/folders` as scratch, so the
  plan reviewer's report was refused as a project write twice and the orchestrator copied it out of the reviewer's
  transcript. `is_scratch` now also takes `~/.claude/jobs/<id>/tmp/`; the rest of `~/.claude` and a `..` out of it
  stay writes. tests/size-budget.json raised: `script_lines` 11,264 → 11,266.
- **The hunter's round cap has one home** (the owner's go, 2026-10-21). `hunter.plan_rounds` was read from the
  config nearest the task file, and a plan's task file lives in its feature worktree, whose copy of the config kept
  the old cap: a row's loop asked the owner to raise it in two files. `reef-adversarial` now reads it from the main
  checkout, through one `policy_config` shared with `hunter.guard_pass` (which already did), so the README's claim
  that `hunter.*` is read from the main checkout holds. tests/size-budget.json lowered: `script_lines` 11,269 → 11,264.
- **Bullets, not paragraphs** (the owner's go, 2026-10-21: "the planning, spec, queue write-up is too big … be
  concise even if you sacrifice grammar"). The seven agents that write English (implementer, verifier, hunter,
  plan reviewer, planner, security, Mahmoud) carry one rule beside the Terse rule: every file they write is one fact
  per bullet, fragments over sentences, grammar optional, nothing restated; the structured lines the scripts parse
  (`RUN:`, `RULE AC<n>`, `VERDICT`, Proof rows, frontmatter) stay exact. The AGENTS.md template says the same for
  the orchestrator's queue rows, journal entries and handoff, keeping the owner's footnotes verbatim; the spec and
  task templates ask for bullets instead of "two or three sentences" and "one paragraph". The mechanic writes no
  prose and is unchanged. A project whose AGENTS.md differs from the rendering gets it as a proposal to accept.
  Also the test for the loop merge's bare command (`ReviewSkill`), whose reef-review line was committed on GitHub
  at 848ef47 without a test or a budget raise; main's size test was red from that commit until this PR.
  tests/size-budget.json raised: `prose_words` 18,952 → 19,349 (this rule 315, the reef-review line 82).
- **The docs for two hosts, step A** (the owner's go, 2026-10-21; `docs/design/docs-two-hosts-plan.md`). Host facts
  have one home: the README's new `## Hosts` table, Claude Code supported and OpenCode planned, not built. The site
  reads that table at page load like the Settings table (a Hosts section and nav link; with the fetch failing it links
  the README); the Arabic manual's install step links it. The honesty ledger gains a Host column: `portable` when a
  script, git or the guard's checks enforce the rule, `Claude Code` for the six rules that need a hook event only
  Claude Code sends (the missing-dispatch Stop check, the tier's model per dispatch, the plan approval capture, the
  context ceiling, the away report, the session-start budget). Host-specific steps say the step and name Claude
  Code's command in brackets ("start a fresh session (`/clear` in Claude Code)"). Docs only; budget unchanged.
- **OpenCode probe passed** (phase 0, 2026-10-21; `docs/perf/opencode-probe-2026-10-21.md`). OpenCode 1.19.3 in a
  scratch repository, a throwaway plugin feeding the guard's normalized input: the guard refused a verifier
  subagent's `git commit` and allowed the main agent's `git status`. The plugin learns the caller from `chat.params`,
  since `tool.execute.before` carries only a session id. OpenCode stays "planned" in the hosts table until the
  adapter is built.
- **The guard takes another host's input, and the caller is required** (the owner's go, 2026-10-21: Reef beyond
  Claude Code, phase 1 of `docs/design/portability-plan.md`). An adapter for another host sends one normalized input
  (`reef_host`, `tool`: shell/write/edit/dispatch, `agent`, `cwd`, the tool's fields); the guard translates it to the
  payload its checks already read, so there is no second check path. Without `agent` the input is refused: a missing
  caller would make every call the main session's, and a judge's write would pass the reviewer lock unseen. An
  unmapped tool is refused too. The Claude Code path is unchanged. Role aliases, also in the go, moved to phase 2:
  on Claude Code they needed resolving in the guard, `reef-attempt`, the plan check and five skills' prose for no
  gain until a second host exists. tests/size-budget.json raised: `script_lines` 11,243 → 11,269.
- **The guard's context warning no longer approves a dispatch** (the owner's go, 2026-10-21). Between
  `caps.context_warn` and the ceiling the guard warned the model on an agent dispatch and also answered
  `permissionDecision: allow`, which approved the dispatch past the session's own permission checks. It now adds
  only the warning text. Found while tracing a loop merge, refused by auto mode as self-approval (that one is
  the owner's permission rule, not a guard change). Budget unchanged.
- **No finding left unfiled, no result typed by hand** (the owner's go after an audit, 2026-10-21). In graph mode
  `settle` read the hunter's report and printed only READY/FAIL — its NEW-ROW and NOTED lines reached no one; settle
  now prints each, with the command that files it. The release security pass filed its BLOCKERs and HIGHs only; each of
  its `NEW-ROW`s now becomes a found row (a security finding is never a note). `settle` takes the completion notice's
  output file as it is (`{"result": …}`) and refuses a run that ended without a result — the trial's orchestrator
  typed a results file by hand and auto mode blocked it as a possible checks bypass. /reef-graph's rule on a task the
  results omit was wrong (`generate` skips a task in flight); it now says the tick frees it after
  `loop.inflight_stale_minutes`. tests/size-budget.json raised: `prose_words` 18,884 → 18,952, `script_lines` 11,213 → 11,243.
- **A finding that may never happen is noted, not queued** (the owner's go, 2026-10-21: found rows outran their
  closing — 77 of the trial project's 82 open rows were found, 11 from one row's hunters in one night — "I'm worried we drop
  important fixes"). The hunter's NEW-ROW is now a hole that WILL happen but is not this item's (a queue row, as
  before); a hole that may never happen is `NOTED: <hole> — possible: <why> — worst case: <…>`, and an uncited finding
  is demoted to NOTED, not NEW-ROW. Anything touching security, privacy, money or data loss is always a NEW-ROW however
  unlikely. `reef-queue.py note "<finding>" --row <id>` records a note in `noted-risks.md` beside the queue and refuses
  one whose words name those classes (a backstop: class words only — "token" would make every share-link finding a
  row); `promote-note n<k>` makes one a found row and marks the note `→ row <id>`; a note is never deleted; `triage`
  counts the open notes on its head line. Filing lines in /reef-plan, /reef-task, /reef-review and reef:mahmoud. On
  last night's 11 found rows: about 4–5 of 11 would have been notes; the security, data and will-happen ones stay rows.
  tests/size-budget.json raised: `prose_words` 18,708 → 18,884, `script_lines` 11,147 → 11,213.
- **A headless session keeps its workflow alive** (the trial night, 2026-10-21; the owner's go): the session launched
  the graph for two tasks, ended its turn, and `claude -p` exited exactly ten minutes later, killing both
  implementers mid-build (Claude Code's run record: `killed`). Claude Code waits for background agents and workflows
  only 10 idle minutes after the last turn by default; the runner now starts every session with
  `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` = 3 hours (documented, Claude Code 2.1.182+; the clock restarts on every
  background result; a value the owner set wins). Verified with a real headless session whose workflow ran past ten
  minutes after its last turn. `reef-queue.py footnote` no longer adds a second date to a decision its author already
  dated (⁵⁴ read "(2026-10-21) (2026-10-21)"). tests/size-budget.json: `script_lines` 11,140 → 11,147.
- **The runner shows its progress** (the owner's go, 2026-10-21: "I cannot see any progress" through an hour of a
  silent night session). `reef-run.py` reads the session's `stream-json` events and prints one line per step: an agent
  or workflow starting (`→ Hunter 1203 plan round 2 (reef:loophole-hunter)`), its hand-back verdict (`← …: FAIL`), the
  orchestrator's own words, a decision or merge command (proxy approval, footnote, record, PR, merge, wait), each
  session's end with its time and cost; a sub-agent's own steps and other Bash calls stay out. The same lines go to
  `.reef/run/live.log` (fresh each run); `reef-run.py watch` follows it from another terminal; `.reef/status.html` gets
  a Runner section (running or not, the last ten lines), re-spliced on every step. Event shapes taken from a real
  headless session. tests/size-budget.json raised: `script_lines` 11,005 → 11,140, `prose_words` 18,693 → 18,708.
- **Night-mode fixes before the first real night** (the owner's yes, 2026-10-21): a hunter dispatched on a task no
  implementer has started (`status: pending`) is the PLAN pass, and the guard writes no `.reef/verifying/<id>` for it —
  a failed pass is never recorded, so its marker showed `in flight: verifying:1202, 1204` for hours on the trial; the
  runner counts only markers newer than `loop.inflight_stale_minutes`, the tick's own rule, so a leftover marker no
  longer stops it with "work in flight". **A personal profile** (`~/.reef/owner.md`, or `REEF_OWNER_PROFILE`):
  `reef-run.py contract` seeds a project's missing `reef/owner.md` from it, so night mode works from a project's first
  day; an existing project profile is never overwritten. tests/size-budget.json raised to `prose_words` 18,693, `script_lines` 11,005.
- **The 0.6-fingerprint compatibility code is gone** (consolidation PR C; precondition the owner's `/reef-doctor`
  on the trial, 2026-10-21: "every approval and review record in the current digest form"). Removed: `reef-plan-check.py
  --legacy-digest` and `--migrate-records`, the LEGACY branches of `--verify-stamp` (stamp, approval, review, hunter),
  `reef-adversarial <task> plan --migrate` and the 0.6 plan hash, the guard's 0.6-stamp denial, the doctor's LEGACY
  stamp and record scans (a plan check per feature on every doctor run), the tick's LEGACY holds, their docs rows and
  ten tests. A project still holding 0.6-form records re-approves its plan (no other project exists). The 0.5 layout
  support stays. tests/size-budget.json lowered: `script_lines` 11,133 → 10,980.
- **Super Reef: one delegated night under Mahmoud, the owner's proxy** (the owner's go and decisions, 2026-10-21;
  plan reviewed by the advisor). `/reef-night`: `reef:mahmoud` — chief design architect and product manager, twenty
  years, precise, concise, simple and robust — drafts the owner's profile (`reef/owner.md`, from their verbatim
  footnotes) and tonight's contract (`Rows:`, the decisions it may take, the hard limits); the owner answers ONE
  question, `Approve night <date> at <digest16>?` (the digest covers the contract AND the profile; an edit to either
  approves nothing), recorded `.reef/approvals/night.json`. `reef-run.py --night` then runs the loop: inside the contract
  Mahmoud decides; `reef-approval.py --proxy` writes his plan approval (`by: mahmoud (proxy)`) only while
  `.reef/night/active` exists (written by the runner alone), for a row the contract names (the feature's SPEC `Row:`),
  from his own report at the protected evidence path `.reef/ci-local/report-mahmoud-<slug>.md`, at the plan's current
  digest, with the plan check green; his other decisions are queue footnotes labeled `Mahmoud (proxy, night <date>):`.
  The guard protects `.reef/night/` like the approvals, refuses the release PR while a night runs, pins
  `roles.proxy` and locks Mahmoud read-only. At exit the runner writes `.reef/night/report.md`: his approvals and
  decisions (undo: delete or edit) apart from the merges (undo: `git revert -m 1`). **Mahmoud runs on Fable** — the
  owner's explicit exception to "opus for every Reef role", for this one role. The README's rule "plan approval is the
  HUMAN's" now names the delegated case. tests/size-budget.json raised: `config_keys` 88 → 89 (`roles.proxy`),
  `prose_words` 17,569 → 18,659 (the agent and the skill), `script_lines` 10,910 → 11,133.
- **`scripts/reef-run.py`, the outer runner** (usability plan B1, the owner's go 2026-10-20): `/reef-loop` in fresh
  headless sessions (`claude -p … --permission-mode auto`), one after another — at the context ceiling the next session
  re-enters from the handoff, so the owner is no longer the restart button. It stops when the loop waits on the owner
  (exit 2; their questions in `.reef/questions.md`, which the handoff already read), stops (0), parks (3), ends a session
  with work in flight (3 — a headless session waits for Bash background work, checked 2026-10-20; the Workflow tool is
  not yet proven, so the runner never starts a second copy), or reaches `--max-iterations` (4). Gated, fail closed:
  `reef-run.py probe` proves reef-guard denies a headless session's forbidden write, per permission mode. One runner per
  checkout (`.reef/run/lock`); it does not stop an interactive `/reef-loop` beside it. `/reef-loop` now grills every
  ready row of the batch in one question set before planning, and asks `.reef/questions.md` first. `reef-init` copies
  the runner and gitignores `.reef/run/` and `.reef/questions.md`. tests/size-budget.json raised: `script_lines`
  10,733 → 10,910 (the runner), `prose_words` 17,436 → 17,569.
- **The hand-back's claims list, told and recorded** (2026-10-20, the trial project, the owner's yes): the implementer's
  definition listed the hand-back's contents without the `Claims:` list the check requires, so a task's hand-back was
  rejected and graph mode counted an attempt; it now names the list and its line shape. The rejection message is true in
  both modes (chat: re-dispatch once, no attempt; graph: settle counts one), and the graph's gate step passes the
  rejection's `- ` reasons so settle records them instead of the header. tests/size-budget.json raised: `prose_words`
  17,406 → 17,436, `script_lines` 10,730 → 10,733.
- **Fix rounds run in graph mode** (2026-10-20, consolidation PR B): a task that failed once went back to the chat, one
  orchestrator turn per agent result (≈ 25 turns per round). Now the tick sends a fix round (`attempts` > 0) and a
  hand-back (`verify now`) to the graph when this machine's probe passed; `generate` gives the round-2 implementer the
  last `attempt N FAIL` line and the gate log path ("keep the rest"), and the verifier reef-attempt's `rejudge:` line
  and its round. After a rejected verifier report, or for a hand-back, it builds a judge-only pipeline: no implementer,
  no dispatch counted, and a FULL judge after a rejected report (no round-1 verdict to carry); that path still counts the
  attempt settle recorded, so a judge's formatting fault moves the cap. The saving is the round's orchestrator turns, to
  be measured on the next failing task — the trial's 170–260k failures were mostly diagnosis of Reef defects, not the
  round. tests/size-budget.json raised for this: `script_lines` 10,697 → 10,730, `prose_words` 17,314 → 17,406 (the skills,
  README, site and manual now say fix rounds run in the graph).
- **Stop the growth, remove the dead** (2026-10-20, the owner: "is Reef creating technical debt?"): `tests/size-budget.json`
  holds Reef's ceiling — template config keys, skill and agent words, script lines — and `test_contracts.py::SizeBudget`
  prints the three numbers on every run and fails when one is above it; a PR that grows Reef edits that file in the same
  diff with its reason here. Two template keys nothing read or named are gone (`writing.prompt_words`,
  `context.read_lines_max`; a project's copy is harmless). The guard enforces `roles.planner` (set everywhere, enforced
  nowhere — the brief's known gap) and `/reef-plan` passes it on the planner dispatch. The implementer, verifier and
  hunter definitions say once: redirect a test or gate to a file and read the exit code, never pipe it (63+ piped-gate
  denials across the trial, each a wasted retry turn).
- **Fix**: recording the hunter's plan pass (`reef-adversarial <task> plan <report>`, or the owner's `--decided` ruling)
  clears the `.reef/verifying/<id>` marker the guard wrote for that hunter, in the task's own checkout and only when it
  names that task file (2026-10-20, the trial project: the tick showed `in flight: verifying:<id>` for a hunter that had
  returned, until the marker went stale). A code pass keeps the orchestrator's `rm`: the verifier shares that marker.
- **The plan gate says what you are approving** (2026-10-20, the owner: "Approve plan … at bd8cd330bfb50bfd?" told them
  nothing): `reef-plan-check.py --summary --feature <slug>` prints one line — tasks, criteria, draft ADRs, and the plan
  files changed since the last recorded approval — and `/reef-plan` puts it VERBATIM under the `Approve` option and above
  the question set. The question itself is unchanged (the hook records only that exact text; the digest still binds the
  approval). `reef-approval.py` now stores `files` = {file: sha12} over the digest's own files (`--plan-files`), so the
  next gate names what moved; a record from before says "read the plan in full" instead of guessing.
- **Platforms said plainly** (2026-10-20, the owner): Reef runs on macOS or Linux; on Windows, inside WSL2. The README,
  the site and the Arabic manual say so first under "What it needs". Native Windows has no `fcntl` locks, no `SIGALRM`
  deadline and no process groups, and the guard died at its first import; it now stops inside a Reef project with that
  sentence and steps aside in any other project, and `reef-init` refuses before writing anything. (The guard's hook calls
  `python3`; a Windows Python reachable only as `python` never reaches the check, so the README is the first word.)
- **Fixes from a trial row's close** (2026-10-20, the owner's yes): (1) a rollup (`R<n>-<slug>.md`) is
  written by `reef-converge`, never planned or stamped, so the plan check keeps its schema, id and graph checks and drops
  the planner's authoring rules (Log last, a human Decision, an FR key, a test name claimed twice); converge writes a
  complete rollup (no placeholders, the feature's own slug in its Proof) and puts each dated `## Converge` section
  before `## Log` — the trial's two closed rollups failed seven rules, and a red check blocks plan approvals. (2)
  `settle` records a rejected report's reasons (the `- …` lines under `REJECTED`), not reef-claims' first line, which
  was a `note:` about word count — a task's fix round got nothing actionable. (3) each dispatchable task's
  `attempts/dispatches` counters are part of the tick's fingerprint, so a graph run that dispatched and failed a task
  between two ticks is progress, not a "no progress" park.
- **Fixes from another trial row's close** (2026-10-19, the owner's yes to both): `reef-converge` numbers a new
  rollup after the highest `R<n>` in EVERY feature folder (it counted its own folder, so one feature took `R1` beside another's and
  the tick printed BROKEN; the orchestrator renamed it by hand). `reef-update --commit` commits `.reef/config.json` with
  Reef's files when it was clean before `reef-init` ran and every value it held is unchanged after — keys added only;
  an owner's uncommitted edit, or a value `reef-init` filled, is named and left for the owner (2026-10-18: `graph.mode`
  and `gates.timeout_s` sat uncommitted after a pull, so feature branches cut from the base lacked them).
- **`/reef-pentest <url>` — the running app attacked, on demand** (2026-10-19, the owner: "the pen test as a standalone, on
  demand, at any point"): the hunter's `pass=system` was described as "once per release" and no step dispatched it. The
  new skill needs the threat model (`reef-threat.py lint` ok), starts the app if given its command, dispatches one
  `loophole-hunter` (no task line, `roles.adversary`) at the URL with the safety rules verbatim — only a target the owner
  named and owns, never production unless the owner says so for this run, never a third party's service, nothing
  destructive — keeps the report as `.reef/hunt/pentest-<date>.md` and files each hole as a `found` queue row. No
  record, no gate, not in the release step. An agent, not a scanner (scanners stay in `gates.release`). The guard's write
  detection now reads a download's output file (`curl -o/--output`, `wget -O/--output-document`) as a write, so the
  attacking judge can `curl -s` the app but not save a response into the project.
- **The release's security pass is Reef's own, and recorded** (2026-10-19, the owner: "Reef is meant for others, the security
  pass should be solid"): the step named `code-security`, an agent in the author's personal `~/.claude/agents/`; for
  anyone else it did nothing, and nothing recorded that it ran. Now `agents/security.md` (`reef:security`, read-only,
  `roles.security`, the judge lock) audits `git diff <release>...<base>` against the threat model and the constitution —
  every threat row's mitigation and proving test, isolation, fail-closed authority, secrets and personal data — then argues
  untrusted input, the authenticated attacker and the deployment surface; the scanners stay in `gates.release`.
  `reef-record security <PASS|FAIL> --report` binds the agent's own VERDICT (a PASS with a BLOCKER line is refused) to
  the head of `branches.base`, stored as `head` so it can never stand in for a feature's GREEN; the guard refuses
  `gh pr create` into `branches.release` without a PASS at that exact head.
- **Fixes from the trial's second graph-mode task** (2026-10-18): (1) `reef-graph-run settle`
  counts a red gate as the attempt — the pipeline skips the judges on a red gate, settle added "no verifier verdict" and
  that text suppressed `reef-attempt`, so the orchestrator counted by hand; the gate's failing block (300 chars) is the
  recorded failure and settle prints `attempt counted: attempt=N/cap`; a rejected hand-back on a judged task counts the
  same way now (it ended the pipeline before the judges; before, only a gate-only task's did). (2) `reef-attempt`'s `## Log` line carries the
  time (`· at <UTC>`), and the tick lists a hand-back under `verify now` only when no failure was recorded after it —
  a hand-back whose gate or judge failed goes back to `dispatch now` (a chat-mode fix round), in graph mode too.
- **A hung gate ends** (`reef-gate.sh`, `gates.timeout_s` 1200, 0 = none; 2026-10-18: a test waiting on a port it had
  leaked held vitest 21 minutes and the graph-mode workflow three hours — chat mode's Bash would have stopped at ten):
  the gate runs in its own process group under python3 and, past the limit, the group is killed, exit 124, and one
  line names the limit outside the capped failing block (a hung suite's log is hundreds of lines past its first FAIL);
  no green marker. A server a test spawned detached is outside that group and may still hold its port.
- **Fix** (`reef-c4`, 2026-10-18, the trial project): every compose service running a third-party image is a container of
  the model, proven by the compose file — the generator admitted only a fixed list of names, so the Mailpit mail catcher
  was hand-added to `workspace.dsl` and `--diff` then contradicted it; a service built from the repository or on a bare
  runtime image (the app itself) is still skipped, and a name already detected from the code is not listed twice.
- **Fix** (`reef-graph-run`, 2026-10-18, the trial's first graph-mode task): the pipeline's mechanic ran `reef-gate.sh fast`
  before the judges where chat mode runs `full`; it runs `full` now (cached when the implementer ran it on the same snapshot).
- **`graph.mode: auto`** (workflow v2 phase 4; 2026-10-18, after the trial's first graph-mode task): the tick decides the
  mode per `dispatch now` task — `dispatch (graph): <ids> — reef-graph-run.py generate` for a fresh task when this
  machine's probe recorded GATE OK (`.reef/graph/gate.json`, fail closed), `dispatch (chat): <ids> — /reef-task` for a
  fix round (`attempts` > 0; round 2 inside the graph is not designed yet), a `verify now`, or no gate; `graph.mode`
  is read from the MAIN checkout like `hunter.*` (`chat` = never, `graph` = as auto with a missing gate named BROKEN);
  `tick --json` carries `dispatch_mode`; `generate` skips a chat-mode task and refuses under `chat`.
- `docs/perf/2026-10-18.md` — batch 2 on the trial measured from the transcripts (unique API turns, never an agent's
  own report): one row by task and by agent run (≈ 25 agent runs, 34 with the review; the hunter's ~40k floor per run;
  the two 145k implementers; the orchestrator's cached reads per session equal to one implementer's), the verifier-FAIL
  drill B4a as 202 ran it on its own (hunter BLOCKER → `attempts: 1` → one-test round → PASS, the fix round re-entered
  across a `/clear`), a task's first graph-mode run with its orchestrator turns beside chat mode's, and the targets the
  0.7 defaults are judged by (≈ 11 runs per 4-task feature, a task under 80k, round 2's verifier under 40k).
- **Fix** (`reef-converge`, a feature review on the trial, 2026-10-18): a Proof cell whose vitest name starts with a runner
  word (`env defaults to …`) is a test unless what follows reads like an argument; `\|` inside a cell is a literal pipe,
  not a column break; a cell reading `superseded …` or struck through is skipped and listed, never run.
- **Fix**: `reef-snapshot.sh` re-hashes every entry's content (the scratch index is dated 1980, so git's racy check
  covers all of it) — a file rewritten within the second at the same size read as unchanged by stat alone, and the
  snapshot did not move (2026-10-18, CI: the gate-cache test; the same gap would let a judge's same-second edit pass).
- **Defaults sized like the field, the records kept** (owner's call, 2026-10-18, after a 4-task feature ran ~25 agent
  runs): the word budgets ship as `0` = off (`writing.task_words`, `handback_words`, `prompt_words`, `report_words`,
  `sentence_words`, `criterion_words`; set a number to enforce) — the only ceiling left is `caps.context_tokens`
  150k with its `dispatch_reserve`; `hunter.plan_pass: critical` (the plan hunter runs on critical plans only; design
  gets the plan reviewer; `design` restores 0.6), `hunter.guard_pass: feature`, `review.diff_review: off`
  (`review.split_lines` 4000 when on); a verifier RULE that does not cite its Proof row is a note, not a rewrite.
  Unchanged: the verifier per task with evidence per criterion, the gate, the hunter on the feature's code, the records,
  the guard, the snapshots. Every agent definition ends with the owner's terse rule: evidence not narration, one line
  per finding, the final message is the file path and the verdict.
- reef-review names where the feature's files are (`<paths.features>/<slug>/` in its worktree) so the review starts by
  reading, not by `find`; the task skill runs `worktree.setup` in the feature worktree after merging a task that changed
  `package.json`, the lockfile or `prisma/schema.prisma` (2026-10-18: a task's merge failed 28 tests on a Prisma client
  older than its migration until `npm ci`).
- **Round ≥2 judges what the round changed** (2026-10-18: a one-test fix round re-verified all 23 criteria, 31 turns,
  71k): `reef-attempt` logs the failure's words under `## Log` and, on the next dispatch, prints `rejudge: AC-n, …` —
  the criteria the failure named plus every criterion whose Proof is not a test; the verifier judges those in full and
  CARRIES the rest (its verdict line names round 1's test and the gate's exit 0 on the new snapshot); `reef-claims
  report` rejects a carried verdict without its test name and a round ≥2 report without a `GATE: … exit 0` line.
- **The gate runs once per snapshot** (2026-10-18: the same tree ran the full gate five times in one task): a green
  `reef-gate.sh` run writes `.reef/ci-local/gate-<mode>-<snapshot>.ok`; a later run on the same snapshot prints `cached`
  and exits 0; `REEF_GATE_NO_CACHE=1` forces a run, and the pre-commit always sets it (the hook trusts no marker).
- **`hunter.guard_pass` is read from the MAIN checkout's config** by `reef-attempt`, `reef-adversarial`, `reef-record` and
  the pre-commit — loop policy has one home, like the queue (2026-10-18: the owner set `feature` on develop; the feature
  worktree's copy of the config predated it, and a fix round dispatched a hunter per task again).
- The session-start text lists the files behind the tick's ids — each `dispatch now` / `verify now` task's file, its
  worktree and the hand-back and report files found in any checkout — so the fresh orchestrator reads them instead of
  searching (2026-10-18: after every `/clear` the first turn ran `find .` over the repository for the task the tick had
  just named); `tick --json` carries them under `files`.
- `reef-update` runs the new copy of itself when the pull changed it (2026-10-18: the process is the copy loaded
  before the pull, so the commit-filter fix ran old on the trial's next pull and left `.githooks/pre-commit` and
  `.gitignore` uncommitted once more); once, never a loop.
- **`hunter.guard_pass: feature`** (2026-10-18: one task's verifier and hunter cost 96k on 20 lines of code; the hunter's
  floor is ~40k per task whatever the diff): the loophole-hunter's guard pass runs ONCE on the feature's merged diff in
  `/reef-review`, before the GREEN record, instead of once per design/critical task. `reef-attempt` prints `guard-pass:
  feature` instead of the `adversary:` line (the task skill and graph-run dispatch no hunter), the pre-commit lets such a
  task close without `adversarial-guard`, `reef-adversarial --feature <slug> guard <report>` records the pass on every
  design/critical task of the feature, and `reef-record <feature> GREEN` refuses while one lacks it. Template default
  `task` (the 0.6 behaviour); set `feature` per project.
- **A task that names an external API/SDK carries its facts** (2026-10-18: the 203 implementer spent 35 of 54 turns and
  145k context on the Anthropic SDK's docs and source — model id, image limits, SDK version, structured outputs —
  because `resources: [heavy]` said nothing): `reef-plan-check` prints a WARN for a task whose text names an SDK
  package, a vendor or an `https://api.` URL while `resources:` (or `## Resources`) carries no doc URL or version;
  `plan.external_api_re` overrides the pattern; the planner clears it before returning.
- `reef-cost` keeps the standing context (the system prompt, the skill list, the environment: paid on every turn,
  recorded a few times in the transcript, never growth) out of the share table and names it on one line per item
  (2026-10-18: two prompt snapshots and three skill listings read as 55% of "the context", and the orchestrator
  reported its standing 109k as that task's cost; the task's growth was 11.5k).
- The session-start text's `next command:` is `/reef-loop` whenever the tick holds anything the loop acts on (a hand-back
  to verify, a returned-unmerged task, a held feature), not only rows, dispatches and PRs (2026-10-18: with 204 handed
  back it said `/reef-plan <row> or /reef-assess`, and the status line's `next:` echoed it after every reply).
  `reef-doctor`'s stamp lines name their checkout, and a closed feature's records are not listed.
- `reef-init` gitignores `.reef/hunt/` (the hunter's reports are evidence like `.reef/ci-local/`; the guard already
  treats them so) — the trial's `git status` carried twelve untracked hunt files since the first day.
- **Fix**: `reef-update --commit` committed the scripts and never `.reef/init-manifest.json` (2026-10-18: three pulls on
  the trial; the first `git status --porcelain` line lost its status column to the output strip, and the manifest sorts
  first), nor the `.gitignore` lines `reef-init` appends. Both are Reef's own files and ride in the `reef: scripts` commit.
- **Records written in the 0.6 digest form migrate, they are never re-asked** (2026-10-18, measured on the trial right
  after the change below: the three live features' approval and review records, and their stamps, read as STALE — a
  re-review and a re-approval of plans nobody had edited). `--verify-stamp` names a stamp, an approval or a review
  record that carries the 0.6 digest of the CURRENT plan as `LEGACY` with the one command; `reef-plan-check.py .
  --migrate-records --feature <slug>` re-digests each such record in place (date kept, `migrated_from_0_6` added),
  leaves a record matching neither form alone (the plan changed), and refuses in a checkout whose own plan-check
  lags the plugin (the guard runs that copy). `--legacy-digest` prints the 0.6 form; the tick holds such a feature
  under `awaiting:` with the command; `reef-doctor` lists them per checkout.
- **The hunter's plan pass is bound to the approval digest, not inside it** (2026-10-18, the trial project): `adversarial-plan`
  sat inside `reef-plan-check`'s digest, so `plan --decided` after Approve (the designed path for a hole open after
  round 2) and a stamp migration voided the approval of a plan nobody had edited. It is now stripped like the guard pass
  and the plan-review record; `--verify-stamp` prints a `hunter:` line per feature (OK / MISSING / STALE / LEGACY with
  the ids and the one command), the tick holds such a task under `awaiting:` with that command instead of listing it
  for a dispatch the guard then denies (202 and 203 reached the gate with stamps their review-round edits had staled;
  nothing named it until the implementer dispatch, past the round cap), and the guard's own check is unchanged.
- **A stamp written before the cut moved is migrated, not re-hunted** (2026-10-18, the trial project: after the pull the
  guard read its `adversarial-plan` as "the plan changed" and asked for a round the cap forbids — the plan was unchanged;
  the stamp was the 0.6 form that hashed the Reviewer notes). `reef-adversarial <task> plan --migrate` re-stamps only when
  the 0.6-form hash of the file still equals the stamp (the proof nothing moved), consumes no round, records no decision,
  and refuses an edited plan; the guard's denial names the command when the stamp is a 0.6 one; `reef-doctor` lists such
  stamps in every checkout with the command, and a stale stamp with its two legitimate exits.
- **Fix**: `reef-init` copies `scripts/reef-graph-run.py` (2026-10-18: `/reef-graph` on the trial found no such file —
  the script shipped, the skill ran it from the project, the SCRIPTS list never named it); a contract test now holds
  every script a skill runs from the project against that list.
- `plan.max_acs` ships as `0` (warn above 8) instead of `8`: `reef-init` merges new template keys into an existing project's config, and
  the trial's running batch holds an approved 21-criterion task that `8` would have blocked mid-flight. Set `8` at a batch boundary.
- **Fixes from the second day's live loop** (2026-10-18): `reef-adversarial`'s plan hash (the guard imports it) now cuts at
  `## Reviewer notes` like `reef-plan-check`'s digest — notes added after the hunter's pass changed the stamp and the
  orchestrator reverted the notes to match; a verifier or hunter dispatched without a `REEF-TASK:` first line is denied
  with the fix instead of "guard internal error"; a judge's `S=<scratchpad>; mkdir -p $S && cd $S && cat > f` is read
  as scratch work: a plain `NAME=path` assigned earlier in the same command stands in for `$NAME`, and a `cd /abs` in
  the same command places later relative targets; `test_graph_run` accepts macOS's `/private/var` realpath.
- **Graph mode** (workflow v2, phase 3; `/reef-graph`, `scripts/reef-graph-run.py`): the ready task graph as ONE Claude
  Code workflow — implementer → gate (`reef:mechanic`) → verifier ‖ hunter → snapshot per task, as a pipeline in fresh
  contexts — instead of one agent result per orchestrator turn. `generate` runs the worktree, `reef-attempt`, the
  in-progress status, the dispatch count and the in-flight marker (what the guard does on a chat dispatch) and writes
  `.reef/graph/run-<hash>.js`; `settle` runs the report checks and the guard-pass record on the workflow's return value,
  clears the markers and prints `READY TO MERGE` or `FAIL` (attempt counted). **Gated, fail closed**: `probe` writes a
  one-agent workflow that tries a forbidden write; `probe-check` records `GATE OK` only when reef-guard denied it and no
  file exists — otherwise graph mode stays OFF on that machine. `reef-cost` attributes a Workflow call to the tasks its
  script names (role `workflow`). `.reef/graph/` is gitignored. A spike: measure a graph-mode task against a chat-mode
  one before preferring it.
- **Ceremony sized to the row** (v2 phase 2, B7): a `found` row whose fix is one file in no risk class is one `mech`/`light`
  task — no hunter, no semantic review; the planner argues a heavier tier in one `## Decision` line. Measured per row by
  `reef-cost.py growth --feature`, target under 10k of planning.
- **One command to update, one screen to diagnose, a map on disk, a status page** (workflow v2 phase 2; usability plan
  A1, A2, A4): `scripts/reef-update.py [--commit] [--push]` pulls the plugin clone (must be on `main`, clean), refreshes
  the project with `reef-init`, lists proposals with their accept/keep commands and commits Reef's own files only;
  `scripts/reef-doctor.py` / `/reef-doctor` prints OK/WARN/FAIL lines with the fix on each (plugin branch and
  freshness, version, scripts behind the plugin in the main checkout and every worktree, the queue's one home,
  worktrees, loop state, gh, Docker, proposals); `reef-init` renders `reef/README.md` (0.5: `docs/REEF.md`) — the
  branches, worktrees, records, rendered files and the loop's state in the project's real paths; every tick writes
  `.reef/status.html` (auto-refresh 60 s: the tick, the wait or stop, the handoff's head). `.reef/status.html` and
  `.reef/cost/` are gitignored.
- **Planning cost per feature, measured** (workflow v2, phase 2): `reef-cost` splits each turn's growth equally among
  the features active in it (`share`, sums to the session) and names the part before the feature's first `REEF-TASK`
  dispatch (`planning`); dispatches per role per feature; the Stop hook records both into `.reef/cost/features.json`;
  `reef-cost.py growth --feature <slug>` sums them across sessions. The number phase 1 is judged by.
- **Workflow v2, phase 1** (`docs/design/workflow-v2.md`; 2026-10-17: three planning sessions, no code): the owner's
  gate is LAST. `/reef-plan` creates the feature worktree first, `reef:planner` drafts there, the hunter and the plan
  reviewer run in parallel on the same digest, one fix round (BLOCKING, hunter BLOCKERs, `WILL BITE`), one fresh re-check,
  then the gate; after Approve only a HALT ruling edits the plan. `reef-adversarial` enforces `hunter.plan_rounds` (2)
  and `plan --decided <mark>` re-stamps a plan the owner ruled on; `plan.max_acs` (template 8; unset = warn above 8)
  bounds a task; the tick names the machine review before the approval; the verifier and the hunter run at the same
  time on a finished task.
- **Evidence is the agent's, never the orchestrator's** (2026-10-17: a hunter report "written from the hand-back" and a
  hand-back typed "so the next session can verify it"): the guard refuses the main session writing
  `.reef/ci-local/{handback,report,hunt,plan-review}-*.md` or `.reef/hunt/*.md` by any means but `cp`/`mv` (a sub-agent,
  with an `agent_id`, writes its own); `reef-attempt` prints the `hand-back:` path; implementer, verifier, hunter and
  plan-reviewer definitions make the file the deliverable and the message its path; a missing file means resuming the
  agent, never transcribing it.
- **The tick sees in-flight work in every worktree**: `.reef/inflight/` and `.reef/verifying/` markers are read from the
  main checkout and each worktree (reef-attempt runs where the task lives; 2026-10-17: `in flight: -` while a task built).
- **`reef:planner`**: a lean agent for drafting and amending plan files (measured 2026-10-17: Reef agents start at ~7k
  context, a general-purpose agent at ~29k); it returns plan-check green. The reef-plan skill dispatches it, never
  general-purpose. Not yet in the guard's model-pin table.
- **Nothing cosmetic voids an approval, and nothing broken gets one** (2026-10-17, three planning sessions without a
  line of code): plan-review advisories go to `## Reviewer notes` in the task (right before `## Log`; outside the
  digest like the Log; only the Log may follow it; the implementer does or declines each, the verifier lists the
  rest as NITs) instead of plan edits that re-ran three hunters, three approvals and three reviews; the ADR
  `Status:` line is outside the digest (it voided two approvals); `reef-approval.py` refuses to record an approval
  while `reef-plan-check.py` fails in the plan's checkout (five long sentences surfaced after the gate).
- **Found-row triage as a command** (usability plan B5): `reef-queue.py triage` lists `found` rows still queued two
  batches after they entered, grouped by module, with rule 7's three outcomes as ONE owner question, and the open
  found-vs-planned count; `set-batch ID N` and `drop-row ID --reason` carry the answer out (deletion recorded as a
  footnote). The tick prints `stale found (rule 7): N` when there is something to ask. First full loop: 18 of 26
  open rows were `found` and no moment asked about them.
- **Fix**: the tick no longer lists a closed row as building because its SPEC sits in every feature worktree's full
  checkout ("building rows: 1, 11, 13, 2" with row 1 archived); only rows still in the queue count.
- **Cost in the record**: the Stop hook folds the session's per-task orchestrator growth into `.reef/cost/tasks.json`
  (`reef-cost.py <transcript> --record`); `reef-cost.py growth <id>` sums it over sessions for the journal's new
  `Orchestrator` column; the tick names tasks over `caps.task_growth` (template `0` = off; set it from ten measured
  tasks). First full loop: a task's cost was computed by hand from the transcript and never reached the journal.
- The status line ends with the next command: `in flight: … / waiting on: … / next: <command>`, and the Stop hook
  refuses (once per reply) a reply without it while the loop is active. First full loop: the owner asked "what do I
  run now?" after every stop while the tick already knew.
- Quiet by default: `reef-init` prints one `skipped N (…)` line (`--verbose` lists them); `reef-plan-check --quiet`
  prints FAIL/WARN and the summary only, and the plan and plan-review skills run it so. First full loop: 38 skipped
  lines per refresh, 24 OK lines per check, all read by the owner or the orchestrator.
- `docs/design/usability-autopilot-plan.md`: what first contact showed about ease of use and autopilot maturity, what
  quantum-loop, Ralph Wiggum, claude-code-harness, spec-kit, BMAD, Superpowers and Claude Code 2.1 do, and the plan in
  two tracks with a mechanism and a measure per item (external runner, progress page, `reef-update`/`/reef:doctor`,
  triage command, cost in the record, drills for the unproven paths).
- `reef-queue.py footnote "<text>" [--row ID]`, `add-row --item … [--depends …] [--source planned|found] [--batch N]
  [--admitted …]`, `set-depends ID "<ids>"`: the orchestrator's queue edits as one command each (next footnote number
  across queue and archive, dated; a found row lands in the next batch unless admitted; the shape kept). First full
  loop (2026-10-17): these were inline Python heredocs — `assistant:tool_use` was the largest Reef-attributable context
  share of the session (15%).
- Plan review: an approved plan is edited only for a BLOCKING fix, a HALT ruling or an owner decision — never cosmetics
  (two approvals were voided by an ADR status line and a sentence trim). Advisories go to the human as one list with a
  default of leave as is; only one the reviewer marks `WILL BITE` is a question. The loop plans colliding rows one at a
  time (a HALT between two plans voided both).
- Plan pass of the loophole-hunter: **two rounds at most** (pass, fix, re-check); a BLOCKER still open afterwards is a
  decision for the human in the gate's question set, never a third round (first full loop, 2026-10-17: one row took four
  rounds, planning three rows spent a whole session before any gate). The hunter writes its report to the scratchpad or
  returns it; the orchestrator records it under `.reef/ci-local/`.
- **Project files stay the project's.** The glossary is a record (write-once, like the journal). `reef-init --keep
  <path>…` marks a rendered file as the project's own (ci.yml after a feature added a service): never proposed again.
  AGENTS.md's Boundaries section is a kept block like the owner's decision points, and the first render after a block
  arrives ADOPTS the current section's text into it. First contact (2026-10-17): the refresh after the first feature
  proposed three reverts — the placeholder and the template's Boundaries line over the owner's AGENTS.md, ci.yml without
  the Postgres service a task added, the glossary without the feature's four terms.
- AGENTS.md's **Owner decision points** live in a kept block (`<!-- BEGIN:reef-owner-decisions -->`): a re-render replaces
  the block in place with the owner's current text, never with the template's placeholder (first contact, 2026-10-17).
- `reef-queue.py`: `Current batch: 2²⁶` is batch 2 — a footnote marker may ride on the line.
- Skills: **read lean** in reef-task and reef-loop (no `git diff` of code, no script source, no full reports; measured 126k
  of 150k on one 3-task feature); reef-plan never reads `reef-approval.py`; reef-review splits a diff over
  `review.split_lines` (1500) by task, and runs `worktree.setup` in the main checkout after the merge when the feature
  added dependencies.
- **A refresh never touches a record**: `reef-init` pins the project's day-zero date and its name in the manifest
  (`_init`) and renders with them; the constitution and the draft ADRs are write-once like the journal. First contact
  (2026-10-17): a plain refresh re-dated four ADRs and the constitution's "Ratified" line to today, lowercased the
  name, and staled the feature's plan review through the ADRs.
- `reef-queue.py check`: the journal's closed set of AC statuses is read from the table's ACs column only — a sentence
  like "AC-9 and AC-13 were probed" is prose (first contact: three honest entries were reworded to pass).
- `reef-converge`: a backticked Proof is a command only when it reads like one (shell operators, a flag, a path, a known
  runner); vitest/jest names with spaces are tests. `[mechanic]` rows are listed, never run. The rollup template is
  found in the plugin (`CLAUDE_PLUGIN_ROOT` or the script's own tree) or embedded — the project's copy used to crash on
  `<project>/templates/task.md`. First contact: 26 false "missing" findings, then nothing written.
- Plan check: a task file under `tasks/done/` must be `status: done` and a `status: done` file must be under `done/`
  (one fact, two homes). First contact (2026-10-17): 103 was merged into `done/` still `in-progress`; the orchestrator
  caught it by eye. The task skill also says where `git branch -d` works (the feature worktree) and when `-D` is right.
- **Opus everywhere by default**: `planner`, `plan_reviewer` and the `critical` tier's judges were `fable`; the owner set it
  aside (2026-10-17: a plan review ran 4–5 minutes on a context the project could not afford). Set a heavier model per
  project in `.reef/config.json` if wanted.
- `reef-claims.py blocking-fixed <review-report> <since-rev>`: every `path:line` the BLOCKING section cites must have
  changed since the fixes began; the plan-review skill runs it before any re-dispatch (the re-review itself stays a
  fresh-context agent). First contact: one ADR line missed cost a full review round and the round-rule stop.
- Guard: a read-only judge may run `git worktree list`, `git stash list` and `git submodule status` (reads); the other
  verbs of those commands stay denied. First contact (2026-10-17): the plan-reviewer was refused `git worktree list`.
- Tick: a ready task whose implementer handed back (`handback-<id>.md` newer than any `report-<id>.md`, in any
  checkout) is listed under **`verify now:`**, not `dispatch now:` — first contact (2026-10-17) the fresh session's tick
  said "dispatch now: 103" over a handed-back, uncommitted worktree. The task skill starts such a task at the gate.
- **Judges learn their report budget before they write**: `reef-attempt` prints `report: budget=N words, RULE lines free
  (k criteria)` and `hunter-report: budget=N words`; the task skill passes the line in the dispatch prompt; the agent
  definitions name it. `reef-claims.py report` no longer counts RULE lines (the contract's length is the plan's) and the
  budget grows 40 words per criterion past 8. First contact (2026-10-16): a 15-criterion verifier report of 1693 words
  and a hunter report of 952 were rejected against a 900 cap measured on 6–7 criteria, two rewrite rounds.
- `reef-adversarial`: `BLOCKER: none found.`, `None — …`, `no blockers here` are no blocker (only the bare word was);
  the hunter re-sent its report for wording at first contact.
- **`caps.dispatch_reserve`** (template `30000`): an implementer dispatch with less room than that left under
  `caps.context_tokens` is denied after the guard's checkpoint — a task started at 126k of 150k was split across two
  sessions; judges and mechanics stay allowed to the ceiling. The ceiling check now runs before the dispatch check, so a
  denied dispatch writes no marker.
- **The queue has one home** — `paths.queue` on `branches.base` in the main checkout. `reef-plan-check.py` fails a
  feature branch whose queue (or archive) differs from its fork point with the base; `/reef-plan` commits the grill's
  rows on the base and pushes before it creates `feat/<slug>`; a hunter's NEW-ROW goes there too. First contact
  (2026-10-16): the roadmap lived only on the first feature branch, and the tick (which reads the
  main checkout) never saw them.
- `reef-cost.py`: a **Tasks** table — per task (from the `REEF-TASK:` line of every dispatch) the main-session growth
  over its span and the dispatches per role (`implementer ×1, verifier ×2, loophole-hunter ×1`); `--format json` adds
  `tasks`. The first real execution could not say which role cost what.
- **`scripts/reef-merge-base`** (copied into projects by `reef-init`): `/reef-task` step 0 brings `branches.base` into
  the feature branch before a wave's first dispatch. A task worktree branches from the feature, so a stale `scripts/`
  there computed a different plan digest than the records carried (first contact: develop said `9bcedd14`, the
  feature's copy said `cc218e66`, the owner merged by hand and resolved two conflicts). Record files (journal, queue,
  archive, HANDOFF) keep both sides — records only grow; a code conflict aborts, names the file and is the human's
  (exit 2). `reef-plan-check.py --verify-stamp` warns when the project's copy differs from the plugin's.
  `tests/test_merge_base.py`.
- **The plan reviewer's verdict is a RECORD the guard requires.** `scripts/reef-record plan-review <slug> PASS|FAIL
  [--report FILE]` writes `.reef/review/plan-<slug>.json` bound to the plan's digest (in the main checkout, like the
  approval). `reef-plan-check.py --verify-stamp` — hence the guard at every implementer dispatch and the tick's
  `awaiting` — requires a PASS at the current digest for any feature with a task above `light`
  (`review: MISSING | STALE | FAILED | OK | not required`). The deterministic stamp alone never meant the semantic
  review passed (first contact, 2026-10-16: three reviews of one plan, none recorded; a plan edited after a PASS
  carried the same stamp). `/reef-plan-review` saves the agent's report verbatim and records the verdict.
  Upgrading a plan already reviewed: run `scripts/reef-record plan-review <slug> PASS --report <saved report>` once.
- **First execution on a real project (2026-10-16) — eight follow-ups.**
  - `reef-graph.py worktree`: a task worktree lives under the MAIN checkout's `worktree.dir`, never nested inside the
    feature worktree the task file was read from (the nested one's `.next/` was linted by the feature's commit gate).
  - `reef-loop.py tick`: only PRs whose head is under `branches.feature_prefix` (default `feat/`) are the loop's;
    Dependabot's and the owner's are counted aside (`(N other PR(s) into the base, not the loop's)`). A feature
    worktree's plan is seen from the main checkout: its ready tasks go through the same approval/stamp gate into
    `dispatch now` or `awaiting`, and its SPEC's `Row:` moves the row from "to plan" to "building" (the main
    checkout's tick said "rows to plan: 1 · tasks: none" while 101 was being built).
  - `reef-watch`: a transcript without a turn is not a session.
  - `reef-plan-check.py`: a Proof row that writes files (a redirect, `rm`/`mv`/`touch`, `.env*`, `--force`) warns
    unless tagged `[mechanic]` — the read-only verifier cannot run it; the mechanic does, verbatim.
  - `skills/reef-task`: judge reports are saved VERBATIM (a shortened report is a rejected report — six ACs lost their
    evidence that way); `[mechanic]` rows go to the mechanic, never the orchestrator; `worktree.setup` runs in the
    orchestrator's checkout before a merge commit when the task added dependencies; `git worktree prune` at close.
  - `skills/reef-plan-review`: step 0 finds the feature worktree and works there (every run tried the base first and
    failed on "no task files"); whatever it commits it pushes.
  - `agents/verifier`: the order is the contract — task file first, RULE lines and `Rules before diff: yes`, then the diff.
  - Templates: `AGENTS.md` names `.reef/` as machine state excluded from lint/format/test and gives examples for the
    owner's decision points; `day-zero.md` has the lint-ignores-`.reef/` step.
- **`reef-plan-check.py`: the hunter's guard-pass record is execution state.** `scripts/reef-adversarial … guard` writes
  `adversarial-guard:` into the task's frontmatter after the code exists; the stamp hashed it as plan content, so the
  first design-tier task to merge (101, first contact 2026-10-16) staled the stamp and the guard refused the next
  task. The key is stripped like `status`/`attempts`/`worktree`; `adversarial-plan` stays in the digest (the approved
  plan is the hunted plan). `tests/test_tiers_lock.py::GuardPassRecordDoesNotStaleTheStamp`.
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

## Before 0.7
The releases from 0.1 to 0.6.0: `docs/changelog-archive.md`.
