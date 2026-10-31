"""Workflow v3, phase 7 — the factory on GitHub Actions: reef-init OFFERS `.github/workflows/reef-factory.yml` (never writes
it: minutes, the model key, the six-hour limit are the owner's call); the job runs ONE command, `reef-factory.py row`, that
checks who asked (admins only), that the base is protected, resumes the row's branch from the forge, proves the guard
reaches a headless session, reads the owner's plan approval from an UNEDITED admin comment on the row's issue
(`reef-approval.py --from-issue`), builds (`reef-run.py --row`, the plugin loaded through `REEF_CLAUDE_ARGS`), pushes the
branch back and writes the row's state as a label (`reef-queue.py label-state`)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import git_repo  # noqa: E402  (the suites' shared fixtures, once)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import test_init as I            # noqa: E402  (node_project, init)
import test_queue_issues as QI   # noqa: E402  (the fake forge with its state file)
import test_row as TR            # noqa: E402  (a valid feature folder: SPEC, TASK)
RUN = os.path.join(ROOT, "scripts", "reef-run.py")
APPROVAL = os.path.join(ROOT, "scripts", "reef-approval.py")
QUEUE = os.path.join(ROOT, "scripts", "reef-queue.py")
FACTORY = os.path.join(ROOT, "scripts", "reef-factory.py")
WORKFLOW = ".github/workflows/reef-factory.yml"
# the forge's fake gains an issue's comments (with their edit time), a collaborator's permission and a branch's protection
FAKE_GH = QI.FAKE_GH.replace('''    path = next(x for x in a[1:] if x.startswith("repos/"))
''', '''    path = next(x for x in a[1:] if x.startswith("repos/"))
    if "/issues/" in path and path.endswith("/comments"):
        n = int(path.split("/issues/")[1].split("/")[0])
        cs = [{"id": k + 1, "user": {"login": c.get("login", "owner")}, "body": c["body"], "created_at": f"2026-10-26T00:0{k}:00Z",
               "updated_at": c.get("updated_at") or f"2026-10-26T00:0{k}:00Z"} for k, c in enumerate(issue(n).get("forge_comments", []))]
        print(json.dumps([cs] if "--slurp" in a else cs)); save(); sys.exit(0)
    if "/collaborators/" in path and path.endswith("/permission"):
        login = path.split("/collaborators/")[1].split("/")[0]
        print(json.dumps({"permission": s.get("perm", {}).get(login, "none"), "user": {"login": login}})); save(); sys.exit(0)
    if "/branches/" in path and path.endswith("/protection"):
        if s.get("protected", True):
            print(json.dumps({"required_status_checks": None})); save(); sys.exit(0)
        print("HTTP 404: Branch not protected", file=sys.stderr); save(); sys.exit(1)
''')
assert FAKE_GH != QI.FAKE_GH
FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json, os, sys
open(os.path.join(os.getcwd(), ".fake-argv"), "a").write(json.dumps(sys.argv[1:]) + "\n")
prompt = sys.argv[sys.argv.index("-p") + 1]
def ev(**e): print(json.dumps(e), flush=True)
ev(type="system", subtype="init", session_id="x")
if "probe" in prompt:
    ev(type="result", result="reef-guard DENY: writing under .reef/approvals/", session_id="p", total_cost_usd=0.01)
else:
    json.dump({"active": True, "wait": "owner: approve the plan", "stop": None, "parked": None, "hashes": []}, open(os.path.join(os.getcwd(), ".reef", "loop.json"), "w"))
    ev(type="result", result="done", session_id="s1", total_cost_usd=0.1)
'''


class Offered(unittest.TestCase):
    def test_init_offers_the_factory_never_writes_it_and_accept_places_it(self):
        d = I.node_project(tempfile.mkdtemp(prefix="reef-factory-init."))
        r = I.init(d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(d, WORKFLOW)), "a workflow that spends minutes and needs a secret is never written unasked")
        self.assertIn("0 proposed", r.stdout, "an offer is not a proposal to change the project's file")
        self.assertIn(f"OFFERED  {WORKFLOW}", r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(d, ".git", "reef", "proposed", WORKFLOW)))
        self.assertEqual(I.read(d, "scripts/reef-factory.py"), I.read(ROOT, "scripts/reef-factory.py"), "the one command the job runs is copied")
        r = I.init(d, "--accept", WORKFLOW)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        text = I.read(d, WORKFLOW)
        for needle in ("reef-ready", "ANTHROPIC_API_KEY", "scripts/reef-factory.py row", "--issue", "--actor", "--plugin-dir", "ref: develop",
                       "workflow_dispatch", "timeout-minutes: 300", "REEF_TOKEN", "protected branch", "UNEDITED"):
            self.assertIn(needle, text, needle)
        self.assertNotIn("schedule:", text, "no schedule until it drains reef-ready rows (the review, 2026-10-27)")
        self.assertNotRegex(text, r"\{\{[a-z_]+\}\}", "every Reef placeholder rendered (GitHub's ${{ }} expressions stay)")
        self.assertRegex(text, r"checkout -q [0-9a-f]{40}\b", "the plugin pinned at the commit this project's scripts came from, never a moving ref")
        self.assertRegex(text, r"git clone -q https://github\.com/\S+/reef ")
        self.assertNotRegex(text, r"(?i)opus|sonnet|haiku")
        self.assertNotRegex(text, r"\$\{\{\s*inputs\.row\s*\}\}[^\n]*>>", "a dispatch input never lands in a shell line: it goes through env")
        r = I.init(d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("OFFERED", r.stdout, "accepted once, it is the project's file: refreshed like the others, never offered again")
        self.assertRegex(r.stdout, r"\n  0 written, (\d+ updated, )?\d+ skipped, 0 proposed")


class RunRow(unittest.TestCase):
    def test_the_runner_drives_one_row_and_loads_the_plugin_the_environment_names(self):
        d = git_repo(prefix="reef-factory-run.", branch="main")
        os.makedirs(os.path.join(d, ".reef"))
        open(os.path.join(d, ".reef", "config.json"), "w").write('{"gates": {"full": "true"}}')
        b = os.path.join(d, ".bin")
        os.makedirs(b)
        open(os.path.join(b, "claude"), "w").write(FAKE_CLAUDE)
        os.chmod(os.path.join(b, "claude"), 0o755)
        env = dict(os.environ, PATH=b + os.pathsep + os.environ["PATH"], REEF_CLAUDE_ARGS="--plugin-dir /x/reef")
        env.pop("REEF_CLAUDE", None)
        r = subprocess.run([sys.executable, RUN, "probe", "--repo", d], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = subprocess.run([sys.executable, RUN, "--row", "12", "--max-iterations", "1", "--repo", d], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        argv = [json.loads(l) for l in open(os.path.join(d, ".fake-argv"))]
        self.assertEqual(len(argv), 2)
        prompt = argv[1][argv[1].index("-p") + 1]
        self.assertTrue(prompt.startswith("/reef-loop 12 "), prompt)
        self.assertIn("--plugin-dir", argv[1]); self.assertIn("/x/reef", argv[1], "REEF_CLAUDE_ARGS, split like a shell would")
        self.assertIn("--plugin-dir", argv[0], "the probe's session loads the same plugin: the gate proves THAT guard")
        r = subprocess.run([sys.executable, RUN, "--row", "x", "--repo", d], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 1, "a row id is digits")
        r = subprocess.run([sys.executable, RUN, "probe", "--repo", d], capture_output=True, text=True, env=dict(env, REEF_CLAUDE_ARGS="--plugin-dir 'x"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("REEF_CLAUDE_ARGS", r.stderr, "an unbalanced quote is a refusal, not a traceback")


class _Forge(QI.Base):
    """Issues mode with a planned row 3 (issue 12, `[3] exact totals`) whose feature folder is in the checkout; a bare origin."""

    def setUp(self):
        super().setUp()
        with open(os.path.join(self.bin, "gh"), "w") as f:
            f.write(FAKE_GH)
        with open(os.path.join(self.bin, "claude"), "w") as f:
            f.write(FAKE_CLAUDE)
        os.chmod(os.path.join(self.bin, "claude"), 0o755)
        self.cfg["paths"]["features"] = "reef/features"
        self.cfg["branches"] = {"base": "main", "release": "release"}
        self.cfg["gates"], self.cfg["merge"] = {"full": "true"}, {"by": "loop"}
        with open(os.path.join(self.d, ".reef", "config.json"), "w") as f:
            f.write(json.dumps(self.cfg, indent=2) + "\n")
        os.makedirs(os.path.join(self.d, "scripts"))
        for n in ("reef-queue.py", "reef-row.py", "reef-plan-check.py", "reef-evidence.py", "reef-gate.sh", "reef-snapshot.sh", "reef-run.py",
                  "reef-approval.py", "reef-factory.py", "reef_common.py"):
            shutil.copy(os.path.join(ROOT, "scripts", n), os.path.join(self.d, "scripts", n))
        TR.write(self.d, "reef/features/exact-totals/SPEC.md", TR.SPEC.replace("Row: 1", "Row: 3"))
        TR.write(self.d, "reef/features/exact-totals/tasks/301-slice.md", TR.TASK.replace("feature: demo-row-one", "feature: exact-totals").replace("id: 101", "id: 301"))
        TR.write(self.d, ".gitignore", ".reef/approvals/\n.reef/queue.json\n.reef/queue-view.md\n.reef/run/\n.reef/loop.json\n.reef/worktrees/\n"
                                       "reef/features/*/tasks/.plan-review.json\nscripts/__pycache__/\n.fake-argv\n")
        TR.write(self.d, "CLAUDE.md", "# brief\n")
        TR.git(self.d, "add", "-A"); TR.git(self.d, "commit", "-qm", "init")
        self.origin = os.path.join(self.tmp, "origin.git")
        subprocess.run(["git", "init", "-q", "--bare", self.origin], check=True)
        TR.git(self.d, "remote", "add", "origin", self.origin)
        TR.git(self.d, "push", "-q", "origin", "main")
        s = self.forge()
        self.issue_12 = next(i for i in s["issues"] if i["number"] == 12)
        self.issue_12["labels"].append("reef-ready")
        s["perm"] = {"mahmoud": "admin", "owner": "admin", "bob": "write"}
        self.put(s)
        pc = os.path.join(self.d, "scripts", "reef-plan-check.py")
        r = subprocess.run([sys.executable, pc, self.d], capture_output=True, text=True)   # the stamp, as /reef-plan leaves it
        self.assertEqual(r.returncode, 0, r.stdout)
        r = subprocess.run([sys.executable, pc, self.d, "--digest", "--feature", "exact-totals"], capture_output=True, text=True)
        self.digest = r.stdout.split()[-1][:16]

    def env(self, **extra):
        e = dict(os.environ, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""), GH_STATE=self.state, GH_MODE="ok", **extra)
        e.pop("REEF_CLAUDE", None)
        return e

    def approval(self, *args):
        return subprocess.run([sys.executable, APPROVAL, *args], capture_output=True, text=True, env=self.env(), cwd=self.d)

    def labels(self):
        return self.issue("3")["labels"]

    def comment(self, body, login="mahmoud", updated_at=None):
        s = self.gh()
        next(i for i in s["issues"] if i["number"] == 12).setdefault("forge_comments", []).append({"login": login, "body": body, "updated_at": updated_at})
        self.put(s)


class Labels(_Forge):
    def test_the_rows_state_is_written_back_as_one_label(self):
        r = self.q("issue-row", "12")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "3"), r.stdout + r.stderr)
        r = self.q("row-issue", "3")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "12"), r.stdout + r.stderr)
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
        s = self.gh()
        s["issues"].append(dict(self.issue_12, number=19, title="[3] exact totals (a duplicate)", labels=["reef-row"]))
        self.put(s)
        r = self.q("row-issue", "3")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("duplicate", r.stderr + r.stdout, "two issues with one id: neither is the row until one is closed")


class FromIssue(_Forge):
    def test_only_the_owners_unedited_comment_at_the_current_digest_is_the_approval(self):
        rec = os.path.join(self.d, ".reef", "approvals", "exact-totals.json")
        r = self.approval("--from-issue", "3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"Approve plan exact-totals at {self.digest}?", r.stdout, "the exact line the owner posts")
        self.assertFalse(os.path.exists(rec))
        self.comment(f"Approve plan exact-totals at {self.digest}?", login="bob")
        r = self.approval("--from-issue", "3")
        self.assertIn("not by an admin", r.stdout); self.assertFalse(os.path.exists(rec), "write access is not the owner")
        self.comment("Approve plan exact-totals at 0123456789abcdef?")
        r = self.approval("--from-issue", "3")
        self.assertIn("stale", r.stdout); self.assertFalse(os.path.exists(rec), "the newest ADMIN comment decides, and this one is stale")
        self.comment(f"Approve plan exact-totals at {self.digest}?", updated_at="2026-10-27T09:00:00Z")
        r = self.approval("--from-issue", "3")
        self.assertIn("edited", r.stdout); self.assertFalse(os.path.exists(rec), "a write collaborator can rewrite anyone's comment: an edited one is not the owner's word")
        self.comment(f"Approve plan exact-totals at {self.digest}?")
        self.comment(f"Approve plan exact-totals at {self.digest}?", login="bob")   # noise after the owner's line is not a veto
        r = self.approval("--from-issue", "3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("approved at", r.stdout)
        got = json.load(open(rec))
        self.assertEqual(got["digest16"], self.digest)
        self.assertEqual(got["by"], "owner (issue #12, @mahmoud)")
        r = subprocess.run([sys.executable, os.path.join(self.d, "scripts", "reef-plan-check.py"), self.d, "--verify-stamp", "--feature", "exact-totals"], capture_output=True, text=True)
        self.assertIn("approval: OK", r.stdout, "the guard's check reads it like the hook's record")

    def test_the_comment_is_matched_against_the_checkout_whose_plan_it_names(self):
        # row 187's shape: the plan amended in its feature worktree, an older copy in a checkout `git worktree list` names first
        wt = os.path.join(self.d, ".reef", "worktrees", "exact-totals")
        TR.git(self.d, "worktree", "add", "-q", "-b", "feat/exact-totals", wt)
        with open(os.path.join(wt, "reef", "features", "exact-totals", "SPEC.md"), "a") as f:
            f.write("\nAmended in the feature worktree.\n")
        r = subprocess.run([sys.executable, os.path.join(self.d, "scripts", "reef-plan-check.py"), wt, "--digest", "--feature", "exact-totals"], capture_output=True, text=True)
        new = r.stdout.split()[-1][:16]
        self.assertNotEqual(new, self.digest)
        r = self.approval("--from-issue", "3")
        self.assertIn(f"Approve plan exact-totals at {new}?", r.stdout, "the line to post names the feature worktree's plan, as the row machine does")
        self.comment(f"Approve plan exact-totals at {self.digest}?")
        r = self.approval("--from-issue", "3")
        self.assertIn("stale", r.stdout, "a comment on the older copy approves nothing, however many checkouts still hold it")
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "approvals", "exact-totals.json")))
        self.comment(f"Approve plan exact-totals at {new}?")
        r = self.approval("--from-issue", "3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn("approved at", r.stdout)
        self.assertEqual(json.load(open(os.path.join(self.d, ".reef", "approvals", "exact-totals.json")))["digest16"], new)

    def test_a_row_without_a_plan_has_nothing_to_approve(self):
        r = self.approval("--from-issue", "4")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("nothing to approve", r.stdout)


class FactoryRun(_Forge):
    def factory(self, *args, **extra):
        return subprocess.run([sys.executable, FACTORY, "row", *args, "--repo", self.d], capture_output=True, text=True, env=self.env(**extra), cwd=self.d)

    def calls(self):
        p = os.path.join(self.d, ".fake-argv")
        return [json.loads(l) for l in open(p)] if os.path.exists(p) else []

    def test_the_one_command_checks_who_asked_and_the_protected_base_before_the_model_runs(self):
        r = self.factory("--issue", "12", "--actor", "bob")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("not admin", r.stdout); self.assertEqual(self.calls(), [], "no model ran")
        s = self.gh(); s["perm"]["owner"] = "triage"; self.put(s)
        r = self.factory("--issue", "12", "--actor", "mahmoud")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("issue's author", r.stdout, "the issue's body is the planner's spec: its author must be an admin too")
        s = self.gh(); s["perm"]["owner"] = "admin"; s["protected"] = False; self.put(s)
        r = self.factory("--issue", "12", "--actor", "mahmoud")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("protected branch", r.stdout); self.assertEqual(self.calls(), [])
        r = self.factory("--issue", "x", "--actor", "mahmoud")
        self.assertEqual(r.returncode, 2)

    def test_the_one_command_resumes_the_branch_probes_approves_builds_pushes_and_labels(self):
        TR.git(self.d, "branch", "feat/exact-totals", "main")
        TR.git(self.d, "push", "-q", "origin", "feat/exact-totals")
        TR.git(self.d, "branch", "-D", "feat/exact-totals")          # the last job pushed it; this runner starts bare
        self.comment(f"Approve plan exact-totals at {self.digest}?")
        r = self.factory("--issue", "12", "--actor", "mahmoud", REEF_CLAUDE_ARGS="--plugin-dir /x/reef")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("resumed feat/exact-totals", r.stdout)
        self.assertTrue(os.path.isdir(os.path.join(self.d, ".reef", "worktrees", "exact-totals")), "the row's worktree, from the forge")
        self.assertIn("approved at", r.stdout, "the owner's comment became the record before the build")
        calls = self.calls()
        self.assertEqual(len(calls), 2, "the probe, then the build")
        self.assertIn("probe", calls[0][calls[0].index("-p") + 1])
        self.assertTrue(calls[1][calls[1].index("-p") + 1].startswith("/reef-loop 3 "))
        self.assertIn("/x/reef", calls[1])
        self.assertIn("pushed feat/exact-totals", r.stdout)
        self.assertIn("reef-building", self.labels(), "approved, nothing built yet: the row is in build")
        self.assertNotIn("reef-ready", self.labels())
        self.assertIn("waiting on you", r.stdout, "the runner's wait is printed, not hidden")


if __name__ == "__main__":
    unittest.main()


class RunKeepsItsTimeoutCode(unittest.TestCase):
    def test_a_timed_out_command_is_1_as_before_so_a_timeout_is_never_built(self):
        # the security review of #215: reef_common.run says 124 on a timeout; reef-factory.py's `built = rc != 1` would have
        # read a timed-out build as built and pushed it. Its adapter keeps the 1 the old copy returned; so do reef-loop's and reef-row's
        import importlib.machinery, importlib.util
        for name in ("reef-factory.py", "reef-loop.py", "reef-row.py"):
            loader = importlib.machinery.SourceFileLoader("m_" + name.replace("-", "_").replace(".", "_"), os.path.join(ROOT, "scripts", name))
            spec = importlib.util.spec_from_loader(loader.name, loader)
            mod = importlib.util.module_from_spec(spec)
            loader.exec_module(mod)
            out = mod.run([sys.executable, "-c", "import time; time.sleep(5)"], ROOT, 0.2)
            self.assertEqual(out[0], 1, f"{name}: a timeout is 1, as before ({out})")
