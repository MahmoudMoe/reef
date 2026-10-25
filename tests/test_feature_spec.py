"""Sabotage suite for 0.6 Phase 2: the feature folder and its SPEC (2.1), the criterion/proof split (2.2),
reef-converge (2.4), the path-class rails and touches (2.5), the hand-back and report checks (2.7).
Every FAIL here is a defect shown red; a 0.5-shaped plan keeps passing."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(ROOT, "scripts", "reef-plan-check.py")
QUEUE = os.path.join(ROOT, "scripts", "reef-queue.py")
TIER = os.path.join(ROOT, "scripts", "reef-tier.py")
CLAIMS = os.path.join(ROOT, "scripts", "reef-claims.py")
CONVERGE = os.path.join(ROOT, "scripts", "reef-converge")

SPEC = """# CSV export for orders — SPEC

Row: 12
Slug: csv-export-for-orders

## Intent
An operator exports the month's orders as CSV. The file opens in a spreadsheet.

## Grill
- Q: which delimiter — A: comma, RFC 4180

## Scope
One command writes one file.

## Non-goals
Scheduling.

## Already shipped
none

## Requirements
- FR-1 [backend]: `export_csv(month)` writes one RFC 4180 file with a header row.
- FR-2 [frontend]: the CLI prints the path it wrote.
- FR-3 [data]: amounts keep two decimals.

## Success criteria
- SC-1: the file opens in LibreOffice without a wizard.

## Owner decisions
- comma, never semicolon (2026-10-16)

## Architecture impact
container `cli` only.
"""

TASK_NEW = """---
id: 1201
feature: csv-export-for-orders
status: pending
complexity: mech
effort: medium
blocked-by: []
resources: []
tier: light
touches: []
verify: gate-only
attempts: 0
dispatches: 0
last_failure_sig: ""
---
# 1201 — write the CSV

## Scope
The exporter writes the file. Short sentences only.

## Acceptance Criteria
- AC-1 (FR-1): the file has a header row and one line per order.
- AC-2 (FR-3): every amount shows two decimals.

## Proof
| AC | Proof |
|---|---|
| AC-1 | `test_csv_header_and_rows` |
| AC-2 | `test_csv_two_decimals` |

## Out of scope

## Log
"""


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def project(flat_tasks=None, version="0.6.0", cfg=None):
    d = tempfile.mkdtemp(prefix="reef-p2.")
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    write(d, ".reef/config.json", json.dumps(cfg or {"gates": {"test": "true"}, "paths": {"features": "reef/features"}}))
    if version:
        write(d, ".reef/version", version + "\n")
    write(d, "CLAUDE.md", "# brief\n")
    write(d, "docs/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 12 | csv export for orders | | planned | 1 | |\n")
    os.makedirs(os.path.join(d, "tasks", "done"))
    for name, text in (flat_tasks or {}).items():
        write(d, f"tasks/{name}", text)
    return d


def feature(d, slug="csv-export-for-orders", spec=SPEC, tasks=None):
    base = f"reef/features/{slug}"
    if spec is not None:
        write(d, f"{base}/SPEC.md", spec)
    os.makedirs(os.path.join(d, base, "tasks", "done"), exist_ok=True)
    for name, text in (tasks if tasks is not None else {"1201-write-csv.md": TASK_NEW}).items():
        write(d, f"{base}/tasks/{name}", text)
    return os.path.join(d, base)


class VerdictSummary(unittest.TestCase):
    """The orchestrator reads a judge's verdict, not its report (the owner's go, 2026-10-24, item 5: the trial night's
    orchestrator read 64,000 characters of full reports, each re-read at every later step)."""

    def test_the_summary_keeps_the_verdict_blockers_failures_and_findings(self):
        d = tempfile.mkdtemp(prefix="reef-verdict.")
        report = write(d, "r.md", "RUN: agent=verifier task=1201\nRULE AC1: PASS iff the header row; FAIL if not\n"
                                  "RULE AC2: PASS iff two decimals; FAIL if not\nlong evidence paragraph\n" * 3 +
                                  "AC1 PASS — test_csv_header_and_rows\nAC2 FAIL — 2.5 printed as 2.5\n"
                                  "BLOCKER: correctness — amounts lose a decimal (export.py:2)\nNEW-ROW: CSV of refunds\n"
                                  "NOTED: a 10,000-row month is slow\nVERDICT: FAIL\n")
        r = subprocess.run([sys.executable, CLAIMS, "verdict", report], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        out = r.stdout
        for kept in ("RUN: agent=verifier task=1201", "AC2 FAIL", "BLOCKER: correctness", "NEW-ROW: CSV of refunds",
                     "NOTED: a 10,000-row month", "VERDICT: FAIL"):
            self.assertIn(kept, out)
        for dropped in ("RULE AC1", "AC1 PASS", "long evidence paragraph"):
            self.assertNotIn(dropped, out)
        self.assertIn("lines in", out, "the full report's path and length, for a blocker's detail")
        passed = write(d, "p.md", "RUN: agent=verifier task=1201\nAC1 PASS — t\nVERDICT: PASS\n")
        self.assertEqual(subprocess.run([sys.executable, CLAIMS, "verdict", passed], capture_output=True, text=True).returncode, 0)
        bare = write(d, "b.md", "no verdict here\n")
        self.assertEqual(subprocess.run([sys.executable, CLAIMS, "verdict", bare], capture_output=True, text=True).returncode, 2)


class JournalAtClose(unittest.TestCase):
    """2026-10-24, the trial: two features both appended to the journal, their PRs conflicted on it, and a hand-resolved
    conflict led to a GREEN re-recorded with no review. A feature branch never edits the journal: each task's journal
    block sits in its task file's Log, and `reef-queue.py journal <slug>` copies them on the base at the row's close."""

    def test_the_close_copies_each_tasks_block_once(self):
        d = project()
        block = "<!-- journal -->\n| Task | Result |\n|---|---|\n| 1201-write-csv | PASS |\n- **Verified, and how**: the gate.\n<!-- /journal -->\n"
        feature(d, tasks={"1201-write-csv.md": TASK_NEW + "- attempt 1 PASS\n" + block,
                          "1202-two-decimals.md": TASK_NEW.replace("id: 1201", "id: 1202").replace("# 1201", "# 1202")})
        write(d, "docs/journal.md", "# Journal\n")
        q = lambda: subprocess.run([sys.executable, QUEUE, "journal", "csv-export-for-orders", "--repo", d], capture_output=True, text=True)
        r = q()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("journal: 1 block(s) appended", r.stdout)
        j = open(os.path.join(d, "docs", "journal.md")).read()
        self.assertIn("| 1201-write-csv | PASS |", j)
        self.assertNotIn("<!-- journal -->", j, "the markers stay in the task file")
        self.assertIn("journal: 0 block(s) appended, 1 already there", q().stdout)
        self.assertEqual(open(os.path.join(d, "docs", "journal.md")).read(), j, "a second close appends nothing")
        self.assertEqual(subprocess.run([sys.executable, QUEUE, "journal", "no-such-feature", "--repo", d], capture_output=True, text=True).returncode, 1)

    def test_the_task_skill_never_edits_the_journal_on_a_feature_branch(self):
        task = open(os.path.join(ROOT, "skills", "reef-task", "SKILL.md"), encoding="utf-8").read()
        loop = open(os.path.join(ROOT, "skills", "reef-loop", "SKILL.md"), encoding="utf-8").read()
        self.assertIn("never edit `paths.runlog` on a feature branch", task)
        self.assertIn("<!-- journal -->", task)
        self.assertIn("reef-queue.py journal <slug>", loop)


class ReadFirst(unittest.TestCase):
    # 2026-10-24, the owner's go (the read-first trial): implementers spent a median 17.5 tool calls exploring before
    # their first edit (38 qassimha runs). The planner lists the ranges it read; the check proves each one is real.
    SRC = "def helper():\n    return 1\n\n\ndef settle_bill(total):\n    return round(total, 2)\n"

    def run_with(self, entries):
        d = project()
        write(d, "src/bill.py", self.SRC)
        write(d, "node_modules/x/index.js", "settle_bill\n")
        body = "## Read first\n" + "".join(f"- {e}\n" for e in entries) + "\n## Acceptance Criteria"
        feature(d, tasks={"1201-write-csv.md": TASK_NEW.replace("## Acceptance Criteria", body, 1)})
        return check(d)

    def test_ranges_the_planner_read_pass(self):
        r = self.run_with(["`src/bill.py:5-6` (settle_bill) — the rounding to change", "`src/bill.py:1-2` (helper) — the shape to copy"])
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("read first: 2 entries, each range holds its symbol", r.stdout)

    def test_a_task_without_the_section_still_passes(self):
        r = self.run_with([])
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_an_entry_that_is_not_real_fails(self):
        cases = {
            "`src/bill.py:1-2` (settle_bill) — x": "settle_bill is not in src/bill.py:1-2",
            "`src/bill.py:5-60` (settle_bill) — x": "src/bill.py:5-60 is not a range within its 6 lines",
            "`src/bill.py:6-5` (settle_bill) — x": "src/bill.py:6-5 is not a range within its 6 lines",
            "`src/gone.py:1-2` (helper) — x": "src/gone.py does not exist",
            "`node_modules/x/index.js:1-1` (settle_bill) — x": "node_modules/x/index.js is a dependency or build path",
            "`../outside.py:1-1` (x) — x": "../outside.py is outside the project",
            "src/bill.py lines 5-6 — x": "not `path:start-end` (symbol) — why",
        }
        for entry, msg in cases.items():
            with self.subTest(entry=entry):
                r = self.run_with([entry])
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn(msg, r.stdout)
        r = self.run_with(["`src/bill.py:5-6` (settle_bill) — x"] * 9)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("9 Read first entries > 8", r.stdout)


class KeysCheckedInTheirOwnFolder(unittest.TestCase):
    # 2026-10-24, qassimha row 18: the key check read the folder of the LAST task file (a stale loop variable), so every
    # feature's citations were checked against the last-sorted folder: 15 false FAILs on other features' tasks, and a key
    # defined only in that folder passed anywhere.
    def two_features(self, first_task):
        d = project()
        write(d, "docs/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n"
              "| 12 | csv export for orders | | planned | 1 | |\n| 13 | zz receipt notes | | planned | 1 | |\n")
        feature(d, tasks={"1201-write-csv.md": first_task})
        spec = SPEC.replace("Row: 12", "Row: 13").replace("Slug: csv-export-for-orders", "Slug: zz-receipt-notes")
        spec = spec.replace("- FR-3 [data]: amounts keep two decimals.\n", "- FR-4 [data]: a note keeps its line breaks.\n")
        task = TASK_NEW.replace("id: 1201", "id: 1301").replace("feature: csv-export-for-orders", "feature: zz-receipt-notes")
        task = task.replace("# 1201", "# 1301").replace("(FR-3)", "(FR-4)").replace("test_csv_", "test_notes_")
        feature(d, slug="zz-receipt-notes", spec=spec, tasks={"1301-keep-notes.md": task})
        return check(d)

    def test_a_key_defined_in_its_own_folder_passes(self):
        r = self.two_features(TASK_NEW)
        self.assertNotIn("not defined in this feature folder", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_a_key_defined_only_in_another_folder_fails(self):
        r = self.two_features(TASK_NEW.replace("(FR-3)", "(FR-4)"))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("cites FR-4 which is not defined in this feature folder", r.stdout)


TASK_REFACTOR = TASK_NEW.replace("id: 1201", "id: 1301").replace("attempts: 0\n", "attempts: 0\nkind: refactor\nsplits: src/big.py under 400 lines\n") \
    .replace("| AC-1 | `test_csv_header_and_rows` |\n| AC-2 | `test_csv_two_decimals` |", "| AC-1 | `true` |\n| AC-2 | `true` |")


class RefactorPreservesBehaviour(unittest.TestCase):
    """0.7.2 (ai-coach, item 15): a `kind: refactor` task's diff may move code and imports, never change an assertion line of an
    existing test; the full gate must be green. Deterministic, in reef-converge."""

    def branch(self, test_text):
        d = project(cfg={"gates": {"full": "true"}, "paths": {"features": "reef/features"}, "branches": {"base": "main"}})
        shutil.copy(os.path.join(ROOT, "scripts", "reef-gate.sh"), os.path.join(d, "scripts", "reef-gate.sh")) if os.path.isdir(os.path.join(d, "scripts")) else (
            os.makedirs(os.path.join(d, "scripts")), shutil.copy(os.path.join(ROOT, "scripts", "reef-gate.sh"), os.path.join(d, "scripts", "reef-gate.sh")))
        write(d, "src/big.py", "import os\n\ndef add(a, b):\n    return a + b\n")
        write(d, "tests/test_big.py", "import os\nfrom src.big import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n    assert add(0, 0) == 0\n")
        git = lambda *a: subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True, capture_output=True)
        git("add", "-A"); git("commit", "-qm", "base")
        git("checkout", "-qb", "feat/split")
        write(d, "tests/test_big.py", test_text)
        write(d, "src/small.py", "def add(a, b):\n    return a + b\n")
        git("add", "-A"); git("commit", "-qm", "split")
        feature(d, tasks={"1301-split-big.md": TASK_REFACTOR})
        return subprocess.run([sys.executable, CONVERGE, "csv-export-for-orders", "--repo", d, "--base", "main", "--dry-run"], capture_output=True, text=True)

    def test_an_edited_assertion_is_red_and_moved_code_with_new_imports_is_green(self):
        r = self.branch("import os\nfrom src.small import add\n\n\ndef test_add():\n    assert add(1, 2) == 4\n    assert add(0, 0) == 0\n")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("1301-split-big.md refactor: contradicts — tests/test_big.py changes an assertion line (1 removed, 1 added)", r.stdout)
        r = self.branch("import sys\nimport os\nfrom src.small import add\n\n\ndef test_add():\n    assert add(0, 0) == 0\n    assert add(1, 2) == 3\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Converged", r.stdout)


class ProofWritersWarn(unittest.TestCase):
    def test_a_proof_that_writes_files_names_the_mechanic(self):
        # first contact (2026-10-16): the read-only verifier could not run AC-4/AC-10 (they write .env files and delete
        # the generated client); the orchestrator ran them itself. The plan should say who runs such a row.
        d = project()
        feature(d, tasks={"1201-write-csv.md": TASK_NEW.replace("| AC-2 | `test_csv_two_decimals` |", "| AC-2 | `rm -f .env .env.local && npm test` |")})
        r = check(d)
        self.assertIn("WARN", r.stdout)
        self.assertIn("Proof for AC-2 writes files", r.stdout)
        self.assertIn("[mechanic]", r.stdout)
        d = project()
        feature(d, tasks={"1201-write-csv.md": TASK_NEW.replace("| AC-2 | `test_csv_two_decimals` |", "| AC-2 | [mechanic] `rm -f .env .env.local && npm test` |")})
        self.assertNotIn("WARN", check(d).stdout)


def check(d, *args):
    return subprocess.run([sys.executable, CHECK, d, *args], capture_output=True, text=True)


def fails(r):
    return [l for l in r.stdout.splitlines() if l.startswith("FAIL") or l.startswith("warning")]


class QueueHasOneHome(unittest.TestCase):
    def test_queue_rows_added_on_a_feature_branch_fail_and_a_feature_merely_behind_passes(self):
        # first contact (2026-10-16): /reef-plan committed the roadmap (rows 2–15) with the spec on feat/…; the tick reads
        # the main checkout's queue and never saw them. The check compares against the fork point, not the base's head.
        d = project(cfg={"gates": {"test": "true"}, "paths": {"features": "reef/features"}, "branches": {"base": "main"}})
        feature(d)
        g = lambda *a: subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *a], capture_output=True, text=True)
        write(d, ".gitignore", "tasks/.plan-review.json\n")
        g("add", "-A"); g("commit", "-qm", "base")
        g("checkout", "-q", "-b", "feat/csv-export-for-orders")
        r = check(d)
        self.assertEqual(r.returncode, 0, r.stdout)
        with open(os.path.join(d, "docs/queue.md"), "a", encoding="utf-8") as f:
            f.write("| 13 | pdf export | 12 | planned | 1 | |\n")
        r = check(d)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("docs/queue.md: changed on feat/csv-export-for-orders", r.stdout)
        self.assertIn("git checkout main -- docs/queue.md", r.stdout)
        g("checkout", "--", "docs/queue.md")
        g("checkout", "-q", "main")
        with open(os.path.join(d, "docs/queue.md"), "a", encoding="utf-8") as f:
            f.write("| 13 | pdf export | 12 | planned | 1 | |\n")
        g("add", "-A"); g("commit", "-qm", "row 13 on the base")
        g("checkout", "-q", "feat/csv-export-for-orders")
        r = check(d)
        self.assertEqual(r.returncode, 0, "a feature behind the base is not blamed for the base's new row:\n" + r.stdout)
        self.assertNotIn("changed on", r.stdout)


class FeatureFolder(unittest.TestCase):
    def test_fresh_06_project_without_tasks_dir_gets_its_stamp(self):
        # 0.7: reef-init on a fresh 0.6 project creates no tasks/ (tasks live in the feature folder); the
        # stamp still lives at <paths.tasks>/.plan-review.json, so the check must create its home or the
        # first plan check of every new project dies with ENOENT after reporting 0 failures
        import shutil
        d = project()
        feature(d)
        shutil.rmtree(os.path.join(d, "tasks"))
        r = check(d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("internal error", r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(d, "tasks", ".plan-review.json")), "the stamp was written")

    def test_well_formed_feature_passes_and_is_06_planned(self):
        d = project()
        feature(d)
        r = check(d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("feature folder (slug, SPEC.md keys 4, 1 tasks)", r.stdout)
        r = check(d, "--verify-stamp", "--feature", "csv-export-for-orders")
        self.assertEqual(r.returncode, 1, "a folder feature is 0.6-planned: the approval is enforced")
        self.assertIn("approval: MISSING", r.stdout)

    def test_missing_key_and_missing_spec_fail(self):
        d = project()
        feature(d, tasks={"1201-write-csv.md": TASK_NEW.replace("(FR-3)", "(FR-9)")})
        r = check(d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("cites FR-9 which is not defined", r.stdout)
        d = project()
        feature(d, spec=None)
        r = check(d)
        self.assertIn("no SPEC.md", r.stdout)
        d = project()
        feature(d, tasks={"1201-write-csv.md": TASK_NEW.replace("- AC-2 (FR-3):", "- AC-2:")})
        self.assertIn("cites no FR-n/SC-n key", check(d).stdout)

    def test_spec_edit_stales_the_stamp(self):
        d = project()
        fdir = feature(d)
        self.assertEqual(check(d).returncode, 0)
        digest1 = check(d, "--digest", "--feature", "csv-export-for-orders").stdout.split()[-1]
        with open(os.path.join(fdir, "SPEC.md"), "a") as f:
            f.write("- FR-4 [infra]: a new requirement.\n")
        digest2 = check(d, "--digest", "--feature", "csv-export-for-orders").stdout.split()[-1]
        self.assertNotEqual(digest1, digest2, "the digest covers the whole feature folder")
        r = check(d, "--verify-stamp", "--feature", "csv-export-for-orders")
        self.assertIn("STALE", r.stdout)

    def test_thirteen_tasks_demand_a_split(self):
        d = project()
        tasks = {}
        for i in range(1, 14):
            tasks[f"12{i:02d}-t{i}.md"] = TASK_NEW.replace("id: 1201", f"id: 12{i:02d}").replace("`test_csv_header_and_rows`", f"`test_h{i}`").replace("`test_csv_two_decimals`", f"`test_d{i}`")
        feature(d, tasks=tasks)
        r = check(d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("13 tasks > plan.max_tasks 12 — split", r.stdout)

    def test_bad_slugs_refused(self):
        for slug in ("export", "misc-stuff", "1201", "Csv-Export", "a-b-c-d-e-f"):
            with self.subTest(slug=slug):
                d = project()
                feature(d, slug=slug, spec=SPEC.replace("csv-export-for-orders", slug), tasks={"1201-write-csv.md": TASK_NEW.replace("feature: csv-export-for-orders", f"feature: {slug}")})
                self.assertIn("feature slug", check(d).stdout)
                r = subprocess.run([sys.executable, QUEUE, "check", "--repo", d], capture_output=True, text=True)
                self.assertEqual(r.returncode, 1, slug)
                self.assertIn("feature slug", r.stdout)

    def test_markdown_outside_a_feature_folder_fails_the_structure_check(self):
        d = project()
        feature(d)
        write(d, "reef/features/notes.md", "# stray\n")
        self.assertIn("outside a feature folder", check(d).stdout)
        r = subprocess.run([sys.executable, QUEUE, "check", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("outside any feature folder", r.stdout)
        os.unlink(os.path.join(d, "reef", "features", "notes.md"))
        write(d, "reef/features/csv-export-for-orders/plan.md", "no plan.md in 0.6\n")
        self.assertIn("does not belong in a feature folder", check(d).stdout)

    def test_index_generated_deterministically(self):
        d = project()
        feature(d)
        r = subprocess.run([sys.executable, QUEUE, "index", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        idx = os.path.join(d, "reef", "features", "README.md")
        with open(idx) as f:
            text = f.read()
        self.assertIn("| [csv-export-for-orders](csv-export-for-orders/SPEC.md) | 12 | 1 | building | 0/1 |", text)
        r = subprocess.run([sys.executable, QUEUE, "index", "--repo", d], capture_output=True, text=True)
        self.assertIn("unchanged", r.stdout)
        self.assertEqual(check(d).returncode, 0, "the generated README is allowed in the features dir")

    def test_adr_numbering_is_one_global_sequence(self):
        d = project()
        fdir = feature(d)
        write(d, "reef/architecture/adr/0003-stack.md", "# ADR 0003\nStatus: Accepted\n")
        write(d, f"{fdir}/adr/draft-12-csv-shape.md", "# csv\nStatus: Accepted (number at merge)\n")
        r = subprocess.run([sys.executable, QUEUE, "adr-number", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(fdir, "adr", "0004-csv-shape.md")), r.stdout)

    def test_pre_06_flat_project_only_warns(self):
        old = TASK_NEW.replace("tier: light\ntouches: []\n", "tier: light\n").replace("## Proof\n| AC | Proof |\n|---|---|\n| AC-1 | `test_csv_header_and_rows` |\n| AC-2 | `test_csv_two_decimals` |\n\n", "")
        old = old.replace("- AC-1 (FR-1): the file has a header row and one line per order.", "- the file has a header row — test_csv_header_and_rows").replace(
            "- AC-2 (FR-3): every amount shows two decimals.", "- two decimals — test_csv_two_decimals. " + "This sentence is deliberately far too long to pass the twenty five word rule of the new writing lint in Reef point six and should only warn here.")
        d = project(flat_tasks={"1201-write-csv.md": old}, version=None)
        r = check(d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(any("warning" in l and "sentence" in l for l in r.stdout.splitlines()), r.stdout)


class ProofSplit(unittest.TestCase):
    def test_new_shape_embedding_a_test_name_fails_old_shape_passes(self):
        d = project()
        feature(d, tasks={"1201-write-csv.md": TASK_NEW.replace("- AC-1 (FR-1): the file has a header row and one line per order.", "- AC-1 (FR-1): the file has a header row — test_csv_header_and_rows")})
        r = check(d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("embeds its proof", r.stdout)
        d = project()
        feature(d, tasks={"1201-write-csv.md": TASK_NEW.replace("| AC-2 | `test_csv_two_decimals` |\n", "")})
        self.assertIn("has no ## Proof row", check(d).stdout)
        d = project(flat_tasks={"001-old.md": TASK_NEW.replace("id: 1201", "id: 1").replace("feature: csv-export-for-orders", "feature: old").replace("## Proof\n| AC | Proof |\n|---|---|\n| AC-1 | `test_csv_header_and_rows` |\n| AC-2 | `test_csv_two_decimals` |\n\n", "").replace(
            "- AC-1 (FR-1): the file has a header row and one line per order.", "- AC-1: header row — test_csv_header_and_rows").replace("- AC-2 (FR-3): every amount shows two decimals.", "- AC-2: two decimals — test_csv_two_decimals")})
        self.assertEqual(check(d).returncode, 0, check(d).stdout)

    def test_proof_rows_feed_the_claimed_twice_check(self):
        d = project()
        feature(d, tasks={"1201-a.md": TASK_NEW, "1202-b.md": TASK_NEW.replace("id: 1201", "id: 1202").replace("`test_csv_two_decimals`", "`test_other`")})
        r = check(d)
        self.assertIn("test name claimed by two task files", r.stdout)
        self.assertIn("test_csv_header_and_rows", r.stdout)

    def test_long_sentence_and_long_criterion_fail_under_06(self):
        d = project()
        long_ac = "- AC-1 (FR-1): " + " ".join(["word"] * 55) + "."
        feature(d, tasks={"1201-write-csv.md": TASK_NEW.replace("- AC-1 (FR-1): the file has a header row and one line per order.", long_ac)})
        r = check(d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("criterion over writing.criterion_words 50", r.stdout)
        d = project()
        feature(d, tasks={"1201-write-csv.md": TASK_NEW.replace("The exporter writes the file.", "The exporter " + "writes and writes " * 14 + "the file.")})
        r = check(d)
        self.assertIn("sentence(s) over writing.sentence_words 25", r.stdout)


class Rails(unittest.TestCase):
    def test_touches_force_the_tier_and_migration_needs_rollback(self):
        d = project()
        feature(d, tasks={"1201-write-csv.md": TASK_NEW.replace("touches: []", "touches: [pii]")})
        r = check(d)
        self.assertIn("touches ['pii'] forces tier critical", r.stdout)
        d = project()
        t = TASK_NEW.replace("touches: []", "touches: [migration]").replace("tier: light", "tier: design").replace("complexity: mech", "complexity: design").replace("verify: gate-only", "verify: judge").replace("## Scope\n", "## Decision\nAdd the column.\n\n## Scope\n")
        feature(d, tasks={"1201-write-csv.md": t})
        r = check(d)
        self.assertIn("requires a `Rollback:` line", r.stdout)
        feature(d, tasks={"1201-write-csv.md": t.replace("Add the column.", "Add the column.\nRollback: drop the column.")})
        self.assertNotIn("Rollback", check(d).stdout)

    def test_one_line_diff_under_auth_tiered_light_is_refused(self):
        d = tempfile.mkdtemp(prefix="reef-rail.")
        g = lambda *a: subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True, capture_output=True)
        subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
        write(d, ".reef/config.json", json.dumps({"tiers": {"light": {"allow": ["**"], "max_lines": 80}, "design": {"paths": ["**/auth/**"]}, "critical": {"paths": [".githooks/**", "scripts/reef-*"]}}}))
        write(d, "src/auth/token.py", "a = 1\n")
        write(d, "scripts/reef-gate.sh", "echo gate\n")
        g("add", "-A"); g("commit", "-qm", "base"); g("checkout", "-qb", "feat")
        write(d, "src/auth/token.py", "a = 2\n")
        g("commit", "-qam", "touch auth")
        t = write(d, "tasks/001-t.md", "---\nid: 1\nfeature: 1\nstatus: pending\ntier: light\n---\n# 1\n")
        r = subprocess.run([sys.executable, TIER, t, "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("computed design", r.stdout)
        self.assertIn("matches tiers.design.paths", r.stdout)
        write(d, "scripts/reef-gate.sh", "echo changed\n")
        g("commit", "-qam", "touch the guard")
        r = subprocess.run([sys.executable, TIER, t, "--repo", d], capture_output=True, text=True)
        self.assertIn("computed critical", r.stdout)
        write(d, "tasks/001-t.md", "---\nid: 1\nfeature: 1\nstatus: pending\ntier: critical\n---\n# 1\n")
        self.assertEqual(subprocess.run([sys.executable, TIER, t, "--repo", d], capture_output=True, text=True).returncode, 0)
        write(d, "tasks/001-t.md", "---\nid: 1\nfeature: 1\nstatus: pending\ntier: full\ntouches: [money]\n---\n# 1\n")
        r = subprocess.run([sys.executable, TIER, t, "--repo", d], capture_output=True, text=True)
        self.assertIn("computed critical", r.stdout)
        write(d, "scripts/reef-gate.sh", "echo gate\n")
        g("commit", "-qam", "guard back")
        r = subprocess.run([sys.executable, TIER, t, "--repo", d], capture_output=True, text=True)
        self.assertIn("touches: money -> critical", r.stdout, "the touch alone forces critical")


class HandbackAndReport(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-hb.")
        write(self.d, ".reef/config.json", json.dumps({"writing": {"handback_words": 150}}))
        self.task = write(self.d, "tasks/1201-write-csv.md", TASK_NEW)

    def claims(self, *args):
        return subprocess.run([sys.executable, CLAIMS, *args, "--repo", self.d], capture_output=True, text=True)

    def test_200_word_handback_fails_short_one_with_claims_passes(self):
        hb = write(self.d, "hb.md", "RUN: agent=implementer task=1201\n" + " ".join(["word"] * 200) + "\nthe header is written — true at export.py:12\n")
        r = self.claims("check", "--handback", hb)
        self.assertEqual(r.returncode, 1)
        self.assertIn("words > writing.handback_words 150", r.stdout)
        hb = write(self.d, "hb2.md", "RUN: agent=implementer task=1201\nWrote export.py; 2 tests OK.\nthe header is written — true at export.py:12\n")
        self.assertEqual(self.claims("check", "--handback", hb).returncode, 0)
        hb = write(self.d, "hb3.md", "RUN: agent=implementer task=1201\nall good\n")
        self.assertIn("no claims list", self.claims("check", "--handback", hb).stdout)
        with open(self.task) as f:
            self.assertIn("attempts: 0", f.read(), "a rejected hand-back consumes no attempt")

    def test_round_two_report_carries_unnamed_criteria_under_the_gate(self):
        # 0.7: a fix round judges the criteria the failure named; the rest are carried with round 1's test and the gate
        head = ("RUN: agent=verifier task=1201 round=2\nREJUDGE: AC-2\n"
                "RULE AC1: PASS iff test_csv_header_and_rows is green; FAIL otherwise\n"
                "RULE AC2: PASS iff test_csv_two_decimals asserts 2 decimals; FAIL otherwise\n")
        good = head + "GATE: scripts/reef-gate.sh full exit 0 on snapshot 0a4d78e9\nAC1 PASS (carried: round 1, `test_csv_header_and_rows`; gate exit 0)\nAC2 PASS — tests/test_export.py:40 asserts 2 decimals, test_csv_two_decimals\nVERDICT: PASS\n"
        r = self.claims("report", write(self.d, "r2.md", good), "--task", self.task)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("1 carried from round 1 under the gate", r.stdout)
        no_gate = good.replace("GATE: scripts/reef-gate.sh full exit 0 on snapshot 0a4d78e9\n", "")
        r = self.claims("report", write(self.d, "r3.md", no_gate), "--task", self.task)
        self.assertEqual(r.returncode, 1)
        self.assertIn("carried verdicts need a `GATE:", r.stdout)
        no_test = good.replace("AC1 PASS (carried: round 1, `test_csv_header_and_rows`; gate exit 0)", "AC1 PASS (carried from round 1)")
        r = self.claims("report", write(self.d, "r4.md", no_test), "--task", self.task)
        self.assertEqual(r.returncode, 1)
        self.assertIn("AC1 is not in REJUDGE: its verdict must read `carried` and name round 1's test", r.stdout)
        round1 = good.replace("round=2", "round=1")
        r = self.claims("report", write(self.d, "r5.md", round1), "--task", self.task)
        self.assertNotIn("carried from round 1", r.stdout, "round 1 carries nothing: REJUDGE is read on round >= 2 only")

    def test_report_needs_rules_citing_proof_rows_and_evidence(self):
        good = ("RUN: agent=verifier task=1201\nRULE AC1: PASS iff test_csv_header_and_rows is green; FAIL otherwise\n"
                "RULE AC2: PASS iff test_csv_two_decimals asserts 2 decimals; FAIL otherwise\n"
                "AC1 PASS — tests/test_export.py:12 asserts the header\nAC2 PASS — test_csv_two_decimals, 2 tests OK\nVERDICT: PASS\n")
        rp = write(self.d, "r.md", good)
        r = self.claims("report", rp, "--task", self.task)
        self.assertEqual(r.returncode, 0, r.stdout)
        rp = write(self.d, "r2.md", good.replace("AC2 PASS — test_csv_two_decimals, 2 tests OK", "AC2 PASS — looks fine"))
        r = self.claims("report", rp, "--task", self.task)
        self.assertEqual(r.returncode, 1)
        self.assertIn("AC2 verdict carries no evidence", r.stdout)
        rp = write(self.d, "r3.md", good.replace("RULE AC2: PASS iff test_csv_two_decimals asserts 2 decimals; FAIL otherwise\n", ""))
        self.assertIn("no `RULE AC2:` line", self.claims("report", rp, "--task", self.task).stdout)
        rp = write(self.d, "r4.md", good.replace("RULE AC1: PASS iff test_csv_header_and_rows is green", "RULE AC1: PASS iff it works"))
        r = self.claims("report", rp, "--task", self.task)
        self.assertEqual(r.returncode, 0, "0.7: a missing Proof citation is a note, never a rewrite round")
        self.assertIn("note: RULE AC1 does not cite its Proof row", r.stdout)

    def test_report_words_cap_is_set_and_enforced(self):
        # 0.7: four real reports measured 538-706 words for 6-7 criteria (docs/perf/dogfood-2026-10-16.md §E); the cap
        # was 900 — and on 2026-10-18 the owner switched every word budget off (a rewrite round cost 9 minutes): the
        # template ships 0, a project that sets a number gets it enforced, not warned about
        with open(os.path.join(ROOT, "templates", "config.json")) as f:
            self.assertEqual(json.load(f)["writing"]["report_words"], 0)
        write(self.d, ".reef/config.json", json.dumps({"gates": {"full": "true"}, "paths": {"features": "reef/features"},
                                                        "writing": {"report_words": 900}}))
        head = ("RUN: agent=verifier task=1201\nRULE AC1: PASS iff test_csv_header_and_rows is green; FAIL otherwise\n"
                "RULE AC2: PASS iff test_csv_two_decimals asserts 2 decimals; FAIL otherwise\n"
                "AC1 PASS — tests/test_export.py:12 asserts the header\nAC2 PASS — test_csv_two_decimals, 2 tests OK\n")
        long = write(self.d, "long.md", head + " ".join(["evidence"] * 1000) + "\nVERDICT: PASS\n")
        r = self.claims("report", long, "--task", self.task)
        self.assertEqual(r.returncode, 1)
        self.assertIn("words (RULE lines free) > writing.report_words 900", r.stdout)
        fine = write(self.d, "fine.md", head + " ".join(["evidence"] * 600) + "\nVERDICT: PASS\n")
        self.assertEqual(self.claims("report", fine, "--task", self.task).returncode, 0)

    def test_report_budget_frees_rule_lines_and_grows_with_criteria(self):
        # first contact (2026-10-16): a 15-criterion task's honest verifier report ran 1693 words (≈650 of them the RULE
        # lines the contract demands) against a cap measured on 6-7 criteria, and was rejected into a rewrite round
        write(self.d, ".reef/config.json", json.dumps({"gates": {"full": "true"}, "paths": {"features": "reef/features"},
                                                        "writing": {"report_words": 900}}))
        n = 15
        acs = "".join(f"- AC-{i} (FR-1): criterion {i} holds.\n" for i in range(1, n + 1))
        proof = "".join(f"| AC-{i} | `test_c{i}` |\n" for i in range(1, n + 1))
        task = write(self.d, "t15.md", "---\nid: 1202\nstatus: pending\n---\n# t\n\n## Acceptance Criteria\n" + acs +
                     "\n## Proof\n| AC | Proof |\n|---|---|\n" + proof)
        rules = "".join(f"RULE AC{i}: PASS iff test_c{i} is green " + " ".join(["and"] * 40) + "; FAIL otherwise\n" for i in range(1, n + 1))
        verdicts = "".join(f"AC{i} PASS — tests/t.py:{i} test_c{i}\n" for i in range(1, n + 1))
        body = " ".join(["evidence"] * 1000)   # 1000 + ~90 words of verdicts: over 900, under 900 + 40×7 = 1180
        r = self.claims("report", write(self.d, "r15.md", f"RUN: agent=verifier task=1202\n{rules}{verdicts}{body}\nVERDICT: PASS\n"), "--task", task)
        self.assertEqual(r.returncode, 0, r.stdout)
        body = " ".join(["evidence"] * 1200)
        r = self.claims("report", write(self.d, "r15b.md", f"RUN: agent=verifier task=1202\n{rules}{verdicts}{body}\nVERDICT: PASS\n"), "--task", task)
        self.assertEqual(r.returncode, 1)
        self.assertIn("(RULE lines free) > writing.report_words 900 + 280 (15 criteria)", r.stdout)

    def test_hunter_report_has_its_own_shape(self):
        # 0.7 dogfood: reef-task sends the hunter's report through `report`, which demanded RULE AC lines the hunter
        # never writes (its shape is DEFECT / BLOCKER / NEW-ROW / NONE / VERDICT) — every live hunter report was rejected
        good = ("RUN: agent=loophole-hunter task=1201 pass=guard\nDEFECT: a row the header does not cover is exported silently\n"
                "NEW-ROW: a BOM header — possible, not now — queue it\nNONE: tried an empty file; refused at export.py:9\nVERDICT: PASS\n")
        rp = write(self.d, "h.md", good)
        r = self.claims("report", rp, "--task", self.task)
        self.assertEqual(r.returncode, 0, r.stdout)
        rp = write(self.d, "h2.md", good.replace("VERDICT: PASS", "VERDICT: FAIL"))
        r = self.claims("report", rp, "--task", self.task)
        self.assertEqual(r.returncode, 1)
        self.assertIn("VERDICT: FAIL with no BLOCKER line", r.stdout)
        rp = write(self.d, "h3.md", good.replace("VERDICT: PASS", "BLOCKER: it just feels wrong — will happen\nVERDICT: FAIL"))
        self.assertIn("BLOCKER without a citation", self.claims("report", rp, "--task", self.task).stdout)
        rp = write(self.d, "h4.md", good.replace("VERDICT: PASS", "BLOCKER: the header check reads only toks[0] — export.py:14 — fix: scan every token\nVERDICT: FAIL"))
        self.assertEqual(self.claims("report", rp, "--task", self.task).returncode, 0)


class BlockingFixed(unittest.TestCase):
    def test_a_cited_line_left_unchanged_is_named_a_changed_one_passes(self):
        # first contact (2026-10-17): the orchestrator amended six files for the reviewer's BLOCKING items and left one
        # cited ADR line as it was; the fresh reviewer failed on that line again and the round rule stopped the loop
        d = tempfile.mkdtemp(prefix="reef-bf.")
        g = lambda *a: subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *a], capture_output=True, text=True, check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
        write(d, "reef/architecture/adr/draft-1-storage.md", "# Storage\n\n## Consequences\nSC-1 and SC-2 prove real Supabase Storage.\nPreview and Production each get a bucket.\n")
        write(d, "AGENTS.md", "# brief\nThe app is deployed to Vercel.\n")
        g("add", "-A"); g("commit", "-qm", "before")
        since = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        report = write(d, "review.md", "RUN: agent=plan-reviewer feature=demo\nVERDICT: FAIL\n\nBLOCKING\n"
                       "B1 — reef/architecture/adr/draft-1-storage.md:4 says SC-1/SC-2 prove real storage; withdrawn.\n"
                       "B2 — AGENTS.md:2 says deployed to Vercel; the owner says never.\n\nADVISORY\n- none\n")
        write(d, "AGENTS.md", "# brief\nThe app is not deployed in this trial.\n")   # B2 fixed, B1 missed
        r = subprocess.run([sys.executable, CLAIMS, "blocking-fixed", report, since, "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("NOT FIXED", r.stdout)
        self.assertIn("draft-1-storage.md:4 unchanged", r.stdout)
        self.assertNotIn("AGENTS.md:2", r.stdout)
        write(d, "reef/architecture/adr/draft-1-storage.md", "# Storage\n\n## Consequences\nSC-1 and SC-2 are withdrawn: storage is only ever stubbed.\nPreview and Production each get a bucket.\n")
        r = subprocess.run([sys.executable, CLAIMS, "blocking-fixed", report, since, "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("ok: 2 cited line(s) changed", r.stdout)
        shorthand = write(d, "review2.md", "RUN: agent=plan-reviewer feature=demo\nVERDICT: FAIL\n\nBLOCKING\nB1 — prisma:34 still says so.\n")
        r = subprocess.run([sys.executable, CLAIMS, "blocking-fixed", shorthand, since, "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("cannot be checked", r.stdout)


class ConvergeReadsTheEvidence(unittest.TestCase):
    """v3 phase 2: a whole-suite proof reads the evidence the gate wrote for this tree instead of running the suite again;
    the gate runs once only when there is none (and writes it); every proof runs holding gates.resources."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-conv2.")
        subprocess.run(["git", "init", "-q", "-b", "main", self.d], check=True)
        os.makedirs(os.path.join(self.d, "scripts"))
        for name in ("reef-gate.sh", "reef-snapshot.sh", "reef-graph.py", "reef-evidence.py"):
            shutil.copy(os.path.join(ROOT, "scripts", name), os.path.join(self.d, "scripts", name))
        self.marker = os.path.join(tempfile.mkdtemp(prefix="reef-conv2-ran."), "ran.log")   # outside the tree: a file in it would move the snapshot
        self.cfg({"gates": {"full": f"echo ran >> {self.marker}; echo '2 passed'"}, "paths": {"features": "reef/features"}})
        feature(self.d)
        write(self.d, "tests/__init__.py", "")
        write(self.d, "tests/test_export.py", "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_csv_header_and_rows(self):\n        pass\n\n    def test_csv_two_decimals(self):\n        pass\n")
        subprocess.run(["git", "-C", self.d, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", self.d, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "start"], check=True, capture_output=True)

    def cfg(self, c):
        write(self.d, ".reef/config.json", json.dumps(c))

    def converge(self):
        return subprocess.run([sys.executable, CONVERGE, "csv-export-for-orders", "--repo", self.d], capture_output=True, text=True)

    def snapshot(self):
        return subprocess.run(["sh", "scripts/reef-snapshot.sh"], cwd=self.d, capture_output=True, text=True).stdout.strip()

    def evidence(self, exit_code, head=None):
        os.makedirs(os.path.join(self.d, ".reef", "evidence"), exist_ok=True)
        head = head or subprocess.run(["git", "-C", self.d, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        write(self.d, f".reef/evidence/{self.snapshot()}.json", json.dumps({"snapshot": self.snapshot(), "head": head, "exit": exit_code, "at": "2030-01-01T00:00:00Z", "mode": "full"}))

    def test_a_whole_suite_proof_reads_the_evidence_and_runs_the_gate_only_when_there_is_none(self):
        self.evidence(0)
        r = self.converge()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("whole suite: evidence: local snapshot", r.stdout)
        self.assertFalse(os.path.exists(self.marker), "green evidence for this tree: the suite is not run again")
        self.evidence(0, head="0" * 40)   # the review (2026-10-25): a record is read through reef-evidence, which checks its head
        r = self.converge()
        self.assertIn("whole suite: the gate, run once", r.stdout + r.stderr)
        self.assertTrue(os.path.exists(self.marker), "a record whose head is not this commit is no evidence: the gate ran")
        os.unlink(self.marker)
        self.evidence(1)
        r = self.converge()
        self.assertEqual(r.returncode, 1)
        self.assertIn("contradicts — test_csv_header_and_rows exists but the full suite is red (exit 1: evidence: local", r.stdout)
        self.assertFalse(os.path.exists(self.marker), "red evidence is read too: the tree has not changed")
        shutil.rmtree(os.path.join(self.d, ".reef", "evidence"))
        # the rollup file converge wrote is part of the tree now; no evidence for it: the gate runs once and writes this tree's
        snap_before = self.snapshot()
        r = self.converge()
        self.assertIn("whole suite: the gate, run once (exit 0", r.stdout + r.stderr)
        with open(self.marker) as f:
            self.assertEqual(f.read().count("ran"), 1, "two proofs, one suite run")
        self.assertTrue(os.path.isfile(os.path.join(self.d, ".reef", "evidence", snap_before + ".json")), "the gate wrote the evidence for this tree")

    def test_every_proof_runs_holding_gates_resources(self):
        import fcntl
        import hashlib
        self.cfg({"gates": {"full": "true", "resources": ["heavy"], "timeout_s": 1}, "resources": {"heavy": {"slots": 1}},
                  "converge": {"test_cmd": "python3 -m unittest -q tests.test_export -k {name}"}, "paths": {"features": "reef/features"}})
        key = os.path.realpath(self.d)
        slot = os.path.join(tempfile.gettempdir(), f"reef-slot-{hashlib.sha1(key.encode()).hexdigest()}-heavy-0")
        with open(slot, "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            r = self.converge()
            # the review (2026-10-25): a held slot is not a red test — nothing written, exit 3, run again
            self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
            self.assertIn("BUSY: 2 proof(s) could not run", r.stdout)
            self.assertNotIn("contradicts", r.stdout)
            self.assertFalse(any(f.startswith("R") for f in os.listdir(os.path.join(self.d, "reef/features/csv-export-for-orders/tasks"))), "no rollup for a busy slot")
        r = self.converge()
        self.assertEqual(r.returncode, 0, "slot free: the named tests run under the lock and pass: " + r.stdout + r.stderr)
        self.assertIn("Converged", r.stdout)


class PlanCheckRefusesShellInACell(unittest.TestCase):
    """v3 phase 2: a Proof is a named test; a shell one-liner over 120 characters in a markdown cell is refused unless it
    is tagged [mechanic] (it must write files). A long test NAME is not shell."""

    def run_check(self, proof):
        d = tempfile.mkdtemp(prefix="reef-pc-proof.")
        write(d, ".reef/config.json", json.dumps({"gates": {"full": "true"}, "paths": {"features": "reef/features"}}))
        feature(d)
        write(d, "reef/features/csv-export-for-orders/tasks/1201-write-csv.md", TASK_NEW.replace("| AC-2 | `test_csv_two_decimals` |", f"| AC-2 | {proof} |"))
        pc = os.path.join(ROOT, "scripts", "reef-plan-check.py")
        r = subprocess.run([sys.executable, pc, d], capture_output=True, text=True)
        return [l for l in r.stdout.splitlines() if "characters of shell in a markdown cell" in l]

    def test_long_shell_refused_mechanic_and_a_long_test_name_allowed(self):
        long_shell = "`npm run build > /tmp/b.log 2>&1 && npx vitest run tests/export.test.ts --reporter=verbose --coverage --coverage.reporter=text --reporter=junit --outputFile=/tmp/junit.xml --run | tail -40`"
        self.assertGreater(len(long_shell), 120)
        self.assertEqual(len(self.run_check(long_shell)), 1, "an untagged shell line over 120 characters fails the check")
        self.assertEqual(self.run_check("[mechanic] " + long_shell), [], "tagged: the mechanic runs it verbatim")
        long_name = "`" + "exports every amount with two decimals even when the locale uses a comma and the order has more than one hundred lines across three currencies`"
        self.assertGreater(len(long_name), 120)
        self.assertEqual(self.run_check(long_name), [], "a long test name is a name, not shell")
        self.assertEqual(self.run_check("`npx vitest run -t \"two decimals\"`"), [], "short shell stays a warning at most")
        # the review (2026-10-25): the row is split on `|`, so a shell line was measured only up to its first pipe; and a
        # test name that begins with a command word is a name
        piped = "`npx vitest run tests/export.test.ts --reporter=verbose --coverage --coverage.reporter=text --run 2>&1 | tee /tmp/vitest.log | tail -40`"
        self.assertGreater(len(piped), 120)
        self.assertEqual(len(self.run_check(piped)), 1, "measured whole, pipes included")
        name = "`node has two children when the order is split across a comma locale and more than one hundred lines are exported to csv`"
        self.assertGreater(len(name), 120)
        self.assertEqual(self.run_check(name), [], "a name beginning with a command word is still a name")


class Converge(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-conv.")
        subprocess.run(["git", "init", "-q", "-b", "main", self.d], check=True)
        write(self.d, ".reef/config.json", json.dumps({"gates": {"full": "python3 -m unittest -q"}, "paths": {"features": "reef/features"}}))
        shutil.copy(os.path.join(ROOT, "scripts", "reef-gate.sh"), os.path.join(self.d, "scripts", "reef-gate.sh") if os.makedirs(os.path.join(self.d, "scripts"), exist_ok=True) is None else "")
        feature(self.d)
        write(self.d, "export.py", "def export_csv(rows):\n    return 'id,amount\\n' + ''.join(f\"{r['id']},{r['amount']:.2f}\\n\" for r in rows)\n")
        write(self.d, "tests/__init__.py", "")
        write(self.d, "tests/test_export.py", "import unittest\nfrom export import export_csv\n\n\nclass T(unittest.TestCase):\n    def test_csv_header_and_rows(self):\n        self.assertTrue(export_csv([{'id': 1, 'amount': 2}]).startswith('id,amount\\n'))\n\n    def test_csv_two_decimals(self):\n        self.assertIn('2.00', export_csv([{'id': 1, 'amount': 2}]))\n")

    def converge(self):
        return subprocess.run([sys.executable, CONVERGE, "csv-export-for-orders", "--repo", self.d], capture_output=True, text=True)

    def test_a_rollup_id_is_unique_across_feature_folders(self):
        # 2026-10-18 (qassimha row 11): its first rollup took R1 because its own folder had none; row 2's R1 was already
        # on develop under another feature's folder, and the tick printed BROKEN (a duplicate id in the one graph)
        write(self.d, "reef/features/receipt-decode/tasks/done/R01-receipt-decode.md", "---\nid: R1\nfeature: receipt-decode\nstatus: done\n---\n# R1\n")
        write(self.d, "reef/features/receipt-decode/tasks/done/R03-receipt-decode.md", "---\nid: R3\nfeature: receipt-decode\nstatus: done\n---\n# R3\n")
        with open(os.path.join(self.d, "tests", "test_export.py")) as f:
            t = f.read()
        write(self.d, "tests/test_export.py", t.replace("    def test_csv_two_decimals(self):\n        self.assertIn('2.00', export_csv([{'id': 1, 'amount': 2}]))\n", ""))
        self.assertEqual(self.converge().returncode, 1)
        tdir = os.path.join(self.d, "reef/features/csv-export-for-orders/tasks")
        made = [f for f in os.listdir(tdir) if f.startswith("R")]
        self.assertEqual(made, ["R04-csv-export-for-orders.md"], "the next id after every rollup in every feature folder")
        with open(os.path.join(tdir, made[0])) as f:
            self.assertIn("id: R4", f.read())

    def test_a_rollup_is_complete_and_holds_to_no_planner_rule(self):
        # 2026-10-19 (qassimha row 68): converge wrote the raw task template (placeholders, complexity design with no
        # Decision, findings after ## Log); the orchestrator hand-filled two rollups with the same literal
        # `reef-converge <feature> --dry-run`, and the plan check failed seven rules on them — a red check blocks approvals
        pc = os.path.join(ROOT, "scripts", "reef-plan-check.py")
        rollup_fails = lambda: [l for l in subprocess.run([sys.executable, pc, self.d], capture_output=True, text=True).stdout.splitlines()
                                if l.startswith("FAIL") and "/R0" in l or l.startswith("FAIL: test name claimed")]
        with open(os.path.join(self.d, "tests", "test_export.py")) as f:
            t = f.read()
        write(self.d, "tests/test_export.py", t.replace("    def test_csv_two_decimals(self):\n        self.assertIn('2.00', export_csv([{'id': 1, 'amount': 2}]))\n", ""))
        self.assertEqual(self.converge().returncode, 1)
        self.assertEqual(self.converge().returncode, 1, "a second run adds its own section")
        p = os.path.join(self.d, "reef/features/csv-export-for-orders/tasks/R01-csv-export-for-orders.md")
        with open(p) as f:
            text = f.read()
        self.assertNotIn("<", text.split("## Converge")[0], "no template placeholder left")
        self.assertIn("`python3 scripts/reef-converge csv-export-for-orders --dry-run`", text)
        self.assertEqual(text.count("## Converge"), 2)
        self.assertTrue(text.rstrip().endswith("## Log"), "## Log stays the last section")
        self.assertEqual(rollup_fails(), [])
        # the trial's shape, hand-edited before this fix: two closed rollups, design, sections after Log, one Proof
        legacy = ("---\nid: R{n}\nfeature: {f}\nstatus: done\ncomplexity: design\neffort: medium\nblocked-by: []\nresources: []\n"
                  "tier: full\ntouches: []\nverify: judge\nattempts: 0\ndispatches: 0\nlast_failure_sig: \"\"\n---\n# R{n}\n\n## Scope\nx\n\n"
                  "## Acceptance Criteria\n- AC-1: every Proof row holds.\n\n## Proof\n| AC | Proof |\n|---|---|\n"
                  "| AC-1 | `python3 scripts/reef-converge <feature> --dry-run` |\n\n## Log\n\n## Converge 2026-10-19\n- x\n\n## Closed 2026-10-19\ny\n")
        write(self.d, "reef/features/old-a/tasks/done/R02-old-a.md", legacy.format(n=2, f="old-a"))
        write(self.d, "reef/features/old-b/tasks/done/R03-old-b.md", legacy.format(n=3, f="old-b"))
        self.assertEqual(rollup_fails(), [], "a rollup keeps schema and graph checks, not the planner's authoring rules")

    def test_converged_then_missing_then_contradicts(self):
        r = self.converge()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Converged", r.stdout)
        self.assertFalse(any(f.startswith("R") for f in os.listdir(os.path.join(self.d, "reef/features/csv-export-for-orders/tasks"))), "nothing written when converged")
        with open(os.path.join(self.d, "tests", "test_export.py")) as f:
            t = f.read()
        write(self.d, "tests/test_export.py", t.replace("    def test_csv_two_decimals(self):\n        self.assertIn('2.00', export_csv([{'id': 1, 'amount': 2}]))\n", ""))
        r = self.converge()
        self.assertEqual(r.returncode, 1)
        self.assertIn("AC-2: missing", r.stdout)
        rollup = os.path.join(self.d, "reef/features/csv-export-for-orders/tasks/R01-csv-export-for-orders.md")
        self.assertTrue(os.path.isfile(rollup), os.listdir(os.path.dirname(rollup)))
        with open(rollup) as f:
            self.assertIn("## Converge", f.read())

        write(self.d, "tests/test_export.py", t)
        write(self.d, "export.py", "def export_csv(rows):\n    return 'id,amount\\n' + ''.join(f\"{r['id']},{r['amount']}\\n\" for r in rows)\n")
        r = self.converge()
        self.assertEqual(r.returncode, 1)
        self.assertIn("contradicts", r.stdout)
        self.assertEqual(len([f for f in os.listdir(os.path.dirname(rollup)) if f.startswith("R")]), 1, "one rollup per feature, appended to")

    def test_a_note_a_printed_value_and_a_prose_cell_are_read_as_written(self):
        # 2026-10-24, the trial's row 18 (note n45): four false "missing" lines — a test name followed by a note in
        # parentheses (backticks inside it too), a command whose cell says what it prints, and a cell of plain prose
        def cells(ac1, ac2):
            task = TASK_NEW.replace("| AC-1 | `test_csv_header_and_rows` |", f"| AC-1 | {ac1} |").replace("| AC-2 | `test_csv_two_decimals` |", f"| AC-2 | {ac2} |")
            write(self.d, "reef/features/csv-export-for-orders/tasks/1201-write-csv.md", task)
            return self.converge()
        r = cells("`test_csv_header_and_rows` (header first, `id,amount`)", "`python3 -c \"print(1 + 2)\"` prints `3`")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Converged", r.stdout)
        r = cells("`test_csv_header_and_rows`", "`python3 -c \"print(1 + 2)\"` prints `4`")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("AC-2: contradicts — `python3 -c \"print(1 + 2)\"` prints '3', not '4'", r.stdout)
        r = cells("`test_csv_header_and_rows`", "both tests above render the header with two decimals")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1 prose row(s) not run here", r.stdout)
        self.assertNotIn("missing", r.stdout)

    def test_a_cell_with_two_backticked_names_checks_each(self):
        # 2026-10-24, the trial's row 5 rollup: a Proof cell holding two names, `a`, `b`, was read as ONE name
        # ("a`, `b") and reported missing although both tests existed
        write(self.d, "tests/export.test.ts", 'import { it } from "vitest";\nit("csv header is written", () => {});\n'
              'it("csv header keeps its order", () => {});\n')
        task = TASK_NEW.replace("| AC-1 | `test_csv_header_and_rows` |", "| AC-1 | `csv header is written`, `csv header keeps its order` |") \
                       .replace("| AC-2 | `test_csv_two_decimals` |", "| AC-2 | `test_csv_two_decimals` and `test_csv_header_and_rows` |")
        write(self.d, "reef/features/csv-export-for-orders/tasks/1201-write-csv.md", task)
        r = self.converge()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Converged", r.stdout)
        write(self.d, "tests/export.test.ts", 'import { it } from "vitest";\nit("csv header is written", () => {});\n')
        r = self.converge()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("AC-1: missing — test csv header keeps its order does not exist", r.stdout)
        self.assertNotIn("csv header is written does not exist", r.stdout)

    def test_runner_word_names_escaped_pipes_and_superseded_rows(self):
        # 2026-10-18, row 2's review (found row 50): a vitest name starting with `env` ran as a command, a grep with an
        # escaped pipe split the table cell, and a row replaced by task 204's Proof had no way to be skipped
        write(self.d, "tests/env.test.ts", 'import { it } from "vitest";\nit("env defaults to the test database when unset", () => {});\n')
        task = TASK_NEW.replace("| AC-1 | `test_csv_header_and_rows` |", "| AC-1 | `env defaults to the test database when unset` |") \
                       .replace("| AC-2 | `test_csv_two_decimals` |", "| AC-2 | `! git grep -nE 'as (Foo\\|Bar)' -- export.py` |")
        write(self.d, "reef/features/csv-export-for-orders/tasks/1201-write-csv.md", task)
        r = self.converge()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Converged", r.stdout)
        self.assertNotIn("missing", r.stdout)
        task = task.replace("| AC-2 | `! git grep -nE 'as (Foo\\|Bar)' -- export.py` |", "| AC-2 | superseded by 204 AC-5 (footnote 37) |")
        write(self.d, "reef/features/csv-export-for-orders/tasks/1201-write-csv.md", task)
        r = self.converge()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1 superseded row(s) skipped", r.stdout)
        self.assertIn("AC-2: superseded by 204 AC-5", r.stdout)

    def test_vitest_names_are_tests_mechanic_rows_are_skipped_and_the_template_is_found_from_a_project_copy(self):
        # first contact (2026-10-17): 26 vitest names in backticks ran as shell and came back "missing"; then the script
        # looked for <project>/templates/task.md and crashed before writing the rollup
        write(self.d, "tests/export.test.ts", 'import { it } from "vitest";\nit("csv header is written", () => {});\n')
        task = TASK_NEW.replace("| AC-1 | `test_csv_header_and_rows` |", "| AC-1 | `csv header is written` |") \
                       .replace("| AC-2 | `test_csv_two_decimals` |", "| AC-2 | [mechanic] `rm -f .env && python3 -m unittest -q` |")
        write(self.d, "reef/features/csv-export-for-orders/tasks/1201-write-csv.md", task)
        r = self.converge()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Converged", r.stdout)
        self.assertIn("1 [mechanic] row(s) not run here", r.stdout)
        self.assertNotIn("missing", r.stdout)
        # the project's copy of the script, far from the plugin's templates/: a finding still gets its rollup
        copy = os.path.join(self.d, "scripts", "reef-converge")
        shutil.copy(CONVERGE, copy)
        write(self.d, "tests/export.test.ts", 'import { it } from "vitest";\nit("csv header is renamed", () => {});\n')
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"}
        r = subprocess.run([sys.executable, copy, "csv-export-for-orders", "--repo", self.d], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("AC-1: missing", r.stdout)
        self.assertNotIn("Traceback", r.stderr)
        rollup = os.path.join(self.d, "reef/features/csv-export-for-orders/tasks/R01-csv-export-for-orders.md")
        self.assertTrue(os.path.isfile(rollup), r.stdout + r.stderr)
        with open(rollup) as f:
            body = f.read()
        self.assertTrue(body.startswith("---\nid: R1\nfeature: csv-export-for-orders\n"), body[:80])
        self.assertIn("## Converge", body)


if __name__ == "__main__":
    unittest.main()
