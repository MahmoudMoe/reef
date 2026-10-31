"""Workflow v3, phase 5b — the row driver: `reef-graph-run.py row <row>` writes ONE Workflow that runs a fast-path row's open
tasks in order (implement, gate, the close in place), then merge-base + push + PR, the evidence on that head, and the one
review, each in a fresh context; `settle` reads the DISK (the result is a summary) into records and prints the row script's
one guard-checked merge command. The orchestrator makes three calls per row instead of three per task plus the review's own."""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import write, git  # noqa: E402  (the suites' shared fixtures, once)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = ("reef_common.py", "reef-graph-run.py", "reef-graph.py", "reef-loop.py", "reef-queue.py", "reef-plan-check.py", "reef-attempt", "reef-claims.py",
           "reef-adversarial", "reef-snapshot.sh", "reef-gate.sh", "reef-row.py", "reef-evidence.py", "reef-tier.py", "reef-merge-close",
           "reef-record", "reef-cost.py", "reef-handoff", "reef-converge")
FEATURE = "demo-row-one"
TASK = """---
id: {id}
feature: demo-row-one
status: pending
complexity: mech
effort: medium
blocked-by: {blocked}
resources: []
tier: light
verify: gate-only
attempts: 0
dispatches: 0
last_failure_sig: ""
---
# {id} — {title}

## Scope
x

## Acceptance Criteria
- AC-1 (FR-1): it works

## Proof
| AC | Proof |
|---|---|
| AC-1 | `{proof}` |

## Out of scope

## Log
"""
SPEC = ("# demo row one\nRow: 1\n\n## Scope\nOne slice.\n\n## Non-goals\n- none\n\n## Already shipped\nnone\n\n"
        "## Requirements\n- FR-1 [backend]: it works.\n\n## Success criteria\n- SC-1: green.\n\n## Architecture impact\nnone\n")
FAKE_GH = r'''#!/usr/bin/env python3
"""fake gh for the row driver: the PR of the feature branch, as the forge would answer."""
import json, os, re, subprocess, sys
repo, branch = os.environ["GH_REPO"], os.environ.get("GH_HEAD_BRANCH", "feat/demo-row-one")
rev = lambda x: subprocess.run(["git", "-C", repo, "rev-parse", x], capture_output=True, text=True).stdout.strip()
a = sys.argv[1:]
with open(os.path.join(repo, ".fake-gh-calls"), "a") as f:
    f.write(" ".join(a) + "\n")
if a[:2] == ["pr", "view"]:
    print(json.dumps({"headRefOid": rev(branch), "baseRefName": "main", "url": "https://github.com/o/r/pull/7", "number": 7, "state": "OPEN"}))
elif a[:2] == ["pr", "list"]:
    print(json.dumps([{"number": 7, "state": "OPEN"}]))
elif a[:1] == ["api"]:
    m = re.search(r"commits/([0-9a-f]+)/check-runs", a[1])
    if m:
        print(json.dumps({"total_count": 0, "check_runs": []})); sys.exit(0)
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


def task(tid, title, blocked, proof, critical=False):
    t = TASK.format(id=tid, title=title, blocked=blocked, proof=proof)
    if critical:   # a design task touching auth: the critical path, as reef-tier.py and the plan check both read it
        t = (t.replace("complexity: mech", "complexity: design").replace("tier: light", "tier: critical").replace("verify: gate-only", "verify: judge")
              .replace("resources: []\n", "resources: []\ntouches: [auth]\n").replace("## Scope\nx", "## Scope\nx\n\n## Decision\nhuman words"))
    return t


class _Row(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reef-rowdrv.")
        self.main = os.path.join(self.tmp, "main")
        os.makedirs(os.path.join(self.main, "scripts"))
        for n in SCRIPTS:
            shutil.copy(os.path.join(ROOT, "scripts", n), os.path.join(self.main, "scripts", n))
        write(self.main, ".reef/config.json", json.dumps({
            "gates": {"full": "echo '1 passed'"}, "ci": {"feature_gate": "local"}, "merge": {"by": "loop"},
            "branches": {"base": "main", "release": "release"}, "graph": {"mode": "auto"}, "worktree": {"dir": ".reef/worktrees"},
            "paths": {"queue": "reef/queue.md", "features": "reef/features", "runlog": "reef/journal.md"}}))
        write(self.main, ".reef/version", "0.6.0\n")
        write(self.main, ".gitignore", ".reef/worktrees/\n.reef/approvals/\n.reef/review/\n.reef/evidence/\n.reef/ci-local/\n.reef/inflight/\n"
                                       ".reef/graph/\n.reef/loop.json\n.reef/run/\ntasks/.plan-review.json\nreef/features/*/tasks/.plan-review.json\nscripts/__pycache__/\n.fake-gh-calls\n")
        write(self.main, "reef/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n"
                                          "| 1 | first | | planned | 1 | |\n")
        write(self.main, "reef/journal.md", "# Journal\n| Task | Implementer | Verifier | Attempts | Result | ACs | Escaped defects |\n|---|---|---|---|---|---|---|\n")
        write(self.main, "CLAUDE.md", "# brief\n")
        write(self.main, "src/a.py", "a = 1\n")
        write(self.main, f"reef/features/{FEATURE}/SPEC.md", SPEC)
        write(self.main, f"reef/features/{FEATURE}/tasks/101-slice.md", task(101, "the slice", "[]", "test_it_works"))
        write(self.main, f"reef/features/{FEATURE}/tasks/102-second.md", task(102, "the second", "[101]", "test_second_works"))
        git(self.main, "init", "-q", "-b", "main")
        for k, v in (("user.email", "t@t"), ("user.name", "t")):   # the scripts' own commits (CI has no identity: 2026-10-26)
            git(self.main, "config", k, v)
        git(self.main, "add", "-A"); git(self.main, "commit", "-qm", "init")
        git(self.main, "remote", "add", "origin", "https://github.com/o/r.git")   # a forge: the fake gh answers for it
        self.co = os.path.join(self.main, ".reef", "worktrees", FEATURE)
        self.assertEqual(git(self.main, "worktree", "add", "-q", "-b", f"feat/{FEATURE}", self.co, "main").returncode, 0)
        self.approve()
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        with open(os.path.join(self.bin, "gh"), "w") as f:
            f.write(FAKE_GH)
        os.chmod(os.path.join(self.bin, "gh"), 0o755)
        self.env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"], GH_REPO=self.main, REEF_GH_TIMEOUT="5")

    def approve(self):
        pc = os.path.join(self.main, "scripts", "reef-plan-check.py")
        r = subprocess.run([sys.executable, pc, self.main], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = subprocess.run([sys.executable, pc, self.main, "--digest", "--feature", FEATURE], capture_output=True, text=True)
        digest = r.stdout.split()[-1]
        write(self.main, f".reef/approvals/{FEATURE}.json", json.dumps({"digest16": digest[:16], "approved_at": "2026-10-26T00:00:00Z"}))

    def g(self, *args):
        return subprocess.run([sys.executable, os.path.join(self.main, "scripts", "reef-graph-run.py"), *args, "--repo", self.main],
                              capture_output=True, text=True, env=self.env)

    def pass_gate(self):
        self.g("probe")
        with open(os.path.join(self.main, ".reef", "graph", "probe-results.json"), "w") as f:
            json.dump({"denied": True, "output": "reef-guard DENY: writing under .reef/approvals/"}, f)
        r = self.g("probe-check", ".reef/graph/probe-results.json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def row(self):
        r = self.g("row", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.reports = r.stdout.split("reports: ")[1].splitlines()[0].strip()
        return r


class RowDriver(_Row):
    def test_the_row_script_runs_the_tasks_in_order_closes_each_then_the_pr_the_evidence_and_the_one_review(self):
        self.pass_gate()
        r = self.row()
        self.assertIn(f"row: 1 ({FEATURE}) tasks in order: 101, 102 · path: fast", r.stdout)
        scripts = glob.glob(os.path.join(self.main, ".reef", "graph", "row-*.js"))
        self.assertEqual(len(scripts), 1, r.stdout)
        js = open(scripts[0]).read()
        self.assertTrue(js.startswith("export const meta = {"))
        self.assertLess(js.index('"id": "101"'), js.index('"id": "102"'), "tasks in id order")
        self.assertIn("for (const t of TASKS)", js, "one task after another in the row's one worktree, never a parallel pipeline")
        self.assertNotIn("pipeline(TASKS", js)
        self.assertIn("agentType: 'reef:implementer'", js)
        self.assertIn("reef-merge-close", js, "each task is closed in place by the mechanic before the next starts")
        self.assertLess(js.index("label: 'pr'"), js.index("label: 'evidence'"),
                        "merge-base and the push BEFORE the gate: the evidence must be the pushed head's (the review, 2026-10-26)")
        self.assertIn("merged_base", js, "a merge-base conflict stops the row for a person")
        self.assertIn("sh scripts/reef-gate.sh full", js, "the full suite once, on the final head: the evidence the reviewer reads")
        self.assertIn("reef-converge", js, "the Proof rows run before the reviewer")
        self.assertIn("gh pr create", js)
        self.assertIn("agentType: 'reef:acceptance'", js, "the ONE reviewer")
        self.assertIn("VERDICT: GREEN|FAIL", js)
        self.assertIn('"judge": false', js, "no per-task judge on the fast path")
        self.assertNotIn("gh pr merge", js, "the merge is never the workflow's: the orchestrator runs it bare, guard-checked")
        self.assertTrue(self.reports.startswith("/tmp/reef-graph-"), self.reports)
        t101 = open(os.path.join(self.co, "reef", "features", FEATURE, "tasks", "101-slice.md")).read()
        self.assertIn("status: in-progress", t101); self.assertIn("dispatches: 1", t101)
        self.assertTrue(os.path.isfile(os.path.join(self.main, ".reef", "inflight", "101")))
        self.assertTrue(os.path.isfile(os.path.join(self.main, ".reef", "inflight", "102")))
        r = self.g("row", "1")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("in flight: 101, 102", r.stdout, "never a second workflow on the same worktree")

    def test_the_driver_refuses_the_owners_steps_the_critical_path_and_an_unknown_row(self):
        self.pass_gate()
        os.unlink(os.path.join(self.main, ".reef", "approvals", f"{FEATURE}.json"))
        r = self.g("row", "1")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("approval", r.stdout); self.assertIn("/reef-plan 1", r.stdout)
        self.assertFalse(glob.glob(os.path.join(self.main, ".reef", "graph", "row-*.js")))
        self.assertEqual(self.g("row", "9").returncode, 2)
        for d in (self.main, self.co):
            write(d, f"reef/features/{FEATURE}/tasks/101-slice.md", task(101, "the slice", "[]", "test_it_works", critical=True))
        self.approve()
        r = self.g("row", "1")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("path: critical", r.stdout); self.assertIn("fast path only", r.stdout); self.assertIn("/reef-review", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.main, ".reef", "inflight", "101")), "nothing dispatched for a refused row")
        shutil.rmtree(os.path.join(self.main, ".reef", "graph"))
        r = self.g("row", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("graph mode is OFF", r.stderr)


class RowSettle(_Row):
    """What the mechanic did inside the workflow is on disk; settle reads the disk and the result, never the result alone."""

    def close(self, name, journal):
        r = subprocess.run([sys.executable, os.path.join(self.co, "scripts", "reef-merge-close"), f"reef/features/{FEATURE}/tasks/{name}",
                            "--subject", f"feat: {name[:-3]}", "--journal", journal, "--repo", self.co], capture_output=True, text=True, cwd=self.co)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def result(self, tasks, head, verdict="GREEN", stopped=None, report=None, feature=FEATURE, worktree=None):
        rep = report if report is not None else write(self.reports, f"review-{FEATURE}.md", f"HEAD: {head[:12]}\nRUN: agent=acceptance feature={FEATURE}\n- FR-1 PASS test_it_works\nVERDICT: {verdict}\n")
        done = not stopped
        res = {"row": "1", "feature": feature, "worktree": worktree or self.co, "report_dir": self.reports, "tasks": tasks, "stopped": stopped,
               "pr": {"merged_base": True, "number": 7, "head": head, "output": "https://github.com/o/r/pull/7"} if done else None,
               "evidence": {"gate_exit": 0, "converge_exit": 0, "evidence_exit": 0, "evidence": "evidence: local green", "notes": ""} if done else None,
               "review": {"verdict": verdict, "report_path": rep, "summary": "fine"} if done else None}
        return write(self.tmp, "row-results.json", json.dumps({"result": res}))

    def task_result(self, tid, closed=True):
        return {"task": tid, "worktree": self.co, "task_file": os.path.join(self.co, "reef", "features", FEATURE, "tasks", f"{tid}-{'slice' if tid == '101' else 'second'}.md"),
                "judge": False, "hunter": False, "gate": {"gate_exit": 0, "handback_check": "ok (3 claims)", "snapshot": "s"}, "judges": [],
                "snapshot_after": "s", "close": {"closed": closed, "output": "closed" if closed else "merge-close: refusing"}}

    def build(self, close_102=True):
        self.pass_gate()
        self.row()
        journal = write(self.tmp, "journal.md", "| 101 | opus | - | 0 | gate green | AC-1 | - |\n")
        write(self.co, "src/a.py", "a = 2\n")
        write(self.co, "tests/test_a.py", "def test_it_works(): pass\ndef test_second_works(): pass\n")   # the named proofs exist
        self.close("101-slice.md", journal)
        if close_102:
            self.close("102-second.md", journal)
        r = subprocess.run(["sh", "scripts/reef-gate.sh", "full"], cwd=self.co, capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return git(self.co, "rev-parse", "HEAD").stdout.strip()

    def test_a_green_row_is_recorded_and_the_merge_is_named_never_run(self):
        head = self.build()
        r = self.g("settle", self.result([self.task_result("101"), self.task_result("102")], head))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rec = json.load(open(os.path.join(self.main, ".reef", "review", f"{FEATURE}.json")))
        self.assertEqual((rec["verdict"], rec["sha"]), ("GREEN", head), "the GREEN record binds to the forge head, written by reef-record")
        self.assertIn("ROW 1 READY TO MERGE (PR #7", r.stdout)
        self.assertIn("\n  gh pr merge 7 --squash --delete-branch\n", r.stdout, "the row script's own line, bare, on its own line")
        self.assertNotIn("pr merge", open(os.path.join(self.main, ".fake-gh-calls")).read(), "settle never merges: a script's gh call is invisible to the guard")
        self.assertTrue(glob.glob(os.path.join(self.co, ".reef", "ci-local", f"review-{FEATURE}-*.md")), "the reviewer's report, copied")
        self.assertFalse(os.path.exists(os.path.join(self.main, ".reef", "inflight", "101")))
        self.assertFalse(os.path.exists(os.path.join(self.main, ".reef", "inflight", "102")))

    def test_a_fail_review_is_recorded_and_the_row_waits_on_the_rollup(self):
        head = self.build()
        r = self.g("settle", self.result([self.task_result("101"), self.task_result("102")], head, verdict="FAIL"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("ROW 1 WAITS review: FAIL", r.stdout)
        self.assertNotIn("READY TO MERGE", r.stdout)
        self.assertEqual(json.load(open(os.path.join(self.main, ".reef", "review", f"{FEATURE}.json")))["verdict"], "FAIL")

    def test_the_verdict_is_the_report_files_not_the_results(self):
        head = self.build()
        rep = write(self.reports, f"review-{FEATURE}.md", f"HEAD: {head[:12]}\nVERDICT: FAIL\n")
        r = self.g("settle", self.result([self.task_result("101"), self.task_result("102")], head, verdict="GREEN", report=rep))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("WAITS review: FAIL", r.stdout)
        outside = write(self.tmp, "elsewhere.md", f"HEAD: {head[:12]}\nVERDICT: GREEN\n")
        r = self.g("settle", self.result([self.task_result("101"), self.task_result("102")], head, report=outside))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("scratch dir", r.stdout, "only a report the run's agents wrote under the run's scratch dir is copied as a record")

    def test_a_task_the_mechanic_did_not_close_fails_with_an_attempt_and_the_row_waits_on_build(self):
        head = self.build(close_102=False)
        r = self.g("settle", self.result([self.task_result("101"), self.task_result("102", closed=False)], head, stopped="task 102"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("FAIL 102: not closed", r.stdout)
        self.assertIn("attempt counted: attempt=2/", r.stdout, "one attempt consumed; the line names the next")
        self.assertIn("ROW 1 WAITS build", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.main, ".reef", "review", f"{FEATURE}.json")))
        self.assertIn("attempts: 1", open(os.path.join(self.co, "reef", "features", FEATURE, "tasks", "102-second.md")).read())

    def test_a_task_the_workflow_never_reached_is_freed_and_the_open_task_on_disk_holds_the_row(self):
        head = self.build(close_102=False)
        r = self.g("settle", self.result([self.task_result("101")], head))   # the result forgets 102; the disk does not
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("CLOSED 101", r.stdout)
        self.assertIn("open task(s) on disk: 102", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.main, ".reef", "inflight", "102")), "a task the sequential row never started is not in flight")
        self.assertFalse(os.path.exists(os.path.join(self.main, ".reef", "review", f"{FEATURE}.json")))

    def test_a_closed_claim_needs_the_close_commit_not_a_moved_file(self):
        head = self.build(close_102=False)
        tdir = os.path.join(self.co, "reef", "features", FEATURE, "tasks")
        os.makedirs(os.path.join(tdir, "done"), exist_ok=True)
        text = open(os.path.join(tdir, "102-second.md")).read().replace("status: in-progress", "status: done")
        os.unlink(os.path.join(tdir, "102-second.md"))
        write(tdir, "done/102-second.md", text)   # moved by hand, nothing committed
        r = self.g("settle", self.result([self.task_result("101"), self.task_result("102")], head))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("FAIL 102: not closed on disk: no commit with `Closes-task: 102-", r.stdout)

    def test_the_result_names_the_rows_own_feature_and_worktree(self):
        head = self.build()
        r = self.g("settle", self.result([self.task_result("101"), self.task_result("102")], head, feature="other-row"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("the disk says", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.main, ".reef", "review", f"{FEATURE}.json")))


if __name__ == "__main__":
    unittest.main()
