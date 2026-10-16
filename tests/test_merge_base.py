"""reef-merge-base: the integration branch comes into the feature branch before a wave; record files keep both
sides, a code conflict aborts and names itself (first contact, 2026-10-16)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MERGE = os.path.join(ROOT, "scripts", "reef-merge-base")


def git(d, *a):
    return subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *a], capture_output=True, text=True)


def write(d, rel, text):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def read(d, rel):
    with open(os.path.join(d, rel), encoding="utf-8") as f:
        return f.read()


def repo():
    d = tempfile.mkdtemp(prefix="reef-mb.")
    subprocess.run(["git", "init", "-q", "-b", "develop", d], check=True)
    subprocess.run(["git", "-C", d, "config", "user.email", "t@t"], check=True)   # the merge commit needs an identity (CI runner has none)
    subprocess.run(["git", "-C", d, "config", "user.name", "t"], check=True)
    write(d, ".reef/config.json", json.dumps({"branches": {"base": "develop", "release": "main"},
                                              "paths": {"runlog": "reef/journal.md", "queue": "reef/queue.md"}}))
    write(d, "reef/journal.md", "# Journal\n| Task | Result |\n|---|---|\n")
    write(d, "scripts/reef-plan-check.py", "# v1\n")
    write(d, "src/a.ts", "export const a = 1;\n")
    git(d, "add", "-A"); git(d, "commit", "-qm", "init")
    git(d, "checkout", "-q", "-b", "feat/demo")
    return d


def run(d):
    return subprocess.run([sys.executable, MERGE, "--repo", d], capture_output=True, text=True)


class MergeBase(unittest.TestCase):
    def test_records_keep_both_sides_and_scripts_arrive(self):
        d = repo()
        # the feature appends 101's row; develop appends the owner's decision AND refreshes a script
        write(d, "reef/journal.md", read(d, "reef/journal.md") + "| 101 | PASS |\n")
        git(d, "add", "-A"); git(d, "commit", "-qm", "101")
        git(d, "checkout", "-q", "develop")
        write(d, "reef/journal.md", read(d, "reef/journal.md") + "\n## owner decision: the audit gate\n")
        write(d, "scripts/reef-plan-check.py", "# v2 — strips adversarial-guard\n")
        git(d, "add", "-A"); git(d, "commit", "-qm", "decision + scripts")
        git(d, "checkout", "-q", "feat/demo")
        r = run(d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("records kept both sides: reef/journal.md", r.stdout)
        j = read(d, "reef/journal.md")
        self.assertIn("| 101 | PASS |", j)
        self.assertIn("owner decision: the audit gate", j)
        self.assertNotIn("<<<<<<<", j)
        self.assertEqual(read(d, "scripts/reef-plan-check.py"), "# v2 — strips adversarial-guard\n", "the feature now runs the base's scripts")
        self.assertEqual(git(d, "status", "--porcelain").stdout.strip(), "", "merge committed, tree clean")
        r2 = run(d)
        self.assertEqual(r2.returncode, 0)
        self.assertIn("already has every commit", r2.stdout)

    def test_a_code_conflict_aborts_and_names_the_file(self):
        d = repo()
        write(d, "src/a.ts", "export const a = 2;\n")
        git(d, "add", "-A"); git(d, "commit", "-qm", "feat a=2")
        git(d, "checkout", "-q", "develop")
        write(d, "src/a.ts", "export const a = 3;\n")
        git(d, "add", "-A"); git(d, "commit", "-qm", "develop a=3")
        git(d, "checkout", "-q", "feat/demo")
        r = run(d)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("CONFLICT in src/a.ts", r.stdout)
        self.assertIn("USER ACTION REQUIRED", r.stdout)
        self.assertEqual(read(d, "src/a.ts"), "export const a = 2;\n", "merge aborted, the feature is untouched")
        self.assertFalse(os.path.exists(os.path.join(d, ".git", "MERGE_HEAD")))

    def test_not_a_feature_branch_refuses(self):
        d = repo()
        git(d, "checkout", "-q", "develop")
        r = run(d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a feature branch", r.stderr)


if __name__ == "__main__":
    unittest.main()
