"""reef-run (0.7, the owner's go 2026-10-20): the outer runner — fresh headless sessions until the loop waits on the
owner, stops, parks, leaves work in flight, or hits the cap; gated by a probe that proves the guard reaches a headless
session. A fake `claude` on PATH plays the scripted sessions (one line of .fake-plan per call), streaming the events a
real `claude -p --output-format stream-json --verbose` sends (shapes taken from a real session, 2026-10-21)."""
import json
import os
import subprocess
import sys
import tempfile
import time
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
open(os.path.join(os.getcwd(), ".fake-env"), "w").write(os.environ.get("CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS", "unset"))
lp = os.path.join(os.getcwd(), ".reef", "loop.json")
st = {"active": True, "wait": None, "stop": None, "parked": None, "hashes": []}
kind, _, arg = step.partition(":")
result = "done"
if kind == "wait": st["wait"] = arg
elif kind == "stop": st["stop"] = arg
elif kind == "park": st["parked"] = arg
elif kind == "ownerstop":   # the owner runs `reef-run.py stop` from another terminal while this session works
    st["wait"] = "/clear requested"
    open(os.path.join(os.getcwd(), ".reef", "run", "stop-request"), "w").write("x")
elif kind == "flight":
    os.makedirs(os.path.join(os.getcwd(), ".reef", "inflight"), exist_ok=True)
    open(os.path.join(os.getcwd(), ".reef", "inflight", arg), "w").write("{}")
elif kind == "probe-deny": result = "reef-guard DENY: writing under .reef/approvals/ or .reef/review/ by hand"
elif kind == "probe-write":
    os.makedirs(os.path.join(os.getcwd(), ".reef", "approvals"), exist_ok=True)
    open(os.path.join(os.getcwd(), ".reef", "approvals", "run-probe.json"), "w").write("{}"); result = "it ran"
if kind not in ("probe-deny", "probe-write"):
    json.dump(st, open(lp, "w"))
def ev(**e): print(json.dumps(e), flush=True)
ev(type="system", subtype="init", session_id="x")
ev(type="assistant", message="a plain string where an object was expected")   # 2026-10-23: this shape killed a night
ev(type="user", message={"content": "plain text content"})
ev(type="system", subtype="task_started", tool_use_id="t1", description="Hunter 1203 plan round 2", subagent_type="reef:loophole-hunter")
ev(type="assistant", parent_tool_use_id="t1", message={"content": [{"type": "text", "text": "a sub-agent's own words"},
   {"type": "tool_use", "name": "SubagentHandback", "input": {"message": "BLOCKER: threat-model row\nVERDICT: FAIL"}}]})
ev(type="system", subtype="task_notification", tool_use_id="t1", status="completed")
ev(type="assistant", parent_tool_use_id=None, message={"content": [{"type": "text", "text": "Row 12: the hunter found one hole.\nmore"},
   {"type": "tool_use", "name": "Bash", "input": {"command": "python3 scripts/reef-approval.py --proxy --feature f --report r", "description": "Record Mahmoud's approval of row 12"}},
   {"type": "tool_use", "name": "Bash", "input": {"command": "ls -la", "description": "noise"}}]})
ev(type="result", result="partial", session_id="early", total_cost_usd=0.05)
ev(type="result", result=result, session_id="s-" + str(len(open(os.path.join(os.getcwd(), ".fake-calls")).read().splitlines())), total_cost_usd=0.1)
"""


FAKE_OC = r"""#!/usr/bin/env python3
import json, os, sys
open(os.path.join(os.getcwd(), ".fake-argv"), "a").write(json.dumps(sys.argv[1:]) + "\n")
plan = os.path.join(os.getcwd(), ".fake-plan")
lines = open(plan).read().splitlines()
step = lines[0] if lines else "none"
open(plan, "w").write("\n".join(lines[1:]))
kind, _, arg = step.partition(":")
lp = os.path.join(os.getcwd(), ".reef", "loop.json")
text = "done"
if kind == "wait":
    json.dump({"active": True, "wait": arg, "stop": None, "parked": None, "hashes": []}, open(lp, "w"))
elif kind == "probe-deny":
    text = "The write was refused: reef-guard: reef-guard DENY: writing under .reef/approvals/ by hand"
def ev(t, **part): print(json.dumps({"type": t, "timestamp": 1, "sessionID": "ses_oc1", "part": part}), flush=True)
ev("step_start")
ev("text", text="Row 5: dispatching the verifier for 501.\nmore")
ev("tool_use", tool="task", state={"status": "completed", "input": {"description": "Verifier 501", "prompt": "p", "subagent_type": "reef:verifier"},
   "output": "<task_result>RUN: agent=verifier\nVERDICT: PASS</task_result>"})
ev("tool_use", tool="bash", state={"status": "completed", "input": {"command": "python3 scripts/reef-approval.py --proxy --feature f --report r", "description": "Record Mahmoud's approval of row 5"}})
ev("tool_use", tool="bash", state={"status": "completed", "input": {"command": "ls -la", "description": "noise"}})
ev("step_finish", reason="tool-calls", cost=0.01, tokens={"input": 10, "output": 1})
ev("text", text=text)
ev("step_finish", reason="stop", cost=0.02, tokens={"input": 5, "output": 1})
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
    open(os.path.join(b, "opencode"), "w").write(FAKE_OC)
    os.chmod(os.path.join(b, "opencode"), 0o755)
    return d


def run(d, plan, *args):
    open(os.path.join(d, ".fake-plan"), "w").write("\n".join(plan))
    env = dict(os.environ, PATH=os.path.join(d, ".bin") + os.pathsep + os.environ["PATH"])
    env.pop("REEF_CLAUDE", None)
    return subprocess.run([sys.executable, RUN, *args, "--repo", d], capture_output=True, text=True, env=env)


def calls(d):
    p = os.path.join(d, ".fake-calls")
    return open(p).read().splitlines() if os.path.exists(p) else []


class Detach(unittest.TestCase):
    """2026-10-24 (the owner: why a manual terminal step instead of /reef-night?): --detach returns at once after every
    check, the runner works on in its own process session, and `status` shows it."""

    def test_a_refusal_prints_to_the_caller_and_a_detached_run_finishes_on_its_own(self):
        d = project()
        r = run(d, [], "--detach")
        self.assertEqual(r.returncode, 1, "no gate: refused before detaching, to the caller")
        self.assertIn("no GATE OK", r.stderr)
        self.assertEqual(run(d, ["probe-deny"], "probe").returncode, 0)
        r = run(d, ["stop:done"], "--detach")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"detached \(pid \d+\)")
        log = os.path.join(d, ".reef", "run", "run.log")
        for _ in range(150):
            if os.path.isfile(log) and '"stop": "done"' in open(log).read() and not os.path.exists(os.path.join(d, ".reef", "run", "lock")):
                break
            time.sleep(0.2)
        self.assertIn('"stop": "done"', open(log).read(), "the detached runner ran its session to the end")
        self.assertTrue(os.path.isfile(os.path.join(d, ".reef", "run", "runner.out")))
        s = run(d, [], "status")
        self.assertEqual(s.returncode, 0, s.stderr)
        self.assertIn("reef-run: not running; no night active", s.stdout)
        self.assertIn("session ended: stop 'done'", s.stdout)
        self.assertIn("ended on: done", s.stdout)


class OnOpenCode(unittest.TestCase):
    """0.7 (portability phase 2): `--host opencode` runs each session as `opencode run --command reef-loop --format json`;
    the probe and its gate are the host's own."""

    def test_the_probe_gates_the_host_and_a_session_streams_its_steps_and_cost(self):
        d = project()
        r = run(d, ["wait:owner x"], "--host", "opencode")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no GATE OK for --permission-mode opencode", r.stderr, "a Claude Code gate is not OpenCode's")
        r = run(d, ["probe-deny"], "probe", "--host", "opencode")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.load(open(os.path.join(d, ".reef", "run", "gate.json")))["mode"], "opencode")
        open(os.path.join(d, ".reef", "questions.md"), "w").write("- row 5: the look? — recommended: approve\n")
        r = run(d, ["wait:owner: row 5 look"], "--host", "opencode")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("run /reef-loop in OpenCode to answer them", r.stdout)
        argv = [json.loads(l) for l in open(os.path.join(d, ".fake-argv"))][-1]
        self.assertEqual(argv[:5], ["run", "--format", "json", "--command", "reef-loop"])
        self.assertTrue(argv[5].startswith("a reef-run iteration"), "the command carries the skill; the message is its arguments")
        live = open(os.path.join(d, ".reef", "run", "live.log")).read()
        self.assertIn("Row 5: dispatching the verifier for 501.", live)
        self.assertNotIn("more", live)
        self.assertIn("↔ Verifier 501 (reef:verifier): PASS", live)
        self.assertIn("· Record Mahmoud's approval of row 5", live)
        self.assertNotIn("noise", live)
        rec = [json.loads(l) for l in open(os.path.join(d, ".reef", "run", "run.log"))][-1]
        self.assertEqual((rec["session"], rec["cost_usd"]), ("ses_oc1", 0.03))
        self.assertEqual(run(d, [], "--host", "codex").returncode, 1)


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

    def test_the_owner_stops_a_running_runner_after_its_current_session(self):
        # 2026-10-24 (the owner: a command for the runner instead of the terminal): /reef-run starts it detached; stopping
        # it must not kill a headless session halfway through a merge, so `stop` asks and the runner ends between sessions
        r = run(self.d, [], "stop")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no runner is running", r.stdout)
        lock = os.path.join(self.d, ".reef", "run", "lock")
        open(lock, "w").write(str(os.getpid()))
        r = run(self.d, [], "stop")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ends after its current session", r.stdout)
        os.unlink(lock)
        r = run(self.d, ["none"], "--max-iterations", "1")
        self.assertNotIn("owner's request", r.stdout, "a request left from before this run is cleared at its start")
        r = run(self.d, ["ownerstop", "wait:/clear requested", "wait:/clear requested"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(calls(self.d)[-1], "ownerstop", "no session after the request")
        self.assertIn("stopped on the owner's request", r.stdout)

    def test_stop_park_work_in_flight_and_the_cap(self):
        self.assertEqual(run(self.d, ["stop:batch 2 released"]).returncode, 0)
        self.assertEqual(run(self.d, ["park:no progress"]).returncode, 3)
        r = run(self.d, ["flight:302"])
        self.assertEqual(r.returncode, 3)
        self.assertIn("work in flight (302)", r.stdout)
        # a marker older than loop.inflight_stale_minutes is a returned agent, not running work (2026-10-21)
        old = os.path.join(self.d, ".reef", "inflight", "302")
        os.utime(old, (os.path.getmtime(old) - 2 * 3600,) * 2)
        r = run(self.d, ["none", "none", "none"], "--max-iterations", "2")
        self.assertEqual(r.returncode, 4)
        self.assertIn("2 sessions, the iteration cap", r.stdout)

    def test_the_owner_sees_each_step_live_in_the_terminal_the_log_and_the_status_page(self):
        # 2026-10-21: the owner watched a silent terminal through a night session — "I cannot see any progress"
        page = os.path.join(self.d, ".reef", "status.html")
        open(page, "w").write("<h1>x</h1><!--runner--><!--/runner--><h2>The tick</h2>")
        r = run(self.d, ["stop:done"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        live = open(os.path.join(self.d, ".reef", "run", "live.log")).read()
        for step in ("s1 session started", "s1 → Hunter 1203 plan round 2 (reef:loophole-hunter)", "s1 ← Hunter 1203 plan round 2: FAIL",
                     "s1 Row 12: the hunter found one hole.", "s1 · Record Mahmoud's approval of row 12", "s1 session ended: stop 'done'"):
            self.assertIn(step, live)
            self.assertIn(step, r.stdout, "the terminal shows the same lines")
        for noise in ("a sub-agent's own words", "noise", "more"):
            self.assertNotIn(noise, live)
        self.assertIn("$0.10", live, "the last result event is the session's cost")
        self.assertEqual(json.loads(open(os.path.join(self.d, ".reef", "run", "run.log")).read().splitlines()[-1])["session"], "s-1")
        body = open(page).read()
        self.assertIn("<h2>Runner</h2>", body)
        self.assertIn("not running", body)
        self.assertIn("← Hunter 1203 plan round 2: FAIL", body)
        self.assertIn("<h2>The tick</h2>", body, "the tick's part is left alone")
        run(self.d, ["stop:again"])
        self.assertNotIn("s1 session ended: stop 'done'", open(os.path.join(self.d, ".reef", "run", "live.log")).read(), "a new run starts a fresh live log")

    def test_watch_follows_the_live_log_from_another_terminal(self):
        live = os.path.join(self.d, ".reef", "run", "live.log")
        open(live, "w").write("08:16 s1 → Hunter 1204 plan round 2 (reef:loophole-hunter)\n")
        w = subprocess.Popen([sys.executable, RUN, "watch", "--repo", self.d], stdout=subprocess.PIPE, text=True)
        time.sleep(1.5)
        open(live, "a").write("08:18 s1 ← Hunter 1204 plan round 2: PASS\n")
        time.sleep(1.5)
        w.terminate()
        out = w.communicate()[0]
        self.assertIn("→ Hunter 1204", out)
        self.assertIn("← Hunter 1204 plan round 2: PASS", out, "a new line shows up as it is written")
        self.assertEqual(calls(self.d), [], "watch starts no session")

    def test_a_session_waits_hours_not_ten_minutes_for_its_background_workflow(self):
        # night 2026-10-21: `claude -p` exited ten idle minutes after the last turn and killed the graph building 1201/1202
        self.assertEqual(run(self.d, ["stop:x"]).returncode, 0)
        self.assertEqual(open(os.path.join(self.d, ".fake-env")).read(), "10800000")
        open(os.path.join(self.d, ".fake-plan"), "w").write("stop:x")
        env = dict(os.environ, PATH=os.path.join(self.d, ".bin") + os.pathsep + os.environ["PATH"], CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS="0")
        env.pop("REEF_CLAUDE", None)
        subprocess.run([sys.executable, RUN, "--repo", self.d], capture_output=True, text=True, env=env)
        self.assertEqual(open(os.path.join(self.d, ".fake-env")).read(), "0", "a value the owner set wins")

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
