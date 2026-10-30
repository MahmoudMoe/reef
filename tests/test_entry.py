"""scripts/reef — the owner's one entry point (2026-10-28: "the person opens the terminal, writes reef, sees a logo and the
options with a short description each"). The owner's verbs, one line each; the internal scripts under --all; every verb runs
the sibling script it names."""
import os
import re
import subprocess
import sys
import tempfile
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
        self.assertTrue(lines[-1].startswith("keys: q quit") and "↑↓" in lines[-1] and "Enter" in lines[-1], "quit first: a narrow terminal cuts the end, never the exit (the owner, 2026-10-30)\n" + lines[-1])
        self.assertIn("▶", lines[sel]); self.assertIn("2  answer", lines[sel])
        box = " ".join(l.strip("│ ") for l in lines if l.startswith("│"))
        self.assertIn("python3 scripts/reef-queue.py footnote 'Batch 9' --row 4", box, "the selected item's command, whole, in the box")
        lines, sel = mod.render(model, width=100, height=34, selected=0)
        box = " ".join(l.strip("│ ").strip() for l in lines if l.startswith("│"))
        self.assertIn("the class has 31 members and a later row re-takes them' --row 7", box, "a long command wraps inside the box, never cut")
        lines, sel = mod.render(model, width=100, height=16, selected=2)
        self.assertLessEqual(len(lines), 16, "a short terminal: still fits\n" + "\n".join(lines))
        self.assertTrue(lines[-1].startswith("keys:"), "the keys are last even when short")
        self.assertIn("3  answer", lines[sel], "the selected row scrolled into view\n" + "\n".join(lines))
        # the review's probe: a narrow terminal (the keys wrap to two rows), a short one, a long run and the doctor on — never a
        # line past the height, the keys always last, the selection always on screen; a cut command is marked, never silent
        full = dict(model, steps=[f"21:00 s1 → step {i}" for i in range(40)], warns=["WARN a", "WARN b", "WARN c"], doctor=True)
        for height, width, selected in ((24, 79, 2), (16, 79, 1), (12, 60, 0), (66, 80, 2), (10, 40, 0)):
            lines, sel = mod.render(full, width=width, height=height, selected=selected)
            self.assertLessEqual(len(lines), height, f"{height}x{width}: {len(lines)} lines\n" + "\n".join(lines))
            self.assertTrue(all(len(l) <= width for l in lines), f"{height}x{width}: a line wider than the terminal")
            self.assertIn("q quit", " ".join(lines[-3:]), f"{height}x{width}: the keys end the screen (on one row or wrapped)\n" + "\n".join(lines))
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
        runner = lines[lines.index("RUNNER  the last steps · w follows live"):]
        runner = runner[:next((i for i, l in enumerate(runner) if l.startswith(("DOCTOR", "─"))), len(runner))]
        self.assertLessEqual(len(runner), 8, "an idle runner's log is a tail of a few steps, not the screen\n" + "\n".join(runner))
        self.assertTrue(runner[-1].startswith("  (the run ended"), "and the tail ends by saying so\n" + "\n".join(runner))
        os.unlink(os.path.join(d, ".reef", "inflight", "403"))
        self.assertNotIn("release", [i["kind"] for i in mod.inbox(d)], "released: the item leaves with the marker (one source)")

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
        self.assertEqual(ran[-1][1:], [mod.script("reef-approval.py"), "--owner", "Approve plan reconcile-instruction-layer at 2cc8e8c3487e9ab2?"], "the question, never a placeholder")

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
