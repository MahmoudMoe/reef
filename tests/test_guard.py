"""Sabotage suite for scripts/reef-guard.py.

Every DENY case here is a bypass that MUST be caught (the gate shown red), and
every ALLOW case is a legitimate command that MUST NOT be blocked (no false
positives — a guard that blocks reef-init's own install is a self-deadlock).
Zero external deps: python3 -m unittest discover tests
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, "scripts", "reef-guard.py")


def run_guard(payload):
    return subprocess.run([sys.executable, GUARD], input=json.dumps(payload),
                          capture_output=True, text=True)


def bash(cmd):
    return run_guard({"tool_name": "Bash", "tool_input": {"command": cmd}})


DENY_BASH = [
    # the colleague's original table — the exact spellings that shamed v0.2.0
    'git commit -m "x" --no-verify',
    'git commit -n -m "x"',
    'git -c core.hooksPath=/dev/null commit -m "x"',
    'git config core.hooksPath /dev/null',
    'git --no-pager commit --no-verify -m "x"',
    # new bypass spellings the tokenizer must catch
    'git commit -anm "x"',                                  # bundled short flags
    'git -c core.hookspath=/dev/null commit -m x',          # case games
    'git config CORE.HOOKSPATH /tmp/nothing',
    'git config --global core.hooksPath /dev/null',
    'git config --unset core.hooksPath',
    'GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x',
    'cd /tmp && git commit -n -m x',                        # behind an operator
    'git push --no-verify',
    'git merge --no-verify feature',
    'rm -rf .githooks',
    'mv .git/hooks/pre-commit /tmp/',
    'chmod -x .githooks/pre-commit',
    'git commit -m "x" --no-verify || true',
]

ALLOW_BASH = [
    'git commit -m "x"',
    'git commit -am "regular commit"',
    'git commit --amend --no-edit',                         # --amend has n but not as a short flag
    'git commit -m "docs: explain why --no-verify is forbidden"',   # value, not flag
    'git config core.hooksPath .githooks',                  # reef-init's own install
    'git config --get core.hooksPath',                      # read-only query
    'git config --list',
    'git log --oneline -n 5',                               # -n belongs to log, not commit
    'git checkout -b feat/x && git commit -m "y"',
    'echo hooksPath is documented in README.md',            # hmm: mentions the word only
    'ls -la',
]


class BashGuard(unittest.TestCase):
    def test_denies_bypasses(self):
        for cmd in DENY_BASH:
            with self.subTest(cmd=cmd):
                r = bash(cmd)
                self.assertEqual(r.returncode, 2, f"NOT DENIED: {cmd!r}\nstderr: {r.stderr}")
                self.assertIn("reef-guard DENY", r.stderr)

    def test_allows_legitimate(self):
        for cmd in ALLOW_BASH:
            with self.subTest(cmd=cmd):
                r = bash(cmd)
                self.assertEqual(r.returncode, 0, f"FALSE POSITIVE: {cmd!r}\nstderr: {r.stderr}")

    def test_unparseable_bypass_denied_innocent_allowed(self):
        self.assertEqual(bash('git commit --no-verify -m "unbalanced').returncode, 2)
        self.assertEqual(bash('echo "unbalanced').returncode, 0)

    def test_garbage_stdin_allows(self):
        r = subprocess.run([sys.executable, GUARD], input="not json", capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)


def make_task(dirpath, name="007-demo.md", status="pending", attempts=0, dispatches=0, extra=""):
    p = os.path.join(dirpath, "tasks", name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(f"---\nid: 7\nfeature: demo\nstatus: {status}\nattempts: {attempts}\n"
                f"dispatches: {dispatches}\n{extra}---\n# demo\n\n## Log\n")
    return p


def dispatch(cwd, prompt, subagent="reef:implementer"):
    return run_guard({"tool_name": "Task", "cwd": cwd,
                      "tool_input": {"subagent_type": subagent, "prompt": prompt}})


class DispatchGuard(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="reef-guard-test.")

    def test_no_header_denied(self):
        r = dispatch(self.dir, "implement the thing please")
        self.assertEqual(r.returncode, 2)
        self.assertIn("REEF-TASK", r.stderr)

    def test_missing_file_denied(self):
        r = dispatch(self.dir, "REEF-TASK: tasks/999-ghost.md\nimplement")
        self.assertEqual(r.returncode, 2)

    def test_blocked_denied(self):
        make_task(self.dir, status="blocked")
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked", r.stderr)

    def test_at_cap_denied(self):
        make_task(self.dir, attempts=3)
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2)
        self.assertIn("retry cap", r.stderr)

    def test_odometer_backstop_denies_runaway(self):
        # the K4 scenario: a model that never records failures re-dispatches forever.
        # The guard itself advances dispatches:; at 2x cap it trips regardless.
        p = make_task(self.dir)
        for i in range(6):
            r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
            self.assertEqual(r.returncode, 0, f"dispatch {i+1} wrongly denied: {r.stderr}")
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2, "7th dispatch with zero recorded failures must trip the backstop")
        self.assertIn("runaway", r.stderr)
        with open(p) as f:
            self.assertIn("dispatches: 6", f.read())

    def test_odometer_written_to_frontmatter_only(self):
        p = make_task(self.dir)
        dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        text = open(p).read()
        fm = text.split("---\n")[1]
        self.assertIn("dispatches: 1", fm)

    def test_non_implementer_ignored(self):
        r = dispatch(self.dir, "anything", subagent="reef:verifier")
        self.assertEqual(r.returncode, 0)

    def test_stale_stamp_denied(self):
        # a repo with reef-plan-check installed and NO stamp -> dispatch must be denied
        import shutil
        make_task(self.dir)
        os.makedirs(os.path.join(self.dir, "scripts"), exist_ok=True)
        os.makedirs(os.path.join(self.dir, ".reef"), exist_ok=True)
        with open(os.path.join(self.dir, ".reef", "config.json"), "w") as f:
            f.write("{}")
        shutil.copy(os.path.join(ROOT, "scripts", "reef-plan-check.py"),
                    os.path.join(self.dir, "scripts", "reef-plan-check.py"))
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2)
        self.assertIn("stamp", r.stderr)


if __name__ == "__main__":
    unittest.main()
