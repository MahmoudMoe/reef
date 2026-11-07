"""reef-merge-close (0.7.2, the owner's go 2026-10-24, item 4): a passed task's commit, merge --no-ff into the feature,
status done + journal block + git mv to done/ in that merge commit, worktree.setup on a lockfile, worktree and branch
removed — one command; a conflict or a gate refusal leaves the tree as it was."""
import glob
import os
import subprocess
import sys
import tempfile
import time
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import write, git  # noqa: E402  (the suites' shared fixtures, once)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLOSE = os.path.join(ROOT, "scripts", "reef-merge-close")
PLAN_CHECK = os.path.join(ROOT, "scripts", "reef-plan-check.py")
GRAPH = os.path.join(ROOT, "scripts", "reef-graph.py")
TASK = """---
id: 101
feature: demo
status: in-progress
complexity: mech
tier: light
attempts: 0
---
# 101 — the slice

## Acceptance Criteria
- AC-1 (FR-1): it works

## Log
"""


# the session ending mid-gate (2026-11-07, an adopted project's task 4701): the pre-commit hook kills the close's own process, then the gate is red
KILL = ("#!/bin/sh\n{only}p=$PPID\nwhile [ \"${{p:-1}}\" -gt 1 ]; do\n"
        "  case \"$(ps -o args= -p \"$p\")\" in *reef-merge-close*) kill -9 \"$p\"; exit 1;; esac\n"
        "  p=$(ps -o ppid= -p \"$p\" | tr -d ' ')\ndone\necho 'gate: no close to kill' >&2; exit 1\n")


def read(d, rel):
    with open(os.path.join(d, rel), encoding="utf-8") as f:
        return f.read()


def gate(main, body):
    """The repository's pre-commit hook (shared by every worktree); None removes it."""
    hook = os.path.join(main, ".git", "hooks", "pre-commit")
    if body is None:
        os.remove(hook)
        return
    write(main, ".git/hooks/pre-commit", body)
    os.chmod(hook, 0o755)


def settled(wt):
    """The orphaned `git commit` let go of the index; the recovery notes left in the worktree's git dir."""
    gd = git(wt, "rev-parse", "--absolute-git-dir").stdout.strip()
    for _ in range(200):
        if not os.path.exists(os.path.join(gd, "index.lock")):
            break
        time.sleep(0.05)
    return glob.glob(os.path.join(gd, "reef-close-*"))


class FastRowClose(unittest.TestCase):
    """Workflow v3, phase 3b: on the fast path there is no task branch — the implementer worked in the feature worktree;
    merge-close commits the work there with the Closes-task trailer, marks the task done and moves it, nothing else."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reef-mc-fast.")
        self.main = os.path.join(self.tmp, "main")
        subprocess.run(["git", "init", "-q", "-b", "main", self.main], check=True)
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            subprocess.run(["git", "-C", self.main, "config", k, v], check=True)
        write(self.main, ".reef/config.json", '{"branches": {"base": "main"}, "paths": {"features": "reef/features"}}')
        write(self.main, ".gitignore", ".reef/worktrees/\n")
        write(self.main, "reef/features/demo/SPEC.md", "# demo\nRow: 1\n")
        write(self.main, "reef/features/demo/tasks/101-slice.md", TASK)
        write(self.main, "src/a.py", "a = 1\n")
        git(self.main, "add", "-A"); git(self.main, "commit", "-qm", "init")
        self.feat = os.path.join(self.main, ".reef", "worktrees", "demo")   # where /reef-plan puts a feature worktree
        self.assertEqual(git(self.main, "worktree", "add", "-q", "-b", "feat/demo", self.feat, "main").returncode, 0)
        # the review (2026-10-26): reef-graph.py worktree records the FEATURE worktree on a fast row — the close must not read
        # that key as a task worktree and tear the feature worktree down
        write(self.feat, "reef/features/demo/tasks/101-slice.md", TASK.replace("attempts: 0\n", "attempts: 0\nworktree: .reef/worktrees/demo\n"))
        write(self.feat, "src/a.py", "a = 2\n")                    # the implementer's work, in the row's one worktree
        write(self.feat, "tests/test_a.py", "def test_a(): pass\n")
        self.journal = os.path.join(self.tmp, "journal.md")
        write(self.tmp, "journal.md", "| 101 | PASS | growth 3 |\n")

    def close(self, task="reef/features/demo/tasks/101-slice.md"):
        return subprocess.run([sys.executable, CLOSE, task, "--subject", "feat: the slice",
                               "--journal", self.journal, "--repo", self.feat], capture_output=True, text=True, cwd=self.feat)

    def _close_moves_no_plan_digest(self, tail):
        # 2026-10-29 (row 9 on the current adoption): every close voided the owner's approval — the journal block landed in
        # the body of a task without `## Log`, inside the digest. The review: whatever the body's last bytes are (no newline,
        # one, two), the close appends and the digest strips exactly that
        text = TASK.replace("attempts: 0\n", "attempts: 0\nworktree: .reef/worktrees/demo\n").replace("\n\n## Log\n", "\n")
        write(self.feat, "reef/features/demo/tasks/101-slice.md", text.rstrip("\n") + tail)
        digest = lambda: subprocess.run([sys.executable, PLAN_CHECK, self.feat, "--digest", "--feature", "demo"], capture_output=True, text=True).stdout.split()[-1]
        before = digest()
        self.assertRegex(before, r"^[0-9a-f]{64}$")
        self.assertEqual(self.close().returncode, 0)
        self.assertIn("<!-- journal -->", read(self.feat, "reef/features/demo/tasks/done/101-slice.md"))
        self.assertEqual(digest(), before, "the close is execution, not a plan edit")

    def test_the_close_moves_no_plan_digest(self):
        self._close_moves_no_plan_digest("\n")

    def test_the_close_moves_no_plan_digest_without_a_trailing_newline(self):
        self._close_moves_no_plan_digest("")

    def test_the_close_moves_no_plan_digest_after_a_blank_line(self):
        self._close_moves_no_plan_digest("\n\n")

    def test_the_close_commits_in_place_with_the_trailer_and_no_merge(self):
        r = self.close()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("fast path", r.stdout)
        self.assertEqual(len(git(self.feat, "rev-list", "--parents", "-1", "HEAD").stdout.split()), 2, "one plain commit, no merge")
        msg = git(self.feat, "log", "-1", "--format=%B", "HEAD").stdout
        self.assertIn("feat: the slice", msg); self.assertIn("Closes-task: 101-slice", msg)
        self.assertEqual(git(self.feat, "show", "HEAD:src/a.py").stdout, "a = 2\n")
        done = git(self.feat, "show", "HEAD:reef/features/demo/tasks/done/101-slice.md").stdout
        self.assertIn("status: done", done)
        self.assertIn("<!-- journal -->\n| 101 | PASS | growth 3 |\n<!-- /journal -->", done)
        self.assertEqual(git(self.feat, "ls-tree", "HEAD", "reef/features/demo/tasks/101-slice.md").stdout, "", "moved, not copied")
        self.assertEqual(git(self.feat, "status", "--porcelain").stdout, "")
        self.assertNotEqual(git(self.feat, "rev-parse", "-q", "--verify", "refs/heads/task/101-slice").returncode, 0, "no task branch was ever made")
        self.assertTrue(os.path.isdir(self.feat), "the feature worktree survives its own task's close")
        self.assertEqual(git(self.main, "rev-parse", "-q", "--verify", "refs/heads/feat/demo").returncode, 0, "and so does the feature branch")
        self.assertEqual(git(self.feat, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), "feat/demo")
        r = self.close()
        self.assertEqual((r.returncode, "already closed" in r.stdout), (0, True), "a second run changes nothing")

    def test_run_from_the_main_checkout_it_closes_in_the_worktree_holding_the_task(self):
        # 2026-10-31, the owner's project: four close jobs ran from the main checkout (on develop) with the task's path into
        # the feature worktree and were refused "not a feature branch" — each a wasted runner session and a re-run
        r = subprocess.run([sys.executable, CLOSE, ".reef/worktrees/demo/reef/features/demo/tasks/101-slice.md", "--subject",
                            "feat: the slice", "--journal", self.journal], capture_output=True, text=True, cwd=self.main)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("closed in place on feat/demo", r.stdout)
        self.assertIn("Closes-task: 101-slice", git(self.feat, "log", "-1", "--format=%B", "HEAD").stdout)
        self.assertEqual(git(self.main, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), "main")
        self.assertEqual(git(self.main, "status", "--porcelain").stdout, "", "the main checkout is untouched")

    def test_a_destination_already_taken_changes_nothing(self):
        write(self.feat, "reef/features/demo/tasks/done/101-slice.md", "stale\n")
        before = git(self.feat, "status", "--porcelain").stdout
        r = self.close()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("already exists", r.stderr)
        self.assertEqual(git(self.feat, "status", "--porcelain").stdout, before, "nothing staged, nothing rewritten")
        self.assertIn("status: in-progress", read(self.feat, "reef/features/demo/tasks/101-slice.md"))

    def test_a_close_killed_mid_commit_is_undone_by_the_next_close_then_closes_once(self):
        # 2026-11-07, an adopted project's task 4701: the session moved on while the gate ran (~40 s) and the close died after its `git mv`
        # and `status: done`, before its restore. The next close took the task under done/ as the task file, was refused by
        # the gate, said "nothing changed" and left ` D tasks/4701-….md`, `?? tasks/done/`
        before = git(self.feat, "status", "--porcelain").stdout
        gate(self.main, KILL.format(only=""))
        r = self.close()
        self.assertEqual(r.returncode, -9, "the close was killed in its own commit: " + r.stdout + r.stderr)
        settled(self.feat)
        self.assertFalse(os.path.exists(os.path.join(self.feat, "reef/features/demo/tasks/101-slice.md")), "the half-done state")
        self.assertIn("status: done", read(self.feat, "reef/features/demo/tasks/done/101-slice.md"))
        gate(self.main, "#!/bin/sh\necho 'gate: red' >&2; exit 1\n")
        r = self.close("reef/features/demo/tasks/done/101-slice.md")   # the path the tick's half-closed scan names
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(git(self.feat, "status", "--porcelain").stdout, before, "refused again: the tree as it was before the FIRST close")
        self.assertIn("status: in-progress", read(self.feat, "reef/features/demo/tasks/101-slice.md"))
        self.assertIn("cut off before its commit", r.stdout)
        gate(self.main, None)
        r = self.close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        done = git(self.feat, "show", "HEAD:reef/features/demo/tasks/done/101-slice.md").stdout
        self.assertEqual((done.count("status: done"), done.count("<!-- journal -->"), done.count("| 101 | PASS |")), (1, 1, 1))
        self.assertEqual(git(self.feat, "rev-list", "--count", "main..HEAD").stdout.strip(), "1", "the task committed once")
        self.assertEqual(git(self.feat, "ls-tree", "HEAD", "reef/features/demo/tasks/101-slice.md").stdout, "", "moved, not copied")
        self.assertEqual(git(self.feat, "status", "--porcelain").stdout, "")
        self.assertEqual(settled(self.feat), [], "no recovery note left")

    def test_a_task_under_done_never_committed_and_no_note_is_refused_not_taken_as_the_task(self):
        tasks = os.path.join(self.feat, "reef/features/demo/tasks")
        os.makedirs(os.path.join(tasks, "done"))
        git(self.feat, "mv", os.path.join(tasks, "101-slice.md"), os.path.join(tasks, "done", "101-slice.md"))
        write(tasks, "done/101-slice.md", read(tasks, "done/101-slice.md").replace("status: in-progress", "status: done"))
        before, head, text = git(self.feat, "status", "--porcelain").stdout, git(self.feat, "rev-parse", "HEAD").stdout, read(tasks, "done/101-slice.md")
        r = self.close()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("not committed", r.stderr)
        self.assertEqual((git(self.feat, "status", "--porcelain").stdout, git(self.feat, "rev-parse", "HEAD").stdout, read(tasks, "done/101-slice.md")),
                         (before, head, text), "nothing changed")

    def test_a_plan_never_committed_is_committed_when_its_first_task_starts_and_the_close_succeeds(self):
        """An adopted project, 2026-11-07 (row 242): the approved plan was written in the feature worktree and never
        committed; the first task's close failed on `git mv` of an untracked task file. `reef-graph.py worktree`, the
        step every build starts with, commits the feature's untracked or added plan files first."""
        write(self.feat, "reef/features/fresh/SPEC.md", "# fresh\nRow: 2\n")
        write(self.feat, "reef/features/fresh/tasks/201-first.md",
              TASK.replace("id: 101", "id: 201").replace("feature: demo", "feature: fresh").replace("101 — the slice", "201 — the first"))
        git(self.feat, "add", "reef/features/fresh/SPEC.md")   # one staged, one untracked: both are an uncommitted plan
        task = "reef/features/fresh/tasks/201-first.md"
        r = subprocess.run([sys.executable, GRAPH, "worktree", task], capture_output=True, text=True, cwd=self.feat)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("plan committed", r.stdout)
        self.assertNotRegex(git(self.feat, "status", "--porcelain", "--", "reef/features/fresh").stdout, r"(?m)^(\?\?|A)",
                            "nothing of the plan is untracked or only staged (the task's own `worktree:` key is an edit)")
        self.assertIn("reef/features/fresh/tasks/201-first.md", git(self.feat, "show", "--name-only", "--format=", "HEAD").stdout)
        self.assertNotIn("src/a.py", git(self.feat, "show", "--name-only", "--format=", "HEAD").stdout, "only the plan's files")
        write(self.tmp, "journal.md", "| 201 | PASS | growth 3 |\n")
        r = self.close(task)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.feat, "reef/features/fresh/tasks/done/201-first.md")))
        r = subprocess.run([sys.executable, GRAPH, "worktree", "reef/features/demo/tasks/101-slice.md"], capture_output=True, text=True, cwd=self.feat)
        self.assertNotIn("plan committed", r.stdout, "a committed plan is left alone")

    def test_a_flat_tasks_folder_commits_only_its_own_new_files_never_the_repo(self):
        """CI, PR 370: with `tasks/` at the repo root the feature folder resolved to the root, and the plan commit took
        every untracked file in the repository. The plan is the tasks folder there."""
        flat = tempfile.mkdtemp(prefix="reef-flat.")
        git(flat, "init", "-q", "-b", "main")
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            git(flat, "config", k, v)
        write(flat, "tasks/101-slice.md", open(os.path.join(self.feat, "reef/features/demo/tasks/101-slice.md")).read())
        write(flat, "README.md", "x\n")
        git(flat, "add", "-A"); git(flat, "commit", "-qm", "init")
        write(flat, "tasks/102-next.md", TASK.replace("id: 101", "id: 102").replace("101 — the slice", "102 — the next"))
        write(flat, "scratch.txt", "not the plan\n")
        r = subprocess.run([sys.executable, GRAPH, "worktree", "tasks/101-slice.md"], capture_output=True, text=True, cwd=flat)
        self.assertIn("plan committed", r.stdout, r.stdout + r.stderr)
        head = git(flat, "show", "--name-only", "--format=", "HEAD").stdout
        self.assertIn("tasks/102-next.md", head)
        self.assertNotIn("scratch.txt", head, "never a file outside the plan")
        self.assertIn("?? scratch.txt", git(flat, "status", "--porcelain").stdout)

    def test_a_secret_shaped_file_is_refused_in_place_too(self):
        write(self.feat, ".env.local", "KEY=1\n")
        r = self.close()
        self.assertEqual(r.returncode, 2)
        self.assertIn("refusing to commit .env.local", r.stderr)
        self.assertEqual(git(self.feat, "diff", "--cached", "--name-only").stdout, "", "nothing left staged")


class MergeClose(unittest.TestCase):
    """A main checkout on main, a feature worktree on feat/demo, a task worktree under the MAIN checkout's .reef/worktrees."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reef-mc.")
        self.main = os.path.join(self.tmp, "main")
        subprocess.run(["git", "init", "-q", "-b", "main", self.main], check=True)
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            subprocess.run(["git", "-C", self.main, "config", k, v], check=True)
        write(self.main, ".reef/config.json", '{"branches": {"base": "main"}, "worktree": {"setup": "echo ran >> setup.log"}}')
        write(self.main, ".gitignore", "setup.log\n.reef/worktrees/\n")
        write(self.main, "reef/features/demo/tasks/101-slice.md", TASK)
        write(self.main, "src/a.py", "a = 1\n")
        write(self.main, "package-lock.json", "{}\n")
        git(self.main, "add", "-A"); git(self.main, "commit", "-qm", "init")
        self.feat = os.path.join(self.tmp, "feat")
        self.assertEqual(git(self.main, "worktree", "add", "-q", "-b", "feat/demo", self.feat, "main").returncode, 0)
        self.wt = os.path.join(self.main, ".reef", "worktrees", "101")
        self.assertEqual(git(self.main, "worktree", "add", "-q", "-b", "task/101-slice", self.wt, "feat/demo").returncode, 0)
        write(self.feat, "reef/features/demo/tasks/101-slice.md", TASK.replace("attempts: 0\n", "attempts: 0\nworktree: .reef/worktrees/101\n"))
        write(self.wt, "src/a.py", "a = 2\n")                     # the implementer's uncommitted work
        write(self.wt, "tests/test_a.py", "def test_a(): pass\n")
        write(self.wt, "package-lock.json", '{"dep": 1}\n')
        self.journal = os.path.join(self.tmp, "journal.md")
        write(self.tmp, "journal.md", "| 101 | PASS | growth 3 |\n")

    def close(self):
        return subprocess.run([sys.executable, CLOSE, "reef/features/demo/tasks/101-slice.md", "--subject", "feat: the slice",
                               "--journal", self.journal, "--repo", self.feat], capture_output=True, text=True, cwd=self.feat)

    def untouched(self):
        self.assertEqual(git(self.feat, "status", "--porcelain").stdout, " M reef/features/demo/tasks/101-slice.md\n")
        self.assertIn("status: in-progress", read(self.feat, "reef/features/demo/tasks/101-slice.md"))
        self.assertFalse(os.path.exists(os.path.join(self.feat, "reef/features/demo/tasks/done/101-slice.md")))
        self.assertTrue(os.path.isdir(self.wt))
        self.assertEqual(git(self.feat, "rev-parse", "-q", "--verify", "refs/heads/task/101-slice").returncode, 0)

    def test_one_command_commits_merges_closes_and_cleans_up(self):
        r = self.close()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("staged in the task worktree: package-lock.json, src/a.py, tests/test_a.py", r.stdout)
        self.assertEqual(len(git(self.feat, "rev-list", "--parents", "-1", "HEAD").stdout.split()), 3, "a --no-ff merge commit")
        task_msg = git(self.feat, "log", "-1", "--format=%B", "HEAD^2").stdout
        self.assertIn("feat: the slice", task_msg); self.assertIn("Closes-task: 101-slice", task_msg)
        self.assertEqual(git(self.feat, "show", "HEAD:src/a.py").stdout, "a = 2\n")
        done = git(self.feat, "show", "HEAD:reef/features/demo/tasks/done/101-slice.md").stdout
        self.assertIn("status: done", done); self.assertIn("worktree: .reef/worktrees/101", done)
        self.assertIn("## Log\n\n<!-- journal -->\n| 101 | PASS | growth 3 |\n<!-- /journal -->\n", done)
        self.assertEqual(git(self.feat, "ls-tree", "HEAD", "reef/features/demo/tasks/101-slice.md").stdout, "", "moved, not copied")
        self.assertEqual(read(self.feat, "setup.log"), "ran\n", "worktree.setup ran in the feature worktree: a lockfile changed")
        self.assertEqual(git(self.feat, "status", "--porcelain").stdout, "")
        self.assertFalse(os.path.exists(self.wt))
        self.assertNotEqual(git(self.feat, "rev-parse", "-q", "--verify", "refs/heads/task/101-slice").returncode, 0)
        r = self.close()
        self.assertEqual((r.returncode, "already closed" in r.stdout), (0, True), "a second run changes nothing")
        self.assertEqual(git(self.feat, "rev-list", "--count", "HEAD").stdout.strip(), "3")

    def test_a_journal_block_with_its_own_markers_or_no_row_is_refused_with_nothing_changed(self):
        # 2026-11-02 (ai-coach row 191, graph mode): the mechanic's journal files for 19104-19108 carried their own
        # `<!-- journal -->` lines and a prose line, no `| id |` row; the close wrapped them as they were, so plan-check
        # failed 5 checks at the feature head and `reef-queue.py journal` had no row to copy.
        for block, why in (("<!-- journal -->\n| 101 | PASS | growth 3 |\n<!-- journal -->\n", "marker"),
                           ("- 101 closed 2026-11-02 · graph mode · 3 rounds\n", "| 101 |")):
            write(self.tmp, "journal.md", block)
            head = git(self.feat, "rev-parse", "HEAD").stdout
            r = self.close()
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn(why, r.stderr)
            self.assertEqual(git(self.feat, "rev-parse", "HEAD").stdout, head)
            self.untouched()

    def test_a_conflict_aborts_with_nothing_changed(self):
        write(self.feat, "src/a.py", "a = 3\n")
        git(self.feat, "add", "src/a.py"); git(self.feat, "commit", "-qm", "the feature moved on")
        head = git(self.feat, "rev-parse", "HEAD").stdout
        r = self.close()
        self.assertEqual(r.returncode, 2)
        self.assertIn("CONFLICT in src/a.py", r.stderr)
        self.assertEqual(git(self.feat, "rev-parse", "HEAD").stdout, head)
        self.untouched()
        self.assertEqual(read(self.feat, "src/a.py"), "a = 3\n")

    def test_a_gate_refusing_the_merge_commit_leaves_the_tree_as_it_was(self):
        hook = os.path.join(self.main, ".git", "hooks", "pre-commit")
        os.makedirs(os.path.dirname(hook), exist_ok=True)
        write(self.main, ".git/hooks/pre-commit", "#!/bin/sh\ngit rev-parse --abbrev-ref HEAD | grep -q '^feat/' && { echo 'gate: red' >&2; exit 1; }\nexit 0\n")
        os.chmod(hook, 0o755)
        head = git(self.feat, "rev-parse", "HEAD").stdout
        r = self.close()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("refused by the gate", r.stderr); self.assertIn("gate: red", r.stderr)
        self.assertEqual(git(self.feat, "rev-parse", "HEAD").stdout, head)
        self.untouched()
        self.assertEqual(git(self.wt, "status", "--porcelain").stdout, "", "the task's own commit stands; a re-run resumes from the merge")

    def test_a_merge_commit_killed_mid_gate_is_undone_by_the_next_close_then_merges_once(self):
        gate(self.main, KILL.format(only="git rev-parse --abbrev-ref HEAD | grep -q '^feat/' || exit 0\n"))
        r = self.close()
        self.assertEqual(r.returncode, -9, "killed in the merge commit: " + r.stdout + r.stderr)
        settled(self.feat)
        self.assertEqual(git(self.feat, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode, 0, "precondition: the merge half-done")
        gate(self.main, None)
        r = self.close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        done = git(self.feat, "show", "HEAD:reef/features/demo/tasks/done/101-slice.md").stdout
        self.assertIn("worktree: .reef/worktrees/101", done, "the task file's own uncommitted edit survived the recovery")
        self.assertEqual((done.count("<!-- journal -->"), git(self.feat, "rev-list", "--merges", "--count", "HEAD").stdout.strip()), (1, "1"))
        self.assertEqual(git(self.feat, "ls-tree", "HEAD", "reef/features/demo/tasks/101-slice.md").stdout, "", "moved, not copied")
        self.assertEqual(git(self.feat, "status", "--porcelain").stdout, "")
        self.assertIn("cut off before its commit", r.stdout)
        self.assertEqual(settled(self.feat), [], "no recovery note left")

    def test_a_judged_task_on_the_critical_path_closes_only_with_the_verifiers_pass_report(self):
        # workflow v3, phase 3b: the critical path keeps a verifier per task, and its close now REQUIRES the report (before,
        # the skill asked for it and nothing checked)
        judged = TASK.replace("attempts: 0\n", "attempts: 0\nworktree: .reef/worktrees/101\nverify: judge\n").replace("complexity: mech\ntier: light", "complexity: design\ntier: critical")
        write(self.feat, "reef/features/demo/tasks/101-slice.md", judged + "\n## Decision\nhuman words\n")
        r = self.close()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("verifier's PASS report", r.stderr)
        self.assertEqual(git(self.feat, "rev-parse", "-q", "--verify", "refs/heads/task/101-slice").returncode, 0, "nothing merged")
        write(self.wt, ".reef/ci-local/report-101.md", "RUN: agent=verifier task=101\nRULE AC1: PASS iff x\nVERDICT: FAIL\n")
        r = self.close()
        self.assertEqual(r.returncode, 2, "a FAIL report closes nothing")
        write(self.wt, ".reef/ci-local/report-101.md", "RUN: agent=verifier task=101\nRULE AC1: PASS iff x\nVERDICT: PASS\n")
        write(self.wt, ".gitignore", ".reef/ci-local/\n")
        # the review (2026-10-26): a PASS older than the last hand-back is round 1's verdict on round 2's code
        import time
        time.sleep(0.05)
        write(self.wt, ".reef/ci-local/handback-101.md", "RUN: agent=implementer task=101\nround 2\n")
        r = self.close()
        self.assertEqual(r.returncode, 2, "a report older than the hand-back is stale: " + r.stdout + r.stderr)
        self.assertIn("predates", r.stderr)
        time.sleep(0.05)
        os.utime(os.path.join(self.wt, ".reef", "ci-local", "report-101.md"), None)
        r = self.close()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_a_secret_shaped_file_in_the_task_worktree_is_refused(self):
        write(self.wt, ".env.local", "KEY=1\n")
        r = self.close()
        self.assertEqual(r.returncode, 2)
        self.assertIn(".env.local", r.stderr)
        self.untouched()
        self.assertEqual(git(self.wt, "diff", "--cached", "--name-only").stdout, "", "nothing left staged")


if __name__ == "__main__":
    unittest.main()
