"""Workflow v3, phase 6 — the proxy by day: the owner approves `reef/proxy.md` (what Mahmoud decides by day: process and
wording) once at its digest; in the day loop a question of those kinds goes to the proxy, and his decision is written as
a labelled footnote by `reef-approval.py --proxy --day` from his own report — never typed by the orchestrator (the guard
refuses the label by hand); product, money, data, look, security and the release stay the owner's; the batch counts the
owner's questions and the proxy's day decisions."""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import test_night as N   # noqa: E402  (the night fixture: owner.md, a queue with rows 12 and 3, feature folders)
import test_guard as G   # noqa: E402  (the guard's Bash runner)
RUN = os.path.join(ROOT, "scripts", "reef-run.py")
APPROVAL = os.path.join(ROOT, "scripts", "reef-approval.py")
COST = os.path.join(ROOT, "scripts", "reef-cost.py")
REPORT = ("RUN: agent=mahmoud day=2026-10-26 kind={kind} question=split 1201 in two?\n"
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


def decide(d, kind="process", row="12", report=".reef/ci-local/report-mahmoud-day-12.md", text=None):
    p = os.path.join(d, report)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(text if text is not None else REPORT.format(kind=kind))
    return subprocess.run([sys.executable, APPROVAL, "--proxy", "--day", "--kind", kind, "--row", row, "--report", report],
                          capture_output=True, text=True, cwd=d)


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
        # the same question, answered otherwise, approves nothing
        os.unlink(os.path.join(d, ".reef", "approvals", "day.json"))
        N.hook(d, q, label="Edit")
        self.assertFalse(os.path.exists(os.path.join(d, ".reef", "approvals", "day.json")))
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

    def test_a_process_decision_becomes_the_proxys_labelled_footnote_and_a_record(self):
        r = decide(self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        q = open(os.path.join(self.d, "reef", "queue.md")).read()
        self.assertIn("Mahmoud (proxy, day 2026-10-26, process): no, keep one task — the slice is small", q)
        self.assertRegex(q, r"\|\s*12\s*\|[^\n]*¹\s*\|", "the footnote mark on row 12")
        log = [json.loads(l) for l in open(os.path.join(self.d, ".reef", "approvals", "day-decisions.jsonl"))]
        self.assertEqual((log[0]["row"], log[0]["kind"]), ("12", "process"))
        self.assertIn("split 1201 in two?", log[0]["question"])

    def test_the_owners_kinds_a_wait_a_foreign_report_and_no_approval_write_nothing(self):
        r = decide(self.d, kind="product")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("the owner's", r.stdout)
        r = decide(self.d, text="RUN: agent=mahmoud day=2026-10-26 kind=process question=x\nWAIT x — the owner kept it (footnote 3)\nVERDICT: DONE\n")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("WAIT", r.stdout); self.assertIn("reef-queue.py ask", r.stdout)
        r = decide(self.d, report="notes.md")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("Mahmoud's own file", r.stdout)
        r = decide(self.d, text="RUN: agent=mahmoud night=2026-10-26\nAPPROVE plan share-links at 0000000000000000 — x\nVERDICT: DONE\n")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertNotIn("Mahmoud (proxy, day", open(os.path.join(self.d, "reef", "queue.md")).read())
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "approvals", "day-decisions.jsonl")))
        os.unlink(os.path.join(self.d, ".reef", "approvals", "day.json"))
        r = decide(self.d)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("no .reef/approvals/day.json", r.stdout)


class DayGuard(unittest.TestCase):
    def test_the_day_label_is_never_typed_by_hand_while_the_night_label_stays_the_orchestrators(self):
        r = G.bash('python3 scripts/reef-queue.py footnote "Mahmoud (proxy, day 2026-10-26, process): keep one task — small" --row 12')
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("--proxy --day", r.stderr)
        r = G.bash('python3 scripts/reef-queue.py footnote "Mahmoud (proxy, night 2026-10-26): keep one task — small" --row 12')
        self.assertEqual(r.returncode, 0, r.stderr)
        r = G.bash('python3 scripts/reef-queue.py footnote "the owner: keep one task" --row 12')
        self.assertEqual(r.returncode, 0, r.stderr)


class DayNumbers(unittest.TestCase):
    def test_the_batch_counts_the_owners_questions_and_the_proxys_day_decisions(self):
        d = N.project()
        approve_day(self, d)
        q = os.path.join(d, "scripts", "reef-queue.py")
        os.makedirs(os.path.dirname(q), exist_ok=True)
        subprocess.run(["cp", os.path.join(ROOT, "scripts", "reef-queue.py"), q], check=True)
        subprocess.run([sys.executable, q, "footnote", "Owner: ship it as one task", "--row", "12", "--repo", d], check=True, capture_output=True)
        self.assertEqual(decide(d).returncode, 0)
        N.L.git(d, "add", "-A"); N.L.git(d, "commit", "-qm", "two footnotes")
        r = subprocess.run([sys.executable, COST, "rows", "--repo", d, "--since", "2026-01-01", "--format", "json"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        b = json.loads(r.stdout)["batch"]
        self.assertEqual((b["owner_questions"], b["proxy_day_decisions"]), (1, 1))
        loader = importlib.machinery.SourceFileLoader("reef_run", RUN)
        spec = importlib.util.spec_from_loader(loader.name, loader)
        run = importlib.util.module_from_spec(spec)
        loader.exec_module(run)
        table = "\n".join(run.numbers_table(None, None))
        self.assertIn("Owner questions", table); self.assertIn("proxy by day", table)


if __name__ == "__main__":
    unittest.main()
