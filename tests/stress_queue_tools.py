"""Stress: the queue, the external tools (gh) and the runner, at their seams — gh missing, failing, hanging or answering
nonsense; an issues queue whose gh flakes between the tick's two reads; file-queue rows in shapes the parser does not
expect; the runner's sync, its gate refusal, its owner-wait lines and its last-mode record; the loop's wait and unlock
from a feature worktree. A test that FAILS is a finding (docs/review/stress-2026-11-02.md); one that passes pins coverage."""
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import write, git_repo, git_checked, load_script, ROOT  # noqa: E402
from test_loop import project, task, approve  # noqa: E402
import test_queue_issues as QI  # noqa: E402

LOOP = os.path.join(ROOT, "scripts", "reef-loop.py")
QUEUE = os.path.join(ROOT, "scripts", "reef-queue.py")
RUN = os.path.join(ROOT, "scripts", "reef-run.py")

# A fake gh for `gh pr list`: GH_MODE ok (prints $GH_PRS), fail (exit 1), hang (sleeps), null, garbage.
FAKE_PR_GH = r'''#!/usr/bin/env python3
import os, sys, time
mode = os.environ.get("GH_MODE", "ok")
if mode == "fail":
    print("HTTP 502: Bad Gateway", file=sys.stderr); sys.exit(1)
if mode == "hang":
    time.sleep(30)
if mode == "null":
    print("null"); sys.exit(0)
if mode == "garbage":
    print("<html>rate limited</html>"); sys.exit(0)
print(open(os.environ["GH_PRS"]).read() if os.environ.get("GH_PRS") else "[]")
'''

# The issues fake of tests/test_queue_issues.py, plus GH_FAIL_FIRST=N: the first N calls of this process tree fail
# (a counter file beside the state) — gh flaky between the tick's `ready` and its `status`.
FAKE_ISSUES_GH = QI.FAKE_GH.replace('''a = sys.argv[1:]
''', '''a = sys.argv[1:]
_ff = int(os.environ.get("GH_FAIL_FIRST") or 0)
if _ff:
    _cp = p + ".count"
    _n = int(open(_cp).read()) if os.path.exists(_cp) else 0
    open(_cp, "w").write(str(_n + 1))
    if _n < _ff:
        print("HTTP 502 (flaky)", file=sys.stderr); sys.exit(1)
if a[:2] == ["pr", "list"]:
    print("[]"); sys.exit(0)
''', 1)
assert FAKE_ISSUES_GH != QI.FAKE_GH


def make_bin(d, script, name="gh"):
    b = os.path.join(d, ".stressbin")
    os.makedirs(b, exist_ok=True)
    p = os.path.join(b, name)
    with open(p, "w") as f:
        f.write(script)
    os.chmod(p, 0o755)
    return b


def tick(d, path, **env):
    e = dict(os.environ, PATH=path)
    e.pop("REEF_RUNNER", None)
    e.update(env)
    t0 = time.time()
    r = subprocess.run([sys.executable, LOOP, "tick", "--json", "--repo", d], capture_output=True, text=True, env=e, timeout=120)
    return r, time.time() - t0


def git_only_path(d):
    """A PATH with git and nothing else of the user's: no gh at all."""
    b = os.path.join(d, ".nogh")
    os.makedirs(b, exist_ok=True)
    git = subprocess.run(["which", "git"], capture_output=True, text=True).stdout.strip()
    os.symlink(git, os.path.join(b, "git"))
    return b + os.pathsep + "/usr/bin/false-dir-without-gh"


# ---------------------------------------------------------------- the tick and `gh pr list`

class TickWithGh(unittest.TestCase):
    def setUp(self):
        self.d = project()
        self.bin = make_bin(self.d, FAKE_PR_GH)
        self.prs = write(self.d, ".stress-prs.json", json.dumps([
            {"number": 7, "headRefName": "feat/first", "title": "row 1", "reviewDecision": ""},
            {"number": 8, "headRefName": "dependabot/pip/requests-2.32", "title": "bump", "reviewDecision": ""},
            {"number": 9, "headRefName": "featured/x", "title": "not ours", "reviewDecision": ""}]))

    def path(self):
        return self.bin + os.pathsep + os.environ["PATH"]

    def test_only_heads_under_feature_prefix_are_the_loops_prs(self):
        # reef-loop.py:235 "the loop reviews ITS PRs: heads under branches.feature_prefix (default feat/). Dependabot's and
        # anyone else's into the base are the owner's"
        r, _ = tick(self.d, self.path(), GH_PRS=self.prs)
        self.assertEqual(r.returncode, 0, r.stderr)
        st = json.loads(r.stdout)
        self.assertEqual(st["prs_to_review"], ["#7 feat/first"], "featured/x is not under feat/")
        self.assertEqual(st["other_prs"], 2)
        cfg = json.load(open(os.path.join(self.d, ".reef", "config.json")))
        cfg["branches"] = {"feature_prefix": "reef/"}
        write(self.d, ".reef/config.json", json.dumps(cfg))
        write(self.d, ".stress-prs.json", json.dumps([{"number": 7, "headRefName": "feat/first", "title": "", "reviewDecision": ""},
                                                       {"number": 10, "headRefName": "reef/12-cache", "title": "", "reviewDecision": ""}]))
        st = json.loads(tick(self.d, self.path(), GH_PRS=self.prs)[0].stdout)
        self.assertEqual(st["prs_to_review"], ["#10 reef/12-cache"], "a configured prefix replaces feat/")

    @unittest.expectedFailure   # open: H4 (docs/review/stress-2026-11-02.md)
    def test_a_failing_gh_is_named_not_read_as_no_prs(self):
        # contract silent: reef-loop.py docstring "the loop engine's one read of the world: the TICK" — an owner expects the
        # tick to say it could not read the PRs, not report "PRs to review: none" while PR #7 waits
        r, _ = tick(self.d, self.path(), GH_PRS=self.prs)
        self.assertEqual(json.loads(r.stdout)["prs_to_review"], ["#7 feat/first"], "sanity: gh up, the PR is listed")
        r, _ = tick(self.d, self.path(), GH_PRS=self.prs, GH_MODE="fail")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = json.loads(r.stdout)
        self.assertTrue(any("gh" in b for b in st["broken"]),
                        f"gh pr list failed and the tick says nothing: prs_to_review={st['prs_to_review']} broken={st['broken']}")

    def test_a_hanging_gh_is_cut_at_its_timeout(self):
        # reef-loop.py:28 GH_TIMEOUT = REEF_GH_TIMEOUT (default 5 s): a hung gh never holds the tick (and the Stop hook) longer
        r, took = tick(self.d, self.path(), GH_PRS=self.prs, GH_MODE="hang", REEF_GH_TIMEOUT="1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(took, 20, "the tick waited on a hung gh")
        json.loads(r.stdout)

    @unittest.expectedFailure   # open: H4 (docs/review/stress-2026-11-02.md)
    def test_gh_printing_json_null_does_not_crash_the_tick(self):
        # contract silent: the tick is the one read the loop and the Stop hook run; garbage from gh must not crash it
        r, _ = tick(self.d, self.path(), GH_MODE="garbage")
        self.assertEqual(r.returncode, 0, r.stderr)
        r, _ = tick(self.d, self.path(), GH_MODE="null")
        self.assertEqual(r.returncode, 0, "gh printed `null` and the tick crashed:\n" + r.stderr[-600:])
        json.loads(r.stdout)

    def test_no_gh_on_the_path_still_ticks(self):
        # reef-loop.py:229 the PR read is optional; a machine without gh (file queue) keeps a working tick
        r, _ = tick(self.d, git_only_path(self.d))
        self.assertEqual(r.returncode, 0, r.stderr)
        st = json.loads(r.stdout)
        self.assertEqual(st["dispatch_now"], ["101"])


# ---------------------------------------------------------------- the issues queue and a flaky gh

class IssuesQueueTick(unittest.TestCase):
    def setUp(self):
        self.d = project({"gates": {"full": "true"}, "paths": {"queue": "reef/queue.md", "runlog": "reef/journal.md"},
                          "queue": {"home": "issues"}})
        write(self.d, "reef/queue.md", "# Queue\n\n## Footnotes\n")
        self.bin = make_bin(self.d, FAKE_ISSUES_GH)
        self.state = os.path.join(self.d, ".stress-gh.json")
        self.put({"next": 30, "labels": [], "calls": [], "collaborators": ["owner"],
                  "milestones": [{"number": 1, "title": "Batch 1", "state": "open"}],
                  "issues": [{"number": 21, "title": "[1] first", "body": QI.body(), "state": "OPEN", "labels": ["reef-row", "planned"],
                              "milestone": "Batch 1", "comments": []},
                             {"number": 23, "title": "[3] third", "body": QI.body(), "state": "OPEN", "labels": ["reef-row", "planned"],
                              "milestone": "Batch 1", "comments": []}]})

    def put(self, s):
        with open(self.state, "w") as f:
            json.dump(s, f)

    def gh(self):
        return json.load(open(self.state))

    def env(self, **extra):
        return dict(PATH=self.bin + os.pathsep + os.environ["PATH"], GH_STATE=self.state, GH_MODE="ok", REEF_GH_READ_TIMEOUT="5", **extra)

    @unittest.expectedFailure   # open: H4 (docs/review/stress-2026-11-02.md)
    def test_gh_down_with_no_snapshot_is_named_never_an_empty_queue(self):
        # reef-queue.py:62 "every read syncs .reef/queue.json first (a failing gh: the last snapshot ...)"; with no snapshot
        # reef-queue exits 1 ("no snapshot, no gh: no queue"). contract silent on the tick: an owner expects the tick to say
        # the queue is unreadable, not "rows to plan: none" as if the queue were empty
        env = {k: v for k, v in self.env(GH_MODE_X="1").items() if k != "PATH"}
        env["GH_MODE"] = "fail"
        r, _ = tick(self.d, self.env()["PATH"], **env)
        self.assertEqual(r.returncode, 0, r.stderr)
        st = json.loads(r.stdout)
        self.assertTrue(any("queue" in b for b in st["broken"]),
                        f"the queue could not be read at all and the tick says nothing: rows_to_plan={st['rows_to_plan']} broken={st['broken']}")

    @unittest.expectedFailure   # open: H4 (docs/review/stress-2026-11-02.md)
    def test_a_row_closed_on_github_is_not_planned_from_a_stale_ready_read(self):
        # contract silent: the tick reads `ready` and `status` as two syncs. gh failing on the first only, `ready` answers from
        # the last snapshot (row 3 queued) while `status` reads the fresh issues (row 3 closed, merged): the tick must not
        # plan a row its own status read says is no longer in the queue
        env = {k: v for k, v in self.env().items() if k != "PATH"}
        r, _ = tick(self.d, self.env()["PATH"], **env)
        self.assertEqual(json.loads(r.stdout)["rows_to_plan"], ["3"], "sanity: gh up, row 3 is the row to plan " + r.stderr)
        s = self.gh()
        s["issues"][1].update(state="CLOSED", stateReason="COMPLETED")
        self.put(s)
        r, _ = tick(self.d, self.env()["PATH"], **dict(env, GH_FAIL_FIRST="1"))
        st = json.loads(r.stdout)
        self.assertNotIn("3", st["rows_to_plan"], "row 3 is closed on GitHub (the tick's own status read omits it) yet it is to plan")

    def test_milestones_failing_mid_sync_falls_back_whole(self):
        # reef-queue.py:235 sync: "a failing gh reads the last snapshot" — the issue list read fresh and the milestones from the
        # snapshot are never mixed: one snapshot answers, said on stderr
        q = lambda *a, **extra: subprocess.run([sys.executable, QUEUE, *a, "--repo", self.d], capture_output=True, text=True,
                                              env=dict(os.environ, **self.env(**extra)))
        self.assertEqual(q("status").returncode, 0)
        s = self.gh()
        s["issues"].append({"number": 24, "title": "[4] fourth", "body": QI.body(), "state": "OPEN", "labels": ["reef-row", "planned"],
                            "milestone": "Batch 1", "comments": []})
        self.put(s)
        os.unlink(self.state + ".count") if os.path.exists(self.state + ".count") else None
        # the issue list (call 1) succeeds, the milestones (call 2) fail: make the fake fail only its 2nd call
        fake = FAKE_ISSUES_GH.replace("if _n < _ff:", "if _n == 1:")
        with open(os.path.join(self.bin, "gh"), "w") as f:
            f.write(fake)
        r = q("status", GH_FAIL_FIRST="9")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("last snapshot", r.stderr)
        self.assertNotIn("fourth", r.stdout, "half a sync: the fresh issue list leaked past a failed milestone read")


# ---------------------------------------------------------------- the file queue's edge shapes

QHEAD = "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n"
AHEAD = "# Queue archive\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n"


class FileQueue(unittest.TestCase):
    def mk(self, rows, archive=""):
        d = git_repo(prefix="reef-stressq.", config={"paths": {"queue": "reef/queue.md"}})
        write(d, "reef/queue.md", QHEAD + rows)
        write(d, "reef/queue-archive.md", AHEAD + archive)
        return d

    def q(self, d, *a):
        return subprocess.run([sys.executable, QUEUE, *a, "--repo", d], capture_output=True, text=True,
                              env=dict(os.environ, REEF_NO_RESUME="1"))

    def ready(self, d):
        return [l.split("\t")[0] for l in self.q(d, "ready", "--with-found").stdout.splitlines() if "\t" in l]

    @unittest.expectedFailure   # open: M5 (docs/review/stress-2026-11-02.md)
    def test_a_row_id_the_parser_cannot_read_is_named_by_check(self):
        # contract silent: reef-queue.py check is "consistency: ... no row id repeats; depends resolve". A row the owner typed
        # as `R7` or with a footnote mark on its id (`8¹`) vanishes from status/ready; check must not say ok over it
        for bad in ("| R7 | a renamed row | | planned | 1 | |\n", "| 8¹ | a marked id | | planned | 1 | |\n"):
            d = self.mk("| 3 | fine | | planned | 1 | |\n" + bad)
            self.assertEqual(self.ready(d), ["3"])
            r = self.q(d, "check")
            self.assertEqual(r.returncode, 1, f"check passed over an unreadable row id {bad.split('|')[1].strip()!r}: {r.stdout}")

    @unittest.expectedFailure   # open: M5 (docs/review/stress-2026-11-02.md)
    def test_a_cycle_in_depends_fails_check(self):
        # contract silent (reef-plan-check refuses a cycle among tasks): two rows that wait on each other are never ready —
        # the loop would idle on "nothing ready" forever; check must name the cycle
        d = self.mk("| 3 | a | 4 | planned | 1 | |\n| 4 | b | 3 | planned | 1 | |\n")
        self.assertEqual(self.ready(d), [])
        r = self.q(d, "check")
        self.assertEqual(r.returncode, 1, "a depends cycle passed check: " + r.stdout)

    def test_queue_and_archive_and_an_archived_dependency(self):
        # reef-queue.py check: "row {i} is in the queue AND the archive"; is_done: an archived dependency is done
        d = self.mk("| 3 | a | 1 | planned | 1 | |\n| 4 | b | 2 | planned | 1 | |\n", archive="| 1 | old | | planned | 1 | |\n| 4 | twice | | planned | 1 | |\n")
        self.assertIn("3", self.ready(d), "row 3 depends on archived row 1: ready")
        r = self.q(d, "check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("row 4 is in the queue AND the archive", r.stdout)
        self.assertIn("row 4 depends on unknown row 2", r.stdout)

    @unittest.expectedFailure   # open: M5 (docs/review/stress-2026-11-02.md)
    def test_footnote_marks_on_current_batch_and_on_a_batch_cell(self):
        # reef-queue.py:148 "`Current batch: 2²⁶` — the owner's footnote marker rides on the line"; the same mark on a row's
        # Batch cell (contract silent) must not hide the row from its batch
        d = self.mk("| 3 | a | | planned | 1 | |\n")
        write(d, "reef/queue.md", QHEAD.replace("Current batch: 1", "Current batch: 1²") + "| 3 | a | | planned | 1 | |\n")
        self.assertEqual(self.ready(d), ["3"], "a mark on the Current batch line is read away")
        write(d, "reef/queue.md", QHEAD + "| 3 | a | | planned | 1³ | |\n")
        self.assertEqual(self.ready(d), ["3"], "a footnote mark on the Batch cell hid row 3 from the current batch")


# ---------------------------------------------------------------- the runner

class OwnerWaitLines(unittest.TestCase):
    """The owner's rule (2026-10-28, reef-run.py:1008): "a stop that names no command is a bug"; the brief: every waiting
    message prints the exact command with real values, never placeholders."""

    def setUp(self):
        self.rr = load_script("reef-run.py")
        self.d = git_repo(prefix="reef-stressw.", config={"paths": {"queue": "reef/queue.md"}})
        write(self.d, "reef/queue.md", QHEAD + "| 7 | seven | | planned | 1 | |\n")

    def cmds(self, text):
        return [l.strip() for l in text.splitlines() if l.startswith("    ")]

    def test_a_filed_question_gets_its_recommended_answer_filled_in(self):
        # reef-run.py:1010 "the recommended answer filled in (reef_common.answer_command)"
        write(self.d, ".reef/questions.md", "- row 7: two decimals or three? — recommended: two decimals\n")
        text = self.rr.owner_wait_lines(self.d, "row 7 needs your answer", "claude")
        self.assertIn("python3 scripts/reef-queue.py footnote 'two decimals' --row 7", text)
        self.assertFalse(any("<" in c for c in self.cmds(text)), text)

    @unittest.expectedFailure   # open: M3 (docs/review/stress-2026-11-02.md)
    def test_a_wait_that_writes_Row_capitalised_still_names_a_command(self):
        # reef-run.py:1008 "a stop that names no command is a bug": the loop's agent wrote the wait; "Row 7" is the same row
        text = self.rr.owner_wait_lines(self.d, "Row 7: the owner decides the rounding", "claude")
        self.assertIn("answer in the terminal", text, "no terminal command for a wait naming Row 7:\n" + text)

    @unittest.expectedFailure   # open: M3 (docs/review/stress-2026-11-02.md)
    def test_a_row_with_nothing_filed_prints_no_placeholder(self):
        # the brief / the owner (memory, 2026-10-28): "exact values, no placeholders (he typed `<date>` literally once)"
        text = self.rr.owner_wait_lines(self.d, "row 7 needs the owner", "claude")
        self.assertTrue(self.cmds(text), text)
        self.assertFalse(any("<" in c and ">" in c for c in self.cmds(text)), "a placeholder in the command the owner copies:\n" + text)


class RunnerStart(unittest.TestCase):
    def setUp(self):
        self.d = git_repo(prefix="reef-stressr.", config={"gates": {"full": "true"}})
        write(self.d, ".reef/run/gate.json", json.dumps({"ok": True, "mode": "auto"}))
        write(self.d, ".reef/night/last-mode.json", json.dumps({"mode": "autopilot", "at": "2026-11-01T00:00:00Z"}))

    def run_(self, *a):
        env = dict(os.environ, PATH="/nonexistent-claude:" + os.environ["PATH"], REEF_NOTIFY="0", REEF_CLAUDE="/nonexistent/claude")
        return subprocess.run([sys.executable, RUN, *a, "--repo", self.d], capture_output=True, text=True, env=env, timeout=60)

    def test_the_gate_refusal_names_the_exact_probe_and_writes_nothing(self):
        # reef-run.py docstring: "1 refused (no probe for this mode ...)"; the refusal prints the one command, real mode
        r = self.run_("--permission-mode", "acceptEdits")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("python3 scripts/reef-run.py probe --permission-mode acceptEdits", r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "run", "lock")))
        self.assertEqual(json.load(open(os.path.join(self.d, ".reef", "night", "last-mode.json")))["mode"], "autopilot")

    @unittest.expectedFailure   # open: M4 (docs/review/stress-2026-11-02.md)
    def test_a_start_refused_by_a_live_runner_leaves_the_last_mode_alone(self):
        # reef-run.py:670 LAST_MODE is "the mode of the last run ... what `resume` restarts". A refused start ran nothing: a
        # plain `reef run` typed while the autopilot runs must not turn the autopilot's resume into a plain loop
        write(self.d, ".reef/run/lock", str(os.getpid()))
        r = self.run_()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("another reef-run", r.stdout + r.stderr)
        self.assertEqual(json.load(open(os.path.join(self.d, ".reef", "night", "last-mode.json")))["mode"], "autopilot",
                         "a refused start rewrote what `resume` restarts")


class SyncScripts(unittest.TestCase):
    """reef-run.py:1453 sync_scripts: only a copy Reef wrote and nobody touched (its bytes hash to the manifest) is replaced;
    an edited copy is the owner's question, never committed; one commit of those files and the manifest alone."""

    def setUp(self):
        self.rr = load_script("reef-run.py")
        self.plugin = git_repo(prefix="reef-stressp.", identity=True)
        write(self.plugin, ".claude-plugin/plugin.json", json.dumps({"name": "reef", "version": "9.9.9"}))
        write(self.plugin, "scripts/reef-x.py", "print('new')\n")
        write(self.plugin, "scripts/reef-y.py", "print('y new')\n")
        git_checked(self.plugin, "add", "-A")
        git_checked(self.plugin, "commit", "-qm", "plugin")
        self.d = git_repo(prefix="reef-stresss.", identity=True, config={"gates": {"full": "true"}})
        write(self.d, "scripts/reef-x.py", "print('old')\n")
        write(self.d, "scripts/reef-y.py", "print('y old')\n")
        sha = lambda t: hashlib.sha256(t.encode()).hexdigest()
        write(self.d, ".reef/init-manifest.json", json.dumps({"scripts/reef-x.py": sha("print('old')\n"),
                                                             "scripts/reef-y.py": sha("print('y old')\n")}))
        git_checked(self.d, "add", "-A")
        git_checked(self.d, "commit", "-qm", "init")
        self.said = []

    def sync(self, tried=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.rr.sync_scripts(self.d, self.plugin, self.said.append, set() if tried is None else tried)

    def read(self, rel):
        return open(os.path.join(self.d, rel)).read()

    def test_a_clean_copy_behind_is_synced_in_one_commit_and_staged_work_stays_out(self):
        write(self.d, "app.py", "x = 1\n")
        git_checked(self.d, "add", "app.py")
        self.assertFalse(self.sync())
        self.assertEqual(self.read("scripts/reef-x.py"), "print('new')\n")
        msg = git_checked(self.d, "log", "-1", "--format=%s").stdout
        self.assertIn("synced by the runner", msg)
        files = git_checked(self.d, "show", "--name-only", "--format=", "HEAD").stdout.split()
        self.assertEqual(sorted(files), [".reef/init-manifest.json", "scripts/reef-x.py", "scripts/reef-y.py"])
        self.assertIn("A  app.py", git_checked(self.d, "status", "--porcelain").stdout, "the owner's staged file stays staged")

    def test_an_edited_copy_is_filed_and_left_as_it_is(self):
        write(self.d, "scripts/reef-x.py", "print('mine')\n")
        git_checked(self.d, "commit", "-qam", "owner edit")
        self.sync()
        self.assertEqual(self.read("scripts/reef-x.py"), "print('mine')\n", "the owner's edit was overwritten")
        self.assertEqual(self.read("scripts/reef-y.py"), "print('y new')\n", "the untouched copy beside it still syncs")
        self.assertIn("reef-x.py", self.read(".reef/questions.md"))
        self.assertIn("python3 scripts/reef update", self.read(".reef/questions.md"))

    def test_a_dirty_plugin_clone_or_a_feature_branch_syncs_nothing(self):
        write(self.plugin, "scripts/reef-x.py", "print('wip')\n")
        self.assertFalse(self.sync())
        self.assertEqual(self.read("scripts/reef-x.py"), "print('old')\n")
        self.assertTrue(any("not clean" in s for s in self.said), self.said)
        git_checked(self.plugin, "checkout", "--", ".")
        git_checked(self.d, "checkout", "-qb", "feat/x")
        self.said.clear()
        self.assertFalse(self.sync())
        self.assertEqual(self.read("scripts/reef-x.py"), "print('old')\n", "synced onto a feature branch")
        self.assertTrue(any("not main" in s for s in self.said), self.said)


# ---------------------------------------------------------------- wait / unlock from a feature worktree

class LoopStateFromAWorktree(unittest.TestCase):
    def setUp(self):
        self.d = project()
        self.wt = os.path.join(self.d, ".reef", "worktrees", "first")
        git_checked(self.d, "worktree", "add", "-q", "-b", "feat/first", self.wt)
        os.makedirs(os.path.join(self.wt, ".reef"), exist_ok=True)
        write(self.wt, ".reef/config.json", open(os.path.join(self.d, ".reef", "config.json")).read())

    def loop(self, repo, *a):
        return subprocess.run([sys.executable, LOOP, *a, "--repo", repo], capture_output=True, text=True,
                              env=dict(os.environ, PATH="/nonexistent-gh:" + os.environ["PATH"]))

    @unittest.expectedFailure   # open: H5 (docs/review/stress-2026-11-02.md)
    def test_a_wait_recorded_from_the_feature_worktree_is_the_loops_wait(self):
        # skills/reef-loop/SKILL.md:11 "`wait "<reason>"` records a chat-side wait ... so the turn may end"; the Stop hook reads
        # the MAIN checkout's .reef/loop.json (reef-guard.py check_stop: root = main_checkout(cwd)), and `wait` already releases
        # the main checkout's hold — the wait itself must land where the hook and the runner read it
        self.assertEqual(self.loop(self.d, "start").returncode, 0)
        r = self.loop(self.wt, "wait", "grill question for row 1")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = json.load(open(os.path.join(self.d, ".reef", "loop.json")))
        self.assertEqual(st.get("wait"), "grill question for row 1",
                         "the wait went to the worktree's loop.json; the main checkout's (the Stop hook's, the runner's) has none")

    def test_unlock_from_the_worktree_drops_the_main_checkouts_dead_hold(self):
        # reef_common.py read_hold: "a dead pid holds nothing"; release_hold: drop_hold(main_checkout(root))
        write(self.d, ".reef/run/orchestrator.json", json.dumps({"session": "dead-session-1", "at": time.time(), "pid": 999999}))
        r = self.loop(self.wt, "unlock")
        self.assertIn("held by session dead-session-1", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "run", "orchestrator.json")))


if __name__ == "__main__":
    unittest.main()
