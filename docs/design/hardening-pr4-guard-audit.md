# Hardening PR-4: the guard audit — WALL or AUTHORITY (plan only)

Status: **plan, no code.** Owner's brief: "classify every guard rule as WALL or AUTHORITY; propose WALLs as Claude Code
sandbox + permission-deny config (`failIfUnavailable: true`)." Base: `main` at `ac377d8` (PR-1..3 merged, #372–#374).
Every row cites `scripts/reef-guard.py:<line>` at that commit. Every config claim cites the Claude Code docs as fetched on
2026-11-15 (section 6). No file under `scripts/`, `hooks/` or `tests/` changes in this PR.

## 1. Verdict first

- **The guard is almost entirely AUTHORITY.** Of 74 refusals, 8 can be held *in part* by harness config. **None** can
  be held *in full* (the guard's rule stays exactly as strong without it). The guard has to stay. It cannot shrink to a config
  file.
- **The real value of the config is three things the guard cannot do for itself.** (a) It stays in force when the guard does
  not run (no python3, a crashed hook, a host without hooks). (b) It holds against any process. The guard only parses command
  text. (c) It can lock the **guard's own trust root**: the plugin install directory, which today no rule protects (W1). It can
  also lock the settings file that holds the walls (W2).
- **`sandbox.failIfUnavailable` exists and does what the owner thinks, with one stated exception: it does not apply "in an
  Anthropic-hosted environment".** The sandbox covers **shell commands only**. Edit/Write are held by `permissions.deny`, not
  the sandbox. A plugin **cannot ship** `permissions` or `sandbox`, so `/reef-init` must write them into the project's
  `.claude/settings.json`.
- **Turning the sandbox on has a cost the brief does not name.** Network isolation comes with it ("your allowed domains start
  empty"), and it cannot tell Reef's own record writers from an agent's `echo >`. So the sandbox walls in section 4 are the ones
  no Reef script needs to cross. The record folders keep their Bash rule in the guard.
- **Recommendation:** ship W1–W8 (section 4) as project settings written by `reef-init`. **Keep every guard check** (defense in
  depth, the table says why for each one). Add `.claude/settings.json` to the guard's protected files. Migrate in four
  commits (section 8).

## 2. Definitions (refined)

- **WALL**: a constraint with no state, that the **harness itself** enforces whoever asks, even if `reef-guard.py` never runs.
  Examples: a path no tool may write, a command form that may not run, a network host. "Harness" means Claude Code's
  `permissions.deny` (all tools, every mode) or its `sandbox` (OS-level, Bash and its children).
  - **full WALL**: the config holds every case the guard's rule holds.
  - **partial WALL**: config holds the common or the OS-level case. The guard keeps the rest (pattern bypasses, legitimate
    writers the config cannot tell apart, an exception that depends on state).
- **AUTHORITY**: depends on state, identity, records or judgment, so it must stay in the guard. Examples: approval records,
  digests, caps, the dispatch model, dead-ends and lessons content, "is this a Reef project", "who is calling", "is a critical
  task in flight". Two kinds:
  - **A-state**: reads records, config, markers, the forge, or the caller's identity.
  - **A-parse**: has no state, but only the guard's own shell parse can see it. Examples: pipe context, a flag inside a bundle,
    an inline program's text, a heredoc. `permissions.deny` cannot express these. The docs say Bash rules "[aren't] a security
    boundary around the program" (section 6, Q3).
- **INFRA**: the guard's own fail-closed plumbing (deadline, internal error, unparseable input). These are not policy, so they
  are not classified.

The owner's binary holds. Every rule is a WALL (full or partial) or an AUTHORITY. The sub-labels only say *why* a rule stays
in the guard.

## 3. Inventory — every refusal

Columns: **id** · **refuses** · **where** · **test** · **class** · **why**. "Test" is the first test that asserts the refusal,
found by grep. "no direct test found" means grep found none, and the code PR should add one (section 9, T0).

### 3.1 The hook layer (`hooks/hooks.json`)

| id | refuses | where | test | class | why |
|---|---|---|---|---|---|
| H1 | Bash with **no python3**: any command whose text matches `no-?verify\|hookspath` (degraded grep) | `hooks/hooks.json:11` | `tests/test_hooks.sh:255` (innocent allowed; the deny case: no direct test found) | partial WALL (W7) | A text grep with no state. W7's deny rules hold the main forms when python3 is missing |
| H2 | Task/Agent with **no python3**: every dispatch | `hooks/hooks.json:22` | `tests/test_hooks.sh:253` | AUTHORITY (A-state) | Fails closed so the dispatch checks (3.6) cannot be skipped. Config has no notion of "the check ran" |
| H3 | Edit/Write/MultiEdit with **no python3**: **nothing**. The hook `exit 0`s, so it **fails open** | `hooks/hooks.json:33` | `tests/test_hooks.sh` (no Edit no-python case found) | — (gap) | Without python3 every Edit rule in 3.3–3.4 is off. W1–W5 close the path-shaped part of this gap |
| H4 | `onFailure: "block"` on the three PreToolUse matchers; `"continue"` on Stop, PostToolUse, SessionStart | `hooks/hooks.json:10,21,32` | `tests/test_tiers_lock.py:665` | — | Host plumbing, not a rule. Docs (Q7): a hook with `onFailure: "block"` blocks on a non-zero exit or a timeout |

The PostToolUse `AskUserQuestion` hook (`scripts/reef-approval.py`) and the SessionStart tick write records and context. They
refuse no tool call. They are record **writers**, not rules, and they run outside the sandbox (Q6), so W-config never touches
them.

### 3.2 Bash: gate bypasses (machine-wide, no Reef project needed)

| id | refuses | where | test | class | why |
|---|---|---|---|---|---|
| B1 | env assignment that smuggles hooksPath (`GIT_CONFIG_KEY_0=core.hooksPath`) | `check_segment` `:942` | `tests/test_guard.py:247` (DENY table `:58`, `:75`) | partial WALL (W7) | `Bash(GIT_CONFIG_* git *)`-style rules miss `export` and a variable set earlier. Docs: a rule "matches past any leading assignment" but not other forms |
| B2 | `git -c core.hooksPath=…`, `-ccore.hookspath`, `--config-env …hookspath`, `--x=…hookspath` | `check_git` `:1341,1344,1348,1352` | `tests/test_guard.py:247` (`:49,54,71,72`) | partial WALL (W7) | Case games and `-C . -c …` defeat a pattern. Docs: `Bash(git push *)` "does not stop `git -C . push`" |
| B3 | `git commit --no-verify` / `-n` / a bundled `-anm` | `check_git` `:1365` | `tests/test_guard.py:247` (`:47,48,53`) | partial WALL (W7) | A bundled flag can't be told apart from `-m "…n…"` by `*` ("`*` matches any text, including spaces") |
| B4 | `git merge --no-verify` | `check_git` `:1371` | `tests/test_guard.py:247` (`:60`) | partial WALL (W7) | Same as B3 |
| B5 | `git push --no-verify` **when `.githooks/pre-push` exists** | `check_git` `:1375` | `tests/test_guard.py:234` | partial WALL (W7) | The condition reads a file. Denying the long form always is stricter, and acceptable: Reef never needs it |
| B6 | `git stash` (bare/push/pop/apply/drop…), list/show allowed | `check_git` `:1379,1388` | `tests/test_guard.py:247` (`:90–94`) | partial WALL (W7) | Deny rules can't carve an exception ("An allow rule can't carve an exception out of a deny rule"), so each verb is listed. `git -C x stash` is missed |
| B7 | `git config --unset core.hooksPath`; `core.hooksPath <v>` with `v ≠ .githooks` | `check_git_config` `:1409,1419` | `tests/test_guard.py:247` (`:50,55–57`); read allowed `:1500` | partial WALL (W7) | "Any value but `.githooks`" has no deny form. W7 denies `--unset` and `/`-rooted values only |
| B8 | `rm/mv/unlink/truncate/shred` on `.githooks/…` or `.git/hooks/…` | `check_segment` `:967` | `tests/test_guard.py:247` (`:61,62`) | partial WALL (W3 + W4) | `.git/hooks/` → **sandbox denyWrite holds it for any process** (W3). `.githooks/` → only the Edit route (W4), because reef-init/update write it via Bash |
| B9 | `chmod` on hook files other than a pure `+x` add | `check_chmod` `:1330` | `tests/test_guard.py:247` (`:63,64,77,78,88`) | partial WALL (W3) | Same split as B8. chmod is a metadata write, which the sandbox blocks under denyWrite on `.git/hooks` (verify in T3) |
| B10 | a **gate piped** into another command without `pipefail` | `check_segment` `:956` | `tests/test_guard.py:247` (`:95–105`), `:210` | AUTHORITY (A-parse, A-state) | Needs the pipe context **and** `.reef/config.json` `gates.*`. Bash rules match each subcommand on its own |

### 3.3 Bash and Edit: Reef's records, the handoff, the evidence

| id | refuses | where | test | class | why |
|---|---|---|---|---|---|
| R1 | Bash write into `.reef/{approvals,review,night,evidence,run/jobs}/` or `.reef/graph/gate.json` (in a Reef project) | `check_record_dirs` `:531` | `tests/test_guard.py:1218` | AUTHORITY (A-state: writer identity) | The **legitimate writers are Bash commands too**: `reef-record`, `reef-approval.py --proxy`, `reef-run.py`, `reef-gate.sh`. Sandbox denyWrite applies to "child processes" and would block them. `excludedCommands` matches a name, which a copy can wear (the reason for RW1) |
| R2 | Edit/Write/MultiEdit into the same record paths | `check_edit` `:1963` | `tests/test_guard.py:1218`; `tests/test_night.py:205` | **partial WALL (W5)** | No script writes records with the Edit tool, so `Edit(…)` deny is safe. The guard keeps the reach rule and the realpath/case games (`re.I`, `:111`) |
| R3 | copy/sync a records folder into `.reef/` | `check_record_dirs` `:552` | `tests/test_guard.py:1218` | AUTHORITY (A-state) | Same writers problem as R1 |
| R4 | `tar -C .reef` unpack | `:556` | `tests/test_guard.py:1218` | AUTHORITY (A-parse) | Same |
| R5 | `rm` of `.reef/` whole | `:558` | `tests/test_guard.py:1218` | AUTHORITY (A-parse) | Same |
| R6 | `find … -delete` over `.reef/` records | `:560` | `tests/test_guard.py:1218` | AUTHORITY (A-parse) | Same |
| R7 | `git clean` over `.reef/` records | `:562` | `tests/test_guard.py:1218` | AUTHORITY (A-parse) | Same |
| R8 | project `HANDOFF.md` by Bash | `check_record_dirs` `:549` | `tests/test_guard.py:991` | AUTHORITY (A-state) | `reef-handoff --write` (Bash) is the writer |
| R9 | project `HANDOFF.md` by Edit/Write | `check_edit` `:1973` | `tests/test_guard.py:991` | **partial WALL (W5)** | `Edit(/HANDOFF.md)` holds the root copy. The guard keeps the "roots and cwd" rule (`is_project_handoff` `:511`) |
| E1 | **main session** writes an agent's evidence (`.reef/ci-local/{handback,report,hunt}-*.md`, `.reef/hunt/*.md`), Bash | `check_evidence_authoring` `:579` | `tests/test_guard.py:1263` | AUTHORITY (A-state: identity) | The agent may write it, the main session may not. Settings apply to the whole session, sub-agents included |
| E2 | main session copies evidence from outside a scratchpad | `:577` | `tests/test_guard.py:1263`; `tests/test_day_proxy.py:178` | AUTHORITY (A-state) | Judges the copy's source |
| E3 | main session Edit/Write of evidence | `check_edit` `:1967` | `tests/test_guard.py:1263` | AUTHORITY (A-state) | Identity |
| Q1 | a sub-agent Edits `docs/queue.md` (or its archive, or `paths.queue`) | `check_edit` `:1971` | no direct test found | AUTHORITY (A-state) | Identity plus a configured path |

### 3.4 The guard guards itself

| id | refuses | where | test | class | why |
|---|---|---|---|---|---|
| G1 | Bash write to `scripts/reef*`, `.githooks/*`, `hooks/hooks.json`, `.reef/config.json` of a Reef project | `check_guard_files` `:782` | `tests/test_guard.py:1203`, `:107–111` | AUTHORITY (A-state) | Allowed under a **tier: critical task in flight** or in Reef's own repo (`exempt` `:492`). Static config can't hold an exception that depends on state, and reef-init/update write these by Bash |
| G2 | git rm/mv/restore/checkout/reset that removes or replaces a guard file (incl. stored aliases, `--theirs`, rewritten index) | `check_guard_files` `:773` (`git_guard_targets` `:666`) | `tests/test_guard.py:795,901,912,927,962` | AUTHORITY (A-state + asks git) | Asks git itself (`git diff --name-only`). No config form |
| G3 | an inline program (`python3 - <<EOF`, `-c`) that writes a guard file | `check_inline_programs` `:812` | `tests/test_guard.py:627` | AUTHORITY (A-parse) | Only a reading of the program text sees it |
| G4 | Edit/Write of `scripts/reef-*`, `.githooks/*`, `hooks/hooks.json` | `check_edit` `:2006` | `tests/test_guard.py:1203,1451` | partial WALL (W4) for `.githooks/*`; **AUTHORITY** for `scripts/reef-*` and `hooks/hooks.json` | The critical exception again. `.githooks/` changes rarely, so it can carry an owner-lifted wall (section 5, decision D2). `scripts/` changes in every critical task |
| G5 | Edit of `.reef/config.json` changing a protected key (`roles caps gates tiers merge ci branches loop worktree`) | `check_edit` `:2004` | `tests/test_tiers_lock.py:714`, `tests/test_guard.py:615` | AUTHORITY (A-parse, key-level) | Config rules are per path, never per JSON key |
| G6 | Edit of `.reef/config.json` that does not parse | `check_edit` `:2000` | no direct test found (`tests/test_tiers_lock.py:714` covers keys) | AUTHORITY (A-parse) | Judges the content |
| G7 | rm/mv/chmod of the hook files whatever the tier (0.5 rule) | = B8/B9 | — | see B8/B9 | — |

### 3.5 Bash: roles, the loop, the forge

| id | refuses | where | test | class | why |
|---|---|---|---|---|---|
| L1 | a locked sub-agent (verifier, hunter, Explore, security, mahmoud, acceptance) runs `reef-setup.py prove/apply` | `check_reviewer_lock` `:839` | `tests/test_guard.py:651` | AUTHORITY (A-state) | Identity (`agent_type`) |
| L2 | a locked sub-agent runs mutating git | `:848` | `tests/test_tiers_lock.py:563` | AUTHORITY (A-state) | Identity. Note: these agents' **Edit/Write route is already a harness wall**: `agents/verifier.md:5`, `agents/loophole-hunter.md:19` give `tools: Read, Glob, Grep, Bash` (no Edit/Write) |
| L3 | a locked sub-agent runs `git branch/tag -d…`, `git config <write>` | `:852` | `tests/test_tiers_lock.py:563` | AUTHORITY (A-state) | Identity |
| L4 | a locked sub-agent writes a file outside scratch | `:860` | `tests/test_guard.py:671,712`; `tests/test_dayzero.py:116` | AUTHORITY (A-state) | Identity |
| L5 | any Reef sub-agent runs `gh pr checks --watch` / `gh run watch` | `:830` | `tests/test_tiers_lock.py:578` | AUTHORITY (A-state) | Identity: the main session may watch |
| L6 | any Reef sub-agent runs `sleep ≥ 60s` | `:835` | `tests/test_tiers_lock.py:578` | AUTHORITY (A-state + A-parse) | Identity and a number |
| P1 | the implementer writes a plan file (feature folder, task file) by Bash or git | `check_plan_files` `:1947` | `tests/test_guard.py:1052` | AUTHORITY (A-state) | Identity plus `paths.features` |
| P2 | the implementer Edits a plan file | `check_edit` `:1958` | `tests/test_guard.py:1032,1073` | AUTHORITY (A-state) | Same. An agent-file `disallowedTools` cannot scope by path |
| M1 | `gh pr merge -R/--repo` | `check_forge_merge` `:1234` | no direct test found | **partial WALL (W8)** | No state (it runs before the config read). `Bash(gh pr merge * --repo *)` etc. holds the documented forms. `gh api …/merge` stays in the guard |
| M2 | loop merge without a usable head, a base tip, the base contained, a green gate, CI's own run, a PASS/GREEN record for this PR, an ancestor record, git ≥ 2.38, clean merge-tree, claims-only (13 refusals) | `:1251,1257,1259,1261,1265,1270,1286,1292,1298,1316,1318`; `gh()` `:984,986,988` | `tests/test_record.py:173,178,212,286,309,328` | AUTHORITY (A-state) | Records, the forge, git |
| RP1 | release PR during a night/autopilot | `check_release_pr` `:1036` | `tests/test_night.py:205` | AUTHORITY (A-state) | Marker files |
| RP2 | release PR with no `--base` from `branches.base` | `:1048` | no direct test found | AUTHORITY (A-state) | Config plus refs |
| RP3 | release PR whose head can't be resolved | `:1051` | no direct test found | AUTHORITY (A-state) | git |
| RP4 | release PR with no PASS security record at its head | `:1064` | `tests/test_record.py:448` | AUTHORITY (A-state) | Record |
| D1 | `reef-queue.py footnote/note/add-row/drop-row` with `$VAR`/`$(…)` words | `check_day_footnote` `:1077` | `tests/test_day_proxy.py:161` | AUTHORITY (A-parse) | Content |
| D2 | a `(proxy, day …)` label typed into a queue writer or `gh issue` | `:1079` | `tests/test_day_proxy.py:161` | AUTHORITY (A-parse) | Content |
| J1 | `reef-run.py _job-run` typed by a session | `check_job_runner` `:1091` | `tests/test_guard.py:1373` | **partial WALL (W8)** | No state. `Bash(*reef-run.py _job-run*)` holds it. A renamed copy doesn't match |
| J2 | a job's inner command is judged as if typed | `:1095` (recursion) | `tests/test_guard.py:1373` | AUTHORITY (A-parse) | Re-runs the whole segment check |
| RC1 | a sub-agent starts `reef-run.py` (not status/watch/probe/contract) | `check_runner_cli` `:1116` | `tests/test_guard.py:1352` | AUTHORITY (A-state) | Identity |
| RC2 | a sub-agent runs `reef-loop.py unlock` | `:1118` | `tests/test_guard.py:1352` | AUTHORITY (A-state) | Identity. The main session may (it is the owner's takeover) |
| RC3 | a sub-agent runs `reef <verb>` other than the read verbs | `:1120` | `tests/test_guard.py:1352` | AUTHORITY (A-state) | Identity |
| RW1 | a record writer run with `PYTHONPATH`/`PYTHONSTARTUP`/… | `check_record_writer` `:1177` | `tests/test_guard.py:1114` | AUTHORITY (A-parse) | Pairs with the bytes check |
| RW2 | a record writer whose bytes, or a sibling it loads, differ from the plugin's; a shadowing module beside it | `:1185` | `tests/test_guard.py:1114,1154,1164` | AUTHORITY (A-state: digest) | Byte compare |
| A1 | `reef-approval.py` without `--proxy` (the owner's approval) | `check_approval_cli` `:1196` | `tests/test_opencode.py:187`; `tests/test_lessons.py:225` | partial WALL (W8) | "Without `--proxy`" has no deny form (no negation). W8 denies `--owner`, the documented spelling. A piped answer stays in the guard |
| A2 | `reef-approval.py --proxy` by a sub-agent other than mahmoud | `:1201` | `tests/test_day_proxy.py:178` | AUTHORITY (A-state) | Identity |
| O1 | a second Claude session acting on the loop (hold held by another live pid < 30 min) | `check_one_orchestrator` `:1877` | `tests/test_lock.py:61` | AUTHORITY (A-state) | Hold file plus pid |

### 3.6 Task/Agent dispatch

| id | refuses | where | test | class | why |
|---|---|---|---|---|---|
| DS1 | a role whose tier table says `none` | `check_role_model` `:1692` | `tests/test_tiers_lock.py:118` | AUTHORITY (A-state) | Config plus tier |
| DS2 | a dispatch whose `model` ≠ the configured role model | `:1695` | `tests/test_guard.py:308,315,320,336` | AUTHORITY (A-state) | Config |
| DS3 | a planner without the approved graph lessons | `check_graph_lessons` `:1522` | `tests/test_lessons.py:464` | AUTHORITY (A-state) | Content vs records |
| DS4 | a verifier/hunter with no `REEF-TASK:` line (tiered) | `_check_dispatch` `:1743` | `tests/test_tiers_lock.py:526` | AUTHORITY (A-parse) | Prompt content |
| DS5 | a hunter plan round above `hunter.plan_rounds` | `:1758` | `tests/test_tiers_lock.py:545` | AUTHORITY (A-state) | Cap |
| DS6 | an implementer with no `REEF-TASK:` line | `:1766` | `tests/test_guard.py:372` | AUTHORITY (A-parse) | Prompt |
| DS7 | the REEF-TASK file is missing | `:1772` | `tests/test_guard.py:377` | AUTHORITY (A-state) | File |
| DS8 | the task file is unreadable, has no frontmatter, non-integer or negative counters | `:1795,1797,1804,1806` | `tests/test_guard.py:482,452` | AUTHORITY (A-state) | File content |
| DS9 | a task that is `blocked` | `:1808` | `tests/test_guard.py:381` | AUTHORITY (A-state) | Status |
| DS10 | a task at the retry cap | `:1810` | `tests/test_guard.py:387` | AUTHORITY (A-state) | Cap |
| DS11 | the odometer at 2× the cap | `:1812` | `tests/test_guard.py:393` | AUTHORITY (A-state) | Counter |
| DS12 | a FAIL on record and the dead-ends block missing from the prompt | `check_dead_ends` `:1506` | `tests/test_guard.py:1308` | AUTHORITY (A-state) | Content vs records |
| DS13 | design/critical with no adversarial-plan pass, or a stale one | `check_adversarial_plan` `:1476,1479` | `tests/test_adversarial.py:158`; `tests/test_tiers_lock.py:118` | AUTHORITY (A-state) | Digest |
| DS14 | a broken task graph, or a task not in the ready set | `:1821,1823` | `tests/test_graph.py:108,218`; `tests/test_guard.py:549` | AUTHORITY (A-state) | Graph |
| DS15 | the same task already in flight (live marker, pid alive, no hand-back) | `:1837` | `tests/test_guard.py:409` | AUTHORITY (A-state) | Marker plus pid |
| DS16 | the plan check missing, unrunnable, or a stale stamp | `check_stamp` `:1572,1583,1586` | `tests/test_guard.py:514,532,869,879`; `tests/test_tiers_lock.py:332` | AUTHORITY (A-state) | Digest |
| DS17 | a rollup with no feature, or a second rollup | `check_single_rollup` `:1600,1615` | `tests/test_guard.py:549` | AUTHORITY (A-state) | Files |
| DS18 | the marker can't be written | `write_marker` `:1708` | no direct test found | AUTHORITY (A-state) | Disk |
| DS19 | the context reserve (an implementer within `caps.dispatch_reserve` of the ceiling) | `check_context_ceiling` `:2132` | `tests/test_loop.py:648` | AUTHORITY (A-state) | Transcript size |
| DS20 | over `caps.context_tokens` | `:2140` | `tests/test_loop.py:681` | AUTHORITY (A-state) | Same |

### 3.7 Stop

| id | refuses | where | test | class | why |
|---|---|---|---|---|---|
| S1 | a reply with no status line while the loop is active (once per message) | `check_stop` `:2042` | `tests/test_loop.py:605` | AUTHORITY (A-state) | loop.json plus content |
| S2 | ending the turn with ready work undispatched | `:2068` | `tests/test_loop.py:619` | AUTHORITY (A-state) | The tick |

### 3.8 INFRA (fail-closed plumbing, not classified)

| id | refuses | where | test |
|---|---|---|---|
| I1 | native Windows inside a Reef project | `:71–86` | `tests/test_guard.py:182` |
| I2 | deadline overrun (8 s, or 25 s for a dispatch) | `arm_deadline` `:2160` | `tests/test_tiers_lock.py:630,638` |
| I3 | internal error: Bash with bypass words, context read, edit, dispatch | `:273,2219,2244,1719` | `tests/test_guard.py:482` (dispatch); others: no direct test found |
| I4 | shell nesting > 25 | `:296` | `tests/test_guard.py:264` |
| I5 | unparseable command with bypass words | `:308` | `tests/test_guard.py:260` |
| I6 | another host's adapter input with no `agent`, or an unmapped tool | `from_host` `:2177,2179` | `tests/test_opencode.py:149` |

### 3.9 The count

| | rows | of which |
|---|---|---|
| Hook layer | 2 refusals (H1, H2) plus 1 gap (H3) | H1 partial WALL; H2 AUTHORITY |
| Bash bypasses B1–B10 | 10 | 9 partial WALL, 1 AUTHORITY |
| Records/handoff/evidence/queue R1–R9, E1–E3, Q1 | 13 | 2 partial WALL (R2, R9), 11 AUTHORITY |
| Self-guard G1–G6 | 6 | 1 partial WALL (G4, `.githooks/` only), 5 AUTHORITY |
| Roles/loop/forge L1–O1 | 25 (M2 counted once) | 3 partial WALL (M1, J1, A1), 22 AUTHORITY |
| Dispatch DS1–DS20 | 20 | 20 AUTHORITY |
| Stop S1–S2 | 2 | 2 AUTHORITY |
| **Policy rules** | **78 rows** (74 refusals plus H3, H4, G7, J2 as non-refusal or alias rows) | **16 partial WALL · 0 full WALL · 58 AUTHORITY** (plus 4 non-refusal rows) |
| INFRA I1–I6 | 6 | not classified |

Counted by `deny(` call: 129 call sites in `reef-guard.py` at `ac377d8`, grouped into the rows above, plus 2 in `hooks.json`.
("74 refusals" counts rules, not call sites.)

## 4. The proposed WALLs

Each WALL lists what it holds, the exact config, where config cannot reach, and whether the guard keeps its check.

### W1 — the plugin install tree is unwritable (NEW: today no rule holds it)

- **Why.** The guard trusts `OWN_SCRIPTS = dirname(realpath(__file__))` (`:1131`) and loads the plan check, the graph, attempt,
  lessons, evidence and claims "from the PLUGIN's own directory" (`load_plugin_module` `:1454`, `load_graph_module` `:1483`).
  `reef_project()` (`:459`) judges only paths inside a Reef project, and `~/.claude/plugins/…` is not one. So today an agent's
  `Edit` of `~/.claude/plugins/cache/<market>/reef/<ver>/scripts/reef-guard.py` passes the guard, and the next hook runs the
  edited guard. This is the guard's trust root, and the cleanest WALL there is.
- **Config.** `permissions.deny: ["Edit(~/.claude/plugins/**)"]` plus `sandbox.filesystem.denyWrite: ["~/.claude/plugins"]`.
- **Breaks.** A plugin update run **inside** a sandboxed session (`/plugin update`, `reef update` as a Bash call) cannot write
  the cache. `claude plugin …` from the owner's own terminal is unaffected, because the settings bind Claude's tools, not the
  shell. `tests/test_entry.py:953` (reef update refreshes the marketplace) must be checked against this in the code PR, and
  if needed the command added to `sandbox.excludedCommands`.
- **Class.** Full WALL for the Edit route and for sandboxed Bash. A new rule, not a migration.

### W2 — the walls' own settings are unwritable

- **Why.** A wall the agent can delete is not a wall. Project settings are a tracked file in the agent's tree.
- **Config.** `permissions.deny: ["Edit(/.claude/settings.json)"]` plus `sandbox.filesystem.denyWrite: ["./.claude/settings.json"]`
  (sandbox `./` = project root; section 6a. It is also a default protected path there). The guard adds `.claude/settings.json` to `GUARD_FILES` (`scripts/reef_common.py:731`), so the
  Bash and git routes get the critical-task rule like every guard file (G1, G2). That is AUTHORITY guarding the WALL, while W1
  is the WALL guarding the AUTHORITY.
- **Breaks.** `reef-init` / `reef update` writing the file by Bash under the sandbox: they would need to run once before the
  sandbox is on (first init), or from `excludedCommands`. See section 7.
- **Class.** Partial WALL. `.claude/settings.local.json` is the user's own and gitignored, and a user-scope `allow` can't beat a
  project `deny` ("deny rules from any scope are evaluated before allow rules"). So it needs no wall.

### W3 — `.git/hooks/` is unwritable (B8, B9 for that path)

- **Config.** `permissions.deny: ["Edit(/.git/hooks/**)"]` plus `sandbox.filesystem.denyWrite: ["./.git/hooks"]`. Per 6a the
  sandbox already write-denies "hooks and config inside .git" by default. The entry restates it as intent.
- **Legitimate writers.** None. Reef points `core.hooksPath` at `.githooks` (B7). No `.git/hooks` writer under `scripts/`
  (grep at `ac377d8`).
- **Gap.** A linked worktree's hooks resolve to the main checkout's `.git/hooks` (git's common dir), which for a session
  started in a worktree is outside `./`. The guard keeps B8/B9. Sandbox writes outside the cwd are already off unless allowed
  (Q3), so this is covered by default when the worktree lives elsewhere.
- **Guard.** Keeps B8/B9 (other paths, the `.githooks` half, and sessions without the sandbox).

### W4 — `.githooks/*` by the Edit tool (B8, B9, G4 for that path)

- **Config.** `permissions.deny: ["Edit(/.githooks/**)"]`. **No sandbox denyWrite**: `reef-init`/`reef update` render and
  `chmod +x` these by Bash (`scripts/reef-init.py` `place(..., executable=True)` `:476`).
- **Breaks.** A critical task that edits `.githooks/*` with the Edit tool. Today the guard allows it (`exempt` `:492`). Decision
  D2 (section 5).
- **Guard.** Keeps B8/B9/G1/G2/G4 in full.

### W5 — the record folders and HANDOFF.md by the Edit tool (R2, R9)

- **Config.**
  `permissions.deny: ["Edit(/.reef/approvals/**)", "Edit(/.reef/review/**)", "Edit(/.reef/night/**)", "Edit(/.reef/evidence/**)", "Edit(/.reef/run/jobs/**)", "Edit(/.reef/graph/gate.json)", "Edit(/HANDOFF.md)"]`.
- **Legitimate writers.** All Bash scripts or hooks (R1 why), never the Edit tool. So nothing breaks.
- **Gaps.** A feature worktree's own `.reef/` copy when the session's primary dir is the main checkout. Case variants
  (`.reef/Evidence/` on a case-insensitive disk: the guard's `re.I`). The docs do not say whether a gitignore-style match folds
  case. The code PR's T5 measures it, and the guard keeps R2/R9.
- **No sandbox denyWrite.** It would block the writers (R1).

### W6 — the sandbox itself, fail-closed

- **Config.** `sandbox.enabled: true`, `sandbox.failIfUnavailable: true`, `sandbox.allowUnsandboxedCommands: false`.
  `allowUnsandboxedCommands: false` is what stops a blocked command being re-run outside the sandbox. Docs: "With the retry
  disabled, Claude Code ignores the `dangerouslyDisableSandbox` parameter."
- **What it adds.** W1–W3's `denyWrite` only exists with the sandbox on. `failIfUnavailable` makes a machine where the sandbox
  can't start refuse to start, instead of running with no walls ("By default … Claude Code runs commands without sandboxing").
- **The stated exception.** "except in an Anthropic-hosted environment". There, per 6a, the session "doesn't enforce your
  `sandbox.filesystem` or `sandbox.network` rules". Claude Code on the web starts anyway, with its own container isolation.
  The walls there are the `permissions.deny` half plus the guard.
- **Scope not verified.** 6a: `failIfUnavailable` may be set from "Any file, with limits on project and local settings", and
  the limits are unstated. If project settings can't set it, it is the owner's user-settings line (section 7).
- **The cost: network.** With the sandbox on, sandboxed commands get network isolation with "allowed domains start empty".
  An unlisted host prompts in manual mode, passes in bypass and is refused in `dontAsk` (6a). Reef
  runs `gh`, `git push/fetch`, and package managers in gates. The code PR must either list `sandbox.network.allowedDomains` per
  stack (github.com, api.github.com, the registries), or put `git`/`gh` in `sandbox.excludedCommands`. The second runs them
  with "no filesystem restrictions", so `git` could then write `.git/hooks` (W3 weakens to the Edit route plus the guard).
  **Recommendation: the allowlist, not the exclusion** (decision D1).
- **Native Windows.** The sandbox does not run there ("On native Windows, Claude Code runs commands unsandboxed"), so
  `failIfUnavailable` refuses to start. That matches I1 (the guard already refuses native Windows in a Reef project).

### W7 — Bash deny rules for the gate bypasses (H1, B1–B7)

- **What they are.** A harness-level copy of the guard's tripwire for the forms Claude "usually produces". It runs **without
  python3** (closes most of H1's degraded grep), and **in every permission mode** ("Deny rules block in every mode, including
  `bypassPermissions`").
- **What they are not.** A boundary. Docs: a deny rule "doesn't match the same program invoked in a different form, so a deny
  or ask rule covers the invocation Claude usually produces and isn't a security boundary". The guard keeps B1–B7 whole. CI
  stays the wall for the gate itself (README, `scripts/reef-guard.py:21–23`).
- **Config.** Section 7's `permissions.deny` Bash list.
- **False positives checked against the guard's ALLOW table** (`tests/test_guard.py:118–169`): `git commit -m "…--no-verify…"`
  (`:121`) **would match** `Bash(git commit *--no-verify*)`. So the long-form rule is written as `Bash(git commit * --no-verify)`
  and `Bash(git commit --no-verify *)`. A trailing or leading flag matches, a quoted message mid-string does not, unless it
  ends the command (`git commit -m "x --no-verify"` still matches the first). That residual false positive is **accepted**
  (decision D3) or the rule is dropped. The code PR's T7 runs the full ALLOW table against the patterns.

### W8 — Bash deny rules with no state for three Reef verbs (M1, J1, A1)

- **Config.** `Bash(gh pr merge * -R *)`, `Bash(gh pr merge * --repo *)`, `Bash(gh pr merge * --repo=*)`,
  `Bash(*reef-run.py _job-run*)`, `Bash(*reef-approval.py --owner*)`, `Bash(*reef-approval.py * --owner*)`.
- **Guard.** Keeps M1/J1/A1 whole (the `gh api` route, renamed copies, a piped answer with no flag).

### Rejected as walls (and why)

- **sandbox denyWrite on `.reef/approvals|review|night|evidence|run/jobs`**: blocks `reef-record`, `reef-approval.py --proxy`,
  `reef-run.py`, `reef-gate.sh`. They run as the agent's Bash children. `excludedCommands` by name is the spoof RW2 exists to
  catch.
- **sandbox denyWrite on `.git/config`**: would hold B7 for any process, but blocks `git push -u`, `git branch
  --set-upstream-to`, `git remote`, `git worktree add` and `reef-init`'s own `git config core.hooksPath .githooks`.
- **sandbox denyWrite on `scripts/reef-*`**: blocks `reef-init --accept` and `reef update`, and every critical task.
- **Edit deny on `scripts/reef-*`, `hooks/hooks.json`, `.reef/config.json`**: the critical-task exception (G1, G4, G5) is
  state.
- **agent-file `tools:` for the reviewer lock**: already in place for the Edit route (L2 note). Bash stays the guard's
  (identity).

## 5. Keep or drop the guard's own check

**Keep every one.** Per WALL:

| WALL | guard rule(s) it shadows | keep? | what breaks if dropped |
|---|---|---|---|
| W1 | — (new) | n/a | — |
| W2 | — (new); the guard adds the file to `GUARD_FILES` | n/a | — |
| W3 | B8, B9 (`.git/hooks` half) | keep | Sessions without the sandbox (Anthropic-hosted, W6), worktree common dir, `excludedCommands` if D1 picks it |
| W4 | B8, B9, G4 (`.githooks` half) | keep | Bash route (no denyWrite), the critical exception's bookkeeping |
| W5 | R2, R9 | keep | Case-folded paths, a worktree's `.reef/`, the reach rule; the Bash route (R1, R8) is the guard's alone |
| W6 | I1 | keep | `failIfUnavailable` does not hold in Anthropic-hosted sessions |
| W7 | H1, B1–B7 | keep | Every non-standard form (`git -C`, `sh -c`, bundles, variables). The docs say so |
| W8 | M1, J1, A1 | keep | `gh api` merge, renamed copies, no-flag approval |

**Decisions for the owner** (the code PR waits on these):

- **D1 — network under the sandbox:** (a) an allowlist per stack written by `reef-init` (recommended), or (b) `git`/`gh` in
  `excludedCommands` (W3 weakens), or (c) no sandbox. Then W1–W3 are Edit-route only, and `failIfUnavailable` is moot.
- **D2 — `.githooks/` by the Edit tool:** wall it (W4, a critical task edits hooks by Bash under the guard's exemption) or
  leave it to the guard.
- **D3 — W7's residual false positive** (a commit message that ends in `--no-verify`): accept, or drop the long-form rule.

## 6. Doc evidence (fetched 2026-11-15)

Sources: <https://code.claude.com/docs/en/settings-reference.md>, <https://code.claude.com/docs/en/sandboxing.md>,
<https://code.claude.com/docs/en/permissions.md>, <https://code.claude.com/docs/en/permission-modes.md>,
<https://code.claude.com/docs/en/settings.md>, <https://code.claude.com/docs/en/managed-settings.md>,
<https://code.claude.com/docs/en/hooks.md>, <https://code.claude.com/docs/en/plugins/manifest-reference.md>,
<https://code.claude.com/docs/en/plugins/components.md>. (`/docs/en/iam` now redirects to Authentication. The permissions
page is `/docs/en/permissions`.) The quotes are as extracted by WebFetch, not byte-compared with the page source.

- **Q1 `failIfUnavailable`.** settings-reference: "`sandbox.failIfUnavailable`: Refuse to start when the sandbox can't, instead
  of running unsandboxed, except in an Anthropic-hosted environment". sandboxing: "By default, when the platform doesn't
  support the sandbox or the dependency check at startup fails, Claude Code runs commands without sandboxing. To make Claude
  Code exit at startup instead, set `sandbox.failIfUnavailable` to `true`." — **exists, default off, as the owner said, with
  the hosted exception.**
- **Q2 sandbox scope.** sandboxing: "The sandbox covers shell commands only. Claude's file tools, MCP servers, and hooks [run
  outside it]." "Built-in file and web tools: tools such as Read, Edit, Write, WebFetch, and WebSearch follow [permission rules]
  instead." permissions: "It applies to Bash, PowerShell, and Monitor tool commands and their child processes." Keys used here:
  `sandbox.enabled` ("Turn on Bash sandboxing on macOS, Linux, and WSL2"), `sandbox.filesystem.denyWrite` ("Block sandboxed
  commands from writing to specific paths"), `sandbox.allowUnsandboxedCommands` ("…With the retry disabled, Claude Code
  ignores the `dangerouslyDisableSandbox` parameter."), `sandbox.excludedCommands` ("…outside the sandbox, which means no
  filesystem restrictions and no network proxy."), `sandbox.network.allowedDomains` ("your allowed domains start empty").
- **Q3 permission rule syntax.** "Permission rules follow the format `Tool` or `Tool(specifier)`." "A `*` in a Bash rule
  matches any text, including spaces". Paths: `//path` absolute, `~/path` home, `/path` "relative to the settings source" (for
  project settings: "`<primary working directory>/path`"), `path`/`./path` relative to cwd. "Read and Edit rules both use
  gitignore pattern syntax". "`Edit` rules apply to all built-in tools that edit files." "use `Edit(docs/**)` in place of
  `Write(docs/**)`". The limits: "Deny and ask rules apply when any subcommand matches them, including a command nested
  inside a subshell, a command substitution, or a control-flow body". "It doesn't match the same program invoked in a
  different form, so a deny or ask rule covers the invocation Claude usually produces and isn't a security boundary around
  the program." `Bash(git push *)` "does not stop `git -C . push origin main`". "For filesystem and network enforcement that
  doesn't depend on the command text, use sandboxing."
- **Q4 precedence.** "Rules are evaluated in order: deny, then ask, then allow." "An allow rule can't carve an exception out of
  a deny rule." "a user-level deny blocks a project-level allow, because deny rules from any scope are evaluated before allow
  rules." Lists merge across files. "`deny` and `ask` rules apply right away" (before the folder is trusted).
- **Q5 plugins.** The manifest and components pages list skills, commands, agents, `hooks/hooks.json`, `.mcp.json`, `.lsp.json`,
  output styles, themes, monitors, `bin/`, channels and `userConfig`. They list no `permissions` and no `sandbox`. **A plugin
  cannot ship the walls** (this is an inference from their absence on those pages, confirmed again in section 6a).
- **Q6 managed.** Linux/WSL `/etc/claude-code/managed-settings.json`, macOS `/Library/Application Support/ClaudeCode/managed-settings.json`.
  `allowManagedPermissionRulesOnly` "ignores `allow`, `ask`, and `deny` rules in user, project, local" files. Bypass is
  `permissions.disableBypassPermissionsMode: "disable"`, not a top-level key.
- **Q7 hooks.** `onFailure`: "`"continue"` or `"block"`" (v2.1.295+). "Exit code 1 without valid JSON output is a non-blocking
  error unless the hook is one [whose failure blocks the action]… If your hook is meant to enforce a policy, use `exit 2`."
  permissions: "PreToolUse hook decisions don't bypass permission rules." "A blocking hook also takes precedence over allow
  rules."
- **Q8 bypass mode.** permission-modes: "Deny rules block in every mode, including `bypassPermissions`."

### 6a. Second fetch (sandbox paths, defaults, plugin settings)

Sources: <https://code.claude.com/docs/en/sandboxing.md>, <https://code.claude.com/docs/en/settings-reference.md>,
<https://code.claude.com/docs/en/plugins-reference.md>, <https://code.claude.com/docs/en/plugins.md>. Items marked **[S]**
came from WebFetch's summary of a long page, not verbatim text. The code PR re-reads them before it writes a key.

- **Sandbox path prefixes differ from permission rules** (settings-reference, "Sandbox path prefixes"): `/` is "Absolute path
  from filesystem root". `~/` is "Relative to home directory". `./` or no prefix is "Relative to the project root for project
  settings, or to `~/.claude` for user settings". The page notes this "differs from Read and Edit permission rules" (there,
  `/` is the project root). So the block's `denyWrite` uses `./…` and `~/…`, and its `Edit(…)` rules use `/…`. Globs: on
  Linux/WSL2, `allowWrite`/`denyWrite` take only a trailing `/**`. The block uses none.
- **Protected paths, write-denied by default** **[S]**: "the `.claude` settings files, the `.claude/skills`, `.claude/agents`,
  `.claude/commands`, and `.claude/hooks` directories, `.mcp.json`" (working dir and above). Also "hooks and config inside
  .git" (working dir only), and most of `~/.claude`. "An `allowWrite` entry can't lift a protected path." So **W2's and W3's
  `denyWrite` entries restate a default**. They stay in the block as explicit intent, and T3 proves the effect. Two
  consequences if the summary holds: (a) B7's file-writing form (`git config core.hooksPath x` writes `.git/config`) is
  already walled by the sandbox for any process; (b) so are `reef-init`'s own `git config core.hooksPath .githooks`,
  `git push -u` and `git remote`. T7 must find out which Reef flows that breaks before commit 3.
- **Defaults** (verbatim): `sandbox.allowUnsandboxedCommands` defaults to **`true`**, so the block's `false` is load-bearing.
  `sandbox.autoAllowBashIfSandboxed` defaults to `false` ("Before v2.1.324, the default was `true`."). How the
  `dangerouslyDisableSandbox` retry is approved depends on the mode: in `bypassPermissions` "the retry runs without a prompt".
- **`failIfUnavailable` scope** **[S]**: "Any file, with limits on project and local settings". **The limits are not stated on
  the pages read.** So it is not verified that a project's `.claude/settings.json` can turn it on. The code PR must check
  this (T6). If project scope can't set it, the key goes in the owner's **user** settings (`~/.claude/settings.json`). `reef-init`
  then prints the one line to add, and does not write the user's file. The Anthropic-hosted case **[S]**: "can start anyway,
  with a warning, and doesn't enforce your `sandbox.filesystem` or `sandbox.network` rules". So there, W1–W3's sandbox half is
  absent, not merely unrequired.
- **Network** (verbatim): "Connections go through a proxy on your machine that checks each host against your allowed domains,
  which start empty. Your permission mode decides what happens to other hosts." **[S]** For an unlisted host: a prompt in
  manual/acceptEdits mode, allowed in bypass, refused in `dontAsk` (and in auto unless approved). Headless `-p` behaviour is
  not stated. There is no switch for "filesystem isolation only". The only one is the reverse (`sandbox.filesystem.disabled`).
- **Hooks** (verbatim): "The sandbox covers shell commands only. Claude's file tools, MCP servers, and hooks run outside it."
  So the guard and the AskUserQuestion record writer are untouched by every `denyWrite`.
- **Plugins**: plugins-reference's layout table lists the manifest, skills, commands, agents, hooks, `.mcp.json`, `.lsp.json`,
  output-styles, workflows, themes, monitors and `bin/`. It lists **no `settings.json`, no `permissions`, no `sandbox`**.
  plugins.md: "Permissions: what the plugin runs, it runs as you." So the plugin cannot ship the walls, and section 7 stands.
- **Edit tool on settings files** **[S]** (settings-reference, `permissions.blockWritesOutsideWorkingDirectories`): "Settings
  files stay refused whatever you add." This is not confirmed as a default outside that setting, so W2 keeps its explicit
  `Edit(/.claude/settings.json)` deny.

## 7. Where the config lives, and the block in full

- **Not the plugin.** Q5: a plugin ships hooks and agents, not `permissions`/`sandbox`.
- **Not managed settings by default.** They are the owner's machine-wide policy, and `allowManagedPermissionRulesOnly` would
  silence every project's rules. Managed settings are the right home for one key only, on the owner's own machine:
  `permissions.disableBypassPermissionsMode: "disable"`. That is optional, and the owner's call.
- **The project's `.claude/settings.json`, written by `reef-init`.** It is committed, so every worktree carries it, and `/path`
  anchors at each session's primary working directory. Today `reef-init` writes **no** `.claude/settings.json` (grep of
  `scripts/reef-init.py` at `ac377d8`). The code PR adds it with `Renderer.offer`/merge semantics (`:528`), so an adopted
  project's existing settings are merged list-wise, never replaced. `reef-doctor` reports a missing or edited block.

The full block (D1 = allowlist; the hosts are per stack, and this is the github + npm case):

```json
{
  "permissions": {
    "deny": [
      "Edit(~/.claude/plugins/**)",
      "Edit(/.claude/settings.json)",
      "Edit(/.git/hooks/**)",
      "Edit(/.githooks/**)",
      "Edit(/.reef/approvals/**)",
      "Edit(/.reef/review/**)",
      "Edit(/.reef/night/**)",
      "Edit(/.reef/evidence/**)",
      "Edit(/.reef/run/jobs/**)",
      "Edit(/.reef/graph/gate.json)",
      "Edit(/HANDOFF.md)",

      "Bash(git commit --no-verify *)",
      "Bash(git commit * --no-verify)",
      "Bash(git commit * --no-verify *)",
      "Bash(git commit -n *)",
      "Bash(git commit * -n *)",
      "Bash(git merge --no-verify *)",
      "Bash(git merge * --no-verify *)",
      "Bash(git push --no-verify *)",
      "Bash(git push * --no-verify *)",
      "Bash(git -c core.hooksPath*)",
      "Bash(git -c core.hookspath*)",
      "Bash(git --config-env*hooksPath*)",
      "Bash(git config core.hooksPath /*)",
      "Bash(git config * core.hooksPath /*)",
      "Bash(git config --unset core.hooksPath*)",
      "Bash(git config --unset-all core.hooksPath*)",
      "Bash(GIT_CONFIG_KEY_* *)",
      "Bash(git stash)",
      "Bash(git stash push*)",
      "Bash(git stash save*)",
      "Bash(git stash pop*)",
      "Bash(git stash apply*)",
      "Bash(git stash drop*)",
      "Bash(git stash clear*)",

      "Bash(gh pr merge * -R *)",
      "Bash(gh pr merge * --repo *)",
      "Bash(gh pr merge * --repo=*)",
      "Bash(*reef-run.py _job-run*)",
      "Bash(*reef-approval.py --owner*)",
      "Bash(*reef-approval.py * --owner*)"
    ]
  },
  "sandbox": {
    "enabled": true,
    "failIfUnavailable": true,
    "allowUnsandboxedCommands": false,
    "filesystem": {
      "denyWrite": ["~/.claude/plugins", "./.claude/settings.json", "./.git/hooks"]
    },
    "network": {
      "allowedDomains": ["github.com", "api.github.com", "registry.npmjs.org"]
    }
  }
}
```

Notes on the block. `Bash(git commit -n *)` also matches `git commit -n` only when something follows. A bare `git commit -n`
has no message and opens an editor, which Claude does not produce. `Bash(GIT_CONFIG_KEY_* *)` is broad on purpose: no Reef
flow sets it. `-c` with a space (`git -c core.hooksPath=x`) is the form the patterns cover. `-ccore.hookspath` glued, and
`git -C . -c …`, are the guard's (B2). The sandbox path prefixes follow 6a: `./` is the project root and `~/` is home. In a sandbox list a bare `/` is
the filesystem root, unlike in `Edit(/…)`. If `failIfUnavailable` turns out not to be settable from project settings (6a),
it moves to the owner's user settings and the project block keeps the other sandbox keys.

## 8. Migration order (the later code PR)

1. **Commit 1 — red tests first** (section 9: T1–T8 written, all red: no config is written yet). Size budget unchanged.
2. **Commit 2 — `reef-init` writes the block** (merge, never replace) and `reef update` refreshes it. `reef-doctor` names a
   missing or edited rule. `GUARD_FILES` gains `.claude/settings.json` (W2), and `tests/test_guard.py:1203`'s shape table gains
   that path. T1–T6 go green.
3. **Commit 3 — the sandbox half** (W1–W3 `denyWrite`, W6), behind D1. T3/T4/T6 go green where the sandbox runs (Linux, macOS
   CI legs). The Anthropic-hosted exception is asserted as a skip with its reason, never a pass.
4. **Commit 4 — docs.** README "Before you run it" names the sandbox prerequisite (bubblewrap/socat on Linux; Q2 page), the
   hosted exception, and the ledger rows (`tests/test_contracts.py:188` "every ledger row says which host enforces it") gain
   "harness" as a host for W1–W8. CHANGELOG line, version bump (`shipped-change-bumps-the-version`, `.github/workflows/ci.yml:48`).

**No guard check is removed in any commit** (section 5). A later PR may revisit that only with field evidence that a WALL held
every case for a release.

## 9. Test plan for the code PR — each WALL red without config

The principle, as in PR-1..3: every new rule has a test that **fails with the config absent**, and passes with it present.

- **T0 — the untested refusals** (from section 3): Q1, G6, M1, RP2, RP3, DS18, H1-deny, H3, I3. One guard test each, with no
  config involved (gaps this audit found).
- **T1 — the block is written** (unit, no Claude): `reef-init` on a fresh project, and on an adopted one with its own
  `.claude/settings.json`, yields a file whose `permissions.deny` ⊇ the block and keeps the project's own keys. Red today
  (init writes no settings).
- **T2 — every deny pattern matches its DENY case and none of the guard's ALLOW cases**: a matcher that follows the docs'
  rule semantics (`*` any text, `:*` trailing only, per-subcommand split on `&& || ; | |& &` and newlines). It runs over
  `tests/test_guard.py`'s DENY (`:47–114`) and ALLOW (`:118–169`) tables. It reports each DENY case the config misses, as the
  guard's (expected, listed), and fails on any ALLOW case the config would block. This is a model of the harness, so it is
  backed by T8.
- **T3 — `.git/hooks` wall, sandbox** (Linux/macOS legs): run `sh -c 'echo x > .git/hooks/pre-commit; chmod -x
  .git/hooks/pre-commit'` under the sandbox runtime with the block's `denyWrite`. Without the config: the write lands
  (**red**). With it: EPERM. Run it with the **guard disabled**, to prove the wall holds alone.
- **T4 — the plugin tree wall** (same harness): a write under a fake `~/.claude/plugins/…` (HOME pointed at a temp dir). Red
  without, EPERM with.
- **T5 — the Edit-route walls** (W1, W2, W4, W5): headless `claude -p` with `--settings <block>` and the plugin's hooks off,
  asking for an Edit of each path. Without the block the edit lands (red), with it the tool reports a deny. Includes the
  `.reef/Evidence/` case-fold probe (W5 gap: the result is recorded, not assumed). Needs an API key, so it runs as an
  **opt-in lane** (`REEF_E2E_CLAUDE=1`), like the eval suite (`tests/eval`). This is the one place the real harness, not a
  model, is asked.
- **T6 — fail-closed** (W6): with `failIfUnavailable: true` and the sandbox's dependency hidden (PATH without bubblewrap), the
  session refuses to start. Without the key it starts unsandboxed (**red**). Opt-in lane, as T5.
- **T7 — no regression**: the whole existing suite (`sh tests/run.sh`, the stress suite) runs **inside** the sandbox with the
  block, so a wall that breaks a Reef flow (W1 vs `reef update`, W6's network) is a red test, not a field report. The
  candidates named here: `tests/test_entry.py:953`, every `gh`/`git push` fixture, and `reef-init`'s `.githooks` render.
- **T8 — the guard is still there**: for each W, the guard's own test of the shadowed rule (section 5's table) is unchanged
  and green with the config **absent**. Defense in depth means each layer is proven alone.
