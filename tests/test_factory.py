"""Workflow v3, phase 7 — the factory on GitHub Actions: reef-init OFFERS `.github/workflows/reef-factory.yml` (never writes
it: minutes, the model key, the six-hour limit are the owner's call); a row's issue labelled `reef-ready` builds in the
Actions sandbox through `reef-run.py --row <id>` with the plugin and its guard loaded (`REEF_CLAUDE_ARGS`); the owner
approves a plan by commenting its question on the row's issue (`reef-approval.py --from-issue`, admin only); the row's
state goes back as labels (`reef-queue.py label-state`)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import test_init as I            # noqa: E402  (node_project, init)
import test_queue_issues as QI   # noqa: E402  (the fake forge with its state file)
import test_row as TR            # noqa: E402  (a valid feature folder: SPEC, TASK)
RUN = os.path.join(ROOT, "scripts", "reef-run.py")
APPROVAL = os.path.join(ROOT, "scripts", "reef-approval.py")
QUEUE = os.path.join(ROOT, "scripts", "reef-queue.py")
FACTORY = ".github/workflows/reef-factory.yml"
# the forge's fake gains an issue's comments and a collaborator's permission, as the GitHub API answers them
FAKE_GH = QI.FAKE_GH.replace('''    path = next(x for x in a[1:] if x.startswith("repos/"))
''', '''    path = next(x for x in a[1:] if x.startswith("repos/"))
    if "/issues/" in path and path.endswith("/comments"):
        n = int(path.split("/issues/")[1].split("/")[0])
        print(json.dumps([{"id": k + 1, "user": {"login": c.get("login", "owner")}, "body": c["body"], "created_at": f"2026-10-26T00:0{k}:00Z"}
                          for k, c in enumerate(issue(n).get("forge_comments", []))])); save(); sys.exit(0)
    if "/collaborators/" in path and path.endswith("/permission"):
        login = path.split("/collaborators/")[1].split("/")[0]
        print(json.dumps({"permission": s.get("perm", {}).get(login, "none"), "user": {"login": login}})); save(); sys.exit(0)
''')
assert FAKE_GH != QI.FAKE_GH
FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json, os, sys
open(os.path.join(os.getcwd(), ".fake-argv"), "a").write(json.dumps(sys.argv[1:]) + "\n")
mode = open(os.path.join(os.getcwd(), ".fake-mode")).read().strip()
def ev(**e): print(json.dumps(e), flush=True)
ev(type="system", subtype="init", session_id="x")
if mode == "probe":
    ev(type="result", result="reef-guard DENY: writing under .reef/approvals/", session_id="p", total_cost_usd=0.01)
else:
    json.dump({"active": True, "wait": "owner: approve row 12", "stop": None, "parked": None, "hashes": []}, open(os.path.join(os.getcwd(), ".reef", "loop.json"), "w"))
    ev(type="result", result="done", session_id="s1", total_cost_usd=0.1)
'''


class Offered(unittest.TestCase):
    def test_init_offers_the_factory_never_writes_it_and_accept_places_it(self):
        d = I.node_project(tempfile.mkdtemp(prefix="reef-factory-init."))
        r = I.init(d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(d, FACTORY)), "a workflow that spends minutes and needs a secret is never written unasked")
        self.assertIn("0 proposed", r.stdout, "an offer is not a proposal to change the project's file")
        self.assertIn(f"OFFERED  {FACTORY}", r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(d, ".git", "reef", "proposed", FACTORY)))
        r = I.init(d, "--accept", FACTORY)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        text = I.read(d, FACTORY)
        for needle in ("reef-ready", "ANTHROPIC_API_KEY", "scripts/reef-run.py probe", "--from-issue", "label-state", "--plugin-dir",
                       "ref: develop", "schedule:", "workflow_dispatch", "timeout-minutes: 300", "issue-row"):
            self.assertIn(needle, text, needle)
        self.assertNotRegex(text, r"\{\{[a-z_]+\}\}", "every Reef placeholder rendered (GitHub's ${{ }} expressions stay)")
        self.assertRegex(text, r"checkout -q ([0-9a-f]{40}|main)\b", "the plugin pinned at the commit this project's scripts came from")
        self.assertRegex(text, r"git clone -q https://github\.com/\S+/reef ")
        self.assertNotRegex(text, r"(?i)opus|sonnet|haiku")
        r = I.init(d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("OFFERED", r.stdout, "accepted once, it is the project's file: refreshed like the others, never offered again")
        self.assertRegex(r.stdout, r"\n  0 written, (\d+ updated, )?\d+ skipped, 0 proposed")


class RunRow(unittest.TestCase):
    def test_the_runner_drives_one_row_and_loads_the_plugin_the_environment_names(self):
        d = tempfile.mkdtemp(prefix="reef-factory-run.")
        subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
        os.makedirs(os.path.join(d, ".reef"))
        open(os.path.join(d, ".reef", "config.json"), "w").write('{"gates": {"full": "true"}}')
        b = os.path.join(d, ".bin")
        os.makedirs(b)
        open(os.path.join(b, "claude"), "w").write(FAKE_CLAUDE)
        os.chmod(os.path.join(b, "claude"), 0o755)
        env = dict(os.environ, PATH=b + os.pathsep + os.environ["PATH"], REEF_CLAUDE_ARGS="--plugin-dir /x/reef")
        env.pop("REEF_CLAUDE", None)
        open(os.path.join(d, ".fake-mode"), "w").write("probe")
        r = subprocess.run([sys.executable, RUN, "probe", "--repo", d], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        open(os.path.join(d, ".fake-mode"), "w").write("loop")
        r = subprocess.run([sys.executable, RUN, "--row", "12", "--max-iterations", "1", "--repo", d], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        argv = [json.loads(l) for l in open(os.path.join(d, ".fake-argv"))]
        self.assertEqual(len(argv), 2)
        prompt = argv[1][argv[1].index("-p") + 1]
        self.assertTrue(prompt.startswith("/reef-loop 12 "), prompt)
        self.assertIn("--plugin-dir", argv[1]); self.assertIn("/x/reef", argv[1], "REEF_CLAUDE_ARGS, split like a shell would")
        self.assertIn("--plugin-dir", argv[0], "the probe's session loads the same plugin: the gate proves THAT guard")


class _Forge(QI.Base):
    """Issues mode with a planned row 3 (issue 12, `[3] exact totals`) whose feature folder is in the checkout."""

    def setUp(self):
        super().setUp()
        with open(os.path.join(self.bin, "gh"), "w") as f:
            f.write(FAKE_GH)
        self.cfg["paths"]["features"] = "reef/features"
        self.cfg["branches"] = {"base": "main", "release": "release"}
        self.cfg["gates"], self.cfg["merge"] = {"full": "true"}, {"by": "loop"}   # the plan check wants a gate and a stated merge.by
        with open(os.path.join(self.d, ".reef", "config.json"), "w") as f:
            f.write(json.dumps(self.cfg, indent=2) + "\n")
        os.makedirs(os.path.join(self.d, "scripts"))
        for n in ("reef-queue.py", "reef-row.py", "reef-plan-check.py", "reef-evidence.py", "reef-gate.sh", "reef-snapshot.sh"):
            shutil.copy(os.path.join(ROOT, "scripts", n), os.path.join(self.d, "scripts", n))
        TR.write(self.d, "reef/features/exact-totals/SPEC.md", TR.SPEC.replace("Row: 1", "Row: 3"))
        TR.write(self.d, "reef/features/exact-totals/tasks/301-slice.md", TR.TASK.replace("feature: demo-row-one", "feature: exact-totals").replace("id: 101", "id: 301"))
        TR.write(self.d, ".gitignore", ".reef/approvals/\n.reef/queue.json\n.reef/queue-view.md\nreef/features/*/tasks/.plan-review.json\nscripts/__pycache__/\n")
        TR.write(self.d, "CLAUDE.md", "# brief\n")
        TR.git(self.d, "add", "-A"); TR.git(self.d, "commit", "-qm", "init")
        s = self.forge()
        self.issue_12 = next(i for i in s["issues"] if i["number"] == 12)
        self.issue_12["labels"].append("reef-ready")
        s["perm"] = {"mahmoud": "admin", "bob": "write"}
        self.put(s)
        pc = os.path.join(self.d, "scripts", "reef-plan-check.py")
        r = subprocess.run([sys.executable, pc, self.d], capture_output=True, text=True)   # the stamp, as /reef-plan leaves it
        self.assertEqual(r.returncode, 0, r.stdout)
        r = subprocess.run([sys.executable, pc, self.d, "--digest", "--feature", "exact-totals"], capture_output=True, text=True)
        self.digest = r.stdout.split()[-1][:16]

    def env(self):
        return dict(os.environ, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""), GH_STATE=self.state, GH_MODE="ok")

    def approval(self, *args):
        return subprocess.run([sys.executable, APPROVAL, *args], capture_output=True, text=True, env=self.env(), cwd=self.d)

    def labels(self):
        return self.issue("3")["labels"]


class Labels(_Forge):
    def test_the_rows_state_is_written_back_as_one_label(self):
        r = self.q("issue-row", "12")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "3"), r.stdout + r.stderr)
        r = self.q("label-state", "3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("approval", r.stdout); self.assertIn("reef-waiting-owner", r.stdout)
        self.assertIn("reef-waiting-owner", self.labels())
        self.assertNotIn("reef-ready", self.labels(), "the trigger label is consumed")
        os.makedirs(os.path.join(self.d, ".reef", "approvals"), exist_ok=True)
        with open(os.path.join(self.d, ".reef", "approvals", "exact-totals.json"), "w") as f:
            json.dump({"digest16": self.digest, "approved_at": "2026-10-26T00:00:00Z"}, f)
        r = self.q("label-state", "3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("reef-building", self.labels()); self.assertNotIn("reef-waiting-owner", self.labels())
        self.assertIn("reef-building", self.gh()["labels"], "the label exists on the forge before it is applied")


class FromIssue(_Forge):
    def comment(self, body, login="mahmoud"):
        s = self.gh()
        next(i for i in s["issues"] if i["number"] == 12).setdefault("forge_comments", []).append({"login": login, "body": body})
        self.put(s)

    def test_the_owners_comment_at_the_current_digest_is_the_approval_and_nothing_else_is(self):
        rec = os.path.join(self.d, ".reef", "approvals", "exact-totals.json")
        r = self.approval("--from-issue", "3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"Approve plan exact-totals at {self.digest}?", r.stdout, "the exact line the owner posts")
        self.assertFalse(os.path.exists(rec))
        self.comment("Approve plan exact-totals at 0123456789abcdef?")
        r = self.approval("--from-issue", "3")
        self.assertIn("stale", r.stdout); self.assertFalse(os.path.exists(rec))
        self.comment(f"Approve plan exact-totals at {self.digest}?", login="bob")
        r = self.approval("--from-issue", "3")
        self.assertIn("admin", r.stdout); self.assertFalse(os.path.exists(rec), "write access is not the owner")
        self.comment(f"Approve plan exact-totals at {self.digest}?")
        r = self.approval("--from-issue", "3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("approved at", r.stdout)
        got = json.load(open(rec))
        self.assertEqual(got["digest16"], self.digest)
        self.assertEqual(got["by"], "owner (issue #12, @mahmoud)")
        r = subprocess.run([sys.executable, os.path.join(self.d, "scripts", "reef-plan-check.py"), self.d, "--verify-stamp", "--feature", "exact-totals"], capture_output=True, text=True)
        self.assertIn("approval: OK", r.stdout, "the guard's check reads it like the hook's record")


if __name__ == "__main__":
    unittest.main()
