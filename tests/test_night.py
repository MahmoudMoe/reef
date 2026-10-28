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


class TonightOnly(unittest.TestCase):
    """2026-10-21 (qassimha): last night's approval (rows 3 and 12, both closed since) still passed `--night`; the night
    ran one 29-second session and waited for the owner."""

    def test_an_old_approval_or_a_contract_with_no_open_row_is_refused(self):
        d = project()
        approve_night(self, d)
        p = os.path.join(d, ".reef", "approvals", "night.json")
        rec = json.load(open(p))
        rec["approved_at"] = "2020-01-01T00:00:00Z"
        json.dump(rec, open(p, "w"))
        r = R.run(d, ["stop:x"], "--night")
        self.assertEqual(r.returncode, 1)
        self.assertIn("another night's — run /reef-night for tonight", r.stderr)
        d = project()
        approve_night(self, d)
        L.write(d, "reef/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n"
                                    "| 3 | items | | planned | 1 | |\n")   # row 12 closed: moved to the archive
        L.write(d, "reef/queue-archive.md", "| 12 | share links | | planned | 1 | |\n")
        r = R.run(d, ["stop:x"], "--night")
        self.assertEqual(r.returncode, 1)
        self.assertIn("every row of the contract (12) is closed", r.stderr)


class ContractNamesTheReadyRows(unittest.TestCase):
    def test_the_contract_warns_of_a_ready_row_it_leaves_out(self):
        d = project()   # rows 12 and 3 ready; the contract names 12
        r = subprocess.run([sys.executable, RUN, "contract", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("WARN ready rows not in tonight's contract, which the night will not touch: 3", r.stdout)


class PersonalProfile(unittest.TestCase):
    def test_a_new_projects_first_night_starts_from_the_owners_personal_profile(self):
        # 2026-10-21, the owner: "this means I cannot start night mode at the beginning of the project!"
        d = project()
        os.remove(os.path.join(d, "reef", "owner.md"))
        mine = os.path.join(tempfile.mkdtemp(prefix="reef-home."), "owner.md")
        with open(mine, "w") as f:
            f.write("# The owner, everywhere\nSimple and robust.\n")
        env = dict(os.environ, REEF_OWNER_PROFILE=mine)
        r = subprocess.run([sys.executable, RUN, "contract", "--repo", d], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("seeded reef/owner.md", r.stdout)
        self.assertEqual(open(os.path.join(d, "reef", "owner.md")).read(), open(mine).read())
        with open(os.path.join(d, "reef", "owner.md"), "a") as f:
            f.write("Project: exact money.\n")
        subprocess.run([sys.executable, RUN, "contract", "--repo", d], capture_output=True, text=True, env=env)
        self.assertIn("Project: exact money.", open(os.path.join(d, "reef", "owner.md")).read(), "an existing project profile is never overwritten")


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


class SquashMergesAreListed(unittest.TestCase):
    """2026-10-28, the first night: row 3 merged by `gh pr merge --squash` and the report said "Merges into develop: none" —
    a squash leaves no merge commit. A first-parent commit whose subject ends in (#n) is that merge, with its own undo."""

    def test_the_report_lists_a_squash_merge_with_its_undo(self):
        d = project()
        b = os.path.join(d, ".bin")
        os.makedirs(b)
        open(os.path.join(b, "claude"), "w").write(R.FAKE)
        os.chmod(os.path.join(b, "claude"), 0o755)
        self.assertEqual(R.run(d, ["probe-deny"], "probe").returncode, 0)
        approve_night(self, d)
        L.write(d, "src/x.py", "x = 1\n")
        L.git(d, "add", "-A"); L.git(d, "commit", "-qm", "feat(share-links): the slice (#63)")
        r = R.run(d, ["stop:night done"], "--night")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rep = open(os.path.join(d, ".reef", "night", "report.md")).read()
        self.assertIn("(#63)  (squash — undo: git revert <sha>)", rep)


class NightNumbers(unittest.TestCase):
    """The morning report counts the night (the owner's go, 2026-10-24, item 3: "how do I know the factory gets better"):
    rows merged into the base, tasks finished on any branch, the first-pass share, the stalls, the cost and the cost per
    merged row, beside the previous night's (.reef/night/history.jsonl)."""

    def test_the_report_counts_the_night_beside_the_last_one(self):
        import importlib.machinery, importlib.util
        loader = importlib.machinery.SourceFileLoader("reef_run_n", RUN)
        spec = importlib.util.spec_from_loader(loader.name, loader)
        run = importlib.util.module_from_spec(spec)
        loader.exec_module(run)
        d = tempfile.mkdtemp(prefix="reef-nightnum.")
        env = dict(os.environ, GIT_AUTHOR_DATE="2099-01-01T00:00:00Z", GIT_COMMITTER_DATE="2099-01-01T00:00:00Z")
        g = lambda *a: subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True, capture_output=True, env=env)
        for sub in ("night", "run", "approvals", "cost", "ci-local"):
            os.makedirs(os.path.join(d, ".reef", sub))
        with open(os.path.join(d, ".reef", "config.json"), "w") as f:
            json.dump({"branches": {"base": "develop"}}, f)
        g("init", "-q", "-b", "develop")
        g("commit", "-q", "--allow-empty", "-m", "start")
        g("checkout", "-qb", "feat/x")
        tdir = os.path.join(d, "reef", "features", "x", "tasks", "done")
        os.makedirs(tdir)
        for name, attempts in (("101-a.md", 0), ("102-b.md", 1)):
            with open(os.path.join(tdir, name), "w") as f:
                f.write(f"---\nid: {name[:3]}\nfeature: x\nstatus: done\nattempts: {attempts}\n---\n")
        with open(os.path.join(d, "app.py"), "w") as f:
            f.write("x = 1\n")
        g("add", "-A"); g("commit", "-qm", "tasks done")
        head = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        g("checkout", "-q", "develop")
        g("merge", "-q", "--squash", "feat/x"); g("commit", "-qm", "Feature x (#5)")
        os.makedirs(os.path.join(d, "reef"), exist_ok=True)
        with open(os.path.join(d, "reef", "queue.md"), "w") as f:
            f.write("| 1 | x | closed |\n")
        g("add", "-A"); g("commit", "-qm", "reef: close row 1")
        # v3 phase 1: the pipeline per row, beside the previous batch — an approval record, the cost record, the gate's run log
        with open(os.path.join(d, ".reef", "approvals", "x.json"), "w") as f:
            json.dump({"digest16": "0" * 16, "approved_at": "2099-01-01T00:00:00Z"}, f)
        with open(os.path.join(d, ".reef", "cost", "features.json"), "w") as f:
            json.dump({"x": {"s1": {"share": 1234, "planning_share": 0, "roles": {}, "turns": 1}}}, f)
        with open(os.path.join(d, ".reef", "ci-local", "runs.jsonl"), "w") as f:
            for mode in ("full", "fast", "full"):
                f.write(json.dumps({"at": "2099-01-01T00:00:00Z", "mode": mode, "head": head, "branch": "feat/x", "exit": 0, "seconds": 1}) + "\n")
        log = os.path.join(d, ".reef", "run", "run.log")
        with open(log, "w") as f:
            f.write(json.dumps({"at": "2099-01-01T00:00:00Z", "cost_usd": 10, "wait": "owner: approve row 12"}) + "\n")
            f.write(json.dumps({"at": "2099-01-01T01:00:00Z", "cost_usd": 6, "wait": "/clear requested"}) + "\n")
        run.morning_report(d, "2000-01-01T00:00:00Z", log)
        rep = open(os.path.join(d, ".reef", "night", "report.md")).read()
        for row in ("| Rows merged | 1 | – |", "| Tasks finished | 2 | – |", "| First pass | 1/2 (50%) | – |",
                    "| Stalls (waits on you, stops, parks) | 1 | – |", "| Cost | $16.00 | – |", "| Cost per merged row | $16.00 | – |",
                    "| Lead time per merged row, plan → merge (median) | 0m | – |", "| Of it after the approval (median) | 0m | – |",
                    "| Tokens per merged row (median) | 1,234 | – |", "| Full-suite runs per merged row (median) | 2 | – |",
                    "| Rework: rollups + reverts | 0 + 0 | – |", "| Process : product commits | 1 : 1 | – |"):
            self.assertIn(row, rep)
        run.morning_report(d, "2000-01-01T00:00:00Z", log)
        rep = open(os.path.join(d, ".reef", "night", "report.md")).read()
        self.assertIn("| First pass | 1/2 (50%) | 1/2 (50%) |", rep, "the second night shows the first beside it")
        self.assertIn("| Full-suite runs per merged row (median) | 2 | 2 |", rep)
        self.assertEqual(len(open(os.path.join(d, ".reef", "night", "history.jsonl")).read().splitlines()), 2)


if __name__ == "__main__":
    unittest.main()


class ContractFromTheInstalledFile(unittest.TestCase):
    """2026-10-28 (the current adoption): the owner re-ran `contract --from .reef/night/contract.md` — the installed
    contract itself — and the copy onto itself raised `shutil.SameFileError` as a traceback."""

    def test_the_installed_contract_as_the_source_is_left_in_place_and_a_missing_source_is_one_line(self):
        d = project()
        draft = os.path.join(tempfile.mkdtemp(prefix="reef-draft."), "night.md")
        with open(draft, "w") as f:
            f.write("# Night\nRows: 12\nDecisions: plan approvals.\nHard limits: the release to main.\n")
        r = subprocess.run([sys.executable, RUN, "contract", "--repo", d, "--from", draft], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("night digest: ", r.stdout)
        r = subprocess.run([sys.executable, RUN, "contract", "--repo", d, "--from", ".reef/night/contract.md"],
                           capture_output=True, text=True, cwd=d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("night digest: ", r.stdout)
        self.assertEqual(open(os.path.join(d, ".reef", "night", "contract.md")).read(), open(draft).read())
        r = subprocess.run([sys.executable, RUN, "contract", "--repo", d, "--from", os.path.join(d, "no-such.md")],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)
        self.assertTrue(r.stderr.startswith("reef-run: "), r.stderr)
