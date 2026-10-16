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


def check(d, *args):
    return subprocess.run([sys.executable, CHECK, d, *args], capture_output=True, text=True)


def fails(r):
    return [l for l in r.stdout.splitlines() if l.startswith("FAIL") or l.startswith("warning")]


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
        self.assertIn("RULE AC1 does not cite its Proof row", self.claims("report", rp, "--task", self.task).stdout)


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


if __name__ == "__main__":
    unittest.main()
