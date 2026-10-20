"""reef-run (0.7, the owner's go 2026-10-20): the outer runner — fresh headless sessions until the loop waits on the
owner, stops, parks, leaves work in flight, or hits the cap; gated by a probe that proves the guard reaches a headless
session. A fake `claude` on PATH plays the scripted sessions (one line of .fake-plan per call)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RUN = os.path.join(ROOT, "scripts", "reef-run.py")

FAKE = r"""#!/usr/bin/env python3
import json, os, sys
plan = os.path.join(os.getcwd(), ".fake-plan")
lines = open(plan).read().splitlines()
step, rest = (lines[0] if lines else "none"), lines[1:]
open(plan, "w").write("\n".join(rest))
open(os.path.join(os.getcwd(), ".fake-calls"), "a").write(step + "\n")
lp = os.path.join(os.getcwd(), ".reef", "loop.json")
st = {"active": True, "wait": None, "stop": None, "parked": None, "hashes": []}
kind, _, arg = step.partition(":")
result = "done"
if kind == "wait": st["wait"] = arg
elif kind == "stop": st["stop"] = arg
elif kind == "park": st["parked"] = arg
elif kind == "flight":
    os.makedirs(os.path.join(os.getcwd(), ".reef", "inflight"), exist_ok=True)
    open(os.path.join(os.getcwd(), ".reef", "inflight", arg), "w").write("{}")
elif kind == "probe-deny": result = "reef-guard DENY: writing under .reef/approvals/ or .reef/review/ by hand"
elif kind == "probe-write":
    os.makedirs(os.path.join(os.getcwd(), ".reef", "approvals"), exist_ok=True)
    open(os.path.join(os.getcwd(), ".reef", "approvals", "run-probe.json"), "w").write("{}"); result = "it ran"
if kind not in ("probe-deny", "probe-write"):
    json.dump(st, open(lp, "w"))
print(json.dumps({"result": result, "session_id": "s-" + str(len(open(os.path.join(os.getcwd(), ".fake-calls")).read().splitlines())), "total_cost_usd": 0.1}))
"""


def project():
    d = tempfile.mkdtemp(prefix="reef-run.")
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    os.makedirs(os.path.join(d, ".reef"))
    open(os.path.join(d, ".reef", "config.json"), "w").write('{"gates": {"full": "true"}}')
    b = os.path.join(d, ".bin")
    os.makedirs(b)
    open(os.path.join(b, "claude"), "w").write(FAKE)
    os.chmod(os.path.join(b, "claude"), 0o755)
    return d


def run(d, plan, *args):
    open(os.path.join(d, ".fake-plan"), "w").write("\n".join(plan))
    env = dict(os.environ, PATH=os.path.join(d, ".bin") + os.pathsep + os.environ["PATH"])
    env.pop("REEF_CLAUDE", None)
    return subprocess.run([sys.executable, RUN, *args, "--repo", d], capture_output=True, text=True, env=env)


def calls(d):
    p = os.path.join(d, ".fake-calls")
    return open(p).read().splitlines() if os.path.exists(p) else []


class Probe(unittest.TestCase):
    def test_the_runner_loops_only_after_a_headless_session_was_denied_a_forbidden_write(self):
        d = project()
        r = run(d, ["stop:x"])
        self.assertEqual(r.returncode, 1, "no probe, no loop")
        self.assertIn("reef-run.py probe", r.stderr)
        self.assertEqual(calls(d), [], "nothing ran")
        r = run(d, ["probe-write"], "probe")
        self.assertEqual(r.returncode, 1)
        self.assertIn("GATE FAILED: the file was written", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(d, ".reef", "approvals", "run-probe.json")), "the probe's write is removed")
        r = run(d, ["probe-deny"], "probe")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("GATE OK", r.stdout)
        gate = json.load(open(os.path.join(d, ".reef", "run", "gate.json")))
        self.assertEqual((gate["ok"], gate["mode"]), (True, "auto"))
        r = run(d, ["stop:x"], "--permission-mode", "bypassPermissions")
        self.assertEqual(r.returncode, 1, "the probe passed for another mode")


class Loop(unittest.TestCase):
    def setUp(self):
        self.d = project()
        self.assertEqual(run(self.d, ["probe-deny"], "probe").returncode, 0)
        open(os.path.join(self.d, ".fake-calls"), "w").write("")

    def test_a_ceiling_handoff_starts_the_next_session_and_an_owner_wait_ends_the_run(self):
        open(os.path.join(self.d, ".reef", "questions.md"), "w").write("- row 12: share links in host logs? — recommended: accept\n")
        r = run(self.d, ["wait:/clear requested — ceiling", "wait:/clear requested — ceiling", "wait:owner: approve row 12"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(len(calls(self.d)), 3)
        self.assertIn("waiting on you — owner: approve row 12", r.stdout)
        self.assertIn("questions.md", r.stdout)
        log = [json.loads(l) for l in open(os.path.join(self.d, ".reef", "run", "run.log"))]
        self.assertEqual([x["iteration"] for x in log], [1, 2, 3])
        self.assertEqual(log[0]["session"], "s-1")
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "run", "lock")), "the lock is released")

    def test_stop_park_work_in_flight_and_the_cap(self):
        self.assertEqual(run(self.d, ["stop:batch 2 released"]).returncode, 0)
        self.assertEqual(run(self.d, ["park:no progress"]).returncode, 3)
        r = run(self.d, ["flight:302"])
        self.assertEqual(r.returncode, 3)
        self.assertIn("work in flight (302)", r.stdout)
        os.remove(os.path.join(self.d, ".reef", "inflight", "302"))
        r = run(self.d, ["none", "none", "none"], "--max-iterations", "2")
        self.assertEqual(r.returncode, 4)
        self.assertIn("2 sessions, the iteration cap", r.stdout)

    def test_a_second_runner_is_refused(self):
        os.makedirs(os.path.join(self.d, ".reef", "run"), exist_ok=True)
        open(os.path.join(self.d, ".reef", "run", "lock"), "w").write(str(os.getpid()))   # a live pid
        n = len(calls(self.d))
        r = run(self.d, ["stop:x"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("one runner per checkout", r.stderr)
        self.assertEqual(len(calls(self.d)), n, "no session started")


if __name__ == "__main__":
    unittest.main()
