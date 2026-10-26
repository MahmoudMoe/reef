"""Workflow v3, phase 5 — the row as a state machine read from disk: scripts/reef-row.py walks a row from plan to closed
and names the one next command at every step; nothing is decided from memory."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
verify: gate-only
attempts: 0
dispatches: 0
last_failure_sig: ""
---
# 101 — the slice

## Scope
x

## Acceptance Criteria
- AC-1 (FR-1): it works

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


class RowStateMachine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reef-row.")
        self.main = os.path.join(self.tmp, "main")
        os.makedirs(os.path.join(self.main, "scripts"))
        for n in ("reef-row.py", "reef-queue.py", "reef-plan-check.py", "reef-evidence.py", "reef-gate.sh", "reef-snapshot.sh"):
            shutil.copy(os.path.join(ROOT, "scripts", n), os.path.join(self.main, "scripts", n))
        write(self.main, ".reef/config.json", json.dumps({"gates": {"full": "echo '1 passed'"}, "ci": {"feature_gate": "local"},
                                                           "branches": {"base": "main", "release": "release"},
                                                           "paths": {"queue": "reef/queue.md", "features": "reef/features"}}))
        write(self.main, ".reef/version", "0.6.0\n")
        write(self.main, ".gitignore", ".reef/worktrees/\n.reef/approvals/\n.reef/review/\n.reef/evidence/\n.reef/ci-local/\ntasks/.plan-review.json\nreef/features/*/tasks/.plan-review.json\n")
        write(self.main, "reef/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n"
                                          "| 1 | first | | planned | 1 | |\n| 2 | second | 1 | planned | 1 | |\n")
        write(self.main, "CLAUDE.md", "# brief\n")
        git(self.main, "init", "-q", "-b", "main"); git(self.main, "add", "-A"); git(self.main, "commit", "-qm", "init")

    def row(self, *args):
        r = subprocess.run([sys.executable, ROW, *args, "--repo", self.main], capture_output=True, text=True,
                           env=dict(os.environ, PATH="/nonexistent-gh:" + os.environ["PATH"]))
        return r

    def state(self, key):
        r = self.row("state", key, "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def test_the_row_walks_from_plan_to_closed_and_names_the_next_command_at_each_step(self):
        s = self.state("1")
        self.assertEqual((s["state"], s["next"]), ("plan", "/reef-plan 1"))
        s = self.state("2")
        self.assertEqual(s["state"], "queued", "row 2 depends on row 1")
        r = self.row("state", "9")
        self.assertEqual(r.returncode, 2, "an unknown row")
        # the plan: a feature worktree with the folder, the plan check green, no approval yet
        feat = os.path.join(self.main, ".reef", "worktrees", "demo-row-one")
        self.assertEqual(git(self.main, "worktree", "add", "-q", "-b", "feat/demo-row-one", feat, "main").returncode, 0)
        write(feat, "reef/features/demo-row-one/SPEC.md", SPEC)
        write(feat, "reef/features/demo-row-one/tasks/101-slice.md", TASK)
        pc = subprocess.run([sys.executable, os.path.join(feat, "scripts", "reef-plan-check.py"), feat], capture_output=True, text=True)
        self.assertEqual(pc.returncode, 0, pc.stdout)
        s = self.state("1")
        self.assertEqual((s["state"], s["slug"]), ("approval", "demo-row-one"))
        self.assertIn("Approve plan demo-row-one at", s["detail"])
        self.assertEqual(s["next"], "/reef-plan 1")
        digest = subprocess.run([sys.executable, os.path.join(feat, "scripts", "reef-plan-check.py"), feat, "--digest", "--feature", "demo-row-one"],
                                capture_output=True, text=True).stdout.split()[-1]
        write(self.main, ".reef/approvals/demo-row-one.json", json.dumps({"digest16": digest[:16], "approved_at": "2026-10-26T00:00:00Z"}))
        s = self.state("1")
        self.assertEqual(s["state"], "build")
        self.assertIn("1 open task(s): 101-slice.md", s["detail"])
        self.assertIn("reef-loop.py tick", s["next"])
        # the slug works as a key too
        self.assertEqual(self.state("demo-row-one")["state"], "build")
        # built: the task closed, the work committed in the row's worktree — no evidence yet
        os.makedirs(os.path.join(feat, "reef/features/demo-row-one/tasks/done"))
        os.rename(os.path.join(feat, "reef/features/demo-row-one/tasks/101-slice.md"), os.path.join(feat, "reef/features/demo-row-one/tasks/done/101-slice.md"))
        write(feat, "src/a.py", "a = 2\n")
        git(feat, "add", "-A"); git(feat, "commit", "-qm", "the slice\n\nCloses-task: 101-slice")
        s = self.state("1")
        self.assertEqual(s["state"], "evidence")
        self.assertIn("sh scripts/reef-gate.sh full", s["next"])
        self.assertEqual(subprocess.run(["sh", "scripts/reef-gate.sh", "full"], cwd=feat, capture_output=True).returncode, 0)
        s = self.state("1")
        self.assertEqual(s["state"], "review", s)
        self.assertEqual(s["next"], "/reef-review demo-row-one")
        # reviewed: a GREEN record at the head (written the way reef-record writes it)
        head = git(feat, "rev-parse", "HEAD").stdout.strip()
        write(self.main, ".reef/review/demo-row-one.json", json.dumps({"sha": head, "verdict": "GREEN", "pr": 7}))
        s = self.state("1")
        self.assertEqual(s["state"], "merge")
        self.assertIn("/reef-review demo-row-one", s["next"], "no forge here: push and PR are the review skill's")
        self.assertIn("is not in main", s["detail"])
        # merged into the base, row still in the queue
        git(self.main, "merge", "-q", "--no-ff", "--no-edit", "feat/demo-row-one")
        s = self.state("1")
        self.assertEqual(s["state"], "close")
        self.assertIn("/reef-loop", s["next"])
        # archived
        write(self.main, "reef/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 2 | second | 1 | planned | 1 | |\n")
        write(self.main, "reef/queue-archive.md", "# Archive\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 1 | first | | planned | 1 | |\n")
        shutil.rmtree(os.path.join(self.main, "reef", "features"), ignore_errors=True)
        git(self.main, "worktree", "remove", "--force", feat)
        s = self.state("1")
        self.assertEqual(s["state"], "closed")
        self.assertEqual(self.state("2")["state"], "plan", "row 1 archived: row 2's dependency is met")
        r = self.row("next", "2")
        self.assertEqual(r.stdout.strip(), "/reef-plan 2")


if __name__ == "__main__":
    unittest.main()
