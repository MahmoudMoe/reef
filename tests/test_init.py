"""Sabotage suite for scripts/reef-init.py: idempotent, never overwrites, one home per fact,
the generated CI is release-only, every generated file is true to the detected stack."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INIT = os.path.join(ROOT, "scripts", "reef-init.py")


def init(root, *args):
    return subprocess.run([sys.executable, INIT, "--root", root, *args], capture_output=True, text=True)


def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        return f.read()


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def node_project(root):
    write(root, "package.json", json.dumps({"name": "demo-app", "scripts": {"test": "echo t", "build": "echo b"}}))
    subprocess.run(["git", "init", "-q", "-b", "develop", root], check=True)
    return root


class Idempotent(unittest.TestCase):
    def setUp(self):
        self.d = node_project(tempfile.mkdtemp(prefix="reef-init."))

    def test_second_run_writes_nothing(self):
        r = init(self.d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0 proposed", r.stdout)
        snapshot = {rel: read(self.d, rel) for rel in ("AGENTS.md", ".reef/config.json", "docs/queue.md", ".gitignore")}
        r2 = init(self.d)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertRegex(r2.stdout, r"\n  0 written, \d+ skipped, 0 proposed")
        for rel, before in snapshot.items():
            self.assertEqual(read(self.d, rel), before, f"{rel} changed on an idempotent re-run")

    def test_existing_file_never_overwritten_diff_proposed_accept_applies(self):
        write(self.d, "AGENTS.md", "# my own AGENTS.md\nhand-written\n")
        r = init(self.d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(read(self.d, "AGENTS.md"), "# my own AGENTS.md\nhand-written\n", "a user's file was overwritten")
        self.assertIn("PROPOSED AGENTS.md", r.stdout)
        self.assertIn("-# my own AGENTS.md", r.stdout)       # the diff was printed
        self.assertTrue(os.path.isfile(os.path.join(self.d, ".reef", "proposed", "AGENTS.md")))
        r = init(self.d, "--accept", "AGENTS.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("# AGENTS.md", read(self.d, "AGENTS.md"))
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "proposed", "AGENTS.md")))

    def test_accept_without_proposal_refused(self):
        init(self.d)
        r = init(self.d, "--accept", "docs/queue.md")
        self.assertEqual(r.returncode, 1)

    def test_config_keys_added_values_never_changed(self):
        write(self.d, ".reef/config.json", json.dumps({"gates": {"full": "my-own-gate"}, "caps": {"attempts": 5}}))
        init(self.d)
        cfg = json.loads(read(self.d, ".reef/config.json"))
        self.assertEqual(cfg["gates"]["full"], "my-own-gate", "a tuned value was overwritten")
        self.assertEqual(cfg["caps"]["attempts"], 5)
        self.assertEqual(cfg["graph"]["parallel"], 10)        # missing keys arrive
        self.assertEqual(cfg["branches"], {"base": "develop", "release": "main"})

    def test_gitignore_and_makefile_appended_not_rewritten(self):
        write(self.d, ".gitignore", "node_modules/\n")
        write(self.d, "Makefile", "build:\n\techo b\n")
        init(self.d)
        gi = read(self.d, ".gitignore")
        self.assertTrue(gi.startswith("node_modules/\n"))
        self.assertIn(".reef/worktrees/", gi)
        mk = read(self.d, "Makefile")
        self.assertTrue(mk.startswith("build:\n"))
        self.assertIn("\nsetup:", mk)
        init(self.d)
        self.assertEqual(read(self.d, "Makefile").count("setup:"), 1, "setup: appended twice")

    def test_claude_md_pointer_only_when_absent(self):
        write(self.d, "CLAUDE.md", "# existing brief\n")
        r = init(self.d)
        self.assertEqual(read(self.d, "CLAUDE.md"), "# existing brief\n")
        self.assertNotIn("PROPOSED CLAUDE.md", r.stdout, "a CLAUDE.md the human wrote is theirs; no pointer proposed")

    def test_dry_run_writes_nothing(self):
        r = init(self.d, "--dry-run")
        self.assertEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.d, "AGENTS.md")))


class OneHomePerFact(unittest.TestCase):
    """A number that lives in .reef/config.json must not be restated in a generated file."""

    def setUp(self):
        self.d = node_project(tempfile.mkdtemp(prefix="reef-init-home."))
        init(self.d)
        self.cfg = json.loads(read(self.d, ".reef/config.json"))

    def test_generated_prose_points_at_config_instead_of_restating(self):
        prose = "".join(read(self.d, rel) for rel in ("AGENTS.md", ".specify/constitution.md", "docs/queue.md", "docs/day-zero.md"))
        cap = self.cfg["caps"]["attempts"]
        self.assertNotRegex(prose, rf"\b{cap} (fix )?rounds?\b", "the round cap is restated instead of pointed at")
        self.assertNotRegex(prose, rf"\b{self.cfg['graph']['parallel']} agents\b")
        self.assertIn("caps.attempts", prose)

    def test_no_open_questions_heading_and_owner_points_present(self):
        agents = read(self.d, "AGENTS.md")
        self.assertNotRegex(agents, r"(?im)^#+\s.*open\s+questions?")
        self.assertRegex(agents, r"(?m)^## Owner decision points")

    def test_stack_facts_true(self):
        agents = read(self.d, "AGENTS.md")
        self.assertIn("npm ci", agents)
        self.assertIn("npm test", agents)
        self.assertEqual(self.cfg["gates"]["full"], "npm test")
        self.assertEqual(self.cfg["gates"]["extra"], {"build": "npm run build"})
        self.assertEqual(self.cfg["worktree"]["setup"], "npm ci")
        self.assertEqual(self.cfg["paths"]["runlog"], "docs/journal.md")

    def test_no_placeholder_survives(self):
        checked = []
        for dirpath, dirs, names in os.walk(self.d):
            dirs[:] = [x for x in dirs if x not in (".git", "node_modules")]   # components, not substrings
            for n in names:
                if n.endswith((".md", ".yml", ".json")):
                    checked.append(n)
                    with open(os.path.join(dirpath, n), encoding="utf-8", errors="replace") as f:
                        # `${{ github.ref }}` is Actions syntax; a bare `{{key}}` is an unrendered placeholder
                        self.assertNotRegex(f.read(), r"(?<!\$)\{\{", f"unrendered placeholder in {n}")
        self.assertIn("ci.yml", checked, ".github/ must be walked")
        self.assertIn("dependabot.yml", checked)


class ReleaseOnlyCi(unittest.TestCase):
    def setUp(self):
        self.d = node_project(tempfile.mkdtemp(prefix="reef-init-ci."))
        init(self.d)
        self.ci = read(self.d, ".github/workflows/ci.yml")

    def test_ci_runs_on_release_prs_only(self):
        self.assertRegex(self.ci, r"(?m)^on:\n  pull_request:\n    branches: \[main\]")
        self.assertNotRegex(self.ci, r"(?m)^  push:", "CI on push runs every change a second time")
        self.assertIn("cancel-in-progress: true", self.ci)
        self.assertIn("timeout-minutes:", self.ci)
        self.assertIn("reef-ci-local.sh --ci", self.ci, "CI must run the same gate list as the local script")

    def test_dependabot_targets_the_integration_branch(self):
        dep = read(self.d, ".github/dependabot.yml")
        self.assertIn('target-branch: "develop"', dep)
        self.assertIn('package-ecosystem: "npm"', dep)
        self.assertNotIn('target-branch: "main"', dep)

    def test_python_stack(self):
        d = tempfile.mkdtemp(prefix="reef-init-py.")
        write(d, "pyproject.toml", "[project]\nname='x'\n")
        write(d, "uv.lock", "")
        subprocess.run(["git", "init", "-q", d], check=True)
        init(d)
        cfg = json.loads(read(d, ".reef/config.json"))
        self.assertEqual(cfg["gates"]["full"], "uv run pytest -q")
        self.assertIn("uv sync", read(d, "AGENTS.md"))

    def test_unknown_stack_leaves_gate_empty_and_says_so(self):
        d = tempfile.mkdtemp(prefix="reef-init-none.")
        subprocess.run(["git", "init", "-q", d], check=True)
        r = init(d)
        self.assertIn("no test command detected", r.stdout)
        self.assertEqual(json.loads(read(d, ".reef/config.json"))["gates"]["full"], "")


if __name__ == "__main__":
    unittest.main()
