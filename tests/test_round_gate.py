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
        # the named test itself, through gates.one (the owner's decision 2: without it the whole fast gate runs, and says so)
        self.make("def add(a, b):\n    return 0\n", cfg={"gates": {"fast": "false", "full": "false", "one": "python3 -m unittest discover -s tests -q -k {test}"}})
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

    def test_a_refused_round_is_recorded_from_its_log_as_the_saw_verbatim(self):
        # hardening PR-2, the owner's decision 2: the round's REFUSED lines reach the FAIL record by code, never retyped
        self.make("def add(a, b):\n    return a + b  # already right\n")
        r = self.round()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        refused = [l for l in r.stdout.splitlines() if l.startswith("round: REFUSED — ")]
        self.assertTrue(refused, r.stdout)
        gd = git(self.d, "rev-parse", "--absolute-git-dir").stdout.strip()
        with open(os.path.join(gd, "reef-round-101.log"), encoding="utf-8") as f:
            log = f.read()
        for l in refused:
            self.assertIn(l + "\n", log, "the round's log holds its REFUSED lines")
        a = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-attempt"), "--from-round", os.path.join(self.d, "tasks", "101-add.md")],
                           capture_output=True, text=True, cwd=self.d)
        self.assertEqual(a.returncode, 0, a.stdout + a.stderr)
        with open(os.path.join(self.d, "tasks", "101-add.md"), encoding="utf-8") as f:
            t = f.read()
        self.assertIn("  - EXPECTED: reef-claims.py round exits 0", t)
        for l in refused:
            self.assertIn(f"  - SAW: {l[:200]}\n", t)

    def test_a_round_whose_test_is_red_on_its_own_tree_is_refused(self):
        self.make("def add(a, b):\n    return 0\n")
        write(self.d, "src/calc.py", "def add(a, b):\n    return -1\n")
        r = self.round()
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not pass on the round's tree", r.stdout)

    def test_without_gates_one_the_check_says_it_ran_the_whole_fast_gate(self):
        # the owner's decision 2 (2026-11-15): no line may read as if the named test was checked when the whole gate ran
        self.make("def add(a, b):\n    return 0\n")
        r = self.round()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("red first: the whole fast gate, not test_add_sums (no gates.one)", r.stdout)

    def test_a_named_test_that_runs_no_test_is_refused(self):
        # unittest's own run of a name that matches nothing: `Ran 0 tests` (exit 5 on 3.12+, 0 before) — neither green nor red
        one = "python3 -m unittest discover -s tests -q -k {test}"
        self.make("def add(a, b):\n    return 0\n", cfg={"gates": {"fast": "false", "full": "false", "one": one}}, proof="test_not_written")
        r = self.round()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("test_not_written ran no test", r.stdout)

    def test_each_runners_run_of_no_test_is_refused_and_a_real_run_counts(self):
        # measured 2026-11-15 (go, cargo, vitest 2.1.9, jest 29.7): a filter matching nothing exits 0 and says so only in its output
        zero = {"go": "testing: warning: no tests to run\nPASS\nok  \tx\t0.001s [no tests to run]",
                "cargo": "running 0 tests\ntest result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 1 filtered out; finished in 0.00s",
                "vitest": " Test Files  1 skipped (1)\n      Tests  1 skipped (1)",
                "jest": "Tests:       1 skipped, 1 total",
                "pytest": "1 deselected in 0.00s"}
        for runner, out in zero.items():
            stub = "printf '%s\\n' " + json.dumps(out).replace("\\t", "\t") + "; exit " + ("5" if runner == "pytest" else "0")
            self.make("def add(a, b):\n    return 0\n", cfg={"gates": {"fast": "false", "full": "false", "one": stub + " # {test}"}})
            r = self.round()
            self.assertEqual(r.returncode, 1, f"{runner}: {r.stdout}{r.stderr}")
            self.assertIn("test_add_sums ran no test", r.stdout, runner)
        real = "if grep -q 'a + b' src/calc.py; then echo '--- PASS: {test} (0.00s)'; else echo '--- FAIL: {test} (0.00s)'; exit 1; fi"
        self.make("def add(a, b):\n    return 0\n", cfg={"gates": {"fast": "false", "full": "false", "one": real}})
        r = self.round()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("red first: test_add_sums fails on the base", r.stdout)

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


DOWN = """---
id: 102
feature: demo
status: pending
complexity: mech
tier: light
attempts: 0
blocked-by: [101]
files: [src/use.py]
consumes: [{consumes}]
---
# 102 — use what 101 made

## Log
"""


class HandOffs(unittest.TestCase):
    """Hardening PR-5, the owner's ruling 2: the round of 101 delivers every path an OPEN downstream task consumes from it — on
    the closing tree, and changed by the round unless the base already had it."""
    make, round = Round.make, Round.round

    def with_down(self, consumes, where="tasks/102-use.md", ignore=None):
        self.make("def add(a, b):\n    return 0\n")
        if ignore:
            write(self.d, ".gitignore", ".reef/ci-local/\n" + ignore + "\n")
        write(self.d, where, DOWN.format(consumes=consumes))
        git(self.d, "add", "-A", "--", "tasks", ".gitignore"); git(self.d, "commit", "-qm", "the downstream task")

    def test_a_consumed_path_missing_on_the_closing_tree_is_refused(self):
        self.with_down("101: src/new.py#make")
        r = self.round()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("round: REFUSED — tasks/102-use.md consumes 101: src/new.py — missing on the closing tree", r.stdout)

    def test_a_consumed_path_the_round_creates_passes(self):
        self.with_down("101: src/new.py#make, 101: src/calc.py#add")
        write(self.d, "src/new.py", "def make():\n    return 1\n")
        r = self.round()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("hand-offs: 2 consumed paths delivered", r.stdout)

    def test_a_new_consumed_path_the_round_does_not_change_is_refused(self):
        # an ignored build output: on disk in the worktree, never in the commit the downstream builds on
        self.with_down("101: src/gen.py", ignore="src/gen.py")
        write(self.d, "src/gen.py", "X = 1\n")
        r = self.round()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("tasks/102-use.md consumes 101: src/gen.py — not changed by this round", r.stdout)

    def test_a_consumed_directory_the_round_creates_passes(self):
        self.with_down("101: src/export/")
        write(self.d, "src/export/csv.py", "X = 1\n")
        r = self.round()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_path_the_base_already_had_may_stay_unchanged(self):
        self.with_down("101: src/__init__.py")
        r = self.round()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_finished_downstream_and_another_tasks_hand_off_are_not_checked(self):
        self.with_down("101: src/new.py", where="tasks/done/102-use.md")
        self.assertEqual(self.round().returncode, 0)
        self.with_down("100: src/new.py")
        self.assertEqual(self.round().returncode, 0)


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


class CloseRefusesAnUndeliveredHandOff(unittest.TestCase):
    """Hardening PR-5, the owner's ruling 2, at the enforcement point: a fast-path close of 101 whose open downstream 102
    consumes a path the round did not produce commits nothing; once the round produces it, the close lands."""

    def test_the_close_refuses_then_closes(self):
        tmp = tempfile.mkdtemp(prefix="reef-handoff-close.")
        main = os.path.join(tmp, "main")
        subprocess.run(["git", "init", "-q", "-b", "main", main], check=True)
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            git(main, "config", k, v)
        write(main, ".reef/config.json", json.dumps({"branches": {"base": "main"}, "paths": {"features": "reef/features"},
                                                     "gates": {"fast": GATE, "full": GATE}}))
        write(main, ".gitignore", ".reef/worktrees/\n.reef/ci-local/\n")
        write(main, "reef/features/demo/SPEC.md", "# demo\nRow: 1\n")
        write(main, "reef/features/demo/tasks/101-add.md", task("files: [src/, tests/]\n"))
        write(main, "reef/features/demo/tasks/102-use.md", DOWN.format(consumes="101: src/new.py"))
        write(main, "src/__init__.py", ""); write(main, "tests/__init__.py", "")
        write(main, "src/calc.py", "def add(a, b):\n    return 0\n")
        git(main, "add", "-A"); git(main, "commit", "-qm", "init")
        feat = os.path.join(main, ".reef", "worktrees", "demo")
        self.assertEqual(git(main, "worktree", "add", "-q", "-b", "feat/demo", feat, "main").returncode, 0)
        write(feat, "src/calc.py", "def add(a, b):\n    return a + b\n")
        write(feat, "tests/test_calc.py", TEST)
        write(tmp, "journal.md", "| 101 | PASS | growth 3 |\n")
        head = git(feat, "rev-parse", "HEAD").stdout
        close = lambda: subprocess.run([sys.executable, CLOSE, "reef/features/demo/tasks/101-add.md", "--subject", "feat: add",
                                        "--journal", os.path.join(tmp, "journal.md"), "--repo", feat], capture_output=True, text=True, cwd=feat)
        r = close()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("102-use.md consumes 101: src/new.py — missing on the closing tree", r.stdout + r.stderr)
        self.assertEqual(git(feat, "rev-parse", "HEAD").stdout, head, "nothing committed")
        write(feat, "src/new.py", "def make():\n    return 1\n")
        r = close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotEqual(git(feat, "rev-parse", "HEAD").stdout, head, "the close landed")
        self.assertIn("src/new.py", git(feat, "show", "--name-only", "HEAD").stdout)


class CloseChecksACommittedRound(unittest.TestCase):
    """Hardening PR-6 (docs/design/hardening-pr6-plan.md): the close ran the round check only on a DIRTY task worktree, so a
    task whose work was already committed on its branch (a close cut off after that commit, or anyone committing there)
    merged with no check. Every merge path now runs it: base = merge-base(task branch, HEAD), the branch's commits included."""

    def setup(self, base_code, down=None, ignore="__pycache__/\n", files="[src/, tests/]"):
        self.tmp = tempfile.mkdtemp(prefix="reef-round-committed.")
        self.main = os.path.join(self.tmp, "main")
        subprocess.run(["git", "init", "-q", "-b", "main", self.main], check=True)
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            git(self.main, "config", k, v)
        write(self.main, ".reef/config.json", json.dumps({"branches": {"base": "main"}, "gates": {"fast": GATE, "full": GATE}}))
        write(self.main, ".gitignore", ".reef/worktrees/\n.reef/ci-local/\n" + ignore)   # the test runs' bytecode, as a project ignores it
        write(self.main, "reef/features/demo/tasks/101-add.md", task(f"files: {files}\n"))   # no SPEC.md: the critical path
        if down:
            write(self.main, "reef/features/demo/tasks/102-use.md", DOWN.format(consumes=down))
        write(self.main, "src/__init__.py", ""); write(self.main, "tests/__init__.py", "")
        write(self.main, "src/calc.py", base_code)
        git(self.main, "add", "-A"); git(self.main, "commit", "-qm", "init")
        self.feat = os.path.join(self.tmp, "feat")
        self.assertEqual(git(self.main, "worktree", "add", "-q", "-b", "feat/demo", self.feat, "main").returncode, 0)
        self.wt = os.path.join(self.main, ".reef", "worktrees", "101")
        self.assertEqual(git(self.main, "worktree", "add", "-q", "-b", "task/101-add", self.wt, "feat/demo").returncode, 0)
        write(self.wt, "src/calc.py", "def add(a, b):\n    return a + b\n")
        write(self.wt, "tests/test_calc.py", TEST)
        write(self.tmp, "journal.md", "| 101 | PASS | growth 3 |\n")

    def commit_round(self):
        git(self.wt, "add", "-A"); git(self.wt, "commit", "-qm", "the round, committed before the close")
        self.assertEqual(git(self.wt, "status", "--porcelain").stdout, "", "precondition: the task worktree is clean")
        self.tip, self.head = git(self.wt, "rev-parse", "HEAD").stdout, git(self.feat, "rev-parse", "HEAD").stdout

    def close(self, env=None):
        return subprocess.run([sys.executable, CLOSE, "reef/features/demo/tasks/101-add.md", "--subject", "feat: add",
                               "--journal", os.path.join(self.tmp, "journal.md"), "--repo", self.feat], capture_output=True, text=True,
                              cwd=self.feat, env=env)

    def refused(self, why):
        r = self.close()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(why, r.stdout + r.stderr)
        self.assertEqual(git(self.feat, "rev-parse", "HEAD").stdout, self.head, "nothing merged")
        self.assertNotEqual(git(self.feat, "merge-base", "--is-ancestor", "task/101-add", "HEAD").returncode, 0, "the branch is unmerged")
        self.assertEqual(git(self.wt, "rev-parse", "HEAD").stdout, self.tip, "the branch's commits are untouched")
        self.assertEqual(git(self.wt, "status", "--porcelain").stdout, "", "the red check left the task worktree clean")

    def test_a_committed_round_whose_test_passes_on_the_base_is_refused(self):
        self.setup("def add(a, b):\n    return a + b  # already right\n")
        self.commit_round()
        self.refused("does not fail on the base")

    def test_a_committed_file_outside_the_declared_files_is_refused(self):
        self.setup("def add(a, b):\n    return 0\n")
        write(self.wt, "docs/notes.md", "x\n")
        self.commit_round()
        self.refused("outside the task's files: docs/notes.md")

    def test_a_committed_round_that_does_not_deliver_a_hand_off_is_refused(self):
        self.setup("def add(a, b):\n    return 0\n", down="101: src/new.py")
        self.commit_round()
        self.refused("102-use.md consumes 101: src/new.py — missing on the closing tree")

    def test_a_committed_round_that_holds_closes_and_merges(self):
        self.setup("def add(a, b):\n    return 0\n")
        self.commit_round()
        r = self.close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("red first: the whole fast gate", r.stdout, "the round check ran on the committed work")
        self.assertIn("fails on the base", r.stdout)
        self.assertEqual(git(self.feat, "show", "HEAD:src/calc.py").stdout, "def add(a, b):\n    return a + b\n")


class FastCloseOfWorkAlreadyCommitted(unittest.TestCase):
    """Hardening PR-6, the fast path: the round check diffs the row's worktree against HEAD, so work committed on the feature
    branch before the close is invisible to it; a round that changed nothing outside the task folder is refused."""

    def test_a_fast_close_with_nothing_to_check_is_refused(self):
        tmp = tempfile.mkdtemp(prefix="reef-round-fast-committed.")
        main = os.path.join(tmp, "main")
        subprocess.run(["git", "init", "-q", "-b", "main", main], check=True)
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            git(main, "config", k, v)
        write(main, ".reef/config.json", json.dumps({"branches": {"base": "main"}, "paths": {"features": "reef/features"},
                                                     "gates": {"fast": GATE, "full": GATE}}))
        write(main, ".gitignore", ".reef/worktrees/\n.reef/ci-local/\n")
        write(main, "reef/features/demo/SPEC.md", "# demo\nRow: 1\n")
        write(main, "reef/features/demo/tasks/101-add.md", task("files: [src/]\n", proof="scripts/check.sh"))
        write(main, "src/calc.py", "def add(a, b):\n    return 0\n")
        git(main, "add", "-A"); git(main, "commit", "-qm", "init")
        feat = os.path.join(main, ".reef", "worktrees", "demo")
        self.assertEqual(git(main, "worktree", "add", "-q", "-b", "feat/demo", feat, "main").returncode, 0)
        write(feat, "docs/out-of-scope.md", "x\n")
        git(feat, "add", "-A"); git(feat, "commit", "-qm", "the work, committed by hand on the feature branch")
        write(tmp, "journal.md", "| 101 | PASS | growth 3 |\n")
        head = git(feat, "rev-parse", "HEAD").stdout
        r = subprocess.run([sys.executable, CLOSE, "reef/features/demo/tasks/101-add.md", "--subject", "feat: add",
                            "--journal", os.path.join(tmp, "journal.md"), "--repo", feat], capture_output=True, text=True, cwd=feat)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("changed nothing outside the task folder", r.stdout + r.stderr)
        self.assertEqual(git(feat, "rev-parse", "HEAD").stdout, head, "nothing committed")
        self.assertEqual(git(feat, "status", "--porcelain").stdout, "", "nothing left changed")


# the test runs' environment as a shell without the variable gives it (the runner may set it; then nothing would be written)
BYTECODE_ON = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}


class TheRoundCheckLeavesNoByteCode(unittest.TestCase):
    """Hardening PR-12 (docs/design/hardening-pr12-plan.md): the round check runs the project's tests in the task worktree;
    in a project whose .gitignore does not ignore __pycache__/, the byte-code they wrote was merged (a dirty close), kept the
    worktree from being removed (a clean close) and tripped files: on the next check. Its runs now write no byte-code;
    a .pyc the round itself adds is still a change of the round."""

    setup, commit_round, close, refused = (CloseChecksACommittedRound.setup, CloseChecksACommittedRound.commit_round,
                                           CloseChecksACommittedRound.close, CloseChecksACommittedRound.refused)

    def bytecode(self, tree):
        return [p for p in git(tree, "ls-files", "-z", "--others", "--exclude-standard").stdout.split("\0") if "__pycache__" in p]

    def test_a_committed_round_closes_and_its_worktree_is_removed(self):
        self.setup("def add(a, b):\n    return 0\n", ignore="")
        self.commit_round()
        r = self.close(BYTECODE_ON)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(self.wt), "the task worktree is removed")

    def test_an_uncommitted_round_merges_no_byte_code(self):
        self.setup("def add(a, b):\n    return 0\n", ignore="")
        r = self.close(BYTECODE_ON)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        merged = git(self.feat, "ls-tree", "-r", "--name-only", "HEAD").stdout.split()
        self.assertEqual([p for p in merged if "__pycache__" in p], [], "no byte-code merged")

    def test_a_second_check_of_the_same_round_is_not_tripped_by_the_first(self):
        self.setup("def add(a, b):\n    return 0\n", ignore="", files="[src/, tests/test_calc.py]")
        wtask = os.path.join(self.wt, "reef/features/demo/tasks/101-add.md")
        run = lambda: subprocess.run([sys.executable, CLAIMS, "round", wtask, "--repo", self.wt, "--base", "main"],
                                     capture_output=True, text=True, cwd=self.wt, env=BYTECODE_ON)
        first = run()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        second = run()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(self.bytecode(self.wt), [], "the check wrote no byte-code")

    def test_the_commit_gate_the_close_runs_writes_no_byte_code_either(self):
        # a project's .githooks/pre-commit runs the tests in the tree it commits: the task worktree, then the feature's
        self.setup("def add(a, b):\n    return 0\n", ignore="")
        write(self.tmp, "hooks/pre-commit", "#!/bin/sh\nexec python3 -m unittest discover -s tests -q\n")
        os.chmod(os.path.join(self.tmp, "hooks/pre-commit"), 0o755)
        git(self.main, "config", "core.hooksPath", os.path.join(self.tmp, "hooks"))
        r = self.close(BYTECODE_ON)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(self.wt), "the task worktree is removed")
        self.assertEqual(self.bytecode(self.feat), [], "the merge commit's gate wrote no byte-code")

    def test_a_pyc_the_round_adds_still_counts(self):
        self.setup("def add(a, b):\n    return 0\n", ignore="", files="[src/calc.py, tests/]")
        write(self.wt, "src/__pycache__/keep.pyc", "kept on purpose\n")
        self.commit_round()
        self.refused("outside the task's files: src/__pycache__/keep.pyc")


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
