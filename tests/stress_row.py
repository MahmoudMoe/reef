"""Stress suite, round two — area `row`: scripts/reef-row.py (a row's one next step, its gh fallback, PR and branch
detection across checkouts) and scripts/reef-record (GREEN, FAIL and security records: head binding, a force-pushed head,
a report from another row). A failing test is a finding; see stress2-findings/row.md."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import write, git, ROOT  # noqa: E402  (the suites' shared fixtures, once)

ROW = os.path.join(ROOT, "scripts", "reef-row.py")
RECORD = os.path.join(ROOT, "scripts", "reef-record")
SCRIPTS = ("reef-row.py", "reef-queue.py", "reef-plan-check.py", "reef-evidence.py", "reef-gate.sh", "reef-snapshot.sh", "reef_common.py")
SLUG = "demo-row-one"
TASK = """---
id: 101
feature: demo-row-one
status: done
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
SPEC = ("# demo row one\nRow: {row}\n\n## Scope\nOne slice.\n\n## Non-goals\n- none\n\n## Already shipped\nnone\n\n"
        "## Requirements\n- FR-1 [backend]: it works.\n\n## Success criteria\n- SC-1: green.\n\n## Architecture impact\nnone\n")

# one fake forge for both scripts. GH_MODE: ok | fail | null. GH_PRS: the `pr list` answer (JSON text).
# `pr view [N]`: the head of GH_VIEW_BRANCH (or of the branch named by GH_BRANCH_<N>), PR number N (default 7).
FAKE_GH = r'''#!/usr/bin/env python3
import json, os, re, subprocess, sys
mode = os.environ.get("GH_MODE", "ok")
if mode == "fail":
    print("HTTP 401: Bad credentials (gh auth login)", file=sys.stderr); sys.exit(1)
repo = os.environ["GH_REPO"]
rev = lambda x: subprocess.run(["git", "-C", repo, "rev-parse", x], capture_output=True, text=True).stdout.strip()
a = sys.argv[1:]
if a[:2] == ["pr", "list"]:
    print("null" if mode == "null" else os.environ.get("GH_PRS", "[]"))
elif a[:2] == ["pr", "view"]:
    num = a[2] if len(a) > 2 and a[2].isdigit() else os.environ.get("GH_VIEW_NUM", "7")
    br = os.environ.get("GH_BRANCH_" + num) or os.environ.get("GH_VIEW_BRANCH", "feat/demo-row-one")
    print(json.dumps({"headRefOid": rev(br), "baseRefName": "main", "url": "https://github.com/o/r/pull/" + num, "number": int(num)}))
elif a[:1] == ["api"]:
    m = re.search(r"commits/([0-9a-f]+)/check-runs", a[1])
    if m:
        print(json.dumps({"total_count": 1, "check_runs": [{"name": "test", "status": "completed", "conclusion": "success"}]})); sys.exit(0)
    m = re.search(r"git/commits/([0-9a-f]+)", a[1])
    if m:
        print(rev(m.group(1) + "^{tree}")); sys.exit(0)
    sys.exit(1)
else:
    sys.exit(1)
'''


def out(d, *a):
    return git(d, *a).stdout.strip()


class _Forge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reef-stress-row.")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        with open(os.path.join(self.bin, "gh"), "w") as f:
            f.write(FAKE_GH)
        os.chmod(os.path.join(self.bin, "gh"), 0o755)

    def env(self, **kw):
        e = dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"], GH_REPO=self.main, REEF_GH_TIMEOUT="5")
        e.update(kw)
        return e


class _RowBase(_Forge):
    """A row built in its feature worktree, its task done, evidence green, a GREEN record at its head: the `merge` state."""

    def setUp(self, row="1", config=None):
        super().setUp()
        self.main = os.path.join(self.tmp, "main")
        os.makedirs(os.path.join(self.main, "scripts"))
        for n in SCRIPTS:
            shutil.copy(os.path.join(ROOT, "scripts", n), os.path.join(self.main, "scripts", n))
        cfg = {"gates": {"full": "echo '1 passed'"}, "ci": {"feature_gate": "local"}, "merge": {"by": "loop"},
               "branches": {"base": "main", "release": "release"}, "paths": {"queue": "reef/queue.md", "features": "reef/features"}}
        cfg.update(config or {})
        write(self.main, ".reef/config.json", json.dumps(cfg))
        write(self.main, ".reef/version", "0.6.0\n")
        write(self.main, ".gitignore", ".reef/worktrees/\n.reef/approvals/\n.reef/review/\n.reef/evidence/\n.reef/ci-local/\n"
                                       "reef/features/*/tasks/.plan-review.json\n")
        write(self.main, "reef/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n"
                                          f"| {row} | first | | planned | 1 | |\n")
        write(self.main, "CLAUDE.md", "# brief\n")
        git(self.main, "init", "-q", "-b", "main")
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            git(self.main, "config", k, v)
        git(self.main, "add", "-A"); git(self.main, "commit", "-qm", "init")
        git(self.main, "remote", "add", "origin", "https://github.com/o/r.git")
        self.feat = os.path.join(self.main, ".reef", "worktrees", SLUG)
        self.assertEqual(git(self.main, "worktree", "add", "-q", "-b", f"feat/{SLUG}", self.feat, "main").returncode, 0)
        write(self.feat, f"reef/features/{SLUG}/SPEC.md", SPEC.format(row=row))
        write(self.feat, f"reef/features/{SLUG}/tasks/done/101-slice.md", TASK)
        write(self.feat, "src/a.py", "a = 2\n")
        git(self.feat, "add", "-A"); git(self.feat, "commit", "-qm", "the slice")
        dg = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-plan-check.py"), self.feat, "--digest", "--feature", SLUG],
                            capture_output=True, text=True).stdout.split()[-1]
        write(self.main, f".reef/approvals/{SLUG}.json", json.dumps({"digest16": dg[:16], "digest": dg, "approved_at": "2026-11-03T00:00:00Z"}))
        self.assertEqual(subprocess.run(["sh", "scripts/reef-gate.sh", "full"], cwd=self.feat, capture_output=True).returncode, 0)
        self.head = out(self.feat, "rev-parse", "HEAD")
        write(self.main, f".reef/review/{SLUG}.json", json.dumps({"sha": self.head, "verdict": "GREEN", "pr": 7}))

    def state(self, key="1", **env):
        r = subprocess.run([sys.executable, ROW, "state", key, "--repo", self.main, "--json"], capture_output=True, text=True, env=self.env(**env), timeout=60)
        self.assertIn(r.returncode, (0, 2), r.stdout + r.stderr)
        return json.loads(r.stdout)


class RowNext(_RowBase):
    def test_coverage_an_open_pr_with_a_green_record_names_the_merge(self):
        s = self.state(GH_PRS='[{"number": 7, "state": "OPEN"}]')
        self.assertEqual((s["state"], s["next"]), ("merge", "gh pr merge 7 --squash --delete-branch"), s)

    def test_a_failing_gh_does_not_send_an_open_pr_back_to_be_created(self):
        # the PR is open on the forge; gh is unauthenticated. Contract: reef-row docstring "Nothing here is decided from memory
        # or prose"; the series rule (d83db09, H4) "a failed gh read is BROKEN, never empty". A failed `gh pr list` must be
        # named, never read as "no PR" — which makes the next step `/reef-review … (push, PR into main)`: a second PR.
        s = self.state(GH_MODE="fail", GH_PRS='[{"number": 7, "state": "OPEN"}]')
        self.assertNotIn("PR into", s["next"], f"gh failed, so the row cannot know there is no PR: {s}")
        self.assertIn("gh", (s["detail"] + " " + s["next"]).lower(), f"the failed gh read is named: {s}")

    def test_a_closed_unmerged_pr_is_never_named_for_merge(self):
        # the owner closed PR 7 without merging (abandoned, or to reopen after a rewrite). `gh pr merge 7` on a closed PR is a
        # dead step. Contract: docstring "merge (the PR is open, or the branch is not in the base)" — a CLOSED PR is neither.
        s = self.state(GH_PRS='[{"number": 7, "state": "CLOSED"}]')
        self.assertNotIn("gh pr merge 7", s["next"], f"PR 7 is closed, not open: {s}")

    def test_coverage_the_open_pr_wins_over_an_older_closed_one(self):
        s = self.state(GH_PRS='[{"number": 9, "state": "OPEN"}, {"number": 7, "state": "CLOSED"}]')
        self.assertEqual(s["next"], "gh pr merge 9 --squash --delete-branch", s)

    def test_coverage_gh_answering_null_is_not_a_crash(self):
        s = self.state(GH_MODE="null")
        self.assertEqual(s["state"], "merge", s)

    def test_coverage_a_squash_merge_reads_close_with_gh_down(self):
        git(self.main, "merge", "-q", "--squash", f"feat/{SLUG}"); git(self.main, "commit", "-qm", "Row 1: the slice (#7)")
        s = self.state(GH_MODE="fail")
        self.assertEqual(s["state"], "close", s)

    def test_coverage_a_force_pushed_head_after_green_goes_back_to_review(self):
        # the head moved after the GREEN (an amend + force push): reef-review SKILL "anything else is a fresh review"
        write(self.feat, "src/a.py", "a = 3\n")
        git(self.feat, "commit", "-qa", "--amend", "--no-edit")
        subprocess.run(["sh", "scripts/reef-gate.sh", "full"], cwd=self.feat, capture_output=True)
        s = self.state(GH_PRS='[{"number": 7, "state": "OPEN"}]')
        self.assertEqual(s["state"], "review", s)


class RowQueueOnIssues(_RowBase):
    def setUp(self):
        super().setUp(config={"queue": {"home": "issues"}})

    def test_a_merged_row_is_not_closed_when_the_queue_read_fails(self):
        # queue.home: issues, gh down, no .reef/queue.json snapshot: `reef-queue.py status` exits 1 ("gh failed and there is no
        # snapshot"). reef-row reads that as an empty queue, so a merged row whose issue is still open reads `closed — merged and
        # archived` and its close step (adr-number, archive, journal) is never run. Contract: docstring "close (merged, row
        # still in the queue) · closed (archived)" — nothing was read, so nothing is archived; H4 "a failed read is BROKEN".
        git(self.main, "merge", "-q", "--no-ff", "--no-edit", f"feat/{SLUG}")
        s = self.state(GH_MODE="fail")
        self.assertNotEqual(s["state"], "closed", f"the queue was never read, the row is not archived: {s}")


class RowLetteredId(_RowBase):
    def setUp(self):
        super().setUp(row="3a")

    def test_a_lettered_row_id_finds_its_own_folder(self):
        # reef-queue reads an Id as `\d+[a-z]?` (reef-queue.py:126/143, stress M5). reef-row's find_folder reads `Row:` as `\d+`,
        # so row 3a's SPEC reads as row 3: `state 3a` says "plan, ready, no feature folder" for a row that is built and reviewed.
        s = self.state("3a", GH_PRS='[{"number": 7, "state": "OPEN"}]')
        self.assertEqual((s["slug"], s["state"]), (SLUG, "merge"), s)

    def test_row_3_is_not_row_3a(self):
        # contract silent: `state 3` must not resolve to row 3a's folder (there is no row 3)
        s = self.state("3", GH_PRS='[{"number": 7, "state": "OPEN"}]')
        self.assertNotEqual(s["slug"], SLUG, s)


class Record(_Forge):
    """reef-record on a repo with two feature branches (two rows), each with a PR on the fake forge."""

    def setUp(self):
        super().setUp()
        self.main = os.path.join(self.tmp, "repo")
        os.makedirs(self.main)
        git(self.main, "init", "-q", "-b", "main")
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            git(self.main, "config", k, v)
        git(self.main, "remote", "add", "origin", "https://github.com/o/r.git")
        write(self.main, ".reef/config.json", json.dumps({"gates": {"full": "true"}, "merge": {"by": "loop"}, "branches": {"base": "main", "release": "release"}}))
        write(self.main, ".gitignore", ".reef/review/\n.reef/ci-local/\n")
        write(self.main, "app.py", "x = 1\n")
        git(self.main, "add", "-A"); git(self.main, "commit", "-qm", "base")
        for br, val in (("feat/alpha", "2"), ("feat/beta", "3")):
            git(self.main, "checkout", "-qb", br, "main")
            write(self.main, "app.py", f"x = {val}\n")
            git(self.main, "commit", "-qam", br)
        git(self.main, "checkout", "-q", "main")
        self.alpha, self.beta = out(self.main, "rev-parse", "feat/alpha"), out(self.main, "rev-parse", "feat/beta")
        self.rec_env = dict(GH_BRANCH_8="feat/alpha", GH_BRANCH_9="feat/beta")

    def report(self, name, head, feature, verdict="GREEN"):
        p = os.path.join(self.tmp, name)
        with open(p, "w") as f:
            f.write(f"HEAD: {head[:12]}\nRUN: agent=acceptance feature={feature}\n- AC-1: test_it_works PASS\nVERDICT: {verdict}\n")
        return p

    def record(self, *args, **env):
        e = self.env(**self.rec_env)
        e.update(env)
        return subprocess.run([sys.executable, RECORD, *args, "--root", self.main], capture_output=True, text=True, env=e, timeout=60)

    def rec(self, feature):
        p = os.path.join(self.main, ".reef", "review", f"{feature}.json")
        return json.load(open(p)) if os.path.isfile(p) else None

    def test_coverage_green_binds_the_reviewed_head(self):
        r = self.record("beta", "GREEN", "--pr", "9", "--report", self.report("b.md", self.beta, "beta"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.rec("beta")["sha"], self.beta)

    def test_coverage_a_report_of_the_head_before_a_force_push_is_refused(self):
        old = self.beta
        git(self.main, "checkout", "-q", "feat/beta")
        write(self.main, "app.py", "x = 33\n")
        git(self.main, "commit", "-qa", "--amend", "--no-edit")   # the force-pushed head
        git(self.main, "checkout", "-q", "main")
        r = self.record("beta", "GREEN", "--pr", "9", "--report", self.report("b.md", old, "beta"))
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIsNone(self.rec("beta"))

    def test_coverage_a_crlf_report_records(self):
        p = self.report("b.md", self.beta, "beta")
        txt = open(p).read().replace("\n", "\r\n")
        open(p, "w", newline="").write(txt)
        r = self.record("beta", "GREEN", "--pr", "9", "--report", p)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_coverage_gh_down_leaves_the_existing_record(self):
        self.assertEqual(self.record("beta", "GREEN", "--pr", "9", "--report", self.report("b.md", self.beta, "beta")).returncode, 0)
        before = self.rec("beta")
        r = self.record("beta", "FAIL", "--pr", "9", GH_MODE="fail")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.rec("beta"), before)

    def test_a_green_record_refuses_another_rows_report_and_pr(self):
        # row alpha's reviewer report (RUN feature=alpha, HEAD alpha) and alpha's PR 8, recorded as beta's GREEN (a slip of
        # the orchestrator's --pr while two rows are in flight). Contract: agents/acceptance.md:25 "RUN: agent=acceptance
        # feature=<slug>"; reef-review SKILL:31 the record is `<feature>`'s, bound to the forge's commit. The security path
        # already refuses a report that is not its agent's (reef-record cmd_security); the GREEN path reads neither the
        # report's feature nor the PR's branch, so beta.json now carries alpha's head (and overwrites beta's own record).
        r = self.record("beta", "GREEN", "--pr", "8", "--report", self.report("a.md", self.alpha, "alpha"))
        self.assertNotEqual(r.returncode, 0, f"beta recorded GREEN from alpha's review: {r.stdout}")
        self.assertIsNone(self.rec("beta"))

    def test_a_stale_fail_report_never_overwrites_a_green_at_the_new_head(self):
        # a step re-run after a crash: the review of X failed, the rollup made Y, Y was reviewed GREEN and recorded; the
        # resumed orchestrator then records the OLD fail report. reef-record binds FAIL to the forge head Y without reading
        # the report, so the GREEN at Y is gone and reef-row names a rollup for a head that passed. Contract: reef-review
        # SKILL:31 "a verdict is a RECORD bound to the forge's commit … refuses a report that does not name that head";
        # reef-record's own rule "the record carries the reviewer's verdict, never another".
        old = self.beta
        fail_report = self.report("b-fail.md", old, "beta", verdict="FAIL")
        git(self.main, "checkout", "-q", "feat/beta")
        write(self.main, "app.py", "x = 4\n")
        git(self.main, "commit", "-qam", "the rollup")
        git(self.main, "checkout", "-q", "main")
        self.beta = out(self.main, "rev-parse", "feat/beta")
        self.assertEqual(self.record("beta", "GREEN", "--pr", "9", "--report", self.report("b.md", self.beta, "beta")).returncode, 0)
        r = self.record("beta", "FAIL", "--pr", "9", "--report", fail_report)
        self.assertNotEqual(r.returncode, 0, f"a FAIL of {old[:12]} was bound to {self.beta[:12]}: {r.stdout}")
        self.assertEqual(self.rec("beta")["verdict"], "GREEN")

    def sec_report(self, head, verdict="PASS"):
        p = os.path.join(self.tmp, "sec.md")
        with open(p, "w") as f:
            f.write(f"RUN: agent=security range=release...main head={head[:12]}\nSPINE: reef/architecture/threat-model.md\nVERDICT: {verdict}\n")
        return p

    def test_coverage_a_security_pass_at_the_audited_head_records(self):
        h = out(self.main, "rev-parse", "main")
        r = self.record("security", "PASS", "--report", self.sec_report(h))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.main, ".reef", "review", f"security-{h[:12]}.json")))

    def test_a_security_pass_of_an_older_base_head_is_not_bound_to_the_new_one(self):
        # the security pass audited main at H1 (its report: `RUN: agent=security … head=<H1 sha12>`, agents/security.md
        # Report). Before the record, another row merged (rows_in_flight 2): main is H2. reef-record binds the PASS to H2,
        # and the guard opens the release PR for code no one audited. Contract: agents/security.md "the guard refuses the
        # release PR without a PASS at its head"; reef-record docstring "bound to the head of branches.base".
        audited = out(self.main, "rev-parse", "main")
        git(self.main, "merge", "-q", "--no-ff", "--no-edit", "feat/alpha")
        now = out(self.main, "rev-parse", "main")
        r = self.record("security", "PASS", "--report", self.sec_report(audited))
        self.assertFalse(os.path.isfile(os.path.join(self.main, ".reef", "review", f"security-{now[:12]}.json")),
                         f"a PASS audited at {audited[:12]} was recorded at {now[:12]}: {r.stdout}")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
