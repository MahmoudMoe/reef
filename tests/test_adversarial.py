"""Sabotage suite for the adversarial stage (scripts/reef-adversarial + the guard's
adversarial-plan check) and for scripts/reef-claims.py (claims bound to the round's diff,
nothing but claims after GREEN). Every refusal here is a shortcut the pilot took once."""
import json
import os
import re
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

    def test_blocker_none_is_no_blocker(self):
        # 0.7 dogfood: the hunter's live PASS report said "BLOCKER: none." and the record was refused as a
        # contradiction; a design-tier row could not be dispatched without re-running the hunter for wording
        rp = write(self.d, "r.txt", REPORT_PASS.format(p="plan").replace("NONE: tried y", "BLOCKER: none.\nNONE: tried y"))
        r = adv(self.t, "plan", rp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("adversarial-plan", fm_of(self.t))
        # first contact (2026-10-16): "BLOCKER: none found." was refused as a hole and the hunter re-sent its report for wording
        for wording in ("BLOCKER: none found.", "BLOCKER: None — every hole is a NEW-ROW", "BLOCKER: no blockers here"):
            with self.subTest(wording=wording):
                rp = write(self.d, "r2.txt", REPORT_PASS.format(p="plan").replace("NONE: tried y", wording + "\nNONE: tried y"))
                self.assertEqual(adv(self.t, "plan", rp).returncode, 0, wording)
        rp = write(self.d, "r3.txt", REPORT_PASS.format(p="plan").replace("NONE: tried y", "BLOCKER: nonexistent key is accepted\nNONE: tried y"))
        self.assertEqual(adv(self.t, "plan", rp).returncode, 2, "a hole that merely starts with 'none…' is still a hole")

    def test_refuses_wrong_pass_fail_and_blocker(self):
        cases = [
            (REPORT_PASS.format(p="guard"), "not 'plan'"),
            (REPORT_PASS.format(p="plan").replace("VERDICT: PASS", "VERDICT: FAIL"), "FAIL is not recorded"),
            (REPORT_PASS.format(p="plan").replace("NONE: tried y", "BLOCKER: hole — will happen"), "contradiction"),
            # a hole written in markdown bold is still a hole (seen live in the 0.7 eval runs)
            (REPORT_PASS.format(p="plan").replace("NONE: tried y", "**BLOCKER:** the heredoc stripper eats the line"), "contradiction"),
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


class NotesOutsideTheHash(unittest.TestCase):
    def test_reviewer_notes_do_not_change_the_plan_hash(self):
        # 2026-10-18: notes added after the hunter's pass changed adversarial-plan; the orchestrator reverted the notes to match
        d = tempfile.mkdtemp(prefix="reef-adv.")
        p = task(d)
        before = adv(p, "plan-hash").stdout.strip()
        with open(p) as f:
            t = f.read()
        with open(p, "w") as f:
            f.write(t.replace("## Log\n", "## Reviewer notes\n- (plan review A3) a cast is refused only by AC-5's grep\n\n## Log\n- attempt 1\n"))
        self.assertEqual(adv(p, "plan-hash").stdout.strip(), before)
        with open(p, "w") as f:
            f.write(t.replace("## Scope\nthe defect", "## Scope\nthe defect, widened"))
        self.assertNotEqual(adv(p, "plan-hash").stdout.strip(), before, "plan text still counts")


def legacy_hash(path):
    """The 0.6 form of the stamp (cut at ## Log, so the Reviewer notes were inside it), computed here, not by the script."""
    import hashlib
    with open(path, encoding="utf-8", newline="") as f:
        t = f.read()
    t = re.split(r"^##[ \t]+[Ll][Oo][Gg][ \t]*$", t, maxsplit=1, flags=re.M)[0]
    m = re.match(r"\A---\r?\n(.*?\r?\n)---\r?\n", t, re.S)
    fm = re.sub(r"^(status|attempts|last_failure_sig|dispatches|worktree|adversarial-plan|adversarial-guard|adversarial-decided):.*(?:\r?\n|\Z)", "", m.group(1), flags=re.M)
    return hashlib.sha1((fm + t[m.end(1):]).encode("utf-8")).hexdigest()[:12]


class MigrateTheStamp(unittest.TestCase):
    """2026-10-18 (qassimha, task 204): the cut moved to ## Reviewer notes (fda6801) and the stamp written the day before,
    with the notes inside it, read as "the plan changed" — a round the cap forbids, over a plan nobody touched."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-adv-migrate.")
        os.makedirs(os.path.join(self.d, ".reef"))
        write(self.d, ".reef/config.json", '{"gates": {"test": "true"}}')
        self.t = task(self.d)
        with open(self.t) as f:
            t = f.read()
        with open(self.t, "w") as f:   # a plan with notes, stamped in the 0.6 form by hand (what the old script wrote)
            f.write(t.replace("## Log\n", "## Reviewer notes\n- (plan review A3) a cast is refused only by AC-5's grep\n\n## Log\n")
                    .replace("dispatches: 0\n", "dispatches: 0\nadversarial-plan: LEGACY\n"))
        self.legacy = legacy_hash(self.t)
        self.restamp(self.legacy)
        self.assertNotEqual(self.legacy, adv(self.t, "plan-hash").stdout.strip(), "the fixture must be a stamp the new cut rejects")

    def restamp(self, value):
        with open(self.t) as f:
            t = f.read()
        with open(self.t, "w") as f:
            f.write(re.sub(r"^adversarial-plan: .*$", f"adversarial-plan: {value}", t, flags=re.M))

    def test_guard_denial_names_migrate_and_migrate_unblocks_without_a_round(self):
        r = dispatch(self.d, self.t)
        self.assertEqual(r.returncode, 2)
        self.assertIn("plan --migrate", r.stderr, "the denial must name the re-stamp, not a hunter round the cap forbids")
        self.assertIn(f"python3 {ADV} ", r.stderr, "the plugin's copy: a feature worktree's scripts/ has no --migrate until the next merge")
        self.assertNotIn("run the hunter again", r.stderr)
        r = adv(self.t, "plan", "--migrate")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"{self.legacy} → {adv(self.t, 'plan-hash').stdout.strip()}", r.stdout)
        self.assertIn(f"adversarial-plan: {adv(self.t, 'plan-hash').stdout.strip()}", fm_of(self.t))
        self.assertNotIn("adversarial-decided", fm_of(self.t), "a migration is not an owner ruling")
        self.assertEqual(dispatch(self.d, self.t).returncode, 0)

    def test_current_stamp_is_a_no_op_and_the_file_is_untouched(self):
        self.restamp(adv(self.t, "plan-hash").stdout.strip())
        with open(self.t, "rb") as f:
            before = f.read()
        r = adv(self.t, "plan", "--migrate")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("nothing to migrate", r.stdout)
        with open(self.t, "rb") as f:
            self.assertEqual(f.read(), before)

    def test_a_changed_plan_is_refused_as_not_a_migration(self):
        with open(self.t) as f:
            t = f.read()
        with open(self.t, "w") as f:
            f.write(t.replace("## Scope\nthe defect", "## Scope\nthe defect, widened after the pass"))
        with open(self.t, "rb") as f:
            before = f.read()
        r = adv(self.t, "plan", "--migrate")
        self.assertEqual(r.returncode, 2, "an edited plan must not be re-stamped by a migration")
        self.assertIn("not a migration", r.stderr)
        self.assertIn("--decided", r.stderr)
        with open(self.t, "rb") as f:
            self.assertEqual(f.read(), before)
        r = dispatch(self.d, self.t)
        self.assertEqual(r.returncode, 2)
        self.assertIn("run the hunter again", r.stderr)
        self.assertNotIn("--migrate", r.stderr, "a stamp that matches neither form is a changed plan, not a 0.6 stamp")

    def test_no_stamp_and_a_forged_stamp_are_refused(self):
        with open(self.t) as f:
            t = f.read()
        with open(self.t, "w") as f:
            f.write(re.sub(r"^adversarial-plan: .*\n", "", t, flags=re.M))
        r = adv(self.t, "plan", "--migrate")
        self.assertEqual(r.returncode, 2)
        self.assertIn("run the hunter", r.stderr)
        self.restamp("000000000000")
        self.assertEqual(adv(self.t, "plan", "--migrate").returncode, 2)


class PlanRoundCap(unittest.TestCase):
    """0.7 / v2: the plan pass is capped (hunter.plan_rounds, default 2). 2026-10-17: rows 2 and 13 reached round 6."""

    def report(self, d, rnd, suffix=""):
        return write(d, f"r{rnd}.md", f"RUN: agent=loophole-hunter task=1 pass=plan {suffix or f'round={rnd}'}\nDEFECT: x\nBLOCKER: none\nVERDICT: PASS\n")

    def test_round_three_is_refused_and_round_two_recorded(self):
        d = tempfile.mkdtemp(prefix="reef-adv.")
        p = task(d)
        self.assertEqual(adv(p, "plan", self.report(d, 2)).returncode, 0)
        r = adv(p, "plan", self.report(d, 3))
        self.assertEqual(r.returncode, 2)
        self.assertIn("round 3 > hunter.plan_rounds 2", r.stderr)
        self.assertIn("--decided", r.stderr)
        r = adv(p, "plan", self.report(d, 5, "(round 5)"))
        self.assertEqual(r.returncode, 2, "the parenthesised spelling seen live counts too")
        self.assertEqual(adv(p, "plan", write(d, "r0.md", "RUN: agent=loophole-hunter task=1 pass=plan\nBLOCKER: none\nVERDICT: PASS\n")).returncode, 0,
                         "no round on the RUN line = round 1 (older reports)")

    def test_cap_from_config_and_zero_means_none(self):
        d = tempfile.mkdtemp(prefix="reef-adv.")
        p = task(d)
        os.makedirs(os.path.join(d, ".reef"))
        with open(os.path.join(d, ".reef", "config.json"), "w") as f:
            json.dump({"hunter": {"plan_rounds": 3}}, f)
        self.assertEqual(adv(p, "plan", self.report(d, 3)).returncode, 0)
        self.assertEqual(adv(p, "plan", self.report(d, 4)).returncode, 2)
        with open(os.path.join(d, ".reef", "config.json"), "w") as f:
            json.dump({"hunter": {"plan_rounds": 0}}, f)
        self.assertEqual(adv(p, "plan", self.report(d, 9)).returncode, 0)

    def test_decided_restamps_without_a_round_and_stays_outside_the_hash(self):
        d = tempfile.mkdtemp(prefix="reef-adv.")
        p = task(d)
        self.assertNotEqual(adv(p, "plan", "--decided", "³⁰").returncode, 0, "a decision replaces a re-check, never the first pass")
        self.assertEqual(adv(p, "plan", self.report(d, 1)).returncode, 0)
        with open(p) as f:
            t = f.read()
        with open(p, "w") as f:
            f.write(t.replace("## Scope\nthe defect", "## Scope\nthe defect, as the owner ruled"))
        stamped = re.search(r"^adversarial-plan: (\w+)", t, re.M).group(1)
        self.assertNotEqual(adv(p, "plan-hash").stdout.strip(), stamped, "the edit staled the stamp")
        r = adv(p, "plan", "--decided", "³⁰")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(p) as f:
            t2 = f.read()
        self.assertIn("adversarial-decided: ³⁰", t2)
        self.assertEqual(re.search(r"^adversarial-plan: (\w+)", t2, re.M).group(1), adv(p, "plan-hash").stdout.strip())
        before = adv(p, "plan-hash").stdout.strip()
        with open(p, "w") as f:
            f.write(t2.replace("adversarial-decided: ³⁰\n", ""))
        self.assertEqual(adv(p, "plan-hash").stdout.strip(), before, "the decided key is an execution key, outside the plan hash")
