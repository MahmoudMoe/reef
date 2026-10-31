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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import git_repo, git  # noqa: E402  (the suites' shared fixtures, once)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RUN = os.path.join(ROOT, "scripts", "reef-run.py")

FAKE = r"""#!/usr/bin/env python3
import json, os, sys
plan = os.path.join(os.getcwd(), ".fake-plan")
open(os.path.join(os.getcwd(), ".fake-prompt"), "a").write((sys.argv[sys.argv.index("-p") + 1] if "-p" in sys.argv else "") + "\n")
lines = open(plan).read().splitlines()
step, rest = (lines[0] if lines else "none"), lines[1:]
open(plan, "w").write("\n".join(rest))
open(os.path.join(os.getcwd(), ".fake-calls"), "a").write(step + "\n")
open(os.path.join(os.getcwd(), ".fake-env"), "w").write(os.environ.get("CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS", "unset"))
open(os.path.join(os.getcwd(), ".fake-argv"), "w").write(json.dumps(sys.argv))
if os.path.isfile(os.path.join(os.getcwd(), ".reef", "night", "autopilot")):   # the marker the runner wrote, for the test to read
    open(os.path.join(os.getcwd(), ".fake-autopilot"), "w").write(open(os.path.join(os.getcwd(), ".reef", "night", "autopilot")).read())
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
elif kind == "job":   # the session starts a runner job (step 3) and records the wait the skill names: job:<name>:<seconds>
    import subprocess
    jn, _, secs = arg.partition(":")
    subprocess.run([sys.executable, os.path.join(os.getcwd(), "scripts", "reef-run.py"), "--repo", os.getcwd(), "job", jn, "--", "sh", "-c", f"sleep {secs}; echo job ok"], check=True)
    st["wait"] = f"job: {jn} — the full gate"
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
if kind == "sleep":   # a session mid-gate: one step after a second, then quiet for a long time
    import signal, time, traceback
    crumb = os.path.join(os.getcwd(), ".fake-died")   # why this fake ended, for the test to show (CI's macOS leg died unseen)
    for s_ in (signal.SIGHUP, signal.SIGPIPE):          # a session outlives its runner: the real `claude` did (2026-10-29)
        signal.signal(s_, signal.SIG_IGN)
    def _named(signum, frame):                          # any other signal: say which one ended this fake, then die of it
        open(crumb, "w").write(f"signal {signum} ({signal.Signals(signum).name}) from the outside\n")
        signal.signal(signum, signal.SIG_DFL); os.kill(os.getpid(), signum)
    for s_ in (signal.SIGTERM, signal.SIGINT, signal.SIGQUIT, signal.SIGABRT, signal.SIGALRM, signal.SIGUSR1, signal.SIGUSR2, signal.SIGXCPU):
        signal.signal(s_, _named)
    def say(**e):   # every print, the first included: on a slow start the runner is dead before this fake says a word (macOS, PRs 215/219/222)
        try:
            ev(**e)
        except OSError:   # the runner is gone and the pipe with it — keep running, as the real one did
            sys.stdout = open(os.devnull, "w")
    try:
        say(type="system", subtype="init", session_id="x")
        time.sleep(1)
        say(type="system", subtype="task_started", tool_use_id="t9", description="Gate full", subagent_type="reef:mechanic")
        time.sleep(120)
    except BaseException as e:
        open(crumb, "w").write("".join(traceback.format_exception(type(e), e, e.__traceback__)) or repr(e))
        raise
    sys.exit(0)
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
open(os.path.join(os.getcwd(), ".fake-prompt"), "a").write((sys.argv[sys.argv.index("-p") + 1] if "-p" in sys.argv else "") + "\n")
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
    d = git_repo(prefix="reef-run.", branch="main")
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
    env = dict(os.environ, PATH=os.path.join(d, ".bin") + os.pathsep + os.environ["PATH"], REEF_NOTIFY="0", CLAUDE_PLUGIN_ROOT=ROOT)
    env.pop("REEF_CLAUDE", None)
    return subprocess.run([sys.executable, RUN, *args, "--repo", d], capture_output=True, text=True, env=env)


def calls(d):
    p = os.path.join(d, ".fake-calls")
    return open(p).read().splitlines() if os.path.exists(p) else []


class UnknownArgument(unittest.TestCase):
    """2026-10-29: `reef-run.py --status`, a typo for the verb `status`, fell through to cmd_run and started a loop session
    on the owner's project without a word. An argument that is neither a verb (first position) nor a known flag refuses
    with the usage block, exit 2; a run starts only on an empty argv or known flags."""

    def load(self):
        import importlib.machinery, importlib.util
        loader = importlib.machinery.SourceFileLoader("reef_run_under_test", RUN)
        spec = importlib.util.spec_from_loader("reef_run_under_test", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        return mod

    def test_a_typo_for_a_verb_refuses_with_the_usage_and_runs_nothing(self):
        import contextlib, io
        mod, d, called = self.load(), project(), []
        mod.cmd_run = lambda *a, **k: called.append("run") or 0
        mod.cmd_status = lambda root: called.append("status") or 0
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            mod.main(["--status", "--repo", d])
        self.assertEqual(cm.exception.code, 1, "refused — 1, the runner's refusal code (2 is 'waiting on the owner', which the factory reads as built)")
        self.assertEqual(called, [], "nothing ran")
        self.assertIn("Usage", err.getvalue())
        self.assertIn("'--status'", err.getvalue())
        self.assertEqual(mod.main(["status", "--repo", d]), 0)
        self.assertEqual(called, ["status"], "the verb reaches cmd_status")
        for argv, why in ((["--repo"], "a flag without its value is refused, not an IndexError"), (["--repo", d, "--nigth"], "a misspelt flag"),
                          (["--max-iterations", "abc"], "a count that is not one")):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
                mod.main(argv)
            self.assertEqual(cm.exception.code, 1, why)
        self.assertEqual(called, ["status"])

    def test_from_the_shell_too_and_no_session_starts(self):
        d = project()
        self.assertEqual(run(d, ["probe-deny"], "probe").returncode, 0)
        r = run(d, ["stop:never"], "--status")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("unknown argument '--status'", r.stderr)
        self.assertEqual(calls(d), ["probe-deny"], "the probe's session only — no loop session was started")
class OrphanSession(unittest.TestCase):
    """2026-10-29 (the owner): the runner died when its stdout pipe closed, its `claude -p /reef-loop` session lived on running
    gates at full CPU with no window anywhere, and `reef-run.py stop` said "no runner is running" — `pkill` was the only way.
    The runner records the session's pid (.reef/run/session.pid); status and stop read it; the runner's own exit ends it."""

    def setUp(self):
        self.d = project()
        self.assertEqual(run(self.d, ["probe-deny"], "probe").returncode, 0)

    def start(self, stdout=subprocess.DEVNULL):
        open(os.path.join(self.d, ".fake-plan"), "w").write("sleep:x")
        env = dict(os.environ, PATH=os.path.join(self.d, ".bin") + os.pathsep + os.environ["PATH"], REEF_NOTIFY="0")
        env.pop("REEF_CLAUDE", None)
        p = subprocess.Popen([sys.executable, RUN, "--repo", self.d], env=env, stdout=stdout, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: p.poll() is None and p.kill())
        sp = os.path.join(self.d, ".reef", "run", "session.pid")
        for _ in range(100):
            if os.path.isfile(sp) and os.path.getsize(sp):
                break
            time.sleep(0.1)
        rec = json.load(open(sp))
        self.assertTrue(alive(rec["pid"]), "the session is running")
        return p, rec

    def test_status_names_the_orphan_and_stop_ends_it(self):
        p, rec = self.start()
        os.kill(p.pid, 9)   # the runner dies without a word — its session does not
        p.wait(timeout=10)
        time.sleep(1.5)     # past the fake's one step: on CI's slower start it wrote into the dead pipe (macOS, PR 215's run)
        crumb = os.path.join(self.d, ".fake-died")
        self.assertTrue(alive(rec["pid"]), "the orphan is what the owner saw — the fake ended: " + (open(crumb).read() if os.path.exists(crumb) else "(no breadcrumb: killed by a signal, or never ran)"))
        r = run(self.d, [], "status")
        self.assertIn(f"runner gone, session {rec['pid']} still running since {rec['started']}", r.stdout)
        r = run(self.d, [], "stop")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(str(rec["pid"]), r.stdout)
        for _ in range(100):
            if not alive(rec["pid"]):
                break
            time.sleep(0.1)
        self.assertFalse(alive(rec["pid"]), "stop ended the session")
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "run", "session.pid")))
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "run", "lock")))
        st = json.load(open(os.path.join(self.d, ".reef", "loop.json")))
        self.assertFalse(st["active"])
        self.assertIn("runner gone", st["stop"], "loop.json agrees: the loop is stopped, and says why")
        self.assertIn("not running", run(self.d, [], "status").stdout)

    def test_stop_kills_only_the_process_the_runner_recorded(self):
        # the security review: session.pid is a file any agent in the checkout can write, and a pid is reused — a record
        # that names a live process the runner did not start must never be killed; the ps start time is the identity
        victim = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            sp = os.path.join(self.d, ".reef", "run", "session.pid")
            json.dump({"pid": victim.pid, "started": "2026-10-29T19:00:00Z; rm -rf /", "lstart": "Wed Oct 29 00:00:00 2025"}, open(sp, "w"))
            r = run(self.d, [], "status")
            self.assertNotIn("rm -rf", r.stdout + r.stderr, "the record's text is validated before it is printed")
            r = run(self.d, [], "stop")
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("does not match", r.stdout + r.stderr)
            self.assertIsNone(victim.poll(), "the process the record named is not the session: untouched")
            self.assertFalse(os.path.exists(sp), "a record that matches nothing is cleared")
        finally:
            victim.kill()

    def test_the_owners_incident_a_closed_stdout_pipe_ends_the_session_with_the_runner(self):
        # 2026-10-29: the runner's stdout pipe closed (the terminal that started it went away), the runner died on the
        # write, the session lived on. The runner's exit path ends the session — and the gate that session was running
        p, rec = self.start(stdout=subprocess.PIPE)
        p.stdout.close()                       # the reader is gone; the runner's next line is a broken pipe
        p.wait(timeout=30)
        for _ in range(150):
            if not alive(rec["pid"]):
                break
            time.sleep(0.1)
        self.assertFalse(alive(rec["pid"]), "the session died with the runner")
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "run", "lock")))
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "run", "session.pid")))

    def test_a_terminated_runner_ends_its_session_itself(self):
        p, rec = self.start()
        os.kill(p.pid, 15)
        p.wait(timeout=20)
        for _ in range(150):
            if not alive(rec["pid"]):
                break
            time.sleep(0.1)
        self.assertFalse(alive(rec["pid"]), "the runner's exit path ends the session it started")
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "run", "session.pid")))
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "run", "lock")))


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


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
        self.assertIn("/reef-loop in OpenCode", r.stdout, "the host is named")
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
        r = run(self.d, ["wait:/clear requested — ceiling after 1201", "wait:/clear requested — ceiling after 1202", "wait:owner: approve row 12"])
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
        self.assertEqual(r.returncode, 2, "a marker that names no session: the owner decides, with the command (2026-10-30)\n" + r.stdout)
        self.assertIn("work in flight (302)", r.stdout)
        self.assertIn("python3 scripts/reef-run.py release 302", r.stdout, "the way out is named")
        # a marker older than loop.inflight_stale_minutes is a returned agent, not running work (2026-10-21)
        old = os.path.join(self.d, ".reef", "inflight", "302")
        os.utime(old, (os.path.getmtime(old) - 2 * 3600,) * 2)
        r = run(self.d, ["none", "none", "none"], "--max-iterations", "2")
        self.assertEqual(r.returncode, 4)
        self.assertIn("2 sessions, the iteration cap", r.stdout)

    def test_a_dead_sessions_in_flight_marker_is_released_and_a_live_one_names_the_release(self):
        """2026-10-30, the owner: task 403's 85-minute run died with its session; the runner stopped "so nothing runs twice" and
        named no way out. The marker names the session's process now (the guard writes its pid): a dead session's marker is
        released by the runner itself and the task retries in the next session; a live one is real work — the runner stops and
        names `reef-run.py release <id>` for when the owner knows it is not running; `release` removes the marker."""
        gone = subprocess.Popen([sys.executable, "-c", "pass"]); gone.wait()
        mk = os.path.join(self.d, ".reef", "inflight")
        os.makedirs(mk, exist_ok=True)
        with open(os.path.join(mk, "403"), "w") as f:
            json.dump({"id": "403", "pid": gone.pid, "agent": "implementer"}, f)
        vk = os.path.join(self.d, ".reef", "verifying"); os.makedirs(vk, exist_ok=True)
        with open(os.path.join(vk, "404"), "w") as f:
            json.dump({"id": "404", "pid": gone.pid, "agent": "verifier"}, f)   # a verifier's marker is released the same way (the review)
        r = run(self.d, ["none:x", "stop:done"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(calls(self.d)), 2, "the next session ran: the markers were a dead session's")
        self.assertFalse(os.path.exists(os.path.join(mk, "403")))
        self.assertFalse(os.path.exists(os.path.join(vk, "404")))
        live = open(os.path.join(self.d, ".reef", "run", "live.log")).read()
        self.assertIn("released in-flight 403", live)
        with open(os.path.join(mk, "403"), "w") as f:
            json.dump({"id": "403", "pid": os.getpid(), "agent": "implementer"}, f)   # this test stands in for a live session
        open(os.path.join(self.d, ".fake-calls"), "w").write("")
        r = run(self.d, ["none:x", "stop:done"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(len(calls(self.d)), 1, "live work: nothing runs twice")
        self.assertIn("python3 scripts/reef-run.py release 403", r.stdout)
        r = run(self.d, [], "release", "403")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(mk, "403")), "release removes the marker")
        self.assertIn("403", r.stdout)
        self.assertEqual(run(self.d, [], "release", "403").returncode, 1, "nothing to release: says so")

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
        lock = os.path.join(self.d, ".reef", "run", "lock")
        open(lock, "w").write(str(os.getpid()))   # a runner is running: this process stands in for it
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
        env = dict(os.environ, PATH=os.path.join(self.d, ".bin") + os.pathsep + os.environ["PATH"], CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS="0", REEF_NOTIFY="0")
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


class NormalRound(unittest.TestCase):
    """2026-10-28 (the owner, after the first night: "so many locks and guardrails … stopping me from normal rounds"): the
    runner the owner starts IS the orchestrator — it takes a loop hold another session left (three night sessions burned on a
    dead desktop session's hold), it stops after two sessions that make no progress (the same wait twice), and every wait it
    prints names the ONE terminal command that answers it — never "open an interactive session"."""

    def setUp(self):
        self.d = project()
        self.assertEqual(run(self.d, ["probe-deny"], "probe").returncode, 0)
        open(os.path.join(self.d, ".fake-calls"), "w").write("")

    def test_the_runner_takes_a_hold_another_session_left(self):
        p = os.path.join(self.d, ".reef", "run", "orchestrator.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            json.dump({"session": "6ee3355f-2fe4-dead", "at": time.time(), "pid": 999999}, f)
        r = run(self.d, ["stop:done"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("taking over the loop held by session 6ee3355f", r.stdout)
        self.assertFalse(os.path.exists(p), "the dead session's hold is gone before the first session")
        # a live holder with a recent action keeps the loop: one orchestrator at a time, and the takeover is the owner's own command
        with open(p, "w") as f:
            json.dump({"session": "a1b2c3d4-live", "at": time.time(), "pid": os.getpid()}, f)
        open(os.path.join(self.d, ".fake-calls"), "w").write("")
        r = run(self.d, ["stop:done"])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("reef-loop.py unlock", r.stderr + r.stdout)
        self.assertEqual(calls(self.d), [], "no session started against a live holder")
        self.assertTrue(os.path.exists(p), "the live hold stands")
        # a live holder whose last action is old is stale: taken over
        with open(p, "w") as f:
            json.dump({"session": "a1b2c3d4-stale", "at": time.time() - 31 * 60, "pid": os.getpid()}, f)
        r = run(self.d, ["stop:done"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("taking over the loop held by session a1b2c3d4", r.stdout)

    def test_two_sessions_on_the_same_wait_stop_the_runner(self):
        r = run(self.d, ["wait:/clear requested — row 3 blocked, same handoff", "wait:/clear requested — row 3 blocked, same handoff", "stop:never"])
        self.assertEqual(r.returncode, 2, "no progress is a question for the owner, told to the desk — not a silent exit (2026-10-30)\n" + r.stdout + r.stderr)
        self.assertEqual(len(calls(self.d)), 2, "no third session when two in a row changed nothing")
        self.assertIn("no progress", r.stdout)
        q = open(os.path.join(self.d, ".reef", "questions.md")).read()
        self.assertIn("- row 3: the loop made no progress", q, "filed on the row the wait names, where the screen shows it and `reef answer 3` clears it")
        open(os.path.join(self.d, ".fake-calls"), "w").write("")
        r = run(self.d, ["wait:/clear requested — row 3 blocked, same handoff", "wait:/clear requested — row 3 blocked, same handoff", "stop:never"])
        self.assertEqual(r.returncode, 2)
        self.assertEqual(open(os.path.join(self.d, ".reef", "questions.md")).read().count("made no progress"), 1, "a restart on the same stuck wait: filed once, and the restart cleared the old notice first")
        open(os.path.join(self.d, ".fake-calls"), "w").write("")
        self.assertEqual(run(self.d, ["stop:done"]).returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "questions.md")), "a runner that starts and runs clears the notice: it has served")
        # a project with the queue script: the question goes through `reef-queue.py ask` (an issue too, on an issues queue); a refusal falls back to the line
        os.makedirs(os.path.join(self.d, "scripts"), exist_ok=True)
        stub = os.path.join(self.d, "scripts", "reef-queue.py")
        open(stub, "w").write("import json, sys\nopen('.ask-argv', 'a').write(json.dumps(sys.argv[1:]) + '\\n')\nsys.exit(int(open('.ask-rc').read()) if __import__('os').path.exists('.ask-rc') else 0)\n")
        open(os.path.join(self.d, ".fake-calls"), "w").write("")   # the notice is gone already: the last run cleared it
        r = run(self.d, ["wait:/clear requested — stuck", "wait:/clear requested — stuck"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        argv = json.loads(open(os.path.join(self.d, ".ask-argv")).read().splitlines()[-1])
        self.assertEqual(argv[0], "ask"); self.assertIn("no progress", argv[1]); self.assertIn("--recommended", argv)
        self.assertNotIn("--row", argv, "a wait that names no row: a row-less question")
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "questions.md")), "the queue filed it: no second line here")
        open(os.path.join(self.d, ".ask-rc"), "w").write("1"); open(os.path.join(self.d, ".fake-calls"), "w").write("")
        r = run(self.d, ["wait:/clear requested — stuck", "wait:/clear requested — stuck"])
        self.assertIn("no progress", open(os.path.join(self.d, ".reef", "questions.md")).read(), "the queue refused: the line is written here")
        open(os.path.join(self.d, ".fake-calls"), "w").write("")
        r = run(self.d, ["wait:/clear requested — step one", "wait:/clear requested — step two", "stop:done"])
        self.assertEqual(r.returncode, 0, "a different handoff is progress: " + r.stdout)
        self.assertEqual(len(calls(self.d)), 3)

    def test_watch_ends_with_the_runners_last_word(self):
        """2026-10-30, the owner: the runner stopped on his approval and `watch` sat on a dead tail, twice. When the runner is gone,
        watch prints what the run left (the wait block is in live.log now) and returns — 2 when the loop waits on the owner."""
        live = os.path.join(self.d, ".reef", "run", "live.log")
        lock = os.path.join(self.d, ".reef", "run", "lock")
        open(live, "w").write("08:16 s1 → Gate full (reef:mechanic)\n")
        open(lock, "w").write(str(os.getpid()))
        w = subprocess.Popen([sys.executable, RUN, "watch", "--repo", self.d], stdout=subprocess.PIPE, text=True)
        time.sleep(1.5)
        open(live, "a").write("08:20 s1 session ended: wait 'owner: row 7'\n08:20 s1 reef-run: waiting on you — owner: row 7\n")
        with open(os.path.join(self.d, ".reef", "loop.json"), "w") as f:
            json.dump({"active": True, "wait": "owner: row 7", "stop": None, "parked": None, "hashes": []}, f)
        os.unlink(lock)   # the runner ended
        try:
            out, _ = w.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            w.kill(); self.fail("watch kept tailing after the runner ended")
        self.assertEqual(w.returncode, 2, out)
        self.assertIn("waiting on you — owner: row 7", out)
        self.assertIn("the runner ended", out)
        self.assertIn("python3 scripts/reef", out.rsplit("the runner ended", 1)[1], "the pointer that is always true")
        r = subprocess.run([sys.executable, RUN, "watch", "--repo", self.d], capture_output=True, text=True, timeout=15)
        self.assertEqual(r.returncode, 2, "no runner: what the last run left, then out — never a dead tail")
        self.assertIn("waiting on you", r.stdout)
        self.assertIn("no runner is running", r.stdout, "it never ran under this watch: say so, not 'ended' (the review)")

    def test_the_desk_is_told_when_the_runner_waits_on_the_owner(self):
        """The runner's stop on the owner reaches the desk: macOS's notification center through osascript (notify-send elsewhere),
        best effort, one line; REEF_NOTIFY=0 keeps a suite or a server quiet."""
        crumb = os.path.join(self.d, ".notified")
        fake = os.path.join(self.d, ".bin", "osascript")
        open(fake, "w").write(f"#!/usr/bin/env python3\nimport sys\nopen({crumb!r}, 'w').write(' '.join(sys.argv[1:]))\n")
        os.chmod(fake, 0o755)
        env = dict(os.environ, PATH=os.path.join(self.d, ".bin") + os.pathsep + os.environ["PATH"], REEF_NOTIFY="1")
        open(os.path.join(self.d, ".fake-plan"), "w").write('wait:owner: row 7 needs you — say "yes" or \\no')
        r = subprocess.run([sys.executable, RUN, "--repo", self.d], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(crumb), "the desk was told")
        told = open(crumb).read()
        self.assertIn("row 7 needs you", told, "the wait itself, not only the title")
        self.assertIn('\\"yes\\"', told, "a quote in the wait is escaped for the AppleScript literal")
        self.assertIn("\\\\no", told, "a backslash too")
        os.unlink(crumb)
        open(os.path.join(self.d, ".fake-plan"), "w").write("wait:owner: row 7\x1b[2Kneeds you")
        r = subprocess.run([sys.executable, RUN, "--repo", self.d], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("\x1b", open(crumb).read(), "an escape in the wait never reaches the desk")
        self.assertNotIn("\x1b", open(os.path.join(self.d, ".reef", "run", "live.log")).read(), "nor live.log, which watch prints raw")
        os.unlink(crumb)
        open(os.path.join(self.d, ".fake-plan"), "w").write("wait:owner: row 7 needs you")
        subprocess.run([sys.executable, RUN, "--repo", self.d], capture_output=True, text=True, env=dict(env, REEF_NOTIFY="0"))
        self.assertFalse(os.path.exists(crumb), "REEF_NOTIFY=0: quiet")

    def test_an_owner_wait_names_the_command_that_answers_it(self):
        r = run(self.d, ["wait:owner: the gate: Approve plan demo-row at 0123456789abcdef?"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn('python3 scripts/reef-approval.py --owner "Approve plan demo-row at 0123456789abcdef?"', r.stdout)
        self.assertNotIn("interactive session", r.stdout)
        # 2026-10-30, the owner (twice): `watch` showed "session ended" and nothing more — the block with the commands went to
        # runner.out alone. The runner's last word is in live.log too, and names the screen that shows every wait
        live = open(os.path.join(self.d, ".reef", "run", "live.log")).read()
        self.assertIn("waiting on you", live)
        self.assertIn('python3 scripts/reef-approval.py --owner "Approve plan demo-row at 0123456789abcdef?"', live)
        self.assertIn("every wait at once, one key each: python3 scripts/reef", r.stdout, "the screen with every wait, named")
        open(os.path.join(self.d, ".reef", "questions.md"), "w").write("- row 12: share links in host logs? — recommended: accept\n")
        r = run(self.d, ["wait:owner: row 12 — share links?"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("reef-queue.py footnote", r.stdout, "a free question has a terminal answer too")
        self.assertIn("--row 12", r.stdout)

    def test_on_an_issues_queue_the_answer_is_reef_queue_answered(self):
        """2026-10-30, the current adoption: the loop filed #90–#93 as reef-question issues and the runner printed the footnote
        command, which closes no issue — the next session read the same four open questions and ended on the same wait. On
        `queue.home: issues` the command is `reef-queue.py answered <#> '<the recommended answer>'`; on a file queue the
        footnote carries the recommended answer too — no placeholder in either; the owner edits the words."""
        open(os.path.join(self.d, ".reef", "questions.md"), "w").write("- row 7: which way? — recommended: (a) comments only\n")
        r = run(self.d, ["wait:owner: row 7 — which way?"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("python3 scripts/reef-queue.py footnote '(a) comments only' --row 7", r.stdout)
        self.assertNotIn("<your answer>", r.stdout)
        open(os.path.join(self.d, ".reef", "config.json"), "w").write('{"gates": {"full": "true"}, "queue": {"home": "issues"}}')
        open(os.path.join(self.d, ".reef", "questions.md"), "w").write("- row 7 #90: which way? — recommended: (a) comments only\n"
                                                                       "- row 4 #91: where? — recommended: Batch 9\n")
        r = run(self.d, ["wait:owner: #90 (row 7 blocked) and #91 (row 4 grill)"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("python3 scripts/reef-queue.py answered 90 '(a) comments only'", r.stdout)
        self.assertIn("python3 scripts/reef-queue.py answered 91 'Batch 9'", r.stdout)
        self.assertNotIn("footnote", r.stdout, "a footnote closes no issue")
        # a line from before this change names no issue (the owner's four live questions): gh names it by the title ask gave it,
        # and when gh cannot, the wait still names the look — never a wait with no command (the review)
        open(os.path.join(self.d, ".reef", "questions.md"), "w").write("- row 7: which way? — recommended: (a) comments only\n- row -: a row-less one? — recommended: yes\n")
        gh = os.path.join(self.d, ".bin", "gh")
        open(gh, "w").write("#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps([{'number': 90, 'title': 'question: row 7: which way?'}]) if 'list' in sys.argv else '')\n")
        os.chmod(gh, 0o755)
        r = run(self.d, ["wait:owner: #90 (row 7)"])
        self.assertIn("python3 scripts/reef-queue.py answered 90 '(a) comments only'", r.stdout, "the number, from the open reef-question issues")
        self.assertIn('gh issue list --label reef-question --search "row -"', r.stdout, "a question gh did not name: the look, not silence")
        open(gh, "w").write("#!/bin/sh\nexit 1\n")
        r = run(self.d, ["wait:owner: #90 (row 7)"])
        self.assertIn('gh issue list --label reef-question --search "row 7"', r.stdout, "gh failing: the look, not silence")
        self.assertNotIn("answered 90", r.stdout)

    def test_a_decision_restarts_the_runner_that_stopped_on_it(self):
        """docs/design/owner-hands-off.md step 1 (2026-10-31): the runner stopped on the owner's decision; once the decision is
        recorded, `reef-run.py resume` starts it again in the same mode — unless it is running, a Claude session holds the loop
        (it continues itself), the loop is stopped or parked, the last run was a night (one approval), or REEF_NO_RESUME=1."""
        r = run(self.d, ["wait:owner: the gate: Approve plan demo-row at 0123456789abcdef?", "stop:done"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("starts again by itself", r.stdout, "the block says the runner resumes on the decision — nobody types --detach")
        rec = json.loads(open(os.path.join(self.d, ".reef", "run", "run.log")).read().splitlines()[-1])
        self.assertEqual(rec.get("mode"), "loop", "the run record names its mode, so resume knows the flags")
        env = dict(os.environ, PATH=os.path.join(self.d, ".bin") + os.pathsep + os.environ["PATH"], REEF_NOTIFY="0")
        env.pop("REEF_NO_RESUME", None)   # the suite sets it (tests/run.sh); this test is the one that resumes
        r = subprocess.run([sys.executable, RUN, "resume", "--repo", self.d], capture_output=True, text=True, env=dict(env, REEF_NO_RESUME="1"))
        self.assertEqual(r.returncode, 3); self.assertIn("REEF_NO_RESUME", r.stdout)
        with open(os.path.join(self.d, ".reef", "run", "orchestrator.json"), "w") as f:
            json.dump({"session": "live1234", "at": time.time(), "pid": os.getpid()}, f)   # an interactive session holds the loop
        r = subprocess.run([sys.executable, RUN, "resume", "--repo", self.d], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 3, r.stdout); self.assertIn("holds the loop", r.stdout)
        os.unlink(os.path.join(self.d, ".reef", "run", "orchestrator.json"))
        r = subprocess.run([sys.executable, RUN, "resume", "--repo", self.d], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("starts again", r.stdout)
        lock = os.path.join(self.d, ".reef", "run", "lock")
        for _ in range(200):   # the detached runner runs the fake's next step (stop:done) and ends
            if calls(self.d)[-1:] == ["stop:done"] and not os.path.exists(lock):
                break
            time.sleep(0.1)
        self.assertEqual(calls(self.d), ["wait:owner: the gate: Approve plan demo-row at 0123456789abcdef?", "stop:done"], "the resumed runner ran the next session")
        r = subprocess.run([sys.executable, RUN, "resume", "--repo", self.d], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 3, r.stdout); self.assertIn("stopped", r.stdout, "a stopped loop is not resumed: reef-loop.py start is the owner's word")
        # the reviews: the mode comes from guarded state, not run.log; a night is not resumed; the owner's stop is not undone; a failed child is a refusal
        open(os.path.join(self.d, ".reef", "loop.json"), "w").write('{"active": true, "wait": "owner: x", "stop": null, "parked": null, "hashes": []}')
        with open(os.path.join(self.d, ".reef", "run", "run.log"), "a") as f:
            f.write(json.dumps({"iteration": 9, "at": "2026-10-31T00:00:00Z", "wait": "owner: x", "in_flight": [], "mode": "autopilot", "stop_requested": False}) + "\n")
        with open(os.path.join(self.d, ".reef", "night", "last-mode.json"), "w") as f:
            json.dump({"mode": "night"}, f)
        r = subprocess.run([sys.executable, RUN, "resume", "--repo", self.d], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 3); self.assertIn("a night", r.stdout, "the guarded last mode wins over a forged run.log")
        with open(os.path.join(self.d, ".reef", "night", "last-mode.json"), "w") as f:
            json.dump({"mode": "autopilot"}, f)
        r = subprocess.run([sys.executable, RUN, "resume", "--repo", self.d], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 3, r.stdout); self.assertIn("not resuming", r.stdout); self.assertIn("standing contract", r.stdout, "autopilot without the contract: the child's refusal, not a false 'starts again'")
        with open(os.path.join(self.d, ".reef", "run", "run.log"), "a") as f:
            f.write(json.dumps({"iteration": 10, "at": "2026-10-31T00:01:00Z", "wait": "/clear requested", "in_flight": [], "mode": "loop", "stop_requested": True}) + "\n")
        r = subprocess.run([sys.executable, RUN, "resume", "--repo", self.d], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 3); self.assertIn("your stop", r.stdout, "the owner's stop is never undone by a decision")

    def test_a_missing_night_approval_names_the_two_commands(self):
        os.makedirs(os.path.join(self.d, ".reef", "night"), exist_ok=True)
        os.makedirs(os.path.join(self.d, "reef"), exist_ok=True)
        open(os.path.join(self.d, ".reef", "night", "contract.md"), "w").write("Rows: 1\n\n# Night contract — tonight\n")
        open(os.path.join(self.d, "reef", "owner.md"), "w").write("# The owner\n")
        r = run(self.d, ["stop:x"], "--night")
        self.assertEqual(r.returncode, 1)
        self.assertRegex(r.stderr + r.stdout, r'reef-approval\.py --owner "Approve night \d{4}-\d\d-\d\d at [0-9a-f]{16}\?"')
        self.assertNotIn("in Claude Code)", r.stderr + r.stdout)


FAKE_ROW = """import json, sys
row = sys.argv[sys.argv.index('state') + 1]
q = 'Approve plan kit-redesign at 0123456789abcdef?'
print(json.dumps({'row': row, 'state': 'approval', 'next': '/reef-plan ' + row,
                  'detail': 'the gate: ' + q + ' — in the terminal: python3 scripts/reef-approval.py --owner "' + q + '"'}))
"""


class TheRunnerSyncsTheScripts(unittest.TestCase):
    """2026-10-31, the owner's autopilot: the plugin clone moved on, the project's copies stayed behind, and an approval was
    refused on a stale reef-approval.py until the owner ran `reef update` by hand. Before each session the runner brings
    the copies Reef wrote to the plugin's, commits them alone, and restarts itself on its own new code; a copy edited in the
    project is the owner's question, never synced (the security review)."""

    def test_reefs_own_copies_are_synced_alone_an_edited_one_is_asked_and_the_runner_restarts_on_its_new_self(self):
        import shutil
        clone = tempfile.mkdtemp(prefix="reef-plugin-main.")
        subprocess.run(["git", "init", "-q", "-b", "main", clone], check=True)
        for sub_ in ("scripts", "templates", ".claude-plugin"):
            shutil.copytree(os.path.join(ROOT, sub_), os.path.join(clone, sub_), ignore=shutil.ignore_patterns("__pycache__"))
        git(clone, "add", "-A"); git(clone, "commit", "-qm", "plugin")
        d = project()
        git(d, "config", "user.email", "t@t"); git(d, "config", "user.name", "t")   # the runner's own commit reads it (CI has none)
        git(d, "add", "-A"); git(d, "commit", "-qm", "project")
        upd = subprocess.run([sys.executable, os.path.join(clone, "scripts", "reef-update.py"), "--repo", d, "--plugin", clone, "--dry-run"],
                             capture_output=True, text=True)
        init = subprocess.run([sys.executable, os.path.join(clone, "scripts", "reef-init.py"), "--root", d, "--plugin", clone], capture_output=True, text=True)
        self.assertEqual(init.returncode, 0, upd.stdout + init.stdout + init.stderr)
        git(d, "add", "-A"); git(d, "commit", "-qm", "reef installed")   # the project as `reef update` leaves it
        git(d, "checkout", "-q", "-b", "develop")   # the base reef-init configured: the sync commits there and nowhere else
        with open(os.path.join(d, "scripts", "reef-queue.py"), "a") as f:
            f.write("# the owner's own line\n")   # a copy edited in the project
        git(d, "commit", "-qam", "owner edit")
        write_ = lambda rel, text: open(os.path.join(d, rel), "w").write(text)
        write_("notes.txt", "staged, not Reef's\n"); git(d, "add", "notes.txt")
        for name in ("reef-run.py", "reef-approval.py", "reef-queue.py"):   # then the plugin moves on
            with open(os.path.join(clone, "scripts", name), "a") as f:
                f.write("# the plugin's next release\n")
        git(clone, "commit", "-qam", "next release")
        self.assertEqual(run(d, ["probe-deny"], "probe").returncode, 0)
        open(os.path.join(d, ".fake-calls"), "w").write("")
        open(os.path.join(d, ".fake-plan"), "w").write("wait:owner: approve row 12")
        os.makedirs(os.path.join(d, ".reef", "run", "jobs"), exist_ok=True)   # a restart state another process wrote: never honoured
        open(os.path.join(d, ".reef", "run", "jobs", ".restart"), "w").write(json.dumps({"pid": 999999, "started": "x", "i": 7, "owner_waits": 0, "tried": [], "plugin": "/tmp"}))
        env = dict(os.environ, PATH=os.path.join(d, ".bin") + os.pathsep + os.environ["PATH"], REEF_NOTIFY="0", CLAUDE_PLUGIN_ROOT=clone, REEF_RUN_RESTARTED='{"i": 7}')
        env.pop("REEF_CLAUDE", None)
        r = subprocess.run([sys.executable, os.path.join(d, "scripts", "reef-run.py"), "--repo", d], capture_output=True, text=True, env=env, timeout=600)
        live = open(os.path.join(d, ".reef", "run", "live.log")).read()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr + live)
        for name in ("reef-run.py", "reef-approval.py"):
            self.assertEqual(open(os.path.join(d, "scripts", name), "rb").read(), open(os.path.join(clone, "scripts", name), "rb").read(), name + "\n" + live[-1500:])
        self.assertIn("# the owner's own line", open(os.path.join(d, "scripts", "reef-queue.py")).read(), "an edited copy is never overwritten")
        self.assertNotIn("the plugin's next release", open(os.path.join(d, "scripts", "reef-queue.py")).read())
        shown = git(d, "show", "--name-only", "--format=%s", "HEAD").stdout.split("\n")
        self.assertTrue(shown[0].startswith("reef: scripts"), shown)
        self.assertEqual(sorted(x for x in shown[1:] if x), [".reef/init-manifest.json", "scripts/reef-approval.py", "scripts/reef-run.py"],
                         "Reef's synced copies and the manifest, nothing else")
        self.assertIn("A  notes.txt", git(d, "status", "--porcelain").stdout, "what else was staged stays staged, uncommitted")
        self.assertIn("scripts edited in this project, not synced (reef-queue.py)", live)
        self.assertIn("reef-queue.py", open(os.path.join(d, ".reef", "questions.md")).read(), "the edited copy is the owner's question")
        self.assertEqual(live.count("session started"), 2, "the runner said it twice: once before the sync, once as its new self\n" + live)
        self.assertEqual(calls(d), ["wait:owner: approve row 12"], "one session, after the sync — never one on the stale copies")
        self.assertFalse(os.path.exists(os.path.join(d, ".reef", "run", "lock")), "the restarted runner released its own lock")
        self.assertIn('"iteration": 1', open(os.path.join(d, ".reef", "run", "run.log")).read(), "the restart is the same run, not a new count")


class TheWaitAsksTheRow(unittest.TestCase):
    """2026-10-28, the owner's first round alone: the loop wrote its wait as "re-approve row 46's plan at <digest>" — not the exact
    question — so the runner printed the footnote command for what was an approval. The runner asks the row machine
    (reef-row.py state <row>) for each row the wait names, and prints the command the row's state carries."""

    def test_an_approval_wait_prints_the_rows_own_command(self):
        d = project()
        self.assertEqual(run(d, ["probe-deny"], "probe").returncode, 0)
        os.makedirs(os.path.join(d, "scripts"), exist_ok=True)
        with open(os.path.join(d, "scripts", "reef-row.py"), "w") as f:   # a row machine that says: row 46 is at the gate
            f.write(FAKE_ROW)
        r = run(d, ["wait:owner: re-approve row 46's plan at 0123456789abcdef (#77) so R03 can dispatch"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn('python3 scripts/reef-approval.py --owner "Approve plan kit-redesign at 0123456789abcdef?"', r.stdout)
        self.assertNotIn("reef-queue.py footnote", r.stdout, "an approval is not answered by a footnote")


class RunnerJobs(unittest.TestCase):
    """Step 3 of docs/design/owner-hands-off.md (2026-10-31: twice a session ended its turn while its own background converge ran on,
    the headless process waited for it and the runner for the process — forty idle minutes): a long command is a runner job, started
    detached by `reef-run.py job <name> -- <command>`; the session ends its turn; the runner waits for the job and the next session
    reads its result. And the loop's merge is pre-allowed where the config says the loop merges (auto mode refused it headless)."""

    def job(self, d, *args):
        return subprocess.run([sys.executable, RUN, "--repo", d, "job", *args], capture_output=True, text=True, cwd=d, env=dict(os.environ, REEF_NOTIFY="0"))

    def test_a_job_runs_detached_and_leaves_its_rc_and_log(self):
        d = project()
        t0 = time.time()
        r = self.job(d, "quick", "--", "sh", "-c", "sleep 1; echo hi; exit 3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertLess(time.time() - t0, 3.0, "job returns at once, not after the command")
        self.assertIn("job quick: started (pid", r.stdout); self.assertIn("end the turn", r.stdout)
        rec = json.load(open(os.path.join(d, ".reef", "run", "jobs", "quick.json")))
        self.assertEqual(rec["cmd"], ["sh", "-c", "sleep 1; echo hi; exit 3"]); self.assertTrue(alive(rec["pid"]), "the job's process runs")
        self.assertIn("running", self.job(d).stdout)
        r = self.job(d, "quick", "--", "true")
        self.assertEqual(r.returncode, 1); self.assertIn("still running", r.stdout + r.stderr, "one name, one job at a time")
        time.sleep(1.6)
        rec = json.load(open(os.path.join(d, ".reef", "run", "jobs", "quick.json")))
        self.assertEqual(rec["rc"], 3, rec); self.assertIn("ended", rec)
        self.assertIn("hi", open(os.path.join(d, ".reef", "run", "jobs", "quick.log")).read())
        self.assertIn("ended rc=3", self.job(d).stdout)
        for bad in (("Bad Name", "--", "true"), ("x",), ("x", "--")):
            self.assertEqual(self.job(d, *bad).returncode, 2, bad)

    def test_the_runner_waits_for_a_job_between_sessions_and_tells_the_next_one(self):
        d = project()
        import shutil
        os.makedirs(os.path.join(d, "scripts"))
        for n in ("reef-run.py", "reef_common.py"):   # the fake session starts the job through the project's own copy, as a real one would
            shutil.copy(os.path.join(ROOT, "scripts", n), os.path.join(d, "scripts", n))
        self.assertEqual(run(d, ["probe-deny"], "probe").returncode, 0); open(os.path.join(d, ".fake-calls"), "w").write(""); open(os.path.join(d, ".fake-prompt"), "w").write("")
        t0 = time.time()
        r = run(d, ["job:gate-4:3", "stop:done"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertGreaterEqual(time.time() - t0, 2.5, "the runner waited for the job before the next session")
        self.assertEqual(calls(d), ["job:gate-4:3", "stop:done"], "a job wait is not the owner's and not no-progress: the next session ran")
        prompts = open(os.path.join(d, ".fake-prompt")).read().splitlines()
        self.assertNotIn("JOBS DONE since", prompts[0]); self.assertIn("JOBS DONE since the last session", prompts[1]); self.assertIn("gate-4 rc=0", prompts[1]); self.assertIn("jobs/gate-4.log", prompts[1])
        live = open(os.path.join(d, ".reef", "run", "live.log")).read()
        self.assertIn("job gate-4: running", live); self.assertIn("jobs done: gate-4 rc=0", live)
        self.assertIn("LONG WORK IS THE RUNNER'S", prompts[0], "the headless prompt forbids a background shell and names the job verb")
        self.assertTrue(json.load(open(os.path.join(d, ".reef", "run", "jobs", "gate-4.json"))).get("reported"), "reported once, after the session read it")
        # a job that ends while no runner runs is reported by the NEXT run's first session (the wait runs before every session)
        self.assertEqual(self.job(d, "late", "--", "sh", "-c", "exit 5").returncode, 0); time.sleep(0.8)
        open(os.path.join(d, ".fake-prompt"), "w").write("")
        self.assertEqual(run(d, ["stop:again"]).returncode, 0)
        first = open(os.path.join(d, ".fake-prompt")).read().splitlines()[0]
        self.assertIn("JOBS DONE since the last session", first); self.assertIn("late rc=5", first)
        self.assertTrue(json.load(open(os.path.join(d, ".reef", "run", "jobs", "late.json"))).get("reported"))

    def test_the_loops_merge_is_pre_allowed_where_the_config_says_the_loop_merges(self):
        d = project()
        self.assertEqual(run(d, ["probe-deny"], "probe").returncode, 0)
        open(os.path.join(d, ".reef", "config.json"), "w").write('{"gates": {"full": "true"}, "merge": {"by": "loop"}}')
        self.assertEqual(run(d, ["stop:x"]).returncode, 0)
        argv = json.load(open(os.path.join(d, ".fake-argv")))
        self.assertIn("--allowedTools", argv); self.assertIn("Bash(gh pr merge:*)", argv)
        self.assertEqual([a for a in argv if a.startswith("Bash(")], ["Bash(gh pr merge:*)"], "the one command the classifier refused — a job line would pre-allow any command")
        open(os.path.join(d, ".reef", "config.json"), "w").write('{"gates": {"full": "true"}, "merge": {"by": "human"}}')
        self.assertEqual(run(d, ["stop:x"]).returncode, 0)
        self.assertNotIn("--allowedTools", json.load(open(os.path.join(d, ".fake-argv"))), "the owner merges: nothing pre-allowed")
        # the v3 default rule, unset merge.by: ci gates feature PRs and base ≠ release → the loop merges; base = release → the owner
        open(os.path.join(d, ".reef", "config.json"), "w").write('{"gates": {"full": "true"}, "ci": {"feature_gate": "ci"}, "branches": {"base": "develop", "release": "main"}}')
        self.assertEqual(run(d, ["stop:x"]).returncode, 0); self.assertIn("Bash(gh pr merge:*)", json.load(open(os.path.join(d, ".fake-argv"))))
        open(os.path.join(d, ".reef", "config.json"), "w").write('{"gates": {"full": "true"}, "ci": {"feature_gate": "ci"}, "branches": {"base": "main", "release": "main"}}')
        self.assertEqual(run(d, ["stop:x"]).returncode, 0); self.assertNotIn("--allowedTools", json.load(open(os.path.join(d, ".fake-argv"))))

    def test_the_owners_stop_ends_the_wait_and_leaves_the_job_running(self):
        d = project()
        self.assertEqual(run(d, ["probe-deny"], "probe").returncode, 0); open(os.path.join(d, ".fake-calls"), "w").write("")
        self.assertEqual(self.job(d, "long", "--", "sleep", "40").returncode, 0)
        pid = json.load(open(os.path.join(d, ".reef", "run", "jobs", "long.json")))["pid"]
        open(os.path.join(d, ".fake-plan"), "w").write("stop:never reached")
        env = dict(os.environ, PATH=os.path.join(d, ".bin") + os.pathsep + os.environ["PATH"], REEF_NOTIFY="0")
        env.pop("REEF_CLAUDE", None)
        p = subprocess.Popen([sys.executable, RUN, "--repo", d], cwd=d, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(2)
        open(os.path.join(d, ".reef", "run", "stop-request"), "w").write("x")   # what `reef-run.py stop` writes
        try:
            out, _ = p.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            p.kill(); self.fail("the runner kept waiting on the job after the owner's stop")
        self.assertEqual(p.returncode, 0, out); self.assertIn("stopped on the owner's request", out); self.assertIn("the job runs on", out)
        self.assertEqual(calls(d), [], "no session started"); self.assertTrue(alive(pid), "the job was left running, not killed")
        os.kill(pid, 15)


    def test_a_planted_record_names_nothing_and_a_dead_or_endless_job_is_reported(self):
        import importlib.machinery, importlib.util
        d = project()
        os.makedirs(os.path.join(d, ".reef", "run", "jobs"))
        loader = importlib.machinery.SourceFileLoader("reef_run_jobs", RUN); spec = importlib.util.spec_from_loader(loader.name, loader)
        mod = importlib.util.module_from_spec(spec); loader.exec_module(mod)
        # a record whose content names a path, a record with a command that is not a list: ignored — the name is the file's
        open(os.path.join(d, ".reef", "run", "jobs", "planted.json"), "w").write(json.dumps({"name": "../../review/forged", "cmd": ["true"], "rc": 0, "verdict": "GREEN", "log": "../../review/forged.json"}))
        open(os.path.join(d, ".reef", "run", "jobs", "Bad Name.json"), "w").write(json.dumps({"name": "x", "cmd": ["true"]}))
        open(os.path.join(d, ".reef", "run", "jobs", "str.json"), "w").write(json.dumps({"name": "str", "cmd": "rm -rf /"}))
        recs = mod.jobs(d)
        self.assertEqual([(j["name"], j["log"]) for j in recs], [("planted", os.path.join(".reef", "run", "jobs", "planted.log"))], "the file's name and the log it gives, nothing from the content")
        done = mod.wait_jobs(d, lambda t: None, os.path.join(d, "no-stop"))
        self.assertEqual([j["name"] for j in done], ["planted"]); self.assertFalse(os.path.exists(os.path.join(d, ".reef", "review")), "nothing written outside the job directory")
        mod.mark_reported(d, done)   # as the runner does once a session has read the note
        # the wrapper refuses to run outside the runner's own start (REEF_JOB), so a typed `_job-run` does nothing
        r = subprocess.run([sys.executable, RUN, "--repo", d, "_job-run", "typed", "--", "sh", "-c", "echo ran > typed.txt"], capture_output=True, text=True, cwd=d, env=dict(os.environ, REEF_NOTIFY="0"))
        self.assertEqual(r.returncode, 2); self.assertFalse(os.path.exists(os.path.join(d, "typed.txt")))
        # a job whose process died without a result is reported as died, not waited for twice
        open(os.path.join(d, ".reef", "run", "jobs", "gone.json"), "w").write(json.dumps({"name": "gone", "cmd": ["sleep", "9"], "pid": 999999, "started_ts": time.time() - 60}))
        done = mod.wait_jobs(d, lambda t: None, os.path.join(d, "no-stop"))
        self.assertEqual([(j["name"], j["rc"]) for j in done], [("gone", -1)]); self.assertIn("died", mod.jobs_note(done)); mod.mark_reported(d, done)
        # a job past loop.job_max_minutes is killed and reported
        open(os.path.join(d, ".reef", "config.json"), "w").write('{"gates": {"full": "true"}, "loop": {"job_max_minutes": 1}}')
        r = subprocess.run([sys.executable, RUN, "--repo", d, "job", "endless", "--", "sleep", "60"], capture_output=True, text=True, cwd=d, env=dict(os.environ, REEF_NOTIFY="0"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rec = json.load(open(os.path.join(d, ".reef", "run", "jobs", "endless.json"))); rec["started_ts"] = time.time() - 120; json.dump(rec, open(os.path.join(d, ".reef", "run", "jobs", "endless.json"), "w"))
        said = []
        done = mod.wait_jobs(d, said.append, os.path.join(d, "no-stop"))
        self.assertEqual([(j["name"], j["rc"]) for j in done], [("endless", 124)]); self.assertTrue(any("killed" in t for t in said)); self.assertIn("killed", mod.jobs_note(done))
        time.sleep(0.3); self.assertFalse(alive(rec["pid"]), "the job's process group was ended")



class WatchInsideASession(unittest.TestCase):
    """2026-10-31, the owner: "add reef-watch so I can see the log from inside Claude Code". A session's tool holds until a command
    returns, so `watch` gains two bounds: `--tail N` (how many of the last lines) and `--for S` (follow S seconds, then return and
    say the runner still runs; 0 returns at once). The terminal's `reef watch` stays unbounded. The skill names the bounded forms only."""

    def setUp(self):
        self.d = project()
        os.makedirs(os.path.join(self.d, ".reef", "run"), exist_ok=True)
        self.log = os.path.join(self.d, ".reef", "run", "live.log")
        open(self.log, "w").write("".join(f"21:{i:02d} s1 → step {i}\n" for i in range(30)))
        open(os.path.join(self.d, ".reef", "run", "lock"), "w").write(str(os.getpid()))   # a live runner

    def test_tail_and_for_bound_the_watch(self):
        t0 = time.time()
        r = subprocess.run([sys.executable, RUN, "watch", "--tail", "3", "--for", "0", "--repo", self.d], capture_output=True, text=True, timeout=20)
        self.assertLess(time.time() - t0, 5, "--for 0 returns at once, runner or not")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        body = [l for l in r.stdout.splitlines() if l.startswith("21:")]
        self.assertEqual(body, ["21:27 s1 → step 27", "21:28 s1 → step 28", "21:29 s1 → step 29"], "the last three lines only\n" + r.stdout)
        self.assertIn("the runner still runs", r.stdout); self.assertIn("watch --for", r.stdout, "the line that follows on is named")
        w = subprocess.Popen([sys.executable, RUN, "watch", "--tail", "1", "--for", "2", "--repo", self.d], stdout=subprocess.PIPE, text=True)
        time.sleep(0.5)
        with open(self.log, "a") as f:
            f.write("21:30 s1 ← step 30: GREEN\n")
        time.sleep(1.2)   # the last second of the window: its line is read on the way out (the review)
        with open(self.log, "a") as f:
            f.write("21:31 s1 ← step 31: GREEN\n")
        t0 = time.time()
        out, _ = w.communicate(timeout=20)
        self.assertLess(time.time() - t0, 4, "--for 2 returned when its seconds were up, with the runner alive")
        self.assertEqual(w.returncode, 0, out)
        self.assertIn("21:30 s1 ← step 30: GREEN", out, "a line written meanwhile was followed")
        self.assertIn("21:31 s1 ← step 31: GREEN", out, "a line written in the last second too")
        self.assertIn("the runner still runs", out)
        # a bad bound exits 1 (2 is the owner's wait, which a session reads); the bounds are watch's alone — a flag-only argv starts no run
        for bad in (["watch", "--for", "x"], ["watch", "--for", "inf"], ["watch", "--tail", "many"]):
            r = subprocess.run([sys.executable, RUN, *bad, "--repo", self.d], capture_output=True, text=True, timeout=20)
            self.assertEqual(r.returncode, 1, bad)
        r = subprocess.run([sys.executable, RUN, "--for", "100", "--repo", self.d], capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 1, "without the verb the flag is unknown: nothing runs\n" + r.stdout + r.stderr)
        self.assertIn("unknown argument", r.stdout + r.stderr); self.assertEqual(calls(self.d), [], "no session started")

    def test_the_skill_and_the_descriptions(self):
        skill = open(os.path.join(ROOT, "skills", "reef-watch", "SKILL.md"), encoding="utf-8").read()
        self.assertIn("name: reef-watch", skill)
        self.assertIn("watch --tail", skill); self.assertIn("--for", skill)
        self.assertRegex(skill, r"(?i)never .*without .*--for", "an unbounded watch holds the session's tool until the runner ends: the skill says never")
        run_skill = open(os.path.join(ROOT, "skills", "reef-run", "SKILL.md"), encoding="utf-8").read().split("---", 2)[1]
        self.assertIn("/reef-run autopilot", run_skill, "the owner looked for /reef:autopilot: the description names it")
        self.assertIn("autopilot", run_skill.split("argument-hint:", 1)[1].splitlines()[0])
        self.assertIn("/reef-watch", open(os.path.join(ROOT, "README.md"), encoding="utf-8").read())


class GraphModeIsForTheOwnersOwnSessions(unittest.TestCase):
    """2026-10-31, the owner: "does the autopilot have graph mode? why was it off, who turned it off?" — the live answer: a headless
    `claude -p` session has no Workflow tool ("The Workflow tool isn't available to me"), so graph mode is for the sessions the owner
    runs himself. The runner never probes the graph gate (every attempt would fail and cost a session), and the loop's tick picks chat
    mode under the runner whatever the gate says."""

    def test_the_runner_never_probes_the_graph_gate(self):
        d = project()
        r = run(d, ["probe-deny"], "probe")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(calls(d), ["probe-deny"], "one session: the headless gate; no graph probe")
        self.assertFalse(os.path.exists(os.path.join(d, ".reef", "graph")))
        open(os.path.join(d, ".fake-calls"), "w").write("")
        self.assertEqual(run(d, ["stop:done"]).returncode, 0)
        self.assertEqual(calls(d), ["stop:done"], "the runner's start probes nothing either")
        src = open(RUN, encoding="utf-8").read()
        self.assertNotIn("Workflow tool", src.split("def cmd_probe", 1)[1].split("def detach", 1)[0], "the runner asks no session for the Workflow tool")

    def test_the_loop_picks_chat_mode_under_the_runner_whatever_the_gate_says(self):
        import importlib.machinery, importlib.util
        loader = importlib.machinery.SourceFileLoader("reef_loop_for_graph_mode", os.path.join(ROOT, "scripts", "reef-loop.py"))
        spec = importlib.util.spec_from_loader(loader.name, loader); loop = importlib.util.module_from_spec(spec); loader.exec_module(loop)
        d = project()
        os.makedirs(os.path.join(d, ".reef", "graph"))
        json.dump({"ok": True}, open(os.path.join(d, ".reef", "graph", "gate.json"), "w"))
        cfg = {"graph": {"mode": "auto"}}
        old = os.environ.pop("REEF_RUNNER", None)
        try:
            self.assertEqual(loop.graph_mode(d, cfg), ("auto", True), "an interactive session with the gate proven: graph")
            os.environ["REEF_RUNNER"] = "1"
            self.assertEqual(loop.graph_mode(d, cfg), ("chat", False), "under the runner: chat, whatever the gate says (no Workflow tool headless)")
            os.environ.pop("REEF_RUNNER")
            os.makedirs(os.path.join(d, ".reef", "run"), exist_ok=True)
            open(os.path.join(d, ".reef", "run", "lock"), "w").write(str(os.getpid()))   # the runner's live lock says the same, env line or not
            self.assertEqual(loop.graph_mode(d, cfg), ("chat", False), "the live lock, not only the env line, means the runner")
            os.remove(os.path.join(d, ".reef", "run", "lock"))
            real = os.path.join(d, ".reef", "graph"); os.rename(real, real + "-elsewhere"); os.symlink(real + "-elsewhere", real)
            self.assertEqual(loop.graph_mode(d, cfg), ("auto", False), "a symlinked .reef/graph is not the probe's record")
        finally:
            os.environ.pop("REEF_RUNNER", None)
            if old is not None:
                os.environ["REEF_RUNNER"] = old
