"""Stress: the tick's `next:` line at every stage of ONE row's life — queued, planned, approved, dispatched, handed back,
failed, fixed, passed, closed on the feature branch, PR open, PR merged, row closed — on the fast path (chat and graph
mode) and the critical path; two rows at the rows_in_flight cap; a row whose dependency is still building; and the Stop
hook at each stage while the loop is active.

The state is built with the real scripts (reef-plan-check, reef-record, reef-adversarial, reef-graph worktree,
reef-attempt, reef-merge-close, reef-loop); only the agents' files (hand-back, report) and gh are faked."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import write, git, ROOT  # noqa: E402

LOOP = os.path.join(ROOT, "scripts", "reef-loop.py")
GUARD = os.path.join(ROOT, "scripts", "reef-guard.py")
SCRIPTS = ("reef_common.py", "reef-loop.py", "reef-queue.py", "reef-graph.py", "reef-cost.py", "reef-handoff", "reef-plan-check.py",
           "reef-attempt", "reef-merge-close", "reef-record", "reef-adversarial", "reef-claims.py", "reef-tier.py", "reef-row.py")
SLUG = "demo-row-one"
SPEC = ("# demo row one\nRow: {row}\n\n## Scope\nOne slice.\n\n## Non-goals\n- none\n\n## Already shipped\nnone\n\n"
        "## Requirements\n- FR-1 [backend]: it works.\n\n## Success criteria\n- SC-1: green.\n\n## Architecture impact\nnone\n")
TASK = """---
id: {id}
feature: {slug}
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
# {id} — the slice

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
QUEUE_HEAD = "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n"


def task_text(tid, slug, critical=False):
    t = TASK.format(id=tid, slug=slug)
    if critical:   # as tests/test_row_driver.py builds a critical task: design, auth touched, judged
        t = (t.replace("complexity: mech", "complexity: design").replace("tier: light", "tier: critical").replace("verify: gate-only", "verify: judge")
              .replace("resources: []\n", "resources: []\ntouches: [auth]\n").replace("## Scope\nx", "## Scope\nx\n\n## Decision\nhuman words"))
    return t


def fake_gh(bindir, prs, rc=0):
    """gh on PATH: `pr list` answers `prs` (exit `rc`)."""
    os.makedirs(bindir, exist_ok=True)
    p = os.path.join(bindir, "gh")
    with open(p, "w") as f:
        f.write("#!/bin/sh\nif [ \"$1\" = pr ] && [ \"$2\" = list ]; then\nprintf '%s' '" + json.dumps(prs) + f"'\nexit {rc}\nfi\nexit 1\n")
    os.chmod(p, 0o755)


class Project:
    """A main checkout on main with the queue; feature worktrees under .reef/worktrees/<slug> on feat/<slug>."""

    def __init__(self, rows=((1, "first", ""),), cfg_extra=None):
        self.tmp = tempfile.mkdtemp(prefix="reef-life.")
        self.main = os.path.join(self.tmp, "main")
        os.makedirs(os.path.join(self.main, "scripts"))
        for n in SCRIPTS:
            shutil.copy(os.path.join(ROOT, "scripts", n), os.path.join(self.main, "scripts", n))
        cfg = {"gates": {"full": "true"}, "branches": {"base": "main", "feature_prefix": "feat/"}, "worktree": {"dir": ".reef/worktrees"},
               "paths": {"queue": "reef/queue.md", "features": "reef/features", "runlog": "reef/journal.md"}}
        cfg.update(cfg_extra or {})
        write(self.main, ".reef/config.json", json.dumps(cfg))
        write(self.main, ".reef/version", "0.6.0\n")
        write(self.main, ".gitignore", ".reef/worktrees/\n.reef/approvals/\n.reef/review/\n.reef/evidence/\n.reef/ci-local/\n.reef/inflight/\n"
                                       ".reef/verifying/\n.reef/graph/\n.reef/loop.json\n.reef/status.html\n.reef/run/\n.reef/cost/\n"
                                       "tasks/.plan-review.json\nreef/features/*/tasks/.plan-review.json\nscripts/__pycache__/\n.reef/hunt/\n")
        write(self.main, "reef/queue.md", QUEUE_HEAD + "".join(f"| {i} | {item} | {dep} | planned | 1 | |\n" for i, item, dep in rows))
        write(self.main, "reef/journal.md", "# Journal\n| Task | Implementer | Verifier | Attempts | Result | ACs | Escaped defects |\n|---|---|---|---|---|---|---|\n")
        write(self.main, "CLAUDE.md", "# brief\n")
        write(self.main, "HANDOFF.md", "# Handoff\n")
        write(self.main, "src/a.py", "a = 1\n")
        git(self.main, "init", "-q", "-b", "main")
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            git(self.main, "config", k, v)
        git(self.main, "add", "-A"); git(self.main, "commit", "-qm", "init")
        self.bin = os.path.join(self.tmp, "bin")
        fake_gh(self.bin, [])
        self.wts = {}

    # ---- the world, through the real scripts ----
    def env(self):
        e = {k: v for k, v in os.environ.items() if k not in ("REEF_RUNNER", "REEF_TRANSCRIPT", "CLAUDE_PLUGIN_ROOT")}
        e["PATH"] = self.bin + os.pathsep + os.environ["PATH"]
        return e

    def tick(self, *a):
        return subprocess.run([sys.executable, LOOP, "tick", *a, "--repo", self.main], capture_output=True, text=True, env=self.env())

    def state(self):
        r = self.tick("--json")
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)

    def next_line(self):
        out = self.tick().stdout
        return next((l[len("next: "):] for l in out.splitlines() if l.startswith("next: ")), "<no next line>\n" + out)

    def loop_cmd(self, *a):
        return subprocess.run([sys.executable, LOOP, *a, "--repo", self.main], capture_output=True, text=True, env=self.env())

    def stop_hook(self):
        payload = {"hook_event_name": "Stop", "cwd": self.main, "stop_hook_active": False,
                   "last_assistant_message": "in flight: - / waiting on: - / next: /reef-loop", "background_tasks": [], "session_crons": []}
        return subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True, env=self.env())

    def fresh_stop_hook(self):
        """The Stop hook as a NEW turn sees it: the refused-once memory cleared, so the verdict is the state's, not the history's."""
        p = os.path.join(self.main, ".reef", "loop.json")
        st = json.load(open(p)) if os.path.isfile(p) else {}
        st.update(refused=None, status_refused=None, hashes=[], parked=None)
        write(self.main, ".reef/loop.json", json.dumps(st))
        return self.stop_hook().returncode

    def plan(self, row, slug=SLUG, tids=(101,), critical=False, approve=True):
        """/reef-plan: the feature worktree, the planner's files there, the machine review, the owner's approval."""
        wt = os.path.join(self.main, ".reef", "worktrees", slug)
        if not os.path.isdir(wt):
            assert git(self.main, "worktree", "add", "-q", "-b", f"feat/{slug}", wt, "main").returncode == 0
        self.wts[slug] = wt
        write(wt, f"reef/features/{slug}/SPEC.md", SPEC.format(row=row))
        for tid in tids:
            write(wt, f"reef/features/{slug}/tasks/{tid}-slice.md", task_text(tid, slug, critical))
        pc = os.path.join(self.main, "scripts", "reef-plan-check.py")
        r = subprocess.run([sys.executable, pc, wt], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        if critical:
            r = subprocess.run([sys.executable, os.path.join(self.main, "scripts", "reef-record"), "plan-review", slug, "PASS", "--root", wt],
                               capture_output=True, text=True)
            assert r.returncode == 0, r.stdout + r.stderr
            for tid in tids:
                hunt = write(self.tmp, f"hunt-{tid}.md", f"RUN: agent=loophole-hunter task={tid} pass=plan round=1\nBLOCKER: none\nVERDICT: PASS\n")
                r = subprocess.run([sys.executable, os.path.join(self.main, "scripts", "reef-adversarial"),
                                    os.path.join(wt, f"reef/features/{slug}/tasks/{tid}-slice.md"), "plan", hunt], capture_output=True, text=True)
                assert r.returncode == 0, r.stdout + r.stderr
        git(wt, "add", "-A"); git(wt, "commit", "-qm", f"plan {slug}")
        if approve:
            self.approve(slug)
        return wt

    def approve(self, slug=SLUG):
        wt = self.wts[slug]
        pc = os.path.join(self.main, "scripts", "reef-plan-check.py")
        r = subprocess.run([sys.executable, pc, wt, "--digest", "--feature", slug], capture_output=True, text=True)
        digest = r.stdout.split()[-1]
        # reef-plan-check.py:33 — "The approvals live in the MAIN checkout's .reef/, never a worktree's."
        write(self.main, f".reef/approvals/{slug}.json", json.dumps({"digest16": digest[:16], "approved_at": "2026-11-01T00:00:00Z"}))

    def task_path(self, tid=101, slug=SLUG, where=None):
        return os.path.join(where or self.wts[slug], f"reef/features/{slug}/tasks/{tid}-slice.md")

    def task_worktree(self, tid=101, slug=SLUG):
        """reef-graph.py worktree: the critical path's task worktree (task/<id>-<slug>) under the MAIN checkout's .reef/worktrees."""
        r = subprocess.run([sys.executable, os.path.join(self.main, "scripts", "reef-graph.py"), "worktree", self.task_path(tid, slug)],
                           capture_output=True, text=True, cwd=self.wts[slug])
        assert r.returncode == 0, r.stdout + r.stderr
        wt = next(l.split(": ", 1)[1] for l in r.stdout.splitlines() if l.startswith("worktree: "))
        # the feature branch's single writer commits the recorded `worktree:` key (else the task branch's merge collides)
        git(self.wts[slug], "add", "-A"); git(self.wts[slug], "commit", "-qm", f"worktree {tid}")
        git(wt, "merge", "-q", "--ff-only", f"feat/{slug}")
        return wt

    def dispatch(self, tid, home):
        """What the guard writes on an allowed implementer dispatch (reef-guard.py:1668): status in-progress, dispatches +1,
        the in-flight marker in the task's root."""
        p = self.task_path(tid, where=home)
        t = open(p).read()
        n = int(t.split("dispatches: ", 1)[1].split("\n", 1)[0]) + 1
        t = t.replace("status: pending", "status: in-progress").replace(f"dispatches: {n - 1}\n", f"dispatches: {n}\n")
        write(home, os.path.relpath(p, home), t)
        write(home, f".reef/inflight/{tid}", json.dumps({"id": tid, "task": p, "pid": os.getpid()}))

    def hand_back(self, tid, home, text="claims"):
        """The implementer's hand-back; /reef-task removes the marker after it (reef-task SKILL step 2)."""
        time.sleep(1.1)   # FAIL lines carry whole seconds: a hand-back must be strictly after the failure it fixes
        write(home, "src/a.py", f"a = {time.time()}\n")
        write(home, f".reef/ci-local/handback-{tid}.md", f"RUN: agent=implementer task={tid}\n{text}\n")
        try:
            os.unlink(os.path.join(home, ".reef", "inflight", str(tid)))
        except FileNotFoundError:
            pass

    def fail(self, tid, home, text="gate exit 1: FAIL test_it_works"):
        time.sleep(1.1)
        r = subprocess.run([os.path.join(self.main, "scripts", "reef-attempt"), self.task_path(tid, where=home), text],
                           capture_output=True, text=True, cwd=home)
        assert r.returncode == 0, r.stdout + r.stderr
        return r

    def report(self, tid, home, verdict="PASS"):
        time.sleep(1.1)
        write(home, f".reef/ci-local/report-{tid}.md", f"RUN: agent=verifier task={tid}\nVERDICT: {verdict}\n")

    def merge_close(self, tid, slug=SLUG):
        j = write(self.tmp, f"journal-{tid}.md", f"| {tid} | opus | sonnet | 1 | PASS | AC-1 achieved | - |\n")
        r = subprocess.run([sys.executable, os.path.join(self.main, "scripts", "reef-merge-close"), f"reef/features/{slug}/tasks/{tid}-slice.md",
                            "--subject", "feat: the slice", "--journal", j, "--repo", self.wts[slug]],
                           capture_output=True, text=True, cwd=self.wts[slug], env=self.env())
        assert r.returncode == 0, r.stdout + r.stderr
        return r

    def pr_open(self, number, slug=SLUG):
        fake_gh(self.bin, [{"number": number, "headRefName": f"feat/{slug}", "title": slug, "reviewDecision": ""}])

    def pr_merged(self, slug=SLUG, remove_worktree=True):
        """The PR merges into main (`gh pr merge --delete-branch`): the forge lists it no more; the base has the feature."""
        fake_gh(self.bin, [])
        assert git(self.main, "merge", "-q", "--no-ff", "-m", f"Merge feat/{slug}", f"feat/{slug}").returncode == 0
        if remove_worktree:
            git(self.main, "worktree", "remove", "--force", self.wts[slug])
            git(self.main, "branch", "-D", f"feat/{slug}")

    def close_row(self, row):
        """SKILL reef-loop §2.4: the row to the archive (file mode: queue-archive.md), the journal, the worktrees removed."""
        q = open(os.path.join(self.main, "reef/queue.md")).read()
        line = next(l for l in q.splitlines() if l.startswith(f"| {row} |"))
        write(self.main, "reef/queue.md", q.replace(line + "\n", ""))
        ap = os.path.join(self.main, "reef/queue-archive.md")
        a = open(ap).read() if os.path.isfile(ap) else "# Archive\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n"
        write(self.main, "reef/queue-archive.md", a + line + "\n")
        r = subprocess.run([sys.executable, os.path.join(self.main, "scripts", "reef-queue.py"), "journal", SLUG, "--repo", self.main],
                           capture_output=True, text=True, env=self.env())
        git(self.main, "add", "-A"); git(self.main, "commit", "-qm", f"close row {row}")
        return r

    def graph_gate(self):
        write(self.main, ".reef/graph/gate.json", json.dumps({"ok": True, "denied": True, "file_existed": False}))


class FastPathLifecycle(unittest.TestCase):
    """One fast-path row (tier light, verify: gate-only) from queued to closed. The order of `next:` is
    scripts/reef-loop.py render_status_page (lines 438-444): verify, dispatch, review, close, plan, awaiting, nothing."""

    def drive(self, graph):
        p = Project()
        if graph:
            p.graph_gate()
        disp = "dispatch (graph): 101 — python3 scripts/reef-graph-run.py generate" if graph else \
               "dispatch (chat): 101 — /reef-task (no GATE OK — reef-graph-run.py probe)"
        verify = "verify (graph): 101 — python3 scripts/reef-graph-run.py generate" if graph else "verify: 101"

        # queued: SKILL reef-loop §1 — the ready row is planned
        self.assertEqual(p.next_line(), "plan: 1")
        # planned, not approved: the row is no longer to plan (reef-loop.py:242-244, planned_elsewhere); the gate is the owner's
        wt = p.plan(1, approve=False)
        st = p.state()
        self.assertEqual(st["rows_to_plan"], [], st)
        self.assertEqual(st["building"], ["1"])
        self.assertRegex(p.next_line(), r"^awaiting: demo-row-one \(approval \(the gate: the machines passed\)\) — python3 scripts/reef-approval\.py --owner \"Approve plan demo-row-one at [0-9a-f]{16}\?\"$")
        # approved: dispatch, in the mode the main checkout's gate says (reef-loop.py:62-69)
        p.approve()
        self.assertEqual(p.next_line(), disp)
        # dispatched: in flight, nothing to dispatch again (reef-loop.py:214-216)
        p.dispatch(101, wt)
        st = p.state()
        self.assertEqual(st["in_flight"], ["101"])
        self.assertEqual(st["dispatch_now"], [])
        self.assertEqual(p.next_line(), "nothing ready — stop or wait")
        # handed back: verify, no implementer (reef-loop.py:270-272)
        p.hand_back(101, wt)
        self.assertEqual(p.next_line(), verify)
        # the gate red: reef-attempt records the FAIL; the next step is the implementer again (reef-loop.py:273-276)
        p.fail(101, wt)
        st = p.state()
        self.assertEqual(st["verify_now"], [])
        self.assertEqual(st["dispatch_now"], ["101"])
        self.assertEqual(st["counters"]["101"], "1/1")
        self.assertEqual(p.next_line(), disp.replace(" (no GATE OK — reef-graph-run.py probe)", " (no GATE OK — reef-graph-run.py probe)"))
        # the fix round, handed back: verify again (a FAIL older than the hand-back does not flip it)
        p.dispatch(101, wt)
        p.hand_back(101, wt, "round 2")
        self.assertEqual(p.next_line(), verify)
        # the gate green: reef-task step 4, the close in place
        p.merge_close(101)
        self.assertIn("status: done", open(p.task_path(101, where=wt).replace("/tasks/", "/tasks/done/")).read())
        return p

    def test_fast_path_chat_mode_to_the_last_task_closed(self):
        self.drive(graph=False)

    def test_fast_path_graph_mode_to_the_last_task_closed(self):
        self.drive(graph=True)

    def test_every_task_done_on_the_feature_branch_with_no_pr_names_the_review(self):
        # The open bug of the brief: every task of row 1 is `done` on feat/demo-row-one, no PR yet. SKILL reef-loop §2.3:
        # after the build comes `/reef-review <feature>` (push, PR, the ONE review). An owner expects the tick to say so.
        # reef-row.py:6-7 names the state: "evidence (no green result for the feature head) · review".
        p = self.drive(graph=False)
        st = p.state()
        self.assertIn("1", st["building"], st)
        nxt = p.next_line()
        self.assertNotEqual(nxt, "nothing ready — stop or wait", "a row whose tasks are all done awaits its review, not nothing")
        self.assertIn("review", nxt)
        ss = p.tick("--session-start").stdout
        self.assertIn("next command: /reef-loop", ss, "the session-start text must not send a fresh session to /reef-plan")

    def test_pr_open_then_merged_then_closed(self):
        p = self.drive(graph=False)
        # PR open: review: #7 (reef-loop.py:441)
        p.pr_open(7)
        self.assertEqual(p.next_line(), "review: #7 feat/demo-row-one")
        # merged into main, worktree and branch removed by --delete-branch / the close: the row is done in main -> close
        p.pr_merged()
        st = p.state()
        self.assertEqual(st["rows_to_close"], ["1"], st)
        self.assertEqual(st["building"], [], "a merged row is not building")
        self.assertEqual(p.next_line(), "close: 1")
        # closed: archived, nothing left
        p.close_row(1)
        st = p.state()
        self.assertEqual((st["rows_to_close"], st["building"], st["rows_in_flight"], st["dispatch_now"], st["verify_now"]), ([], [], [], [], []), st)
        self.assertEqual(p.next_line(), "nothing ready — stop or wait")

    def test_pr_merged_but_the_feature_worktree_not_yet_removed_is_to_close_not_building(self):
        # contract silent: SKILL reef-loop §2.4 removes the worktrees AT the close, so between the merge and the close the
        # feature worktree still stands on feat/<slug>. The row is done in the base: an owner expects `close: 1` and the
        # row no longer counted as building.
        p = self.drive(graph=False)
        p.pr_merged(remove_worktree=False)
        st = p.state()
        self.assertEqual(st["rows_to_close"], ["1"], st)
        self.assertEqual(p.next_line(), "close: 1")
        self.assertNotIn("1", st["building"], "a row merged into the base is not building (its worktree only awaits the close)")

    def test_pr_open_while_gh_fails_is_named_not_nothing(self):
        # contract silent: an external tool failing. The PR is open but `gh pr list` exits 1 (auth expired, rate limit,
        # network). reef-loop.py:229-234 drops the error and the tick says "nothing ready" — the owner is told to stop
        # with a PR waiting. An owner expects the failure named (a BROKEN line), never a quiet "nothing ready".
        p = self.drive(graph=False)
        fake_gh(p.bin, [{"number": 7, "headRefName": "feat/demo-row-one"}], rc=1)
        out = p.tick().stdout
        self.assertNotIn("next: nothing ready", out, out)
        self.assertIn("BROKEN", out, "gh pr list failed: the tick cannot see the loop's PRs and must say so")


class CriticalPathLifecycle(unittest.TestCase):
    """One critical-path row: a task worktree per task, the judge's report, reef-merge-close from the feature worktree."""

    def drive_to_pass(self):
        p = Project()
        wt = p.plan(1, critical=True)
        self.assertEqual(p.next_line(), "dispatch (chat): 101 — /reef-task (no GATE OK — reef-graph-run.py probe)")
        tw = p.task_worktree(101)
        self.assertTrue(tw.endswith(os.path.join(".reef", "worktrees", "101")), tw)
        p.dispatch(101, tw)
        st = p.state()
        self.assertEqual(st["in_flight"], ["101"], st)
        self.assertEqual(st["dispatch_now"], [])
        p.hand_back(101, tw)
        self.assertEqual(p.next_line(), "verify: 101")
        # the verifier's FAIL, recorded in the task worktree's copy (PR 295's seam): back to the implementer
        p.report(101, tw, "FAIL")
        p.fail(101, tw, "AC-1 not achieved: test_it_works asserts nothing")
        st = p.state()
        self.assertEqual(st["verify_now"], [], st)
        self.assertEqual(st["dispatch_now"], ["101"], st)
        # the fix round, handed back: verify (the round-2 hand-back is newer than round 1's report and FAIL)
        p.dispatch(101, tw)
        p.hand_back(101, tw, "round 2")
        self.assertEqual(p.next_line(), "verify: 101")
        p.report(101, tw, "PASS")
        return p, wt, tw

    def test_critical_path_to_pass(self):
        self.drive_to_pass()

    def test_a_pass_not_yet_merged_is_not_dispatched_again(self):
        # The verifier's PASS report is on disk (newer than the hand-back) and the session ends before reef-merge-close
        # (a /clear at the ceiling, a crash). SKILL reef-loop "Re-entry": "Continue every row from its furthest completed
        # step"; SKILL reef-task §4 "Merge (on PASS only)". The furthest step is the PASS: the next is the merge-close,
        # never a fresh implementer. reef-loop.py:296 drops the task from verify_now when a report is newer than the
        # hand-back, and the task falls back to `dispatch now` — /reef-task would dispatch a second implementer on
        # passed work (and spend a dispatch against the cap).
        p, wt, tw = self.drive_to_pass()
        st = p.state()
        self.assertNotIn("101", st["dispatch_now"], f"a PASSED task is to merge-close, not to dispatch: next: {p.next_line()}")

    def test_merge_close_then_pr_then_merge_then_close(self):
        p, wt, tw = self.drive_to_pass()
        p.merge_close(101)
        self.assertFalse(os.path.isdir(tw), "merge-close removes the task worktree")
        self.assertIn("status: done", open(os.path.join(wt, f"reef/features/{SLUG}/tasks/done/101-slice.md")).read())
        st = p.state()
        self.assertEqual((st["dispatch_now"], st["verify_now"], st["in_flight"]), ([], [], []), st)
        p.pr_open(9)
        self.assertEqual(p.next_line(), "review: #9 feat/demo-row-one")
        p.pr_merged()
        self.assertEqual(p.next_line(), "close: 1")
        p.close_row(1)
        self.assertEqual(p.next_line(), "nothing ready — stop or wait")


class CrashedMarkers(unittest.TestCase):
    """A step that crashed half-way: the in-flight marker outlives its moment."""

    def test_a_hand_back_whose_marker_was_not_removed_is_to_verify(self):
        # reef-task SKILL step 2: the guard writes .reef/inflight/<id> at dispatch; the orchestrator must `rm` it after the
        # hand-back. A session that dies between the agent's return and the `rm` leaves both on disk. The hand-back is
        # NEWER than the marker: the work came back. contract silent on the tick — an owner expects `verify: 101`, not
        # "in flight: 101 · next: nothing ready" for loop.inflight_stale_minutes (90 min), during which the Stop hook
        # lets every turn end (in flight) and nothing moves.
        p = Project()
        wt = p.plan(1)
        p.dispatch(101, wt)
        time.sleep(1.1)
        write(wt, ".reef/ci-local/handback-101.md", "RUN: agent=implementer task=101\nclaims\n")   # marker NOT removed
        st = p.state()
        self.assertEqual(st["verify_now"], ["101"], f"the hand-back is newer than the in-flight marker: next: {p.next_line()}")

    def test_a_done_task_is_never_in_flight(self):
        # contract silent: the marker survived the close (graph mode wrote it in the MAIN checkout's .reef/inflight, see
        # tests/test_row_driver.py; the session died before removing it). After reef-merge-close the task is `done` on the
        # feature branch; an owner expects it neither in flight nor returned-unmerged.
        p = Project()
        wt = p.plan(1)
        p.dispatch(101, wt)
        write(p.main, ".reef/inflight/101", json.dumps({"id": 101}))   # the graph's copy of the marker, in main
        p.hand_back(101, wt)
        p.merge_close(101)
        st = p.state()
        self.assertEqual(st["in_flight"], [], f"101 is done on feat/{SLUG}: {st}")


class TwoRowsAtTheCap(unittest.TestCase):
    """SKILL reef-loop §1: "the tick plans a new row only while fewer than loop.rows_in_flight (default 2) are between plan
    and close"; reef-loop.py:364-371."""

    def test_two_rows_building_in_worktrees_hold_the_third(self):
        p = Project(rows=((1, "first", ""), (2, "second", ""), (3, "third", "")))
        self.assertEqual(p.state()["rows_to_plan"], ["1", "2"], "room for two")
        p.plan(1, slug="row-one-thing", tids=(101,))
        p.plan(2, slug="row-two-thing", tids=(201,))
        st = p.state()
        self.assertEqual(st["rows_in_flight"], ["1", "2"], st)
        self.assertEqual(st["rows_to_plan"], [])
        self.assertEqual(st["rows_held"], ["3"])
        self.assertEqual(sorted(st["dispatch_now"]), ["101", "201"], "both rows' first tasks dispatch at once")
        self.assertIn("rows to plan: - (held by loop.rows_in_flight 2: 3; in flight: 1, 2)", p.tick().stdout)

    def test_a_row_done_on_its_branch_with_no_pr_still_counts_against_the_cap(self):
        p = Project(rows=((1, "first", ""), (2, "second", ""), (3, "third", "")))
        p.plan(1, slug="row-one-thing", tids=(101,))
        p.plan(2, slug="row-two-thing", tids=(201,))
        p.merge_close(101, slug="row-one-thing")   # every task of row 1 done on its branch, no PR
        st = p.state()
        self.assertEqual(st["rows_in_flight"], ["1", "2"], st)
        self.assertEqual(st["rows_held"], ["3"], "row 1 is not closed: finish before starting")

    def test_a_merged_row_awaiting_close_counts_and_its_close_frees_the_slot(self):
        p = Project(rows=((1, "first", ""), (2, "second", ""), (3, "third", "")))
        p.plan(1, slug=SLUG, tids=(101,))
        p.plan(2, slug="row-two-thing", tids=(201,))
        p.merge_close(101)
        p.pr_merged()
        st = p.state()
        self.assertEqual(st["rows_to_close"], ["1"], st)
        self.assertEqual(st["rows_in_flight"], ["1", "2"], st)
        self.assertEqual(st["rows_held"], ["3"])
        self.assertEqual(p.next_line(), "dispatch (chat): 201 — /reef-task (no GATE OK — reef-graph-run.py probe)")
        p.close_row(1)
        st = p.state()
        self.assertEqual(st["rows_to_plan"], ["3"], "the close freed a slot")
        self.assertEqual(st["rows_held"], [])


class DependencyStillBuilding(unittest.TestCase):
    """reef-queue.py ready: "rows whose `Depends` are merged" (SKILL reef-loop §1)."""

    def test_a_dependent_row_waits_until_its_dependency_is_merged_not_just_done_on_its_branch(self):
        p = Project(rows=((1, "first", ""), (2, "second", "1")))
        self.assertEqual(p.state()["rows_to_plan"], ["1"])
        p.plan(1)
        st = p.state()
        self.assertEqual((st["rows_to_plan"], st["rows_held"]), ([], []), "row 2 depends on a row still building")
        p.merge_close(101)                    # done on the feature branch, not merged
        st = p.state()
        self.assertEqual((st["rows_to_plan"], st["rows_held"]), ([], []), "done on its branch is not merged: row 2 still waits")
        p.pr_merged()                         # merged into main: row 2 is ready; row 1 is closed first
        st = p.state()
        self.assertEqual(st["rows_to_close"], ["1"])
        self.assertEqual(st["rows_to_plan"], ["2"], "room under the cap: the dependent row is ready")
        self.assertEqual(p.next_line(), "close: 1", "finish before starting: the close comes before the plan")

    def test_the_dependents_plan_is_not_dispatched_while_its_dependency_is_unmerged(self):
        # contract silent: row 2 was planned early (the owner asked) in its own worktree off main, while row 1 still builds.
        # Its tasks are ready by the graph's rule (no blocked-by), but its row's dependency is not merged: building on a
        # base without row 1 is building on sand. An owner expects row 2's tasks held until row 1 merges.
        p = Project(rows=((1, "first", ""), (2, "second", "1")))
        p.plan(1, slug=SLUG, tids=(101,))
        p.plan(2, slug="row-two-thing", tids=(201,))
        st = p.state()
        self.assertNotIn("201", st["dispatch_now"], f"row 2 depends on row 1 (still building): {st['dispatch_now']}")


class StopHookAtEachStage(unittest.TestCase):
    """reef-loop.py:10 — `--assert-no-idle` (the Stop hook) exits 2 only for: active, no wait, ready work, nothing in flight,
    no stop. SKILL reef-loop line 11: "the Stop hook then refuses a turn that leaves ready work undispatched"."""

    def test_the_stop_hook_through_the_fast_path(self):
        p = Project()
        p.loop_cmd("start")
        wt = p.plan(1, approve=False)
        self.assertEqual(p.fresh_stop_hook(), 0, "awaiting the owner's approval: the stop is allowed")
        p.approve()
        self.assertEqual(p.fresh_stop_hook(), 2, "dispatch now: 101 undispatched — refused")
        p.dispatch(101, wt)
        self.assertEqual(p.fresh_stop_hook(), 0, "in flight — allowed")
        p.hand_back(101, wt)
        self.assertEqual(p.fresh_stop_hook(), 2, "verify now: 101 — refused")
        p.fail(101, wt)
        self.assertEqual(p.fresh_stop_hook(), 2, "a fix round undispatched — refused")
        r = p.stop_hook()
        self.assertEqual(r.returncode, 0, "the same tick is refused once only")
        p.loop_cmd("wait", "owner: a question")
        self.assertEqual(p.fresh_stop_hook(), 0, "a recorded wait allows the stop")
        p.loop_cmd("clear-wait")

if __name__ == "__main__":
    unittest.main()
