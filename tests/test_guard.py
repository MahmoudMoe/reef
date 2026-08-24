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
    # bypass spellings the tokenizer must catch
    'git commit -anm "x"',                                  # bundled short flags
    'git -c core.hookspath=/dev/null commit -m x',          # case games
    'git config CORE.HOOKSPATH /tmp/nothing',
    'git config --global core.hooksPath /dev/null',
    'git config --unset core.hooksPath',
    'GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x',
    'cd /tmp && git commit -n -m x',                        # behind an operator
    'git merge --no-verify feature',
    'rm -rf .githooks',
    'mv .git/hooks/pre-commit /tmp/',
    'chmod -x .githooks/pre-commit',
    'chmod 000 .githooks',
    'git commit -m "x" --no-verify || true',
    # round-2 findings: shapes the first guard missed
    'git commit -m x\ngit commit -n -m y',                  # newline-separated second command
    'sh -c "git commit -n -m x"',                           # shell wrapper payload
    'bash -c "git commit --no-verify -m x"',
    'eval git commit -n -m x',
    'git --config-env core.hooksPath=EVIL commit -m x',     # space form of --config-env
    'git --config-env=core.hooksPath=EVIL commit -m x',     # glued form
    # round-3 findings: shapes the second guard missed
    'nohup git commit -n -m x',                             # prefix word hides the head
    'env GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x',
    'nice -n 5 git commit --no-verify -m x',
    'chmod ugo+r,ugo-x .githooks/pre-commit',               # '+' present but strips exec
    'chmod u=rw .githooks/pre-commit',                      # '=' can strip exec too
    'bash -lc "git commit -n -m x"',                        # bundled -c flag
    'git commit -m x \\\n--no-verify',                      # backslash continuation
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
    'echo hooksPath is documented in README.md',            # bare word in a value
    'ls -la',
    # round-2 findings: false positives the first guard would have produced
    'chmod +x .githooks/pre-commit .githooks/pre-merge-commit',   # reef-init's own install step
    'git merge -n topic',                                   # merge -n is --no-stat, not --no-verify
    'git push --no-verify',                                 # no pre-push hook exists to bypass
    'git config core.hooksPathological x',                  # not the hooksPath key
    'rm not.githooksish.txt',                               # substring, not a path component
    'git commit -m fix -- -n',                              # after -- it is a pathspec
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

    def test_denied_dispatch_never_bumps_odometer(self):
        p = make_task(self.dir, status="blocked", dispatches=2)
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2)
        with open(p) as f:
            self.assertIn("dispatches: 2", f.read())   # unchanged: a denial costs nothing

    def test_path_with_spaces(self):
        make_task(self.dir, name="008-two words.md")
        r = dispatch(self.dir, "REEF-TASK: tasks/008-two words.md\nimplement")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_crlf_prompt_accepted(self):
        # round-3: a CRLF prompt left '\r' glued to the path and false-denied
        make_task(self.dir)
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\r\nimplement")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_negative_dispatches_denied(self):
        # round-3: a negative odometer disabled the runaway backstop
        make_task(self.dir, dispatches=-999)
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2)
        self.assertIn("negative", r.stderr)

    def test_duplicate_status_key_first_wins(self):
        # round-3: guard read the LAST duplicate key while reef-attempt reads the FIRST
        p = make_task(self.dir, status="blocked", extra="status: pending\n")
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2, "first occurrence (blocked) must win in the guard too")

    def test_absolute_path_accepted(self):
        p = make_task(self.dir)
        r = dispatch("/somewhere/else", f"REEF-TASK: {p}\nimplement")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_non_utf8_task_fails_closed(self):
        p = make_task(self.dir)
        with open(p, "ab") as f:
            f.write(b"\xff\xfe garbage")
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2, "an unreadable task file must DENY, never crash-allow")

    def _stamped_repo(self):
        """A real git repo with a full valid plan and a written stamp."""
        import shutil
        import subprocess as sp
        d = self.dir
        sp.run(["git", "init", "-q", "-b", "main", d], check=True)
        os.makedirs(os.path.join(d, "tasks", "done"), exist_ok=True)
        os.makedirs(os.path.join(d, "scripts"), exist_ok=True)
        os.makedirs(os.path.join(d, ".reef"), exist_ok=True)
        with open(os.path.join(d, ".reef", "config.json"), "w") as f:
            f.write('{"gates": {"test": "true"}}')
        with open(os.path.join(d, "CLAUDE.md"), "w") as f:
            f.write("# demo brief\n")
        with open(os.path.join(d, "tasks", "007-demo.md"), "w") as f:
            f.write("---\nid: 7\nfeature: demo\nstatus: pending\ncomplexity: mech\n"
                    "effort: medium\nblocked-by: []\nverify: gate-only\nattempts: 0\n"
                    "dispatches: 0\nlast_failure_sig: \"\"\n---\n# 7\n\n## Scope\nx\n\n"
                    "## Acceptance Criteria\n- test_demo_works goes red first\n\n## Log\n")
        shutil.copy(os.path.join(ROOT, "scripts", "reef-plan-check.py"),
                    os.path.join(d, "scripts", "reef-plan-check.py"))
        r = sp.run([sys.executable, os.path.join(d, "scripts", "reef-plan-check.py"), d],
                   capture_output=True, text=True)
        assert r.returncode == 0, f"fixture plan must pass plan-check:\n{r.stdout}"
        return d

    def test_stamp_match_allows_and_stale_denies(self):
        d = self._stamped_repo()
        r = dispatch(d, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 0, f"fresh stamp must allow: {r.stderr}")
        # the guard's own odometer bump must NOT stale the stamp
        r = dispatch(d, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 0, f"odometer bump staled the stamp: {r.stderr}")
        # a real plan edit must deny
        p = os.path.join(d, "tasks", "007-demo.md")
        with open(p) as f:
            t = f.read()
        with open(p, "w") as f:
            f.write(t.replace("## Scope\nx", "## Scope\nsneaky edit"))
        r = dispatch(d, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2)
        self.assertIn("stamp", r.stderr)

    def test_missing_stamp_denied(self):
        import shutil
        make_task(self.dir)
        os.makedirs(os.path.join(self.dir, "scripts"), exist_ok=True)
        import subprocess as sp
        sp.run(["git", "init", "-q", "-b", "main", self.dir], check=True)
        shutil.copy(os.path.join(ROOT, "scripts", "reef-plan-check.py"),
                    os.path.join(self.dir, "scripts", "reef-plan-check.py"))
        os.makedirs(os.path.join(self.dir, ".reef"), exist_ok=True)
        with open(os.path.join(self.dir, ".reef", "config.json"), "w") as f:
            f.write('{"gates": {"test": "true"}}')
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2)
        self.assertIn("stamp", r.stderr)


if __name__ == "__main__":
    unittest.main()
