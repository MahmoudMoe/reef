"""Stress suite, round two: the loophole-hunter's records (scripts/reef-adversarial) and what the guard, the pre-commit and
reef-record trust from them. A failing test here is a finding (see the round-two findings file); a passing one is coverage."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import ROOT, git, git_checked, stamped, write  # noqa: E402

ADV = os.path.join(ROOT, "scripts", "reef-adversarial")
GUARD = os.path.join(ROOT, "scripts", "reef-guard.py")
RECORD = os.path.join(ROOT, "scripts", "reef-record")

PASS_PLAN = "RUN: agent=loophole-hunter task=1 pass={p}\nDEFECT: x\nBLOCKER: none\nNONE: tried y\nVERDICT: PASS\n"


def task(d, rel="tasks/001-t.md", tier="critical", extra="", tid="1", feature="demo", nl="\n"):
    body = (f"---\nid: {tid}\nfeature: {feature}\nstatus: pending\ncomplexity: design\neffort: medium\nblocked-by: []\n"
            f"resources: []\ntier: {tier}\nverify: judge\nattempts: 0\ndispatches: 0\nlast_failure_sig: \"\"\n{extra}---\n"
            f"# {tid}\n\n## Scope\nthe defect\n\n## Decision\nhuman wrote this\n\n## Acceptance Criteria\n- test_x goes red first\n\n## Log\n")
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", newline="") as f:
        f.write(body.replace("\n", nl))
    return p


def adv(*args, cwd=None):
    return subprocess.run([sys.executable, ADV, *args], capture_output=True, text=True, cwd=cwd, timeout=30)


def raw(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def fm_of(path):
    return raw(path).replace("\r\n", "\n").split("---\n")[1]


def project(config=None):
    d = tempfile.mkdtemp(prefix="reef-stress-adv.")
    write(d, ".reef/config.json", json.dumps(config or {"gates": {"test": "true"}}))
    return d


class ReportShapes(unittest.TestCase):
    """The hunter writes the report; check_report decides whether it is a PASS. agents/loophole-hunter.md's Output block: the
    report ENDS `VERDICT: PASS | FAIL`; a BLOCKER fails the pass; "Bullets, not paragraphs (0.7, the owner's rule)"."""

    def setUp(self):
        self.d = project()
        self.t = task(self.d)

    def test_a_guard_report_quoting_the_last_rounds_pass_and_ending_fail_is_not_recorded(self):
        # loophole-hunter.md Method 4: "On pass=guard, attack the last round's fix first" — the hunter quotes that round;
        # reef_common.report_verdict: "its LAST `VERDICT:` line" (the round-one fix, 2026-11-02, not applied here)
        self.assertEqual(adv(self.t, "plan", write(self.d, "p.md", PASS_PLAN.format(p="plan"))).returncode, 0)
        rp = write(self.d, "g.md", "RUN: agent=loophole-hunter task=1 pass=guard\nDEFECT: the stripper misses a heredoc\n"
                   "Last round's report ended:\nVERDICT: PASS\n\n### Blockers\n1. the fix only handles <<EOF, not <<'EOF' — "
                   "will happen: scripts/x.py:12\n\nVERDICT: FAIL\n")
        r = adv(self.t, "guard", rp)
        self.assertNotEqual(r.returncode, 0, "a report ending VERDICT: FAIL was recorded as the guard pass: " + r.stdout)
        self.assertNotIn("adversarial-guard", fm_of(self.t))

    def test_a_pass_inside_a_code_block_does_not_outvote_the_final_fail(self):
        # the brief's own seam: a VERDICT line inside a fenced block (the hunter quoting the verifier it attacks)
        self.assertEqual(adv(self.t, "plan", write(self.d, "p.md", PASS_PLAN.format(p="plan"))).returncode, 0)
        rp = write(self.d, "g.md", "RUN: agent=loophole-hunter task=1 pass=guard\nDEFECT: x\nThe verifier's report:\n```\n"
                   "RUN: agent=verifier task=1\nVERDICT: PASS\n```\nNOTED: the verifier read only the happy path\n"
                   "1. hole the code keeps — will happen: a.py:3\nVERDICT: FAIL\n")
        r = adv(self.t, "guard", rp)
        self.assertNotEqual(r.returncode, 0, "the fenced PASS outvoted the report's own FAIL")
        self.assertNotIn("adversarial-guard", fm_of(self.t))

    def test_a_bulleted_blocker_fails_the_pass(self):
        # loophole-hunter.md: "Bullets, not paragraphs ... one fact per bullet" and "A BLOCKER ... fails the pass";
        # reef_common.BLOCKER_LINE = ^\W*BLOCKER\b — "`BLOCKER:` and `- **BLOCKER**` alike"
        for line in ("- BLOCKER: the lock is taken after the read — will happen: a.py:9",
                     "* **BLOCKER:** the lock is taken after the read",
                     "  - BLOCKER — the lock is taken after the read"):
            with self.subTest(line=line):
                t = task(self.d, rel=f"tasks/00{len(line) % 7 + 2}-t.md")
                rp = write(self.d, "p.md", f"RUN: agent=loophole-hunter task=1 pass=plan\nDEFECT: x\n{line}\nVERDICT: PASS\n")
                r = adv(t, "plan", rp)
                self.assertEqual(r.returncode, 2, f"a bulleted BLOCKER beside VERDICT: PASS was recorded: {line!r}")
                self.assertNotIn("adversarial-plan", fm_of(t))

    def test_a_bulleted_blocker_none_is_still_no_blocker(self):
        # coverage: the 0.7 dogfood wording, as a bullet
        for line in ("- BLOCKER: none", "- **BLOCKER:** none found."):
            with self.subTest(line=line):
                rp = write(self.d, "p.md", f"RUN: agent=loophole-hunter task=1 pass=plan\nDEFECT: x\n{line}\nVERDICT: PASS\n")
                self.assertEqual(adv(self.t, "plan", rp).returncode, 0)

    def test_a_crlf_report_records_like_an_lf_one(self):
        # coverage: a report written on a CRLF editor or copied through Windows tooling
        rp = os.path.join(self.d, "p.md")
        with open(rp, "w", newline="") as f:
            f.write(PASS_PLAN.format(p="plan").replace("\n", "\r\n"))
        r = adv(self.t, "plan", rp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("adversarial-plan:", fm_of(self.t))


class RoundCap(unittest.TestCase):
    def test_a_round_two_pass_that_quotes_round_ones_fail_is_recorded(self):
        # reef-adversarial docstring: "A PASS is recorded at any round: it ends the cycle (2026-10-21: R4's round-3 PASS was
        # refused ...)". The cap test greps ANY `VERDICT: FAIL` line (reef-adversarial:304), not the report's verdict.
        d = project()
        t = task(d)
        rp = write(d, "r2.md", "RUN: agent=loophole-hunter task=1 pass=plan round=2\nDEFECT: x\n"
                   "Round 1 ended:\nVERDICT: FAIL\nIts hole is closed: the plan now names the lock (Scope line 2).\n"
                   "BLOCKER: none\nVERDICT: PASS\n")
        r = adv(t, "plan", rp)
        self.assertEqual(r.returncode, 0, "a round-2 PASS was refused as a FAIL at the cap: " + r.stderr)
        self.assertIn("adversarial-plan:", fm_of(t))


class DesignTierUnderDefaults(unittest.TestCase):
    """templates/config.json ships hunter.plan_pass `design` (0.7.5: the plan-reviewer is gone, so the hunter reads every
    critical-path plan) and guard_pass `feature`; these tests pin the `critical` mode, which a project may still choose. skills/reef-plan/SKILL.md:41: the plan
    hunter runs on every `critical` task ("every `design` task too under hunter.plan_pass: design"). skills/reef-review/SKILL.md 4b
    and reef-record (0.7.5): a critical-path feature's GREEN report carries `## Guard pass`. skills/reef-task/SKILL.md:34: per task,
    the guard PASS is recorded with reef-adversarial <task> guard (the pre-commit refuses a design-tier close without it)."""

    def test_a_design_task_takes_its_per_task_guard_pass_without_a_plan_pass(self):
        d = project({"gates": {"test": "true"}, "hunter": {"plan_pass": "critical", "guard_pass": "task"}})
        t = task(d, tier="design")
        r = adv(t, "guard", write(d, "g.md", PASS_PLAN.format(p="guard")))
        self.assertEqual(r.returncode, 0, "a design task's guard PASS is unrecordable under the default plan_pass, so the "
                         "pre-commit can never close it: " + r.stderr)
        self.assertIn("adversarial-guard:", fm_of(t))

    def test_under_the_shipped_defaults_a_design_only_feature_is_green_on_its_reviews_guard_pass(self):
        with open(os.path.join(ROOT, "templates", "config.json"), encoding="utf-8") as f:
            hunter = json.load(f)["hunter"]
        self.assertEqual((hunter.get("plan_pass"), hunter.get("guard_pass")), ("design", "feature"), "the shipped defaults")
        hunter = dict(hunter, plan_pass="critical")   # the mode this test is about: a design task with no plan pass
        d = project({"gates": {"test": "true"}, "hunter": hunter, "paths": {"features": "reef/features"}})
        task(d, rel="reef/features/demo/tasks/002-b.md", tier="design", tid="2")
        rep = write(d, "review.md", "RUN: agent=acceptance feature=demo\nHEAD: 0000000\nVERDICT: GREEN\n")
        r = subprocess.run([sys.executable, RECORD, "demo", "GREEN", "--report", rep, "--root", d], cwd=d, capture_output=True, text=True, timeout=30)
        self.assertIn("## Guard pass", r.stderr, "a design-only feature is on the critical path: its review carries the guard pass")
        self.assertNotIn("adversarial-plan", r.stderr, "no plan-pass record stands between it and GREEN")


def main_with_feature_worktree():
    """A main checkout (guard_pass feature) and the feature's worktree holding the plan, as /reef-plan leaves it (v3)."""
    main = tempfile.mkdtemp(prefix="reef-stress-adv-main.")
    git_checked(main, "init", "-q", "-b", "main")
    write(main, ".reef/config.json", json.dumps({"gates": {"test": "true"}, "hunter": {"plan_pass": "critical", "guard_pass": "feature"},
                                                 "paths": {"features": "reef/features"}}))
    write(main, ".gitignore", ".reef/worktrees/\n")
    git_checked(main, "add", "-A")
    git_checked(main, "commit", "-qm", "base")
    wt = os.path.join(main, ".reef", "worktrees", "demo")
    git_checked(main, "worktree", "add", "-q", "-b", "feat/demo", wt)
    p = task(wt, rel="reef/features/demo/tasks/001-a.md", extra="adversarial-plan: aaaaaaaaaaaa\n")
    git_checked(wt, "add", "-A")
    git_checked(wt, "commit", "-qm", "plan")
    return main, wt, p


class FeatureRecordAcrossCheckouts(unittest.TestCase):
    def test_green_through_root_main_refuses_while_the_review_lacks_the_guard_pass(self):
        # reef-graph-run.py settle_row runs `reef-record <slug> GREEN --pr N --report … --root <main>` from the feature
        # worktree; reef-record reads the feature's tasks where the plan lives (feature_home), not under --root.
        # skills/reef-review/SKILL.md 4b (0.7.5): "`reef-record … GREEN` refuses a report without them".
        main, wt, _ = main_with_feature_worktree()
        rep = write(wt, ".reef/ci-local/review-demo.md", "HEAD: 0000000\nVERDICT: GREEN\n")
        fake = tempfile.mkdtemp(prefix="reef-fake-gh.")
        write(fake, "gh", "#!/bin/sh\necho '{}'\nexit 0\n")
        os.chmod(os.path.join(fake, "gh"), 0o755)
        env = dict(os.environ, PATH=fake + os.pathsep + os.environ.get("PATH", ""))
        r = subprocess.run([sys.executable, RECORD, "demo", "GREEN", "--pr", "1", "--report", rep, "--root", main],
                           cwd=wt, capture_output=True, text=True, env=env, timeout=30)
        self.assertIn("## Guard pass", r.stderr,
                      "GREEN went on to gh without the review's guard pass (the check read main, which holds no copy): " + r.stderr[-300:])

    def test_green_run_from_main_finds_the_tasks_in_the_feature_worktree(self):
        # the loop session runs in the main checkout: the feature's tasks live only in its worktree, and a GREEN from main must
        # still read the path there — never "feature not found", never a pass because main holds no critical task
        main, wt, p = main_with_feature_worktree()
        rep = write(main, "review.md", "RUN: agent=acceptance feature=demo\nHEAD: 0000000\nVERDICT: GREEN\n")
        r = subprocess.run([sys.executable, RECORD, "demo", "GREEN", "--report", rep], cwd=main, capture_output=True, text=True, timeout=30)
        self.assertNotIn("feature not found", r.stderr)
        self.assertIn("## Guard pass", r.stderr)


class PreCommitTrust(unittest.TestCase):
    def test_a_quoted_tier_still_needs_the_guard_pass_to_close(self):
        # templates/pre-commit:36-38: "A tier: design (or critical) task closes only after the loophole-hunter's SECOND pass".
        # reef_common.task_frontmatter strips quotes, so the guard and the plan check treat `tier: "critical"` as critical
        # (and demand the plan pass); the pre-commit greps '^tier: *(design|critical)' and lets it close unjudged.
        d = tempfile.mkdtemp(prefix="reef-stress-adv-hook.")
        git_checked(d, "init", "-q", "-b", "main")
        os.makedirs(os.path.join(d, "scripts"))
        shutil.copy(os.path.join(ROOT, "scripts", "reef-gate.sh"), os.path.join(d, "scripts", "reef-gate.sh"))
        os.makedirs(os.path.join(d, ".githooks"))
        shutil.copy(os.path.join(ROOT, "templates", "pre-commit"), os.path.join(d, ".githooks", "pre-commit"))
        os.chmod(os.path.join(d, ".githooks", "pre-commit"), 0o755)
        write(d, ".reef/config.json", '{"gates": {"test": "true"}}\n')
        git_checked(d, "config", "core.hooksPath", ".githooks")
        task(d, tier='"critical"', extra="adversarial-plan: abc\n")
        os.makedirs(os.path.join(d, "tasks", "done"))
        git_checked(d, "add", "-A")
        git_checked(d, "commit", "-qm", "plan")
        git_checked(d, "mv", "tasks/001-t.md", "tasks/done/001-t.md")
        r = git(d, "commit", "-qm", "close")
        self.assertNotEqual(r.returncode, 0, "a quoted-tier critical task closed with no adversarial-guard record")
        self.assertIn("closing without adversarial-guard", r.stderr)


class CrlfTaskFiles(unittest.TestCase):
    def test_a_crlf_task_file_stays_crlf_through_two_records(self):
        # contract silent; round one's M1 fix idea: set_key keeps `[^\r\n]*` (reef-attempt TaskFile.set). reef-adversarial's own
        # set_key appends `key: value\n` and its `.*$` substitution eats the `\r` — a CRLF file ends with mixed endings.
        d = project()
        t = task(d, nl="\r\n")
        self.assertEqual(adv(t, "plan", write(d, "p.md", PASS_PLAN.format(p="plan"))).returncode, 0)
        with open(t, newline="") as f:
            text = f.read()
        with open(t, "w", newline="") as f:
            f.write(text.replace("the defect", "the defect, widened"))
        self.assertEqual(adv(t, "plan", write(d, "p2.md", PASS_PLAN.format(p="plan"))).returncode, 0)
        fm = raw(t).split("---", 2)[1]
        bare = [l for l in fm.split("\r\n") if "\n" in l]
        self.assertEqual(bare, [], "LF-only lines inside a CRLF frontmatter")

    def test_a_crlf_task_recorded_by_the_hunter_is_dispatchable(self):
        # coverage: the guard compares adversarial-plan with plan_hash on the same CRLF bytes
        d = project()
        t = task(d, nl="\r\n")
        self.assertEqual(adv(t, "plan", write(d, "p.md", PASS_PLAN.format(p="plan"))).returncode, 0)
        stamped(d)
        r = subprocess.run([sys.executable, GUARD], input=json.dumps(
            {"tool_name": "Task", "cwd": d,
             "tool_input": {"subagent_type": "reef:implementer", "prompt": f"REEF-TASK: {t}\nimplement"}}),
            capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
