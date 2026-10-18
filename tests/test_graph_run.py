"""reef-graph-run (0.7, workflow v2 phase 3): the task graph as a Claude Code workflow — gated, bookkept like a chat dispatch,
settled with the same checks."""
import glob
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
import test_loop as T  # noqa: E402  (the loop's project fixture: an approved, reviewed light task 101)


def graph_project():
    d = T.project()
    for n in ("reef-attempt", "reef-claims.py", "reef-adversarial", "reef-snapshot.sh", "reef-gate.sh", "reef-graph-run.py"):
        shutil.copy(os.path.join(ROOT, "scripts", n), os.path.join(d, "scripts", n))
    return d


def g(d, *args):
    return subprocess.run([sys.executable, os.path.join(d, "scripts", "reef-graph-run.py"), *args, "--repo", d], capture_output=True, text=True)


def pass_gate(d):
    g(d, "probe")
    with open(os.path.join(d, ".reef", "graph", "probe-results.json"), "w") as f:
        json.dump({"denied": True, "output": "reef-guard DENY: writing under .reef/approvals/"}, f)
    return g(d, "probe-check", ".reef/graph/probe-results.json")


class Gate(unittest.TestCase):
    def test_generate_refuses_until_the_probe_proves_the_hooks_reach_workflow_agents(self):
        d = graph_project()
        r = g(d, "generate")
        self.assertEqual(r.returncode, 1)
        self.assertIn("graph mode is OFF", r.stderr)
        r = g(d, "probe")
        self.assertEqual(r.returncode, 0, r.stderr)
        js = open(os.path.join(d, ".reef", "graph", "probe.js")).read()
        self.assertIn("export const meta", js)
        self.assertIn(".reef/approvals/graph-probe.json", js)
        self.assertIn("agentType: 'reef:mechanic'", js)
        # the agent says it was not denied → gate failed, graph mode stays off
        with open(os.path.join(d, ".reef", "graph", "probe-results.json"), "w") as f:
            json.dump({"denied": False, "output": "wrote it"}, f)
        r = g(d, "probe-check", ".reef/graph/probe-results.json")
        self.assertEqual(r.returncode, 1)
        self.assertIn("GATE FAILED", r.stdout)
        self.assertEqual(g(d, "generate").returncode, 1)
        # denied but the file exists anyway → failed, and the forged record is removed
        os.makedirs(os.path.join(d, ".reef", "approvals"), exist_ok=True)
        open(os.path.join(d, ".reef", "approvals", "graph-probe.json"), "w").write("{}")
        with open(os.path.join(d, ".reef", "graph", "probe-results.json"), "w") as f:
            json.dump({"denied": True, "output": "x"}, f)
        r = g(d, "probe-check", ".reef/graph/probe-results.json")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(d, ".reef", "approvals", "graph-probe.json")))
        # denied and no file → ok
        r = pass_gate(d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("GATE OK", r.stdout)
        self.assertTrue(json.load(open(os.path.join(d, ".reef", "graph", "gate.json")))["ok"])


class Generate(unittest.TestCase):
    def test_the_script_carries_the_tasks_and_the_dispatch_is_bookkept_like_the_guards(self):
        d = graph_project()
        pass_gate(d)
        r = g(d, "generate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("graph: 1 task(s): 101", r.stdout)
        scripts = glob.glob(os.path.join(d, ".reef", "graph", "run-*.js"))
        self.assertEqual(len(scripts), 1)
        js = open(scripts[0]).read()
        self.assertTrue(js.startswith("export const meta = {"))
        self.assertTrue(("REEF-TASK: " + os.path.join(d, "tasks", "101-a.md")) in js or ("REEF-TASK: " + os.path.join(os.path.realpath(d), "tasks", "101-a.md")) in js,
                        "the task's REEF-TASK: line (macOS: /var/folders resolves to /private/var/folders)")
        self.assertIn("agentType: 'reef:implementer'", js)
        self.assertIn("agentType: 'reef:mechanic'", js)
        self.assertIn("pipeline(TASKS", js)
        self.assertIn('"judge": false', js, "a gate-only task has no judge stage")
        self.assertNotIn("Date.now", js)
        # what the guard does on a chat dispatch happened here
        task = open(os.path.join(d, "tasks", "101-a.md")).read()
        self.assertIn("status: in-progress", task)
        self.assertIn("dispatches: 1", task)
        self.assertTrue(os.path.isfile(os.path.join(d, ".reef", "inflight", "101")))
        tick = subprocess.run([sys.executable, os.path.join(d, "scripts", "reef-loop.py"), "tick", "--repo", d], capture_output=True, text=True).stdout
        self.assertIn("in flight: 101", tick)
        self.assertIn("dispatch now: -", tick)
        # nothing left to dispatch now
        r = g(d, "generate")
        self.assertEqual(r.returncode, 1)
        self.assertIn("nothing to dispatch", r.stdout)


    def test_generate_leaves_a_fix_round_to_chat_and_refuses_under_mode_chat(self):
        d = graph_project()
        pass_gate(d)
        T.write(d, "tasks/101-a.md", T.task(101, "1").replace("attempts: 0", "attempts: 1"))
        r = g(d, "generate")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("skipped 101: chat mode (a fix round", r.stdout)
        self.assertIn("nothing to dispatch", r.stdout)
        self.assertEqual(glob.glob(os.path.join(d, ".reef", "graph", "run-*.js")), [])
        self.assertIn("attempts: 1\ndispatches: 0", open(os.path.join(d, "tasks", "101-a.md")).read(), "nothing was bookkept")
        T.write(d, "tasks/101-a.md", T.task(101, "1"))
        cfg = json.load(open(os.path.join(d, ".reef", "config.json")))
        cfg["graph"] = {"mode": "chat"}
        T.write(d, ".reef/config.json", json.dumps(cfg))
        r = g(d, "generate")
        self.assertEqual(r.returncode, 1)
        self.assertIn("graph.mode is `chat`", r.stderr)


class Settle(unittest.TestCase):
    def results(self, d, **gate):
        wt = os.path.join(d, ".reef", "worktrees", "101")
        os.makedirs(os.path.join(wt, ".reef", "ci-local"), exist_ok=True)
        gt = {"gate_exit": 0, "handback_check": "ok: hand-back 3 lines", "snapshot": "abc"}
        gt.update(gate)
        res = {"tasks": [{"task": "101", "task_file": os.path.join(d, "tasks", "101-a.md"), "worktree": wt, "judge": False, "hunter": False,
                          "gate": gt, "judges": [], "snapshot_after": "abc"}], "skipped": 0}
        p = os.path.join(d, ".reef", "graph", "results.json")
        with open(p, "w") as f:
            json.dump(res, f)
        return p

    def test_ready_clears_the_marker_and_a_failed_gate_counts_an_attempt(self):
        d = graph_project()
        pass_gate(d)
        g(d, "generate")
        r = g(d, "settle", self.results(d))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("READY TO MERGE 101", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(d, ".reef", "inflight", "101")), "handed back: no longer in flight")
        r = g(d, "settle", self.results(d, gate_exit=1, notes="FAIL tests/x"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL 101: gate exit 1: FAIL tests/x", r.stdout)
        self.assertIn("attempts: 1", open(os.path.join(d, "tasks", "101-a.md")).read(), "the failure is counted the way a chat round is")
        r = g(d, "settle", self.results(d, handback_check="REJECTED hand-back: 314 words > 150"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("hand-back: REJECTED", r.stdout)


if __name__ == "__main__":
    unittest.main()
