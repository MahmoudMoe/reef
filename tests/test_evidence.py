"""Workflow v3, phase 2 — evidence once per commit. The full gate writes `.reef/evidence/<snapshot>.json` in the MAIN
checkout on every real run; `scripts/reef-evidence.py` reads it (or, with CI on feature PRs, the commit's check-runs)
and never makes it; a red gate is red evidence; a worktree at the same commit finds the main checkout's record."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVIDENCE = os.path.join(ROOT, "scripts", "reef-evidence.py")

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
mode = os.environ.get("GH_CHECKS", "success")
if mode == "down":
    print("HTTP 502", file=sys.stderr); sys.exit(1)
a = sys.argv[1:]
if a[:1] == ["api"] and "check-runs" in a[1]:
    runs = {"success": [{"name": "test (ubuntu-latest)", "status": "completed", "conclusion": "success"},
                        {"name": "CodeQL", "status": "completed", "conclusion": "success"}],
            "failure": [{"name": "test (ubuntu-latest)", "status": "completed", "conclusion": "failure"},
                        {"name": "CodeQL", "status": "completed", "conclusion": "success"}],
            "pending": [{"name": "test (ubuntu-latest)", "status": "in_progress", "conclusion": None},
                        {"name": "CodeQL", "status": "completed", "conclusion": "success"}],
            "skipped": [{"name": "test (ubuntu-latest)", "status": "completed", "conclusion": "skipped"},
                        {"name": "CodeQL", "status": "completed", "conclusion": "success"}],
            "none": []}[mode]
    print(json.dumps({"total_count": len(runs), "check_runs": runs})); sys.exit(0)
sys.exit(1)
'''


def git(d, *a):
    return subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True, capture_output=True, text=True).stdout.strip()


class Evidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reef-evidence.")
        self.d = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.d, "scripts"))
        os.makedirs(os.path.join(self.d, ".reef"))
        for name in ("reef-gate.sh", "reef-snapshot.sh", "reef-evidence.py"):
            shutil.copy(os.path.join(ROOT, "scripts", name), os.path.join(self.d, "scripts", name))
        with open(os.path.join(self.d, ".gitignore"), "w") as f:
            f.write(".reef/ci-local/\n.reef/evidence/\n")   # as reef-init writes it
        self.config({"gates": {"full": "echo '3 passed in 0.1s'"}, "ci": {"feature_gate": "local"}})
        git(self.d, "init", "-q", "-b", "main")
        with open(os.path.join(self.d, "app.py"), "w") as f:
            f.write("x = 1\n")
        git(self.d, "add", "-A"); git(self.d, "commit", "-qm", "start")
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        with open(os.path.join(self.bin, "gh"), "w") as f:
            f.write(FAKE_GH)
        os.chmod(os.path.join(self.bin, "gh"), 0o755)

    def config(self, cfg):
        with open(os.path.join(self.d, ".reef", "config.json"), "w") as f:
            json.dump(cfg, f)

    def gate(self, cwd=None, **env):
        e = dict(os.environ, **env)
        return subprocess.run(["sh", "scripts/reef-gate.sh", "full"], cwd=cwd or self.d, capture_output=True, text=True, env=e)

    def evidence(self, *args, cwd=None, **env):
        e = dict(os.environ, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""), REEF_GH_TIMEOUT="2", **env)
        return subprocess.run([sys.executable, EVIDENCE, *args], cwd=cwd or self.d, capture_output=True, text=True, env=e)

    def snapshot(self, cwd=None):
        return subprocess.run(["sh", "scripts/reef-snapshot.sh"], cwd=cwd or self.d, capture_output=True, text=True).stdout.strip()

    def test_the_full_gate_writes_the_evidence_and_the_reader_reads_it_never_makes_it(self):
        r = self.evidence()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("evidence: none", r.stdout)
        self.assertFalse(os.path.isdir(os.path.join(self.d, ".reef", "evidence")), "the reader made nothing")
        self.assertEqual(self.gate().returncode, 0)
        snap = self.snapshot()
        p = os.path.join(self.d, ".reef", "evidence", f"{snap}.json")
        self.assertTrue(os.path.isfile(p), os.listdir(os.path.join(self.d, ".reef")))
        with open(p) as f:
            rec = json.load(f)
        self.assertEqual((rec["exit"], rec["mode"], rec["snapshot"], rec["head"], rec["counts"]), (0, "full", snap, git(self.d, "rev-parse", "HEAD"), {"passed": 3}))
        self.assertEqual(rec["tail"][-1], "3 passed in 0.1s")
        r = self.evidence()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"^evidence: local snapshot [0-9a-f]{12} head [0-9a-f]{12} exit 0 — 3 passed at ")
        r = self.evidence("--format", "json")
        self.assertEqual(json.loads(r.stdout)["state"], "green")

    def test_a_red_gate_is_red_evidence_and_an_edit_is_a_new_snapshot_without_evidence(self):
        self.config({"gates": {"full": "echo '1 failed, 2 passed'; exit 1"}, "ci": {"feature_gate": "local"}})
        self.assertEqual(self.gate().returncode, 1)
        r = self.evidence()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("exit 1 — 2 passed, 1 failed", r.stdout)
        with open(os.path.join(self.d, "app.py"), "a") as f:
            f.write("y = 2\n")
        r = self.evidence()
        self.assertEqual(r.returncode, 2, "the tree changed: the old result is not this tree's evidence")

    def test_a_worktree_at_the_same_commit_finds_the_main_checkouts_record_by_commit(self):
        self.config({"gates": {"full": "echo '3 passed'"}, "ci": {"feature_gate": "local"}})
        git(self.d, "add", "-A"); git(self.d, "commit", "-qm", "config")
        self.assertEqual(self.gate().returncode, 0)
        sha = git(self.d, "rev-parse", "HEAD")
        wt = os.path.join(self.tmp, "wt")
        git(self.d, "worktree", "add", "-q", wt, "HEAD")
        r = self.evidence(sha, cwd=wt)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"head {sha[:12]} exit 0", r.stdout)
        self.assertEqual(self.gate(cwd=wt).returncode, 0)
        self.assertFalse(os.path.isdir(os.path.join(wt, ".reef", "evidence")), "a worktree's run writes the MAIN checkout's record")
        self.assertEqual(len(os.listdir(os.path.join(self.d, ".reef", "evidence"))), 1, "the same tree: the same file")
        # the security review (2026-10-25): a DIRTY tree must not inherit HEAD's green
        with open(os.path.join(self.d, "app.py"), "a") as f:
            f.write("y = 2\n")
        r = self.evidence()
        self.assertEqual(r.returncode, 2, "an edited tree has no record of its own: " + r.stdout)
        self.assertIn("differs from HEAD", r.stdout)
        r = self.evidence(sha)
        self.assertEqual(r.returncode, 2, "naming HEAD's commit changes nothing while the tree differs: " + r.stdout)
        # a forged record: the right file name, the wrong head inside
        with open(os.path.join(self.d, "app.py"), "w") as f:
            f.write("x = 1\n")
        snap = self.snapshot()
        with open(os.path.join(self.d, ".reef", "evidence", f"{snap}.json"), "w") as f:
            json.dump({"snapshot": snap, "head": "0" * 40, "exit": 0, "mode": "full"}, f)
        self.assertEqual(self.evidence().returncode, 2, "a record whose head is not this commit is no evidence")

    def test_with_ci_on_feature_prs_the_check_runs_are_the_evidence_and_local_is_the_fallback(self):
        self.config({"gates": {"full": "echo '3 passed'"}, "ci": {"feature_gate": "ci"}})
        git(self.d, "add", "-A"); git(self.d, "commit", "-qm", "cfg")   # CI answers for a COMMIT: the tree must be that commit (the review, 2026-10-25)
        git(self.d, "remote", "add", "origin", "https://github.com/o/r.git")
        r = self.evidence(GH_CHECKS="success")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"^evidence: ci commit [0-9a-f]{12} exit 0 — 2 check runs, all green \(test \(ubuntu-latest\), CodeQL\)")
        r = self.evidence(GH_CHECKS="failure")
        self.assertEqual(r.returncode, 1)
        self.assertIn("exit 1 — failed: test (ubuntu-latest)", r.stdout)
        r = self.evidence(GH_CHECKS="pending")
        self.assertEqual(r.returncode, 3)
        self.assertIn("pending — 1 of 2 check runs still running", r.stdout)
        r = self.evidence(GH_CHECKS="none")
        self.assertEqual(r.returncode, 2, "no check run and no local record: none")
        r = self.evidence(GH_CHECKS="skipped")
        self.assertEqual(r.returncode, 2, "a skipped check is not a green suite: " + r.stdout)
        self.config({"gates": {"full": "echo '3 passed'"}, "ci": {"feature_gate": "ci", "check_name": "CodeQL"}})
        git(self.d, "add", "-A"); git(self.d, "commit", "-qm", "cfg")
        self.assertEqual(self.evidence(GH_CHECKS="skipped").returncode, 0, "ci.check_name, the required check, alone decides when the commit has it")
        self.config({"gates": {"full": "echo '3 passed'"}, "ci": {"feature_gate": "ci", "check_name": "test (ubuntu-latest)"}})
        git(self.d, "add", "-A"); git(self.d, "commit", "-qm", "cfg")
        self.assertEqual(self.evidence(GH_CHECKS="skipped").returncode, 2, "the suite's check was skipped: none")
        self.assertEqual(self.evidence(GH_CHECKS="success").returncode, 0)
        self.config({"gates": {"full": "echo '3 passed'"}, "ci": {"feature_gate": "ci"}})
        git(self.d, "add", "-A"); git(self.d, "commit", "-qm", "cfg")
        self.assertEqual(self.gate().returncode, 0)
        for mode in ("none", "down"):
            r = self.evidence(GH_CHECKS=mode)
            self.assertEqual(r.returncode, 0, f"{mode}: {r.stdout}{r.stderr}")
            self.assertIn("evidence: local", r.stdout)
        # the review (2026-10-25): CI tested the COMMIT; a dirty tree at HEAD is not that commit
        git(self.d, "add", "-A"); git(self.d, "commit", "-qm", "ci config", "--allow-empty")
        self.assertEqual(self.evidence(GH_CHECKS="success").returncode, 0, "clean HEAD: CI's result is this tree's")
        with open(os.path.join(self.d, "app.py"), "a") as f:
            f.write("z = 3\n")
        r = self.evidence(GH_CHECKS="success")
        self.assertEqual(r.returncode, 2, "dirty HEAD: CI's green is not this tree's: " + r.stdout)
        self.assertIn("differs from HEAD", r.stdout)
        # a head not fetched here (a web edit, another machine): the forge still answers for it
        remote = "a" * 40
        self.assertEqual(self.evidence(remote, GH_CHECKS="success").returncode, 0, "a commit the forge knows and this checkout does not")
        r = self.evidence(remote, GH_CHECKS="none")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not in this checkout", r.stdout)
        self.config({"gates": {"full": "echo '3 passed'"}, "ci": {"feature_gate": "local"}})
        r = self.evidence(GH_CHECKS="failure")
        self.assertNotIn("evidence: ci", r.stdout, "feature_gate local: CI is not asked")


if __name__ == "__main__":
    unittest.main()
