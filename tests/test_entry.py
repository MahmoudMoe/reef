"""scripts/reef — the owner's one entry point (2026-10-28: "the person opens the terminal, writes reef, sees a logo and the
options with a short description each"). The owner's verbs, one line each; the internal scripts under --all; every verb runs
the sibling script it names."""
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest

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
        d = tempfile.mkdtemp(prefix="reef-entry.")
        subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
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
        mod = load_entry()
        line = mod.update_done_line("mahmoudmoe")
        self.assertIn("/plugin marketplace update mahmoudmoe", line)
        self.assertIn("/reload-plugins", line)
        self.assertNotIn("<", line)
        line = mod.update_done_line(None)
        self.assertIn("/reload-plugins", line)
        self.assertNotIn("marketplace update", line, "no marketplace lists the clone: the reload alone")
        self.assertNotIn("<", line)
        self.assertNotIn("<marketplace>", open(ENTRY, encoding="utf-8").read(), "no placeholder left in the entry point")


def project(**files):
    d = tempfile.mkdtemp(prefix="reef-screen.")
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    os.makedirs(os.path.join(d, ".reef", "run"))
    open(os.path.join(d, ".reef", "config.json"), "w").write('{"gates": {"full": "true"}}')
    open(os.path.join(d, ".reef", "version"), "w").write("0.7.3\n")
    for rel, text in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(text)
    return d


def load_entry():
    import importlib.machinery, importlib.util
    loader = importlib.machinery.SourceFileLoader("reef_entry_under_test", ENTRY)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


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
        mod = load_entry()
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
        mod = load_entry()
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
        mod = load_entry()
        src = open(ENTRY, encoding="utf-8").read()
        self.assertNotIn("run_shown", src, "no leaving the screen to run a command")
        self.assertNotIn("input(", src.split("def screen_loop", 1)[1].split("def cmd_approve", 1)[0], "no terminal prompt in the screen's loop")
        on = mod.on_key
        self.assertEqual(on(ord("3"), 0, 5, "inbox"), ("select", 2), "a digit selects")
        self.assertEqual(on(ord("3"), 2, 5, "inbox"), ("select", 2), "a digit only selects; Enter runs (two rules, as the keys line says)")
        self.assertEqual(on(ord("R"), 0, 5, "inbox"), ("verb", "run"), "one case: a caps lock is not silence")
        self.assertEqual(on(10, 1, 5, "inbox"), ("run", 1), "Enter runs the selected")
        self.assertEqual(on(ord("9"), 0, 2, "inbox"), None, "a digit past the list is nothing")
        self.assertEqual(on(ord("q"), 0, 2, "inbox"), ("quit",)); self.assertEqual(on(27, 0, 2, "inbox"), ("quit",))
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
        log, _ = mod.render_log(model["log"], width=100, height=20, offset=0)
        self.assertLessEqual(len(log), 20)
        self.assertTrue(log[0].startswith("LOG"), log[0]); self.assertIn("step 59", "\n".join(log), "the newest lines first on the screen")
        log2, _ = mod.render_log(model["log"], width=100, height=20, offset=10)
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
            def getch(self): return self.keys.pop(0) if self.keys else ord("q")
        ran = []
        real_run = mod.run_captured
        mod.run_captured = lambda root, argv, timeout=900: (ran.append(argv), (0, ["ok"]))[1]
        mod.doctor_lines = lambda root: []
        d2 = project(**{".reef/questions.md": "- row 7: Keep it? — recommended: yes\n- row 8: Rename it? — recommended: no\n"})
        win = FakeWin([ord("i"), ord("2"), 10, 10, ord("x"), 10, 10, ord("q")])   # i: the inbox (the screen opens on WORK since the fourth design); 2 selects; Enter runs it and opens the answer line; Enter keeps 'no'; x closes the panel; Enter, Enter again; q
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
        mod = load_entry()
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
        plan, pstyles = mod.render_plan(wm, [], width=110, height=30)
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
        self.assertEqual(on(27, 0, 3, "help"), ("view", "work")); self.assertEqual(on(ord("q"), 0, 3, "help"), ("view", "work"))
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
        self.assertEqual(mod.runner_line(d, 0, 0, ""), "no runner is running"); self.assertIn("gone", mod.runner_line(d, 0, 70418, "01:06", tree))
        self.assertIn("since 23:56 ", mod.runner_line(d, 70417, 70418, "2026-10-30T23:56:56Z", tree) + " ", "the runner's ISO start as a clock time")
        os.makedirs(os.path.join(d, ".reef", "approvals"), exist_ok=True)
        open(os.path.join(d, ".reef", "approvals", "move-specs.json"), "w").write('{"digest16": "73b12e4b024b95eb", "approved_at": "%sT21:42:42Z", "by": "mahmoud (proxy)"}' % time.strftime("%Y-%m-%d", time.gmtime()))
        open(os.path.join(d, ".reef", "approvals", "older.json"), "w").write('{"digest16": "x", "approved_at": "2026-10-01T00:00:00Z", "by": "mahmoud (proxy)"}')
        open(os.path.join(d, ".reef", "approvals", "mine.json"), "w").write('{"digest16": "y", "approved_at": "%sT09:00:00Z"}' % time.strftime("%Y-%m-%d", time.gmtime()))
        self.assertEqual(mod.autopilot_view(d)["decided_today"], 1, "his plan approval today counts; an older one and the owner's own do not")
        # the loop on the board (a fake curses, as the inbox test below): Enter opens the selected row through the row machine, never an inbox item;
        # Tab, Tab shows PLAN; q quits
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
            def getch(self): return self.keys.pop(0) if self.keys else ord("q")
        ran = []
        mod.run_captured = lambda root, argv, timeout=900: (ran.append(argv), (0, ["state: build"]))[1]
        mod.doctor_lines = lambda root: []
        mod.inbox = lambda root, doctor=None, runner=None: [{"kind": "approve", "text": "x", "argv": [sys.executable, "-c", "pass"], "cmd": "approve x", "row": "7", "recommended": "", "issue": ""}]
        win = FW([ord("2"), 10, ord("x"), 9, 9, 10, ord("x"), ord("q")])   # 2 selects row 7, Enter opens it; x closes; Tab Tab → PLAN; Enter there opens the row too; q
        self.assertEqual(mod.screen_loop(win, d, FC()), 0)
        self.assertEqual(len(ran), 2, str(ran)); self.assertTrue(all(os.path.basename(str(r[1])) == "reef-row.py" and r[2:4] == ["state", "7"] for r in ran), str(ran))
        self.assertTrue(any(r.startswith("PLAN") for r in win.rows), "Tab, Tab reached PLAN")

    def test_an_empty_project_has_only_the_doctors_fixes_in_its_inbox(self):
        d = project()
        r = reef("screen", "--once", "--repo", d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        items = [l for l in r.stdout.splitlines() if re.match(r"^\s*\d+\s+\w+", l)]
        self.assertTrue(all(re.match(r"^\s*\d+\s+fix\b", l) for l in items), "no approval, question or park: only the doctor's fixes, if any\n" + r.stdout)
        mod = load_entry()
        self.assertEqual(mod.inbox(d), [], "without the doctor's lines the inbox is empty")
        self.assertIn("nothing waits on you", mod.screen_text(d))

    def test_the_model_asks_the_row_machine_for_a_rows_command(self):
        mod = load_entry()
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
        mod = load_entry()
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
        mod = load_entry()
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
        mod = load_entry()
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
        mod = load_entry()
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
        mod.work_model = lambda root, runner=None: (_t.sleep(3), {"rows": [], "facts": ["x"] * 5, "progress": {"rows": (0, 0), "tasks": (0, 0)}, "cost_today": 0, "autopilot": {}, "order": "queue", "cap": 2, "at": _t.time()})[1]
        mod.doctor_lines = lambda root: (_t.sleep(3), [])[1]
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
        mod.work_model = lambda root, runner=None: (_ for _ in ()).throw(RuntimeError("the queue file is not a table"))
        mod.doctor_lines = lambda root: []
        win = FW([-1, -1, -1, ord("q")])
        self.assertEqual(mod.screen_loop(win, d, FC()), 0)
        self.assertTrue(any("reading failed" in r and "RuntimeError" in r for r in win.rows), "the error is on the screen\n" + "\n".join(win.rows[-12:]))

