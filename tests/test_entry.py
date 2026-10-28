"""scripts/reef — the owner's one entry point (2026-10-28: "the person opens the terminal, writes reef, sees a logo and the
options with a short description each"). The owner's verbs, one line each; the internal scripts under --all; every verb runs
the sibling script it names."""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(ROOT, "scripts", "reef")
OWNER_VERBS = ("status", "doctor", "run", "night", "watch", "stop", "setup", "update", "factory", "cost")


def reef(*args, cwd=None):
    env = dict(os.environ, PATH="/nonexistent-gh:" + os.environ["PATH"])
    return subprocess.run([sys.executable, ENTRY, *args], capture_output=True, text=True, cwd=cwd, env=env, timeout=120)


class EntryPoint(unittest.TestCase):
    def test_no_arguments_shows_the_banner_and_the_owners_verbs_with_a_line_each(self):
        r = reef()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Reef", r.stdout)
        for v in OWNER_VERBS:
            self.assertRegex(r.stdout, rf"(?m)^\s*{v}\b.*\S.*$", f"the verb {v} with a description")
        self.assertNotIn("reef-plan-check.py", r.stdout, "internal scripts are not the owner's menu")

    def test_all_lists_every_script_with_its_first_line(self):
        r = reef("--all")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for name in ("reef-plan-check.py", "reef-guard.py", "reef-setup.py", "reef-row.py"):
            self.assertIn(name, r.stdout)
        self.assertNotIn("Usage:", r.stdout.split("reef-plan-check.py")[1].splitlines()[0], "the line is the script's purpose, not its usage")

    def test_a_verb_runs_its_script_and_an_unknown_verb_is_refused(self):
        d = tempfile.mkdtemp(prefix="reef-entry.")
        subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
        os.makedirs(os.path.join(d, ".reef"))
        open(os.path.join(d, ".reef", "config.json"), "w").write('{"gates": {"full": "true"}}')
        r = reef("status", "--repo", d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("reef-run: not running", r.stdout)
        r = reef("doctor", "--repo", d)
        self.assertNotIn("Traceback", r.stdout + r.stderr, "a project never carries reef-doctor.py: the entry point runs the plugin's")
        self.assertNotIn("No such file", r.stdout + r.stderr)
        r = reef("nonsense")
        self.assertEqual(r.returncode, 2)
        self.assertIn("nonsense", r.stderr + r.stdout)


class UpdatePushes(unittest.TestCase):
    """2026-10-28: `reef update` committed the project's new scripts and said "done" without pushing them — the owner found the
    commit sitting local. The update pushes the base (`git push`), or says why it could not."""

    def test_the_update_pushes_the_commit_it_makes(self):
        src = open(ENTRY, encoding="utf-8").read()
        self.assertIn('["git", "push"', src)
        self.assertIn("reef update: pushed", src)
