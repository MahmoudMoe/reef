"""Stress: several checkouts of one truth. The main checkout, a feature worktree (.reef/worktrees/<slug>, feat/<slug>) and a
task worktree (.reef/worktrees/<id>, task/<id>) each carry their own copy of the task files, the markers, the hand-backs,
the stamp and the config. Each scenario builds a divergence between copies with the real scripts and git, fakes only the
agents' files, and asserts what Reef's own contract says the engine decides. A failing test is a finding
(docs/review/stress-2026-11-02.md); a passing one pins the behaviour."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import write, git, ROOT  # noqa: E402
from test_loop import project, task, approve, loop  # noqa: E402

DOCTOR = os.path.join(ROOT, "scripts", "reef-doctor.py")
CLOSE = os.path.join(ROOT, "scripts", "reef-merge-close")
ATTEMPT = os.path.join(ROOT, "scripts", "reef-attempt")
QUEUE = os.path.join(ROOT, "scripts", "reef-queue.py")


def tick(d):
    r = loop(d, "tick", "--json")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def feature_wt(d, slug, branch=None):
    w = os.path.join(d, ".reef", "worktrees", slug)
    git(d, "worktree", "add", "-q", "-b", branch or f"feat/{slug}", w, "main", check=True)
    return w


def age(p, minutes):
    old = time.time() - minutes * 60
    os.utime(p, (old, old))


SPEC = ("# first row slice\nRow: 1\n\n## Scope\nOne slice.\n\n## Non-goals\n- none\n\n## Already shipped\nnone\n\n"
        "## Requirements\n- FR-1 [backend]: it works.\n\n## Success criteria\n- SC-1: green.\n\n## Architecture impact\nnone\n")


def ftask(tid, status="pending", blocked="[]"):
    """A task of the feature folder: its criterion cites FR-1 (reef-plan-check's key rule)."""
    return task(tid, "first-row-slice", status=status, blocked=blocked).replace(f"- test_t{tid} goes red first", f"- AC-1 (FR-1): test_t{tid} goes red first")


def approve_wt(d, w, feature):
    """The plan on feat/<slug> reviewed (the stamp, per checkout, in the worktree) and approved (the record, in MAIN)."""
    pc = os.path.join(d, "scripts", "reef-plan-check.py")
    r = subprocess.run([sys.executable, pc, w], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    digest = subprocess.run([sys.executable, pc, w, "--digest", "--feature", feature], capture_output=True, text=True).stdout.split()[-1]
    write(d, f".reef/approvals/{feature}.json", json.dumps({"digest16": digest[:16], "approved_at": "2026-10-16T00:00:00Z"}))


def plan_only_in_worktree(done=False):
    """The contract's layout (reef-plan §1a: "Every plan file is written IN that worktree ... the tick sees the plan from its
    first line"): the main checkout carries no task of row 1; feat/first carries reef/features/first-row-slice with SPEC `Row: 1`."""
    d = project()
    git(d, "rm", "-q", "-r", "tasks/101-a.md", "tasks/102-b.md", check=True)
    git(d, "commit", "-qm", "the plan lives on its feature branch", check=True)
    w = feature_wt(d, "first")
    st = "done" if done else "pending"
    sub = "tasks/done" if done else "tasks"
    write(w, "reef/features/first-row-slice/SPEC.md", SPEC)
    write(w, f"reef/features/first-row-slice/{sub}/101-a.md", ftask(101, status=st))
    write(w, f"reef/features/first-row-slice/{sub}/102-b.md", ftask(102, status=st, blocked="[101]"))
    git(w, "add", "-A", check=True)
    git(w, "commit", "-qm", "plan", check=True)
    return d, w


class Markers(unittest.TestCase):
    @unittest.expectedFailure   # open: H2 (docs/review/stress-2026-11-02.md)
    def test_a_stale_marker_in_main_does_not_shadow_a_fresh_one_in_the_feature_worktree(self):
        # reef-loop.py all_roots: "reef-attempt runs where the task file lives, so its in-flight marker lands in that worktree's
        # .reef/"; graph-run writes .reef/inflight/<id> in the MAIN checkout (reef-graph-run.py:232). Round 1 in the graph died
        # (main's marker goes stale), round 2 runs in chat (the guard's marker in the feature worktree, fresh). The task is in
        # flight: the tick must not list it as returned nor offer it to a second implementer.
        d = project()
        w = feature_wt(d, "first")
        p = write(d, ".reef/inflight/101", json.dumps({"id": 101, "tier": "light"}))
        age(p, 200)
        write(w, ".reef/inflight/101", json.dumps({"id": 101, "tier": "light"}))
        st = tick(d)
        self.assertIn("101", st["in_flight"], st)
        self.assertNotIn("101", st["returned_unmerged"])
        self.assertNotIn("101", st["dispatch_now"], "a second implementer on a task in flight")

    def test_a_stale_marker_in_a_task_worktree_is_returned(self):
        # reef-loop.py docstring: "in flight from .reef/inflight/ — stale after loop.inflight_stale_minutes = returned"
        d = project()
        tw = os.path.join(d, ".reef", "worktrees", "101")
        git(d, "worktree", "add", "-q", "-b", "task/101-a", tw, "main", check=True)
        p = write(tw, ".reef/inflight/101", json.dumps({"id": 101, "tier": "light"}))
        self.assertIn("101", tick(d)["in_flight"])
        age(p, 200)
        st = tick(d)
        self.assertEqual(st["returned_unmerged"], ["101"])
        self.assertIn("101", st["dispatch_now"])


class HandBacks(unittest.TestCase):
    @unittest.expectedFailure   # open: H2 (docs/review/stress-2026-11-02.md)
    def test_a_handback_in_the_task_worktree_judged_by_a_report_in_main_is_not_verified_again(self):
        # reef-loop.py tick: "a ready task whose implementer already handed back (handback-<id>.md in any checkout's
        # .reef/ci-local, with no report newer than it) is not to DISPATCH but to VERIFY". reef-attempt prints the hand-back
        # path "in the task worktree"; reef-task §36 has the orchestrator write the judge's report to
        # `.reef/ci-local/report-<task>.md` — from its own cwd, the main checkout. A report newer than the hand-back, in any
        # checkout, judged that round (the same lesson as PR 295's FAIL line in another copy).
        d = project()
        tw = os.path.join(d, ".reef", "worktrees", "101")
        git(d, "worktree", "add", "-q", "-b", "task/101-a", tw, "main", check=True)
        write(tw, ".reef/ci-local/handback-101.md", "RUN: agent=implementer task=101\nclaims\n")
        self.assertEqual(tick(d)["verify_now"], ["101"])
        time.sleep(0.05)
        write(d, ".reef/ci-local/report-101.md", "RUN: agent=verifier task=101\nVERDICT: PASS\n")
        st = tick(d)
        self.assertEqual(st["verify_now"], [], "the verifier's report is newer than the hand-back: the round was judged")

    def test_a_handback_judged_in_its_own_checkout_is_not_verified_again(self):
        # coverage: the same pair inside one task worktree
        d = project()
        tw = os.path.join(d, ".reef", "worktrees", "101")
        git(d, "worktree", "add", "-q", "-b", "task/101-a", tw, "main", check=True)
        write(tw, ".reef/ci-local/handback-101.md", "RUN: agent=implementer task=101\n")
        time.sleep(0.05)
        write(tw, ".reef/ci-local/report-101.md", "RUN: agent=verifier task=101\nVERDICT: PASS\n")
        self.assertEqual(tick(d)["verify_now"], [])


class DivergingTaskCopies(unittest.TestCase):
    @unittest.expectedFailure   # open: H1 (docs/review/stress-2026-11-02.md)
    def test_a_task_done_on_the_feature_branch_is_not_offered_again_from_mains_copy(self):
        # reef-loop.py tick: "a feature's plan lives on its branch, in its worktree, until the row closes: the main checkout's
        # graph does not see it". A project whose plan was committed on the base (the flat tasks/ layout the loop's own
        # fixture uses) builds row 1 on feat/first: 101 merges there (status done). Main's copy still says pending. The
        # feature branch is the plan's home; 101 is not to be dispatched again.
        d = project()
        w = feature_wt(d, "first")
        approve(w, "1")
        write(w, "tasks/101-a.md", task(101, "1", status="done"))
        st = tick(d)
        self.assertNotIn("101", st["dispatch_now"], st)
        self.assertIn("102", st["dispatch_now"], "its dependant is ready on the feature branch")

    @unittest.expectedFailure   # open: H1 (docs/review/stress-2026-11-02.md)
    def test_a_broken_graph_in_a_feature_worktree_is_named_broken(self):
        # reef-graph.py: "A broken graph (duplicate id, dangling blocked-by, cycle) has NO ready set: `check` denies and
        # `ready` exits 1, never a best-effort subset"; the tick names main's as BROKEN. A half-resolved merge left 101 under
        # tasks/ AND tasks/done/ in the feature worktree, where the plan lives: the loop must say so, not "nothing ready".
        d, w = plan_only_in_worktree()
        approve_wt(d, w, "first-row-slice")
        self.assertIn("101", tick(d)["dispatch_now"])
        write(w, "reef/features/first-row-slice/tasks/done/101-a.md", ftask(101, status="done"))
        st = tick(d)
        self.assertTrue(any("graph" in b for b in st["broken"]), st)

    @unittest.expectedFailure   # open: H1 (docs/review/stress-2026-11-02.md)
    def test_a_row_whose_tasks_are_all_done_on_its_branch_is_named_for_review(self):
        # KNOWN OPEN BUG (brief): the tick says "nothing ready" when a row's tasks are all done on its feature branch and no PR
        # exists. reef-loop SKILL step 3: after the build, `/reef-review <feature>` opens the PR; reef-row.py: build ->
        # evidence -> review. The tick, "the ONE read" of state, must name the row's next step.
        d, w = plan_only_in_worktree(done=True)
        text = loop(d, "tick").stdout
        nxt = [l for l in text.splitlines() if l.startswith("next:")][0]
        self.assertNotIn("nothing ready", nxt, text)
        self.assertIn("1", nxt, text)

    @unittest.expectedFailure   # open: H1 (docs/review/stress-2026-11-02.md)
    def test_reef_queue_status_reads_a_row_built_in_its_worktree_as_building(self):
        # contract silent. reef-queue.py: "status DERIVED from the task files"; the plan's task files live in the feature
        # worktree (reef-plan §1a). `reef-queue.py status` in the main checkout calls row 1 `queued` while its tasks are in
        # progress on feat/first (the tick patches this with planned_elsewhere; the owner's own command does not).
        d, w = plan_only_in_worktree()
        r = subprocess.run([sys.executable, QUEUE, "status", "--repo", d], capture_output=True, text=True)
        row1 = [l for l in r.stdout.splitlines() if l.startswith("1\t")][0]
        self.assertNotIn("\tqueued\t", row1, r.stdout)


class WorktreesGoneOrOrphaned(unittest.TestCase):
    def test_the_tick_survives_a_feature_worktree_deleted_by_hand(self):
        # coverage: git still lists the worktree (prunable); every reader of it must keep going
        d = project()
        w = feature_wt(d, "first")
        shutil.rmtree(w)
        r = loop(d, "tick", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = json.loads(r.stdout)
        self.assertEqual(st["dispatch_now"], ["101"])
        self.assertEqual(st["broken"], [])

    @unittest.expectedFailure   # open: M2 (docs/review/stress-2026-11-02.md)
    def test_the_doctor_names_a_worktree_whose_directory_is_gone(self):
        # contract silent. reef-doctor SKILL: "One screen on what is wrong ... worktrees ... and the command that fixes each
        # thing". A worktree deleted by hand stays registered (git refuses `branch -d` on its branch until it is pruned).
        d = project()
        w = feature_wt(d, "first")
        shutil.rmtree(w)
        env = dict(os.environ, PATH="/nonexistent-gh:" + os.environ["PATH"])
        r = subprocess.run([sys.executable, DOCTOR, "--repo", d, "--plugin", ROOT], capture_output=True, text=True, env=env)
        line = [l for l in r.stdout.splitlines() if "worktrees/first" in l]
        self.assertTrue(line, r.stdout)
        self.assertNotRegex(line[0], r"^\s*OK\b", r.stdout)
        self.assertIn("prune", r.stdout)

    @unittest.expectedFailure   # open: H1 (docs/review/stress-2026-11-02.md)
    def test_a_feature_branch_without_its_worktree_is_not_a_row_to_plan(self):
        # contract silent. The plan of row 1 sits committed on feat/first; its worktree was removed (by hand, or a
        # half-finished cleanup). The tick says "plan: 1" — /reef-plan §1a would `git branch feat/first` over a branch that
        # carries an approved plan. An owner expects the tick to name the orphaned branch, never to plan the row afresh.
        d, w = plan_only_in_worktree()
        git(d, "worktree", "remove", "--force", w, check=True)
        self.assertEqual(git(d, "rev-parse", "-q", "--verify", "refs/heads/feat/first").returncode, 0)
        st = tick(d)
        self.assertNotIn("1", st["rows_to_plan"], st)

    @unittest.expectedFailure   # open: M2 (docs/review/stress-2026-11-02.md)
    def test_merge_close_finishes_after_the_task_worktree_was_deleted_by_hand(self):
        # reef-merge-close: "In order, each step skipped when already done ... (4) `git worktree remove`, `git branch -d`,
        # `git worktree prune`". The merge commit landed (steps 1-3); the task worktree's directory was then deleted by hand.
        # A re-run must finish step 4.
        tmp = tempfile.mkdtemp(prefix="reef-stress-mc.")
        main = os.path.join(tmp, "main")
        subprocess.run(["git", "init", "-q", "-b", "main", main], check=True)
        write(main, ".reef/config.json", '{"branches": {"base": "main"}}')
        write(main, ".gitignore", ".reef/worktrees/\n")
        t = task(101, "demo", status="in-progress").replace("verify: gate-only", "verify: gate-only")
        write(main, "reef/features/demo/tasks/101-slice.md", t)
        write(main, "src/a.py", "a = 1\n")
        git(main, "add", "-A", check=True); git(main, "commit", "-qm", "init", check=True)
        feat = os.path.join(tmp, "feat")
        git(main, "worktree", "add", "-q", "-b", "feat/demo", feat, "main", check=True)
        tw = os.path.join(main, ".reef", "worktrees", "101")
        git(main, "worktree", "add", "-q", "-b", "task/101-slice", tw, "feat/demo", check=True)
        write(tw, "src/a.py", "a = 2\n")
        git(tw, "commit", "-qam", "the slice", check=True)
        # steps 2-3 as the close does them: merge --no-ff, status done, git mv to done/, one commit
        git(feat, "merge", "--no-ff", "--no-commit", "task/101-slice", check=True)
        src = os.path.join(feat, "reef/features/demo/tasks/101-slice.md")
        with open(src, encoding="utf-8") as f:
            body = f.read().replace("status: in-progress", "status: done")
        with open(src, "w", encoding="utf-8") as f:
            f.write(body)
        os.makedirs(os.path.join(feat, "reef/features/demo/tasks/done"), exist_ok=True)
        git(feat, "mv", "reef/features/demo/tasks/101-slice.md", "reef/features/demo/tasks/done/101-slice.md", check=True)
        git(feat, "add", "-A", check=True)
        git(feat, "commit", "-qm", "merge task/101-slice", check=True)
        shutil.rmtree(tw)   # the owner tidied up by hand
        write(tmp, "journal.md", "| 101 | PASS | growth 3 |\n")
        r = subprocess.run([sys.executable, CLOSE, "reef/features/demo/tasks/101-slice.md", "--subject", "feat: the slice",
                            "--journal", os.path.join(tmp, "journal.md"), "--repo", feat], capture_output=True, text=True, cwd=feat)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotEqual(git(feat, "rev-parse", "-q", "--verify", "refs/heads/task/101-slice").returncode, 0, "the branch is removed")


class StampsApprovalsConfig(unittest.TestCase):
    def test_an_approval_written_in_a_worktree_approves_nothing(self):
        # reef-plan-check.py: "The approvals live in the MAIN checkout's .reef/, never a worktree's."
        d = project()
        w = feature_wt(d, "first")
        rec = open(os.path.join(d, ".reef", "approvals", "1.json")).read()
        os.unlink(os.path.join(d, ".reef", "approvals", "1.json"))
        write(w, ".reef/approvals/1.json", rec)
        st = tick(d)
        self.assertNotIn("101", st["dispatch_now"], st)
        self.assertTrue(any(a.startswith("1 (approval") for a in st["awaiting"]), st["awaiting"])

    def test_a_stamp_in_main_only_does_not_release_the_worktrees_plan(self):
        # reef-plan-check.py: "The stamp is per-worktree state" — main's stamp says nothing of the plan on feat/first
        d, w = plan_only_in_worktree()
        subprocess.run([sys.executable, os.path.join(d, "scripts", "reef-plan-check.py"), d], capture_output=True, text=True)
        st = tick(d)
        self.assertEqual(st["dispatch_now"], [], st)
        self.assertTrue(any(a.startswith("first-row-slice (") for a in st["awaiting"]), st["awaiting"])
        approve_wt(d, w, "first-row-slice")
        self.assertEqual(tick(d)["dispatch_now"], ["101"])

    def test_the_attempt_reads_hunter_policy_from_main_not_the_lagging_worktree(self):
        # reef-attempt: "loop policy has ONE home, the main checkout ... the feature worktree's copy of the config predated it"
        d = project()
        w = feature_wt(d, "first")
        cfg = json.loads(open(os.path.join(d, ".reef", "config.json")).read())
        cfg["hunter"] = {"guard_pass": "feature"}
        write(d, ".reef/config.json", json.dumps(cfg))
        write(w, "tasks/101-a.md", task(101, "1").replace("tier: light", "tier: design"))
        r = subprocess.run([sys.executable, ATTEMPT, os.path.join(w, "tasks", "101-a.md")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("guard-pass: feature", r.stdout)
        self.assertNotIn("adversary:", r.stdout)

    @unittest.expectedFailure   # open: H5 (docs/review/stress-2026-11-02.md)
    def test_the_tick_from_inside_a_feature_worktree_reads_the_loops_one_state(self):
        # contract silent on the tick, explicit for its neighbours: reef_common.main_checkout "Machine state (approvals,
        # records, the queue, the slot locks) lives there, never in a task worktree"; the Stop hook ticks the MAIN checkout
        # (reef-guard check_stop). A session whose cwd is the feature worktree runs `reef-loop.py tick` there: it must see the
        # loop the owner started in main (active), not a fresh inactive loop.json of its own.
        d = project()
        w = feature_wt(d, "first")
        loop(d, "start")
        st = json.loads(loop(w, "tick", "--json").stdout)
        self.assertTrue(st["active"], "the loop is active in the main checkout")


if __name__ == "__main__":
    unittest.main()
