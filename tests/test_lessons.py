"""Hardening PR-3 (docs/design/hardening-pr3-plan.md): the learning edge. A failure the loop survived (GREEN after a FAIL, or the
same failure twice) becomes a candidate with facts by code; the model drafts ONE line tagged harness|loop|graph, refused by code
when it is not that shape; the OWNER approves it (a record at the draft's digest); code lands it in the layer's file under a cap,
counts its class's recurrence, proposes its retirement, and removes it on the owner's approval, kept in the history."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import write, load_script, git_repo  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATTEMPT = os.path.join(ROOT, "scripts", "reef-attempt")
LESSONS = os.path.join(ROOT, "scripts", "reef-lessons.py")
APPROVAL = os.path.join(ROOT, "scripts", "reef-approval.py")
LOOP = os.path.join(ROOT, "scripts", "reef-loop.py")
GUARD = os.path.join(ROOT, "scripts", "reef-guard.py")
ROUND_EXPECTED = ("EXPECTED: reef-claims.py round exits 0 — each Proof test fails on the base and passes on the round's tree; "
                  "only files: changed")


def task(tid, feature="demo"):
    return (f"---\nid: {tid}\nfeature: {feature}\nstatus: pending\neffort: medium\nattempts: 0\nfiles: [src/a.py, tests/]\n---\n"
            f"# {tid}\n\n## Acceptance Criteria\n- AC-1 it works\n\n## Log\n")


def project(cap=2, recur=2, quiet=2):
    d = os.path.realpath(tempfile.mkdtemp(prefix="reef-lessons."))
    write(d, ".reef/config.json", json.dumps({"lessons": {"cap": cap, "recur": recur, "quiet_rows": quiet}}))
    os.makedirs(os.path.join(d, "tasks", "done"))
    for t in (101, 102, 103):
        write(d, f"tasks/{t}-t.md", task(t))
    return d


def attempt(d, tid, *fields):
    return subprocess.run([sys.executable, ATTEMPT, os.path.join(d, "tasks", f"{tid}-t.md"), *fields], capture_output=True, text=True, cwd=d)


def lessons(d, *args):
    return subprocess.run([sys.executable, LESSONS, *args, "--repo", d], capture_output=True, text=True, cwd=d)


def owner(d, question):
    return subprocess.run([sys.executable, APPROVAL, "--owner", question], capture_output=True, text=True, cwd=d,
                          env=dict(os.environ, REEF_NO_RESUME="1"))


def ledger(d):
    p = os.path.join(d, ".reef", "approvals", "lessons.jsonl")
    return [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.isfile(p) else []


def twice(d, tid, saw="round: REFUSED — the round changed files outside the task's files: src/b.py"):
    """The same failure twice: the task blocks on its signature (trigger b)."""
    attempt(d, tid, ROUND_EXPECTED, f"SAW: {saw}")
    return attempt(d, tid, ROUND_EXPECTED, f"SAW: {saw}")


def question(d, kind="lesson", lid="L1"):
    out = lessons(d, "report").stdout
    m = re.search(rf"Approve {'retiring ' if kind == 'retire' else ''}lesson {lid} at [0-9a-f]{{16}}\?", out)
    assert m, out
    return m.group(0)


def landed(d, lid="L1", text="harness: a round that edits a file outside files: is refused — name the file in the plan first"):
    r = lessons(d, "draft", lid, text)
    assert r.returncode == 0, r.stdout + r.stderr
    r = owner(d, question(d, lid=lid))
    assert r.returncode == 0, r.stdout + r.stderr
    return r


class Triggers(unittest.TestCase):
    def test_the_same_failure_twice_writes_a_candidate_with_its_facts(self):
        d = project()
        r = twice(d, 101)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("same failure signature twice", r.stderr)
        self.assertIn("lesson L1: candidate (same-failure)", r.stdout)
        cands = [e for e in ledger(d) if e.get("ev") == "candidate"]
        self.assertEqual(len(cands), 1, cands)
        self.assertEqual((cands[0]["trigger"], cands[0]["task"], cands[0]["class"]), ("same-failure", "101", "round-scope"))
        f = lessons(d, "facts", "L1")
        self.assertEqual(f.returncode, 0, f.stdout + f.stderr)
        for want in ("task: 101 (feature demo)", "rounds: 2 FAIL", "class: round-scope", f"sig: {cands[0]['sig']}",
                     "files: [src/a.py, tests/]", "#1 attempt 1 EXPECTED: reef-claims.py round exits 0",
                     "#2 attempt 2 SAW: round: REFUSED — the round changed files outside the task's files: src/b.py",
                     "#1 attempt 1 FENCE (derived):", "python3 scripts/reef-lessons.py draft L1", "lesson L1: end"):
            self.assertIn(want, f.stdout)
        self.assertNotIn("transcript", f.stdout.lower())

    def test_the_retry_cap_alone_is_no_trigger(self):
        d = project()
        for n in (1, 2, 3):
            r = attempt(d, 101, "EXPECTED: AC-1 it works", f"SAW: AssertionError number {n} differs")
        self.assertIn("retry cap 3", r.stderr)
        self.assertEqual([e for e in ledger(d) if e.get("ev") == "candidate"], [])

    def test_every_fail_recorded_appends_a_fail_event_with_its_classes(self):
        d = project()
        attempt(d, 101, ROUND_EXPECTED, "SAW: round: REFUSED — test_a does not fail on the base (abc, 1 test files in place) — the test is not red first",
                "round: REFUSED — the round changed files outside the task's files: src/z.py")
        fails = [e for e in ledger(d) if e.get("ev") == "fail"]
        self.assertEqual(len(fails), 1, ledger(d))
        self.assertEqual(fails[0]["classes"], ["round-not-red", "round-scope"])
        self.assertEqual((fails[0]["task"], fails[0]["feature"], fails[0]["attempt"]), ("101", "demo", 1))

    def test_a_project_without_reef_gets_no_ledger(self):
        d = os.path.realpath(tempfile.mkdtemp(prefix="reef-lessons-bare."))
        write(d, "tasks/101-t.md", task(101))
        attempt(d, 101, "EXPECTED: x", "SAW: y")
        self.assertFalse(os.path.exists(os.path.join(d, ".reef")))


class FailureClass(unittest.TestCase):
    def setUp(self):
        self.m = load_script("reef-lessons.py")

    def cls(self, expected, *saw):
        return self.m.classes({"EXPECTED": [expected], "SAW": list(saw)})

    def test_the_round_checks_refusals(self):
        e = ROUND_EXPECTED[len("EXPECTED: "):]
        self.assertEqual(self.cls(e, "round: REFUSED — the round changed files outside the task's files: a"), ["round-scope"])
        self.assertEqual(self.cls(e, "round: REFUSED — test_x does not pass on the round's tree — green first"), ["round-not-green"])
        self.assertEqual(self.cls(e, "round: REFUSED — test_x ran no test (gates.one: `x`)"), ["round-no-test"])
        self.assertEqual(self.cls(e, "round: REFUSED — test_x timed out on the base (gates.timeout_s)"), ["round-timeout"])
        self.assertEqual(self.cls(e, "round: REFUSED — files: must be a list, `files: [x]`"), ["round-files-shape"])
        self.assertEqual(self.cls(e, "round: REFUSED — something new"), ["round-other"])

    def test_graph_settles_reasons(self):
        e = "gate exit 0, the hand-back check ok, every judge PASS"
        self.assertEqual(self.cls(e, "gate exit 1: boom", "verifier report rejected: no RULE", "FAILED tests/x.py::t"), ["gate-red", "report-rejected"])
        self.assertEqual(self.cls(e, "verifier: FAIL — AC-2 missing"), ["verifier-fail"])
        self.assertEqual(self.cls(e, "hand-back rejected: no Claims"), ["handback-rejected"])
        self.assertEqual(self.cls(e, "who knows"), ["settle-other"])

    def test_a_recorders_own_expected_is_its_hash_the_same_across_noise(self):
        a, b = self.cls("AC-2 the export refuses an empty name", "x"), self.cls("ac-2  the export refuses an empty name ", "y")
        self.assertTrue(a[0].startswith("expected-") and len(a[0]) == len("expected-") + 8, a)
        self.assertEqual(a, b)
        self.assertNotEqual(a, self.cls("AC-3 another requirement", "x"))


class Draft(unittest.TestCase):
    def setUp(self):
        self.d = project()
        twice(self.d, 101)

    def refused(self, text, lid="L1"):
        before = ledger(self.d)
        r = lessons(self.d, "draft", lid, text)
        self.assertEqual(r.returncode, 2, f"{text!r}: {r.stdout}{r.stderr}")
        self.assertEqual(ledger(self.d), before, "a refused draft writes nothing")
        return r.stderr

    def test_the_shape_is_code(self):
        self.assertIn("one line", self.refused("harness: first line of the lesson is fine\nharness: and a second one"))
        self.assertIn("harness, loop or graph", self.refused("a lesson with no layer tag in front of it at all"))
        self.assertIn("harness, loop or graph", self.refused("planner: a lesson tagged with a layer that does not exist"))
        self.assertIn("20", self.refused("harness: too short"))
        self.assertIn("160", self.refused("harness: " + "x" * 161))
        self.assertIn("bullet", self.refused("harness: # a heading is not a lesson line at all"))
        self.assertIn("control", self.refused("harness: a lesson with a \x1b[31m terminal escape inside"))
        self.assertIn("not a candidate", self.refused("harness: a fine lesson for a candidate that is not there", lid="L9"))

    def test_a_good_draft_is_recorded_and_proposed_with_its_question(self):
        r = lessons(self.d, "draft", "L1", "Harness: name every file the fix touches in files: before the round starts")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        drafts = [e for e in ledger(self.d) if e.get("ev") == "draft"]
        self.assertEqual((drafts[0]["layer"], drafts[0]["lesson"]), ("harness", "name every file the fix touches in files: before the round starts"))
        rep = lessons(self.d, "report").stdout
        self.assertRegex(rep, r"proposed: L1 harness — name every file .* — Approve lesson L1 at [0-9a-f]{16}\?")

    def test_an_undrafted_candidate_is_named_with_its_facts_command(self):
        self.assertIn("to draft: L1 (same-failure, task 101, class round-scope) — python3 scripts/reef-lessons.py facts L1", lessons(self.d, "report").stdout)


class ApproveAndLand(unittest.TestCase):
    def setUp(self):
        self.d = project()
        twice(self.d, 101)

    def test_the_owners_approval_lands_the_line_with_its_id_class_signature_and_date(self):
        r = landed(self.d)
        self.assertIn("lesson L1 landed in reef/lessons/harness.md", r.stdout)
        text = open(os.path.join(self.d, "reef", "lessons", "harness.md")).read()
        sig = [e for e in ledger(self.d) if e.get("ev") == "candidate"][0]["sig"]
        self.assertRegex(text, r"(?m)^## Lessons\n(.*\n)*- L1 · class round-scope · sig " + sig + r" · landed \d{4}-\d\d-\d\d · a round that edits")
        rec = json.load(open(os.path.join(self.d, ".reef", "approvals", "lesson-L1.json")))
        self.assertEqual((rec["action"], rec["by"]), ("land", "owner"))
        self.assertIn("landed: L1 harness · round-scope", lessons(self.d, "report").stdout)

    def test_a_redraft_makes_the_old_question_stale_and_nothing_is_written(self):
        lessons(self.d, "draft", "L1", "harness: the first draft of the lesson, long enough")
        q = question(self.d)
        lessons(self.d, "draft", "L1", "harness: the second draft of the lesson, long enough")
        r = owner(self.d, q)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("stale", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.d, "reef", "lessons", "harness.md")))
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "approvals", "lesson-L1.json")))

    def test_another_answer_than_approve_writes_nothing(self):
        lessons(self.d, "draft", "L1", "harness: the first draft of the lesson, long enough")
        payload = {"tool_name": "AskUserQuestion", "cwd": self.d, "tool_response": {"answers": {question(self.d): "Not yet"}}}
        subprocess.run([sys.executable, APPROVAL], input=json.dumps(payload), capture_output=True, text=True, cwd=self.d)
        self.assertFalse(os.path.exists(os.path.join(self.d, "reef", "lessons", "harness.md")))

    def test_the_hook_takes_the_owners_answer(self):
        lessons(self.d, "draft", "L1", "loop: close a task only after its round check printed ok in the same session")
        payload = {"tool_name": "AskUserQuestion", "cwd": self.d, "tool_response": {"answers": {question(self.d): "Approve"}}}
        subprocess.run([sys.executable, APPROVAL], input=json.dumps(payload), capture_output=True, text=True, cwd=self.d)
        self.assertIn("- L1 · class round-scope", open(os.path.join(self.d, "reef", "lessons", "loop.md")).read())

    def test_an_agent_cannot_run_the_approval_for_a_lesson(self):
        lessons(self.d, "draft", "L1", "harness: the first draft of the lesson, long enough")
        q = question(self.d)
        r = subprocess.run([sys.executable, GUARD], input=json.dumps({"tool_name": "Bash", "cwd": self.d, "tool_input": {
            "command": f'python3 scripts/reef-approval.py --owner "{q}"'}}), capture_output=True, text=True)
        self.assertIn("reef-guard DENY: reef-approval.py records the OWNER's approval", r.stdout + r.stderr)
        r = subprocess.run([sys.executable, APPROVAL, "--proxy", "--day", "--kind", "process", "--row", "1", "--report", ".reef/ci-local/x.md"],
                           capture_output=True, text=True, cwd=self.d)
        self.assertFalse(os.path.exists(os.path.join(self.d, "reef", "lessons", "harness.md")), "no proxy path lands a lesson")

    def test_the_cap_refuses_a_landing_until_one_is_retired(self):
        landed(self.d)
        twice(self.d, 102, saw="round: REFUSED — test_b does not fail on the base (x) — the test is not red first")
        landed(self.d, "L2", "harness: write the failing assertion before the code, and run it on the base first")
        twice(self.d, 103, saw="round: REFUSED — test_c ran no test (gates.one: `x`)")
        lessons(self.d, "draft", "L3", "harness: name the test exactly as the runner names it, or it runs no test at all")
        before = open(os.path.join(self.d, "reef", "lessons", "harness.md")).read()
        r = owner(self.d, question(self.d, lid="L3"))
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("holds 2/2 lessons — retire one first", r.stdout)
        self.assertEqual(open(os.path.join(self.d, "reef", "lessons", "harness.md")).read(), before)
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "approvals", "lesson-L3.json")))
        self.assertIn("harness 2/2", lessons(self.d, "report").stdout)
        # retire one: the slot frees, the third lands
        r = owner(self.d, question(self.d, "retire", "L1"))
        self.assertEqual(r.returncode, 0, r.stdout)
        r = owner(self.d, question(self.d, lid="L3"))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("- L3 ·", open(os.path.join(self.d, "reef", "lessons", "harness.md")).read())


class Measure(unittest.TestCase):
    def setUp(self):
        self.d = project(cap=5, recur=2, quiet=2)
        attempt(self.d, 103, ROUND_EXPECTED, "SAW: round: REFUSED — the round changed files outside the task's files: early")   # before landing
        twice(self.d, 101)
        landed(self.d)
        self.m = load_script("reef-lessons.py")

    def line(self):
        return next(l for l in lessons(self.d, "report").stdout.splitlines() if l.startswith("- landed: L1"))

    def test_recurrence_counts_only_its_class_after_landing(self):
        self.assertIn("recurred 0", self.line())
        attempt(self.d, 102, "EXPECTED: AC-1 it works", "SAW: another class of failure")
        self.assertIn("recurred 0", self.line(), "another class is no recurrence")
        attempt(self.d, 102, ROUND_EXPECTED, "SAW: round: REFUSED — the round changed files outside the task's files: src/q.py")
        self.assertIn("recurred 1", self.line())

    def test_quiet_rows_count_distinct_features_closed_since(self):
        self.assertIn("0 rows since", self.line())
        for tid, feat in (("101", "demo"), ("102", "demo"), ("103", "other")):
            p = os.path.join(self.d, "tasks", f"{tid}-t.md")
            open(p, "w").write(task(int(tid), feat))
            self.m.record_close(self.d, p)
        self.assertIn("2 rows since", self.line())


class Prune(unittest.TestCase):
    def setUp(self):
        self.d = project(cap=5, recur=2, quiet=2)
        twice(self.d, 101)
        landed(self.d)
        self.m = load_script("reef-lessons.py")

    def report(self):
        return lessons(self.d, "report").stdout

    def test_neither_rule_proposes_nothing(self):
        self.assertNotIn("retire?", self.report())

    def test_a_class_that_recurs_n_times_is_proposed_as_a_code_check_or_retired(self):
        for tid in (102, 103):
            attempt(self.d, tid, ROUND_EXPECTED, f"SAW: round: REFUSED — the round changed files outside the task's files: src/{tid}.py")
        self.assertRegex(self.report(), r"retire\? L1 — recurred 2 times since it landed: it does not work — turn it into a code check, "
                                        r"or retire it — Approve retiring lesson L1 at [0-9a-f]{16}\?")

    def test_no_recurrence_over_m_rows_is_the_deletion_test(self):
        for tid, feat in (("102", "a"), ("103", "b")):
            p = os.path.join(self.d, "tasks", f"{tid}-t.md")
            open(p, "w").write(task(int(tid), feat))
            self.m.record_close(self.d, p)
        self.assertRegex(self.report(), r"retire\? L1 — no recurrence over 2 rows: the deletion test — retire it — Approve retiring lesson L1")

    def test_the_retirement_removes_the_line_and_keeps_it_in_the_history(self):
        r = owner(self.d, question(self.d, "retire", "L1"))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("- L1 ·", open(os.path.join(self.d, "reef", "lessons", "harness.md")).read())
        hist = open(os.path.join(self.d, "reef", "lessons", "history.md")).read()
        self.assertRegex(hist, r"- \d{4}-\d\d-\d\d retired L1 \(harness, class round-scope, recurred 0 over 0 rows, landed \d{4}-\d\d-\d\d\): a round that edits")
        self.assertEqual(json.load(open(os.path.join(self.d, ".reef", "approvals", "lesson-L1-retire.json")))["action"], "retire")
        self.assertNotIn("L1", "\n".join(l for l in self.report().splitlines() if l.startswith("- landed")))
        self.assertIn("- layers: harness 0/5", self.report(), "the slot is free")


class Delivery(unittest.TestCase):
    def setUp(self):
        self.d = project()
        twice(self.d, 101)
        landed(self.d)
        self.hf = os.path.join(self.d, "reef", "lessons", "harness.md")

    def dispatch(self):
        return subprocess.run([sys.executable, ATTEMPT, os.path.join(self.d, "tasks", "102-t.md")], capture_output=True, text=True, cwd=self.d).stdout

    def test_the_dispatch_prints_the_harness_lessons_the_owner_approved(self):
        out = self.dispatch()
        self.assertIn("lessons: 1 landed (harness, reef/lessons/harness.md, approved by the owner) — pass every line through `lessons: end` "
                      "to the implementer verbatim", out)
        self.assertIn("  L1 (round-scope): a round that edits a file outside files: is refused — name the file in the plan first\nlessons: end", out)

    def test_a_line_edited_or_added_by_hand_is_not_delivered_and_the_report_says_so(self):
        text = open(self.hf).read()
        open(self.hf, "w").write(text.replace("is refused", "is fine") + "- L7 · class x · sig y · landed 2026-11-15 · a line nobody approved\n")
        out = self.dispatch()
        self.assertNotIn("is fine", out)
        self.assertNotIn("nobody approved", out)
        rep = lessons(self.d, "report").stdout
        self.assertIn("not approved (edited by hand, not delivered): reef/lessons/harness.md: - L7", rep)
        self.assertIn("not approved (edited by hand, not delivered): reef/lessons/harness.md: - L1", rep)

    def test_the_session_start_carries_the_loop_lessons(self):
        d = git_repo(prefix="reef-lessons-loop.", branch="main", config={"gates": {"full": "true"}, "lessons": {"cap": 2}})
        write(d, "tasks/101-t.md", task(101))
        write(d, ".reef/version", "0.7.4\n")
        twice(d, 101)
        lessons(d, "draft", "L1", "loop: close a task only after its round check printed ok in the same session")
        self.assertEqual(owner(d, question(d)).returncode, 0)
        out = subprocess.run([sys.executable, LOOP, "tick", "--session-start", "--repo", d], capture_output=True, text=True,
                             env=dict(os.environ, PATH="/nonexistent-gh:" + os.environ["PATH"])).stdout
        self.assertIn("lessons: 1 landed (loop, reef/lessons/loop.md, approved by the owner)", out)
        self.assertIn("  L1 (round-scope): close a task only after its round check printed ok in the same session", out)


class Report(unittest.TestCase):
    def test_the_night_report_has_the_lessons_section(self):
        d = git_repo(prefix="reef-lessons-night.", branch="main", config={"gates": {"full": "true"}, "lessons": {"cap": 2}}, identity=True)
        write(d, "tasks/101-t.md", task(101))
        write(d, "README.md", "x\n")
        subprocess.run(["git", "-C", d, "add", "-A"], check=True)
        subprocess.run(["git", "-C", d, "commit", "-qm", "init"], check=True)
        twice(d, 101)
        lessons(d, "draft", "L1", "harness: name every file the fix touches in files: before the round starts")
        os.makedirs(os.path.join(d, ".reef", "night"), exist_ok=True)
        log = os.path.join(d, ".reef", "run", "run.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        open(log, "w").close()
        load_script("reef-run.py").morning_report(d, "2000-01-01T00:00:00Z", log)
        rep = open(os.path.join(d, ".reef", "night", "report.md")).read()
        self.assertIn("## Lessons (approve: python3 scripts/reef-approval.py --owner \"<question>\")", rep)
        self.assertRegex(rep, r"- proposed: L1 harness — name every file .* — Approve lesson L1 at [0-9a-f]{16}\?")
        self.assertIn("- layers: harness 0/2 · loop 0/2 · graph 0/2", rep)

    def test_the_screens_inbox_has_the_approve_item_and_drops_it_once_landed(self):
        d = git_repo(prefix="reef-lessons-screen.", branch="main", config={"gates": {"full": "true"}})
        write(d, ".reef/version", "0.7.4\n")
        os.makedirs(os.path.join(d, ".reef", "run"), exist_ok=True)
        write(d, "tasks/101-t.md", task(101))
        twice(d, 101)
        lessons(d, "draft", "L1", "harness: name every file the fix touches in files: before the round starts")
        q = question(d)
        mod = load_script("reef", "reef_entry_lessons_under_test")
        mod.runner_view = lambda root: (0, 0, "")
        cmds = [i["cmd"] for i in mod.inbox(d)]
        self.assertIn(f'python3 scripts/reef-approval.py --owner "{q}"', cmds)
        self.assertEqual(owner(d, q).returncode, 0)
        self.assertNotIn(f'python3 scripts/reef-approval.py --owner "{q}"', [i["cmd"] for i in mod.inbox(d)])


if __name__ == "__main__":
    unittest.main()
