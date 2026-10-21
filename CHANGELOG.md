# Changelog

## 0.7 (unreleased)
- **The docs for two hosts, step A** (the owner's go, 2026-10-21; `docs/design/docs-two-hosts-plan.md`). Host facts
  have one home: the README's new `## Hosts` table, Claude Code supported and OpenCode planned, not built. The site
  reads that table at page load like the Settings table (a Hosts section and nav link; with the fetch failing it links
  the README); the Arabic manual's install step links it. The honesty ledger gains a Host column: `portable` when a
  script, git or the guard's checks enforce the rule, `Claude Code` for the six rules that need a hook event only
  Claude Code sends (the missing-dispatch Stop check, the tier's model per dispatch, the plan approval capture, the
  context ceiling, the away report, the session-start budget). Host-specific steps say the step and name Claude
  Code's command in brackets ("start a fresh session (`/clear` in Claude Code)"). Docs only; budget unchanged.
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
  only the warning text. Found while tracing row 3's loop merge, refused by auto mode as self-approval (that one is
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
  closing — 77 of qassimha's 82 open rows were found, 11 from one row's hunters in one night — "I'm worried we drop
  important fixes"). The hunter's NEW-ROW is now a hole that WILL happen but is not this item's (a queue row, as
  before); a hole that may never happen is `NOTED: <hole> — possible: <why> — worst case: <…>`, and an uncited finding
  is demoted to NOTED, not NEW-ROW. Anything touching security, privacy, money or data loss is always a NEW-ROW however
  unlikely. `reef-queue.py note "<finding>" --row <id>` records a note in `noted-risks.md` beside the queue and refuses
  one whose words name those classes (a backstop: class words only — "token" would make every share-link finding a
  row); `promote-note n<k>` makes one a found row and marks the note `→ row <id>`; a note is never deleted; `triage`
  counts the open notes on its head line. Filing lines in /reef-plan, /reef-task, /reef-review and reef:mahmoud. On
  last night's rows 78–88: about 4–5 of 11 would have been notes; the security, data and will-happen ones stay rows.
  tests/size-budget.json raised: `prose_words` 18,708 → 18,884, `script_lines` 11,147 → 11,213.
- **A headless session keeps its workflow alive** (the trial night, 2026-10-21; the owner's go): the session launched
  the graph for 1201 and 1202, ended its turn, and `claude -p` exited exactly ten minutes later, killing both
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
- **The hand-back's claims list, told and recorded** (2026-10-20, qassimha 301, the owner's yes): the implementer's
  definition listed the hand-back's contents without the `Claims:` list the check requires, so 301's hand-back was
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
  names that task file (2026-10-20, qassimha 302: the tick showed `in flight: verifying:302` for a hunter that had
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
- **Fixes from the trial's row 13** (2026-10-20, queue rows 68–70, the owner's yes): (68) a rollup (`R<n>-<slug>.md`) is
  written by `reef-converge`, never planned or stamped, so the plan check keeps its schema, id and graph checks and drops
  the planner's authoring rules (Log last, a human Decision, an FR key, a test name claimed twice); converge writes a
  complete rollup (no placeholders, the feature's own slug in its Proof) and puts each dated `## Converge` section
  before `## Log` — the trial's two closed rollups failed seven rules, and a red check blocks plan approvals. (69)
  `settle` records a rejected report's reasons (the `- …` lines under `REJECTED`), not reef-claims' first line, which
  was a `note:` about word count — 1302's fix round got nothing actionable. (70) each dispatchable task's
  `attempts/dispatches` counters are part of the tick's fingerprint, so a graph run that dispatched and failed a task
  between two ticks is progress, not a "no progress" park.
- **Fixes from the trial's row 11 close** (2026-10-19, queue row 67, the owner's yes to both): `reef-converge` numbers a new
  rollup after the highest `R<n>` in EVERY feature folder (it counted its own folder, so row 11 took `R1` beside row 2's and
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
- **Fixes from the trial's second graph-mode task** (2026-10-18, qassimha 1103, queue rows 57 and 58): (57) `reef-graph-run settle`
  counts a red gate as the attempt — the pipeline skips the judges on a red gate, settle added "no verifier verdict" and
  that text suppressed `reef-attempt`, so the orchestrator counted by hand; the gate's failing block (300 chars) is the
  recorded failure and settle prints `attempt counted: attempt=N/cap`; a rejected hand-back on a judged task counts the
  same way now (it ended the pipeline before the judges; before, only a gate-only task's did). (58) `reef-attempt`'s `## Log` line carries the
  time (`· at <UTC>`), and the tick lists a hand-back under `verify now` only when no failure was recorded after it —
  a hand-back whose gate or judge failed goes back to `dispatch now` (a chat-mode fix round), in graph mode too.
- **A hung gate ends** (`reef-gate.sh`, `gates.timeout_s` 1200, 0 = none; 2026-10-18: a test waiting on a port it had
  leaked held vitest 21 minutes and the graph-mode workflow three hours — chat mode's Bash would have stopped at ten):
  the gate runs in its own process group under python3 and, past the limit, the group is killed, exit 124, and one
  line names the limit outside the capped failing block (a hung suite's log is hundreds of lines past its first FAIL);
  no green marker. A server a test spawned detached is outside that group and may still hold its port.
- **Fix** (`reef-c4`, 2026-10-18, qassimha task 1102): every compose service running a third-party image is a container of
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
  own report): row 2 by task and by agent run (≈ 25 agent runs, 34 with the review; the hunter's ~40k floor per run;
  the two 145k implementers; the orchestrator's cached reads per session equal to one implementer's), the verifier-FAIL
  drill B4a as 202 ran it on its own (hunter BLOCKER → `attempts: 1` → one-test round → PASS, the fix round re-entered
  across a `/clear`), task 1102's first graph-mode run with its orchestrator turns beside chat mode's, and the targets the
  0.7 defaults are judged by (≈ 11 runs per 4-task feature, a task under 80k, round 2's verifier under 40k).
- **Fix** (`reef-converge`, row 2's review on the trial, 2026-10-18): a Proof cell whose vitest name starts with a runner
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
  `package.json`, the lockfile or `prisma/schema.prisma` (2026-10-18: 202's merge failed 28 tests on a Prisma client
  older than its migration until `npm ci`).
- **Round ≥2 judges what the round changed** (2026-10-18: 202's one-test fix round re-verified all 23 criteria, 31 turns,
  71k): `reef-attempt` logs the failure's words under `## Log` and, on the next dispatch, prints `rejudge: AC-n, …` —
  the criteria the failure named plus every criterion whose Proof is not a test; the verifier judges those in full and
  CARRIES the rest (its verdict line names round 1's test and the gate's exit 0 on the new snapshot); `reef-claims
  report` rejects a carried verdict without its test name and a round ≥2 report without a `GATE: … exit 0` line.
- **The gate runs once per snapshot** (2026-10-18: the same tree ran the full gate five times in one task): a green
  `reef-gate.sh` run writes `.reef/ci-local/gate-<mode>-<snapshot>.ok`; a later run on the same snapshot prints `cached`
  and exits 0; `REEF_GATE_NO_CACHE=1` forces a run, and the pre-commit always sets it (the hook trusts no marker).
- **`hunter.guard_pass` is read from the MAIN checkout's config** by `reef-attempt`, `reef-adversarial`, `reef-record` and
  the pre-commit — loop policy has one home, like the queue (2026-10-18: the owner set `feature` on develop; the feature
  worktree's copy of the config predated it, and 202's fix round dispatched a hunter per task again).
- The session-start text lists the files behind the tick's ids — each `dispatch now` / `verify now` task's file, its
  worktree and the hand-back and report files found in any checkout — so the fresh orchestrator reads them instead of
  searching (2026-10-18: after every `/clear` the first turn ran `find .` over the repository for the task the tick had
  just named); `tick --json` carries them under `files`.
- `reef-update` runs the new copy of itself when the pull changed it (2026-10-18: the process is the copy loaded
  before the pull, so the commit-filter fix ran old on the trial's next pull and left `.githooks/pre-commit` and
  `.gitignore` uncommitted once more); once, never a loop.
- **`hunter.guard_pass: feature`** (2026-10-18: task 204's verifier and hunter cost 96k on 20 lines of code; the hunter's
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
  reported its standing 109k as task 204's cost; the task's growth was 11.5k).
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
- **The hunter's plan pass is bound to the approval digest, not inside it** (2026-10-18, qassimha): `adversarial-plan`
  sat inside `reef-plan-check`'s digest, so `plan --decided` after Approve (the designed path for a hole open after
  round 2) and a stamp migration voided the approval of a plan nobody had edited. It is now stripped like the guard pass
  and the plan-review record; `--verify-stamp` prints a `hunter:` line per feature (OK / MISSING / STALE / LEGACY with
  the ids and the one command), the tick holds such a task under `awaiting:` with that command instead of listing it
  for a dispatch the guard then denies (202 and 203 reached the gate with stamps their review-round edits had staled;
  nothing named it until the implementer dispatch, past the round cap), and the guard's own check is unchanged.
- **A stamp written before the cut moved is migrated, not re-hunted** (2026-10-18, qassimha task 204: after the pull the
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
  1101 hand-back typed "so the next session can verify it"): the guard refuses the main session writing
  `.reef/ci-local/{handback,report,hunt,plan-review}-*.md` or `.reef/hunt/*.md` by any means but `cp`/`mv` (a sub-agent,
  with an `agent_id`, writes its own); `reef-attempt` prints the `hand-back:` path; implementer, verifier, hunter and
  plan-reviewer definitions make the file the deliverable and the message its path; a missing file means resuming the
  agent, never transcribing it.
- **The tick sees in-flight work in every worktree**: `.reef/inflight/` and `.reef/verifying/` markers are read from the
  main checkout and each worktree (reef-attempt runs where the task lives; 2026-10-17: `in flight: -` while 1101 built).
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
  the Postgres service task 103 added, the glossary without the feature's four terms.
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
  (2026-10-16): the roadmap, rows 2–15, lived only on `feat/receipt-upload-skeleton`, and the tick (which reads the
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
- **First execution on a real project (101 of qassimha, 2026-10-16) — eight follow-ups.**
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
