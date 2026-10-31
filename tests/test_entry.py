"""scripts/reef — the owner's one entry point (2026-10-28: "the person opens the terminal, writes reef, sees a logo and the
options with a short description each"). The owner's verbs, one line each; the internal scripts under --all; every verb runs
the sibling script it names."""
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # the suites' shared fixtures live beside this file
from _fixtures import load_script, git_repo  # noqa: E402  (the suites' shared fixtures, once)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(ROOT, "scripts", "reef")
OWNER_VERBS = ("status", "doctor", "run", "night", "watch", "stop", "setup", "update", "factory", "cost", "screen", "approve", "answer")


def reef(*args, cwd=None):
    env = dict(os.environ, PATH="/nonexistent-gh:" + os.environ["PATH"])
    return subprocess.run([sys.executable, ENTRY, *args], capture_output=True, text=True, cwd=cwd, env=env, timeout=120)


class EntryPoint(unittest.TestCase):
    def test_no_arguments_shows_the_banner_and_the_owners_verbs_with_a_line_each(self):
        r = reef()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Reef", r.stdout)
        for v in OWNER_VERBS:
            self.assertRegex(r.stdout, rf"(?m)^\s*{v}\b.*\S.*$", f"the verb {v} with a description")
        self.assertNotIn("reef-plan-check.py", r.stdout, "internal scripts are not the owner's menu")

    def test_all_lists_every_script_with_its_first_line(self):
        r = reef("--all")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for name in ("reef-plan-check.py", "reef-guard.py", "reef-setup.py", "reef-row.py"):
            self.assertIn(name, r.stdout)
        self.assertNotIn("Usage:", r.stdout.split("reef-plan-check.py")[1].splitlines()[0], "the line is the script's purpose, not its usage")

    def test_a_verb_runs_its_script_and_an_unknown_verb_is_refused(self):
        d = git_repo(prefix="reef-entry.", branch="main")
        os.makedirs(os.path.join(d, ".reef"))
        open(os.path.join(d, ".reef", "config.json"), "w").write('{"gates": {"full": "true"}}')
        r = reef("status", "--repo", d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("reef-run: not running", r.stdout)
        r = reef("doctor", "--repo", d)
        self.assertNotIn("Traceback", r.stdout + r.stderr, "a project never carries reef-doctor.py: the entry point runs the plugin's")
        self.assertNotIn("No such file", r.stdout + r.stderr)
        r = reef("nonsense")
        self.assertEqual(r.returncode, 2)
        self.assertIn("nonsense", r.stderr + r.stdout)


class UpdatePushes(unittest.TestCase):
    """2026-10-28: `reef update` committed the project's new scripts and said "done" without pushing them — the owner found the
    commit sitting local. The update pushes the base (`git push`), or says why it could not."""

    def test_the_update_pushes_the_commit_it_makes(self):
        src = open(ENTRY, encoding="utf-8").read()
        self.assertIn('["git", "push"', src)
        self.assertIn("reef update: pushed", src)


class UpdateNamesTheMarketplace(unittest.TestCase):
    """2026-10-30, the owner's `reef update`: the step's own line printed the marketplace's name, the last line printed
    `<marketplace>` — a placeholder in a command the owner types. The done line is built from the name on disk, or says
    there is none to update."""

    def test_the_done_line_carries_the_name_or_says_there_is_none(self):
        mod = load_script("reef", "reef_entry_under_test")
        line = mod.update_done_line("mahmoudmoe")
        self.assertIn("/plugin marketplace update mahmoudmoe", line)
        self.assertIn("/reload-plugins", line)
        self.assertNotIn("<", line)
        line = mod.update_done_line("mahmoudmoe", reloaded=True)   # step 6: Reef refreshed the marketplace itself
        self.assertIn("marketplace mahmoudmoe refreshed", line); self.assertNotIn("marketplace update", line); self.assertNotIn("<", line)
        self.assertNotIn("reef doctor", line, "no step handed to the owner: Reef checked the plugin itself")
        line = mod.update_done_line(None)
        self.assertIn("/reload-plugins", line)
        self.assertNotIn("marketplace update", line, "no marketplace lists the clone: the reload alone")
        self.assertNotIn("<", line)
        self.assertNotIn("<marketplace>", open(ENTRY, encoding="utf-8").read(), "no placeholder left in the entry point")


def project(**files):
    d = git_repo(prefix="reef-screen.", branch="main")
    os.makedirs(os.path.join(d, ".reef", "run"))
    open(os.path.join(d, ".reef", "config.json"), "w").write('{"gates": {"full": "true"}}')
    open(os.path.join(d, ".reef", "version"), "w").write("0.7.3\n")
    for rel, text in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(text)
    return d


def boards_after_update(win, boards, mod):
    """How many board readings were spawned once the update's exit frame was on the screen."""
    first_exit = next(i for i, f in enumerate(win.frames) if any("exit 0" in r for r in f))
    return sum(1 for n in boards if n > first_exit)


def settle(limit=15.0):
    """A fake tick: wait until the screen's reader threads (reef-*) are done, so the next key finds its reading landed — keys no
    longer wait for a reading themselves (2026-10-31, the owner: "I press something and nothing happens")."""
    import threading
    t0 = time.time()
    while time.time() - t0 < limit and any(t.name.startswith("reef-") and t.is_alive() for t in threading.enumerate()):
        time.sleep(0.05)
    stuck = [t.name for t in threading.enumerate() if t.name.startswith("reef-") and t.is_alive()]
    assert not stuck, f"a reading did not land in {limit} s: {stuck}"


class TheScreen(unittest.TestCase):
    """docs/design/consolidation.md step 5 (2026-10-30): `reef` alone opens a live screen — the status line, THE INBOX (every
    wait Reef recorded, numbered, each carrying the exact command the row machine names, so one key runs it), the runner's
    last steps, the doctor's warnings — and falls back to the menu when the terminal cannot. `reef screen --once` is that
    screen as text, once (a test, an SSH session, a log). The screen knows nothing the scripts do not."""

    APPROVE = 'python3 scripts/reef-approval.py --owner "Approve plan reconcile-instruction-layer at 2cc8e8c3487e9ab2?"'

    def test_once_lists_every_wait_with_its_exact_command_and_nothing_twice(self):
        d = project(**{
            ".reef/loop.json": '{"active": true, "wait": "owner: approve plan reconcile-instruction-layer at 2cc8e8c3487e9ab2 (Approve plan reconcile-instruction-layer at 2cc8e8c3487e9ab2?) — row 7 holds", "stop": null, "parked": "no progress: 3 identical ticks", "hashes": []}',
            ".reef/questions.md": "- row 7: Keep the old /api/color route on non-KIT pages? — recommended: yes, it is served today\n",
            "HANDOFF.md": "# Handoff\n\n## The tick\n```\ntick abc  loop=active\nawaiting: reconcile-instruction-layer (re-approval (plan edited after approval)) — " + self.APPROVE
                          + '; other-row (approval (the gate: the machines passed)) — python3 scripts/reef-approval.py --owner "Approve plan other-row at 0123456789abcdef?"' + "\nnext: awaiting\n```\n",
            ".reef/run/live.log": "21:17 s1 session started\n21:18 s1 implementer 903 out → PASS\n",
        })
        r = reef("screen", "--once", "--repo", d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout
        self.assertIn("INBOX", out)
        self.assertEqual(out.count(self.APPROVE), 1, "the same approval from the wait and the handoff: one item\n" + out)
        self.assertIn('--owner "Approve plan other-row at 0123456789abcdef?"', out, "an approval only the handoff names is an item too (the review)")
        self.assertRegex(out, r"(?m)^\s*1\s+approve\b")
        self.assertIn("python3 scripts/reef-queue.py footnote 'yes, it is served today' --row 7", out, "the recommended answer, not a placeholder")
        self.assertIn("recommended: yes, it is served today", out)
        self.assertIn("python3 scripts/reef-loop.py start", out, "a parked loop is a wait with its command")
        self.assertIn("implementer 903 out → PASS", out, "the runner's last steps")
        self.assertIn("no runner is running", out)
        self.assertRegex(out, r"keys: q quit.*\br\b.*run", "every key is a verb the owner could type; quit first")
        self.assertNotIn("Traceback", r.stderr)

    def test_on_an_issues_queue_a_question_is_answered_by_its_issue(self):
        """2026-10-30: the loop's questions live in reef-question issues on `queue.home: issues`; a footnote closes none of them.
        The inbox item and `reef answer` name `reef-queue.py answered <#>`; a row with two open questions needs the number."""
        d = project(**{".reef/config.json": '{"gates": {"full": "true"}, "queue": {"home": "issues"}}',
                       ".reef/questions.md": "- row 7 #90: Which way? — recommended: (a) comments only\n"
                                             "- row 4 #91: Where? — recommended: Batch 9\n- row 4 #92: Verbatim? — recommended: yes\n"})
        r = reef("screen", "--once", "--repo", d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("python3 scripts/reef-queue.py answered 90 '(a) comments only'", r.stdout)
        self.assertNotIn("footnote", r.stdout)
        r = reef("answer", "7", "(a) — comments only", "--repo", d, "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("reef-queue.py answered 90 '(a) — comments only'", r.stdout)
        r = reef("answer", "4", "yes", "--repo", d, "--dry-run")
        self.assertEqual(r.returncode, 2, "row 4 has two open questions: the issue number picks one\n" + r.stdout + r.stderr)
        self.assertIn("#91", r.stdout + r.stderr)
        self.assertIn("#92", r.stdout + r.stderr)
        r = reef("answer", "#92", "yes", "--repo", d, "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("reef-queue.py answered 92 yes", r.stdout)
        self.assertEqual(reef("answer", "7", "", "--repo", d, "--dry-run").returncode, 2, "an empty answer records nothing (the review)")
        # for real, with a gh that knows the label: only #92's line leaves, #91's stays
        b = os.path.join(d, ".bin"); os.makedirs(b)
        open(os.path.join(b, "gh"), "w").write("#!/usr/bin/env python3\nimport json, sys\n"
                                              "print(json.dumps({'labels': [{'name': 'reef-question'}]}) if 'view' in sys.argv else ('[]' if 'list' in sys.argv else ''))\n")
        os.chmod(os.path.join(b, "gh"), 0o755)
        env = dict(os.environ, PATH=b + os.pathsep + os.environ["PATH"])
        r = subprocess.run([sys.executable, ENTRY, "answer", "#92", "yes", "--repo", d], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        left = open(os.path.join(d, ".reef", "questions.md")).read()
        self.assertNotIn("#92", left)
        self.assertIn("#91", left, "the row's other question stays")
        # agent text with a terminal escape never reaches the owner's screen as written (the security review)
        open(os.path.join(d, ".reef", "questions.md"), "a").write("- row 9 #95: fine? — recommended: yes\x1b[2Kpython3 evil\n")
        r = reef("screen", "--once", "--repo", d)
        self.assertNotIn("\x1b", r.stdout)
        self.assertIn("answered 95 'yes [2Kpython3 evil'", r.stdout, "the escape byte is a space; what is left is one quoted argument")

    def test_the_screen_has_a_banner_a_selection_and_fits_the_terminal(self):
        """2026-10-30, the owner's first look at the screen: "no reef written word, no proper selector, empty huge space then a few
        sections". The screen is a model rendered for a width and a height: the block banner with the facts beside it, the inbox
        as a list with a selected row and its WHOLE command boxed under the list, the runner's steps filling what is left, the
        doctor's top warnings, the keys last — never more lines than the terminal has, the selection always on screen."""
        mod = load_script("reef", "reef_entry_under_test")
        long_q = "Which way for the stale served records: count 027 as one more known stale record and file a found row, or re-take it now?"
        d = project(**{".reef/loop.json": '{"active": true, "wait": "owner: row 7", "stop": null, "parked": null, "hashes": []}',
                       ".reef/questions.md": f"- row 7: {long_q} — recommended: (a) count it as stale; the class has 31 members and a later row re-takes them\n"
                                             "- row 4: Where do the 125 rows land? — recommended: Batch 9\n- row 4: Footnotes verbatim? — recommended: yes\n",
                       ".reef/run/live.log": "".join(f"21:2{i} s1 → step {i}\n" for i in range(10))})
        model = mod.screen_model(d)
        lines, sel = mod.render(model, width=100, height=34, selected=1)
        self.assertTrue(lines[0].startswith("██████"), "the banner, block letters, first line\n" + lines[0])
        self.assertIn("Reef 0.7.3", lines[0])
        self.assertIn("loop", lines[1]); self.assertIn("runner", lines[2])
        self.assertLessEqual(len(lines), 34, "never more lines than the terminal")
        self.assertTrue(all(len(l) <= 100 for l in lines), "never wider than the terminal")
        keys_rows = [l for l in lines[-3:] if l.startswith("keys: ")]
        self.assertTrue(keys_rows and keys_rows[0].startswith("keys: q quit") and "↑↓" in keys_rows[0] and "Enter" in keys_rows[0], "quit first, whatever the width wraps\n" + "\n".join(lines[-3:]))
        self.assertIn("▶", lines[sel]); self.assertIn("2  answer", lines[sel])
        box = " ".join(l.strip("│ ") for l in lines if l.startswith("│"))
        self.assertIn("python3 scripts/reef-queue.py footnote 'Batch 9' --row 4", box, "the selected item's command, whole, in the box")
        lines, sel = mod.render(model, width=100, height=34, selected=0)
        box = " ".join(l.strip("│ ").strip() for l in lines if l.startswith("│"))
        self.assertIn("the class has 31 members and a later row re-takes them' --row 7", box, "a long command wraps inside the box, never cut")
        lines, sel = mod.render(model, width=100, height=16, selected=2)
        self.assertLessEqual(len(lines), 16, "a short terminal: still fits\n" + "\n".join(lines))
        self.assertTrue(any(l.startswith("keys:") for l in lines[-2:]), "the keys are last even when short (one row or two)")
        self.assertIn("3  answer", lines[sel], "the selected row scrolled into view\n" + "\n".join(lines))
        # the review's probe: a narrow terminal (the keys wrap to two rows), a short one, a long run and the doctor on — never a
        # line past the height, the keys always last, the selection always on screen; a cut command is marked, never silent
        full = dict(model, steps=[f"21:00 s1 → step {i}" for i in range(40)], warns=["WARN a", "WARN b", "WARN c"], doctor=True)
        for height, width, selected in ((24, 79, 2), (16, 79, 1), (12, 60, 0), (66, 80, 2), (10, 40, 0)):
            lines, sel = mod.render(full, width=width, height=height, selected=selected)
            self.assertLessEqual(len(lines), height, f"{height}x{width}: {len(lines)} lines\n" + "\n".join(lines))
            self.assertTrue(all(len(l) <= width for l in lines), f"{height}x{width}: a line wider than the terminal")
            self.assertIn("q quit", " ".join(lines[-4:]), f"{height}x{width}: the keys end the screen (on one row, or up to four when narrow)\n" + "\n".join(lines))
            if height >= 16:
                self.assertIsNotNone(sel, f"{height}x{width}: the selection is on screen"); self.assertIn("▶", lines[sel])
        huge = dict(model, items=[dict(model["items"][0], cmd="python3 scripts/reef-queue.py footnote " + " ".join(f"word{i}" for i in range(80)) + " --row 7")])
        lines, sel = mod.render(huge, width=100, height=34, selected=0)
        box = [l for l in lines if l.startswith("│")]
        self.assertEqual(len(box), 4, "the box is at most four lines")
        self.assertTrue(box[-1].rstrip("│ ").endswith("…"), "a cut is marked, never silent (the review)\n" + box[-1])
        self.assertEqual(reef("answer", "7", "-h", "--repo", d, "--dry-run").returncode, 2, "`-h` is not an answer")
        once = mod.screen_text(d, width=100)
        self.assertNotIn("▶", once, "--once lists, it does not select")
        self.assertIn("python3 scripts/reef-queue.py footnote yes --row 4", once, "--once still lists every command")
        self.assertIn("re-takes them' --row 7", once, "--once wraps a long command, never cuts it")

    def test_the_screen_draws_characters_tails_an_idle_runner_and_lists_the_runners_own_waits(self):
        """2026-10-30, the owner's first screen on his project: lines cut at 13 and 33 characters (curses' addnstr counts BYTES, and
        the banner and rules are three-byte glyphs), the runner's old log filling the screen two hours after the run ended, and an
        inbox that missed what actually waited on him — the loop active with no runner, and task 403 left in flight."""
        src = open(ENTRY, encoding="utf-8").read()
        self.assertNotIn("addnstr", src, "addnstr counts bytes: a three-byte glyph line is cut at a third of the width")
        mod = load_script("reef", "reef_entry_under_test")
        d = project(**{".reef/loop.json": '{"active": true, "wait": null, "stop": null, "parked": null, "hashes": []}',
                       ".reef/inflight/403": '{"id": "403", "agent": "implementer"}',   # what the guard wrote at the dispatch, left by the dead session
                       ".reef/run/live.log": "".join(f"21:{i:02d} s1 → step {i}\n" for i in range(40)) + "21:51 s1 session ended: in flight ['403'] · 1863.1 s · $6.11\n"})
        mod.runner_view = lambda root: (0, 0, "")   # no runner is running
        items = mod.inbox(d)
        kinds = [i["kind"] for i in items]
        self.assertIn("release", kinds, "work left in flight by the last run is an item\n" + str(kinds))
        self.assertIn("python3 scripts/reef-run.py release 403", [i["cmd"] for i in items])
        self.assertIn("run", kinds, "the loop is active and no runner runs: starting it is an item")
        self.assertIn("python3 scripts/reef run", [i["cmd"] for i in items])
        self.assertLess(kinds.index("release"), kinds.index("run"), "the leftover first: a restart would wait on it")
        model = mod.screen_model(d)
        lines, _ = mod.render(model, width=100, height=40, selected=0)
        runner = lines[lines.index("RUNNER  the last steps · w for the log"):]
        runner = runner[:next((i for i, l in enumerate(runner) if l.startswith(("DOCTOR", "─"))), len(runner))]
        self.assertLessEqual(len(runner), 8, "an idle runner's log is a tail of a few steps, not the screen\n" + "\n".join(runner))
        self.assertTrue(runner[-1].startswith("  (the run ended"), "and the tail ends by saying so\n" + "\n".join(runner))
        os.unlink(os.path.join(d, ".reef", "inflight", "403"))
        self.assertNotIn("release", [i["kind"] for i in mod.inbox(d)], "released: the item leaves with the marker (one source)")

    def test_the_screen_selects_by_digit_runs_inside_itself_and_edits_an_answer_on_screen(self):
        """2026-10-31, the owner: "shouldn't 1-9 select? why can't I execute from within — reef closes, runs, then a Return key to
        come back." The keys are one table: a digit SELECTS, Enter (or the same digit again) runs; a command runs inside the screen
        and its output sits in a panel until a key; `w` is the log, scrolled on the screen; an answer is typed on the screen with
        the recommendation prefilled. The screen never leaves curses for a command."""
        mod = load_script("reef", "reef_entry_under_test")
        src = open(ENTRY, encoding="utf-8").read()
        self.assertNotIn("run_shown", src, "no leaving the screen to run a command")
        self.assertNotIn("input(", src.split("def screen_loop", 1)[1].split("def cmd_approve", 1)[0], "no terminal prompt in the screen's loop")
        on = mod.on_key
        self.assertEqual(on(ord("3"), 0, 5, "inbox"), ("select", 2), "a digit selects")
        self.assertEqual(on(ord("3"), 2, 5, "inbox"), ("select", 2), "a digit only selects; Enter runs (two rules, as the keys line says)")
        self.assertEqual(on(ord("R"), 0, 5, "inbox"), ("verb", "run"), "one case: a caps lock is not silence")
        self.assertEqual(on(10, 1, 5, "inbox"), ("run", 1), "Enter runs the selected")
        self.assertEqual(on(ord("9"), 0, 2, "inbox"), None, "a digit past the list is nothing")
        self.assertEqual(on(ord("q"), 0, 2, "inbox"), ("quit",)); self.assertIsNone(on(27, 0, 2, "inbox"))   # Esc never quits (the CLI review)
        self.assertEqual(on(ord("w"), 0, 2, "inbox"), ("log",)); self.assertEqual(on(ord("w"), 0, 2, "log"), ("back",))
        self.assertEqual(on(ord("q"), 0, 2, "log"), ("back",), "q in the log view goes back, not out")
        self.assertEqual(on(ord("r"), 0, 2, "inbox"), ("verb", "run"))
        self.assertEqual(on(ord("j"), 0, 2, "inbox"), ("down",)); self.assertEqual(on(ord("k"), 1, 2, "inbox"), ("up",))
        edit = mod.edit_step
        self.assertEqual(edit("Batch 9", "!"), ("Batch 9!", None)); self.assertEqual(edit("Batch ", "é"), ("Batch é", None), "a whole character, not its bytes")
        self.assertEqual(edit("Batch 9", "\x7f"), ("Batch ", None)); self.assertEqual(edit("Batch 9", 263), ("Batch ", None))
        self.assertEqual(edit("Batch 9", "\n"), ("Batch 9", "done")); self.assertEqual(edit("x", "\x1b"), ("x", "cancel"))
        self.assertEqual(edit("a", 0x1b5b), ("a", None), "a special key the line does not know changes nothing")
        d = project(**{".reef/questions.md": "- row 7: Keep it? — recommended: yes\n",
                       ".reef/run/live.log": "".join(f"21:{i:02d} s1 → step {i}\n" for i in range(60))})
        model = mod.screen_model(d)
        panel = {"shown": "python3 scripts/reef-queue.py footnote yes --row 7", "rc": 0, "lines": [f"line {i}" for i in range(30)]}
        lines, sel = mod.render(model, width=100, height=36, selected=0, panel=panel)
        self.assertLessEqual(len(lines), 36)
        head = [l for l in lines if l.startswith("OUTPUT")]
        self.assertEqual(len(head), 1, "the command's output is a section on the screen\n" + "\n".join(lines))
        self.assertIn("footnote yes --row 7", head[0]); self.assertIn("exit 0", head[0])
        self.assertIn("  line 29", lines, "the last lines of the output, not the first")
        self.assertTrue(any(l.startswith("keys: q quit") for l in lines[-3:]), "the keys end the screen, quit first")
        log, _, _ = mod.render_log(model["log"], width=100, height=20, offset=0)
        self.assertLessEqual(len(log), 20)
        self.assertTrue(log[0].startswith("LOG"), log[0]); self.assertIn("step 59", "\n".join(log), "the newest lines first on the screen")
        log2, _, _ = mod.render_log(model["log"], width=100, height=20, offset=10)
        self.assertIn("step 49", log2[-2], "↑ scrolls back ten lines: the window ends ten earlier"); self.assertNotIn("step 59", "\n".join(log2))
        self.assertIn("1-9 select", mod.KEYS); self.assertIn("Enter runs", mod.KEYS); self.assertIn("w log", mod.KEYS); self.assertIn("a autopilot", mod.KEYS)
        # the panel is shed before the steps on a short terminal, and never silently
        lines, _ = mod.render(dict(model, steps=[f"s{i}" for i in range(30)]), width=100, height=18, selected=0, panel=panel)
        self.assertLessEqual(len(lines), 18)
        self.assertTrue(any(l.startswith("OUTPUT") for l in lines), "the panel's header survives a short terminal")
        self.assertTrue(any("more line(s) above" in l for l in lines), "a cut panel says so")

        # the loop itself, driven with a fake curses and a fake window (the owner's Python has no get_wch: getch only)
        class FakeCurses:
            A_REVERSE, A_BOLD, A_NORMAL = 1, 2, 0
            error = Exception
            def curs_set(self, *_): pass
            def flushinp(self): pass
            def update_lines_cols(self): pass
        class FakeWin:
            def __init__(self, keys): self.keys = list(keys); self.rows = []
            def getmaxyx(self): return (40, 120)
            def timeout(self, *_): pass
            def erase(self): pass
            def refresh(self): pass
            def clear(self): pass
            def move(self, *_): pass
            def clrtoeol(self): pass
            def addstr(self, y, x, text, *a): self.rows.append(text)
            def getch(self):
                k = self.keys.pop(0) if self.keys else ord("q")
                if k == -1:
                    settle()
                return k
        ran = []
        real_run = mod.run_captured
        mod.run_captured = lambda root, argv, timeout=900, sink=None: (ran.append(argv), (0, ["ok"]))[1]
        mod.doctor_lines = lambda root, fetch=False: []
        d2 = project(**{".reef/questions.md": "- row 7: Keep it? — recommended: yes\n- row 8: Rename it? — recommended: no\n"})
        win = FakeWin([-1, ord("i"), ord("2"), 10, 10, -1, ord("x"), 10, 10, -1, ord("q")])   # a tick (the readings land); i: the inbox (the screen opens on WORK since the fourth design); 2 selects; Enter runs it and opens the answer line; Enter keeps 'no'; x closes the panel; Enter, Enter again; q
        self.assertEqual(mod.screen_loop(win, d2, FakeCurses()), 0)
        self.assertEqual(len(ran), 2, "Enter ran the selected item twice (the second Enter, after the close): never the close key itself\n" + str(ran))
        self.assertIn("no", ran[0], "the recommendation kept with a plain Enter on the answer line")
        self.assertTrue(any(r.startswith("OUTPUT") for r in win.rows), "the output panel was drawn")
        # UTF-8 on the answer line through getch bytes: é is two bytes, one character
        win2 = FakeWin([0xC3, 0xA9, 10])
        self.assertEqual(mod.edit_line(win2, FakeCurses(), 1, 100, "a: ", "caf"), "café")
        # the child never sees the screen's keyboard (the security review): stdin is empty, prompts are off
        rc, out = real_run(d2, [sys.executable, "-c", "import os, sys; print(repr(sys.stdin.read()), os.environ.get('GIT_TERMINAL_PROMPT'))"])
        self.assertEqual((rc, out), (0, ["'' 0"]))

    def test_the_work_board_shows_the_batch_as_rows_with_state_tasks_lanes_and_what_can_start(self):
        """2026-10-31, the owner: "before I choose anything I want to see what is pending on this project, what I can start with,
        what can go in parallel and what cannot, the progress; then I choose the order, start the autopilot, and it shows me the
        tasks it will finish and which GitHub issues it will close." The screen opens on WORK: the current batch's rows with a
        state mark (✓ done, ▶ building, ○ ready, ⏸ blocked by whom, ⧖ yours), tasks n/m, depends, a lane (rows that share a module
        go one at a time; different modules run beside each other), the forge (its issue, its PR); the header carries the batch's
        progress and today's cost. PLAN is the progress view; `a` is the autopilot's start panel; `?` lists every key."""
        mod = load_script("reef", "reef_entry_under_test")
        d = project(**{
            "docs/queue.md": "# Queue\nCurrent batch: 2\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n"
                             "| 4 | legacy queue to issues (scripts/legacy-queue-issues.ts) | | planned | 2 | |\n"
                             "| 7 | move specs to reef/ (reef/specs) | | planned | 2 | |\n"
                             "| 8 | journal to issues (reef/specs/journal.md) | 7 | planned | 2 | |\n"
                             "| 10 | design conformance (src/lib/design.ts) | | planned | 2 | |\n"
                             "| 35 | shot-743 live take | 4, 7 | planned | 2 | |\n"
                             "| 99 | later thing | | planned | 3 | |\n",
            "reef/features/legacy-queue-to-issues/SPEC.md": "# x\n\nRow: 4\n",
            "reef/features/legacy-queue-to-issues/tasks/done/401-a.md": "---\nid: 401\nfeature: legacy-queue-to-issues\nstatus: done\n---\n",
            "reef/features/legacy-queue-to-issues/tasks/done/402-b.md": "---\nid: 402\nfeature: legacy-queue-to-issues\nstatus: done\n---\n",
            "reef/features/legacy-queue-to-issues/tasks/403-c.md": "---\nid: 403\nfeature: legacy-queue-to-issues\nstatus: in-progress\n---\n",
            "reef/features/move-specs-to-reef/SPEC.md": "# x\n\nRow: 7\n",
            "reef/features/move-specs-to-reef/tasks/701-a.md": "---\nid: 701\nfeature: move-specs-to-reef\nstatus: pending\n---\n",
            ".reef/run/run.log": '{"at": "%sT00:10:00Z", "cost_usd": 4.5, "mode": "autopilot"}\n' % time.strftime("%Y-%m-%d", time.gmtime()),
        })
        states = {"4": {"row": "4", "slug": "legacy-queue-to-issues", "state": "build", "next": "/reef-task", "detail": "1 open task(s) (PR #90)", "tasks": {"done": 2, "total": 3}},
                  "7": {"row": "7", "slug": "move-specs-to-reef", "state": "approval", "next": "/reef-plan", "detail": "the gate: Approve plan move-specs-to-reef at 0123456789abcdef?"}}
        mod.row_state = lambda root, row: states.get(str(row), {"row": str(row), "state": "plan", "next": "/reef-plan", "detail": ""})
        wm = mod.work_model(d)
        self.assertEqual(wm["batch"], "2")
        ids = [r["id"] for r in wm["rows"]]
        self.assertEqual(ids, ["4", "7", "8", "10", "35"], "the current batch's rows, in queue order; row 99 is batch 3")
        by = {r["id"]: r for r in wm["rows"]}
        self.assertEqual(by["4"]["mark"], "▶"); self.assertEqual(by["4"]["tasks"], (2, 3)); self.assertIn("PR #90", by["4"]["forge"])
        states["4"]["tasks"] = {"done": 1, "total": 4}   # the row machine's count wins over the main checkout's folder: the plan lives in the feature worktree until the merge
        self.assertEqual(mod.work_model(d)["rows"][0]["tasks"], (1, 4))
        del states["4"]["tasks"]
        self.assertEqual(by["7"]["mark"], "⧖", "a row at the owner's gate is his"); self.assertEqual(by["7"]["tasks"], (0, 1))
        self.assertEqual(by["8"]["mark"], "⏸"); self.assertIn("7", by["8"]["waits"], "blocked by an open row it depends on")
        self.assertEqual(by["10"]["mark"], "○", "no open depends, not building: can start now")
        self.assertEqual(by["35"]["waits"], ["4", "7"])
        self.assertEqual(by["7"]["lane"], by["8"]["lane"], "the same module (reef/specs, as reef-queue.py module_of cuts it): one lane, one at a time")
        self.assertNotEqual(by["4"]["lane"], by["10"]["lane"], "different modules: beside each other")
        self.assertEqual(wm["progress"]["rows"], (0, 5)); self.assertEqual(wm["progress"]["tasks"], (2, 4))
        self.assertEqual(wm["cost_today"], 4.5)
        lines, styles, sel = mod.render_work(wm, [], width=110, height=36, selected=1)
        self.assertLessEqual(len(lines), 36); self.assertTrue(all(len(l) <= 110 for l in lines))
        self.assertTrue(any(l.startswith("██████") for l in lines[:1]), "the banner first")
        self.assertIn("WORK", lines[6]); self.assertIn("INBOX", lines[6]); self.assertIn("PLAN", lines[6]); self.assertIn("LOG", lines[6])
        self.assertTrue(any("row" in l and "lane" in l and "forge" in l for l in lines), "the column head")
        row4 = next(l for l in lines if l.lstrip().startswith("▶ 4")); self.assertIn("2/3", row4)
        row8 = next(l for l in lines if l.lstrip().startswith("⏸ 8")); self.assertIn("waits: row 7", row8)
        row10 = next(l for l in lines if l.lstrip().startswith("○ 10")); self.assertIn("can start now", row10)
        self.assertIn("7", lines[sel], "the selected row"); self.assertFalse(lines[sel].startswith("▶"), "the highlight alone marks the selection — no second arrow")
        self.assertTrue(any(l.startswith("┌─ row 7") for l in lines), "the selected row's details under the table")
        self.assertEqual(styles.get(0), "banner"); self.assertIn(styles.get(sel), ("sel",))
        self.assertTrue(any(v == "done" or v == "wait" or v == "blocked" for v in styles.values()), "states carry colors")
        self.assertIn("batch 2", lines[1]); self.assertIn("0/5 rows", lines[1]); self.assertIn("2/4 tasks", lines[1]); self.assertIn("$4.50 today", lines[1])
        self.assertEqual([r["id"] for r in mod.ordered(dict(wm, order="start"))], ["10", "4", "7", "8", "35"], "o: what can start first, then building, yours, blocked")
        short, sstyles2, ssel = mod.render_work(wm, [], width=110, height=14, selected=4)
        self.assertLessEqual(len(short), 14); self.assertIn("35", short[ssel], "the selected row survives the shedding"); self.assertTrue(any("more (" in l for l in short), "the cut is said")
        wm["autopilot"] = {"on": True, "pid": 70417, "since": "01:22", "decided_today": 3}
        plan, pstyles, _ = mod.render_plan(wm, [], width=110, height=30)
        self.assertLessEqual(len(plan), 30)
        self.assertTrue(any("row 4" in l and "█" in l for l in plan), "a progress bar per row")
        self.assertTrue(any("decided by Mahmoud today" in l and "3" in l for l in plan))
        start, sstyles = mod.render_autopilot(wm, {"digest16": "11a6d568580789c5", "decides": ["plan", "question"], "never": "the release"}, width=110, height=30)
        self.assertTrue(start[0].startswith("AUTOPILOT")); self.assertIn("plan, question", start[0]); self.assertIn("the release", "\n".join(start))
        self.assertTrue(any("1." in l and "row 4" in l for l in start), "the order, the first row first")
        self.assertTrue(any("row 35" in l and "asks you" in l for l in start), "a row that waits on open rows: after them")
        self.assertTrue(any("Enter starts" in l for l in start))
        helps, _ = mod.render_help("work", width=100, height=30)
        for key in ("Tab", "?", "a", "i", "w", "q", "Enter", "1-9", "↑↓", "o"):
            self.assertTrue(any(key in l for l in helps), f"help names {key}")
        on = mod.on_key
        self.assertEqual(on(9, 0, 3, "work"), ("view", "inbox")); self.assertEqual(on(9, 0, 3, "inbox"), ("view", "plan"))
        self.assertEqual(on(ord("?"), 0, 3, "work"), ("help",)); self.assertEqual(on(ord("i"), 0, 3, "work"), ("view", "inbox"))
        self.assertEqual(on(ord("a"), 0, 3, "work"), ("autopilot",)); self.assertEqual(on(ord("o"), 0, 3, "work"), ("order",))
        self.assertEqual(on(ord("3"), 0, 5, "work"), ("select", 2)); self.assertEqual(on(10, 1, 5, "work"), ("open", 1))
        self.assertEqual(on(10, 1, 5, "plan"), ("open", 1), "PLAN shows rows: Enter never runs an inbox item the view does not show (the security review)")
        self.assertEqual(on(ord("q"), 0, 2, "log"), ("back",))
        self.assertEqual(on(27, 0, 3, "help"), ("back",)); self.assertEqual(on(ord("q"), 0, 3, "help"), ("back",))   # to the page it was opened from
        attrs = mod.style_attrs({"A_REVERSE": 1, "A_BOLD": 2, "A_NORMAL": 0, "A_DIM": 4}, colors=False)
        self.assertEqual(attrs["sel"], 1); self.assertEqual(attrs["banner"], 2); self.assertEqual(attrs["done"], 4, "done is dim, not green: the eye goes to what can start")
        class C:   # a curses with colors: the palette that reads at a glance
            A_REVERSE, A_BOLD, A_NORMAL, A_DIM = 1, 2, 0, 4
            COLOR_GREEN, COLOR_CYAN, COLOR_YELLOW, COLOR_RED, COLOR_WHITE = 10, 11, 12, 13, 14
            pairs = {}
            def has_colors(self): return True
            def start_color(self): pass
            def use_default_colors(self): pass
            def init_pair(self, i, fg, bg): self.pairs[i] = fg
            def color_pair(self, i): return 100 * i
        c = C(); attrs = mod.style_attrs(c, colors=True)
        self.assertEqual(c.pairs[1], 10); self.assertEqual(attrs["ready"], 100 | 2, "can start = green, bold"); self.assertEqual(attrs["blocked"], 400 | 2, "blocked = red")
        self.assertEqual(attrs["banner"], 300 | 2, "the banner in color"); self.assertEqual(attrs["done"], 500 | 4, "done is dim")
        # 2026-10-31 02:08, the owner: "how do I know if the runner is working, doing something or dead?" — the log was silent
        # 20 minutes while a converge run ran under the session: the runner line names the live child and the silence
        tree = [(70418, 70417, "01:03:44", "claude -p /reef-loop …"), (72923, 70418, "22:54", "/bin/zsh -c source snapshot.sh && python3 scripts/reef-converge legacy-queue-to-issues"),
                (72927, 72923, "22:54", "/Library/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python scripts/reef-converge legacy-queue-to-issues"),
                (48446, 72927, "00:11", "/usr/bin/python3 /x/.reef/worktrees/legacy-queue-to-issues/scripts/reef-graph lock heavy -- npm exec vitest run -t legacy"),
                (48452, 48446, "00:11", "npm exec vitest run -t legacy archive: each ledger keeps its bytes")]
        doing = mod.session_doing(70418, tree)
        self.assertEqual(doing, "running: reef-converge legacy-queue-to-issues (22:54)", "the Reef script in the chain, its argument, how long it has run")
        self.assertIn("running: vitest", mod.session_doing(1, [(2, 1, "00:40", "/bin/zsh -c x"), (3, 2, "00:39", "npm exec vitest run -t a"), (4, 1, "00:01", "node helper.cjs")]), "no Reef script: the deepest; a young helper beside the work is ignored")
        self.assertEqual(mod.session_doing(70418, [(70418, 70417, "01:03:44", "claude -p")]), "", "no child: the session is thinking")
        self.assertEqual(mod.session_doing(0, tree), "")
        os.utime(os.path.join(d, ".reef", "run", "run.log"), (time.time() - 1500, time.time() - 1500))
        open(os.path.join(d, ".reef", "run", "live.log"), "w").write("01:54 s1 last\n"); os.utime(os.path.join(d, ".reef", "run", "live.log"), (time.time() - 1500, time.time() - 1500))
        line = mod.runner_line(d, 70417, 70418, "01:06", tree)
        self.assertIn("pid 70417", line); self.assertIn("quiet 25 min", line); self.assertIn("running: ", line)
        self.assertIn("thinking", mod.runner_line(d, 70417, 70418, "01:06", [(70418, 70417, "1:00", "claude -p")]))
        os.makedirs(os.path.join(d, ".reef", "run", "jobs"), exist_ok=True)   # the runner's own record of its long work comes before the process table
        open(os.path.join(d, ".reef", "run", "jobs", "gate-4.json"), "w").write(json.dumps({"name": "gate-4", "pid": os.getpid(), "cmd": ["sh", "scripts/reef-gate.sh", "full"], "started_ts": time.time() - 700}))
        self.assertIn("job gate-4 (11 min)", mod.runner_line(d, 70417, 70418, "01:06", tree))
        open(os.path.join(d, ".reef", "run", "jobs", "gate-4.json"), "w").write(json.dumps({"name": "gate-4", "pid": os.getpid(), "cmd": ["x"], "started_ts": time.time(), "rc": 0}))
        self.assertNotIn("job gate-4", mod.runner_line(d, 70417, 70418, "01:06", tree), "an ended job is not running")
        self.assertEqual(mod.runner_line(d, 0, 0, ""), "no runner is running"); self.assertIn("gone", mod.runner_line(d, 0, 70418, "01:06", tree))
        self.assertIn("since 23:56 ", mod.runner_line(d, 70417, 70418, "2026-10-30T23:56:56Z", tree) + " ", "the runner's ISO start as a clock time")
        os.makedirs(os.path.join(d, ".reef", "approvals"), exist_ok=True)
        open(os.path.join(d, ".reef", "approvals", "move-specs.json"), "w").write('{"digest16": "73b12e4b024b95eb", "approved_at": "%sT21:42:42Z", "by": "mahmoud (proxy)"}' % time.strftime("%Y-%m-%d", time.gmtime()))
        open(os.path.join(d, ".reef", "approvals", "older.json"), "w").write('{"digest16": "x", "approved_at": "2026-10-01T00:00:00Z", "by": "mahmoud (proxy)"}')
        open(os.path.join(d, ".reef", "approvals", "mine.json"), "w").write('{"digest16": "y", "approved_at": "%sT09:00:00Z"}' % time.strftime("%Y-%m-%d", time.gmtime()))
        self.assertEqual(mod.autopilot_view(d)["decided_today"], 1, "his plan approval today counts; an older one and the owner's own do not")
        # the loop on the board (a fake curses, as the inbox test below): Enter on a row that is yours opens INBOX on its item — no subprocess
        # (the CLI review: reef-row.py ran on the UI thread to show what the box showed); Tab shows PLAN, Enter there does the same; q quits
        class FC:
            A_REVERSE, A_BOLD, A_NORMAL = 1, 2, 0
            error = Exception
            def curs_set(self, *_): pass
            def flushinp(self): pass
            def update_lines_cols(self): pass
            def has_colors(self): return False
        class FW:
            def __init__(self, keys): self.keys = list(keys); self.rows = []
            def getmaxyx(self): return (40, 120)
            def timeout(self, *_): pass
            def erase(self): pass
            def refresh(self): pass
            def addstr(self, y, x, text, *a): self.rows.append(text)
            def getch(self):
                k = self.keys.pop(0) if self.keys else ord("q")
                if k == -1:
                    settle()
                return k
        ran = []
        mod.run_captured = lambda root, argv, timeout=900, sink=None: (ran.append(argv), (0, ["state: build"]))[1]
        mod.doctor_lines = lambda root, fetch=False: []
        mod.inbox = lambda root, doctor=None, runner=None: [{"kind": "approve", "text": "x", "argv": [sys.executable, "-c", "pass"], "cmd": "approve x", "row": "7", "recommended": "", "issue": ""}]
        win = FW([-1, ord("2"), 10, 9, 10, ord("q")])   # a tick (the board lands); 2 selects row 7, Enter: INBOX on its item; Tab → PLAN; Enter there: INBOX again; q
        self.assertEqual(mod.screen_loop(win, d, FC()), 0)
        self.assertEqual(ran, [], "Enter on a row runs nothing")
        self.assertTrue(any("▶ 1  approve  x" in r for r in win.rows), "the row's item, selected on INBOX\n" + "\n".join(win.rows[-40:]))
        self.assertTrue(any(r.startswith("PLAN") for r in win.rows), "Tab reached PLAN")

    def test_an_empty_project_has_only_the_doctors_fixes_in_its_inbox(self):
        d = project()
        r = reef("screen", "--once", "--repo", d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        items = [l for l in r.stdout.splitlines() if re.match(r"^\s*\d+\s+\w+", l)]
        self.assertTrue(all(re.match(r"^\s*\d+\s+fix\b", l) for l in items), "no approval, question or park: only the doctor's fixes, if any\n" + r.stdout)
        mod = load_script("reef", "reef_entry_under_test")
        self.assertEqual(mod.inbox(d), [], "without the doctor's lines the inbox is empty")
        self.assertIn("nothing waits on you", mod.screen_text(d))

    def test_the_model_asks_the_row_machine_for_a_rows_command(self):
        mod = load_script("reef", "reef_entry_under_test")
        d = project(**{".reef/loop.json": '{"active": true, "wait": "owner: row 9 needs you", "stop": null, "parked": null, "hashes": []}'})
        mod.row_state = lambda root, row: {"row": row, "state": "approval", "detail": "the gate: … — in the terminal: " + self.APPROVE}
        items = mod.inbox(d)
        self.assertEqual([i["kind"] for i in items], ["approve"])
        self.assertEqual(items[0]["cmd"], self.APPROVE)
        mod.row_state = lambda root, row: {"row": row, "state": "build", "detail": "2 open task(s)"}
        self.assertEqual(mod.inbox(d), [], "a row that is building asks nothing of the owner")

    def test_approve_and_answer_are_verbs_that_run_the_exact_commands(self):
        d = project(**{".reef/questions.md": "- row 7: Keep the old route? — recommended: yes\n- row 8: Rename it? — recommended: no\n"})
        r = reef("approve", "9", "--repo", d, "--dry-run")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("row 9", r.stdout + r.stderr)
        self.assertIn("nothing to approve", r.stdout + r.stderr)
        r = reef("answer", "7", "yes, keep it", "--repo", d, "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("reef-queue.py footnote 'yes, keep it' --row 7", r.stdout)
        self.assertIn("row 7", open(os.path.join(d, ".reef", "questions.md")).read(), "a dry run clears nothing")
        mod = load_script("reef", "reef_entry_under_test")
        mod.row_state = lambda root, row: {"row": row, "state": "approval", "detail": "… — in the terminal: " + TheScreen.APPROVE}
        ran, orig = [], subprocess.run
        try:
            mod.subprocess.run = lambda cmd, **kw: ran.append(cmd) or orig(["true"], capture_output=True)   # the module's subprocess is the one subprocess: restore it
            self.assertEqual(mod.main(["approve", "9", "--repo", d]), 0)
        finally:
            subprocess.run = orig
        self.assertEqual(ran[-1][1:], [mod.script("reef-approval.py"), "--owner", "Approve plan reconcile-instruction-layer at 2cc8e8c3487e9ab2?"], "the question, never a placeholder — and no resume of the entry's own: reef-approval.py resumes (the review)")

    def test_no_shell_between_the_screen_and_a_command(self):
        # the reviews of #221: every item is an argv list — never a string a shell parses — and agent-written text (a row
        # in questions.md, a feature slug in the row machine's detail, a doctor line with prose) never becomes a command
        mod = load_script("reef", "reef_entry_under_test")
        d = project(**{
            ".reef/loop.json": '{"active": true, "wait": "owner: row 9 and row 7;rm needs you (Approve plan demo at 0123456789abcdef?)", "stop": null, "parked": "x", "hashes": []}',
            ".reef/questions.md": "- row 7;echo pwned: Keep it? — recommended: yes\n- row 8: Rename it? — recommended: no\n",
        })
        mod.row_state = lambda root, row: {"row": row, "state": "approval", "detail": 'in the terminal: python3 scripts/reef-approval.py --owner "Approve plan $(cmd) at 0123456789abcdef?"'}
        doctor = ["WARN hold: a dead session — python3 scripts/reef-loop.py unlock   (a dead session's hold; the runner takes one over)",
                  "WARN gate probe: none — the runner refuses to start — python3 scripts/reef-run.py probe"]
        items = mod.inbox(d, doctor)
        for it in items:
            self.assertIsInstance(it["argv"], list, it)
            self.assertTrue(it["argv"][0] == sys.executable or it["argv"][0] == "python3" and False, f"the interpreter, resolved: {it['argv']}")
        kinds = [(i["kind"], i["row"]) for i in items]
        self.assertIn(("approve", None), kinds, "the wait's own question")
        self.assertNotIn(("approve", "9"), kinds, "a slug outside the approval regex ($(cmd)) is never a command")
        self.assertIn(("answer", "8"), kinds)
        self.assertNotIn(("answer", "7;echo pwned"), kinds, "a row is digits")
        self.assertEqual([i["argv"][-1] for i in items if i["kind"] == "fix"], ["probe"], "a fix with prose or shell syntax is not an item; the probe is")
        q = [i for i in items if i["kind"] == "approve"][0]
        self.assertEqual(q["argv"][2:], ["--owner", "Approve plan demo at 0123456789abcdef?"], "the question is ONE argument")
        self.assertEqual(q["cmd"], 'python3 scripts/reef-approval.py --owner "Approve plan demo at 0123456789abcdef?"', "shown as the line the owner would type")

    def test_the_inbox_reads_a_doctors_fix_as_its_last_part_and_never_shows_a_placeholder(self):
        mod = load_script("reef", "reef_entry_under_test")
        d = project()
        doctor = ["WARN gate probe: none — the runner refuses to start — python3 scripts/reef-run.py probe",
                  "WARN setup: scripts/reef-setup.py is missing — python3 <plugin>/scripts/reef-update.py --commit",
                  "WARN env: the local gate reads .env — compare once: DATABASE_URL= npm test",
                  "OK   scripts: match"]
        items = mod.inbox(d, doctor)
        self.assertEqual([i["cmd"] for i in items], ["python3 scripts/reef-run.py probe"],
                         "the fix is the last dash part; a line with <…> is not a command the owner can run; prose is not a command")

    def test_the_doctor_never_prints_a_placeholder(self):
        # the screen runs what the doctor prints — so the doctor prints the plugin's real path, never `<plugin>`
        d = project()
        r = reef("doctor", "--repo", d)
        self.assertNotIn("<plugin>", r.stdout + r.stderr, r.stdout)

    def test_reef_alone_is_the_menu_off_a_terminal(self):
        r = reef("--repo", project())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("screen", r.stdout, "the menu names the screen")
        self.assertNotIn("INBOX", r.stdout, "no terminal: the menu, not the screen")


class TheScreenNeverFreezes(unittest.TestCase):
    """2026-10-31 03:05, the owner's first run of the fourth screen on an issues queue: "nothing works and still in black and white"
    — the board asked the row machine about every row, one subprocess after another, on the UI thread; the first frame stayed for
    minutes and the keys were dead. Now every reading runs in a thread, the rows are read four at a time, and q works at once."""

    def test_the_rows_are_read_in_parallel_and_the_keys_work_while_the_board_loads(self):
        import time as _t
        mod = load_script("reef", "reef_entry_under_test")
        d = project(**{"docs/queue.md": "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n"
                                        + "".join(f"| {i} | row {i} (src/m{i}) | | planned | 1 | |\n" for i in range(1, 9))})
        mod.row_state = lambda root, row: (_t.sleep(0.25), {"row": str(row), "state": "plan", "next": "", "detail": ""})[1]
        t0 = _t.time(); wm = mod.work_model(d); dt = _t.time() - t0
        self.assertEqual(len(wm["rows"]), 8); self.assertLess(dt, 1.2, f"eight rows at 0.25 s each took {dt:.2f} s: not in parallel")
        self.assertEqual(mod.BOARD["done"], 8)
        # the loop: a slow board, a slow doctor — the placeholder frame is drawn, q quits at once
        class FC:
            A_REVERSE, A_BOLD, A_NORMAL = 1, 2, 0
            error = Exception
            def curs_set(self, *_): pass
            def flushinp(self): pass
            def update_lines_cols(self): pass
            def has_colors(self): return False
        class FW:
            def __init__(self, keys): self.keys = list(keys); self.rows = []; self.timeouts = []
            def getmaxyx(self): return (40, 120)
            def timeout(self, ms): self.timeouts.append(ms)
            def erase(self): pass
            def refresh(self): pass
            def addstr(self, y, x, text, *a): self.rows.append(text)
            def getch(self): return self.keys.pop(0) if self.keys else ord("q")
        mod.work_model = lambda root, runner=None, states=True: (_t.sleep(3), {"rows": [], "facts": ["x"] * 5, "progress": {"rows": (0, 0), "tasks": (0, 0)}, "cost_today": 0, "autopilot": {}, "order": "queue", "cap": 2, "at": _t.time()})[1]
        mod.doctor_lines = lambda root, fetch=False: (_t.sleep(3), [])[1]
        win = FW([-1, -1, ord("q")])
        t0 = _t.time(); self.assertEqual(mod.screen_loop(win, d, FC()), 0); dt = _t.time() - t0
        self.assertLess(dt, 1.5, f"q took {dt:.2f} s while the board loaded: the UI thread ran a reading")
        self.assertTrue(any("reading the" in r for r in win.rows), "the placeholder frame says what it waits for")
        self.assertTrue(any("keys work" in r for r in win.rows))
        self.assertIn(400, win.timeouts, "while a reading runs the screen redraws often")
        self.assertTrue(mod.QUIT.is_set(), "q sets QUIT")
        self.assertFalse([t for t in __import__("threading").enumerate() if not t.daemon and t is not __import__("threading").main_thread()],
                         "no non-daemon thread outlives the screen: q returns the prompt at once (the review: an executor's workers would hold the exit)")
        # the row readers stop at QUIT: eight slow rows, QUIT set after the first wave — read_rows returns at once with what it has
        mod.QUIT.clear(); seen = []
        def slow(rid):
            seen.append(rid); _t.sleep(0.2); mod.QUIT.set(); return {}
        t0 = _t.time(); out = mod.read_rows([str(i) for i in range(8)], slow); dt = _t.time() - t0
        self.assertLess(dt, 0.6, f"the readers kept taking rows after QUIT: {dt:.2f} s"); self.assertLessEqual(len(out), 4)
        mod.QUIT.clear()
        # a reading that raises is shown, not swallowed into "reading …" forever
        mod.work_model = lambda root, runner=None, states=True: (_ for _ in ()).throw(RuntimeError("the queue file is not a table"))
        mod.doctor_lines = lambda root, fetch=False: []
        win = FW([-1, -1, -1, ord("q")])
        self.assertEqual(mod.screen_loop(win, d, FC()), 0)
        self.assertTrue(any("reading failed" in r and "RuntimeError" in r for r in win.rows), "the error is on the screen\n" + "\n".join(win.rows[-12:]))


class TheUpdateIsReefs(unittest.TestCase):
    """docs/design/owner-hands-off.md step 6 (2026-10-31): after a merge in Reef a person told the owner to run `reef update`, then two
    Claude Code commands. Now the screen's doctor reading fetches the plugin clone itself, every UPDATE_SECONDS in its thread; the
    doctor's lines about a new Reef name one verb, so the inbox holds ONE item (`update`) and the headers say a new Reef waits; `u` or
    Enter on it runs `reef update` inside the screen, and the update refreshes the marketplace itself."""

    class FC:
        A_REVERSE, A_BOLD, A_NORMAL = 1, 2, 0
        error = Exception
        def curs_set(self, *_): pass
        def flushinp(self): pass
        def update_lines_cols(self): pass
        def has_colors(self): return False

    class FW:
        def __init__(self, keys): self.keys = list(keys); self.rows = []
        def getmaxyx(self): return (40, 120)
        def timeout(self, *_): pass
        def erase(self): pass
        def refresh(self): pass
        def addstr(self, y, x, text, *a): self.rows.append(text)
        def getch(self):
            k = self.keys.pop(0) if self.keys else ord("q")
            if callable(k):   # a step of the test between two ticks (the clock moves on)
                k(); k = -1
            if k == -1:
                settle()   # a tick: the readings land meanwhile
            return k

    def test_the_real_doctors_lines_are_one_item_on_the_inbox_and_the_headers_say_so(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import test_doctor as D
        mod = load_script("reef", "reef_entry_under_test")
        d = project(**{"scripts/reef": "# a stale copy of the entry point\n", "docs/queue.md": "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n"})
        clone, bare, g = D.plugin_with_upstream()
        D.upstream_moves(bare, g, "The board counts tasks where the folder is")
        old = os.environ.get("CLAUDE_PLUGIN_ROOT")
        os.environ["CLAUDE_PLUGIN_ROOT"] = clone
        try:
            lines = mod.doctor_lines(d, fetch=True)   # the screen's reading: the real doctor, the real fetch
        finally:
            os.environ.pop("CLAUDE_PLUGIN_ROOT", None) if old is None else os.environ.__setitem__("CLAUDE_PLUGIN_ROOT", old)
        self.assertGreaterEqual(sum(1 for l in lines if l.endswith(" — python3 scripts/reef update")), 2, "the doctor said it more than once:\n" + "\n".join(lines))
        items = mod.inbox(d, lines)
        ups = [i for i in items if i["cmd"] == mod.UPDATE_SHOWN]
        self.assertEqual(len(ups), 1, "one item for a new Reef, not one per doctor line\n" + str(items))
        self.assertEqual([i["kind"] for i in items if i["kind"] == "update"], ["update"], str(items))
        self.assertTrue(all(i["kind"] == "fix" for i in items if i is not ups[0]), "the doctor's other fixes (the probe) stay fixes: " + str(items))
        self.assertIn("a new Reef, 1 commit(s) since your copy: The board counts tasks", ups[0]["text"])
        self.assertEqual(ups[0]["argv"], [sys.executable, "scripts/reef", "update"], "the project's own entry point, run from the project")
        model = mod.screen_model(d, lines)
        self.assertIn("a new Reef waits (u)", model["facts"][0], "the inbox header says it beside the version")
        wm = {"rows": [], "facts": ["demo · Reef 0.7.3", "", "", "", ""], "progress": {"rows": (0, 0), "tasks": (0, 0)}, "cost_today": 0, "autopilot": {}, "order": "queue", "cap": 2, "at": time.time()}
        work, _, _ = mod.render_work(wm, model["items"], width=120, height=30)
        self.assertIn("a new Reef waits (u)", work[0], "the board — the first view — says it too")
        work, _, _ = mod.render_work(wm, [], width=120, height=30)
        self.assertNotIn("a new Reef", work[0])
        self.assertNotIn("a new Reef", mod.screen_model(d, [])["facts"][0])

    def test_the_screen_asks_the_forge_itself_minutes_apart_and_enter_or_u_applies_it(self):
        mod = load_script("reef", "reef_entry_under_test")
        d = project()
        reads = []
        mod.doctor_lines = lambda root, fetch=False: (reads.append(fetch), ["WARN plugin: a new Reef, 2 commit(s) since your copy: Two fixes — python3 scripts/reef update"])[1]
        mod.work_model = lambda root, runner=None, states=True: {"rows": [], "facts": ["x"] * 5, "progress": {"rows": (0, 0), "tasks": (0, 0)}, "cost_today": 0, "autopilot": {}, "order": "queue", "cap": 2, "at": time.time()}
        ran = []
        mod.run_captured = lambda root, argv, timeout=900, sink=None: (ran.append(argv), (0, ["reef update: done"]))[1]
        restarted = []
        mod.restart_screen = lambda curses: restarted.append(1)   # a successful update restarts the screen (os.execv) — not inside a test
        def age_out():
            mod.UPDATE_SECONDS = 0.1   # fifteen minutes pass
        mod.run_captured = lambda root, argv, timeout=900, sink=None: (ran.append(argv), (0, ["python3 scripts/reef-row.py state 7"]))[1]
        win = self.FW([-1, -1, -1, ord("g"), -1, -1, age_out, -1, -1, ord("i"), ord("q")])   # ticks; g (a command's re-read, no fetch); the reading ages; i the inbox; q
        self.assertEqual(mod.screen_loop(win, d, self.FC()), 0)
        self.assertEqual(reads[:2], [True, False], f"the first reading fetches; a re-read after g does not (the forge is asked minutes apart, not after every key): {reads}")
        self.assertIn(True, reads[2:], f"once the reading is UPDATE_SECONDS old, the doctor fetches again: {reads}")
        self.assertTrue(any("update" in r and "2 commit(s)" in r for r in win.rows), "the item is on the inbox\n" + "\n".join(win.rows[-30:]))
        mod.UPDATE_SECONDS = 900; ran.clear()
        mod.run_captured = lambda root, argv, timeout=900, sink=None: (ran.append(argv), (0, ["reef update: done"]))[1]
        self.assertEqual(mod.screen_loop(self.FW([-1, -1, -1, ord("i"), 10, -1, ord("x")]), d, self.FC()), 0)   # ticks: the doctor lands, then the inbox with its item; Enter, the update lands, a key restarts
        self.assertEqual(ran, [[sys.executable, "scripts/reef", "update"]], "Enter on the item runs the one verb\n" + str(ran))
        self.assertEqual(restarted, [1], "and a successful update restarts the screen; nothing after it runs in the old process")
        self.assertEqual(mod.on_key(ord("u"), 0, 0, "work"), ("verb", "update"))
        self.assertGreaterEqual(load_script("reef", "reef_entry_under_test").UPDATE_SECONDS, 300, "a fetch is a network call: minutes apart, not every tick")
        # a doctor that does not answer is a failed reading on the screen, not "nothing wrong" kept for fifteen minutes
        mod.doctor_lines = lambda root, fetch=False: None
        win = self.FW([-1, -1, ord("i"), -1, ord("q")])
        self.assertEqual(mod.screen_loop(win, d, self.FC()), 0)
        self.assertTrue(any("reading failed" in r and "doctor: no answer" in r for r in win.rows), "\n".join(win.rows[-20:]))
        self.assertFalse(any("DOCTOR  nothing wrong" in r for r in win.rows))

    def test_reef_update_refreshes_the_marketplace_itself_re_enables_the_plugin_and_hands_the_owner_no_step(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import test_doctor as D
        clone, bare, g = D.plugin_with_upstream()
        d = project()
        with open(os.path.join(d, ".reef", "config.json"), "w") as f:
            json.dump({"branches": {"base": "main", "feature_prefix": "feat/"}, "paths": {"queue": "reef/queue.md"}, "gates": {"full": "true"}}, f)
        os.makedirs(os.path.join(d, "reef"), exist_ok=True)
        open(os.path.join(d, "reef", "queue.md"), "w").write("# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 1 | a | | planned | 1 | |\n")
        g(d, "add", "-A"); g(d, "commit", "-qm", "init")
        pbare = tempfile.mkdtemp(prefix="reef-origin.")
        subprocess.run(["git", "clone", "-q", "--bare", d, pbare], check=True)
        g(d, "remote", "add", "origin", pbare); g(d, "fetch", "-q", "origin"); g(d, "branch", "-q", "-u", "origin/main")
        home = tempfile.mkdtemp(prefix="reef-home.")
        os.makedirs(os.path.join(home, ".claude", "plugins"))
        with open(os.path.join(home, ".claude", "plugins", "known_marketplaces.json"), "w") as f:
            json.dump({"mymarket": {"source": {"source": "directory", "path": clone}, "installLocation": clone}}, f)
        fake_bin = tempfile.mkdtemp(prefix="reef-bin.")
        calls = os.path.join(fake_bin, "claude-calls.txt")
        with open(os.path.join(fake_bin, "claude"), "w") as f:   # a `claude` that records its argv; its `plugin list` says the plugin is DISABLED (the 2026-10-28 incident)
            f.write("#!/bin/sh\nprintf '%s\\n' \"$*\" >> " + shlex.quote(calls) + "\n"
                    "case \"$*\" in\n  'plugin list'*) printf 'Installed plugins:\\n\\n  \u276f reef@mymarket\\n    Version: 0.7.3\\n    Status: \u2718 disabled\\n' ;;\n"
                    "  *) printf '%s\\n' '{\"outcome\":\"ok\"}' ;;\nesac\n")
        os.chmod(os.path.join(fake_bin, "claude"), 0o755)
        ident = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        env = dict(os.environ, HOME=home, CLAUDE_PLUGIN_ROOT=clone, PATH=fake_bin + os.pathsep + "/usr/bin:/bin", **ident)
        r = subprocess.run([sys.executable, ENTRY, "update", "--repo", d], capture_output=True, text=True, env=env, timeout=600)
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertTrue(os.path.exists(calls), "the update refreshed the marketplace itself (claude plugin marketplace update)\n" + out)
        called = open(calls, encoding="utf-8").read().splitlines()
        self.assertIn("plugin marketplace update mymarket", called)
        self.assertIn("plugin enable reef@mymarket", called, "the refresh left the plugin disabled: Reef enabled it again, the owner was not told to\n" + out)
        self.assertIn("left reef@mymarket disabled — enabled it again", r.stdout)
        self.assertIn("marketplace mymarket refreshed", r.stdout)
        self.assertNotIn("/plugin marketplace update", out, "no step handed to the owner — not by reef update, not by reef-update.py under it\n" + out)
        self.assertNotIn("now, in Claude Code", out); self.assertNotIn("reef doctor", r.stdout.split("reef update: done")[1])
        self.assertIn("/reload-plugins", r.stdout, "a window open now is told, once, what reloads it")
        # no `claude` on this PATH: the step cannot run here, so the line names it — with the real name, never a placeholder
        r = subprocess.run([sys.executable, ENTRY, "update", "--repo", d], capture_output=True, text=True, env=dict(env, PATH="/usr/bin:/bin"), timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("/plugin marketplace update mymarket, then /reload-plugins", r.stdout)
        self.assertNotIn("<", r.stdout.split("reef update: done")[1])


class TheLogIsOnTheScreen(unittest.TestCase):
    """2026-10-31, the owner: "when I open the log it should appear in a big box under the screen, with navigation". The board carries
    the runner's last lines under the table (colored: → cyan started, ← green returned, red failed, yellow a wait), shed first on a
    short terminal; `w` opens the whole log as a page that scrolls by line and by page, jumps to the ends, and finds a line (`/`, then
    `n` for the next older one)."""

    LOG = [f"21:{i:02d} s1 → Implement {1200 + i} (reef:implementer)" if i % 3 == 0 else f"21:{i:02d} s1 ← Verify {1200 + i}: GREEN" if i % 3 == 1
           else f"21:{i:02d} s1 ← Gate {1200 + i}: FAIL" for i in range(40)] + ["21:40 s1 WAIT owner: row 7 needs you"]

    def test_the_board_carries_the_runners_last_lines_colored_and_sheds_them_first(self):
        mod = load_script("reef", "reef_entry_under_test")
        wm = {"rows": [{"id": "7", "mark": "▶", "tasks": (1, 3), "lane": "src/a", "state": "build", "detail": "1 open task", "next": "tick", "depends": [], "forge": "PR #9", "item": "row seven"}],
              "facts": ["demo · Reef 0.7.4", "", "", "", ""], "progress": {"rows": (0, 1), "tasks": (1, 3)}, "cost_today": 0, "autopilot": {}, "order": "queue", "cap": 2, "at": time.time()}
        lines, st, sel = mod.render_work(wm, [], width=120, height=40, selected=0, log=self.LOG)
        head = [i for i, l in enumerate(lines) if l.startswith("LOG")]
        self.assertEqual(len(head), 1, "one LOG section on the board\n" + "\n".join(lines))
        self.assertIn("w opens it", lines[head[0]])
        body = lines[head[0] + 1:head[0] + 9]
        self.assertTrue(body[-1].endswith("row 7 needs you"), "the newest line last\n" + "\n".join(lines))
        self.assertTrue(any("21:33" in l for l in body) and not any("21:20" in l for l in body), "the last eight lines, not the first")
        self.assertEqual([st.get(head[0] + 1 + i) for i in range(8)], [mod.log_style(l) for l in self.LOG[-8:]], "each line styled by what it says")
        self.assertIn("blocked", [st.get(head[0] + 1 + i) for i in range(8)])
        self.assertEqual(mod.log_style("21:00 s1 → Implement 1200 (reef:implementer)"), "build")
        self.assertEqual(mod.log_style("21:00 s1 → Implement 1203: fix the error path, red first (reef:implementer)"), "build", "a title is prose, not a verdict")
        self.assertEqual(mod.log_style("21:01 s1 ← Verify 1201: GREEN"), "done")
        self.assertEqual(mod.log_style("21:01 s1 ← Implement 1201: returned"), "", "returned is no verdict: no color")
        self.assertEqual(mod.log_style("21:02 s1 ← Gate 1202: FAIL"), "blocked")
        self.assertEqual(mod.log_style("21:02 s1 ← Implement the red-first test: completed"), "done", "the verdict is read, not the name")
        self.assertEqual(mod.log_style("21:02 s1 ← gate-4 rc=1 (3 min)"), "blocked")
        self.assertEqual(mod.log_style("21:02 s1 jobs done: gate-801 rc=0 — this session continues their rows"), "")
        self.assertEqual(mod.log_style("21:02 s1 job converge-8: killed after 180 min"), "blocked")
        self.assertEqual(mod.log_style("21:40 s1 WAIT owner: row 7 needs you"), "wait")
        self.assertEqual(mod.log_style("21:41 the runner ended"), "")
        # a short terminal: the log lines go before the row's box and the rows; the header stays
        short, st2, _ = mod.render_work(wm, [], width=120, height=24, selected=0, log=self.LOG)
        self.assertLessEqual(len(short), 24)
        self.assertTrue(any(l.startswith("LOG") for l in short), "the header survives")
        box = lambda ls: sum(1 for l in ls if l.startswith("│ "))
        self.assertEqual(box(short), box(lines), "the row's box is whole: the log paid first")
        self.assertLess(sum(1 for l in short if l.startswith("  21:")), 8); self.assertGreaterEqual(sum(1 for l in short if l.startswith("  21:")), 2, "the newest two stay")
        empty, _, _ = mod.render_work(wm, [], width=120, height=40, selected=0, log=[])
        self.assertTrue(any(l.startswith("LOG") and "no live log yet" in l for l in empty), "\n".join(empty))

    def test_the_log_page_scrolls_by_page_jumps_to_the_ends_and_finds_a_line(self):
        mod = load_script("reef", "reef_entry_under_test")
        on = mod.on_key
        self.assertEqual(on(mod.KEY_PPAGE, 0, 0, "log"), ("page_up",)); self.assertEqual(on(mod.KEY_NPAGE, 0, 0, "log"), ("page_down",))
        self.assertEqual(on(mod.KEY_HOME, 0, 0, "log"), ("top",)); self.assertEqual(on(mod.KEY_END, 0, 0, "log"), ("bottom",))
        self.assertEqual(on(ord("/"), 0, 0, "log"), ("search",)); self.assertEqual(on(ord("n"), 0, 0, "log"), ("next",))
        self.assertEqual(on(ord("q"), 0, 0, "log"), ("back",), "q still goes back")
        self.assertEqual(mod.log_find(self.LOG, "verify 1210", before=len(self.LOG)), 10, "case-insensitive, the newest match before `before`")
        self.assertEqual(mod.log_find(self.LOG, "GREEN", before=10), 7, "n: the next older match")
        self.assertIsNone(mod.log_find(self.LOG, "nothing like it", before=len(self.LOG)))
        lines, st, most = mod.render_log(self.LOG, width=100, height=20, offset=0)
        self.assertIn("↑↓ [ ] scroll", lines[0]); self.assertIn("/ search", lines[0]); self.assertIn("following", lines[0])   # PgUp/PgDn work too; the help says so (a Mac keyboard has no PgUp)
        self.assertEqual(st, {i: mod.log_style(l[2:]) for i, l in enumerate(lines) if l.startswith("  21:") and mod.log_style(l[2:])}, "the page's lines carry the board's styles")
        lines, _, most = mod.render_log(self.LOG, width=100, height=20, offset=5)
        self.assertIn("5 back", lines[0]); self.assertIn("b newest", lines[0])
        self.assertIn("no match for 'zzz'", mod.render_log(self.LOG, width=100, height=20, found="zzz", matched=False)[0][0])
        nav = mod.log_nav
        self.assertEqual(nav("page_up", self.LOG, 18, 0, "", None), (18, None)); self.assertEqual(nav("page_up", self.LOG, 18, 18, "", None), (23, None), "clamped at the oldest page")
        self.assertEqual(nav("top", self.LOG, 18, 0, "", None), (23, None)); self.assertEqual(nav("bottom", self.LOG, 18, 23, "", None), (0, None))
        self.assertEqual(nav("search", self.LOG, 18, 0, "GREEN", None), (3, 37), "the newest hit as the page's last line")
        self.assertEqual(nav("next", self.LOG, 18, 3, "GREEN", 37), (6, 34), "n: the next older")
        self.assertEqual(nav("next", self.LOG, 18, 23, "GREEN", 1), (3, 37), "none older: the newest again")
        self.assertEqual(nav("search", self.LOG, 18, 5, "zzz", None), (5, None), "no hit at all: found_at None, the offset kept")
        self.assertEqual(nav("next", self.LOG, 18, 5, "zzz", None), (5, None))
        d = project(**{".reef/run/live.log": "\n".join(self.LOG) + "\n"})
        class FC:
            A_REVERSE, A_BOLD, A_NORMAL = 1, 2, 0
            error = Exception
            def curs_set(self, *_): pass
            def flushinp(self): pass
            def update_lines_cols(self): pass
            def has_colors(self): return False
        class FW:
            def __init__(self, keys): self.keys = list(keys); self.rows = []; self.frames = []
            def getmaxyx(self): return (20, 100)
            def timeout(self, *_): pass
            def erase(self): self.frames.append([])
            def refresh(self): pass
            def move(self, *_): pass
            def clrtoeol(self): pass
            def addstr(self, y, x, text, *a):
                self.rows.append(text)
                if self.frames: self.frames[-1].append((text, a[0] if a else 0))
            def getch(self):
                k = self.keys.pop(0) if self.keys else ord("q")
                if k == -1:
                    settle()
                return k
        mod.doctor_lines = lambda root, fetch=False: []
        mod.work_model = lambda root, runner=None, states=True: {"rows": [], "facts": ["x"] * 5, "progress": {"rows": (0, 0), "tasks": (0, 0)}, "cost_today": 0, "autopilot": {}, "order": "queue", "cap": 2, "at": time.time()}
        keys = [-1, ord("w"), mod.KEY_PPAGE, mod.KEY_HOME, mod.KEY_END, ord("/")] + [ord(c) for c in "green"] + [10, ord("n"), ord("/")] + [ord(c) for c in "zzz"] + [10, ord("q"), ord("q")]
        win = FW(keys)
        self.assertEqual(mod.screen_loop(win, d, FC()), 0)
        logs = [f for f in win.frames if f and f[0][0].startswith("LOG")]
        self.assertGreaterEqual(len(logs), 5, "the log page was drawn after each key")
        after_pgup, after_home, after_end = logs[1], logs[2], logs[3]
        self.assertIn("18 back", after_pgup[0][0], "PgUp scrolls a page (the body's height)")
        self.assertIn("21:00", after_home[1][0], "Home: the oldest line first")
        self.assertIn("following", after_end[0][0], "End: the newest lines, following")
        found = [f for f in logs if "found 'green'" in f[0][0]]
        self.assertGreaterEqual(len(found), 2, "the header names what was found\n" + "\n".join(x[0] for x in logs[-1]))
        body = lambda f: [(t, a) for t, a in f if t.startswith("  21:")]   # the page's lines (the find prompt is drawn into the frame too)
        self.assertTrue(body(found[0])[-1][0].endswith("Verify 1237: GREEN"), "the newest hit is the page's last line\n" + "\n".join(t for t, _ in found[0]))
        self.assertEqual(body(found[0])[-1][1], 1, "the hit is highlighted (A_REVERSE)")
        self.assertTrue(body(found[1])[-1][0].endswith("Verify 1234: GREEN"), "n: the next older hit is the page's last line\n" + "\n".join(t for t, _ in found[1]))
        self.assertTrue(any("no match for 'zzz'" in f[0][0] for f in logs), "a query with no hit says so in the header")


class TheScreenAnswersAtOnce(unittest.TestCase):
    """2026-10-31 12:30, the owner on an issues queue: "the CLI is heavy and hangs today — I press something and nothing happens". A key
    pressed before the board landed waited up to five seconds and was re-queued (every key felt dead while the row machine asked GitHub
    about eight rows), and the board stayed "reading the rows … 3/8" until the last row landed. Now a key acts at once on what is
    there; the rows show the moment the queue is read, each with a `…` mark that becomes its state as the row machine answers; the
    inbox is read every INBOX_SECONDS and the board every BOARD_SECONDS, minutes apart (each row's state is a subprocess that may
    talk to the forge)."""

    class FC:
        A_REVERSE, A_BOLD, A_NORMAL = 1, 2, 0
        error = Exception
        def curs_set(self, *_): pass
        def flushinp(self): pass
        def update_lines_cols(self): pass
        def has_colors(self): return False

    class FW:
        def __init__(self, keys, tick=0.25): self.keys = list(keys); self.rows = []; self.frames = []; self.tick = tick
        def getmaxyx(self): return (40, 120)
        def timeout(self, *_): pass
        def erase(self): self.frames.append([])
        def refresh(self): pass
        def addstr(self, y, x, text, *a):
            self.rows.append(text)
            if self.frames: self.frames[-1].append(text)
        def getch(self):
            k = self.keys.pop(0) if self.keys else ord("q")
            if callable(k):   # a step of the test between two ticks
                k(); k = -1
            if k == -1:
                time.sleep(self.tick)
            return k

    def test_a_key_never_waits_for_a_reading(self):
        mod = load_script("reef", "reef_entry_under_test")
        d = project()
        mod.work_model = lambda root, runner=None, states=True: (time.sleep(2), {"rows": [], "facts": ["x"] * 5, "progress": {"rows": (0, 0), "tasks": (0, 0)}, "cost_today": 0, "autopilot": {}, "order": "queue", "cap": 2, "at": time.time()})[1]
        mod.doctor_lines = lambda root, fetch=False: (time.sleep(2), [])[1]
        mod.screen_model = lambda root, doctor=None, runner=None: (time.sleep(2), {"facts": ["m"] * 5, "items": [], "steps": [], "log": [], "warns": [], "doctor": False})[1]
        win = self.FW([ord("i"), 9, ord("w"), ord("q"), ord("q")])   # i: the inbox, Tab: the next view, w: the log, q back, q out — none waits for a reading
        t0 = time.time(); self.assertEqual(mod.screen_loop(win, d, self.FC()), 0); dt = time.time() - t0
        self.assertLess(dt, 1.5, f"five keys took {dt:.2f} s: a key waited for a reading")
        self.assertTrue(any(r.startswith("INBOX") for r in win.rows), "the inbox was drawn before its reading landed")
        self.assertTrue(any(r.startswith("LOG") for r in win.rows), "the log too")

    def test_the_rows_show_at_once_and_their_states_fill_in(self):
        mod = load_script("reef", "reef_entry_under_test")
        d = project(**{"docs/queue.md": "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n"
                                        + "".join(f"| {i} | row {i} (src/m{i}) | | planned | 1 | |\n" for i in range(1, 7))})
        mod.row_state = lambda root, row: (time.sleep(0.6), {"row": str(row), "state": "build", "next": "tick", "detail": f"1 open task(s) (PR #{row})"})[1]
        mod.doctor_lines = lambda root, fetch=False: []
        win = self.FW([-1] * 14 + [ord("q")], tick=0.25)
        self.assertEqual(mod.screen_loop(win, d, self.FC()), 0)
        boards = [f for f in win.frames if any(l.strip().startswith(("… 1", "▶ 1", "○ 1")) for l in f)]
        self.assertTrue(boards, "the rows were listed\n" + "\n".join(win.frames[-1]))
        first = boards[0]
        self.assertTrue(any(l.strip().startswith("… 6") for l in first), "at first every row carries the reading mark, the id and item visible\n" + "\n".join(first))
        self.assertTrue(any("reading the rows" in l for l in first), "the header counts the rows as they land")
        mixed = [f for f in boards if any(l.strip().startswith("… ") for l in f) and any(l.strip().startswith("▶ ") for l in f)]
        self.assertTrue(mixed, "a frame with some states landed and some still reading: they fill in one by one, not all at the end")
        last = boards[-1]
        self.assertFalse(any(l.strip().startswith("… ") for l in last), "in the end every row has its state\n" + "\n".join(last))
        self.assertTrue(any(l.strip().startswith("▶ 6") and "PR #6" in l for l in last))
        # the model, asked for the queue alone, is the provisional board: every open row reading, done rows done
        wm = mod.work_model(d, states=False)
        self.assertTrue(wm.get("partial")); self.assertEqual({r["mark"] for r in wm["rows"]}, {"…"})
        self.assertEqual(mod.row_what(wm["rows"][0]), "reading …")
        for key in ("raw", "done_ids", "asked", "task_counts"):
            self.assertNotIn(key, wm, "the board carries no intermediates: the reader threads publish finished rows")
        self.assertLess(mod.MARK_ORDER["…"], mod.MARK_ORDER["✓"], "in start order an unknown row sorts before a done one")

    def test_the_readings_are_minutes_apart_and_g_reads_a_failed_one_again(self):
        mod = load_script("reef", "reef_entry_under_test")
        d = project()
        calls = {"model": 0, "board": 0}
        def board(root, runner=None, states=True):
            calls["board"] += 1
            if calls["board"] == 1:
                raise RuntimeError("the forge did not answer")
            return {"rows": [], "facts": ["x"] * 5, "progress": {"rows": (0, 0), "tasks": (0, 0)}, "cost_today": 0, "autopilot": {}, "order": "queue", "cap": 2, "at": time.time(), "partial": not states}
        mod.work_model = board
        mod.screen_model = lambda root, doctor=None, runner=None: (calls.__setitem__("model", calls["model"] + 1), {"facts": ["m"] * 5, "items": [], "steps": [], "log": [], "warns": [], "doctor": False})[1]
        mod.doctor_lines = lambda root, fetch=False: []
        seen = {}
        def note():
            seen["model"], seen["board"] = calls["model"], calls["board"]
        def age():
            mod.INBOX_SECONDS, mod.BOARD_SECONDS = 0.0, 0.0   # minutes pass
        win = self.FW([-1, -1, -1, -1, note, ord("g"), -1, -1, age, -1, -1, ord("q")])
        self.assertEqual(mod.screen_loop(win, d, self.FC()), 0)
        self.assertLessEqual(seen["model"], 2, f"four ticks within INBOX_SECONDS: one inbox reading (and one more when the doctor landed), not one per tick ({calls})")
        self.assertEqual(seen["board"], 2, f"the queue and the board, once each, within BOARD_SECONDS ({calls})")
        self.assertTrue(any("reading failed" in r and "RuntimeError" in r for r in win.rows), "the board that raised is on the screen")
        self.assertGreaterEqual(calls["board"], 3, f"g read the failed board again ({calls})")
        self.assertGreaterEqual(calls["model"], 3, f"once INBOX_SECONDS passed the inbox was read again ({calls})")


class TheScreenRestartsAfterAnUpdate(unittest.TestCase):
    """2026-10-31 18:50, the owner: `u` inside the screen applied a new Reef, then the screen crashed — `ImportError: cannot import name
    'die' from 'reef_common'`. The process kept the OLD code in memory while the files on disk were new; the next lazy load of a
    sibling (reef-run.py, for the autopilot panel) imported the new file against the old module. After a successful update the screen
    restarts itself — the same command, a fresh process — so what runs is what is on disk. A failed update restarts nothing."""

    class FC:
        A_REVERSE, A_BOLD, A_NORMAL = 1, 2, 0
        error = Exception
        def curs_set(self, *_): pass
        def flushinp(self): pass
        def update_lines_cols(self): pass
        def has_colors(self): return False
        def endwin(self): self.ended = True

    class FW:
        def __init__(self, keys): self.keys = list(keys); self.rows = []
        def getmaxyx(self): return (40, 120)
        def timeout(self, *_): pass
        def erase(self): pass
        def refresh(self): pass
        def addstr(self, y, x, text, *a): self.rows.append(text)
        def getch(self):
            k = self.keys.pop(0) if self.keys else ord("q")
            if k == -1:
                settle()
            return k

    def test_u_that_succeeds_restarts_the_screen_and_a_failure_does_not(self):
        mod = load_script("reef", "reef_entry_under_test")
        d = project()
        mod.doctor_lines = lambda root, fetch=False: []
        mod.work_model = lambda root, runner=None, states=True: {"rows": [], "facts": ["x"] * 5, "progress": {"rows": (0, 0), "tasks": (0, 0)}, "cost_today": 0, "autopilot": {}, "order": "queue", "cap": 2, "at": time.time()}
        restarted = []
        mod.restart_screen = lambda curses: restarted.append(curses)
        mod.run_captured = lambda root, argv, timeout=900, sink=None: (0, ["reef update: done"]) if argv[2:3] == ["update"] else (0, ["ok"])
        fc = self.FC()
        self.assertEqual(mod.screen_loop(self.FW([-1, ord("u"), -1, ord("x")]), d, fc), 0)
        self.assertEqual(len(restarted), 1, "a successful update restarts the screen — the files on disk are new, the process is old")
        restarted.clear()
        mod.run_captured = lambda root, argv, timeout=900, sink=None: (1, ["reef update: stopped at that step"])
        self.assertEqual(mod.screen_loop(self.FW([-1, ord("u"), -1, ord("x"), ord("q")]), d, fc), 0)
        self.assertEqual(restarted, [], "a failed update: the output stays on the screen, nothing restarts")
        src = open(ENTRY, encoding="utf-8").read()
        self.assertIn("def restart_screen", src)
        self.assertIn("os.execv(", src.split("def restart_screen", 1)[1].split("\ndef ", 1)[0], "the restart is the same command in a fresh process")


class TheOwnersWalkThroughTheScreen(unittest.TestCase):
    """2026-10-31 19:00, the owner, after a day on the screen: "I like the homepage — the log, the tasks, the rows. In the inbox I still see
    plan approvals I already approved. When I press Tab it stops at a certain page and I cannot get back; it says Home/End and I have
    no Home key; q takes me out." Four rules: an approval whose record exists at the question's digest has left the inbox (the
    runner's last wait text is not the truth, the record is); Tab, i, p and w work from every page, LOG and help included; the LOG
    page has keys a Mac keyboard has — t the oldest, b the newest (follow), [ and ] a page — beside Home/End and PgUp/PgDn; q on a
    sub-page (LOG, help, the autopilot panel) goes back and the page's first line says so; on the main pages q quits."""

    def test_an_approval_already_recorded_leaves_the_inbox(self):
        mod = load_script("reef", "reef_entry_under_test")
        d = project(**{".reef/loop.json": '{"active": true, "wait": "owner: Approve plan invoices-pdf at 3f9a1c77be02d4e1? and Approve plan rate-limits at 0123456789abcdef?", "stop": null, "parked": null, "hashes": []}',
                       ".reef/approvals/invoices-pdf.json": '{"digest16": "3f9a1c77be02d4e1", "approved_at": "2026-10-31T18:00:00Z"}'})
        items = mod.inbox(d)
        self.assertEqual([i["text"] for i in items], ["Approve plan rate-limits at 0123456789abcdef?"], "the approved plan is gone; the other stays\n" + str(items))
        self.assertTrue(mod.already_approved(d, "Approve plan invoices-pdf at 3f9a1c77be02d4e1?"))
        self.assertFalse(mod.already_approved(d, "Approve plan invoices-pdf at ffffffffffffffff?"), "a record at another digest is not this approval (the plan changed)")
        open(os.path.join(d, ".reef", "approvals", "night.json"), "w").write('{"digest16": "aaaaaaaaaaaaaaaa"}')
        self.assertTrue(mod.already_approved(d, "Approve night 2026-10-31 at aaaaaaaaaaaaaaaa?"))
        self.assertFalse(mod.already_approved(d, "Approve proxy by day at bbbbbbbbbbbbbbbb?"))
        open(os.path.join(d, ".reef", "approvals", "day.json"), "w").write('{"digest16": "bbbbbbbbbbbbbbbb"}')   # reef-approval.py's name for the day contract
        self.assertTrue(mod.already_approved(d, "Approve proxy by day at bbbbbbbbbbbbbbbb?"), "the day contract's record is day.json (the review: proxy-day.json was nobody's file)")
        open(os.path.join(d, ".reef", "approvals", "night.json"), "w").write('["not a record"]')
        self.assertFalse(mod.already_approved(d, "Approve night 2026-10-31 at aaaaaaaaaaaaaaaa?"), "a record that is not a dict is no record")

    def test_every_page_answers_tab_i_p_w_and_says_what_q_does(self):
        mod = load_script("reef", "reef_entry_under_test")
        on = mod.on_key
        for view in ("log", "help", "autopilot"):
            self.assertEqual(on(9, 0, 0, view)[0], "view", f"Tab from {view} moves on")
            self.assertEqual(on(ord("i"), 0, 0, view), ("view", "inbox"), f"i from {view}")
            self.assertEqual(on(ord("p"), 0, 0, view), ("view", "plan"), f"p from {view}")
            self.assertIn(on(ord("q"), 0, 0, view)[0], ("back", "view"), f"q from {view} goes back, never out")
        self.assertEqual(on(9, 0, 0, "log"), ("view", "work"), "Tab from LOG: the cycle starts again at WORK")
        self.assertEqual(on(ord("w"), 0, 0, "help"), ("log",), "w from help: the log"); self.assertEqual(on(ord("w"), 0, 0, "autopilot"), ("log",), "w from the autopilot panel too (one rule)")
        self.assertEqual(on(ord("t"), 0, 0, "log"), ("top",)); self.assertEqual(on(ord("b"), 0, 0, "log"), ("bottom",))
        self.assertEqual(on(ord("["), 0, 0, "log"), ("page_up",)); self.assertEqual(on(ord("]"), 0, 0, "log"), ("page_down",))
        self.assertEqual(on(ord("q"), 0, 2, "work"), ("quit",)); self.assertEqual(on(ord("q"), 0, 2, "inbox"), ("quit",))
        lines, _, _ = mod.render_log(["a", "b"], width=120, height=10)
        self.assertIn("t oldest · b newest", lines[0], "the LOG header names keys a Mac keyboard has (Home/End stay in the help)"); self.assertIn("q back", lines[0])
        longest = mod.render_log(["a"] * 400, width=127, height=10, offset=357, found="a query of some length", matched=True)[0][0]   # scrolled back, a search on: the screen's width is w-1
        self.assertIn("q back · Tab views", longest, "the header's last words survive 127 columns in its longest state:\n" + longest)
        help_lines, _ = mod.render_help("work", width=120)
        self.assertIn("q back", help_lines[0]); self.assertTrue(any("t oldest" in l and "b newest" in l for l in help_lines), "\n".join(help_lines))
        self.assertTrue(any("Tab" in l and "every page" in l for l in help_lines), "the help says Tab works from every page")
        self.assertIn("w log", mod.KEYS, "the banner's keys line stays short (a 10x4 terminal wraps it to four rows); i and p are in the help")


class TheScreenStaysSmooth(unittest.TestCase):
    """The CLI review (2026-10-31 19:30), ranked first: `u` froze the screen for minutes (the update ran on the UI thread, 900 s cap, the
    parent killed mid-step past it) and the restart fired before the owner saw the update's last word; Enter on a WORK row ran
    `reef-row.py state` on the UI thread to show what the box already showed, and the next key was eaten; after every command the
    doctor was dropped (`doctor = None`) so its items vanished for seconds and the selection could jump. The rules: a command runs in
    a thread named reef-command and its lines stream into the panel as they come; after a successful update the panel stays with the
    last line and `any key restarts`, no reading is spawned meanwhile, and the key restarts; Enter on a row that is yours (an inbox
    item names it) opens INBOX on that item, on any other row shows the row's facts from the board in the panel — no subprocess;
    the box says `yours: <the command>` or `the runner's next: …`; a command re-reads the doctor but keeps its lines until then."""

    class FC:
        A_REVERSE, A_BOLD, A_NORMAL = 1, 2, 0
        error = Exception
        def curs_set(self, *_): pass
        def flushinp(self): pass
        def update_lines_cols(self): pass
        def has_colors(self): return False
        def endwin(self): pass

    class FW:
        """Keys: -1 a tick that waits for every reading and the command; -2 a tick that waits for nothing (a frame mid-run);
        -3 a tick that waits for the command alone."""
        def __init__(self, keys): self.keys = list(keys); self.rows = []; self.frames = []
        def getmaxyx(self): return (40, 120)
        def timeout(self, *_): pass
        def erase(self): self.frames.append([])
        def refresh(self): pass
        def move(self, *_): pass
        def clrtoeol(self): pass
        def addstr(self, y, x, text, *a): self.rows.append(text); self.frames[-1].append(text) if self.frames else None
        def getch(self):
            import threading
            k = self.keys.pop(0) if self.keys else ord("q")
            if k == -1:
                settle()
            if k == -3:
                t0 = time.time()
                while time.time() - t0 < 10 and any(t.name == "reef-command" and t.is_alive() for t in threading.enumerate()):
                    time.sleep(0.02)
            return -1 if k in (-2, -3) else k

    def board(self, rows):
        return {"rows": rows, "facts": ["x"] * 5, "progress": {"rows": (0, len(rows)), "tasks": (0, 0)}, "cost_today": 0, "autopilot": {}, "order": "queue", "cap": 2, "at": time.time(), "batch": 3}

    def row(self, id, mark, detail="", nxt="", state="plan"):
        return {"id": id, "mark": mark, "tasks": (0, 0), "lane": "src", "state": state, "detail": detail, "next": nxt, "depends": [], "waits": [], "forge": "", "item": f"row {id} item", "slug": ""}

    def test_a_command_streams_into_the_panel_from_a_thread(self):
        mod = load_script("reef", "reef_entry_under_test")
        d = project()
        mod.doctor_lines = lambda root, fetch=False: []
        mod.work_model = lambda root, runner=None, states=True: self.board([])
        win = self.FW([-1, ord("d"), -2, -2, -2, -2, -2, -3, -2, ord("x"), ord("q")])
        seen = []
        def slow(root, argv, timeout=900, sink=None):
            sink.append("first line")
            t0 = time.time()
            while time.time() - t0 < 3 and not any("first line" in r for r in win.rows):
                time.sleep(0.02)   # the screen draws while the command runs: the UI thread is free
            seen.append(any("first line" in r for r in win.rows))
            sink.append("done")
            return 0, list(sink)
        mod.run_captured = slow
        self.assertEqual(mod.screen_loop(win, d, self.FC()), 0)
        self.assertEqual(seen, [True], "the first line was on the screen while the command still ran")
        self.assertTrue(any("running" in r for r in win.rows), "the panel said running meanwhile")
        self.assertTrue(any(r.startswith("OUTPUT") and "exit 0" in r for r in win.rows), "then the exit")

    def test_a_successful_update_keeps_its_last_word_and_restarts_on_the_next_key(self):
        mod = load_script("reef", "reef_entry_under_test")
        d = project()
        mod.doctor_lines = lambda root, fetch=False: []
        boards = []
        mod.work_model = lambda root, runner=None, states=True: (boards.append(len(win.frames)), self.board([]))[1]   # each reading remembers how many frames were drawn
        restarted = []
        mod.restart_screen = lambda curses: restarted.append(1)
        mod.run_captured = lambda root, argv, timeout=900, sink=None: (0, ["reef update: pulled", "reef update: done — /reload-plugins"]) if argv[2:3] == ["update"] else (0, ["ok"])
        win = None
        mod.BOARD_SECONDS = 0   # the board is due again at once: after the update it must NOT be read (work_model loads siblings)
        try:
            win = self.FW([-1, ord("u"), -3, -2, -2, -2, ord("x")])
            self.assertEqual(mod.screen_loop(win, d, self.FC()), 0)
        finally:
            mod.BOARD_SECONDS = 120
        self.assertEqual(len(restarted), 1, "the key after the update restarts the screen")
        frames_after = [f for f in win.frames if any("exit 0" in r for r in f)]
        self.assertTrue(frames_after, "the update's exit was drawn before the restart")
        self.assertTrue(all(any("reef update: done" in r for r in f) for f in frames_after), "its last word stayed on the screen")
        self.assertTrue(all(any("any key restarts" in r for r in f) for f in frames_after), "the panel says the key restarts")
        before = len(boards)
        self.assertLessEqual(before, 4, "the board was read before the update, a few times (BOARD_SECONDS is 0 here): " + str(before))
        self.assertTrue(all(any("exit 0" in r for r in f) for f in win.frames[-3:]), "the last frames are the frozen panel")
        self.assertEqual(boards_after_update(win, boards, mod), 0, "no board reading was spawned after the update (the old process must not load the new files)")

    def test_enter_on_a_row_that_is_yours_opens_its_inbox_item_and_on_another_row_shows_the_row(self):   # noqa: E301
        mod = load_script("reef", "reef_entry_under_test")
        q = "Approve plan rate-limits at 0123456789abcdef?"
        d = project(**{".reef/loop.json": '{"active": true, "wait": "owner: ' + q + '", "stop": null, "parked": null, "hashes": []}'})
        mod.doctor_lines = lambda root, fetch=False: []
        mod.work_model = lambda root, runner=None, states=True: self.board([self.row("9", "⧖", detail=q, state="approval", nxt="python3 scripts/reef-loop.py tick"),
                                                                             self.row("10", "▶", detail="task 2 of 4", nxt="/reef-review invoices", state="build")])
        ran = []
        mod.run_captured = lambda root, argv, timeout=900, sink=None: (ran.append(argv), (0, ["ok"]))[1]
        win = self.FW([-1, 10, -2, 9, 9, 9, ord("2"), 10, -2, ord("x"), ord("q")])   # Enter on row 9 (yours): INBOX, its item selected; Tab Tab Tab: back on WORK; 2 Enter: row 10 in the panel, from the board
        self.assertEqual(mod.screen_loop(win, d, self.FC()), 0)
        self.assertEqual(ran, [], "Enter on a row runs nothing: the jump, or the row's facts from the board")
        frame = next((f for f in win.frames if any(r == "INBOX  1 item(s) wait on you" for r in f)), None)   # the INBOX page (WORK's line says "· i opens it")
        self.assertIsNotNone(frame, "Enter on the row that is yours opened the inbox\n" + "\n".join(win.frames[-1]))
        self.assertTrue(any("▶ 1  approve" in r for r in frame), "its item is the selected one\n" + "\n".join(frame))
        self.assertTrue(any("OUTPUT  $ row 10" in r for r in win.rows) and any("build · task 2 of 4" in r for r in win.rows), "row 10, from the board, in the panel")

    def test_the_box_and_the_panel_say_whose_the_next_step_is(self):
        mod = load_script("reef", "reef_entry_under_test")
        q = "Approve plan rate-limits at 0123456789abcdef?"
        it = mod.approve_item(q)
        rows = [self.row("9", "⧖", detail=q, state="approval", nxt="python3 scripts/reef-loop.py tick"), self.row("10", "▶", detail="task 2 of 4", nxt="/reef-review invoices", state="build")]
        lines, _, _ = mod.render_work(self.board(rows), [it], width=120, height=40, selected=0)
        self.assertTrue(any("yours: python3 scripts/reef-approval.py --owner" in l for l in lines), "the ⧖ row's box names the owner's own command, not the orchestrator's step\n" + "\n".join(lines))
        self.assertFalse(any("reef-loop.py tick" in l for l in lines), "the orchestrator's step is not the owner's")
        lines, _, _ = mod.render_work(self.board(rows), [it], width=120, height=40, selected=1)
        self.assertTrue(any("the runner's next: /reef-review invoices" in l for l in lines), "a building row: the runner's step, named as such\n" + "\n".join(lines))
        self.assertEqual(mod.row_panel(rows[1], [it])["lines"][:2], ["row 10 item", "build · task 2 of 4"])
        self.assertEqual(mod.mine(rows[0], [it]), 0); self.assertIsNone(mod.mine(rows[1], [it]))

    def test_a_command_keeps_the_doctor_until_the_new_reading_lands(self):
        mod = load_script("reef", "reef_entry_under_test")
        d = project()
        calls = []
        def doctor(root, fetch=False):
            calls.append(fetch)
            if len(calls) > 1:
                time.sleep(0.6)   # the second reading is slow (it fetches): the first one's lines must stay meanwhile
            return ["WARN plugin: a new Reef, 2 commit(s) since your copy"]
        mod.doctor_lines = doctor
        mod.work_model = lambda root, runner=None, states=True: self.board([])
        mod.run_captured = lambda root, argv, timeout=900, sink=None: (0, ["ok"])
        win = self.FW([-1, -1, -1, ord("i"), ord("c"), -3, ord("x"), -1, -2, ord("q")])   # ticks: the doctor, then the model read with it; i; c runs; the command lands; x closes; the slow doctor lands; a frame
        self.assertEqual(mod.screen_loop(win, d, self.FC()), 0)
        self.assertGreaterEqual(len(calls), 2, "a command re-reads the doctor")
        frames = [f for f in win.frames if any(r.startswith("RUNNER  the last steps") for r in f)]   # the INBOX page, by its RUNNER header (the DOCTOR section is what may vanish)
        self.assertGreaterEqual(len(frames), 3)
        self.assertTrue(all(any("WARN plugin" in r for r in f) for f in frames), "the doctor's line never left the inbox page\n" + "\n".join(next((f for f in frames if not any("WARN plugin" in r for r in f)), [])))


class ThePagesAndTheKeys(unittest.TestCase):
    """The CLI review (2026-10-31 19:30), the second group: PLAN was half a view (no selection drawn, yet ↑↓/digits/Enter moved an
    invisible one; a command there drew another page's frame and came back with no panel); `d` kept the doctor's LAST twelve lines
    while the WARNs are its first; help's own header said `q back` but q went to WORK from anywhere; Esc meant back on sub-pages
    and quit on the main ones, and arrived a second late; the tabs line nagged `board N s old` for 96% of every cycle while the
    help promised a refresh every 3 s; `s` ended a night with one unconfirmed keystroke next to a/d/w; the keys line broke
    `c / cost` across two rows at 120 columns."""

    class FC:
        A_REVERSE, A_BOLD, A_NORMAL = 1, 2, 0
        error = Exception
        def curs_set(self, *_): pass
        def flushinp(self): pass
        def update_lines_cols(self): pass
        def has_colors(self): return False
        def endwin(self): pass

    class FW:
        def __init__(self, keys): self.keys = list(keys); self.rows = []; self.frames = []
        def getmaxyx(self): return (40, 120)
        def timeout(self, *_): pass
        def erase(self): self.frames.append([])
        def refresh(self): pass
        def move(self, *_): pass
        def clrtoeol(self): pass
        def addstr(self, y, x, text, *a): self.rows.append(text); self.frames[-1].append(text) if self.frames else None
        def getch(self):
            k = self.keys.pop(0) if self.keys else ord("q")
            if k == -1:
                settle()
            return k

    def board(self, rows):
        return {"rows": rows, "facts": ["x"] * 5, "progress": {"rows": (0, len(rows)), "tasks": (0, 0)}, "cost_today": 0, "autopilot": {}, "order": "queue", "cap": 2, "at": time.time(), "batch": 3}

    def row(self, id, mark, detail="", nxt="", state="plan"):
        return {"id": id, "mark": mark, "tasks": (1, 3), "lane": "src", "state": state, "detail": detail, "next": nxt, "depends": [], "waits": [], "forge": "", "item": f"row {id} item", "slug": ""}

    def test_plan_shows_its_selection_and_the_panel(self):
        mod = load_script("reef", "reef_entry_under_test")
        wm = self.board([self.row("9", "○"), self.row("10", "▶", state="build")])
        lines, styles, sel_line = mod.render_plan(wm, [], width=120, height=40, selected=1)
        self.assertIsNotNone(sel_line); self.assertIn("row 10", lines[sel_line]); self.assertEqual(styles.get(sel_line), "sel", "the selected row is drawn as such")
        lines, styles, _ = mod.render_plan(wm, [], width=120, height=40, selected=0, panel={"shown": "reef cost", "rc": 0, "lines": ["$1.20 per row"]})
        self.assertTrue(any(l.startswith("OUTPUT  $ reef cost · exit 0") for l in lines), "the panel is on PLAN too\n" + "\n".join(lines))
        self.assertTrue(any("$1.20 per row" in l for l in lines))
        # on the screen: a verb on PLAN draws PLAN with the panel, and the key after the exit closes it (never eaten by an invisible one)
        d = project()
        mod.doctor_lines = lambda root, fetch=False: []
        mod.work_model = lambda root, runner=None, states=True: self.board([self.row("9", "○")])
        mod.run_captured = lambda root, argv, timeout=900, sink=None: (0, ["$1.20 per row"])
        win = self.FW([-1, ord("p"), ord("c"), -1, ord("x"), ord("q")])
        self.assertEqual(mod.screen_loop(win, d, self.FC()), 0)
        plan_frames = [f for f in win.frames if any(l.startswith("PLAN  batch") for l in f)]
        self.assertTrue(any(any(l.startswith("OUTPUT") for l in f) for f in plan_frames), "the panel was drawn on the PLAN page")
        self.assertFalse(any("[WORK]" in l for f in plan_frames for l in f))

    def test_plan_windows_its_rows_around_the_selection_and_carries_the_tabs(self):
        mod = load_script("reef", "reef_entry_under_test")
        wm = self.board([self.row(str(i), "○") for i in range(30)])
        lines, styles, sel_line = mod.render_plan(wm, [], width=120, height=20, selected=25)
        self.assertLessEqual(len(lines), 20)
        self.assertIsNotNone(sel_line, "the selected row is on the page, whatever the height (the review: it fell off the cut)")
        self.assertIn("row 25", lines[sel_line]); self.assertEqual(styles[sel_line], "sel")
        self.assertTrue(any("… " in l and "more" in l for l in lines), "the cut is marked\n" + "\n".join(lines))
        self.assertTrue(lines[0].startswith(" WORK ") and "[PLAN]" in lines[0], "the tabs row says where Tab stands\n" + lines[0])
        # a panel that keeps its head (the doctor's) sheds from the tail on a short page, on WORK too
        panel = {"shown": "reef doctor", "rc": 0, "lines": ["FAIL a", "WARN b"] + [f"OK {i}" for i in range(10)], "keep": "head"}
        lines, _, _ = mod.render_work(self.board([self.row("9", "○")]), [], width=120, height=22, selected=0, panel=panel)
        self.assertTrue(any("FAIL a" in l for l in lines), "the FAIL survives a short page\n" + "\n".join(lines))
        self.assertTrue(any("more line(s) below" in l for l in lines))
        self.assertEqual(mod.doctor_first(["OK a"] + ["WARN x"] * 13)[-1], "… 3 more line(s), 2 of them WARN or FAIL — reef doctor in a terminal shows them")

    def test_the_doctor_panel_puts_its_warnings_first(self):
        mod = load_script("reef", "reef_entry_under_test")
        d = project()
        mod.doctor_lines = lambda root, fetch=False: []
        mod.work_model = lambda root, runner=None, states=True: self.board([])
        out = [f"OK   check {i}" for i in range(14)] + ["WARN plugin: a new Reef, 2 commit(s) since your copy", "FAIL queue: the branch carries queue edits"]
        mod.run_captured = lambda root, argv, timeout=900, sink=None: (0, list(out)) if argv[2:3] == ["doctor"] else (0, ["ok"])
        win = self.FW([-1, ord("d"), -1, ord("x"), ord("q")])
        self.assertEqual(mod.screen_loop(win, d, self.FC()), 0)
        frame = next(f for f in win.frames if any(l.startswith("OUTPUT  $ reef doctor · exit 0") for l in f))
        i = next(j for j, l in enumerate(frame) if l.startswith("OUTPUT"))
        self.assertIn("FAIL queue", frame[i + 1]); self.assertIn("WARN plugin", frame[i + 2]); self.assertIn("OK   check 0", frame[i + 3])
        self.assertEqual(mod.doctor_first(["OK a", "WARN b", "FAIL c", "OK d"]), ["FAIL c", "WARN b", "OK a", "OK d"])

    def test_q_and_esc_go_back_to_the_page_help_was_opened_from_and_esc_never_quits(self):
        mod = load_script("reef", "reef_entry_under_test")
        on = mod.on_key
        self.assertEqual(on(ord("q"), 0, 0, "help"), ("back",)); self.assertEqual(on(27, 0, 0, "help"), ("back",)); self.assertEqual(on(ord("?"), 0, 0, "help"), ("back",))
        self.assertEqual(on(ord("q"), 0, 0, "autopilot"), ("back",)); self.assertEqual(on(27, 0, 0, "autopilot"), ("back",))
        self.assertEqual(on(27, 0, 0, "log"), ("back",))
        for view in ("work", "inbox", "plan"):
            self.assertIsNone(on(27, 0, 2, view), f"Esc on {view} quits nothing (the CLI review: Esc twice out of LOG quit the screen)")
            self.assertEqual(on(ord("q"), 0, 2, view), ("quit",))
        d = project()
        mod.doctor_lines = lambda root, fetch=False: ["WARN plugin: x"]
        mod.work_model = lambda root, runner=None, states=True: self.board([])
        win = self.FW([-1, -1, -1, ord("i"), ord("?"), ord("q"), 27, 27, ord("q")])   # i; ? help; q: INBOX again; Esc Esc: still here; q quits
        self.assertEqual(mod.screen_loop(win, d, self.FC()), 0)
        help_at = next(i for i, f in enumerate(win.frames) if any(l.startswith("KEYS  (you are on INBOX)") for l in f))
        after = win.frames[help_at + 1:]
        self.assertGreaterEqual(len(after), 3, "Esc Esc drew two more frames: the screen stayed")
        self.assertTrue(all(any(l.startswith("DOCTOR") for l in f) for f in after), "every frame after the help is the INBOX page\n" + "\n".join(after[0]))
        src = open(ENTRY, encoding="utf-8").read()
        self.assertIn("set_escdelay(", src, "Esc arrives at once (curses waits a second for a sequence by default) — a reading of the source: the fake curses has no delay to measure")
        # the help opened on the autopilot panel returns there (the review: it went to WORK and the header lied)
        win = self.FW([-1, ord("a"), ord("?"), ord("q"), ord("q"), ord("q")])   # a: the panel; ?: help; q: the panel again; q: back to WORK; q quits
        mod.contract_view = lambda root: {"digest16": "", "decides": [], "never": "", "approved": False, "question": ""}
        self.assertEqual(mod.screen_loop(win, d, self.FC()), 0)
        at = [i for i, f in enumerate(win.frames) if any(l.startswith("AUTOPILOT  start") for l in f)]
        hp = next(i for i, f in enumerate(win.frames) if any(l.startswith("KEYS  (you are on AUTOPILOT)") for l in f))
        self.assertTrue(any(i > hp for i in at), "after q on the help, the autopilot panel again")
        lines, _ = mod.render_help("inbox", width=120)
        self.assertTrue(any("q / Esc" in l and "back" in l and "Esc never quits" in l for l in lines), "\n".join(lines))

    def test_the_tabs_line_names_the_boards_age_only_when_overdue_and_the_help_the_real_intervals(self):
        mod = load_script("reef", "reef_entry_under_test")
        self.assertNotIn("old", mod.tabs_line("work", 0, 120, age=30))
        self.assertNotIn("old", mod.tabs_line("work", 0, 120, age=mod.BOARD_SECONDS + 10), "a reading in progress is not overdue")
        self.assertIn("board 5 min old (g reads it now)", mod.tabs_line("work", 0, 120, age=300))
        lines, _ = mod.render_help("work", width=120)
        g = next(l for l in lines if l.startswith("  g "))
        self.assertIn(f"inbox every {mod.INBOX_SECONDS} s", g); self.assertIn(f"board every {mod.BOARD_SECONDS // 60} min", g); self.assertIn(f"doctor every {mod.UPDATE_SECONDS // 60} min", g); self.assertNotIn("3 s", g)
        self.assertEqual((mod.INBOX_SECONDS, mod.BOARD_SECONDS, mod.UPDATE_SECONDS), (10, 120, 900), "the intervals the owner was told")

    def test_s_asks_before_it_stops_the_runner(self):
        mod = load_script("reef", "reef_entry_under_test")
        d = project()
        mod.doctor_lines = lambda root, fetch=False: []
        mod.work_model = lambda root, runner=None, states=True: self.board([])
        ran = []
        mod.run_captured = lambda root, argv, timeout=900, sink=None: (ran.append(argv), (0, ["stopped"]))[1]
        win = self.FW([-1, ord("s"), ord("n"), 10, ord("s"), ord("y"), 10, -1, ord("x"), ord("q")])   # s, n Enter: nothing; s, y Enter: the stop
        self.assertEqual(mod.screen_loop(win, d, self.FC()), 0)
        self.assertEqual([a[2] for a in ran], ["stop"], "one stop, after the yes\n" + str(ran))
        self.assertTrue(any("stop the runner after its session? y/N" in r for r in win.rows), "the question on the last line")
        self.assertEqual(mod.on_key(ord("s"), 0, 0, "work"), ("verb", "stop"))

    def test_the_keys_line_wraps_between_keys_never_inside_one(self):
        mod = load_script("reef", "reef_entry_under_test")
        cells = mod.KEYS.split(" · ")
        for w in range(24, 160):
            rows = mod.wrap_cells(mod.KEYS, w)
            for r in rows:
                self.assertLessEqual(len(r), w)
                for c in r.split(" · "):
                    self.assertIn(c, cells, f"width {w}: a key was cut: {r!r}")
            self.assertEqual(" · ".join(rows).split(" · "), cells, f"width {w}: every key, in order")
        self.assertEqual(mod.wrap_cells("a · bb · ccc", 6), ["a · bb", "ccc"])
        self.assertEqual(mod.wrap_cells("keys: q quit · x", 5), ["keys:", "q", "quit", "x"], "a cell wider than the terminal falls back to words")
        lines, _, _ = mod.render_work(self.board([]), [], width=120, height=40)
        self.assertFalse(any(l.endswith(" · c") or l.startswith("cost") for l in lines), "no `c` / `cost` across two rows at 120 columns")
