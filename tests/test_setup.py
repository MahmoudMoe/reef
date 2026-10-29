"""scripts/reef-setup.py — worktree.setup proven ONCE per change (2026-10-28, the current adoption: a fresh row worktree had no
built app, 60 tests went red for reasons unrelated to the row, the orchestrator guessed a build and the suite ran twice per
row). A row's own red is never the proof; the proof is a scratch worktree of the base with the setup, then the full gate."""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETUP = os.path.join(ROOT, "scripts", "reef-setup.py")
ROW = os.path.join(ROOT, "scripts", "reef-row.py")

TASK = """---
id: 101
feature: demo-row-one
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
# 101 — the slice

## Scope
One slice.

## Acceptance Criteria
- AC-1 (FR-1): the thing works.

## Proof
| AC | Proof |
|---|---|
| AC-1 | `test_it_works` |

## Out of scope

## Log
"""
SPEC = ("# demo row one\nRow: 1\n\n## Scope\nOne slice.\n\n## Non-goals\n- none\n\n## Already shipped\nnone\n\n"
        "## Requirements\n- FR-1 [backend]: it works.\n\n## Success criteria\n- SC-1: green.\n\n## Architecture impact\nnone\n")


def git(d, *a):
    return subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *a], capture_output=True, text=True)


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


class SetupProof(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reef-setup.")
        self.main = os.path.join(self.tmp, "main")
        os.makedirs(os.path.join(self.main, "scripts"))
        for n in ("reef-setup.py", "reef_common.py", "reef-row.py", "reef-queue.py", "reef-plan-check.py", "reef-evidence.py", "reef-gate.sh", "reef-snapshot.sh", "reef-graph.py", "reef-attempt"):
            if os.path.isfile(os.path.join(ROOT, "scripts", n)):
                shutil.copy(os.path.join(ROOT, "scripts", n), os.path.join(self.main, "scripts", n))
        # the suite needs a file the setup makes — the shape of "the tests read the built app"
        write(self.main, "tests/__init__.py", "")
        write(self.main, "tests/test_built.py", "import os, unittest\n\nclass T(unittest.TestCase):\n    def test_it_works(self):\n        self.assertTrue(os.path.isfile('built.txt'), 'the setup did not build')\n")
        self.config({"setup": "true"})
        write(self.main, ".reef/version", "0.7.2\n")
        write(self.main, ".gitignore", ".reef/worktrees/\n.reef/approvals/\n.reef/review/\n.reef/evidence/\n.reef/ci-local/\nbuilt.txt\ntasks/.plan-review.json\nreef/features/*/tasks/.plan-review.json\n")
        write(self.main, "reef/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 1 | first | | planned | 1 | |\n")
        write(self.main, "CLAUDE.md", "# brief\n")
        git(self.main, "init", "-q", "-b", "main"); git(self.main, "add", "-A"); git(self.main, "commit", "-qm", "init")

    def config(self, worktree, lock=None):
        write(self.main, ".reef/config.json", json.dumps({"gates": {"full": "python3 -m unittest -q tests.test_built", "timeout_s": 120},
                                                           "worktree": {"dir": ".reef/worktrees", **worktree}, "ci": {"feature_gate": "local"},
                                                           "branches": {"base": "main", "release": "release"},
                                                           "paths": {"queue": "reef/queue.md", "features": "reef/features"}}))

    def setup(self, *args):
        return subprocess.run([sys.executable, SETUP, *args, "--repo", self.main], capture_output=True, text=True)

    def test_unproven_then_incomplete_then_proven_once_per_change(self):
        r = self.setup("state")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("unproven", r.stdout)
        self.assertIn("reef-setup.py prove", r.stdout)
        r = self.setup("prove")
        self.assertEqual(r.returncode, 1, "a setup that builds nothing leaves the gate red on an untouched tree:\n" + r.stdout + r.stderr)
        self.assertIn("INCOMPLETE", r.stdout)
        self.assertIn("worktree.setup", r.stdout)
        self.assertIn("setup-", r.stdout.split(".log")[0][-60:] + ".log", "the INCOMPLETE line names the log")
        self.assertEqual(self.setup("state").returncode, 1, "the record says incomplete, no re-run")
        recs = [f for f in os.listdir(os.path.join(self.main, ".reef", "ci-local")) if f.startswith("setup-") and f.endswith(".json")]
        self.assertEqual(len(recs), 1)
        rec = json.load(open(os.path.join(self.main, ".reef", "ci-local", recs[0])))
        self.assertFalse(rec["ok"])
        self.assertTrue(rec["failing"], "the failing lines are kept for the owner")
        self.assertEqual([d for d in os.listdir(os.path.join(self.main, ".reef", "worktrees")) if d.startswith(".setup-")], [], "the scratch worktree is removed")
        self.assertNotIn("setup-", git(self.main, "worktree", "list").stdout)
        self.assertFalse(os.path.isdir(os.path.join(self.main, ".reef", "evidence")), "a tree lacking its setup is no evidence about the base")
        # the owner completes the setup: a new digest, unproven again, then proven
        self.config({"setup": "touch built.txt"})
        r = self.setup("state")
        self.assertEqual(r.returncode, 3, "the setup changed: the old record does not speak for it")
        r = self.setup("prove")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("proven", r.stdout)
        self.assertEqual(self.setup("state").returncode, 0)
        self.assertFalse(os.path.isfile(os.path.join(self.main, "built.txt")), "the proof ran in the scratch worktree, not the main checkout")
        recs = sorted(f for f in os.listdir(os.path.join(self.main, ".reef", "ci-local")) if f.startswith("setup-"))
        self.assertEqual(len([f for f in recs if f.endswith(".json")]), 1, "an old digest's record is pruned: " + str(recs))
        # a lockfile change is a setup change
        write(self.main, "package-lock.json", "{}\n")
        self.assertEqual(self.setup("state").returncode, 3, "a lockfile changed: prove again")
        d1 = self.setup("digest").stdout.strip()
        write(self.main, "package-lock.json", "{\"lockfileVersion\": 3}\n")
        self.assertNotEqual(d1, self.setup("digest").stdout.strip())

    def test_a_failing_setup_command_is_incomplete_and_named(self):
        self.config({"setup": "sh -c 'echo no-such-tool >&2; exit 7'"})
        r = self.setup("prove")
        self.assertEqual(r.returncode, 1)
        self.assertIn("exited 7", r.stdout)
        self.assertNotIn("setup-", git(self.main, "worktree", "list").stdout)

    def test_the_row_builds_only_on_a_proven_setup(self):
        # an approved plan with an open task, as the row state machine sees it
        feat = os.path.join(self.main, ".reef", "worktrees", "demo-row-one")
        self.assertEqual(git(self.main, "worktree", "add", "-q", "-b", "feat/demo-row-one", feat, "main").returncode, 0)
        write(feat, "reef/features/demo-row-one/SPEC.md", SPEC)
        write(feat, "reef/features/demo-row-one/tasks/101-slice.md", TASK)
        pc = subprocess.run([sys.executable, os.path.join(feat, "scripts", "reef-plan-check.py"), feat], capture_output=True, text=True)
        self.assertEqual(pc.returncode, 0, pc.stdout)
        digest = subprocess.run([sys.executable, os.path.join(feat, "scripts", "reef-plan-check.py"), feat, "--digest", "--feature", "demo-row-one"],
                                capture_output=True, text=True).stdout.split()[-1]
        write(self.main, ".reef/approvals/demo-row-one.json", json.dumps({"digest16": digest[:16], "approved_at": "2026-10-28T00:00:00Z"}))
        env = dict(os.environ, PATH="/nonexistent-gh:" + os.environ["PATH"])
        row = lambda: json.loads(subprocess.run([sys.executable, ROW, "state", "1", "--json", "--repo", self.main], capture_output=True, text=True, env=env).stdout)
        s = row()
        self.assertEqual(s["state"], "build")
        self.assertIn("reef-setup.py prove", s["next"], "unproven: the one next command is the proof, not the build")
        self.assertEqual(self.setup("prove").returncode, 1)
        s = row()
        self.assertIn("INCOMPLETE", s["next"] + s["detail"])
        self.assertIn("wait", s["next"], "incomplete: the owner's config, the row waits")
        self.config({"setup": "touch built.txt"})
        self.assertEqual(self.setup("prove").returncode, 0)
        s = row()
        self.assertIn("reef-setup.py apply", s["next"], "proven, but this worktree was set up under the old setup: apply it here first")
        self.assertIn(".reef/worktrees/demo-row-one", s["next"])
        r = self.setup("apply", feat)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(feat, "built.txt")))
        s = row()
        self.assertIn("reef-loop.py tick", s["next"], "proven and applied: the build as before")

    def test_the_proof_comes_before_the_plans_worktree(self):
        env = dict(os.environ, PATH="/nonexistent-gh:" + os.environ["PATH"])
        row = lambda: json.loads(subprocess.run([sys.executable, ROW, "state", "1", "--json", "--repo", self.main], capture_output=True, text=True, env=env).stdout)
        s = row()
        self.assertEqual(s["state"], "plan")
        self.assertIn("reef-setup.py prove", s["next"], "the plan's worktree is created by /reef-plan: the proof comes first")
        self.config({"setup": "touch built.txt"})
        self.assertEqual(self.setup("prove").returncode, 0)
        self.assertEqual(row()["next"], "/reef-plan 1")

    def test_apply_runs_the_setup_once_per_digest_in_a_worktree(self):
        self.config({"setup": "touch built.txt && echo ran >> count.txt"})
        wt = os.path.join(self.main, ".reef", "worktrees", "x")
        self.assertEqual(git(self.main, "worktree", "add", "-q", "-b", "feat/x", wt, "main").returncode, 0)
        r = self.setup("apply", wt)
        self.assertEqual(r.returncode, 3, "apply needs a proven setup: " + r.stdout)
        self.assertEqual(self.setup("prove").returncode, 0)
        self.assertEqual(self.setup("apply", wt).returncode, 0)
        self.assertEqual(self.setup("apply", wt).returncode, 0)
        self.assertEqual(open(os.path.join(wt, "count.txt")).read().count("ran"), 1, "the second apply is a no-op on the same digest")
        self.config({"setup": "touch built.txt && echo ran >> count.txt && true"})
        self.assertEqual(self.setup("prove").returncode, 0)
        self.assertEqual(self.setup("apply", wt).returncode, 0)
        self.assertEqual(open(os.path.join(wt, "count.txt")).read().count("ran"), 2, "a changed setup runs again in the worktree")

    def test_a_task_worktree_is_refused_while_unproven(self):
        # the critical path's worktree per task (reef-graph.py worktree) — a flat tasks/ layout takes that path
        write(self.main, "tasks/001-demo.md", TASK.replace("id: 101", "id: 1").replace("feature: demo-row-one", "feature: demo"))
        git(self.main, "add", "-A"); git(self.main, "commit", "-qm", "a task")
        r = subprocess.run([sys.executable, os.path.join(self.main, "scripts", "reef-graph.py"), "worktree", os.path.join(self.main, "tasks", "001-demo.md")],
                           capture_output=True, text=True, cwd=self.main)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unproven", r.stdout + r.stderr)
        self.assertFalse(os.path.isdir(os.path.join(self.main, ".reef", "worktrees", "1")))
        self.config({"setup": "touch built.txt"})
        self.assertEqual(self.setup("prove").returncode, 0)
        r = subprocess.run([sys.executable, os.path.join(self.main, "scripts", "reef-graph.py"), "worktree", os.path.join(self.main, "tasks", "001-demo.md")],
                           capture_output=True, text=True, cwd=self.main)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.main, ".reef", "worktrees", "1", "built.txt")), "the task worktree got the proven setup through apply")

    def test_a_gate_that_is_the_gate_script_is_refused(self):
        write(self.main, ".reef/config.json", json.dumps({"gates": {"full": "sh scripts/reef-gate.sh full"}, "worktree": {"setup": "true"},
                                                           "branches": {"base": "main"}, "paths": {"queue": "reef/queue.md", "features": "reef/features"}}))
        r = self.setup("prove")
        self.assertEqual(r.returncode, 1)
        self.assertIn("reef-gate", r.stdout)
        self.assertFalse(os.path.isdir(os.path.join(self.main, ".reef", "evidence")))

    def test_the_digest_follows_the_manifest_too(self):
        d1 = self.setup("digest").stdout.strip()
        write(self.main, "package.json", json.dumps({"scripts": {"build": "next build"}}))
        self.assertNotEqual(d1, self.setup("digest").stdout.strip(), "a changed build script is a changed setup")


class FailingLinesAreTheRealOnes(unittest.TestCase):
    """2026-10-28, the first proof on the current adoption: the INCOMPLETE line quoted a stderr line that merely contained
    the word "failed" ("[session-patch] nothing was stored: the closing write failed …") while the real `FAIL` lines sat
    further down. A runner's own failure marker outranks a sentence with the word in it."""

    def test_fail_markers_come_before_sentences_with_the_word(self):
        tmp = tempfile.mkdtemp(prefix="reef-setup-lines.")
        main = os.path.join(tmp, "main")
        os.makedirs(os.path.join(main, "scripts"))
        for n in ("reef-setup.py", "reef_common.py"):
            shutil.copy(os.path.join(ROOT, "scripts", n), os.path.join(main, "scripts", n))
        gate = "sh -c 'echo \"[session-patch] nothing was stored: the closing write failed with X\"; echo \" FAIL  tests/t.py > the real one\"; echo \"Tests 1 failed | 3 passed\"; exit 1'"
        write(main, ".reef/config.json", json.dumps({"gates": {"full": gate}, "worktree": {"setup": "true"}, "branches": {"base": "main"}}))
        write(main, ".gitignore", ".reef/worktrees/\n.reef/ci-local/\n")
        git(main, "init", "-q", "-b", "main"); git(main, "add", "-A"); git(main, "commit", "-qm", "init")
        r = subprocess.run([sys.executable, SETUP, "prove", "--repo", main], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        rec = json.load(open(glob.glob(os.path.join(main, ".reef", "ci-local", "setup-*.json"))[0]))
        self.assertIn("FAIL  tests/t.py", rec["failing"][0], rec["failing"])
        self.assertIn("FAIL  tests/t.py", r.stdout)
