"""Sabotage suite for 0.6 item 1.1: review records bound to the forge SHA. A fake `gh` on PATH answers from
the fixture repository the way the forge would (head of the PR branch, tree of a commit, tip of the base).
Push after GREEN then merge -> DENY; gh non-zero or slow -> DENY; a clean base merge -> allow; a rebase ->
DENY; an old git -> DENY; merge.by: human -> the record gates nothing."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, "scripts", "reef-guard.py")
RECORD = os.path.join(ROOT, "scripts", "reef-record")

FAKE_GH = r'''#!/usr/bin/env python3
"""fake gh: answers `pr view` and `api` from the repository in GH_REPO, as the forge would."""
import json, os, re, subprocess, sys, time
mode = os.environ.get("GH_MODE", "ok")
if mode == "fail":
    print("HTTP 502", file=sys.stderr); sys.exit(1)
if mode == "slow":
    time.sleep(30)
repo = os.environ["GH_REPO"]
rev = lambda x: subprocess.run(["git", "-C", repo, "rev-parse", x], capture_output=True, text=True).stdout.strip()
a = sys.argv[1:]
if a[:2] == ["pr", "view"]:
    print(json.dumps({"headRefOid": rev("feat"), "baseRefName": "main", "url": "https://github.com/o/r/pull/7", "number": 7}))
elif a[:1] == ["api"]:
    m = re.search(r"git/commits/([0-9a-f]+)", a[1])
    if m:
        print(rev(m.group(1) + "^{tree}")); sys.exit(0)
    m = re.search(r"git/ref/heads/(\S+)", a[1])
    if m:
        print(rev(m.group(1))); sys.exit(0)
    sys.exit(1)
else:
    sys.exit(1)
'''


def git(d, *a):
    return subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True, capture_output=True, text=True).stdout.strip()


class _Repo:
    """The fixture repository and the fake forge, shared by the merge and the security-pass suites (a mixin, so the
    security suite does not re-run every merge test)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reef-record.")
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        with open(os.path.join(self.bin, "gh"), "w") as f:
            f.write(FAKE_GH)
        os.chmod(os.path.join(self.bin, "gh"), 0o755)
        self.d = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.d, ".reef"))
        subprocess.run(["git", "init", "-q", "-b", "main", self.d], check=True)
        with open(os.path.join(self.d, ".reef", "config.json"), "w") as f:
            json.dump({"gates": {"full": "true"}, "merge": {"by": "loop"}, "branches": {"base": "main", "release": "release"}}, f)
        with open(os.path.join(self.d, "app.py"), "w") as f:
            f.write("x = 1\n")
        git(self.d, "add", "-A")
        git(self.d, "commit", "-qm", "base")
        git(self.d, "checkout", "-qb", "feat")
        with open(os.path.join(self.d, "app.py"), "w") as f:
            f.write("x = 2\n")
        git(self.d, "commit", "-qam", "feature work")

    def env(self, **kw):
        e = dict(os.environ, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""), GH_REPO=self.d, REEF_GH_TIMEOUT="2")
        e.pop("CLAUDE_PLUGIN_ROOT", None)
        e.update(kw)
        return e

    def record(self, verdict="GREEN", report="ok", **kw):
        """A GREEN/PASS record carries its reviewer's report (2026-10-24): the VERDICT line and the head it reviewed."""
        args = [sys.executable, RECORD, "demo", verdict, "--root", self.d]
        if report and verdict in ("GREEN", "PASS"):
            p = os.path.join(self.tmp, "review.md")
            head = git(self.d, "rev-parse", "feat")[:12] if report != "old-head" else "0123456789ab"
            with open(p, "w") as f:
                f.write(f"RUN: agent=acceptance feature=demo\nHEAD: {head}\n" + ("VERDICT: FAIL\n" if report == "fail" else f"VERDICT: {verdict}\n"))
            args += ["--report", p]
        return subprocess.run(args, capture_output=True, text=True, env=self.env(**kw))

    def merge(self, cmd="gh pr merge 7 --squash --delete-branch", **kw):
        payload = {"tool_name": "Bash", "cwd": self.d, "tool_input": {"command": cmd}}
        return subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True, env=self.env(**kw))



class ForgeMerge(_Repo, unittest.TestCase):
    def test_record_written_from_the_forge_and_merge_allowed_on_that_head(self):
        r = self.record()
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.d, ".reef", "review", "demo.json")) as f:
            rec = json.load(f)
        self.assertEqual(rec["sha"], git(self.d, "rev-parse", "feat"))
        self.assertEqual(rec["tree"], git(self.d, "rev-parse", "feat^{tree}"))
        self.assertEqual(rec["verdict"], "GREEN")
        self.assertEqual(self.merge().returncode, 0, self.merge().stderr)
        self.assertEqual(self.merge("gh api -X PUT repos/o/r/pulls/7/merge -f merge_method=squash").returncode, 0)

    def test_green_needs_the_feature_guard_pass_under_feature_mode(self):
        # 0.7 hunter.guard_pass = feature: the merge's GREEN record is the enforcement point (the pre-commit no longer is)
        with open(os.path.join(self.d, ".reef", "config.json"), "w") as f:
            json.dump({"gates": {"full": "true"}, "merge": {"by": "loop"}, "branches": {"base": "main", "release": "release"},
                       "hunter": {"guard_pass": "feature"}, "paths": {"features": "reef/features"}}, f)
        tasks = os.path.join(self.d, "reef", "features", "demo", "tasks", "done")
        os.makedirs(tasks)
        tp = os.path.join(tasks, "001-a.md")
        with open(tp, "w") as f:
            f.write("---\nid: 1\nfeature: demo\nstatus: done\ncomplexity: design\ntier: critical\nverify: judge\nattempts: 0\n"
                    "adversarial-plan: aaaaaaaaaaaa\n---\n# 1\n\n## Log\n")
        r = self.record()
        self.assertNotEqual(r.returncode, 0, "GREEN recorded without the feature's guard pass")
        self.assertIn("--feature demo guard", r.stderr)
        self.assertIn("task(s) 1", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "review", "demo.json")))
        with open(os.path.join(self.d, "guard.md"), "w") as f:
            f.write("RUN: agent=loophole-hunter task=1 pass=guard\nBLOCKER: none\nVERDICT: PASS\n")
        a = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-adversarial"), "--feature", "demo", "guard", os.path.join(self.d, "guard.md")],
                           capture_output=True, text=True, cwd=self.d)
        self.assertEqual(a.returncode, 0, a.stderr)
        r = self.record()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.record("FAIL").returncode, 0, "a FAIL record never needs the pass")

    def test_no_record_denied(self):
        r = self.merge()
        self.assertEqual(r.returncode, 2)
        self.assertIn("no PASS/GREEN review record", r.stderr)

    def test_push_after_green_denied_claims_only_allowed(self):
        self.record()
        with open(os.path.join(self.d, "app.py"), "a") as f:
            f.write("y = 3\n")
        git(self.d, "commit", "-qam", "sneaky code after GREEN")
        r = self.merge()
        self.assertEqual(r.returncode, 2)
        self.assertIn("moved since the GREEN record", r.stderr)
        # a claims-only commit (docs) on top of the GREEN head is the one allowed move
        git(self.d, "reset", "-q", "--hard", "HEAD~1")
        with open(os.path.join(self.d, "CLAIMS.md"), "w") as f:
            f.write("x is 2 — true at app.py:1\n")
        git(self.d, "add", "CLAIMS.md")
        git(self.d, "commit", "-qm", "claims")
        self.assertEqual(self.merge().returncode, 0, self.merge().stderr)

    def test_clean_base_merge_allowed_rebase_denied(self):
        self.record()
        git(self.d, "checkout", "-q", "main")
        with open(os.path.join(self.d, "other.py"), "w") as f:
            f.write("z = 9\n")
        git(self.d, "add", "other.py")
        git(self.d, "commit", "-qm", "main moved")
        git(self.d, "checkout", "-q", "feat")
        git(self.d, "merge", "-q", "--no-edit", "main")
        r = self.merge()
        self.assertEqual(r.returncode, 0, f"a clean merge of the base is a carry-over: {r.stderr}")
        r = self.merge(REEF_GIT_VERSION_OVERRIDE="2.30")
        self.assertEqual(r.returncode, 2, "an old git cannot prove the carry-over")
        self.assertIn("2.38", r.stderr)
        # the same content REBASED: the reviewed commit is no longer an ancestor
        git(self.d, "reset", "-q", "--hard", "HEAD~1")
        git(self.d, "rebase", "-q", "main")
        r = self.merge()
        self.assertEqual(r.returncode, 2)
        self.assertIn("not an ancestor", r.stderr)

    def test_green_carries_its_reviewers_report(self):
        # 2026-10-24, the trial: the guard refused a merge ("re-review and re-record"), and the orchestrator re-recorded
        # GREEN at the new head with no review. A GREEN record now carries the report that names the head it reviewed.
        r = self.record(report=None)
        self.assertEqual(r.returncode, 2)
        self.assertIn("carries its reviewer's report", r.stderr)
        r = self.record(report="old-head")
        self.assertEqual(r.returncode, 2)
        self.assertIn("reviewed 0123456789ab, not the PR head", r.stderr)
        r = self.record(report="fail")
        self.assertEqual(r.returncode, 2)
        self.assertIn("says VERDICT: FAIL", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "review", "demo.json")))
        r = self.record()
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.d, ".reef", "review", "demo.json")) as f:
            self.assertRegex(json.load(f)["report_sha256"], r"^[0-9a-f]{64}$")

    def test_a_conflicted_base_merge_that_leaves_the_feature_unchanged_carries_over(self):
        # both sides appended to the journal, as parallel features do: the merge conflicts, the resolution keeps both
        # lines, and the feature's own change is byte-for-byte the one reviewed — no re-record needed
        for branch, line in (("main", "| base row |\n"), ("feat", "| feature row |\n")):
            git(self.d, "checkout", "-q", branch)
            with open(os.path.join(self.d, "journal.md"), "a") as f:
                f.write("# Journal\n" if branch == "main" else "")
            if branch == "main":
                git(self.d, "add", "journal.md"); git(self.d, "commit", "-qm", "journal")
                git(self.d, "checkout", "-q", "feat"); git(self.d, "merge", "-q", "--no-edit", "main")
                git(self.d, "checkout", "-q", "main")
            with open(os.path.join(self.d, "journal.md"), "a") as f:
                f.write(line)
            if branch == "main":   # the base also brings another feature's code, so the move is not claims-only
                with open(os.path.join(self.d, "other.py"), "w") as f:
                    f.write("z = 9\n")
                git(self.d, "add", "other.py")
            git(self.d, "commit", "-qam", f"{branch} journal row")
        self.record()
        subprocess.run(["git", "-C", self.d, "merge", "-q", "--no-edit", "main"], capture_output=True)
        with open(os.path.join(self.d, "journal.md"), "w") as f:
            f.write("# Journal\n| base row |\n| feature row |\n")
        git(self.d, "add", "journal.md")
        git(self.d, "commit", "-qm", "merge main, both journal rows kept")
        r = self.merge()
        self.assertEqual(r.returncode, 0, f"the feature's own diff is the reviewed one: {r.stderr}")
        with open(os.path.join(self.d, "app.py"), "a") as f:
            f.write("y = 3\n")
        git(self.d, "commit", "-q", "--amend", "-a", "--no-edit")
        r = self.merge()
        self.assertEqual(r.returncode, 2, "code slipped into the merge resolution: re-review")
        self.assertIn("moved since the GREEN record", r.stderr)

    def test_gh_failure_or_slowness_denies(self):
        self.record()
        r = self.merge(GH_MODE="fail")
        self.assertEqual(r.returncode, 2)
        self.assertIn("refusing to merge blind", r.stderr)
        t0 = time.monotonic()
        r = self.merge(GH_MODE="slow", REEF_GH_TIMEOUT="1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("did not answer", r.stderr)
        self.assertLess(time.monotonic() - t0, 8)
        r = self.record(GH_MODE="fail")
        self.assertEqual(r.returncode, 2, "reef-record exits 2 when gh fails")
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "review", "demo.json")) and json.load(open(os.path.join(self.d, ".reef", "review", "demo.json"))).get("verdict") != "GREEN")

    def test_merge_by_human_gates_nothing(self):
        with open(os.path.join(self.d, ".reef", "config.json"), "w") as f:
            json.dump({"gates": {"full": "true"}, "merge": {"by": "human"}}, f)
        self.assertEqual(self.merge().returncode, 0)
        self.assertEqual(self.record().returncode, 0, "the record is still written as the journal's evidence")

    def test_fail_record_does_not_count(self):
        self.record("FAIL")
        r = self.merge()
        self.assertEqual(r.returncode, 2)




class SecurityPass(_Repo, unittest.TestCase):
    """0.7 (the owner, 2026-10-19: "Reef is meant for others, the security pass should be solid"): the release's audit is
    Reef's own agent (reef:security), its verdict a record bound to the head of branches.base, and the guard opens the
    release PR only on a PASS at that exact head. A security record never stands in for a feature's GREEN."""

    def report(self, text):
        p = os.path.join(self.tmp, "security.md")
        with open(p, "w") as f:
            f.write(text)
        return p

    def sec(self, verdict, report):
        args = [sys.executable, RECORD, "security", verdict] + (["--report", report] if report else []) + ["--root", self.d]
        return subprocess.run(args, capture_output=True, text=True, env=self.env())

    def create(self, cmd="gh pr create --base release --head main --title r --body b", **kw):
        payload = {"tool_name": "Bash", "cwd": self.d, "tool_input": {"command": cmd}}
        return subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True, env=self.env(**kw))

    GOOD = "RUN: agent=security range=release...main head=x\nSPINE: reef/architecture/threat-model.md\nHIGH src/a.ts:3 — x — y\nVERDICT: PASS\n"

    def test_the_record_carries_the_agents_own_verdict_or_nothing(self):
        for verdict, report, why in (("PASS", None, "--report"),
                                     ("PASS", "VERDICT: PASS\n", "RUN: agent=security"),
                                     ("PASS", "RUN: agent=security\nnothing\n", "VERDICT"),
                                     ("PASS", "RUN: agent=security\nVERDICT: FAIL\n", "not PASS"),
                                     ("PASS", "RUN: agent=security\nBLOCKER src/a.ts:1 — x — y\nVERDICT: PASS\n", "BLOCKER")):
            with self.subTest(why=why):
                r = self.sec(verdict, self.report(report) if report else None)
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertIn(why, r.stderr)
        self.assertFalse(os.path.isdir(os.path.join(self.d, ".reef", "review")) and any(
            f.startswith("security-") for f in os.listdir(os.path.join(self.d, ".reef", "review"))), "a refused record writes nothing")
        r = self.sec("PASS", self.report(self.GOOD))
        self.assertEqual(r.returncode, 0, r.stderr)
        head = git(self.d, "rev-parse", "main")
        with open(os.path.join(self.d, ".reef", "review", f"security-{head[:12]}.json")) as f:
            rec = json.load(f)
        self.assertEqual((rec["kind"], rec["head"], rec["verdict"], rec["base"]), ("security", head, "PASS", "main"))
        self.assertNotIn("sha", rec, "stored as `head`: the merge check's `sha` must never match a security record")
        self.assertEqual(len(rec["report_sha256"]), 64)

    def test_the_release_pr_opens_only_on_a_pass_at_its_exact_head(self):
        r = self.create()
        self.assertEqual(r.returncode, 2, "release PR opened with no security pass")
        self.assertIn("no PASS security record", r.stderr)
        self.assertIn("reef:security", r.stderr)
        self.sec("FAIL", self.report("RUN: agent=security\nBLOCKER src/a.ts:1 — x — y\nVERDICT: FAIL\n"))
        self.assertEqual(self.create().returncode, 2, "a FAIL record opens nothing")
        self.sec("PASS", self.report(self.GOOD))
        for cmd in ("gh pr create --base release --head main --title r --body b",
                    "gh pr create -B release -H main -t r -b b", "gh pr create --base=release --head=main --fill"):
            with self.subTest(cmd=cmd):
                r = self.create(cmd)
                self.assertEqual(r.returncode, 0, r.stderr)
        # no --base: gh targets the forge's default branch, the release branch on a base/release project
        r = self.create("gh pr create --head main --title r --body b")
        self.assertEqual(r.returncode, 2, "a release PR with no --base slipped past the security pass")
        self.assertIn("--base release", r.stderr)
        self.assertEqual(self.create("gh pr create --head feat --fill").returncode, 0, "a feature PR with no --base is not the release PR")
        # the base moved after the pass: a new release, audited again
        git(self.d, "checkout", "-q", "main")
        with open(os.path.join(self.d, "late.py"), "w") as f:
            f.write("y = 1\n")
        git(self.d, "add", "late.py")
        git(self.d, "commit", "-qm", "late change")
        r = self.create()
        self.assertEqual(r.returncode, 2, "a commit after the pass reached the release PR")
        # untouched: a feature PR into the base, and a project with no release step
        self.assertEqual(self.create("gh pr create --base main --head feat --title f --body b").returncode, 0)
        with open(os.path.join(self.d, ".reef", "config.json"), "w") as f:
            json.dump({"gates": {"full": "true"}, "merge": {"by": "loop"}, "branches": {"base": "main", "release": "main"}}, f)
        self.assertEqual(self.create("gh pr create --base main --head feat --title f --body b").returncode, 0)

    def test_a_security_record_never_opens_a_feature_merge(self):
        git(self.d, "checkout", "-q", "feat")
        git(self.d, "branch", "-f", "main", "feat")    # the worst case: the audited head IS the PR head
        self.sec("PASS", self.report(self.GOOD))
        r = self.merge()
        self.assertEqual(r.returncode, 2, "a security PASS opened `gh pr merge` without the feature's GREEN")
        self.assertIn("no PASS/GREEN review record", r.stderr)

if __name__ == "__main__":
    unittest.main()
