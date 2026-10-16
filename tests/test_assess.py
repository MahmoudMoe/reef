"""Sabotage suite for `reef-claims.py assess`: /reef-assess's output as data. The fixture under tests/fixtures/assess/
ledger/ is a REAL report (four Explore agents on the ledger dogfood project, 2026-10-16); it must pass as written, and
each way an assess can lie must be caught: a claim with no Observed/Inferred label, an Observed claim with no proving
path, a harnessability heading whose sum or level does not match its table, a missing dimension, a missing section."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAIMS = os.path.join(ROOT, "scripts", "reef-claims.py")
FIX = os.path.join(ROOT, "tests", "fixtures", "assess", "ledger")


def project():
    d = tempfile.mkdtemp(prefix="reef-assess.")
    os.makedirs(os.path.join(d, "reef", "architecture"))
    for name in ("architecture.md", "conventions.md"):
        shutil.copy(os.path.join(FIX, name), os.path.join(d, "reef", "architecture", name))
    shutil.copy(os.path.join(FIX, "day-zero.md"), os.path.join(d, "reef", "day-zero.md"))
    return d


def assess(d):
    return subprocess.run([sys.executable, CLAIMS, "assess", d], capture_output=True, text=True)


def edit(d, rel, old, new):
    p = os.path.join(d, rel)
    with open(p, encoding="utf-8") as f:
        t = f.read()
    assert old in t, old
    with open(p, "w", encoding="utf-8") as f:
        f.write(t.replace(old, new, 1))


class Assess(unittest.TestCase):
    def test_the_real_report_passes(self):
        r = assess(project())
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("harnessability moderate (3/5) consistent", r.stdout)

    def test_unlabelled_claim_and_proofless_observed_are_rejected(self):
        d = project()
        edit(d, "reef/architecture/architecture.md", "- Observed — `requires-python", "- Python 3.11 is required (`requires-python")
        r = assess(d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("a claim without Observed/Inferred", r.stdout)
        d = project()
        # an Observed claim with no path, line or command behind it, placed in an observed section
        edit(d, "reef/architecture/conventions.md", "## Naming", "- Observed — everything is tidy and well named\n\n## Naming")
        r = assess(d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("Observed without a proving path", r.stdout)

    def test_a_proposal_under_open_needs_no_label(self):
        # the real report's Open and "should take" sections carry unlabelled proposals and pass; the same bullet
        # moved into an observed section is caught
        d = project()
        edit(d, "reef/architecture/architecture.md", "## Open\n", "## Open\n- Reconsider the queue table format\n")
        self.assertEqual(assess(d).returncode, 0)

    def test_harnessability_sum_level_and_dimensions_are_checked(self):
        d = project()
        edit(d, "reef/day-zero.md", "## Harnessability — moderate (3/5)", "## Harnessability — high (5/5)")
        r = assess(d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("says 5/5 but the dimensions sum to 3", r.stdout)
        d = project()
        edit(d, "reef/day-zero.md", "## Harnessability — moderate (3/5)", "## Harnessability — low (3/5)")
        self.assertIn("3/5 is 'moderate', the heading says 'low'", assess(d).stdout)
        d = project()
        edit(d, "reef/day-zero.md", "| Lint baseline |", "| Style baseline |")
        self.assertIn("lacks 'lint baseline'", assess(d).stdout)

    def test_missing_section_or_file_is_rejected(self):
        d = project()
        edit(d, "reef/architecture/conventions.md", "## How it was pushed", "## Git history")
        self.assertIn("no section for 'how it was pushed'", assess(d).stdout)
        d = project()
        os.unlink(os.path.join(d, "reef", "day-zero.md"))
        r = assess(d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing reef/day-zero.md", r.stdout)


if __name__ == "__main__":
    unittest.main()
