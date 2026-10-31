"""Sabotage suite for scripts/reef-tier.py (a tier can only get heavier) and
scripts/reef-queue.py (the outer graph: status derived from task files, ready rows, consistency,
ADR numbering at merge)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import write, git, git_repo  # noqa: E402  (the suites' shared fixtures, once)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIER = os.path.join(ROOT, "scripts", "reef-tier.py")
QUEUE = os.path.join(ROOT, "scripts", "reef-queue.py")


def repo(cfg=None):
    d = git_repo(prefix="reef-tq.", branch="main", identity=True)
    write(d, ".reef/config.json", json.dumps(cfg or {}))
    write(d, "src/app.py", "print(1)\n")
    write(d, "docs/notes.md", "n\n")
    git(d, "add", "-A")
    git(d, "commit", "-qm", "base")
    git(d, "checkout", "-qb", "feat")
    return d


def task(d, tier):
    return write(d, "tasks/001-t.md", f"---\nid: 1\nfeature: 1\nstatus: pending\ntier: {tier}\n---\n# 1\n")


def commit(d):
    git(d, "add", "-A")
    git(d, "commit", "-qm", "work")


def tier(task_path, *args):
    return subprocess.run([sys.executable, TIER, task_path, "--repo", os.path.dirname(os.path.dirname(task_path)), *args],
                          capture_output=True, text=True)


CFG = {"tiers": {"light": {"allow": ["docs/**", "src/safe/**"], "max_lines": 5, "migrations": ["migrations/**"]}}}


class Path(unittest.TestCase):
    """Workflow v3, phase 3: the tier names the PATH, and the path decides the pipeline — light/full = fast; design/critical,
    or a touch of auth/pii/money/migration = critical. `reef-tier.py path <task files>` prints it; rollups are not tasks."""

    def test_path_from_tiers_and_touches(self):
        d = tempfile.mkdtemp(prefix="reef-path.")
        fm = lambda tier, touches, tid=1: f"---\nid: {tid}\nfeature: f\nstatus: pending\ntier: {tier}\ntouches: [{touches}]\n---\n# t\n"
        a = write(d, "tasks/101-a.md", fm("light", "", 101))
        b = write(d, "tasks/102-b.md", fm("full", "", 102))
        r = subprocess.run([sys.executable, TIER, "path", a, b], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "path: fast (tiers light, full; no risk touch)")
        c = write(d, "tasks/103-c.md", fm("full", "migration", 103))
        r = subprocess.run([sys.executable, TIER, "path", a, b, c], capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "path: critical — 103: touches migration")
        e = write(d, "tasks/104-e.md", fm("design", "", 104))
        r = subprocess.run([sys.executable, TIER, "path", a, e], capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "path: critical — 104: tier design")
        rollup = write(d, "tasks/R01-f.md", fm("critical", "money", "R1"))
        r = subprocess.run([sys.executable, TIER, "path", a, rollup], capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "path: fast (tiers light; no risk touch)", "a rollup is a fix round, not a task of the plan")
        r = subprocess.run([sys.executable, TIER, "path"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, "no task file: usage")
        # the review (2026-10-25): one rule, one parser — a bracketless `touches: auth` (which the check now refuses) reads the
        # same here as in reef-plan-check.feature_path and the guard: critical
        g = write(d, "tasks/105-g.md", "---\nid: 105\nfeature: f\nstatus: pending\ntier: full\ntouches: auth\n---\n# t\n")
        r = subprocess.run([sys.executable, TIER, "path", a, g], capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "path: critical — 105: touches auth")


class Tier(unittest.TestCase):
    def test_light_diff_passes_light_declaration(self):
        d = repo(CFG)
        t = task(d, "light")
        write(d, "docs/notes.md", "n\nmore\n")
        write(d, "src/safe/x.py", "a = 1\n")
        commit(d)
        r = tier(t)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_declared_light_computed_full_refused_and_write_raises(self):
        d = repo(CFG)
        t = task(d, "light")
        write(d, "src/app.py", "print(2)\n")        # not allowlisted
        commit(d)
        r = tier(t)
        self.assertEqual(r.returncode, 1, "a diff outside the allowlist cannot be light")
        self.assertIn("not in tiers.light.allow", r.stdout)
        r = tier(t, "--write")
        self.assertEqual(r.returncode, 1)
        with open(t) as f:
            self.assertIn("tier: full", f.read())

    def test_migration_and_line_ceiling_make_it_full(self):
        d = repo(CFG)
        t = task(d, "light")
        write(d, "migrations/001.sql", "x\n")
        commit(d)
        self.assertIn("a migration", tier(t).stdout)
        d = repo(CFG)
        t = task(d, "light")
        write(d, "src/safe/big.py", "\n".join(f"l{i} = {i}" for i in range(10)) + "\n")
        commit(d)
        r = tier(t)
        self.assertEqual(r.returncode, 1)
        self.assertIn("product lines added", r.stdout)

    def test_tests_do_not_count_as_product_lines(self):
        d = repo(CFG)
        t = task(d, "light")
        write(d, "tests/test_big.py", "\n".join(f"def test_{i}(): pass" for i in range(40)) + "\n")
        write(d, "src/safe/x.py", "a = 1\n")
        commit(d)
        self.assertEqual(tier(t).returncode, 1, "tests/ is not in the allowlist — still full")
        cfg = {"tiers": {"light": {"allow": ["src/safe/**", "tests/**"], "max_lines": 5}}}
        d = repo(cfg)
        t = task(d, "light")
        write(d, "tests/test_big.py", "\n".join(f"def test_{i}(): pass" for i in range(40)) + "\n")
        write(d, "src/safe/x.py", "a = 1\n")
        commit(d)
        self.assertEqual(tier(t).returncode, 0, "test lines must not count toward the product-line ceiling")

    def test_heavier_declaration_always_ok_and_empty_diff_refused(self):
        d = repo(CFG)
        t = task(d, "design")
        write(d, "docs/notes.md", "n\nx\n")
        commit(d)
        self.assertEqual(tier(t).returncode, 0)
        d = repo(CFG)
        t = task(d, "light")
        commit(d)
        r = tier(t)
        self.assertEqual(r.returncode, 1)
        self.assertIn("empty diff", r.stderr)


QUEUE_MD = """# Queue
Current batch: 1

| Id | Item | Depends | Source | Batch | Admitted |
|---|---|---|---|---|---|
| 1 | first | | planned | 1 | |
| 2 | second | 1 | planned | 1 | |
| 3 | found thing | | found | 1 | |
| 4 | later | | planned | 2 | |
"""


def queue(root, *args):
    return subprocess.run([sys.executable, QUEUE, *args, "--repo", root], capture_output=True, text=True)


def qrepo():
    d = tempfile.mkdtemp(prefix="reef-q.")
    git(d, "init", "-q", "-b", "main")
    write(d, ".reef/config.json", json.dumps({"writing": {"queue_words": 200}}))
    write(d, "docs/queue.md", QUEUE_MD)
    return d


class JournalStatuses(unittest.TestCase):
    def test_statuses_are_read_from_the_acs_column_not_from_prose(self):
        # first contact (2026-10-17): "AC-9 and AC-13 were probed" in a Verified paragraph was rejected as the status "and";
        # three honest entries were reworded to pass. The closed set applies to the table's ACs column only.
        d = qrepo()
        write(d, ".reef/version", "0.7.0\n")
        write(d, "tasks/101-a.md", "---\nid: 101\nfeature: 1\nstatus: done\n---\n")
        write(d, "docs/journal.md", "# Journal\n\n| Task | Implementer | Verifier | Attempts | Result | ACs | Escaped defects |\n|---|---|---|---|---|---|---|\n"
                                    "| 101 | opus | opus | 0 | PASS | AC-1 achieved; AC-2 achieved | - |\n\n"
                                    "- **Verified, and how**: AC-9 and AC-13 were probed with a live canary; AC-4 was re-run by the mechanic.\n")
        r = queue(d, "check")
        self.assertEqual(r.returncode, 0, r.stdout)
        write(d, "docs/journal.md", "# Journal\n\n| Task | Implementer | Verifier | Attempts | Result | ACs | Escaped defects |\n|---|---|---|---|---|---|---|\n"
                                    "| 101 | opus | opus | 0 | PASS | AC-1 achieved; AC-2 maybe | - |\n")
        r = queue(d, "check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("AC status 'maybe'", r.stdout)


class JournalNotesInParentheses(unittest.TestCase):
    def test_a_note_in_parentheses_is_not_a_status(self):
        # 2026-10-24, the trial (twice): "AC1…AC5 achieved (AC3, AC4 rendered on the server by their Proof tests, not a
        # browser)" read "rendered" as a status, and the agent rewrote the honest caveat as "achieved via server-rendered HTML"
        d = qrepo()
        write(d, ".reef/version", "0.7.0\n")
        write(d, "tasks/101-a.md", "---\nid: 101\nfeature: 1\nstatus: done\n---\n")
        head = "# Journal\n\n| Task | Implementer | Verifier | Attempts | Result | ACs | Escaped defects |\n|---|---|---|---|---|---|---|\n"
        write(d, "docs/journal.md", head + "| 101 | opus | opus | 0 | PASS | AC1…AC5 achieved (AC3, AC4 rendered on the server by their Proof tests, not a browser) | none |\n")
        r = queue(d, "check")
        self.assertEqual(r.returncode, 0, r.stdout)
        write(d, "docs/journal.md", head + "| 101 | opus | opus | 0 | PASS | AC-1 achieved (by hand); AC-2 maybe | none |\n")
        r = queue(d, "check")
        self.assertEqual(r.returncode, 1, "a status outside the parentheses is still checked")
        self.assertIn("AC status 'maybe'", r.stdout)


class BatchLineWithFootnote(unittest.TestCase):
    def test_a_footnote_marker_on_the_batch_line_is_not_part_of_the_number(self):
        # first contact (2026-10-17): the owner's decision to skip the release was footnoted on the line — "Current batch: 2²⁶" read as batch "2²⁶"
        d = qrepo()
        write(d, "docs/queue.md", read_file(d, "docs/queue.md").replace("Current batch: 1", "Current batch: 2²⁶"))
        r = queue(d, "ready")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("4\tqueued\tplanned\tlater", r.stdout, "row 4 (batch 2) is ready once batch 2 is current")
        self.assertNotIn("1\t", r.stdout.splitlines()[0][:2], "batch 1 rows are not current")


def read_file(d, rel):
    with open(os.path.join(d, rel), encoding="utf-8") as f:
        return f.read()


BATCHED_MD = """# Queue — Demo
Current batch: 2

## Rules
1. x

## Batch 1

| Id | Item | Depends | Source | Batch | Admitted |
|---|---|---|---|---|---|

## Batch 2

| Id | Item | Depends | Source | Batch | Admitted |
|---|---|---|---|---|---|
| 11 | Auth.js owner sign-in⁵ | 1 | planned | 2 | |
| 13 | Receipt photo deletion¹² | 1 | planned | 2 | |

## Footnotes
¹ host: Vercel (2026-10-16)
¹² deletion closes before promotion (2026-10-16)
"""


TRIAGE_MD = """# Queue — Demo
Current batch: 3

## Rules
1. x

## Batch 1

| Id | Item | Depends | Source | Batch | Admitted |
|---|---|---|---|---|---|
| 14 | Test-DB setup hardening (tests/setup-database.mts; hunter, task 101) | 1 | found | 1 | |
| 16 | Receipt cache lifetime: `put` sets `cacheControl` (src/lib/supabase-receipts.ts; hunter, task 102) | 1 | found | 1 | |

## Batch 2

| Id | Item | Depends | Source | Batch | Admitted |
|---|---|---|---|---|---|
| 18 | Bill page wiring test (src/app/b/[id]/page.tsx; hunter) | 1 | found | 2 | |
| 20 | Share links¹² | 11 | planned | 2 | |

## Batch 3

| Id | Item | Depends | Source | Batch | Admitted |
|---|---|---|---|---|---|
| 25 | CDN purge smoke (owner) | 1 | found | 3 | |
| 30 | Exact calculations | 20 | planned | 3 | |

## Footnotes
¹² deletion closes before promotion (2026-10-16)
"""


class Triage(unittest.TestCase):
    """0.7 (usability plan B5): the first full loop had 18 of 26 open rows `found` and no moment that asked about them.
    Rule 7 as a command: the stale set, grouped by module, the three outcomes as one owner question, and the two
    commands that carry his answer out."""

    def setUp(self):
        self.d = qrepo()
        write(self.d, "docs/queue.md", TRIAGE_MD)
        write(self.d, "docs/queue-archive.md", "# Archive\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 1 | skeleton | | planned | 1 | |\n| 11 | sign-in | 1 | planned | 2 | |\n")

    def test_stale_found_rows_two_batches_old_grouped_by_module_as_one_question(self):
        r = queue(self.d, "triage")
        self.assertEqual(r.returncode, 1, "exit 1: there is something to triage")
        self.assertIn("triage: batch 3 · open found 4 vs planned 2 · stale found (rule 7): 2", r.stdout)
        self.assertIn("found rows outnumber planned ones", r.stdout)
        self.assertIn("## src/lib", r.stdout)
        self.assertIn("## tests/setup-database.mts", r.stdout)
        self.assertIn("- row 14 (entered batch 1", r.stdout)
        self.assertIn("- row 16 (entered batch 1", r.stdout)
        self.assertNotIn("row 18", r.stdout, "batch 2 is one behind, not two")
        self.assertNotIn("row 25", r.stdout)
        self.assertNotIn("row 20", r.stdout, "planned rows are never triaged")
        for word in ("Promote", "Merge into design row", "Delete"):
            self.assertIn(word, r.stdout)
        self.assertEqual(queue(self.d, "triage", "--count").stdout.strip(), "triage: batch 3 · open found 4 vs planned 2 · stale found (rule 7): 2")

    def test_nothing_stale_exits_zero(self):
        write(self.d, "docs/queue.md", TRIAGE_MD.replace("Current batch: 3", "Current batch: 2"))
        r = queue(self.d, "triage")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("nothing to triage", r.stdout)
        self.assertEqual(queue(self.d, "triage", "--count").returncode, 0)

    def test_a_finding_that_may_never_happen_is_noted_not_queued_and_promoted_in_one_step(self):
        # the owner, 2026-10-21: found rows outran their closing (77 of 82 open rows), but nothing important may be dropped
        r = queue(self.d, "note", "Names in join order tie within one ms | cosmetic", "--row", "12")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "n1"), r.stderr)
        self.assertEqual(queue(self.d, "note", "a no-JS double submit orphans one name").stdout.strip(), "n2")
        notes = read_file(self.d, "docs/noted-risks.md")
        self.assertRegex(notes, r"(?m)^- n1 · row 12 · \d{4}-\d{2}-\d{2} · Names in join order tie within one ms / cosmetic$")
        self.assertEqual(queue(self.d, "check").returncode, 0, "the notes file beside the queue keeps check green")
        before = read_file(self.d, "docs/queue.md")
        for risky in ("participant cookies sent site-wide", "a leaked link stays live", "refund amounts round twice", "an attacker floods the join form"):
            r = queue(self.d, "note", risky, "--row", "12")
            self.assertEqual(r.returncode, 1, risky)
            self.assertIn("always a queue row", r.stderr)
        self.assertEqual(read_file(self.d, "docs/queue.md"), before)
        r = queue(self.d, "triage", "--count")
        self.assertIn("noted risks: 2 open (docs/noted-risks.md; promote-note n<k> makes one a row)", r.stdout)
        r = queue(self.d, "promote-note", "n1")
        self.assertEqual(r.returncode, 0, r.stderr)
        rid = r.stdout.strip()
        self.assertRegex(read_file(self.d, "docs/queue.md"), rf"(?m)^\| {rid} \| Names in join order tie within one ms / cosmetic \(noted n1\) \| 12 \| found \| 4 \|", "a found row, the next batch (rule 6)")
        self.assertIn(f"· Names in join order tie within one ms / cosmetic → row {rid}", read_file(self.d, "docs/noted-risks.md"), "kept, marked")
        self.assertEqual(queue(self.d, "promote-note", "n1").returncode, 1, "promoted once")
        self.assertIn("noted risks: 1 open", queue(self.d, "triage", "--count").stdout)

    def test_set_batch_moves_the_row_under_its_new_heading(self):
        r = queue(self.d, "set-batch", "14", "3")
        self.assertEqual(r.returncode, 0, r.stderr)
        q = read_file(self.d, "docs/queue.md")
        b3 = q[q.index("## Batch 3"):q.index("## Footnotes")]
        self.assertIn("| 14 | Test-DB setup hardening", b3)
        self.assertRegex(b3, r"\| 14 \|[^\n]*\| found \| 3 \|")
        self.assertNotIn("| 14 |", q[q.index("## Batch 1"):q.index("## Batch 2")])
        self.assertEqual(queue(self.d, "check").returncode, 0, "the queue is still consistent")
        self.assertIn("triage: batch 3 · open found 4 vs planned 2 · stale found (rule 7): 1", queue(self.d, "triage", "--count").stdout)

    def test_drop_row_deletes_a_queued_row_and_records_the_reason(self):
        self.assertNotEqual(queue(self.d, "drop-row", "16").returncode, 0, "no reason, no deletion")
        r = queue(self.d, "drop-row", "16", "--reason", "storage-js 2.90 caps cacheControl at the signed-URL TTL")
        self.assertEqual(r.returncode, 0, r.stderr)
        q = read_file(self.d, "docs/queue.md")
        self.assertNotIn("| 16 |", q)
        self.assertIn("¹³ row 16 deleted (rule 7): storage-js 2.90 caps cacheControl at the signed-URL TTL — was: Receipt cache lifetime", q)
        self.assertEqual(queue(self.d, "check").returncode, 0)
        # a built row is not dropped: its close-out archives it
        write(self.d, "tasks/1401-a.md", "---\nid: 1401\nfeature: 14\nstatus: pending\n---\n# x\n")
        r = queue(self.d, "drop-row", "14", "--reason", "x")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("only a queued row", r.stderr + r.stdout)


class QueueEdits(unittest.TestCase):
    """0.7: the orchestrator's queue edits (a footnote, a found row, a Depends change) were inline Python heredocs — the
    largest Reef-attributable context share of the first full loop (assistant:tool_use 15%). One command each, shape kept."""

    def setUp(self):
        self.d = qrepo()
        write(self.d, "docs/queue.md", BATCHED_MD)
        write(self.d, "docs/queue-archive.md", "# Archive\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 1 | skeleton²² | | planned | 1 | |\n| 2 | LLM decode | 1 | planned | 1 | |\n\n## Footnotes\n²² no deployment (2026-10-17)\n")

    def test_footnote_takes_the_next_number_across_queue_and_archive_and_marks_the_row(self):
        r = queue(self.d, "footnote", "row 11 wins: owner scoping in the store", "--row", "13")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "²³", "the archive holds ²², so the next is ²³")
        q = read_file(self.d, "docs/queue.md")
        self.assertRegex(q, r"(?m)^²³ row 11 wins: owner scoping in the store \(\d{4}-\d{2}-\d{2}\)$")
        self.assertIn("| 13 | Receipt photo deletion¹²²³ | 1 | planned | 2 | |", q)
        self.assertTrue(q.rstrip().endswith(")"), "appended under ## Footnotes, nothing after")
        self.assertEqual(queue(self.d, "check").returncode, 0, "the queue still parses")
        # a decision its author already dated keeps ONE date (night 2026-10-21: ⁵⁴ read "(2026-10-21) (2026-10-21)")
        queue(self.d, "footnote", "Mahmoud (proxy, night 2026-10-21): keep the confirm (2026-10-21)")
        self.assertRegex(read_file(self.d, "docs/queue.md"), r"(?m)^²⁴ Mahmoud \(proxy, night 2026-10-21\): keep the confirm \(2026-10-21\)$")

    def test_add_row_found_lands_in_the_next_batch_planned_in_the_current_and_set_depends_edits_one_cell(self):
        r = queue(self.d, "add-row", "--item", "Magic-link rate limit (row 11 plan)", "--depends", "11", "--source", "found")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "14")
        q = read_file(self.d, "docs/queue.md")
        self.assertIn("## Batch 3\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 14 | Magic-link rate limit (row 11 plan) | 11 | found | 3 | |", q)
        self.assertLess(q.index("## Batch 3"), q.index("## Footnotes"), "a new batch section sits before the footnotes")
        r = queue(self.d, "add-row", "--item", "Share links", "--depends", "11", "--source", "planned")
        self.assertEqual(r.stdout.strip(), "15")
        q = read_file(self.d, "docs/queue.md")
        self.assertIn("| 15 | Share links | 11 | planned | 2 | |", q, "a planned row joins the current batch's table")
        self.assertLess(q.index("| 13 |"), q.index("| 15 |"))
        r = queue(self.d, "add-row", "--item", "Owner account deletion", "--depends", "11", "--source", "found", "--admitted", "Article IX")
        q = read_file(self.d, "docs/queue.md")
        self.assertIn("| 16 | Owner account deletion | 11 | found | 2 | Article IX |", q, "an admitted found row enters the running batch")
        r = queue(self.d, "set-depends", "13", "1, 2, 11")
        self.assertEqual(r.returncode, 0, r.stderr)
        q = read_file(self.d, "docs/queue.md")
        self.assertIn("| 13 | Receipt photo deletion¹² | 1, 2, 11 | planned | 2 | |", q)
        self.assertEqual(queue(self.d, "check").returncode, 0, "the queue still parses")
        self.assertIn("13\tqueued\tdepends=['1', '2', '11']", queue(self.d, "status").stdout)


class Queue(unittest.TestCase):
    def test_status_derived_from_task_files(self):
        d = qrepo()
        write(d, "tasks/101-a.md", "---\nid: 101\nfeature: 1\nstatus: done\n---\n")
        write(d, "tasks/201-b.md", "---\nid: 201\nfeature: 2\nstatus: in-progress\n---\n")
        out = queue(d, "status").stdout
        self.assertIn("1\tdone", out)
        self.assertIn("2\tbuilding", out)
        self.assertIn("3\tqueued", out)

    def test_ready_respects_depends_batch_and_planned_first(self):
        d = qrepo()
        out = queue(d, "ready").stdout
        self.assertIn("1\tqueued", out)
        self.assertNotIn("2\t", out, "2 depends on 1, which is not done")
        self.assertNotIn("3\t", out, "a found row waits while a planned row is ready")
        self.assertNotIn("4\t", out, "batch 2 is not the current batch")
        write(d, "tasks/101-a.md", "---\nid: 101\nfeature: 1\nstatus: done\n---\n")
        out = queue(d, "ready").stdout
        self.assertIn("2\tqueued", out)
        self.assertNotIn("1\t", out)

    def test_with_found_lists_the_found_rows_after_the_planned_ones(self):
        # 2026-10-23 (qassimha): 89 found rows, none ever ready while a planned row was — a night's contract needs them
        d = qrepo()
        out = queue(d, "ready", "--with-found").stdout.splitlines()
        ids = [l.split("\t")[0] for l in out]
        self.assertIn("3", ids, "the found row is listed")
        self.assertLess(ids.index("1"), ids.index("3"), "planned first")
        self.assertNotIn("2", ids, "dependencies still hold")
        self.assertNotIn("4", ids, "the batch still holds")

    def test_archived_dependency_counts_as_done(self):
        d = qrepo()
        write(d, "docs/queue-archive.md", "| Id | Item | Depends |\n|---|---|---|\n| 0 | old | |\n")
        write(d, "docs/queue.md", QUEUE_MD.replace("| 1 | first | |", "| 1 | first | 0 |"))
        self.assertIn("1\tqueued", queue(d, "ready").stdout)

    def test_check_catches_orphans_duplicates_unknown_depends_and_word_cap(self):
        d = qrepo()
        self.assertEqual(queue(d, "check").returncode, 0)
        write(d, "tasks/901-x.md", "---\nid: 901\nfeature: 9\nstatus: pending\n---\n")
        r = queue(d, "check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("feature: 9 have no queue row", r.stdout)
        write(d, "docs/queue.md", QUEUE_MD + "| 2 | again | 7 | planned | 1 | |\n")
        r = queue(d, "check")
        self.assertIn("row id 2 repeats", r.stdout)
        self.assertIn("unknown row 7", r.stdout)
        write(d, "docs/queue.md", QUEUE_MD + " ".join(["word"] * 300))
        self.assertIn("over writing.queue_words", queue(d, "check").stdout)

    def test_adr_number_renames_and_rewrites_citations(self):
        d = qrepo()
        write(d, "docs/adr/0003-old.md", "# ADR 0003\nStatus: Accepted\n")
        write(d, "docs/adr/draft-12-cache.md", "# cache\nStatus: Accepted (number at merge)\n")
        write(d, "tasks/1201-t.md", "---\nid: 1201\nfeature: 12\nstatus: done\n---\nsee draft-12-cache\n")
        r = queue(d, "adr-number")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(d, "docs", "adr", "0004-cache.md")))
        self.assertFalse(os.path.exists(os.path.join(d, "docs", "adr", "draft-12-cache.md")))
        with open(os.path.join(d, "docs", "adr", "0004-cache.md")) as f:
            self.assertIn("Status: Accepted\n", f.read())
        with open(os.path.join(d, "tasks", "1201-t.md")) as f:
            self.assertIn("see ADR 0004", f.read())
        self.assertEqual(queue(d, "adr-number").returncode, 1, "nothing left to number")

    def test_adr_number_title_and_path_citations(self):
        # 0.7 dogfood: reef-init's draft title reads `# ADR draft-1-x — …`, and a SPEC cites the file by path;
        # numbering produced `# ADR ADR 0001 — …` and a dead `adr/ADR 0001.md` — the close had to fix four spots by hand
        d = qrepo()
        write(d, "docs/adr/draft-1-hosting.md", "# ADR draft-1-hosting — Hosting: one VPS\n\nStatus: Accepted (number at merge)\n")
        write(d, "docs/spec.md", "# spec\nDesign: [hosting](adr/draft-1-hosting.md); see also draft-1-hosting.\n")
        r = queue(d, "adr-number")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(d, "docs", "adr", "0001-hosting.md")) as f:
            title = f.readline()
        self.assertEqual(title, "# ADR 0001 — Hosting: one VPS\n")
        with open(os.path.join(d, "docs", "spec.md")) as f:
            spec = f.read()
        self.assertIn("(adr/0001-hosting.md)", spec, "a path citation still points at a file")
        self.assertIn("see also ADR 0001.", spec)
        self.assertNotIn("ADR ADR", spec)


if __name__ == "__main__":
    unittest.main()
