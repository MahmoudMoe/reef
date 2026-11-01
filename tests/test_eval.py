"""Sabotage suite for tests/eval/reef-eval (decision 4: no agent prompt change without the eval).

The live run needs the CLI and credentials and never runs in CI. What CI proves is the MECHANICAL half:
the verdict parser, the truth comparison, the metrics and the comparison rule, replayed over fixture
reports. `tests/eval/fixtures/good/` holds reports aligned with the corpus truth; `trusting/` holds what
an agent whose file was edited to "trust the hand-off" produces (it repeats the hand-off's claims) —
scoring it must show a dropped catch-rate and `compare` must refuse it. Every corpus entry must build
into a worktree whose gate is green (the defect hides behind a green suite, or there is nothing to catch)."""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL = os.path.join(ROOT, "tests", "eval", "reef-eval")
FIX = os.path.join(ROOT, "tests", "eval", "fixtures")
AGENTS = ("verifier", "hunter", "plan-reviewer", "acceptance")


def load_eval():
    loader = importlib.machinery.SourceFileLoader("reef_eval", EVAL)
    spec = importlib.util.spec_from_loader("reef_eval", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def run(*args):
    return subprocess.run([sys.executable, EVAL, *args], capture_output=True, text=True)


class Parser(unittest.TestCase):
    def setUp(self):
        self.ev = load_eval()

    def test_last_verdict_wins_and_blocking_lines_collected(self):
        report = "RUN: agent=verifier task=4\nRULE AC1: PASS iff x\nAC1 FAIL — core.py:7 raises\nVERDICT: PASS\n(amended after re-run)\nVERDICT: FAIL\nBLOCKER: a hole — fix: y\n"
        verdict, blocking = self.ev.parse(report)
        self.assertEqual(verdict, "FAIL")
        self.assertEqual(len(blocking), 2)
        self.assertTrue(any(b.startswith("AC1 FAIL") for b in blocking))
        self.assertTrue(any(b.startswith("BLOCKER:") for b in blocking))

    def test_rule_lines_are_not_blocking_findings(self):
        # "RULE AC1: PASS iff …; FAIL if …" names FAIL but is a rule, not a finding
        _, blocking = self.ev.parse("RULE AC1: PASS iff the test exists; FAIL if it does not\nVERDICT: PASS\n")
        self.assertEqual(blocking, [])

    def test_unparsed_report_is_counted_not_caught(self):
        entry = {"id": "x", "truth": {"verdict": "FAIL", "blockers": ["hole"]}}
        row = self.ev.judge(entry, "I think it is fine.")
        self.assertIsNone(row["verdict"])
        self.assertFalse(row["caught"])
        self.assertEqual(self.ev.metrics([row])["unparsed"], 1)

    def test_catch_needs_fail_and_every_truth_blocker(self):
        entry = {"id": "x", "truth": {"verdict": "FAIL", "blockers": ["-n|short", "nohup"]}}
        self.assertFalse(self.ev.judge(entry, "BLOCKER: short -n passes\nVERDICT: FAIL\n")["caught"], "one of two blockers named")
        self.assertTrue(self.ev.judge(entry, "BLOCKER: short -n passes\nBLOCKER: nohup git passes\nVERDICT: FAIL\n")["caught"])
        self.assertFalse(self.ev.judge(entry, "BLOCKER: short -n passes\nBLOCKER: nohup\nVERDICT: PASS\n")["caught"], "a PASS verdict never counts as a catch")


    def test_green_is_the_acceptance_reviewers_pass(self):
        # agents/acceptance.md ends its report `VERDICT: GREEN | FAIL`; GREEN scores as PASS
        verdict, _ = self.ev.parse("HEAD: 0123456789ab\nFR-1 PASS — test_x\nVERDICT: GREEN\n")
        self.assertEqual(verdict, "PASS")

    def test_a_nit_is_caught_only_on_a_pass_naming_every_truth_nit(self):
        # step 2 of docs/review/squid-adoption-plan-2026-11-01.md: an over-built but correct diff is a NIT, never a blocker
        entry = {"id": "x", "truth": {"verdict": "PASS", "blockers": [], "nits": ["abstract|registry"]}}
        self.assertTrue(self.ev.judge(entry, "NIT: unused Exporter abstract base\nVERDICT: GREEN\n")["nit_caught"])
        self.assertFalse(self.ev.judge(entry, "NIT: README typo\nVERDICT: GREEN\n")["nit_caught"], "the wrong NIT")
        self.assertFalse(self.ev.judge(entry, "BLOCKER: abstract base unused\nVERDICT: FAIL\n")["nit_caught"], "a blocker is a false FAIL, not a NIT")
        self.assertIsNone(self.ev.metrics([self.ev.judge({"id": "y", "truth": {"verdict": "PASS", "blockers": []}}, "VERDICT: PASS")])["nit_rate"],
                          "no entry asks for a NIT: no rate")


class FixtureReplay(unittest.TestCase):
    def test_good_fixtures_score_perfectly(self):
        for agent in AGENTS:
            with self.subTest(agent=agent):
                r = run("score", agent, os.path.join(FIX, "good", agent), "--json")
                self.assertEqual(r.returncode, 0, r.stderr)
                m = json.loads(r.stdout)
                self.assertEqual((m["catch_rate"], m["approve_precision"], m["unparsed"]), (1.0, 1.0, 0), agent)

    def test_trusting_the_handoff_drops_the_catch_rate_and_is_refused(self):
        for agent in AGENTS:
            with self.subTest(agent=agent):
                d = tempfile.mkdtemp(prefix="reef-eval-cmp.")
                good = json.loads(run("score", agent, os.path.join(FIX, "good", agent), "--json").stdout)
                bad = json.loads(run("score", agent, os.path.join(FIX, "trusting", agent), "--json").stdout)
                self.assertLess(bad["catch_rate"], good["catch_rate"], f"{agent}: trusting the hand-off must lose catches")
                if good["nit_rate"] is not None:
                    self.assertEqual(good["nit_rate"], 1.0, f"{agent}: the good fixtures name every truth NIT")
                    self.assertLess(bad["nit_rate"], good["nit_rate"], f"{agent}: a trusting reviewer names no NIT")
                    lost = dict(good, nit_rate=0.0)
                    with open(os.path.join(d, "lost.json"), "w") as f:
                        json.dump(lost, f)
                    self.assertEqual(run("compare", os.path.join(d, "good.json"), os.path.join(d, "lost.json")).returncode, 1,
                                     "a candidate that names fewer truth NITs is refused")
                for name, m in (("good.json", good), ("bad.json", bad)):
                    with open(os.path.join(d, name), "w") as f:
                        json.dump(m, f)
                self.assertEqual(run("compare", os.path.join(d, "good.json"), os.path.join(d, "bad.json")).returncode, 1)
                self.assertEqual(run("compare", os.path.join(d, "good.json"), os.path.join(d, "good.json")).returncode, 0)
                # moving TOWARD truth is allowed: a candidate with the same catch-rate and higher precision passes
                better = dict(good, approve_precision=1.0)
                worse_prec = dict(good, approve_precision=0.5)
                with open(os.path.join(d, "worse.json"), "w") as f:
                    json.dump(worse_prec, f)
                with open(os.path.join(d, "better.json"), "w") as f:
                    json.dump(better, f)
                self.assertEqual(run("compare", os.path.join(d, "worse.json"), os.path.join(d, "better.json")).returncode, 0)
                self.assertEqual(run("compare", os.path.join(d, "better.json"), os.path.join(d, "worse.json")).returncode, 1)

    def test_empty_directory_is_an_error_not_a_pass(self):
        self.assertEqual(run("score", "verifier", tempfile.mkdtemp()).returncode, 1)


class Corpus(unittest.TestCase):
    def test_every_entry_builds_and_its_gate_is_green(self):
        ev = load_eval()
        for agent in AGENTS:
            c = ev.corpus(agent)
            self.assertGreaterEqual(len(c["entries"]), 5, f"{agent}: five to ten entries")
            self.assertTrue(any(e["truth"]["verdict"] == "PASS" for e in c["entries"]), f"{agent}: precision needs a PASS entry")
            for e in c["entries"]:
                with self.subTest(agent=agent, entry=e["id"]):
                    self.assertIn(e["truth"]["verdict"], ("PASS", "FAIL"))
                    if e["truth"]["verdict"] == "FAIL":
                        self.assertTrue(e["truth"]["blockers"], "a FAIL entry names what must be caught")
                    wt = ev.build_worktree(e, agent)
                    try:
                        g = subprocess.run(["sh", "scripts/reef-gate.sh", "full"], cwd=wt, capture_output=True, text=True)
                        self.assertEqual(g.returncode, 0, f"the defect must hide behind a GREEN gate: {g.stderr[-300:]}")
                        if e.get("after"):
                            rng = ["main...HEAD"] if agent == "acceptance" else []
                            diff = subprocess.run(["git", "diff", "--stat", *rng], cwd=wt, capture_output=True, text=True).stdout
                            self.assertTrue(diff.strip(), "the agent judges a non-empty diff")
                        if agent == "acceptance":
                            st = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=wt, capture_output=True, text=True).stdout
                            self.assertEqual(st, "", "the reviewer reads a committed PR head, not a dirty tree")
                            ev_ = subprocess.run([sys.executable, "scripts/reef-evidence.py", "HEAD"], cwd=wt, capture_output=True, text=True)
                            self.assertIn(ev_.returncode, (0, 2), "the reviewer's GATE line comes from reef-evidence.py: " + ev_.stderr[-300:])
                            for k in e["truth"].get("nits", []):
                                self.assertEqual(e["truth"]["verdict"], "PASS", "a NIT entry is a correct diff")
                        if agent == "plan-reviewer":
                            pc = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-plan-check.py"), wt],
                                                capture_output=True, text=True)
                            self.assertEqual(pc.returncode, 0, "the reviewer runs only after plan-check passed:\n" + pc.stdout)
                    finally:
                        shutil.rmtree(wt, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
