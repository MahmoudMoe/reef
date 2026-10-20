"""Super Reef (0.7, the owner's go 2026-10-21): one delegated night. The owner approves tonight's contract + their profile
once; while `reef-run.py --night` runs, Mahmoud (the owner's proxy) may approve a plan for a row the contract names,
from his own report, at the plan's current digest; the night folder is a protected record; a release PR waits for
the morning; the runner writes the morning report."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import test_layout as L  # noqa: E402  (a 0.6 feature folder with a Row: line)
import test_run as R     # noqa: E402  (the scripted fake claude)

RUN = os.path.join(ROOT, "scripts", "reef-run.py")
APPROVAL = os.path.join(ROOT, "scripts", "reef-approval.py")
GUARD = os.path.join(ROOT, "scripts", "reef-guard.py")
CHECK = os.path.join(ROOT, "scripts", "reef-plan-check.py")


def project():
    d = tempfile.mkdtemp(prefix="reef-night.")
    subprocess.run(["git", "init", "-q", "-b", "develop", d], check=True)
    L.write(d, ".reef/config.json", json.dumps({"gates": {"full": "true"}, "branches": {"base": "develop", "release": "main"},
                                                "paths": {"features": "reef/features", "tasks": "tasks", "queue": "reef/queue.md"}}))
    L.write(d, ".reef/version", "0.6.0\n")
    L.write(d, "AGENTS.md", "# brief\n")
    L.write(d, "reef/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n"
                                "| 12 | share links | | planned | 1 | |\n| 3 | items | | planned | 1 | |\n")
    L.write(d, "reef/features/share-links/SPEC.md", L.SPEC.format(slug="share-links", row=12))
    L.write(d, "reef/features/share-links/tasks/1201-a.md", L.task(1201, "share-links"))
    L.write(d, "reef/features/editable-items/SPEC.md", L.SPEC.format(slug="editable-items", row=3))
    L.write(d, "reef/features/editable-items/tasks/301-a.md", L.task(301, "editable-items"))
    L.write(d, "reef/owner.md", "# The owner\nSimple and robust; no over-engineering.\n")
    L.write(d, ".reef/night/contract.md", "# Night\nRows: 12\nDecisions: plan approvals, design looks.\nHard limits: the release to main.\n")
    L.git(d, "add", "-A")
    L.git(d, "commit", "-qm", "init")
    return d


def digest(d, feature):
    return subprocess.run([sys.executable, CHECK, d, "--digest", "--feature", feature], capture_output=True, text=True).stdout.split()[-1][:16]


def hook(d, question, label="Approve"):
    payload = {"tool_name": "AskUserQuestion", "hook_event_name": "PostToolUse", "cwd": d,
               "tool_input": {"questions": [{"question": question}]}, "tool_response": {"answers": {question: label}}}
    return subprocess.run([sys.executable, APPROVAL], input=json.dumps(payload), capture_output=True, text=True)


def proxy(d, feature, report):
    return subprocess.run([sys.executable, APPROVAL, "--proxy", "--feature", feature, "--report", report], capture_output=True, text=True, cwd=d)


def approve_night(tc, d):
    r = subprocess.run([sys.executable, RUN, "contract", "--repo", d], capture_output=True, text=True)
    tc.assertEqual(r.returncode, 0, r.stderr)
    q = [l for l in r.stdout.splitlines() if l.startswith("question: ")][0][len("question: "):]
    tc.assertRegex(q, r"^Approve night \d{4}-\d\d-\d\d at [0-9a-f]{16}\?$")
    r = hook(d, q)
    tc.assertIn("approved at", r.stdout)
    return q


class Contract(unittest.TestCase):
    def test_the_owner_approves_the_contract_and_profile_once_and_an_edit_voids_it(self):
        d = project()
        q = approve_night(self, d)
        rec = json.load(open(os.path.join(d, ".reef", "approvals", "night.json")))
        self.assertEqual(rec["rows"], ["12"])
        self.assertEqual(hook(d, q.replace(q[-17:-1], "0" * 16)).stdout.count("stale"), 1, "a stale digest writes nothing")
        with open(os.path.join(d, "reef", "owner.md"), "a") as f:
            f.write("Ship fast.\n")              # the profile changed after the approval
        r = R.run(d, ["stop:x"], "--night")
        self.assertEqual(r.returncode, 1)
        self.assertIn("changed since the owner approved it", r.stderr)


class ProxyApproval(unittest.TestCase):
    def setUp(self):
        self.d = project()
        approve_night(self, self.d)
        self.rep = os.path.join(self.d, ".reef", "ci-local", "report-mahmoud-share-links.md")
        os.makedirs(os.path.dirname(self.rep), exist_ok=True)

    def report(self, feature="share-links", dg=None, path=None):
        p = path or self.rep
        with open(p, "w") as f:
            f.write(f"RUN: agent=mahmoud night=2026-10-21 question=approve\nAPPROVE plan {feature} at {dg or digest(self.d, feature)} — slices are vertical\nVERDICT: DONE\n")
        return p

    def test_mahmoud_approves_only_while_the_night_runs_for_a_contract_row_at_the_current_digest(self):
        rec = os.path.join(self.d, ".reef", "approvals", "share-links.json")
        r = proxy(self.d, "share-links", self.report())
        self.assertEqual(r.returncode, 1)
        self.assertIn("no night is running", r.stdout)
        L.write(self.d, ".reef/night/active", "{}")          # what reef-run --night writes
        other = os.path.join(self.d, "notes.md")
        self.assertIn("Mahmoud's own file", proxy(self.d, "share-links", self.report(path=other)).stdout)
        self.assertIn("no `APPROVE plan share-links at", proxy(self.d, "share-links", self.report(dg="0" * 16)).stdout, "a stale plan digest")
        rep3 = os.path.join(self.d, ".reef", "ci-local", "report-mahmoud-editable-items.md")
        self.assertIn("not in tonight's contract", proxy(self.d, "editable-items", self.report(feature="editable-items", path=rep3)).stdout)
        self.assertFalse(os.path.exists(rec))
        r = proxy(self.d, "share-links", self.report())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        got = json.load(open(rec))
        self.assertEqual(got["by"], "mahmoud (proxy)")
        self.assertEqual(got["digest16"], digest(self.d, "share-links"))
        r = subprocess.run([sys.executable, CHECK, self.d, "--verify-stamp", "--feature", "share-links"], capture_output=True, text=True)
        self.assertIn("approval: OK", r.stdout, "the guard's check reads a proxy record like the owner's")


class NightGuard(unittest.TestCase):
    def guard(self, d, cmd):
        return subprocess.run([sys.executable, GUARD], input=json.dumps({"tool_name": "Bash", "cwd": d, "tool_input": {"command": cmd}}),
                              capture_output=True, text=True)

    def test_the_night_folder_is_a_record_and_the_release_waits_for_the_morning(self):
        d = project()
        for cmd in ("touch .reef/night/active", "rm .reef/night/active", "printf x > .reef/night/contract.md", "cp /tmp/x .reef/night/contract.md"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.guard(d, cmd).returncode, 2, cmd)
        L.write(d, ".reef/night/active", "{}")
        r = self.guard(d, "gh pr create --base main --head develop --fill")
        self.assertEqual(r.returncode, 2)
        self.assertIn("super Reef night is running", r.stderr)


class NightRun(unittest.TestCase):
    def test_the_runner_marks_the_night_active_and_writes_the_morning_report(self):
        d = project()
        b = os.path.join(d, ".bin")
        os.makedirs(b)
        fake = R.FAKE.replace("open(plan, \"w\").write", "open(os.path.join(os.getcwd(), '.active-seen'), 'w').write(str(os.path.exists(os.path.join(os.getcwd(), '.reef', 'night', 'active'))))\nopen(plan, \"w\").write", 1)
        open(os.path.join(b, "claude"), "w").write(fake)
        os.chmod(os.path.join(b, "claude"), 0o755)
        self.assertEqual(R.run(d, ["probe-deny"], "probe").returncode, 0)
        approve_night(self, d)
        r = R.run(d, ["stop:night done"], "--night")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(open(os.path.join(d, ".active-seen")).read(), "True", "the session ran under .reef/night/active")
        self.assertFalse(os.path.exists(os.path.join(d, ".reef", "night", "active")), "removed at exit")
        rep = open(os.path.join(d, ".reef", "night", "report.md")).read()
        for h in ("## Mahmoud's plan approvals", "## Mahmoud's other decisions", "## Merges into develop (undo: git revert -m 1 <sha>)", "## Waiting for you", "Sessions: 1"):
            self.assertIn(h, rep)


if __name__ == "__main__":
    unittest.main()
