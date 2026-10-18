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
        self.assertIn("001-t.md in . carries a 0.6 adversarial-plan", line[0], "the line names its checkout: a task worktree holds the same file")
        self.assertIn(f"python3 {os.path.join(ROOT, 'scripts', 'reef-adversarial')} reef/features/demo/tasks/001-t.md plan --migrate", line[0],
                      "the plugin's copy, not the checkout's (a worktree's scripts/ lags the base)")
        m = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-adversarial"), p, "plan", "--migrate"], capture_output=True, text=True)
        self.assertEqual(m.returncode, 0, m.stderr)
        r = doctor(d)
        self.assertNotIn("stamp:", r.stdout)
        self.assertIn("stamps: 1 design/critical task(s) current", r.stdout)


class LegacyRecords(unittest.TestCase):
    def test_a_0_6_form_record_is_named_with_the_migrate_command(self):
        d = project()
        p = legacy_stamped_task(d)
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-adversarial"), p, "plan", "--migrate"], capture_output=True, text=True)
        with open(os.path.join(d, "reef", "features", "demo", "SPEC.md"), "w") as f:
            f.write("# demo\nRow: 1\n")
        pc = os.path.join(ROOT, "scripts", "reef-plan-check.py")
        old = subprocess.run([sys.executable, pc, d, "--legacy-digest", "--feature", "demo"], capture_output=True, text=True).stdout.split()[-1]
        new = subprocess.run([sys.executable, pc, d, "--digest", "--feature", "demo"], capture_output=True, text=True).stdout.split()[-1]
        os.makedirs(os.path.join(d, "tasks"), exist_ok=True)
        with open(os.path.join(d, "tasks", ".plan-review.json"), "w") as f:
            json.dump({"features": {"demo": new}, "checks": 1, "planned_under": {"demo": "0.6.0"}}, f)
        os.makedirs(os.path.join(d, ".reef", "approvals"))
        with open(os.path.join(d, ".reef", "approvals", "demo.json"), "w") as f:
            json.dump({"digest16": old[:16], "approved_at": "2026-10-17T21:14:28Z"}, f)
        r = doctor(d)
        line = [l for l in r.stdout.splitlines() if "records:" in l]
        self.assertEqual(len(line), 1, r.stdout)
        self.assertTrue(line[0].startswith("WARN"), line[0])
        self.assertIn("demo in . carry the 0.6 digest form", line[0])
        self.assertIn(f"python3 {pc} . --migrate-records --feature demo", line[0])
        # a closed feature (every task under done/) is history nothing reads: 2026-10-18 row 1 was listed in five checkouts
        os.makedirs(os.path.join(d, "reef", "features", "demo", "tasks", "done"))
        os.rename(p, os.path.join(d, "reef", "features", "demo", "tasks", "done", "001-t.md"))
        r = doctor(d)
        self.assertNotIn("WARN records:", r.stdout, r.stdout)


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

    def test_a_pull_that_changes_reef_update_runs_the_new_copy(self):
        # 2026-10-18: the fix to reef-update's commit filter (#55) ran old on the trial's next pull — the process is
        # the copy loaded before the pull. The pull changed the file → the new copy runs, once.
        import shutil
        d = project()
        with open(os.path.join(d, "package.json"), "w") as f:
            json.dump({"name": "demo", "scripts": {"test": "true"}}, f)
        git(d, "add", "-A"); git(d, "commit", "-qm", "pkg")
        clone = tempfile.mkdtemp(prefix="reef-plugin-main.")
        subprocess.run(["git", "init", "-q", "-b", "main", clone], check=True)
        for sub in ("scripts", "templates", ".claude-plugin"):
            shutil.copytree(os.path.join(ROOT, sub), os.path.join(clone, sub), ignore=shutil.ignore_patterns("__pycache__"))
        git(clone, "add", "-A"); git(clone, "commit", "-qm", "plugin")
        bare = tempfile.mkdtemp(prefix="reef-plugin-origin.")
        subprocess.run(["git", "clone", "-q", "--bare", clone, bare], check=True)
        git(clone, "remote", "add", "origin", bare); git(clone, "fetch", "-q", "origin"); git(clone, "branch", "-q", "-u", "origin/main")
        # the origin moves: a newer reef-update that announces itself
        work = tempfile.mkdtemp(prefix="reef-plugin-work.")
        subprocess.run(["git", "clone", "-q", bare, work], check=True)
        up = os.path.join(work, "scripts", "reef-update.py")
        with open(up) as f:
            src = f.read()
        with open(up, "w") as f:
            f.write(src.replace("def main(argv):\n", "def main(argv):\n    print('NEW COPY RUNNING')\n", 1))
        git(work, "commit", "-qam", "newer reef-update"); git(work, "push", "-q", "origin", "main")
        r = subprocess.run([sys.executable, os.path.join(clone, "scripts", "reef-update.py"), "--repo", d, "--plugin", clone, "--commit"],
                           capture_output=True, text=True, env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("running the new copy", r.stdout)
        self.assertEqual(r.stdout.count("NEW COPY RUNNING"), 1, "the new copy runs once, never a loop")
        self.assertIn("project: committed", r.stdout, "the new copy finishes the update")

    def test_commit_takes_the_manifest_and_the_gitignore_lines_too(self):
        # 2026-10-18 (qassimha): three pulls with --commit committed the scripts and never .reef/init-manifest.json
        # (the first porcelain line lost its status column to run()'s strip) nor the .gitignore lines reef-init appends
        import shutil
        d = project()
        with open(os.path.join(d, "package.json"), "w") as f:
            json.dump({"name": "demo", "scripts": {"test": "true"}}, f)
        with open(os.path.join(d, ".reef", "init-manifest.json"), "w") as f:
            f.write("{}\n")
        git(d, "add", "-A"); git(d, "commit", "-qm", "manifest")
        clone = tempfile.mkdtemp(prefix="reef-plugin-main.")
        subprocess.run(["git", "init", "-q", "-b", "main", clone], check=True)
        for sub in ("scripts", "templates", ".claude-plugin"):
            shutil.copytree(os.path.join(ROOT, sub), os.path.join(clone, sub), ignore=shutil.ignore_patterns("__pycache__"))
        git(clone, "add", "-A"); git(clone, "commit", "-qm", "plugin")
        bare = tempfile.mkdtemp(prefix="reef-plugin-origin.")
        subprocess.run(["git", "clone", "-q", "--bare", clone, bare], check=True)
        git(clone, "remote", "add", "origin", bare); git(clone, "fetch", "-q", "origin"); git(clone, "branch", "-q", "-u", "origin/main")
        r = subprocess.run([sys.executable, UPDATE, "--repo", d, "--plugin", clone, "--commit"], capture_output=True, text=True,
                           env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("project: committed", r.stdout)
        left = git(d, "status", "--porcelain", "--", ".reef/init-manifest.json", ".gitignore", "scripts").stdout
        self.assertEqual(left.strip(), "", f"Reef's own files left uncommitted:\n{left}")
        last = git(d, "show", "--stat", "--format=", "HEAD").stdout
        self.assertIn(".reef/init-manifest.json", last)
        self.assertIn(".gitignore", last)

    def plugin_clone(self):
        import shutil
        clone = tempfile.mkdtemp(prefix="reef-plugin-main.")
        subprocess.run(["git", "init", "-q", "-b", "main", clone], check=True)
        for sub in ("scripts", "templates", ".claude-plugin"):
            shutil.copytree(os.path.join(ROOT, sub), os.path.join(clone, sub), ignore=shutil.ignore_patterns("__pycache__"))
        git(clone, "add", "-A"); git(clone, "commit", "-qm", "plugin")
        bare = tempfile.mkdtemp(prefix="reef-plugin-origin.")
        subprocess.run(["git", "clone", "-q", "--bare", clone, bare], check=True)
        git(clone, "remote", "add", "origin", bare); git(clone, "fetch", "-q", "origin"); git(clone, "branch", "-q", "-u", "origin/main")
        return clone

    def test_config_keys_reef_init_adds_are_committed_and_owner_edits_never_are(self):
        # 2026-10-18 (qassimha): after a pull, `graph.mode` and `gates.timeout_s` sat uncommitted in .reef/config.json
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        clone = self.plugin_clone()
        d = project()
        with open(os.path.join(d, "package.json"), "w") as f:
            json.dump({"name": "demo", "scripts": {"test": "true"}}, f)
        cfg_p = os.path.join(d, ".reef", "config.json")
        with open(cfg_p) as f:
            cfg = json.load(f)
        cfg.setdefault("caps", {})["attempts"] = 5          # the owner's own value
        cfg.pop("graph", None)                              # a key a newer Reef ships
        with open(cfg_p, "w") as f:
            json.dump(cfg, f)
        git(d, "add", "-A"); git(d, "commit", "-qm", "owner config")
        r = subprocess.run([sys.executable, UPDATE, "--repo", d, "--plugin", clone, "--commit"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("config: reef-init added new keys", r.stdout)
        self.assertEqual(git(d, "status", "--porcelain", "--", ".reef/config.json").stdout.strip(), "", "the added keys were left uncommitted")
        committed = json.loads(git(d, "show", "HEAD:.reef/config.json").stdout)
        self.assertEqual(committed["caps"]["attempts"], 5, "the owner's value survives")
        self.assertEqual(committed["graph"]["mode"], "auto")
        # an owner's uncommitted edit is never committed by the update, even when keys are added beside it
        with open(cfg_p) as f:
            cfg = json.load(f)
        cfg["caps"]["attempts"] = 4
        cfg["graph"].pop("mode")
        with open(cfg_p, "w") as f:
            json.dump(cfg, f)
        r = subprocess.run([sys.executable, UPDATE, "--repo", d, "--plugin", clone, "--commit"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("config: reef-init added new keys", r.stdout)
        self.assertIn(".reef/config.json", git(d, "status", "--porcelain").stdout, "the owner's edit stays theirs to commit")
        self.assertEqual(json.loads(git(d, "show", "HEAD:.reef/config.json").stdout)["caps"]["attempts"], 5)


if __name__ == "__main__":
    unittest.main()
