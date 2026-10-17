"""reef-doctor and reef-update (0.7, usability plan A1): the screen names the state and the fix; the update is one command."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCTOR = os.path.join(ROOT, "scripts", "reef-doctor.py")
UPDATE = os.path.join(ROOT, "scripts", "reef-update.py")


def git(d, *a):
    return subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *a], capture_output=True, text=True)


def project():
    d = tempfile.mkdtemp(prefix="reef-doctor.")
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    os.makedirs(os.path.join(d, ".reef"))
    os.makedirs(os.path.join(d, "scripts"))
    os.makedirs(os.path.join(d, "reef"))
    with open(os.path.join(d, ".reef", "config.json"), "w") as f:
        json.dump({"branches": {"base": "main", "feature_prefix": "feat/"}, "paths": {"queue": "reef/queue.md"}}, f)
    with open(os.path.join(d, ".reef", "version"), "w") as f:
        f.write("0.6.0\n")
    with open(os.path.join(d, "reef", "queue.md"), "w") as f:
        f.write("# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 1 | a | | planned | 1 | |\n")
    # the project's copies: one identical, one behind
    with open(os.path.join(ROOT, "scripts", "reef-loop.py"), "rb") as a, open(os.path.join(d, "scripts", "reef-loop.py"), "wb") as b:
        b.write(a.read())
    with open(os.path.join(d, "scripts", "reef-queue.py"), "w") as f:
        f.write("# old copy\n")
    git(d, "add", "-A"); git(d, "commit", "-qm", "init")
    return d


def doctor(d, *a):
    env = dict(os.environ, PATH="/nonexistent-gh:" + os.environ["PATH"])
    return subprocess.run([sys.executable, DOCTOR, "--repo", d, "--plugin", ROOT, *a], capture_output=True, text=True, env=env)


def legacy_stamped_task(d):
    """A design task with Reviewer notes, stamped in the 0.6 form (the cut at ## Log) — what every stamp written before
    2026-10-18 looks like after the plugin upgrade."""
    import hashlib
    import re
    p = os.path.join(d, "reef", "features", "demo", "tasks", "001-t.md")
    os.makedirs(os.path.dirname(p))
    body = ("---\nid: 1\nfeature: demo\nstatus: pending\ncomplexity: design\neffort: medium\nblocked-by: []\nresources: []\n"
            "tier: design\nverify: judge\nattempts: 0\ndispatches: 0\nlast_failure_sig: \"\"\nadversarial-plan: STAMP\n---\n# 1\n\n"
            "## Scope\nthe defect\n\n## Acceptance Criteria\n- test_x goes red first\n\n## Reviewer notes\n- (A1) a note\n\n## Log\n")
    cut = body.split("## Log\n")[0]
    fm, rest = re.match(r"\A---\n(.*?\n)---\n(.*)", cut, re.S).groups()
    fm = re.sub(r"^(status|attempts|last_failure_sig|dispatches|adversarial-plan):.*\n", "", fm, flags=re.M)
    stamp = hashlib.sha1((fm + "---\n" + rest).encode("utf-8")).hexdigest()[:12]
    with open(p, "w") as f:
        f.write(body.replace("adversarial-plan: STAMP", f"adversarial-plan: {stamp}"))
    return p


class StampCheck(unittest.TestCase):
    def test_a_0_6_stamp_is_named_with_the_migrate_command_and_clears_after_it(self):
        # 2026-10-18: task 204's stamp read as "the plan changed" after the pull; nothing on the screen said why
        d = project()
        p = legacy_stamped_task(d)
        r = doctor(d)
        line = [l for l in r.stdout.splitlines() if l.startswith("WARN") and "stamp:" in l]
        self.assertEqual(len(line), 1, r.stdout)
        self.assertIn("0.6 adversarial-plan", line[0])
        self.assertIn("reef-adversarial reef/features/demo/tasks/001-t.md plan --migrate", line[0])
        m = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-adversarial"), p, "plan", "--migrate"], capture_output=True, text=True)
        self.assertEqual(m.returncode, 0, m.stderr)
        r = doctor(d)
        self.assertNotIn("stamp:", r.stdout)
        self.assertIn("stamps: 1 design/critical task(s) current", r.stdout)


class Doctor(unittest.TestCase):
    def test_names_scripts_behind_the_queue_home_and_the_fix(self):
        d = project()
        r = doctor(d)
        self.assertIn("scripts: 1 project script(s) differ from the plugin's (reef-queue.py)", r.stdout)
        self.assertIn("reef-update.py", r.stdout, "the fix is named on the same line")
        self.assertIn("version: project 0.6.0, plugin", r.stdout)
        self.assertIn("loop: inactive", r.stdout)
        self.assertIn("status page: not written yet", r.stdout)
        self.assertRegex(r.stdout, r"gh: not (authenticated|installed)")
        self.assertEqual(r.returncode, 0, "warnings are not failures")
        # a feature worktree carrying a queue edit: the one FAIL
        git(d, "worktree", "add", "-q", "-b", "feat/a", os.path.join(d, ".reef", "worktrees", "a"), "main")
        wt = os.path.join(d, ".reef", "worktrees", "a")
        with open(os.path.join(wt, "reef", "queue.md"), "a") as f:
            f.write("| 2 | b | 1 | found | 2 | |\n")
        git(wt, "add", "-A"); git(wt, "commit", "-qm", "queue on the feature")
        r = doctor(d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL queue: feat/a carries queue edits the base lacks", r.stdout)
        self.assertIn("checkout main -- reef/queue.md", r.stdout)
        self.assertIn("worktree: .reef/worktrees/a [feat/a] (feature)", r.stdout)

    def test_not_a_reef_project_exits_2(self):
        d = tempfile.mkdtemp(prefix="reef-doctor-none.")
        subprocess.run(["git", "init", "-q", d], check=True)
        self.assertEqual(doctor(d).returncode, 2)


class Update(unittest.TestCase):
    def test_refuses_a_plugin_clone_off_main_and_dry_runs_otherwise(self):
        d = project()
        # a fake plugin clone on a feature branch
        plugin = tempfile.mkdtemp(prefix="reef-plugin.")
        subprocess.run(["git", "init", "-q", "-b", "claude/x", plugin], check=True)
        os.makedirs(os.path.join(plugin, ".claude-plugin"))
        with open(os.path.join(plugin, ".claude-plugin", "plugin.json"), "w") as f:
            json.dump({"name": "reef", "version": "0.7.0"}, f)
        git(plugin, "add", "-A"); git(plugin, "commit", "-qm", "x")
        r = subprocess.run([sys.executable, UPDATE, "--repo", d, "--plugin", plugin, "--dry-run"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("is on `claude/x`, not main", r.stdout)
        # a clean clone on main with the real scripts and templates: no pull (dry), init in dry-run, the Claude Code commands printed
        import shutil
        clone = tempfile.mkdtemp(prefix="reef-plugin-main.")
        subprocess.run(["git", "init", "-q", "-b", "main", clone], check=True)
        shutil.copytree(os.path.join(ROOT, "scripts"), os.path.join(clone, "scripts"), ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(os.path.join(ROOT, "templates"), os.path.join(clone, "templates"))
        shutil.copytree(os.path.join(ROOT, ".claude-plugin"), os.path.join(clone, ".claude-plugin"))
        git(clone, "add", "-A"); git(clone, "commit", "-qm", "plugin")
        r = subprocess.run([sys.executable, UPDATE, "--repo", d, "--plugin", clone, "--dry-run"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("dry run: no pull", r.stdout)
        self.assertIn("/reload-plugins", r.stdout)


if __name__ == "__main__":
    unittest.main()
