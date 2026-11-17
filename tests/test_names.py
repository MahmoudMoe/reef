"""Hardening PR-10 (docs/design/hardening-pr10-plan.md; 2026-11-17, the owner: "the reports use ids nobody explained"): every row,
task, lesson or ADR id the owner reads carries its name — `row 7 (CSV export)`, never a bare `row 7`.

The check is reef_common.bare_refs over each owner-facing output, rendered from one fixture project. The outputs covered (a new
owner-facing writer is covered once a test here renders it): the night report and the autopilot report (reef-run.py
morning_report, with reef-lessons.py report_lines), the runner's wait lines (owner_wait_lines), the night contract's lines
(reef-run.py contract) and the `reef` screen's inbox texts. Exempt by the detector, never by a test: an approval question verbatim,
a command, a backtick span, a RUN:/VERDICT/summary: line."""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from _fixtures import git_repo, load_script, write  # noqa: E402
import reef_common as C  # noqa: E402

RUN = os.path.join(ROOT, "scripts", "reef-run.py")
QUEUE = os.path.join(ROOT, "scripts", "reef-queue.py")
WAIT = "owner: row 7 needs your answer; rows 3 and 12 wait on it (task 1201 is parked)"


def task(tid, feature, title):
    return (f"---\nid: {tid}\nfeature: {feature}\nstatus: pending\neffort: medium\nattempts: 0\nfiles: [src/a.py]\n---\n"
            f"# {tid} — {title}\n\n## Acceptance Criteria\n- AC-1 it works\n\n## Log\n")


def project():
    d = os.path.realpath(git_repo(prefix="reef-names.", branch="develop", identity=True))
    write(d, ".reef/config.json", json.dumps({"gates": {"full": "true"}, "branches": {"base": "develop", "release": "main"},
                                              "paths": {"features": "reef/features", "tasks": "tasks", "queue": "reef/queue.md"}}))
    write(d, ".reef/version", "0.7.4\n")
    write(d, "reef/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n"
                              "| 12 | share links | | planned | 1 | |\n| 3 | editable items | | planned | 1 | |\n| 7 | CSV export | | planned | 1 | |\n")
    write(d, "reef/features/share-links/tasks/1201-button.md", task(1201, "share-links", "the share button"))
    write(d, "reef/features/editable-items/tasks/301-form.md", task(301, "editable-items", "the edit form"))
    write(d, "reef/owner.md", "# The owner\nSimple and robust.\n")
    write(d, ".reef/night/contract.md", "# Night\nRows: 12, 3\nDecisions: plan approvals.\nHard limits: the release to main.\n")
    write(d, "README.md", "x\n")
    subprocess.run(["git", "-C", d, "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", d, "commit", "-qm", "init"], check=True, capture_output=True)
    # what the night left: the proxy's footnote (night and day), a day decision, three lessons, a filed question, a wait, a task in flight
    for text in ("Mahmoud (proxy, night 2099-01-01): row 12 ships as two tasks — the plan's task 1201 is half the row",
                 "Mahmoud (proxy, day 2099-01-01, process): split task 1201 in two — row 12's review asked"):
        r = subprocess.run([sys.executable, QUEUE, "footnote", text, "--row", "12", "--repo", d], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
    write(d, ".reef/approvals/day-decisions.jsonl", json.dumps({"at": "2099-01-01T01:00:00Z", "row": "12", "kind": "process",
          "question": "split task 1201 in two?", "decision": "yes", "footnote": "[^2]"}) + "\n")
    led = [{"ev": "candidate", "id": "L1", "at": "2099-01-01T00:00:00Z", "trigger": "same-failure", "task": "1201", "feature": "share-links",
            "sig": "s1", "class": "round-scope", "files": "", "rounds": 2, "facts": []},
           {"ev": "draft", "id": "L1", "at": "2099-01-01T00:01:00Z", "layer": "harness", "lesson": "harness: name every file the fix touches in files: first"},
           {"ev": "candidate", "id": "L2", "at": "2099-01-01T00:02:00Z", "trigger": "green-after-fail", "task": "301", "feature": "editable-items",
            "sig": "s2", "class": "gate", "files": "", "rounds": 1, "facts": []}]
    write(d, ".reef/approvals/lessons.jsonl", "".join(json.dumps(e) + "\n" for e in led))
    write(d, ".reef/questions.md", C.question_line("7", "Keep the old export route for row 3?", "yes, it is served today") + "\n")
    write(d, ".reef/loop.json", json.dumps({"active": True, "wait": WAIT, "stop": None, "parked": None, "hashes": []}))
    write(d, ".reef/inflight/1201", json.dumps({"id": "1201", "agent": "implementer"}))
    os.makedirs(os.path.join(d, ".reef", "run"), exist_ok=True)
    open(os.path.join(d, ".reef", "run", "run.log"), "w").close()
    return d


class TheOwnerReadsNames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = project()
        cls.names = C.names(cls.d)

    def assertNamed(self, what, text):
        bare = C.bare_refs(text, self.names)
        self.assertEqual(bare, [], f"{what}: bare ids {bare}\n--- {what} ---\n{text}")

    def test_the_names_are_read_from_the_project(self):
        n = self.names
        self.assertEqual((n["row"].get("12"), n["task"].get("1201"), n["lesson"].get("L1"), n["lesson"].get("L2")),
                         ("share links", "the share button", "name every file the fix touches in files: first", "not drafted yet"))

    def test_the_night_report_names_every_id(self):
        run = load_script("reef-run.py", "reef_run_names")
        run.morning_report(self.d, "2000-01-01T00:00:00Z", os.path.join(self.d, ".reef", "run", "run.log"))
        rep = open(os.path.join(self.d, ".reef", "night", "report.md"), encoding="utf-8").read()
        self.assertNamed("the night report", rep)
        self.assertIn("row 7 (CSV export)", rep, "the question waiting for the owner names its row")
        self.assertIn("Approve lesson L1 at", rep, "the approval question stays verbatim — the hook matches it exactly")

    def test_the_autopilot_report_names_every_id(self):
        run = load_script("reef-run.py", "reef_run_names_day")
        run.morning_report(self.d, "2000-01-01T00:00:00Z", os.path.join(self.d, ".reef", "run", "run.log"), mode="autopilot")
        self.assertNamed("the autopilot report", open(os.path.join(self.d, ".reef", "run", "autopilot.md"), encoding="utf-8").read())

    def test_the_runners_wait_names_every_id_and_keeps_its_commands(self):
        run = load_script("reef-run.py", "reef_run_names_wait")
        text = run.owner_wait_lines(self.d, WAIT, "claude")
        self.assertNamed("the runner's wait", text)
        self.assertIn("--row 7", text, "the command the owner copies is the command, not prose")

    def test_the_night_contract_names_its_rows(self):
        r = subprocess.run([sys.executable, RUN, "contract", "--repo", self.d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNamed("the night contract", r.stdout)
        self.assertRegex(r.stdout, r"(?m)^question: Approve night \d{4}-\d\d-\d\d at [0-9a-f]{16}\?$", "the question stays exact")

    def test_the_inbox_names_every_id(self):
        mod = load_script("reef", "reef_entry_names")
        mod.runner_view = lambda root: (0, 0, "")   # no runner: the task left in flight is an item
        mod.row_state = lambda root, row: {"row": row, "state": "approval", "detail": "Approve plan csv-export at 0123456789abcdef?"} if row == "7" else {}
        items = mod.inbox(self.d)
        self.assertNamed("the inbox", "\n".join(i["text"] for i in items))
        self.assertIn("python3 scripts/reef-run.py release 1201", [i["cmd"] for i in items], "the command is untouched")


class TheDetector(unittest.TestCase):
    """bare_refs: what counts as a bare id, and the exempt spans (an approval question, a command, a backtick span, RUN:)."""
    N = {"row": {"7": "CSV export", "12": "share links"}, "task": {"403": "the button"}, "lesson": {"L1": "name every file"}}

    def test_a_bare_id_is_found_and_a_named_one_is_not(self):
        for text, bare in (("row 7: keep it?", [("row", "7")]), ("rows 7, 12 and 3 wait", [("row", "7"), ("row", "12"), ("row", "3")]),
                           ("task 403 is in flight", [("task", "403")]), ("- proposed: L1 harness", [("lesson", "L1")]),
                           ("DECIDE row #12 split it", [("row", "12")]), ("ADR 0003 holds", [("adr", "0003")]),
                           ("row 12 (process): x", [("row", "12")]), ("rows: 12, 3", [("row", "12"), ("row", "3")]),   # a word in parentheses is not the row's name
                           ("row 7 (CSV export): keep it?", []), ("rows 7 (CSV export), 12 (share links)", []),
                           ("lesson L1 (name every file) — harness", []), ("task 403 (the button)", [])):
            self.assertEqual(C.bare_refs(text, self.N), bare, text)

    def test_machine_read_spans_and_non_ids_are_exempt(self):
        for text in ("Approve lesson L1 at 0123456789abcdef?", "Approve plan share-links at 0123456789abcdef?",
                     "  python3 scripts/reef-queue.py footnote 'x' --row 7", "the command `reef approve 9`",
                     "RUN: agent=mahmoud night=2099-01-01 question=row 12", "summary: share-links · 2 task(s)",
                     "| Rows merged | 1 | – |", "Row: 12", "PR #377 merged", "3 rows since", "tasks/done/101-a.md",
                     "undo: git revert -m 1 abc1234 (row 7)"):
            self.assertEqual(C.bare_refs(text, self.N), [], text)

    def test_name_refs_names_prose_and_leaves_the_exempt_spans(self):
        self.assertEqual(C.name_refs("row 7 and task 403; `row 12`; python3 x --row 12", self.N),
                         "row 7 (CSV export) and task 403 (the button); `row 12`; python3 x --row 12")
        self.assertEqual(C.name_refs("rows 7, 12 and 9", self.N), "rows 7 (CSV export), 12 (share links) and 9 (not in the queue)")
        self.assertEqual(C.named("row", "7", self.N), "row 7 (CSV export)")
        self.assertEqual(C.named("task", "999", self.N), "task 999 (no task file)", "a name not found is said")
        long = {"row": {"1": "x" * 100}}
        self.assertEqual(len(C.named("row", "1", long)), len("row 1 ()") + C.NAME_MAX, "a long name is cut to NAME_MAX, the cut marked")
        self.assertTrue(C.named("row", "1", long).endswith("…)"))


if __name__ == "__main__":
    unittest.main()
