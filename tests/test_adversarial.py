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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import stamped, write  # noqa: E402  (the suites' shared fixtures, once)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, "scripts", "reef-guard.py")
ADV = os.path.join(ROOT, "scripts", "reef-adversarial")
CLAIMS = os.path.join(ROOT, "scripts", "reef-claims.py")

REPORT_PASS = "RUN: agent=loophole-hunter task=1 pass={p}\nDEFECT: x\nNONE: tried y\nVERDICT: PASS\n"


def task(d, tier="critical", complexity="design", extra=""):   # 0.7: the plan pass is critical's by default (hunter.plan_pass)
    p = os.path.join(d, "tasks", "001-t.md")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(f"---\nid: 1\nfeature: demo\nstatus: pending\ncomplexity: {complexity}\neffort: medium\n"
                f"blocked-by: []\nresources: []\ntier: {tier}\nverify: judge\nattempts: 0\ndispatches: 0\n"
                f"last_failure_sig: \"\"\n{extra}---\n# 1\n\n## Scope\nthe defect\n\n## Decision\nhuman wrote this\n\n"
                f"## Acceptance Criteria\n- test_x goes red first\n\n## Log\n")
    return p


def adv(*args):
    return subprocess.run([sys.executable, ADV, *args], capture_output=True, text=True)


def dispatch(cwd, path):
    stamped(cwd)   # the subject here is the graph/the plan pass, not the stamp
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

    def test_a_recorded_plan_pass_clears_its_hunters_verifying_marker(self):
        # 2026-10-20 (qassimha 302): the guard writes .reef/verifying/<id> on the hunter's dispatch; after a PLAN pass
        # nothing removed it, and the tick showed `in flight: verifying:302` for a hunter that had long returned
        import json as _json
        os.makedirs(os.path.join(self.d, ".reef", "verifying"), exist_ok=True)
        mk = lambda tid, path: write(self.d, f".reef/verifying/{tid}", _json.dumps({"id": tid, "task": os.path.abspath(path), "tier": "critical"}))
        mine, other = mk("1", self.t), mk("9", os.path.join(self.d, "tasks", "009-other.md"))
        r = adv(self.t, "plan", self.ok)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("verifying marker cleared", r.stdout)
        self.assertFalse(os.path.exists(mine), "the plan pass is over once recorded")
        self.assertTrue(os.path.exists(other), "another task's marker is not this record's")
        # the code pass keeps the orchestrator's rm: the verifier shares that marker and may still be reading
        mine = mk("1", self.t)
        adv(self.t, "guard", write(self.d, "g.txt", REPORT_PASS.format(p="guard")))
        self.assertTrue(os.path.exists(mine), "a guard-pass record leaves the shared marker alone")
        # the owner's ruling at the gate ends the plan pass too
        self.assertEqual(adv(self.t, "plan", "--decided", "⁵⁰").returncode, 0)
        self.assertFalse(os.path.exists(mine))

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
        self.assertEqual(r.returncode, 2, "a tier: critical task reached an implementer with no adversarial pass")
        self.assertIn("adversarial-plan", r.stderr)

    def test_plan_pass_is_critical_only_by_default_and_design_on_request(self):
        # 0.7 (2026-10-17/18): the plan hunter's rounds were the planning sessions' cost; a design task gets the plan reviewer
        t = task(self.d, tier="design")
        self.assertEqual(dispatch(self.d, t).returncode, 0, "a design task needs no hunter plan pass by default")
        write(self.d, ".reef/config.json", '{"gates": {"test": "true"}, "hunter": {"plan_pass": "design"}}')
        r = dispatch(self.d, t)
        self.assertEqual(r.returncode, 2, "hunter.plan_pass design: the 0.6 behaviour")
        self.assertIn("adversarial-plan", r.stderr)

    def test_a_review_rollup_needs_no_plan_pass(self):
        # the owner's go, 2026-10-24: qassimha's R4 rollup took three hunter plan rounds before its fix could start
        with open(self.t) as f:
            text = f.read()
        r_path = os.path.join(os.path.dirname(self.t), "R01-t.md")
        with open(r_path, "w") as f:
            f.write(text.replace("id: 1\n", "id: R01\n").replace("# 1\n", "# R01\n"))
        r = dispatch(self.d, r_path)   # the planned task stays: a rollup is never stamped, its feature's stamp is its tasks'
        self.assertNotIn("adversarial-plan", r.stderr, "a critical rollup is not held for the hunter's plan pass")
        self.assertEqual(r.returncode, 0, r.stderr)

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


class FeatureGuardPass(unittest.TestCase):
    """0.7 hunter.guard_pass = feature (2026-10-18: two judges, 96k, 20 lines): ONE guard pass on the feature's diff,
    recorded on every design/critical task of the feature, open and done; light tasks untouched; the plan pass first."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-adv-feature.")
        os.makedirs(os.path.join(self.d, ".reef"))
        write(self.d, ".reef/config.json", '{"gates": {"test": "true"}, "hunter": {"guard_pass": "feature"}, "paths": {"features": "reef/features"}}')
        self.tasks = os.path.join(self.d, "reef", "features", "demo", "tasks")
        os.makedirs(os.path.join(self.tasks, "done"))
        def t(name, tier, cx, extra=""):
            p = os.path.join(self.tasks, name)
            tid = re.search(r"(\d+)-", os.path.basename(name)).group(1).lstrip("0")
            with open(p, "w") as f:
                f.write(f"---\nid: {tid}\nfeature: demo\nstatus: pending\ncomplexity: {cx}\neffort: medium\nblocked-by: []\n"
                        f"resources: []\ntier: {tier}\nverify: judge\nattempts: 0\ndispatches: 0\nlast_failure_sig: \"\"\n{extra}---\n# x\n\n## Scope\nx\n\n## Log\n")
            return p
        self.p1 = t("001-a.md", "critical", "design", "adversarial-plan: aaaaaaaaaaaa\n")
        self.p2 = t("002-b.md", "light", "mech")
        self.p3 = t("done/003-c.md", "design", "design", "adversarial-plan: bbbbbbbbbbbb\n")
        self.report = write(self.d, "guard.md", "RUN: agent=loophole-hunter task=1 pass=guard\nDEFECT: x\nBLOCKER: none\nVERDICT: PASS\n")

    def run_in(self, *args):
        return subprocess.run([sys.executable, ADV, *args], capture_output=True, text=True, cwd=self.d)

    def test_one_pass_stamps_every_design_or_critical_task_and_light_stays(self):
        r = self.run_in("--feature", "demo", "guard", self.report)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("on 2 task(s) of demo: 1, 3", r.stdout)
        v1 = re.search(r"^adversarial-guard: (\S+)", fm_of(self.p1), re.M).group(1)
        self.assertEqual(v1, re.search(r"^adversarial-guard: (\S+)", fm_of(self.p3), re.M).group(1), "one record, one value")
        self.assertNotIn("adversarial-guard", fm_of(self.p2))

    def test_refuses_a_plan_report_an_unhunted_plan_and_a_feature_without_judged_tasks(self):
        r = self.run_in("--feature", "demo", "guard", write(self.d, "p.md", REPORT_PASS.format(p="plan")))
        self.assertEqual(r.returncode, 2)
        self.assertIn("not 'guard'", r.stderr)
        with open(self.p1) as f:
            t = f.read()
        with open(self.p1, "w") as f:
            f.write(t.replace("adversarial-plan: aaaaaaaaaaaa\n", ""))
        r = self.run_in("--feature", "demo", "guard", self.report)
        self.assertEqual(r.returncode, 2)
        self.assertIn("plan pass comes first", r.stderr)
        self.assertNotIn("adversarial-guard", fm_of(self.p3), "nothing stamped when one task refuses")
        r = self.run_in("--feature", "other", "guard", self.report)
        self.assertEqual(r.returncode, 2)
        self.assertIn("no task of tier design or critical", r.stderr)

    def test_complexity_design_at_tier_full_needs_no_guard_pass_and_says_why(self):
        # 2026-10-24, the trial's row 18: task 1801 was complexity: design, tier: full; the orchestrator read "a design
        # task" as the complexity, found the pass unrecordable, and filed a found row against the project for it
        tdir = os.path.join(self.d, "reef", "features", "upload", "tasks")
        os.makedirs(tdir)
        with open(os.path.join(tdir, "001-u.md"), "w") as f:
            f.write("---\nid: 1\nfeature: upload\nstatus: done\ncomplexity: design\ntier: full\nverify: judge\n---\n# u\n")
        r = self.run_in("--feature", "upload", "guard", self.report)
        self.assertEqual(r.returncode, 2)
        self.assertIn("its `tier:`, not its `complexity:`", r.stderr)
        self.assertIn("no guard pass is required", r.stderr)
        review = open(os.path.join(ROOT, "skills", "reef-review", "SKILL.md"), encoding="utf-8").read()
        self.assertIn("a task of tier `design` or `critical` (its `tier:`, not its `complexity:`)", review)


class PlanRoundCap(unittest.TestCase):
    """0.7 / v2: the plan pass is capped (hunter.plan_rounds, default 2). 2026-10-17: rows 2 and 13 reached round 6."""

    def report(self, d, rnd, suffix=""):
        return write(d, f"r{rnd}.md", f"RUN: agent=loophole-hunter task=1 pass=plan {suffix or f'round={rnd}'}\nDEFECT: x\nBLOCKER: none\nVERDICT: PASS\n")

    def failed(self, d, rnd):
        return write(d, f"f{rnd}.md", f"RUN: agent=loophole-hunter task=1 pass=plan round={rnd}\nDEFECT: x\nBLOCKER: a hole\nVERDICT: FAIL\n")

    def test_a_pass_records_at_any_round_and_a_fail_at_the_cap_goes_to_the_owner(self):
        # 2026-10-21 (qassimha R4): the round-3 PASS was refused at cap 2 and the only way out was a config change; the
        # cap meant "no further round after a FAIL", and it threw a PASS away instead
        d = tempfile.mkdtemp(prefix="reef-adv.")
        p = task(d)
        r = adv(p, "plan", self.failed(d, 1))
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("--decided", r.stderr, "below the cap a FAIL means fix and re-check")
        r = adv(p, "plan", self.failed(d, 2))
        self.assertEqual(r.returncode, 2)
        self.assertIn("round 2 FAILED at hunter.plan_rounds 2", r.stderr)
        self.assertIn("--decided", r.stderr)
        r = adv(p, "plan", self.report(d, 3))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("above hunter.plan_rounds 2", r.stdout)
        self.assertEqual(adv(p, "plan", self.report(d, 5, "(round 5)")).returncode, 0, "the parenthesised spelling seen live counts too")
        self.assertEqual(adv(p, "plan", write(d, "r0.md", "RUN: agent=loophole-hunter task=1 pass=plan\nBLOCKER: none\nVERDICT: PASS\n")).returncode, 0,
                         "no round on the RUN line = round 1 (older reports)")

    def test_cap_from_config_and_zero_means_none(self):
        d = tempfile.mkdtemp(prefix="reef-adv.")
        p = task(d)
        os.makedirs(os.path.join(d, ".reef"))
        with open(os.path.join(d, ".reef", "config.json"), "w") as f:
            json.dump({"hunter": {"plan_rounds": 3}}, f)
        self.assertNotIn("--decided", adv(p, "plan", self.failed(d, 2)).stderr)
        self.assertIn("round 3 FAILED at hunter.plan_rounds 3", adv(p, "plan", self.failed(d, 3)).stderr)
        with open(os.path.join(d, ".reef", "config.json"), "w") as f:
            json.dump({"hunter": {"plan_rounds": 0}}, f)
        self.assertNotIn("--decided", adv(p, "plan", self.failed(d, 9)).stderr, "0 = no cap")

    def test_decided_needs_the_owners_footnote_not_a_prior_pass(self):
        # 2026-10-21 (qassimha R4): `--decided` refused a plan the hunter had never passed, so the route the cap message
        # names was closed exactly where the cap sends you. The brake is the owner's ruling, written on the row.
        d = tempfile.mkdtemp(prefix="reef-adv.")
        p = task(d)
        os.makedirs(os.path.join(d, ".reef"))
        with open(os.path.join(d, ".reef", "config.json"), "w") as f:
            json.dump({"paths": {"queue": "reef/queue.md"}}, f)
        os.makedirs(os.path.join(d, "reef"))
        with open(os.path.join(d, "reef", "queue.md"), "w") as f:
            f.write("# Queue\n\n⁶⁸ Row 1, owner ruled: fix as drafted.\n")
        r = adv(p, "plan", "--decided", "⁶⁹")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no queue footnote ⁶⁹", r.stderr)
        r = adv(p, "plan", "--decided", "68")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("owner decision 68", r.stdout)
        self.assertRegex(open(p).read(), r"(?m)^adversarial-decided: 68$")

    def test_the_cap_is_read_from_the_main_checkout_not_the_worktree(self):
        # 2026-10-21: row 4's plan lives in its feature worktree; the worktree's copy of the config kept plan_rounds 2
        # after the owner's 3 on develop, and the loop asked the owner to edit both files. Loop policy has one home.
        main = tempfile.mkdtemp(prefix="reef-adv-main.")
        g = ["git", "-C", main, "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(["git", "init", "-q", "-b", "develop", main], check=True)
        os.makedirs(os.path.join(main, ".reef"))
        with open(os.path.join(main, ".reef", "config.json"), "w") as f:
            json.dump({"hunter": {"plan_rounds": 2}}, f)
        subprocess.run(g + ["add", "-A"], check=True, capture_output=True)
        subprocess.run(g + ["commit", "-qm", "cap 2"], check=True, capture_output=True)
        wt = os.path.join(main, ".reef", "worktrees", "feat")
        subprocess.run(g + ["worktree", "add", "-q", "-b", "feat/x", wt], check=True, capture_output=True)
        with open(os.path.join(main, ".reef", "config.json"), "w") as f:
            json.dump({"hunter": {"plan_rounds": 3}}, f)   # the owner's edit, on develop only
        p = task(wt)
        r = adv(p, "plan", self.failed(wt, 2))
        self.assertNotIn("--decided", r.stderr, "the worktree's stale copy (cap 2) must not decide: " + r.stderr)
        self.assertIn("round 3 FAILED at hunter.plan_rounds 3", adv(p, "plan", self.failed(wt, 3)).stderr)

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
