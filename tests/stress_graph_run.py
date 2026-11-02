"""Stress: reef-graph-run.py at its seams — what `generate` records per task (mark_dispatched: the status, the dispatch
odometer, the in-flight marker), a re-run after a crashed workflow, two generates at once, a task already done or at its
cap, `settle` re-run on the same output file or from another checkout, and how its records meet `reef-loop.py tick`.

The state is built with the real scripts (reef-plan-check, reef-record, reef-graph worktree, reef-attempt, reef-claims,
reef-loop); only the workflow's return value (results JSON) and the agents' files (hand-back, report) are faked."""
import glob
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import write, git, load_script, ROOT  # noqa: E402

import test_loop as T  # noqa: E402  (project(): an approved light task 101 in tasks/, 102 blocked by it)
import test_graph_run as G  # noqa: E402  (graph_project(), pass_gate(), g())


def read(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def tick(d):
    r = T.loop(d, "tick", "--json")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def task_file(d):
    return os.path.join(d, "tasks", "101-a.md")


def results(d, tid="101", **gate):
    """The workflow's return value for one gate-only task, as the completion notice's output file holds it."""
    wt = os.path.join(d, ".reef", "worktrees", tid)
    os.makedirs(os.path.join(wt, ".reef", "ci-local"), exist_ok=True)
    gt = {"gate_exit": 0, "handback_check": "ok: hand-back 3 lines", "snapshot": "abc"}
    gt.update(gate)
    res = {"tasks": [{"task": tid, "task_file": task_file(d), "worktree": wt, "judge": False, "hunter": False,
                      "gate": gt, "judges": [], "snapshot_after": "abc"}], "skipped": 0}
    p = os.path.join(d, ".reef", "graph", f"wf-{tid}.output")
    with open(p, "w") as f:
        json.dump({"summary": "reef graph", "result": res}, f)
    return p


def judged(d, attempts=0):
    """101 as a judged (full-tier) task, approved and plan-reviewed at its digest — the shape test_graph_run uses."""
    t = (T.task(101, "1").replace("complexity: mech", "complexity: design").replace("tier: light", "tier: full")
         .replace("verify: gate-only", "verify: judge").replace("## Scope\nx", "## Scope\nx\n\n## Decision\nhuman words")
         .replace("attempts: 0", f"attempts: {attempts}"))
    T.write(d, "tasks/101-a.md", t)
    T.approve(d, "1")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-record"), "plan-review", "1", "PASS", "--root", d],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


class Bookkeeping(unittest.TestCase):
    """mark_dispatched's docstring: "What the guard does on an allowed Task dispatch (reef-guard check_dispatch): the task becomes
    in-progress, its dispatch odometer moves, and .reef/inflight/<id> is written in the main checkout"."""

    def test_a_task_file_without_a_dispatches_key_still_has_its_odometer_moved(self):
        # the plan check does not require `dispatches:` (reef-plan-check.py REQUIRED, :55); the guard's bump_dispatches adds the
        # key when it is missing (reef-guard.py:1238-1241) — graph mode must move the same odometer (docstring above)
        d = G.graph_project()
        T.write(d, "tasks/101-a.md", read(task_file(d)).replace("dispatches: 0\n", ""))
        T.approve(d, "1")
        G.pass_gate(d)
        r = G.g(d, "generate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("status: in-progress", read(task_file(d)))
        self.assertRegex(read(task_file(d)), r"(?m)^dispatches: 1$",
                         "the dispatch odometer moves on a graph dispatch as on a chat one; without it the runaway backstop never counts")

    def test_the_runaway_backstop_refuses_a_task_dispatched_twice_the_cap_without_failures(self):
        # the guard: `dispatches >= 2 * cap` → deny, "runaway-loop backstop" (reef-guard.py:1653-1655). graph-run's docstring:
        # "Dispatch-time checks the guard makes on a Task call ... happen here at generation instead" — a crashed workflow records
        # no failure (settle refuses a null result), so the odometer is the only count of those rounds
        d = G.graph_project()
        T.write(d, "tasks/101-a.md", read(task_file(d)).replace("dispatches: 0", "dispatches: 6"))
        T.approve(d, "1")
        G.pass_gate(d)
        r = G.g(d, "generate")
        self.assertNotIn("graph: 1 task(s): 101", r.stdout, "a task dispatched 6x against cap 3 with no recorded failure is not dispatched again")
        self.assertFalse(os.path.exists(os.path.join(d, ".reef", "inflight", "101")), r.stdout)
        self.assertRegex(read(task_file(d)), r"(?m)^dispatches: 6$")

    def test_a_crlf_task_file_keeps_its_line_endings_when_dispatched(self):
        # contract silent; the reader in reef-attempt keeps `[^\r\n]*` (stress round one, M1); a dispatch must not leave a
        # file with mixed line endings (the next digest and every `^status:` reader read a different line than the writer)
        mod = load_script("reef-graph-run.py")
        d = T.project()
        text = read(task_file(d)).replace("\n", "\r\n")
        with open(task_file(d), "w", encoding="utf-8", newline="") as f:
            f.write(text)
        mod.mark_dispatched(d, task_file(d), "101")
        after = read(task_file(d))
        self.assertIn("status: in-progress\r\n", after)
        self.assertNotRegex(after, r"[^\r]\n", "every line still ends in CRLF")

    def test_the_markers_tier_is_the_guards_reading_of_a_quoted_critical_tier(self):
        # the guard reads frontmatter with quotes stripped (reef-guard.py:1229) and its critical_inflight lock reads the marker's
        # `tier` == "critical" (reef-guard.py:1720-1724); the plan check accepts a quoted value. The marker must carry the same word
        mod = load_script("reef-graph-run.py")
        d = T.project()
        T.write(d, "tasks/101-a.md", read(task_file(d)).replace("tier: light", 'tier: "critical"').replace("feature: 1", 'feature: "1"'))
        mod.mark_dispatched(d, task_file(d), "101")
        rec = json.load(open(os.path.join(d, ".reef", "inflight", "101")))
        self.assertEqual(rec["tier"], "critical")
        self.assertEqual(rec["feature"], "1")

    def test_a_mech_task_without_a_tier_key_is_marked_light_as_the_guard_marks_it(self):
        # reef-guard.py:1402 task_tier: no tier → light for complexity mech, else full; mark_dispatched defaults to full always
        mod = load_script("reef-graph-run.py")
        d = T.project()
        T.write(d, "tasks/101-a.md", read(task_file(d)).replace("tier: light\n", ""))
        mod.mark_dispatched(d, task_file(d), "101")
        self.assertEqual(json.load(open(os.path.join(d, ".reef", "inflight", "101")))["tier"], "light")


class ReRuns(unittest.TestCase):
    def test_a_crashed_workflow_is_held_in_flight_then_re_dispatched_once_its_marker_is_stale(self):
        # SKILL reef-graph Rules: "A task the results omit (the agent died or was skipped) stays in flight: `generate` skips it,
        # and the tick frees it after loop.inflight_stale_minutes"
        d = G.graph_project()
        G.pass_gate(d)
        self.assertEqual(G.g(d, "generate").returncode, 0)
        # the workflow was killed: its output holds result null, settle refuses and leaves the marker
        out = os.path.join(d, "wf.output")
        json.dump({"summary": "reef graph", "result": None}, open(out, "w"))
        r = G.g(d, "settle", out)
        self.assertEqual(r.returncode, 1)
        self.assertTrue(os.path.isfile(os.path.join(d, ".reef", "inflight", "101")))
        r = G.g(d, "generate")
        self.assertEqual(r.returncode, 1)
        self.assertIn("nothing to dispatch", r.stdout, "still in flight: never a second workflow on it")
        old = time.time() - 120 * 60
        os.utime(os.path.join(d, ".reef", "inflight", "101"), (old, old))
        st = tick(d)
        self.assertIn("101", st["returned_unmerged"])
        self.assertIn("101", st["dispatch_now"])
        r = G.g(d, "generate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("graph: 1 task(s): 101", r.stdout)
        self.assertRegex(read(task_file(d)), r"(?m)^dispatches: 2$")
        self.assertIn("101", tick(d)["in_flight"], "the fresh marker holds it again")

    def test_settling_the_same_output_file_twice_counts_one_attempt(self):
        # contract silent on a re-run; SKILL reef-graph §3: "`FAIL <id>: <why>` → the attempt is already counted" — one round,
        # one attempt. The orchestrator re-runs a step whose session died after it printed (the class "a step that crashed
        # half-way, re-run"); the results file is the same round's summary
        d = G.graph_project()
        G.pass_gate(d)
        G.g(d, "generate")
        p = results(d, gate_exit=1, notes="FAIL tests/x")
        r = G.g(d, "settle", p)
        self.assertIn("attempt counted: attempt=2/3", r.stdout)
        r = G.g(d, "settle", p)
        self.assertRegex(read(task_file(d)), r"(?m)^attempts: 1$", "the same round settled twice burns one attempt, not two:\n" + r.stdout)

    def test_settle_from_the_feature_worktree_clears_the_marker_generate_wrote_in_main(self):
        # mark_dispatched writes the marker "in the main checkout"; SKILL reef-graph Rules: "`settle` clears every marker it sees
        # in the results". settle removes it at os.path.join(<the caller's checkout>, ...) only
        d = G.graph_project()
        G.pass_gate(d)
        G.g(d, "generate")
        self.assertTrue(os.path.isfile(os.path.join(d, ".reef", "inflight", "101")))
        wt = os.path.join(d, ".reef", "worktrees", "feat")
        self.assertEqual(git(d, "worktree", "add", "-q", "-b", "feat/1", wt).returncode, 0)
        r = subprocess.run([sys.executable, os.path.join(d, "scripts", "reef-graph-run.py"), "settle", results(d), "--repo", wt],
                           capture_output=True, text=True)
        self.assertIn("READY TO MERGE 101", r.stdout, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(d, ".reef", "inflight", "101")),
                         "the task was handed back: its marker in main is gone, or the tick holds it in flight for 90 minutes")

    def test_generate_from_inside_a_feature_worktree_reads_this_machines_gate(self):
        # the tick reads the gate from the main checkout (reef-loop.py graph_mode: "this machine's probe recorded GATE OK
        # (`.reef/graph/gate.json`)" in `first`, the main checkout) and names the task `dispatch (graph)`; generate must agree
        d = G.graph_project()
        G.pass_gate(d)
        wt = os.path.join(d, ".reef", "worktrees", "feat")
        self.assertEqual(git(d, "worktree", "add", "-q", "-b", "feat/1", wt).returncode, 0)
        self.assertEqual(tick(d)["dispatch_mode"].get("101"), "graph")
        r = subprocess.run([sys.executable, os.path.join(d, "scripts", "reef-graph-run.py"), "generate", "--repo", wt],
                           capture_output=True, text=True)
        self.assertNotIn("graph mode is OFF", r.stderr, "the machine's gate is one record, in the main checkout")


class TwoAtOnce(unittest.TestCase):
    def test_two_ready_tasks_are_both_dispatched_and_both_in_flight(self):
        d = G.graph_project()
        T.write(d, "tasks/103-c.md", T.task(103, "1"))
        T.approve(d, "1")
        cfg = json.load(open(os.path.join(d, ".reef", "config.json")))
        cfg["graph"] = {"parallel": 3}
        T.write(d, ".reef/config.json", json.dumps(cfg))
        G.pass_gate(d)
        r = G.g(d, "generate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("graph: 2 task(s): 101, 103", r.stdout)
        st = tick(d)
        self.assertEqual(sorted(st["in_flight"]), ["101", "103"])
        self.assertEqual(st["dispatch_now"], [])

    def test_two_generates_at_once_dispatch_a_task_once(self):
        # reef-graph.py:23 "two dispatches racing for the last parallel slot cannot both win" (the guard's graph lock,
        # reef-guard.py:1630-1636); graph-run's docstring puts the guard's dispatch-time checks at generation. Two generates
        # racing (a second session, the runner and a chat) read the same tick before either marks. Round 2: the task worktree
        # already exists, so `git worktree add` no longer serialises the first dispatch by accident
        d = G.graph_project()
        G.pass_gate(d)
        self.assertEqual(G.g(d, "generate").returncode, 0)
        r = G.g(d, "settle", results(d, gate_exit=1, notes="FAIL tests/x"))
        self.assertIn("attempt counted: attempt=2/3", r.stdout, r.stdout + r.stderr)
        real = os.path.join(d, "scripts", "reef-loop-real.py")
        shutil.move(os.path.join(d, "scripts", "reef-loop.py"), real)
        T.write(d, "scripts/reef-loop.py", "import runpy, sys, time\ntime.sleep(1.0)\nsys.argv[0] = %r\nrunpy.run_path(%r, run_name='__main__')\n" % (real, real))
        outs = []

        def one():
            outs.append(G.g(d, "generate"))
        th = [threading.Thread(target=one) for _ in range(2)]
        for t in th:
            t.start()
        for t in th:
            t.join()
        won = [o for o in outs if "graph: 1 task(s): 101" in o.stdout]
        self.assertEqual(len(won), 1, "one workflow for 101, not two on the same worktree:\n" + "\n---\n".join(o.stdout + o.stderr for o in outs))
        self.assertRegex(read(task_file(d)), r"(?m)^dispatches: 2$")


class DoneOrCapped(unittest.TestCase):
    def test_a_done_task_named_by_tasks_is_skipped_and_untouched(self):
        d = G.graph_project()
        T.write(d, "tasks/done/101-a.md", T.task(101, "1", status="done"))
        os.unlink(task_file(d))
        T.approve(d, "1")
        G.pass_gate(d)
        r = G.g(d, "generate", "--tasks", "101")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(d, ".reef", "inflight", "101")))
        self.assertIn("status: done", read(os.path.join(d, "tasks", "done", "101-a.md")))

    def test_a_task_at_its_cap_is_skipped_and_untouched(self):
        # SKILL reef-graph §1: "reef-attempt (caps …; exit 2 = parked, listed as `skipped`)"
        d = G.graph_project()
        T.write(d, "tasks/101-a.md", read(task_file(d)).replace("attempts: 0", "attempts: 3"))
        T.approve(d, "1")
        G.pass_gate(d)
        r = G.g(d, "generate", "--tasks", "101")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(d, ".reef", "inflight", "101")))
        self.assertIn("status: pending", read(task_file(d)))
        self.assertIn("dispatches: 0", read(task_file(d)))


class MeetsTheTick(unittest.TestCase):
    def test_a_report_settle_rejected_is_never_closed_by_the_next_tick(self):
        # settle copies the verifier's report into the worktree, then reef-claims rejects it and reef-attempt records the FAIL
        # (graph-run settle_task). The tick: "a PASS newer than both [hand-back, FAIL] → merge-close" (reef-loop.py:340-343).
        # The FAIL settle just wrote is the newer record: the next step is a fix round, never a close on a rejected report
        d = G.graph_project()
        G.pass_gate(d)
        judged(d)
        self.assertEqual(G.g(d, "generate").returncode, 0)
        rp = os.path.join(d, "report-101-verifier.md")
        with open(rp, "w") as f:
            f.write("RUN: agent=verifier task=101\nVERDICT: PASS\n")   # no `RULE AC1:` line: reef-claims rejects it
        p = results(d)
        res = json.load(open(p))
        t = res["result"]["tasks"][0]
        t["judge"] = True
        t["judges"] = [{"role": "verifier", "verdict": "PASS", "report_path": rp, "summary": "PASS"}]
        json.dump(res, open(p, "w"))
        while time.time() % 1 > 0.2:   # settle's copy and its FAIL land in one wall-clock second, as they do in most real runs
            time.sleep(0.02)
        r = G.g(d, "settle", p)
        self.assertIn("verifier report rejected", r.stdout, r.stdout + r.stderr)
        self.assertIn("attempts: 1", read(task_file(d)))
        st = tick(d)
        self.assertNotIn("101", st["close_now"], "a report settle rejected is not a PASS to merge-close: " + json.dumps(st)[:400])

    def test_after_a_green_settle_the_tick_never_dispatches_a_second_implementer(self):
        # SKILL reef-graph §3: READY TO MERGE → /reef-task step 4. Until the orchestrator merges, the tick must not offer the task
        # to a fresh implementer (the hand-back is in the worktree, the marker gone)
        d = G.graph_project()
        G.pass_gate(d)
        G.g(d, "generate")
        T.write(d, ".reef/ci-local/handback-101.md", "RUN: agent=implementer task=101\n")
        r = G.g(d, "settle", results(d))
        self.assertIn("READY TO MERGE 101", r.stdout)
        st = tick(d)
        self.assertNotIn("101", st["dispatch_now"])


if __name__ == "__main__":
    unittest.main()
