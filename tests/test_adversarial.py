"""Sabotage suite for the adversarial stage (scripts/reef-adversarial + the guard's
adversarial-plan check) and for scripts/reef-claims.py (claims bound to the round's diff,
nothing but claims after GREEN). Every refusal here is a shortcut the pilot took once."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, "scripts", "reef-guard.py")
ADV = os.path.join(ROOT, "scripts", "reef-adversarial")
CLAIMS = os.path.join(ROOT, "scripts", "reef-claims.py")

REPORT_PASS = "RUN: agent=loophole-hunter task=1 pass={p}\nDEFECT: x\nNONE: tried y\nVERDICT: PASS\n"


def task(d, tier="design", complexity="design", extra=""):
    p = os.path.join(d, "tasks", "001-t.md")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(f"---\nid: 1\nfeature: demo\nstatus: pending\ncomplexity: {complexity}\neffort: medium\n"
                f"blocked-by: []\nresources: []\ntier: {tier}\nverify: judge\nattempts: 0\ndispatches: 0\n"
                f"last_failure_sig: \"\"\n{extra}---\n# 1\n\n## Scope\nthe defect\n\n## Decision\nhuman wrote this\n\n"
                f"## Acceptance Criteria\n- test_x goes red first\n\n## Log\n")
    return p


def write(d, name, text):
    p = os.path.join(d, name)
    with open(p, "w") as f:
        f.write(text)
    return p


def adv(*args):
    return subprocess.run([sys.executable, ADV, *args], capture_output=True, text=True)


def dispatch(cwd, path):
    return subprocess.run([sys.executable, GUARD], input=json.dumps(
        {"tool_name": "Task", "cwd": cwd,
         "tool_input": {"subagent_type": "reef:implementer", "prompt": f"REEF-TASK: {path}\nimplement"}}),
        capture_output=True, text=True)


def fm_of(path):
    with open(path) as f:
        return f.read().split("---\n")[1]


class Record(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-adv.")
        os.makedirs(os.path.join(self.d, ".reef"))
        write(self.d, ".reef/config.json", '{"gates": {"test": "true"}}')
        self.t = task(self.d)
        self.ok = write(self.d, "plan.txt", REPORT_PASS.format(p="plan"))

    def test_records_plan_pass_bound_to_plan_content(self):
        r = adv(self.t, "plan", self.ok)
        self.assertEqual(r.returncode, 0, r.stderr)
        h = adv(self.t, "plan-hash").stdout.strip()
        self.assertIn(f"adversarial-plan: {h}", fm_of(self.t))

    def test_refuses_mech_and_light(self):
        t = task(self.d, tier="light", complexity="mech")
        r = adv(t, "plan", self.ok)
        self.assertEqual(r.returncode, 2)
        self.assertIn("never runs on a mech", r.stderr)

    def test_refuses_wrong_pass_fail_and_blocker(self):
        cases = [
            (REPORT_PASS.format(p="guard"), "not 'plan'"),
            (REPORT_PASS.format(p="plan").replace("VERDICT: PASS", "VERDICT: FAIL"), "FAIL is not recorded"),
            (REPORT_PASS.format(p="plan").replace("NONE: tried y", "BLOCKER: hole — will happen"), "contradiction"),
            ("RUN: agent=verifier task=1\nVERDICT: PASS\n", "loophole-hunter"),
            (REPORT_PASS.format(p="plan").replace("VERDICT: PASS\n", ""), "no VERDICT"),
        ]
        for text, msg in cases:
            with self.subTest(msg=msg):
                rp = write(self.d, "r.txt", text)
                r = adv(self.t, "plan", rp)
                self.assertEqual(r.returncode, 2, f"{msg}: wrongly recorded")
                self.assertIn(msg, r.stderr)
                self.assertNotIn("adversarial-plan", fm_of(self.t))

    def test_guard_pass_needs_plan_pass_first(self):
        g = write(self.d, "g.txt", REPORT_PASS.format(p="guard"))
        r = adv(self.t, "guard", g)
        self.assertEqual(r.returncode, 2)
        self.assertIn("plan pass comes first", r.stderr)
        adv(self.t, "plan", self.ok)
        r = adv(self.t, "guard", g)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("adversarial-guard: ", fm_of(self.t))


class GuardRequiresPlanPass(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-adv-guard.")
        os.makedirs(os.path.join(self.d, ".reef"))
        write(self.d, ".reef/config.json", '{"gates": {"test": "true"}}')
        self.t = task(self.d)

    def test_design_tier_without_pass_denied(self):
        r = dispatch(self.d, self.t)
        self.assertEqual(r.returncode, 2, "a tier: design task reached an implementer with no adversarial pass")
        self.assertIn("adversarial-plan", r.stderr)

    def test_fresh_pass_allows_edited_plan_denies(self):
        adv(self.t, "plan", write(self.d, "p.txt", REPORT_PASS.format(p="plan")))
        self.assertEqual(dispatch(self.d, self.t).returncode, 0)
        with open(self.t) as f:
            text = f.read()
        with open(self.t, "w") as f:
            f.write(text.replace("## Scope\nthe defect", "## Scope\na different defect"))
        r = dispatch(self.d, self.t)
        self.assertEqual(r.returncode, 2, "the plan changed after the pass — the pass is void")
        self.assertIn("plan changed", r.stderr)

    def test_execution_state_does_not_void_the_pass(self):
        adv(self.t, "plan", write(self.d, "p.txt", REPORT_PASS.format(p="plan")))
        self.assertEqual(dispatch(self.d, self.t).returncode, 0)   # writes in-progress + dispatches
        self.assertEqual(dispatch(self.d, self.t).returncode, 0, "the guard's own writes voided the pass")

    def test_full_tier_needs_no_pass(self):
        t = task(self.d, tier="full")
        self.assertEqual(dispatch(self.d, t).returncode, 0)

    def test_forged_record_denied(self):
        t = task(self.d, extra="adversarial-plan: 000000000000\n")
        r = dispatch(self.d, t)
        self.assertEqual(r.returncode, 2, "a hand-written record must not pass as a real pass")


class Claims(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-claims.")
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        write(self.d, "a.py", "x = 1\ny = 2\n")
        os.makedirs(os.path.join(self.d, "docs"))
        write(self.d, "docs/n.md", "notes\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").stdout.strip()

    def git(self, *a):
        return subprocess.run(["git", "-C", self.d, *a], capture_output=True, text=True)

    def commit(self, msg="round"):
        self.git("add", "-A")
        self.git("commit", "-qm", msg)
        return self.git("rev-parse", "HEAD").stdout.strip()

    def claims(self, *args):
        return subprocess.run([sys.executable, CLAIMS, "--repo", self.d, *args], capture_output=True, text=True)

    def test_claim_inside_the_round_passes_outside_fails(self):
        write(self.d, "a.py", "x = 1\ny = 3\nz = 4\n")
        head = self.commit()
        rng = f"{self.base}..{head}"
        good = write(self.d, "c.txt", "y is now 3 — true at a.py:2\nz added — true at a.py:3\n")
        self.assertEqual(self.claims("check", rng, good).returncode, 0)
        bad = write(self.d, "c.txt", "x unchanged — true at a.py:1\nnotes say so — true at docs/n.md:1\n")
        r = self.claims("check", rng, bad)
        self.assertEqual(r.returncode, 1, "claims naming lines the round did not add must be rejected")
        self.assertIn("a.py:1", r.stdout)
        self.assertIn("did not change docs/n.md", r.stdout)

    def test_malformed_and_empty_lists_rejected(self):
        write(self.d, "a.py", "x = 1\ny = 3\n")
        head = self.commit()
        rng = f"{self.base}..{head}"
        r = self.claims("check", rng, write(self.d, "c.txt", "trust me, it works\n"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a claim", r.stdout)
        r = self.claims("check", rng, write(self.d, "c.txt", "\n"))
        self.assertEqual(r.returncode, 1, "an empty list after a round that added lines is not a claims list")

    def test_claims_only_after_green(self):
        write(self.d, "a.py", "x = 1\n# explained why\ny = 2\n")
        write(self.d, "docs/n.md", "notes\nmore notes\n")
        head = self.commit()
        r = self.claims("claims-only", f"{self.base}..{head}")
        self.assertEqual(r.returncode, 0, r.stdout)
        write(self.d, "a.py", "x = 1\n# explained why\ny = 5\n")
        head2 = self.commit()
        r = self.claims("claims-only", f"{head}..{head2}")
        self.assertEqual(r.returncode, 1, "a code line after GREEN must be refused")
        self.assertIn("a.py", r.stdout)

    def test_claims_only_sees_a_deleted_code_line(self):
        write(self.d, "a.py", "x = 1\n")
        head = self.commit()
        r = self.claims("claims-only", f"{self.base}..{head}")
        self.assertEqual(r.returncode, 1, "removing code is a code change too")


if __name__ == "__main__":
    unittest.main()
