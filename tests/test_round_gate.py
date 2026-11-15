"""Hardening PR-1 (docs/design/hardening-pr1-plan.md): the implementer's round is judged by code, not by its prose.
`reef-claims.py round <task>`: (a) the task's named Proof tests fail on the base (its code, the round's tests in place) and
pass on the round's tree; (b) every path the round changed matches the task's `files:`. reef-merge-close refuses a close
whose round does not hold; the agent and the skill point at the check."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import write, git  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAIMS = os.path.join(ROOT, "scripts", "reef-claims.py")
CLOSE = os.path.join(ROOT, "scripts", "reef-merge-close")
GATE = "python3 -m unittest discover -s tests -q"
TASK = """---
id: 101
feature: demo
status: in-progress
complexity: mech
tier: light
attempts: 0
{extra}---
# 101 — add adds

## Acceptance Criteria
- AC-1 (FR-1): add returns the sum

## Proof
| AC | Proof |
|---|---|
| AC-1 | `{proof}` |

## Log
"""
TEST = "import unittest\nfrom src.calc import add\n\nclass T(unittest.TestCase):\n    def test_add_sums(self):\n        self.assertEqual(add(1, 2), 3)\n"


def task(extra="", proof="test_add_sums"):
    return TASK.format(extra=extra, proof=proof)


class Round(unittest.TestCase):
    """A flat project; the base is committed, the round's work is uncommitted in the worktree, as the implementer leaves it."""

    def make(self, base_code, cfg=None, extra="files: [src/, tests/test_calc.py]\n", proof="test_add_sums"):
        self.d = tempfile.mkdtemp(prefix="reef-round.")
        subprocess.run(["git", "init", "-q", "-b", "main", self.d], check=True)
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            git(self.d, "config", k, v)
        write(self.d, ".reef/config.json", json.dumps(cfg or {"gates": {"fast": GATE, "full": GATE}}))
        write(self.d, ".gitignore", ".reef/ci-local/\n")
        write(self.d, "src/__init__.py", "")
        write(self.d, "src/calc.py", base_code)
        write(self.d, "tests/__init__.py", "")
        write(self.d, "tasks/101-add.md", task(extra, proof))
        git(self.d, "add", "-A"); git(self.d, "commit", "-qm", "base")
        write(self.d, "src/calc.py", "def add(a, b):\n    return a + b\n")   # the round: the fix
        write(self.d, "tests/test_calc.py", TEST)                            # and its new test

    def round(self, *extra):
        return subprocess.run([sys.executable, CLAIMS, "round", "tasks/101-add.md", "--repo", self.d, *extra],
                              capture_output=True, text=True, cwd=self.d)

    def test_a_test_that_fails_on_the_base_passes_the_round(self):
        self.make("def add(a, b):\n    return 0\n")
        r = self.round()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("red first: test_add_sums", r.stdout)

    def test_a_test_that_already_passes_on_the_base_is_refused(self):
        self.make("def add(a, b):\n    return a + b  # already right\n")
        r = self.round()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("does not fail on the base", r.stdout)
        with open(os.path.join(self.d, "src/calc.py"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "def add(a, b):\n    return a + b\n", "the round's code is back after the check")
        self.assertEqual(git(self.d, "status", "--porcelain").stdout.split("\n").count(" M src/calc.py"), 1)

    def test_gates_one_runs_each_named_test_alone(self):
        one = "python3 -m unittest discover -s tests -q -k {test} && mkdir -p .reef/ci-local && echo ran-{test} >> .reef/ci-local/one.log"
        self.make("def add(a, b):\n    return 0\n", cfg={"gates": {"fast": "false", "full": "false", "one": one}})
        r = self.round()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(self.d, ".reef/ci-local/one.log"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "ran-test_add_sums\n", "gates.one ran with {test} replaced (green on the tree only)")

    def test_a_round_whose_test_is_red_on_its_own_tree_is_refused(self):
        self.make("def add(a, b):\n    return 0\n")
        write(self.d, "src/calc.py", "def add(a, b):\n    return -1\n")
        r = self.round()
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not pass on the round's tree", r.stdout)

    def test_a_file_outside_the_declared_files_is_refused(self):
        self.make("def add(a, b):\n    return 0\n")
        write(self.d, "README.md", "drive-by\n")
        r = self.round()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("outside the task's files: README.md", r.stdout)

    def test_a_glob_and_the_task_folder_are_allowed(self):
        self.make("def add(a, b):\n    return 0\n", extra="files: [src/*.py, tests/test_*.py]\n")
        with open(os.path.join(self.d, "tasks/101-add.md"), "a", encoding="utf-8") as f:
            f.write("note\n")
        r = self.round()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("scope: 2 changed files within files:", r.stdout)

    def test_the_task_folder_is_allowed_when_the_worktree_is_reached_through_a_symlink(self):
        # CI on PR 372, macOS: /var is a link to /private/var — the worktree's path and the task's path named one folder two ways
        self.make("def add(a, b):\n    return 0\n")
        with open(os.path.join(self.d, "tasks/101-add.md"), "a", encoding="utf-8") as f:
            f.write("note\n")
        link = self.d + "-link"
        os.symlink(self.d, link)
        r = subprocess.run([sys.executable, CLAIMS, "round", os.path.join(self.d, "tasks/101-add.md"), "--repo", link],
                           capture_output=True, text=True, cwd=self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_task_folder_is_allowed_when_the_task_file_is_read_from_another_checkout(self):
        # CI on PR 372, macOS, the critical path: the close found no copy in the task worktree and passed the feature worktree's
        self.make("def add(a, b):\n    return 0\n")
        with open(os.path.join(self.d, "tasks/101-add.md"), "a", encoding="utf-8") as f:
            f.write("note\n")
        other = self.d + "-feature"
        git(self.d, "worktree", "add", "-q", "--detach", other, "HEAD")
        r = subprocess.run([sys.executable, CLAIMS, "round", os.path.join(other, "tasks/101-add.md"), "--repo", self.d],
                           capture_output=True, text=True, cwd=self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_task_without_files_is_not_scope_checked(self):
        self.make("def add(a, b):\n    return 0\n", extra="")
        write(self.d, "README.md", "drive-by\n")
        r = self.round()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("scope: not declared", r.stdout)

    def test_a_refactor_and_a_command_proof_skip_the_red_check(self):
        self.make("def add(a, b):\n    return a + b\n", extra="kind: refactor\nfiles: [src/, tests/]\n")
        r = self.round()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("red first: skipped — kind: refactor", r.stdout)
        self.make("def add(a, b):\n    return a + b\n", proof="scripts/check.sh", extra="files: [src/, tests/]\n")
        r = self.round()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("red first: skipped — the Proof names no test", r.stdout)

    def test_a_check_cut_off_mid_run_is_restored_by_the_next(self):
        self.make("def add(a, b):\n    return 0\n")
        gd = git(self.d, "rev-parse", "--absolute-git-dir").stdout.strip()
        bk = os.path.join(gd, "reef-red-101")
        write(bk, "files/src/calc.py", "def add(a, b):\n    return a + b\n")
        write(bk, "manifest.json", json.dumps({"saved": ["src/calc.py"], "new": []}))
        write(self.d, "src/calc.py", "def add(a, b):\n    return 0\n")   # the base's code, left by the killed run
        r = self.round()
        self.assertIn("restored the round's files from an earlier check cut off", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(bk))


class CloseRefusesTheRound(unittest.TestCase):
    """The enforcement: a fast-path close whose round is not red first commits nothing."""

    def test_the_close_refuses_a_round_whose_test_passes_on_the_base(self):
        tmp = tempfile.mkdtemp(prefix="reef-round-close.")
        main = os.path.join(tmp, "main")
        subprocess.run(["git", "init", "-q", "-b", "main", main], check=True)
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            git(main, "config", k, v)
        write(main, ".reef/config.json", json.dumps({"branches": {"base": "main"}, "paths": {"features": "reef/features"},
                                                     "gates": {"fast": GATE, "full": GATE}}))
        write(main, ".gitignore", ".reef/worktrees/\n.reef/ci-local/\n")
        write(main, "reef/features/demo/SPEC.md", "# demo\nRow: 1\n")
        write(main, "reef/features/demo/tasks/101-add.md", task("files: [src/, tests/]\n"))
        write(main, "src/__init__.py", ""); write(main, "tests/__init__.py", "")
        write(main, "src/calc.py", "def add(a, b):\n    return a + b\n")
        git(main, "add", "-A"); git(main, "commit", "-qm", "init")
        feat = os.path.join(main, ".reef", "worktrees", "demo")
        self.assertEqual(git(main, "worktree", "add", "-q", "-b", "feat/demo", feat, "main").returncode, 0)
        write(feat, "tests/test_calc.py", TEST)
        write(tmp, "journal.md", "| 101 | PASS | growth 3 |\n")
        head = git(feat, "rev-parse", "HEAD").stdout
        r = subprocess.run([sys.executable, CLOSE, "reef/features/demo/tasks/101-add.md", "--subject", "feat: add",
                            "--journal", os.path.join(tmp, "journal.md"), "--repo", feat], capture_output=True, text=True, cwd=feat)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("does not fail on the base", r.stdout + r.stderr)
        self.assertEqual(git(feat, "rev-parse", "HEAD").stdout, head, "nothing committed")


class ThePromptsPointAtTheGate(unittest.TestCase):
    def test_the_implementer_and_the_task_skill_name_the_round_check(self):
        with open(os.path.join(ROOT, "agents", "implementer.md"), encoding="utf-8") as f:
            agent = f.read()
        with open(os.path.join(ROOT, "skills", "reef-task", "SKILL.md"), encoding="utf-8") as f:
            skill = f.read()
        self.assertIn("reef-claims.py round", agent)
        self.assertIn("reef-claims.py round", skill)


if __name__ == "__main__":
    unittest.main()
