"""Sabotage suite for scripts/reef-graph.py and the guard's graph check.

The invariant (docs/design/graph-and-setup.md §1): no implementer runs on a task
outside the ready set. Every DENY here is a dispatch that an orchestrator running
tasks "in blocked-by order from memory" could issue — shown red at the guard.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, "scripts", "reef-guard.py")
GRAPH = os.path.join(ROOT, "scripts", "reef-graph.py")


def task(dirpath, id_, status="pending", deps=(), resources=(), attempts=0, done=False, slug="t"):
    sub = os.path.join("tasks", "done") if done else "tasks"
    p = os.path.join(dirpath, sub, f"{int(id_):03d}-{slug}.md")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(f"---\nid: {int(id_)}\nfeature: demo\nstatus: {status}\ncomplexity: mech\neffort: medium\n"
                f"blocked-by: [{', '.join(str(d) for d in deps)}]\nresources: [{', '.join(resources)}]\n"
                f"verify: gate-only\nattempts: {attempts}\ndispatches: 0\nlast_failure_sig: \"\"\n---\n"
                f"# {id_}\n\n## Scope\nx\n\n## Acceptance Criteria\n- test_x_{id_} goes red first\n\n## Log\n")
    return p


def config(dirpath, **cfg):
    os.makedirs(os.path.join(dirpath, ".reef"), exist_ok=True)
    with open(os.path.join(dirpath, ".reef", "config.json"), "w") as f:
        json.dump(cfg, f)


def dispatch(cwd, path):
    return subprocess.run([sys.executable, GUARD], input=json.dumps(
        {"tool_name": "Task", "cwd": cwd,
         "tool_input": {"subagent_type": "reef:implementer", "prompt": f"REEF-TASK: {path}\nimplement"}}),
        capture_output=True, text=True, timeout=60)


def graph(*args, cwd=None):
    return subprocess.run([sys.executable, GRAPH, *args], capture_output=True, text=True, cwd=cwd, timeout=60)


def frontmatter(path):
    with open(path) as f:
        return f.read().split("---\n")[1]


class GuardGraph(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-graph-test.")
        config(self.d, gates={"test": "true"})

    # --- the defect this change exists to catch
    def test_undone_dependency_denied(self):
        task(self.d, 1)
        p = task(self.d, 2, deps=[1])
        r = dispatch(self.d, p)
        self.assertEqual(r.returncode, 2, "task 2 blocked-by an undone task 1 must NOT dispatch")
        self.assertIn("blocked-by not done", r.stderr)
        self.assertIn("status: pending", frontmatter(p))   # a denial changes nothing

    def test_done_dependency_allows(self):
        task(self.d, 1, status="done", done=True)
        p = task(self.d, 2, deps=[1])
        r = dispatch(self.d, p)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_dispatch_marks_in_progress(self):
        p = task(self.d, 1)
        self.assertEqual(dispatch(self.d, p).returncode, 0)
        fm = frontmatter(p)
        self.assertIn("status: in-progress", fm)
        self.assertIn("dispatches: 1", fm)

    def test_missing_dependency_denied(self):
        p = task(self.d, 2, deps=[9])
        r = dispatch(self.d, p)
        self.assertEqual(r.returncode, 2)
        self.assertIn("missing task id", r.stderr)

    def test_cycle_denied(self):
        task(self.d, 1, deps=[2])
        p = task(self.d, 2, deps=[1])
        r = dispatch(self.d, p)
        self.assertEqual(r.returncode, 2)
        self.assertIn("cycle", r.stderr)

    def test_duplicate_id_denied(self):
        task(self.d, 1, slug="a")
        p = task(self.d, 1, slug="b")
        r = dispatch(self.d, p)
        self.assertEqual(r.returncode, 2)
        self.assertIn("duplicate", r.stderr)

    def test_done_task_denied(self):
        p = task(self.d, 1, status="done", done=True)
        r = dispatch(self.d, p)
        self.assertEqual(r.returncode, 2)
        self.assertIn("status is 'done'", r.stderr)

    # --- resources
    def test_resource_held_denied_then_freed(self):
        held = task(self.d, 1, status="in-progress", resources=["db"])
        p = task(self.d, 2, resources=["db"])
        r = dispatch(self.d, p)
        self.assertEqual(r.returncode, 2, "db is held by task 1 — 2 must wait")
        self.assertIn("resource 'db' held by task(s) 1", r.stderr)
        with open(held) as f:
            text = f.read()
        with open(held, "w") as f:   # 1 finishes
            f.write(text.replace("status: in-progress", "status: done"))
        self.assertEqual(dispatch(self.d, p).returncode, 0)

    def test_resource_slots_from_config(self):
        config(self.d, gates={"test": "true"}, resources={"heavy": {"slots": 2}})
        task(self.d, 1, status="in-progress", resources=["heavy"])
        p = task(self.d, 2, resources=["heavy"])
        self.assertEqual(dispatch(self.d, p).returncode, 0, "two slots: the second holder fits")
        p3 = task(self.d, 3, resources=["heavy"])
        r = dispatch(self.d, p3)
        self.assertEqual(r.returncode, 2, "the third holder of a 2-slot resource must wait")

    def test_self_exclusion_retry_holds_its_own_resource(self):
        # after a FAIL the task is in-progress and holds db: its retry must not block on itself
        config(self.d, gates={"test": "true"}, graph={"parallel": 1})
        p = task(self.d, 1, status="in-progress", resources=["db"], attempts=1)
        r = dispatch(self.d, p)
        self.assertEqual(r.returncode, 0, f"a retry self-blocked: {r.stderr}")

    # --- parallel cap
    def test_parallel_cap_denied(self):
        config(self.d, gates={"test": "true"}, graph={"parallel": 1})
        task(self.d, 1, status="in-progress")
        p = task(self.d, 2)
        r = dispatch(self.d, p)
        self.assertEqual(r.returncode, 2)
        self.assertIn("parallel cap 1 reached", r.stderr)

    def test_nonsense_parallel_setting_denies(self):
        config(self.d, gates={"test": "true"}, graph={"parallel": "lots"})
        p = task(self.d, 1)
        r = dispatch(self.d, p)
        self.assertEqual(r.returncode, 2, "an unparseable cap must not silently become the default")
        self.assertIn("not an integer", r.stderr)

    def test_race_for_last_slot_exactly_one_wins(self):
        # N guards fire at once (one orchestrator message with N Agent calls); cap 1.
        # Without the graph-wide lock every one reads "0 in progress" and all pass.
        config(self.d, gates={"test": "true"}, graph={"parallel": 1})
        paths = [task(self.d, i) for i in range(1, 9)]
        results = [None] * len(paths)

        def go(i):
            results[i] = dispatch(self.d, paths[i]).returncode
        threads = [threading.Thread(target=go, args=(i,)) for i in range(len(paths))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        self.assertTrue(all(r is not None for r in results), "a guard hung past the deadline")
        self.assertEqual(results.count(0), 1, f"exactly one dispatch may win the last slot, got {results}")

    def test_plugin_copy_decides_not_project_copy(self):
        # a project whose scripts/reef-graph.py claims everything is ready must still be denied
        os.makedirs(os.path.join(self.d, "scripts"))
        with open(os.path.join(self.d, "scripts", "reef-graph.py"), "w") as f:
            f.write("import sys\nprint('ready')\nsys.exit(0)\n")
        task(self.d, 1)
        p = task(self.d, 2, deps=[1])
        self.assertEqual(dispatch(self.d, p).returncode, 2)


class SchedulerCli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-graph-cli.")
        config(self.d, gates={"test": "true"}, graph={"parallel": 3})

    def test_ready_set_in_id_order(self):
        task(self.d, 1, status="done", done=True)
        task(self.d, 3, deps=[1])
        task(self.d, 2)
        task(self.d, 4, deps=[3])
        task(self.d, 5, attempts=3)              # at cap: never ready
        task(self.d, 6, status="blocked")
        r = graph("ready", "--root", self.d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([l.split("\t")[0] for l in r.stdout.splitlines()], ["2", "3"])
        j = json.loads(graph("ready", "--root", self.d, "--json").stdout)
        self.assertEqual([x["id"] for x in j], ["2", "3"])

    def test_broken_graph_has_no_ready_set(self):
        task(self.d, 1, deps=[2])
        task(self.d, 2, deps=[1])
        task(self.d, 3)
        r = graph("ready", "--root", self.d)
        self.assertEqual(r.returncode, 1, "a cycle anywhere means no best-effort subset")
        self.assertEqual(r.stdout, "")
        self.assertIn("cycle", r.stderr)

    def test_check_exit_codes(self):
        task(self.d, 1)
        p = task(self.d, 2, deps=[1])
        self.assertEqual(graph("check", p).returncode, 2)
        self.assertEqual(graph("check", os.path.join(self.d, "tasks", "001-t.md")).returncode, 0)
        self.assertEqual(graph("check", os.path.join(self.d, "tasks", "nope.md")).returncode, 1)

    def test_status_lists_every_task(self):
        task(self.d, 1, status="in-progress", resources=["db"])
        task(self.d, 2, deps=[1])
        r = graph("status", "--root", self.d)
        self.assertEqual(r.returncode, 0)
        self.assertIn("1\tin-progress", r.stdout)
        self.assertIn("waiting: blocked-by not done: 1 (in-progress)", r.stdout)


class Lock(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-graph-lock.")
        os.makedirs(os.path.join(self.d, ".reef"))

    def test_second_holder_times_out_with_deadline(self):
        config(self.d, resources={"heavy": {"slots": 1}})
        holder = subprocess.Popen([sys.executable, GRAPH, "lock", "heavy", "--root", self.d, "--",
                                   sys.executable, "-c", "import time; time.sleep(4)"])
        time.sleep(0.8)   # let the holder take the slot
        t0 = time.monotonic()
        r = graph("lock", "heavy", "--root", self.d, "--timeout", "0.5", "--", "true")
        self.assertEqual(r.returncode, 75, "no free slot must be a reported timeout, never a hang")
        self.assertLess(time.monotonic() - t0, 3, "the deadline was not honoured")
        self.assertIn("no free slot", r.stderr)
        holder.wait(timeout=10)

    def test_two_slots_run_two(self):
        config(self.d, resources={"heavy": {"slots": 2}})
        holder = subprocess.Popen([sys.executable, GRAPH, "lock", "heavy", "--root", self.d, "--",
                                   sys.executable, "-c", "import time; time.sleep(2)"])
        time.sleep(0.5)
        r = graph("lock", "heavy", "--root", self.d, "--timeout", "0.5", "--", "true")
        self.assertEqual(r.returncode, 0, r.stderr)
        holder.wait(timeout=10)

    def test_command_exit_code_propagates(self):
        config(self.d, resources={})
        r = graph("lock", "x", "--root", self.d, "--timeout", "1", "--", "sh", "-c", "exit 7")
        self.assertEqual(r.returncode, 7)


class Worktree(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-graph-wt.")
        subprocess.run(["git", "init", "-q", "-b", "feat/demo", self.d], check=True)
        subprocess.run(["git", "-C", self.d, "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", self.d, "config", "user.name", "t"], check=True)
        config(self.d, gates={"test": "true"}, worktree={"setup": "echo ran > setup-marker"})
        self.p = task(self.d, 1, slug="demo")
        subprocess.run(["git", "-C", self.d, "add", "-A"], check=True)
        subprocess.run(["git", "-C", self.d, "commit", "-qm", "init"], check=True)

    def test_worktree_created_recorded_idempotent(self):
        r = graph("worktree", self.p)
        self.assertEqual(r.returncode, 0, r.stderr)
        wt = os.path.join(self.d, ".reef", "worktrees", "1")
        self.assertTrue(os.path.isdir(os.path.join(wt, ".git")) or os.path.isfile(os.path.join(wt, ".git")))
        branch = subprocess.run(["git", "-C", wt, "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True).stdout.strip()
        self.assertEqual(branch, "task/1-demo")
        self.assertTrue(os.path.isfile(os.path.join(wt, "setup-marker")), "worktree.setup did not run")
        self.assertIn("worktree: .reef/worktrees/1", frontmatter(self.p))
        r2 = graph("worktree", self.p)
        self.assertEqual(r2.returncode, 0, f"second call must reuse, not fail: {r2.stderr}")

    def test_failed_setup_is_loud(self):
        config(self.d, gates={"test": "true"}, worktree={"setup": "exit 3"})
        r = graph("worktree", self.p)
        self.assertEqual(r.returncode, 1)
        self.assertIn("worktree.setup", r.stderr)


if __name__ == "__main__":
    unittest.main()
