"""Workflow v3, phase 6 — the proxy by day: the owner approves `reef/proxy.md` (what Mahmoud decides by day: process and
wording) once at its digest; in the day loop a question of those kinds goes to the proxy, and his decision is written as
a labelled footnote by `reef-approval.py --proxy --day` from his own report — never typed by the orchestrator (the guard
refuses the label by hand, however spelled, into any writer); product, money, data, look, security and the release stay
the owner's; the batch counts the owner's questions (one per footnote mark) and the proxy's day decisions (its record)."""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import test_night as N   # noqa: E402  (the night fixture: owner.md, a queue with rows 12 and 3, feature folders)
import test_guard as G   # noqa: E402  (the guard's Bash runner)
RUN = os.path.join(ROOT, "scripts", "reef-run.py")
APPROVAL = os.path.join(ROOT, "scripts", "reef-approval.py")
COST = os.path.join(ROOT, "scripts", "reef-cost.py")
TODAY = time.strftime("%Y-%m-%d")
REPORT = ("RUN: agent=mahmoud day={day} kind={kind} question=split 1201 in two?\n"
          "DECIDE split 1201 in two? — no, keep one task — the slice is small (reef/owner.md: simple and robust)\nVERDICT: DONE\n")


def contract_day(d):
    return subprocess.run([sys.executable, RUN, "contract", "--day", "--repo", d], capture_output=True, text=True)


def approve_day(tc, d):
    r = contract_day(d)
    tc.assertEqual(r.returncode, 0, r.stdout + r.stderr)
    q = [l for l in r.stdout.splitlines() if l.startswith("question: ")][0][len("question: "):]
    tc.assertRegex(q, r"^Approve proxy by day at [0-9a-f]{16}\?$")
    r = N.hook(d, q)
    tc.assertIn("proxy by day approved", r.stdout)
    return q


def decide(d, kind="process", row="12", report=".reef/ci-local/report-mahmoud-day-12.md", text=None, day=TODAY):
    p = os.path.join(d, report)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(text if text is not None else REPORT.format(kind=kind, day=day))
    return subprocess.run([sys.executable, APPROVAL, "--proxy", "--day", "--kind", kind, "--row", row, "--report", report],
                          capture_output=True, text=True, cwd=d)


def load_run():
    loader = importlib.machinery.SourceFileLoader("reef_run", RUN)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class DayContract(unittest.TestCase):
    def test_the_owner_approves_the_day_contract_once_at_its_digest_and_an_edit_voids_it(self):
        d = N.project()
        self.assertFalse(os.path.exists(os.path.join(d, "reef", "proxy.md")))
        q = approve_day(self, d)
        text = open(os.path.join(d, "reef", "proxy.md")).read()
        self.assertIn("Decides: process, wording", text, "seeded from Reef's default: the owner edits it, then approves again")
        rec = json.load(open(os.path.join(d, ".reef", "approvals", "day.json")))
        self.assertEqual(rec["digest16"], q.split(" at ")[1][:16])
        self.assertIn("approved_at", rec)
        os.unlink(os.path.join(d, ".reef", "approvals", "day.json"))
        N.hook(d, q, label="Edit")
        self.assertFalse(os.path.exists(os.path.join(d, ".reef", "approvals", "day.json")), "the same question, answered otherwise, approves nothing")
        approve_day(self, d)
        with open(os.path.join(d, "reef", "proxy.md"), "a") as f:
            f.write("Decides: process, wording, product\n")
        r = decide(d, kind="product")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("changed since the owner approved", r.stdout)


class DayDecision(unittest.TestCase):
    def setUp(self):
        self.d = N.project()
        approve_day(self, self.d)

    def test_a_process_decision_becomes_the_proxys_labelled_footnote_and_a_record_once(self):
        r = decide(self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        q = open(os.path.join(self.d, "reef", "queue.md")).read()
        self.assertIn(f"Mahmoud (proxy, day {TODAY}, process): no, keep one task — the slice is small", q)
        self.assertRegex(q, r"\|\s*12\s*\|[^\n]*¹\s*\|", "the footnote mark on row 12")
        self.assertEqual(q.count(f"({TODAY})"), 1, "one date on the footnote: the clock's")
        log = [json.loads(l) for l in open(os.path.join(self.d, ".reef", "approvals", "day-decisions.jsonl"))]
        self.assertEqual((log[0]["row"], log[0]["kind"]), ("12", "process"))
        self.assertIn("split 1201 in two?", log[0]["question"])
        r = decide(self.d)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("already recorded", r.stdout, "the same report run twice is one decision, not two")
        self.assertEqual(open(os.path.join(self.d, "reef", "queue.md")).read().count("Mahmoud (proxy, day"), 1)

    def test_the_owners_kinds_a_wait_a_foreign_report_a_stale_date_a_night_and_no_approval_write_nothing(self):
        r = decide(self.d, kind="product")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("the owner's", r.stdout)
        r = decide(self.d, text=f"RUN: agent=mahmoud day={TODAY} kind=process question=x\nWAIT x — the owner kept it (footnote 3)\nVERDICT: DONE\n")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("WAIT", r.stdout); self.assertIn("reef-queue.py ask", r.stdout)
        r = decide(self.d, report="notes.md")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("Mahmoud's own file", r.stdout)
        r = decide(self.d, text="RUN: agent=mahmoud night=2026-10-26\nAPPROVE plan share-links at 0000000000000000 — x\nVERDICT: DONE\n")
        self.assertEqual(r.returncode, 1, r.stdout)
        r = decide(self.d, day="2026-10-20")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("today is", r.stdout, "the date is the clock's, not the report's")
        N.L.write(self.d, ".reef/night/active", "{}")
        r = decide(self.d)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("night", r.stdout, "while a night runs its contract governs; the day contract waits for the morning")
        os.unlink(os.path.join(self.d, ".reef", "night", "active"))
        self.assertNotIn("Mahmoud (proxy, day", open(os.path.join(self.d, "reef", "queue.md")).read())
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "approvals", "day-decisions.jsonl")))
        os.unlink(os.path.join(self.d, ".reef", "approvals", "day.json"))
        r = decide(self.d)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("no .reef/approvals/day.json", r.stdout)


class DayGuard(unittest.TestCase):
    def agent(self, cmd, who="reef:implementer"):
        return G.run_guard({"tool_name": "Bash", "agent_id": "a0e1e40f", "agent_type": who, "tool_input": {"command": cmd}})

    def test_the_day_label_is_never_typed_by_hand_however_spelled_into_any_writer(self):
        for cmd in ('python3 scripts/reef-queue.py footnote "Mahmoud (proxy, day 2026-10-26, process): keep one task — small" --row 12',
                    'python3 scripts/reef-queue.py footnote "Mahmoud (proxy,  Day 2026-10-26, process): x" --row 12',
                    'python3 scripts/reef-queue.py footnote "Mahmoud (by proxy, day 2026-10-26, process): x" --row 12',
                    'python3 scripts/reef-queue.py drop-row 12 --reason "Mahmoud (proxy, day 2026-10-26, process): x"',
                    'python3 scripts/reef-queue.py note "Mahmoud (proxy, day 2026-10-26, process): x" --row 12',
                    'gh issue comment 7 --body "Mahmoud (proxy, day 2026-10-26, process): x"',
                    'L="(proxy, day"; python3 scripts/reef-queue.py footnote "Mahmoud $L 2026-10-26, process): x" --row 12'):
            r = G.bash(cmd)
            self.assertEqual(r.returncode, 2, cmd + "\n" + r.stdout + r.stderr)
            self.assertTrue("--proxy --day" in r.stderr or "shell variable" in r.stderr, cmd + "\n" + r.stderr)
        for cmd in ('python3 scripts/reef-queue.py footnote "Mahmoud (proxy, night 2026-10-26): keep one task — small" --row 12',
                    'python3 scripts/reef-queue.py footnote "the owner: keep one task" --row 12',
                    'gh issue comment 7 --body "merged in #9"'):
            r = G.bash(cmd)
            self.assertEqual(r.returncode, 0, cmd + "\n" + r.stderr)

    def test_the_report_is_copied_from_the_scratchpad_and_only_the_proxy_or_the_main_session_records_it(self):
        r = G.bash("cp /tmp/r.md .reef/ci-local/report-mahmoud-day-12.md")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("scratchpad", r.stderr, "a copy from anywhere is a report nobody but the orchestrator wrote")
        self.assertEqual(G.bash("cp /tmp/claude-1/x/scratchpad/r.md .reef/ci-local/report-mahmoud-day-12.md").returncode, 0)
        self.assertEqual(G.bash("cp /tmp/reef-graph-0a1b2c3d/row-x-1/review-x.md .reef/ci-local/report-mahmoud-day-12.md").returncode, 0,
                         "the agents' own report folder is a scratchpad too")
        r = G.run_guard({"tool_name": "Write", "tool_input": {"file_path": ".reef/CI-LOCAL/report-mahmoud-day-12.md", "content": "x"}})
        self.assertEqual(r.returncode, 2, "a case-insensitive disk opens .reef/CI-LOCAL/ as the same folder")
        cmd = "python3 scripts/reef-approval.py --proxy --day --kind process --row 12 --report .reef/ci-local/report-mahmoud-day-12.md"
        self.assertEqual(self.agent(cmd).returncode, 2, "an implementer is not the proxy")
        self.assertEqual(self.agent(cmd, who="reef:mahmoud").returncode, 0)
        self.assertEqual(G.bash(cmd).returncode, 0, "the orchestrator runs it after copying his report")
        r = G.run_guard({"tool_name": "Edit", "agent_id": "a0e1e40f", "agent_type": "reef:implementer", "cwd": ROOT,
                         "tool_input": {"file_path": os.path.join(ROOT, "docs", "queue.md"), "old_string": "a", "new_string": "b"}})
        self.assertEqual(r.returncode, 2, "queue edits are commands; no agent edits the queue file")


class DayNumbers(unittest.TestCase):
    def test_the_batch_counts_the_owners_questions_once_each_and_the_proxys_decisions_from_their_record(self):
        d = N.project()
        approve_day(self, d)
        q = os.path.join(ROOT, "scripts", "reef-queue.py")
        subprocess.run([sys.executable, q, "footnote", "Owner: ship it as one task", "--row", "12", "--repo", d], check=True, capture_output=True)
        self.assertEqual(decide(d).returncode, 0)
        N.L.git(d, "add", "-A"); N.L.git(d, "commit", "-qm", "two footnotes")
        qp = os.path.join(d, "reef", "queue.md")
        open(qp, "w").write(open(qp).read().replace("ship it as one task", "ship it as one task, in batch 1"))   # the owner's undo-by-edit
        # a drop's footnote (what cmd_drop_row writes) is not a question
        subprocess.run([sys.executable, q, "footnote", "row 13 deleted (rule 7): superseded", "--repo", d], check=True, capture_output=True)
        N.L.git(d, "add", "-A"); N.L.git(d, "commit", "-qm", "an edit and a drop")
        r = subprocess.run([sys.executable, COST, "rows", "--repo", d, "--since", "2026-01-01", "--format", "json"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        b = json.loads(r.stdout)["batch"]
        self.assertEqual((b["owner_questions"], b["proxy_day_decisions"]), (1, 1), "an edited footnote is the same question; a drop is not a question")
        run = load_run()
        table = "\n".join(run.numbers_table(None, None))
        self.assertIn("Owner questions", table); self.assertIn("proxy by day", table)
        log = os.path.join(d, ".reef", "run", "run.log")
        os.makedirs(os.path.dirname(log), exist_ok=True); open(log, "w").close()
        os.makedirs(os.path.join(d, ".reef", "night"), exist_ok=True)
        run.morning_report(d, "2026-01-01T00:00:00Z", log)
        rep = open(os.path.join(d, ".reef", "night", "report.md")).read()
        self.assertIn("split 1201 in two?", rep, "the owner reads what was called `process`")
        self.assertNotIn("Mahmoud (proxy, day", rep.split("## Mahmoud's other decisions")[1].split("##")[0], "the night's list is the night's")


if __name__ == "__main__":
    unittest.main()


class Challenge(unittest.TestCase):
    """2026-10-31, the owner: "a CTO who challenges — guardrails that keep him right, not ones that slow him." Mahmoud's CHALLENGE on
    a plan is recorded once per row and the second is the owner's (exit 3) — on disk, so a /clear or a runner restart cannot turn
    one round into a night of rounds; where the contract does not give him `plan`, a challenge is refused like an approval."""

    def challenge(self, d, row="12", text=None):
        p = os.path.join(d, ".reef", "ci-local", f"report-mahmoud-challenge-{row}.md")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text if text is not None else f"RUN: agent=mahmoud day={TODAY} kind=plan question=plan 12\n"
                    "CHALLENGE plan row 12 — three tasks for one screen: over-built — one task, the screen and its test\nVERDICT: DONE\n")
        return subprocess.run([sys.executable, APPROVAL, "--proxy", "--challenge", "--row", row, "--report", os.path.relpath(p, d)],
                              capture_output=True, text=True, cwd=d)

    def test_the_first_challenge_is_recorded_and_carried_the_second_is_the_owners(self):
        d = N.project()
        contract_day(d)
        pm = os.path.join(d, "reef", "proxy.md")
        text = open(pm).read()
        open(pm, "w").write(text.replace("Decides: process, wording", "Decides: process, wording, plan"))
        approve_day(self, d)
        r = self.challenge(d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn("recorded", r.stdout); self.assertIn("once more", r.stdout)
        log = [json.loads(l) for l in open(os.path.join(d, ".reef", "approvals", "day-decisions.jsonl"))]
        self.assertEqual((log[-1]["row"], log[-1]["kind"]), ("12", "challenge")); self.assertIn("one task", log[-1]["want"])
        r = self.challenge(d, text=f"RUN: agent=mahmoud day={TODAY} kind=plan question=plan 12\nCHALLENGE plan row 12 — still two tasks — one\nVERDICT: DONE\n")
        self.assertEqual(r.returncode, 3, r.stdout); self.assertIn("the owner's", r.stdout); self.assertIn("reef-queue.py ask", r.stdout)
        self.assertEqual(sum(1 for l in open(os.path.join(d, ".reef", "approvals", "day-decisions.jsonl")) if '"challenge"' in l), 1, "one record per row")
        r = self.challenge(d, row="3", text=f"RUN: agent=mahmoud day={TODAY} kind=plan question=plan 3\nDECIDE x — y — z\nVERDICT: DONE\n")
        self.assertEqual(r.returncode, 1); self.assertIn("no `CHALLENGE", r.stdout)

    def test_without_plan_in_decides_or_without_the_approval_a_challenge_is_refused(self):
        d = N.project()
        approve_day(self, d)   # the seed: process, wording — no plan
        r = self.challenge(d)
        self.assertEqual(r.returncode, 1, r.stdout); self.assertIn("does not name `plan`", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(d, ".reef", "approvals", "day-decisions.jsonl")))
        d2 = N.project()
        r = self.challenge(d2)
        self.assertEqual(r.returncode, 1, r.stdout)
        # a running night: its contract governs — no day approval needed
        os.makedirs(os.path.join(d2, ".reef", "night"), exist_ok=True); open(os.path.join(d2, ".reef", "night", "active"), "w").write("x")
        r = self.challenge(d2)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

