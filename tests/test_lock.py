"""One orchestrator at a time (0.7.1, the owner's go 2026-10-24): two Claude sessions ran one project's loop, a terminal
one and a background one forked from an older conversation, and collided on develop. The first main session that
dispatches an agent or writes the loop's state holds the project; another is refused while the holder acted in the last
30 minutes. `reef-loop.py wait` and `stop` release it (the /clear hand-over), `reef-loop.py unlock` is the owner's
takeover, and the runner releases the hold of a session it ran."""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, "scripts", "reef-guard.py")
LOOP = os.path.join(ROOT, "scripts", "reef-loop.py")


class OneOrchestrator(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-lock.")
        subprocess.run(["git", "init", "-q", "-b", "main", self.d], check=True)
        os.makedirs(os.path.join(self.d, ".reef"))
        with open(os.path.join(self.d, ".reef", "config.json"), "w") as f:
            json.dump({"gates": {"full": "true"}}, f)
        self.lock = os.path.join(self.d, ".reef", "run", "orchestrator.json")

    def guard(self, session, cmd="python3 scripts/reef-loop.py tick", **extra):
        payload = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": self.d, "session_id": session, **extra}
        return subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True)

    def loop(self, *args):
        return subprocess.run([sys.executable, LOOP, *args, "--repo", self.d], capture_output=True, text=True)

    def test_a_second_session_is_refused_while_the_first_holds_the_project(self):
        self.assertEqual(self.guard("aaaa1111").returncode, 0)
        self.assertEqual(json.load(open(self.lock))["session"], "aaaa1111")
        r = self.guard("bbbb2222")
        self.assertEqual(r.returncode, 2)
        self.assertIn("another Claude session (aaaa1111", r.stderr)
        self.assertIn("reef-loop.py unlock", r.stderr)
        self.assertEqual(self.guard("bbbb2222", "gh pr merge 7 --squash").returncode, 2, "a merge is a loop write too")
        self.assertEqual(self.guard("bbbb2222", "git status").returncode, 0, "reading is anyone's")
        self.assertEqual(self.guard("bbbb2222", agent_id="sub-1").returncode, 0, "a subagent belongs to its own session")
        self.assertEqual(self.guard("aaaa1111").returncode, 0, "the holder keeps going")

    def test_wait_and_unlock_release_and_an_old_hold_is_taken_over(self):
        self.guard("aaaa1111")
        self.assertEqual(self.loop("wait", "/clear requested").returncode, 0)
        self.assertFalse(os.path.exists(self.lock), "the /clear hand-over releases the project")
        self.assertEqual(self.guard("bbbb2222").returncode, 0, "the next session starts at once")
        r = self.loop("unlock")
        self.assertEqual(r.returncode, 0)
        self.assertIn("bbbb2222", r.stdout)
        self.assertEqual(self.guard("cccc3333").returncode, 0, "the owner took over")
        with open(self.lock, "w") as f:
            json.dump({"session": "cccc3333", "at": time.time() - 31 * 60}, f)
        self.assertEqual(self.guard("dddd4444").returncode, 0, "a hold idle for more than 30 minutes is taken over")

    def test_the_runner_releases_the_hold_of_a_session_it_ran(self):
        loader = importlib.machinery.SourceFileLoader("reef_run", os.path.join(ROOT, "scripts", "reef-run.py"))
        spec = importlib.util.spec_from_loader("reef_run", loader)
        run = importlib.util.module_from_spec(spec)
        loader.exec_module(run)
        self.guard("aaaa1111")
        run.release_hold(self.d, "zzzz9999")
        self.assertTrue(os.path.exists(self.lock), "another session's hold is not the runner's to drop")
        run.release_hold(self.d, "aaaa1111")
        self.assertFalse(os.path.exists(self.lock))


if __name__ == "__main__":
    unittest.main()
