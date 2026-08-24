"""Sabotage suite for scripts/reef-attempt: the cap must be reachable, the
signature guard must fire on the same failure (not on byte-identical text), and
every ambiguous input must fail CLOSED (exit 2), never silently pass."""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATTEMPT = os.path.join(ROOT, "scripts", "reef-attempt")


def make_task(d, name="007-demo.md", fm="id: 7\nstatus: pending\neffort: medium\nattempts: 0\n", body="# demo\n\n## Log\n"):
    p = os.path.join(d, name)
    with open(p, "w") as f:
        f.write(f"---\n{fm}---\n{body}")
    return p


def run(*args):
    return subprocess.run([sys.executable, ATTEMPT, *args], capture_output=True, text=True)


class Attempt(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="reef-attempt-test.")

    def test_clean_dispatch_prints_header(self):
        p = make_task(self.dir)
        r = run(p)
        self.assertEqual(r.returncode, 0)
        self.assertIn("dispatch: model=opus effort=medium attempt=1/3", r.stdout)
        self.assertIn("REEF-TASK:", r.stdout)

    def test_effort_base_from_task_then_escalates(self):
        p = make_task(self.dir, fm="id: 7\nstatus: pending\neffort: low\nattempts: 0\n")
        self.assertIn("effort=low", run(p).stdout)
        run(p, "AssertionError: boom")
        self.assertIn("effort=high", run(p).stdout)

    def test_cap_blocks_on_third_fail(self):
        p = make_task(self.dir)
        self.assertEqual(run(p, "fail one").returncode, 0)
        self.assertEqual(run(p, "fail two").returncode, 0)
        r = run(p, "fail three")
        self.assertEqual(r.returncode, 2)
        self.assertIn("retry cap 3", r.stderr)
        self.assertIn("status: blocked", open(p).read())

    def test_same_failure_twice_blocks(self):
        p = make_task(self.dir)
        run(p, "AssertionError: expected 401 got 200")
        r = run(p, "AssertionError: expected 401 got 200")
        self.assertEqual(r.returncode, 2)
        self.assertIn("same failure signature twice", r.stderr)

    def test_signature_normalized_across_noise(self):
        # same failure, different line number / timing / whitespace -> still "twice"
        p = make_task(self.dir)
        run(p, "tests/test_x.py:17: AssertionError: expected 401 got 200  (0.42s)")
        r = run(p, "tests/test_x.py:19:  AssertionError: Expected 401 got 200 (0.57s)")
        self.assertEqual(r.returncode, 2, f"normalization failed: {r.stdout} {r.stderr}")

    def test_different_failure_not_repeated(self):
        p = make_task(self.dir)
        run(p, "AssertionError: expected 401 got 200")
        r = run(p, "TypeError: cannot unpack None")
        self.assertEqual(r.returncode, 0)

    def test_human_reset_not_burned_by_stale_sig(self):
        # the round-2 scenario: block, human resets attempts/status but the Log keeps
        # history; the FIRST fail of the fresh round must not be "same failure twice"
        p = make_task(self.dir)
        run(p, "AssertionError: boom")
        run(p, "AssertionError: boom")           # blocked (repeated)
        text = open(p).read().replace("status: blocked", "status: pending").replace("attempts: 2", "attempts: 0")
        open(p, "w").write(text)                 # human resets, but leaves last_failure_sig stale
        r = run(p, "AssertionError: boom")
        self.assertEqual(r.returncode, 0, f"stale sig burned the fresh round: {r.stderr}")

    def test_body_keys_never_touched(self):
        # K5: a 'last_failure_sig:' line inside ## Log is history, not state
        body = "# demo\n\n## Log\nlast_failure_sig: deadbeefdead\nstatus: was blocked once\n"
        p = make_task(self.dir, body=body)
        r = run(p, "some new failure")
        self.assertEqual(r.returncode, 0)
        text = open(p).read()
        self.assertIn("last_failure_sig: deadbeefdead", text)   # body line untouched
        fm = text.split("---\n")[1]
        self.assertIn("last_failure_sig: ", fm)                  # state landed in frontmatter

    def test_no_frontmatter_fails_closed(self):
        p = os.path.join(self.dir, "no-fm.md")
        open(p, "w").write("# just a doc\n")
        r = run(p, "failure")
        self.assertEqual(r.returncode, 2)
        self.assertIn("frontmatter", r.stderr)

    def test_empty_failure_arg_fails_closed(self):
        p = make_task(self.dir)
        r = run(p, "")
        self.assertEqual(r.returncode, 2, "an empty failure arg must not be laundered into a dispatch")

    def test_missing_file_fails_closed(self):
        r = run(os.path.join(self.dir, "ghost.md"))
        self.assertEqual(r.returncode, 2)

    def test_non_integer_attempts_fails_closed(self):
        p = make_task(self.dir, fm="id: 7\nstatus: pending\nattempts: banana\n")
        self.assertEqual(run(p).returncode, 2)

    def test_negative_attempts_fails_closed(self):
        p = make_task(self.dir, fm="id: 7\nstatus: pending\nattempts: -5\n")
        self.assertEqual(run(p).returncode, 2)

    def test_dispatch_path_enforces_cap_too(self):
        p = make_task(self.dir, fm="id: 7\nstatus: pending\nattempts: 3\n")
        r = run(p)
        self.assertEqual(r.returncode, 2, "attempts>=cap with status!=blocked must still refuse dispatch")

    def test_cap_flag_and_config_cap(self):
        p = make_task(self.dir, fm="id: 7\nstatus: pending\nattempts: 4\n")
        self.assertEqual(run(p).returncode, 2)
        self.assertEqual(run("--cap", "5", p).returncode, 0)
        os.makedirs(os.path.join(self.dir, ".reef"), exist_ok=True)
        open(os.path.join(self.dir, ".reef", "config.json"), "w").write('{"caps": {"attempts": 6}}')
        self.assertEqual(run(p).returncode, 0)   # config raises the cap

    def test_blocked_status_refuses_dispatch(self):
        p = make_task(self.dir, fm="id: 7\nstatus: blocked\nattempts: 1\n")
        self.assertEqual(run(p).returncode, 2)


if __name__ == "__main__":
    unittest.main()
