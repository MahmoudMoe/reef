"""reef-doctor and reef-update (0.7, usability plan A1): the screen names the state and the fix; the update is one command."""
import json
import os
import shutil
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

    def test_a_local_env_file_is_named_by_its_keys_never_its_values(self):
        # 0.7.2 (ai-coach, 2026-10-24): Prisma loads the checkout's .env; two keys made 21 tests fail locally that pass in CI
        d = project()
        with open(os.path.join(d, ".reef", "config.json"), "w") as f:
            json.dump({"branches": {"base": "main"}, "paths": {"queue": "reef/queue.md"}, "gates": {"full": "npm test"}}, f)
        self.assertNotIn("the local gate reads .env", doctor(d).stdout, "no .env: no line")
        with open(os.path.join(d, ".env"), "w") as f:
            f.write("# local\nDATABASE_URL=postgres://u:sekret@localhost/db\nexport AI_COACH_SPEED_HASH = topsecret\n")
        r = doctor(d)
        self.assertIn("WARN env: the local gate reads .env (2 key(s): DATABASE_URL, AI_COACH_SPEED_HASH), CI does not", r.stdout)
        self.assertIn("compare once: DATABASE_URL= AI_COACH_SPEED_HASH= npm test", r.stdout)
        self.assertNotIn("sekret", r.stdout); self.assertNotIn("topsecret", r.stdout)

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

    def _clone(self):
        import shutil
        clone = tempfile.mkdtemp(prefix="reef-plugin-main.")
        subprocess.run(["git", "init", "-q", "-b", "main", clone], check=True)
        for sub in ("scripts", "templates", ".claude-plugin"):
            shutil.copytree(os.path.join(ROOT, sub), os.path.join(clone, sub), ignore=shutil.ignore_patterns("__pycache__"))
        git(clone, "add", "-A"); git(clone, "commit", "-qm", "plugin")
        return clone

    def test_the_reload_line_names_the_marketplace_and_the_push_hint_rebases_first(self):
        # 2026-10-29 (the owner's update): the last line read `/plugin marketplace update <marketplace>` — a placeholder in a
        # command, against the owner's rule — and when his push was rejected (the loop had pushed meanwhile) the hint said
        # `git push`, which fails the same way. The marketplace is read from ~/.claude/plugins; the hint rebases first.
        d, clone = project(), self._clone()
        home = tempfile.mkdtemp(prefix="reef-home.")
        os.makedirs(os.path.join(home, ".claude", "plugins"))
        with open(os.path.join(home, ".claude", "plugins", "known_marketplaces.json"), "w") as f:
            json.dump({"official": {"installLocation": "/elsewhere"}, "mymarket": {"source": {"source": "directory", "path": clone}, "installLocation": clone}}, f)
        ident = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}   # HOME replaced: no ~/.gitconfig (CI)
        env = dict(os.environ, HOME=home, **ident)
        r = subprocess.run([sys.executable, UPDATE, "--repo", d, "--plugin", clone, "--dry-run"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("/plugin marketplace update mymarket   then   /reload-plugins", r.stdout)
        self.assertNotIn("<marketplace>", r.stdout)
        env_none = dict(os.environ, HOME=tempfile.mkdtemp(prefix="reef-home-none."), **ident)
        r = subprocess.run([sys.executable, UPDATE, "--repo", d, "--plugin", clone, "--dry-run"], capture_output=True, text=True, env=env_none)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("<marketplace>", r.stdout, "no placeholder, ever")
        self.assertIn("/reload-plugins", r.stdout)
        home2 = tempfile.mkdtemp(prefix="reef-home-installed.")   # the fallback: installed_plugins.json names reef@<name>
        os.makedirs(os.path.join(home2, ".claude", "plugins"))
        with open(os.path.join(home2, ".claude", "plugins", "installed_plugins.json"), "w") as f:
            json.dump({"version": 2, "plugins": {"reef@foo": [{"scope": "user"}]}}, f)
        r = subprocess.run([sys.executable, UPDATE, "--repo", d, "--plugin", clone, "--dry-run"], capture_output=True, text=True, env=dict(os.environ, HOME=home2, **ident))
        self.assertIn("/plugin marketplace update foo   then   /reload-plugins", r.stdout)
        # the push: origin moved under the owner — the hint is the line that lands it (the plugin clone gets its upstream, as
        # a real one has: a non-dry update pulls it first)
        pbare = tempfile.mkdtemp(prefix="reef-plugin-origin.")
        subprocess.run(["git", "clone", "-q", "--bare", clone, pbare], check=True)
        git(clone, "remote", "add", "origin", pbare); git(clone, "fetch", "-q", "origin"); git(clone, "branch", "-q", "-u", "origin/main")
        bare = tempfile.mkdtemp(prefix="reef-origin.")
        subprocess.run(["git", "clone", "-q", "--bare", d, bare], check=True)
        git(d, "remote", "add", "origin", bare); git(d, "fetch", "-q", "origin"); git(d, "branch", "-q", "-u", "origin/main")
        other = tempfile.mkdtemp(prefix="reef-other.")
        subprocess.run(["git", "clone", "-q", bare, other], check=True)
        with open(os.path.join(other, "vitest.txt"), "w") as f:
            f.write("four workers\n")
        git(other, "add", "-A"); git(other, "commit", "-qm", "the loop's merge"); git(other, "push", "-q", "origin", "main")
        r = subprocess.run([sys.executable, UPDATE, "--repo", d, "--plugin", clone, "--commit", "--push"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("git pull --rebase --autostash origin main && git push", r.stdout)
        self.assertIn("an autostash that does not re-apply stays in `git stash list`", r.stdout)
        # the security review: a branch name is git's, not the owner's — `fix;x` is a legal ref — and lands in a shell line
        git(d, "checkout", "-q", "-b", "fix;x"); git(d, "push", "-q", "-u", "origin", "fix;x")
        git(other, "fetch", "-q"); git(other, "checkout", "-q", "fix;x")
        with open(os.path.join(other, "more.txt"), "w") as f:
            f.write("x\n")
        git(other, "add", "-A"); git(other, "commit", "-qm", "ahead"); git(other, "push", "-q", "origin", "fix;x")
        os.unlink(os.path.join(d, "scripts", "reef-row.py"))   # a copy to restore (an edited copy would be a proposal, not a change)
        git(d, "commit", "-qam", "behind again")
        r = subprocess.run([sys.executable, UPDATE, "--repo", d, "--plugin", clone, "--commit", "--push"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("origin 'fix;x' && git push", r.stdout, "quoted for the shell")
        # a push that fails for another reason gets no rebase advice
        git(d, "remote", "set-url", "origin", "/nonexistent/origin.git")
        os.unlink(os.path.join(d, "scripts", "reef-evidence.py"))   # another copy to restore: the commit happens, then the push fails for its own reason
        git(d, "commit", "-qam", "a copy removed")
        r = subprocess.run([sys.executable, UPDATE, "--repo", d, "--plugin", clone, "--commit", "--push"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("git pull --rebase", r.stdout, "no rebase hint for a push that failed for another reason")
        self.assertIn("reef-update FAILED: push:", r.stdout)
        # a marketplace key is any JSON string: one outside [A-Za-z0-9._-] is not rendered into the Claude Code line
        with open(os.path.join(home, ".claude", "plugins", "known_marketplaces.json"), "w") as f:
            json.dump({"my market; rm -rf": {"installLocation": clone}}, f)
        r = subprocess.run([sys.executable, UPDATE, "--repo", d, "--plugin", clone, "--dry-run"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("rm -rf", r.stdout); self.assertIn("/reload-plugins", r.stdout)
        with open(os.path.join(home, ".claude", "plugins", "known_marketplaces.json"), "w") as f:
            json.dump(["not", "an", "object"], f)
        r = subprocess.run([sys.executable, UPDATE, "--repo", d, "--plugin", clone, "--dry-run"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, "a file of another shape is no crash: " + r.stdout + r.stderr)

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


    def test_a_managed_file_reef_init_updates_in_place_is_committed_and_an_owner_edit_never_is(self):
        # 2026-10-21 (qassimha): the update rewrote AGENTS.md with a new rule and committed only the manifest and the
        # scripts; AGENTS.md sat modified and uncommitted. The printed accept line named scripts/reef-init.py, which a
        # project does not have.
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        clone = self.plugin_clone()
        d = project()
        with open(os.path.join(d, "package.json"), "w") as f:
            json.dump({"name": "demo", "scripts": {"test": "true"}}, f)
        git(d, "add", "-A"); git(d, "commit", "-qm", "stack")
        update = lambda: subprocess.run([sys.executable, UPDATE, "--repo", d, "--plugin", clone, "--commit"], capture_output=True, text=True, env=env)
        r = update()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        git(d, "add", "-A"); git(d, "commit", "-qm", "the owner commits the first rendering")

        def new_rule(word):
            tp = os.path.join(clone, "templates", "project", "AGENTS.md")
            with open(tp) as f:
                t = f.read()
            with open(tp, "w") as f:
                f.write(t.replace("Point, don't narrate.", f"Point, don't narrate. {word}.", 1))
            git(clone, "commit", "-qam", word); git(clone, "push", "-q", "origin", "main")

        new_rule("RULE-ONE")
        r = update()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("RULE-ONE", git(d, "show", "HEAD:AGENTS.md").stdout, "the rewritten AGENTS.md is in Reef's commit")
        self.assertEqual(git(d, "status", "--porcelain", "--", "AGENTS.md").stdout.strip(), "", "nothing left uncommitted")
        # the owner's uncommitted edit is never swept into Reef's commit, whatever reef-init does with the file
        with open(os.path.join(d, "AGENTS.md"), "a") as f:
            f.write("\nThe owner's own line.\n")
        new_rule("RULE-TWO")
        r = update()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("The owner's own line.", git(d, "show", "HEAD:AGENTS.md").stdout)
        self.assertIn("The owner's own line.", open(os.path.join(d, "AGENTS.md")).read())
        self.assertNotIn("python3 scripts/reef-init.py --accept", r.stdout, "a project has no scripts/reef-init.py")
        if "proposal: AGENTS.md" in r.stdout:
            self.assertRegex(r.stdout, r"python3 \S*reef-plugin-main\.\w+/scripts/reef-init\.py --root \S+ --accept AGENTS\.md")

if __name__ == "__main__":
    unittest.main()


class NormalRoundChecks(unittest.TestCase):
    """2026-10-28 (the owner, after the first night): the doctor checks what stopped him that day — a loop hold left by a dead
    session, no probe for the runner, the worktree setup unproven, the plugin disabled — each with the one fix."""

    def test_the_hold_the_probe_the_setup_and_the_plugin_are_checked(self):
        d = project()
        os.makedirs(os.path.join(d, ".reef", "run"), exist_ok=True)
        with open(os.path.join(d, ".reef", "run", "orchestrator.json"), "w") as f:
            json.dump({"session": "6ee3355f-2fe4-4a00", "at": 1.0, "pid": 999999}, f)
        for n in ("reef-setup.py", "reef_common.py"):
            shutil.copy(os.path.join(ROOT, "scripts", n), os.path.join(d, "scripts", n))
        r = doctor(d)
        out = r.stdout
        self.assertIn("hold: session 6ee3355f", out)
        self.assertIn("dead", out)
        self.assertIn("reef-loop.py unlock", out)
        self.assertIn("gate probe: none", out)
        self.assertIn("reef-run.py probe", out)
        self.assertIn("setup: unproven", out)
        self.assertIn("reef-setup.py prove", out)
        self.assertIn("plugin enabled:", out, "the plugin's on/off state is a doctor line (it flipped to disabled after a marketplace update)")
