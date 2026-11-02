# Stress triage, round three (hard tests): 81 failing tests

The suites tests/stress_e2e.py (crash-resume end to end) and tests/stress_fuzz.py (seeded fuzz of agent-written files), run at be50adb. Line numbers are from that tree. The triager re-ran each file once: e2e **7 failed, 28 passed** (134 s); fuzz **74 failed, 190 passed** (19 s). Both match the findings files.

**Verdicts:** e2e 7 VALID, 0 INVALID. Fuzz 51 VALID, 23 INVALID. **Clusters:** 15 (2 high, 6 medium, 7 low; one owner decision on whether to fix or drop the low non-ASCII digit cluster).

How the fuzz was judged:
- A mutation counts only if an agent or the owner would realistically write it, it gets past the gates in front of the reader, and it reads as a different meaning. Realistic mutations are case, bullets, bold, quotes, a fenced example, and the like.
- Task frontmatter is written by the planner, and `reef-plan-check.py` checks it before approval. That check is case-sensitive: `REQUIRED` at :55/:915, the vocabularies at :47-51/:916-919, the id at :920, the folder slug at :972, and it is pinned by tests/test_plan_check.py:1082. After approval, the plan stamp covers `tier`, `verify`, `id` and `feature` (:651 strips only the execution keys), and only scripts write `status`. So frontmatter mutations that plan-check refuses are out of contract.
- Cyrillic lookalikes are VALID only where the shared reader's fix closes them anyway (the verdict key and value). Non-ASCII digits are LOW and form one cluster with one shared rule.

## Clusters (by severity)

| id | sev | root cause (file:line) | tests | smallest fix that closes the cluster |
|---|---|---|---|---|
| **H1** | high | **The shared verdict reader still falls back to an earlier verdict.** reef_common.py:488 is `re.findall(r"^VERDICT:[ \t]*([A-Za-z]+)", …)[-1]`, with two problems. First, a line in a ``` fence counts. Second, a last verdict line the regex cannot parse is skipped, so the reader falls back to the earlier, fenced PASS or GREEN. The unparseable shapes are `verdict: FAIL`, `- VERDICT: FAIL`, `**VERDICT: FAIL**`, `VERDICT: "FAIL"`, an empty `VERDICT:`, and a Cyrillic `VЕRDICT`. A fenced example AFTER the verdict is in contract: verifier.md:17 says the report "ends `VERDICT: …` + concrete feedback", and the owner's "Bullets, not paragraphs" invites `- VERDICT:`. The effect: a round-2 FAIL that quotes round 1's PASS reads PASS (reef-claims `verdict`, reef-loop, merge-close:165, graph-run), and an acceptance FAIL that names a data BLOCKER binds GREEN (reef-record :284 → `report_binding` :509). `VERDICT: PAЅS` reads `'PA'`, which fails closed (low). Private copies remain: reef-claims.py:262 and :300 (`^VERDICT:\s*…`, first match; `\s*` crosses lines). | verifier ×14 · acceptance ×6 (list below) | **One reader, authoritative.** (1) Add `prose_lines(text)` to reef_common: the lines outside ``` fences and not starting with `>`. (2) `report_verdict` = the LAST prose line matching `^\W*verdict\W*:` (re.I). Its value, stripped of `*`, `` ` ``, `'` and `"`, must fullmatch `PASS\|FAIL\|GREEN` (re.I), else `''`. Skipping `>` lines is required: without it the new `^\W*` pattern would read `> VERDICT: PASS` (the passing `verdict_quoted_after` class). (3) reef-claims :262/:300 call `report_verdict`. |
| **H2** | high | **A GREEN record binds a head without the row's work.** The scenario: 102's close is killed after `git mv` and before the commit. reef-loop.py:339 reads `to_review` from the working tree's file names (`done/` full, `tasks/` empty), so the PR opens at a head without 102's code. `reef-gate full` then runs on the dirty tree. reef-evidence.py:116-119 still answers green from the `live` snapshot and only sets `dirty`, and reef-record :291 (`evidence_for`) ignores `dirty`. The guard's later `gh pr merge` check is the only thing that notices. | e2e: step07_verify_crash_mv | reef-record refuses `e.get("dirty")` for GREEN ("the tree differs from <sha>: commit or close first"). reef-loop's `to_review` also requires `git -C co status --porcelain` to be empty; a dirty one is named `close_now` for the open task. This keeps tests/test_evidence.py:117-131 (a dirty tree has no record of its own). |
| M1 | medium | **`BLOCKER_LINE` is case-sensitive** (reef_common.py:520, `^\W*BLOCKER\b`). A security PASS with `Blocker src/auth.py:9 …` is recorded (reef-record:183; security.md:40 says "FAIL iff a BLOCKER"), and so is a hunter PASS with `Blocker: …` (reef-adversarial:251). reef-claims.py:261 already reads the hunter's blockers with re.I, so the two readers disagree. | security: blocker_key_case · hunter: blocker_key_case | Add `re.I` to `BLOCKER_LINE`, and make reef-adversarial's `none` test case-insensitive (`Blocker: None`). This fails closed on `blocker-free` prose, which is acceptable. |
| M2 | medium | **A half-done task close stalls the row.** merge-close is killed after it writes `status: done` and the journal block and before the commit. The tick's graph read (reef-graph `status`, used at reef-loop.py:339) treats a `status: done` file still in `tasks/` as done, so it is never ready or `close_now`. The next task's fast-path close then runs `git add -A` (reef-merge-close:105) and sweeps the half-close into its own commit. reef-row says `build … (1 open task)` and the tick names nothing, which breaks reef-loop SKILL:44 ("continue every row from its furthest completed step"). plan-check already defines finished as `in_done(path) and status == done` (reef-plan-check.py:83). | e2e: step04_verify_crash_fm, step07_verify_crash_fm | In the tick, a task file outside `done/` with `status: done` is `close_now`; merge-close resumes it (:95 and :153 fall through to add, commit and mv). In merge-close's fast path, stage everything except other tasks' files (`git add -A -- . ':!<tasks>/*.md'`, then the task's own file). |
| M3 | medium | **A killed row close reads `closed`.** reef-row.py:121 treats archived and out of the queue as `closed`, with no check that the journal holds the feature's blocks, that the archive edit is committed, or that the feature worktree and branch are gone. The tick also skips the worktree once the row is archived (reef-loop.py:335). As a result, journal rows are lost silently and branches are left behind. | e2e: step12_close_crash_archived, step12_close_crash_journaled, step12_close_crash_committed (low) | reef-row reports `closed` only when all four hold: `reef-queue journal <slug>` would append 0, `git status --porcelain -- <queue> <archive> <journal>` is clean, there is no `feat/<slug>` branch, and there is no feature worktree. Otherwise it reports `close` and names the missing part. The close step is idempotent, so re-running it finishes the job. |
| M4 | medium | **A chat-mode dispatch never re-reads the live inflight marker.** reef-guard.py:1600-1636 bumps and writes the marker with no check for `.reef/inflight/<id>`, so the same Task call issued twice puts two implementers on one worktree. Graph mode refuses this (reef-graph-run.py:247-248), and its docstring promises the tick sees both modes alike. | e2e: step02_dispatch_dup_twice | Under the graph lock, before `bump_dispatches`, deny when the marker is younger than `inflight_stale_minutes`, its pid is alive, and no hand-back is newer than the marker. reef-task SKILL:28 says "`rm` each marker after its hand-back", so a fix round stays allowed. **Owner decision:** tests/test_guard.py:410 `test_odometer_backstop_denies_runaway` dispatches 6× without removing the marker, and the test runner is the live pid. Change it to `rm` the marker between dispatches, which is what the orchestrator does. |
| M5 | medium | **The SPEC `Row:` line still has seven private readers.** All of them use `^Row:\s*`, and `\s*` crosses the newline: reef-loop.py:199 and :330, reef-queue.py:186, :905 and :1328, reef-guard.py:1512, and scripts/reef:1342. reef_common.spec_row (:481) has the same `\s*`. `Row:` followed by `1. the owner …` reads row 1, and plan-check :857 accepts it as present. A fenced `Row: 3` above `Row: 12` reads 3. `Row: 12` then `Row: 14` silently reads 12. | spec: spec_row × 3 (empty_value_numbered_next, row_in_fence_before, row_duplicate_conflicting), queue_row_reader × 2 (row_in_fence_before, row_duplicate_conflicting) | `spec_row` reads `^Row:[ \t]*(\d+[a-z]?)\b` over `prose_lines` (from H1) and returns `''` when two Row lines disagree, the same rule as reef-run `contract_line`. All seven sites call `spec_row`. plan-check and `reef-queue check` fail on `''`. |
| M6 | medium | **`reef-queue check` passes a queue that `status`/`ready` misread** (reef-queue.py: `parse_table` :123-147, `current_batch` :150-153, `ready` :848, `check` :860). `Current Batch: 2` or `Current batch: '2'` reads as None, so `ready` offers every batch (medium). A second `Current batch: 3` loses silently. `\| id \|` or `\| ID \|` gives 0 rows and still `ok`. A fenced example table adds row 99. An emptied Id cell drops the row unnamed. `\| '2' \|` in Batch means the row is never ready (low). | queue: current_batch_key_case, current_batch_quoted, current_batch_duplicate, header_case, table_in_fence, row_id_empty, batch_cell_quoted | `current_batch`: read case-insensitively and strip quotes. `check` fails on zero or more than one readable line when a table has a Batch column. `parse_table`: skip non-`prose_lines`, match the header case-insensitively, and send an empty Id (with other cells filled) or a non-`[0-9]+` Batch to `rejected`. |
| L1 | low | reef-claims `check --handback` (:168) counts a claim inside a fence or after `>`, so a hand-back with no claims passes the shape check. The later `check` still requires the claim to name a line this round added. | handback: claim_in_fence, claim_in_quote | Collect claims from `prose_lines` (H1). |
| L2 | low | **reef-queue has a private journal-block regex.** :1284 `JOURNAL_BLOCK` is unanchored, so a `> <!-- journal -->` quote is copied into the journal. reef_common `JOURNAL_BLOCK_RE` (:521), which merge-close uses, is anchored, and neither one skips a fenced example. A fenced example also makes merge-close:114 think the block is already written. | journal: example_in_fence, example_in_quote | reef-queue `cmd_journal` uses `JOURNAL_BLOCK_RE` over `"\n".join(prose_lines(text))`, and so does merge-close :114/:205. Delete the private copy. |
| L3 | low | **reef-run's contract lines lose ids or kinds silently** (fail-closed). `night_rows` (:814) stops at a footnote mark (`Rows: 12³, 14` → 12 only; the owner's marks ride on lines, as with first contact's `2²⁶`). `day_kinds` (:879) keeps quotes (`Decides: "process, …, plan"` → `"process` and `plan"`, so `plan` is not the proxy's). | night: row_footnote_mark · proxy: value_quoted | `contract_line` strips one pair of surrounding quotes or backticks. `night_rows` allows `[⁰-⁹]*` after each id. |
| L4 | low | **Two private frontmatter readers keep single quotes** (round one's M1 remnant). reef-graph.py:68 and reef-queue.py:174-180 strip only `"`. `feature: '12'` (legacy flat layout, where plan-check has no slug rule) is keyed `"'12'"`, so row 12 reads `queued` while its task is done. | frontmatter: graph_read_frontmatter__value_quoted_single, queue_task_states__value_quoted_single | Both call `reef_common.task_frontmatter`, and the private loops are deleted. plan-check's `parse_frontmatter` (:123) stays the strict gate, since it refuses duplicate keys. |
| L5 | low | **Non-ASCII digits read as ids** (`\d` is Unicode). Examples: `id: ７` (plan-check :920 `R?\d+` accepts it), `feature: ١٢`, `Current batch: ２`, a `\| ١٥ \|` row (`int('١٥') == 15` in the sort), `Rows: ١٢`, and `Row: １２`. No model is likely to write these. | frontmatter × 5 (task_frontmatter and graph: unicode_digit_id, unicode_digit_feature; queue_task_states: unicode_digit_feature) · queue: current_batch_unicode_digit, row_id_unicode_digit · night: row_unicode_digit · spec: spec_row__row_unicode_digit | **One shared rule:** `ROW_ID = r"[0-9]+[a-z]?"` in reef_common, used by `spec_row`, `parse_table`, `current_batch`, `night_rows` and plan-check's id. `task_frontmatter` returns None when `id`/`feature` holds a non-ASCII digit. **Owner decision:** fix it (one PR-3 commit), or put the 9 tests in `OUT_OF_CONTRACT`. |

Shared helpers to reuse: reef_common `report_verdict`, `BLOCKER_LINE`, `spec_row`, `task_frontmatter` and `JOURNAL_BLOCK_RE`, plus reef-run `contract_line`. New: `prose_lines` (H1, then reused by M5, M6, L1, L2) and `ROW_ID` (L5).

## INVALID (23, all in stress_fuzz.py)

The generator draws every mutant from ONE shared `random.Random(SEED)`. Deleting an op from a table would shift every later kind's mutants. **Don't delete ops.** Add a skip set, or change an expectation, both of which consume no randomness:

```python
OUT_OF_CONTRACT = {   # (kind, reader, class): INVALID in docs/review/stress-2026-11-03-hard.md — no test generated
    ...
}
```

In the generator loop, `continue` on a hit before `setattr`.

**Skip: the class cannot reach the reader**
- **frontmatter · task_frontmatter / graph_read_frontmatter / queue_task_states · value_case, key_case, key_lookalike, empty_value** (12 tests). Plan-check refuses each one before approval: `Status:` or `ѕtatus:` is a missing REQUIRED key, and `verify: Judge`, `tier: Critical`, `status: Pending` and `status:` fall outside the vocabularies at :916-919, pinned by tests/test_plan_check.py:1082. `tier` and `verify` are in the plan stamp, so a later edit stales the approval and the guard denies dispatch. `status` is written only by scripts (`bump_dispatches`, merge-close, reef-attempt).
- **frontmatter · queue_task_states · bom.** Round one ruled BOM unreachable: no agent writer emits one.
- **frontmatter · queue_task_states · truncated.** Task files are written by atomic replace (reef_common.py:466-469 `bump_dispatches`, reef-graph `set_keys`) and read as committed files.
- **hunter · adversarial_plan · blocker_lookalike** and **security · record_security · blocker_lookalike.** The only fix is a confusables fold or a non-ASCII refusal, which is no shared rule. A model does not write a Cyrillic `О` in an English keyword.
- **journal · queue_journal · marker_case, marker_spacing, trailing_spaces.** Only reef-merge-close writes the markers, in the exact shape (`--journal` file between `<!-- journal -->` lines, :114/:205). No agent writes them.
- **journal · queue_journal · block_duplicate_same.** merge-close writes a block only when the body has none (:114, :205), so two identical blocks are unreachable. Deduping `new` in `cmd_journal` would cost one line if wanted.
- **journal · queue_journal · truncated.** The file is committed whole before the close copies it. A cut before the opening marker is also indistinguishable from a task with no block, so the REFUSE label cannot be met.

**Reclassify: the expectation is wrong**
- **acceptance · report_binding · head_duplicate_conflicting.** Change REFUSE to SAME in `head_ops`. The report "opens with HEAD" (acceptance.md:3, :24), and `report_head` reads that opening line. An unfenced second HEAD line further down is not an agent shape; the realistic one, a fenced earlier HEAD, is in the sample and passes.
- **security · record_security · run_duplicate_conflicting.** This is a test bug. `run_ops` substitutes `head=\w+`, and that pattern does not match the `{HEAD12}` placeholder, so the "conflicting" line is an identical copy of the RUN line. Use `head=\S+`, then change REFUSE to SAME for the same reason as above: the RUN line is the first line (security.md:32).

## PR split (3, high first)

1. **One report reader** (H1, M1, L1). Files: scripts/reef_common.py (`prose_lines`, `report_verdict`, `BLOCKER_LINE`) and scripts/reef-claims.py (:168, :262, :300), plus the case-insensitive none-test in scripts/reef-adversarial:251. **24 fuzz tests.** Run tests/test_adversarial.py, test_record.py and stress_adversarial.py, which pin the current report shapes.
2. **Crash-resume closes what it started** (H2, M2, M3, M4). Files: scripts/reef-record (:291), scripts/reef-loop.py (:335-339 `to_review`/`close_now`), scripts/reef-merge-close (:105), scripts/reef-row.py (:121) and scripts/reef-guard.py (:1600-1636). **7 e2e tests.** Owner decision: M4 rewrites tests/test_guard.py:410 to `rm` the marker between dispatches.
3. **Agent-written lines read one way** (M5, M6, L2, L3, L4, and L5 if the owner chooses to fix it). Files: scripts/reef_common.py (`spec_row`, `ROW_ID`, `task_frontmatter`), scripts/reef-queue.py, scripts/reef-run.py and scripts/reef-graph.py, plus `spec_row` call sites in reef-loop.py:199/:330, reef-guard.py:1512 and scripts/reef:1342. **18 fuzz tests, 27 with L5.** This PR overlaps PR 1 (reef_common, which it reuses `prose_lines` from) and PR 2 (reef-loop and reef-guard, different functions), so land it last.

**Owner decisions**
- **M4:** flip the pinned test_guard.py:410 (rm the marker between dispatches).
- **L5:** fix the non-ASCII digits, or skip them.
- **Optional, not needed to close any test:** reef-record GREEN also refuses an acceptance report with a non-`none` `BLOCKER:` line, as `security` does at :183. acceptance.md:18 defines a BLOCKER, but the contract never says that one forbids GREEN.

## stress_e2e.py runtime

Measured with `--durations=0`: 135 s in total.
- **Golden run:** 20 s in `setUpClass`.
- **The 7 failing tests:** 39 s. `step02_dispatch_dup_twice` alone takes 16 s, because two dispatches drive to the end.
- **The 28 passing tests:** 76 s. One outlier is `step04_verify_crash_mv` at 14 s; most of the rest take 1-4 s each.

**It can be trimmed with no finding lost.** All 7 findings come from the dup, fm, mv and close-crash faults.
- **Drop 11 tests that are redundant by construction**, saving about 19 s and bringing the file to about 116 s:
  - `dup` at steps 0, 1, 3, 8, 9, 11 and 12 (about 12 s). Each of these steps either refuses its second run or is idempotent by design, and each passed.
  - `stale` at steps 2 and 8 (about 3 s). Step 4 keeps it.
  - the `gh pr list --base` fault at step 0 (about 1.7 s). Step 4 keeps it, and the comment at :729 says the boundary behaves the same at every step.
- **Or, preferred: keep the full matrix behind `REEF_E2E_FULL=1`.** By default, run the golden run, the 7 finding tests and one test of each fault kind (gh, stale, code-only, report-only), about 75 s.

Fewer faults per step would not help on its own. The cost is the per-fault drive to the end (1-16 s each), not the number of crash prefixes.

## Per-test verdicts

**Marking.** Both files generate their tests in a loop with `setattr`. Neither has hand-written methods to decorate, and no generated test mixes classes: fuzz has one test per (kind, reader, class), and e2e one per (step, fault). So no test needs splitting. Wrap at generation time:

```python
OPEN = {   # test name -> cluster id in docs/review/stress-2026-11-03-hard.md
    "test_verifier__report_verdict__verdict_fenced_after": "H1",
    ...
}
...
        t = make_test(_kind, _reader, _cls)
        if name in OPEN:
            t = unittest.expectedFailure(t)   # open: OPEN[name] (docs/review/stress-2026-11-03-hard.md)
        setattr(Fuzz, name, t)
```

In stress_e2e.py, do the same inside the `_make` loop, keyed by `_t.__name__`. A fix PR removes its ids from `OPEN`. An unexpected success then flags any id that was missed.

### tests/stress_fuzz.py: VALID (51)
- test_verifier__report_verdict__verdict_fenced_after → H1
- test_verifier__report_verdict__verdict_key_case → H1
- test_verifier__report_verdict__verdict_markdown → H1
- test_verifier__report_verdict__verdict_value_quoted → H1
- test_verifier__report_verdict__verdict_empty_value → H1
- test_verifier__report_verdict__verdict_key_lookalike → H1 (low)
- test_verifier__report_verdict__verdict_value_lookalike → H1 (low, fails closed)
- test_verifier__claims_verdict__verdict_fenced_after → H1
- test_verifier__claims_verdict__verdict_key_case → H1
- test_verifier__claims_verdict__verdict_markdown → H1
- test_verifier__claims_verdict__verdict_value_quoted → H1
- test_verifier__claims_verdict__verdict_empty_value → H1
- test_verifier__claims_verdict__verdict_key_lookalike → H1 (low)
- test_verifier__claims_verdict__verdict_value_lookalike → H1 (low, fails closed)
- test_acceptance__report_binding__verdict_fenced_after → H1
- test_acceptance__report_binding__verdict_key_case → H1
- test_acceptance__report_binding__verdict_markdown → H1
- test_acceptance__report_binding__verdict_value_quoted → H1
- test_acceptance__report_binding__verdict_empty_value → H1
- test_acceptance__report_binding__verdict_key_lookalike → H1 (low)
- test_security__record_security__blocker_key_case → M1
- test_hunter__adversarial_plan__blocker_key_case → M1
- test_spec__spec_row__empty_value_numbered_next → M5
- test_spec__spec_row__row_in_fence_before → M5
- test_spec__spec_row__row_duplicate_conflicting → M5
- test_spec__queue_row_reader__row_in_fence_before → M5
- test_spec__queue_row_reader__row_duplicate_conflicting → M5
- test_queue__queue_status__current_batch_key_case → M6
- test_queue__queue_status__current_batch_quoted → M6
- test_queue__queue_status__current_batch_duplicate → M6
- test_queue__queue_status__header_case → M6
- test_queue__queue_status__table_in_fence → M6
- test_queue__queue_status__row_id_empty → M6
- test_queue__queue_status__batch_cell_quoted → M6
- test_handback__claims_handback__claim_in_fence → L1
- test_handback__claims_handback__claim_in_quote → L1
- test_journal__queue_journal__example_in_fence → L2
- test_journal__queue_journal__example_in_quote → L2
- test_night__night_rows__row_footnote_mark → L3
- test_proxy__day_kinds__value_quoted → L3
- test_frontmatter__graph_read_frontmatter__value_quoted_single → L4
- test_frontmatter__queue_task_states__value_quoted_single → L4
- test_frontmatter__task_frontmatter__unicode_digit_id → L5
- test_frontmatter__task_frontmatter__unicode_digit_feature → L5
- test_frontmatter__graph_read_frontmatter__unicode_digit_id → L5
- test_frontmatter__graph_read_frontmatter__unicode_digit_feature → L5
- test_frontmatter__queue_task_states__unicode_digit_feature → L5
- test_queue__queue_status__current_batch_unicode_digit → L5
- test_queue__queue_status__row_id_unicode_digit → L5
- test_night__night_rows__row_unicode_digit → L5
- test_spec__spec_row__row_unicode_digit → L5

### tests/stress_fuzz.py: INVALID (23), see the INVALID section above
- **OUT_OF_CONTRACT (21):**
  - frontmatter × task_frontmatter, graph_read_frontmatter, queue_task_states × value_case, key_case, key_lookalike, empty_value (12)
  - (frontmatter, queue_task_states, bom)
  - (frontmatter, queue_task_states, truncated)
  - (hunter, adversarial_plan, blocker_lookalike)
  - (security, record_security, blocker_lookalike)
  - (journal, queue_journal, marker_case)
  - (journal, queue_journal, marker_spacing)
  - (journal, queue_journal, trailing_spaces)
  - (journal, queue_journal, block_duplicate_same)
  - (journal, queue_journal, truncated)
- **Reclassify (2):**
  - test_acceptance__report_binding__head_duplicate_conflicting → SAME
  - test_security__record_security__run_duplicate_conflicting → `head=\S+` and SAME

### tests/stress_e2e.py: VALID (7)
- Golden::test_step07_verify_crash_mv → H2
- Golden::test_step04_verify_crash_fm → M2
- Golden::test_step07_verify_crash_fm → M2
- Golden::test_step12_close_crash_archived → M3
- Golden::test_step12_close_crash_journaled → M3
- Golden::test_step12_close_crash_committed → M3 (low)
- Golden::test_step02_dispatch_dup_twice → M4 (owner decision: test_guard.py:410)

Severity notes where I differ from the findings files:
- **Fuzz F1-F3 frontmatter (value_case `verify: Judge` and the rest), medium → out of contract.** plan-check and the plan stamp sit in front of every reader.
- **Fuzz Q1 header_case, low-medium → low.**
- **Fuzz P2 `Row:` crossing a line stays medium.** Seven private readers share the bug.
