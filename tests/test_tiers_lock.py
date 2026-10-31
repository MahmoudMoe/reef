"""Sabotage suite for 0.6 Phase 1: the four tiers resolved at dispatch (1.0), the human-only plan
approval bound to the digest (1.2), the reviewer lock (1.3), the guard's deadline (1.4) and the guard
guarding itself (1.5). Every DENY here is a defect shown red; every allow is a legitimate action that must
keep working, including the whole 0.5 behaviour when no tier table is set."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import git_checked as git  # noqa: E402  (the suites' shared fixtures, once)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, "scripts", "reef-guard.py")
ATTEMPT = os.path.join(ROOT, "scripts", "reef-attempt")
CHECK = os.path.join(ROOT, "scripts", "reef-plan-check.py")
APPROVAL = os.path.join(ROOT, "scripts", "reef-approval.py")
RECORD = os.path.join(ROOT, "scripts", "reef-record")

TIERS = {"critical": {"roles": {"author": "opus", "verifier": "fable", "adversary": "fable", "plan_reviewer": "fable"}, "effort": "high"},
         "design": {"roles": {"author": "opus", "verifier": "opus", "adversary": "opus", "plan_reviewer": "fable"}, "effort": "high"},
         "full": {"roles": {"author": "opus", "verifier": "opus", "plan_reviewer": "fable"}, "effort": "medium"},
         "light": {"roles": {"author": "sonnet", "plan_reviewer": "none"}, "effort": "low"}}
ROLES = {"author": "opus", "verifier": "opus", "plan_reviewer": "fable", "adversary": "opus", "mechanic": "sonnet"}


def guard(payload, env=None):
    e = dict(os.environ)
    e.pop("CLAUDE_PLUGIN_ROOT", None)
    e.update(env or {})
    return subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True, env=e)


def task_text(tid, feature, tier, complexity, extra=""):
    return (f"---\nid: {tid}\nfeature: {feature}\nstatus: pending\ncomplexity: {complexity}\neffort: medium\n"
            f"blocked-by: []\nresources: []\ntier: {tier}\nverify: {'judge' if complexity == 'design' else 'gate-only'}\n"
            f"attempts: 0\ndispatches: 0\nlast_failure_sig: \"\"\n{extra}---\n# {tid}\n\n## Scope\nx\n\n"
            f"## Decision\nhuman words\n\n## Acceptance Criteria\n- test_{feature}_{tid}_works goes red first\n\n## Log\n")


def project(cfg, tasks, version="0.6.0"):
    """A committed project with the plan-check script, a fresh stamp and the gitignored machine state."""
    d = tempfile.mkdtemp(prefix="reef-p1.")
    os.makedirs(os.path.join(d, "tasks", "done"))
    os.makedirs(os.path.join(d, "scripts"))
    os.makedirs(os.path.join(d, ".reef"))
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    with open(os.path.join(d, ".reef", "config.json"), "w") as f:
        json.dump(cfg, f)
    if version:
        with open(os.path.join(d, ".reef", "version"), "w") as f:
            f.write(version + "\n")
    with open(os.path.join(d, "CLAUDE.md"), "w") as f:
        f.write("# brief\n")
    with open(os.path.join(d, ".gitignore"), "w") as f:
        f.write("tasks/.plan-review.json\n.reef/approvals/\n.reef/inflight/\n.reef/verifying/\n")
    for name, text in tasks.items():
        with open(os.path.join(d, "tasks", name), "w") as f:
            f.write(text)
    shutil.copy(CHECK, os.path.join(d, "scripts", "reef-plan-check.py"))
    shutil.copy(os.path.join(ROOT, "scripts", "reef_common.py"), os.path.join(d, "scripts", "reef_common.py"))
    git(d, "add", "-A")
    git(d, "commit", "-qm", "plan")
    return d


def plan_check(d, *args):
    return subprocess.run([sys.executable, os.path.join(d, "scripts", "reef-plan-check.py"), d, *args], capture_output=True, text=True)


def approve(d, feature):
    """The human's approval, written the way the hook writes it (digest-bound)."""
    r = plan_check(d, "--digest", "--feature", feature)
    digest = r.stdout.split()[-1]
    os.makedirs(os.path.join(d, ".reef", "approvals"), exist_ok=True)
    with open(os.path.join(d, ".reef", "approvals", f"{feature}.json"), "w") as f:
        json.dump({"digest16": digest[:16], "approved_at": "2026-10-16T00:00:00Z"}, f)
    # and reviewed: the plan reviewer's PASS, recorded the way the skill records it (0.7)
    r = subprocess.run([sys.executable, RECORD, "plan-review", feature, "PASS", "--root", d], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return digest


def dispatch(d, sub, prompt, model=None, extra=None):
    ti = {"subagent_type": sub, "prompt": prompt}
    if model:
        ti["model"] = model
    payload = {"tool_name": "Task", "cwd": d, "tool_input": ti}
    payload.update(extra or {})
    return guard(payload)


def bash(d, cmd, **payload):
    p = {"tool_name": "Bash", "cwd": d, "tool_input": {"command": cmd}}
    p.update(payload)
    return guard(p)


class FourTiers(unittest.TestCase):
    """1.0: the model per role comes from the task's tier table; the guard refuses a mismatch."""

    def setUp(self):
        self.d = project({"gates": {"test": "true"}, "roles": ROLES, "tiers": TIERS},
                         {"001-light.md": task_text(1, "demo", "light", "mech"),
                          "002-crit.md": task_text(2, "demo", "critical", "design"),
                          "003-full.md": task_text(3, "other", "full", "design")})
        self.assertEqual(plan_check(self.d).returncode, 0, plan_check(self.d).stdout)
        approve(self.d, "demo")
        approve(self.d, "other")

    def test_light_task_dispatched_with_opus_denied_when_tier_says_sonnet(self):
        r = dispatch(self.d, "reef:implementer", "REEF-TASK: tasks/001-light.md\nimplement", model="opus")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("tiers.light.roles.author = 'sonnet'", r.stderr)
        self.assertEqual(dispatch(self.d, "reef:implementer", "REEF-TASK: tasks/001-light.md\nimplement", model="sonnet").returncode, 0)

    def test_critical_task_with_sonnet_denied_and_without_adversarial_plan_denied(self):
        r = dispatch(self.d, "reef:verifier", "REEF-TASK: tasks/002-crit.md\nverify", model="opus")
        self.assertEqual(r.returncode, 2, "critical verification runs on the critical table (fable)")
        self.assertIn("tiers.critical.roles.verifier = 'fable'", r.stderr)
        r = dispatch(self.d, "reef:implementer", "REEF-TASK: tasks/002-crit.md\nimplement", model="opus")
        self.assertEqual(r.returncode, 2)
        self.assertIn("adversarial-plan", r.stderr, "critical needs the hunter's plan pass like design")

    def test_role_dispatch_without_task_line_keeps_05_behaviour(self):
        # no REEF-TASK/REEF-FEATURE: roles.* decides, exactly as in 0.5
        self.assertEqual(dispatch(self.d, "reef:verifier", "verify something", model="opus").returncode, 0)
        self.assertEqual(dispatch(self.d, "reef:verifier", "verify something", model="fable").returncode, 2)

    def test_feature_line_resolves_the_heaviest_tier(self):
        r = dispatch(self.d, "reef:plan-reviewer", "REEF-FEATURE: demo\nreview", model="fable")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = dispatch(self.d, "reef:plan-reviewer", "REEF-FEATURE: nope-only-light\nreview", model="fable")
        self.assertEqual(r.returncode, 0, "an unknown feature falls back to roles.* (fable)")
        with open(os.path.join(self.d, "tasks", "004-l2.md"), "w") as f:
            f.write(task_text(4, "lightonly", "light", "mech"))
        r = dispatch(self.d, "reef:plan-reviewer", "REEF-FEATURE: lightonly\nreview", model="fable")
        self.assertEqual(r.returncode, 2, "an all-light feature needs no plan-reviewer agent")
        self.assertIn("none", r.stderr)
        # v3 phase 3a: a full-tier feature with no risk touch is the fast path — the check is the review, no plan-reviewer
        r = dispatch(self.d, "reef:plan-reviewer", "REEF-FEATURE: other\nreview", model="fable")
        self.assertEqual(r.returncode, 2, "the fast path dispatches no plan-reviewer: " + r.stderr)
        self.assertIn("fast path", r.stderr)
        # the review (2026-10-25): a risk touch on an otherwise full feature is the critical path — the sabotage test of
        # the touches branch (delete it and this dispatch is refused as fast)
        with open(os.path.join(self.d, "tasks", "005-risky.md"), "w") as f:
            f.write(task_text(5, "risky", "full", "design", extra="touches: [auth]\n"))
        r = dispatch(self.d, "reef:plan-reviewer", "REEF-FEATURE: risky\nreview", model="fable")
        self.assertEqual(r.returncode, 0, "a risk touch is the critical path: the plan-reviewer is dispatched: " + r.stderr)

    def test_explore_is_a_mechanic(self):
        self.assertEqual(dispatch(self.d, "Explore", "look around", model="opus").returncode, 2)
        self.assertEqual(dispatch(self.d, "Explore", "look around", model="sonnet").returncode, 0)

    def test_needs_agent_on_the_critical_path_and_none_on_the_fast_path(self):
        # changed on purpose for v3 phase 3a (2026-10-25): `other` holds one full task and no risk touch — the fast path;
        # before, every task heavier than light called the plan-reviewer agent
        r = plan_check(self.d, "--needs-agent", "--feature", "other")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("plan-reviewer: none (fast path: heaviest tier full", r.stdout)
        with open(os.path.join(self.d, "tasks", "004-l2.md"), "w") as f:
            f.write(task_text(4, "lightonly", "light", "mech"))
        r = plan_check(self.d, "--needs-agent", "--feature", "lightonly")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("plan-reviewer: none", r.stdout)
        r = plan_check(self.d, "--needs-agent", "--feature", "demo")
        self.assertEqual(r.returncode, 0, "demo holds a critical task: the agent is needed")

    def test_attempt_prints_tier_resolved_roles_and_effort(self):
        r = subprocess.run([sys.executable, ATTEMPT, os.path.join(self.d, "tasks", "002-crit.md")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("dispatch: model=opus effort=high", r.stdout, "critical raises medium to high")
        self.assertIn("author: model=opus tier=critical", r.stdout)
        self.assertIn("verifier: model=fable", r.stdout)
        self.assertIn("adversary: model=fable", r.stdout)
        r = subprocess.run([sys.executable, ATTEMPT, os.path.join(self.d, "tasks", "001-light.md")], capture_output=True, text=True)
        self.assertIn("dispatch: model=sonnet effort=medium", r.stdout, "the task's own medium is never lowered to the tier's low")
        self.assertNotIn("adversary:", r.stdout)

    def test_unset_tier_table_is_exactly_05(self):
        d = project({"gates": {"test": "true"}, "roles": ROLES}, {"002-crit.md": task_text(2, "demo", "critical", "design")}, version=None)
        r = subprocess.run([sys.executable, ATTEMPT, os.path.join(d, "tasks", "002-crit.md")], capture_output=True, text=True)
        self.assertIn("dispatch: model=opus effort=medium", r.stdout)
        self.assertIn("verifier: model=opus", r.stdout)
        self.assertEqual(dispatch(d, "reef:verifier", "REEF-TASK: tasks/002-crit.md\nverify", model="opus").returncode, 0)
        self.assertEqual(dispatch(d, "reef:verifier", "REEF-TASK: tasks/002-crit.md\nverify", model="fable").returncode, 2)


class ApprovalSurvivesTheHunterStamp(unittest.TestCase):
    """2026-10-18: `adversarial-plan` sat inside the approval digest, so `plan --decided` after Approve (the designed
    path for a hole open after round 2) and a stamp migration voided the approval of a plan nobody had edited."""

    def test_stamp_decision_and_migration_keep_the_approval_and_the_dispatch(self):
        d = project({"gates": {"test": "true"}, "roles": ROLES, "tiers": TIERS}, {"002-crit.md": task_text(2, "demo", "critical", "design")})
        self.assertEqual(plan_check(d).returncode, 0, plan_check(d).stdout)
        digest = approve(d, "demo")
        p = os.path.join(d, "tasks", "002-crit.md")
        with open(os.path.join(d, "hunt.md"), "w") as f:
            f.write("RUN: agent=loophole-hunter task=2 pass=plan round=2\nBLOCKER: none\nVERDICT: PASS\n")
        adv = os.path.join(ROOT, "scripts", "reef-adversarial")
        self.assertEqual(subprocess.run([sys.executable, adv, p, "plan", os.path.join(d, "hunt.md")], capture_output=True, text=True).returncode, 0)
        self.assertEqual(plan_check(d, "--digest", "--feature", "demo").stdout.split()[-1], digest, "the hunter's record is outside the digest")
        self.assertEqual(subprocess.run([sys.executable, adv, p, "plan", "--decided", "⁴⁰"], capture_output=True, text=True).returncode, 0)
        self.assertEqual(plan_check(d, "--digest", "--feature", "demo").stdout.split()[-1], digest, "the owner's ruling re-stamps without a re-approval")
        self.assertEqual(plan_check(d, "--verify-stamp", "--feature", "demo").returncode, 0)
        r = dispatch(d, "reef:implementer", "REEF-TASK: tasks/002-crit.md\nimplement", model="opus")
        self.assertEqual(r.returncode, 0, r.stderr)


class HumanOnlyApproval(unittest.TestCase):
    """1.2: the approval is a record bound to the digest; only the hook writes it."""

    def setUp(self):
        self.d = project({"gates": {"test": "true"}}, {"007-demo.md": task_text(7, "demo", "light", "mech")})
        self.assertEqual(plan_check(self.d).returncode, 0)

    def test_stamped_but_unapproved_06_feature_is_denied(self):
        r = dispatch(self.d, "reef:implementer", "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2)
        self.assertIn("approval: MISSING", r.stderr)
        approve(self.d, "demo")
        self.assertEqual(dispatch(self.d, "reef:implementer", "REEF-TASK: tasks/007-demo.md\nimplement").returncode, 0)

    def test_pre_06_feature_warns_only(self):
        d = project({"gates": {"test": "true"}}, {"007-demo.md": task_text(7, "demo", "light", "mech")}, version=None)
        self.assertEqual(plan_check(d).returncode, 0)
        r = plan_check(d, "--verify-stamp", "--feature", "demo")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("warning: approval: MISSING", r.stdout)
        self.assertEqual(dispatch(d, "reef:implementer", "REEF-TASK: tasks/007-demo.md\nimplement").returncode, 0)

    def test_hand_written_approval_denied_by_bash_and_edit(self):
        for cmd in ("echo '{}' > .reef/approvals/demo.json", "tee .reef/approvals/demo.json", "cp x .reef/review/demo.json",
                    "printf '{}' >> .reef/approvals/demo.json"):
            with self.subTest(cmd=cmd):
                self.assertEqual(bash(self.d, cmd).returncode, 2, cmd)
        self.assertEqual(bash(self.d, "cat .reef/approvals/demo.json").returncode, 0, "reading a record is fine")
        r = guard({"tool_name": "Write", "cwd": self.d, "tool_input": {"file_path": os.path.join(self.d, ".reef/approvals/demo.json"), "content": "{}"}})
        self.assertEqual(r.returncode, 2)
        r = guard({"tool_name": "Edit", "cwd": self.d, "tool_input": {"file_path": ".reef/review/demo.json", "old_string": "a", "new_string": "b"}})
        self.assertEqual(r.returncode, 2)

    def _hook(self, question, label, extra_resp=None):
        resp = {"questions": [{"question": question, "options": [{"label": "Approve"}, {"label": "Edit"}, {"label": "Cancel"}]}],
                "answers": {question: label}, "annotations": {}}
        resp.update(extra_resp or {})
        payload = {"tool_name": "AskUserQuestion", "hook_event_name": "PostToolUse", "cwd": self.d,
                   "tool_input": {"questions": resp["questions"]}, "tool_response": resp}
        return subprocess.run([sys.executable, APPROVAL], input=json.dumps(payload), capture_output=True, text=True)

    def test_hook_writes_only_on_approve_with_the_current_digest(self):
        digest = plan_check(self.d, "--digest", "--feature", "demo").stdout.split()[-1]
        rec = os.path.join(self.d, ".reef", "approvals", "demo.json")
        q = f"Approve plan demo at {digest[:16]}?"
        self._hook(q, "Edit")
        self.assertFalse(os.path.exists(rec), "wrong label writes nothing")
        self._hook(f"Approve plan demo at {'0' * 16}?", "Approve")
        self.assertFalse(os.path.exists(rec), "a stale digest writes nothing")
        self._hook(q, "Approve", {"afkTimeoutMs": 300000})
        self.assertFalse(os.path.exists(rec), "a timeout answer writes nothing")
        r = self._hook(q, "Approve")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(rec), r.stdout)
        with open(rec) as f:
            self.assertEqual(json.load(f)["digest16"], digest[:16])
        self.assertEqual(plan_check(self.d, "--verify-stamp", "--feature", "demo").returncode, 0)
        # editing the plan (a Scope line, not the Log — the stamp ignores the Log) makes the approval stale again
        tp = os.path.join(self.d, "tasks", "007-demo.md")
        with open(tp) as f:
            t = f.read()
        with open(tp, "w") as f:
            f.write(t.replace("## Scope\nx", "## Scope\nx and more"))
        plan_check(self.d)
        r = plan_check(self.d, "--verify-stamp", "--feature", "demo")
        self.assertEqual(r.returncode, 1)
        self.assertIn("approval: STALE", r.stdout)


    def test_the_gate_line_is_computed_and_names_what_changed_since_the_approval(self):
        # 0.7 (the owner, 2026-10-20): "Approve plan … at bd8cd330bfb50bfd?" told them nothing; a readable line from a
        # script now sits beside the fingerprint, and the approval record keeps {file: sha12} to say what changed since
        line = lambda: plan_check(self.d, "--summary", "--feature", "demo").stdout.strip()
        self.assertEqual(line(), "summary: demo · 1 task(s) · 1 criteria · 0 draft ADR(s) · first approval")
        digest = plan_check(self.d, "--digest", "--feature", "demo").stdout.split()[-1]
        q = f"Approve plan demo at {digest[:16]}?"
        self.assertEqual(self._hook(q, "Approve").returncode, 0)
        with open(os.path.join(self.d, ".reef", "approvals", "demo.json")) as f:
            rec = json.load(f)
        self.assertEqual(rec["digest16"], digest[:16])
        self.assertEqual(list(rec["files"]), ["007-demo.md"], "the digest's own files, keyed as the digest keys them")
        self.assertRegex(line(), r"· unchanged since your approval on \d{4}-\d\d-\d\d$")
        tp = os.path.join(self.d, "tasks", "007-demo.md")
        with open(tp) as f:
            t = f.read()
        with open(tp, "w") as f:
            f.write(t.replace("## Scope\nx", "## Scope\nx and more"))
        self.assertRegex(line(), r"· changed since your approval on \d{4}-\d\d-\d\d: 007-demo\.md$")
        # a record from before this field: the line says so instead of guessing
        with open(os.path.join(self.d, ".reef", "approvals", "demo.json"), "w") as f:
            json.dump({"digest16": digest[:16], "approved_at": "2026-10-19T00:00:00Z"}, f)
        self.assertIn("approved 2026-10-19, before this line recorded files: read the plan in full", line())

    def test_the_record_binds_the_full_digest_not_its_16_hex(self):
        # the security review of #259: a 16-hex binding is a 64-bit prefix — an agent writing both plans finds a collision
        # in ~2^32 tries, so the record keeps the full digest; the owner still reads and types 16 hex
        digest = plan_check(self.d, "--digest", "--feature", "demo").stdout.split()[-1]
        rec = os.path.join(self.d, ".reef", "approvals", "demo.json")
        self.assertEqual(self._hook(f"Approve plan demo at {digest[:16]}?", "Approve").returncode, 0)
        with open(rec) as f:
            self.assertEqual(json.load(f)["digest"], digest, "the record carries the full digest of the plan approved")
        rr = subprocess.run([sys.executable, RECORD, "plan-review", "demo", "PASS", "--root", self.d], capture_output=True, text=True)
        self.assertEqual(rr.returncode, 0, rr.stderr)
        with open(os.path.join(self.d, ".reef", "review", "plan-demo.json")) as f:
            self.assertEqual(json.load(f)["digest"], digest, "so does the review record")
        self.assertEqual(plan_check(self.d, "--verify-stamp", "--feature", "demo").returncode, 0)
        collided = digest[:16] + ("0" if digest[16] != "0" else "1") + digest[17:]
        with open(rec, "w") as f:
            json.dump({"digest16": digest[:16], "digest": collided, "approved_at": "2026-10-31T00:00:00Z"}, f)
        r = plan_check(self.d, "--verify-stamp", "--feature", "demo")
        self.assertEqual(r.returncode, 1, "the same 16 hex with another full digest is another plan")
        self.assertIn(f"approval: STALE for 'demo' (approved {collided}, plan is {digest})", r.stdout, "the line names the full digests")
        with open(rec, "w") as f:
            json.dump({"digest16": digest[:16], "digest": "", "approved_at": "2026-10-31T00:00:00Z"}, f)
        self.assertEqual(plan_check(self.d, "--verify-stamp", "--feature", "demo").returncode, 1, "an empty digest binds nothing")
        with open(rec, "w") as f:
            json.dump({"digest16": digest[:16], "approved_at": "2026-10-19T00:00:00Z"}, f)
        self.assertEqual(plan_check(self.d, "--verify-stamp", "--feature", "demo").returncode, 0, "an older record (16 hex only) works for one release")

    def test_two_plans_sharing_the_16_hex_approve_neither(self):
        # the hook takes the owner's 16 hex: when two checkouts' plans share them, which plan the owner read is unknowable
        import contextlib
        import io
        from _fixtures import load_script
        mod = load_script("reef-approval.py")
        a, b = os.path.join(self.d, "a"), os.path.join(self.d, "b")
        mod.plan_digests = lambda cwd, feature: {a: "ab" * 8 + "0" * 48, b: "ab" * 8 + "1" * 48}
        mod.plan_check_failures = lambda root, feature: []
        mod.plan_files = lambda root, feature: {}
        mod.clear_question = lambda *a: 0
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            mod.main(["--owner", f"Approve plan demo at {'ab' * 8}?", "--root", self.d])
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "approvals", "demo.json")), out.getvalue())
        self.assertIn("two plans", out.getvalue())

    def test_a_checkouts_own_plan_check_is_not_believed(self):
        # the security review of #259: the hook and the guard ran <checkout>/scripts/reef-plan-check.py, so a copy that
        # prints a forged digest, a green check and an empty files map wrote the record and passed the stamp
        forger = os.path.join(self.d, "scripts", "reef-plan-check.py")
        with open(forger, "w") as f:
            f.write("import sys\nif '--digest' in sys.argv: print('digest: demo ' + 'ab' * 32)\n"
                    "elif '--plan-files' in sys.argv: print('{}')\nelse: print('stamp: MATCH')\n")
        r = self._hook(f"Approve plan demo at {'ab' * 8}?", "Approve")
        self.assertEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "approvals", "demo.json")), "a forged digest writes nothing: " + r.stdout)
        r = dispatch(self.d, "reef:implementer", "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2, "the copy's green --verify-stamp opens no gate")
        self.assertIn("approval: MISSING", r.stderr)
        rr = subprocess.run([sys.executable, RECORD, "plan-review", "demo", "PASS", "--root", self.d], capture_output=True, text=True)
        self.assertEqual(rr.returncode, 0, rr.stderr)
        real = subprocess.run([sys.executable, CHECK, self.d, "--digest", "--feature", "demo"], capture_output=True, text=True).stdout.split()[-1]
        with open(os.path.join(self.d, ".reef", "review", "plan-demo.json")) as f:
            self.assertEqual(json.load(f)["digest16"], real[:16], "reef-record binds the review to the real digest, not the copy's")

    def test_hook_refuses_while_plan_check_fails(self):
        # 2026-10-17: five sentences over the word ceiling surfaced AFTER the owner approved; fixing them voided the approval
        tp = os.path.join(self.d, "tasks", "007-demo.md")
        with open(tp) as f:
            t = f.read()
        long = "this one sentence runs on and on past the ceiling of twenty five words that the writing rule sets for every task file in a feature folder and more"
        with open(tp, "w") as f:
            f.write(t.replace("## Scope\nx", "## Scope\n" + long))
        digest = plan_check(self.d, "--digest", "--feature", "demo").stdout.split()[-1]
        r = self._hook(f"Approve plan demo at {digest[:16]}?", "Approve")
        self.assertEqual(r.returncode, 0)
        self.assertIn("REFUSED", r.stdout)
        self.assertIn("plan-check", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "approvals", "demo.json")), "a failing plan is not approved")


class JudgeDispatchNeedsTheTaskLine(unittest.TestCase):
    def test_a_hunter_dispatched_without_reef_task_is_denied_with_the_fix(self):
        # 2026-10-18: a plan-pass hunter sent with REEF-FEATURE: only read as "guard internal error — failing closed"
        d = project({"gates": {"test": "true"}}, {"007-demo.md": task_text(7, "demo", "critical", "design")})
        r = dispatch(d, "reef:loophole-hunter", "REEF-FEATURE: demo\nhunt the plan")
        self.assertEqual(r.returncode, 2)
        self.assertIn("without a 'REEF-TASK: <task-file>' first line", r.stderr)
        self.assertNotIn("internal error", r.stderr)


class ApprovalInAWorktree(unittest.TestCase):
    """First contact (2026-10-16): the plan was moved to a feature worktree; the hook computed the digest in the main
    checkout (develop had no feature files) and an 'Approve' wrote nothing. The digest is computed where the plan
    lives; the record still lands in the main checkout."""

    def test_plan_in_a_feature_worktree_is_approved_and_recorded_in_main(self):
        d = project({"gates": {"test": "true"}}, {"007-demo.md": task_text(7, "demo", "full", "design")})
        wt = os.path.join(tempfile.mkdtemp(prefix="reef-wt."), "feat")
        git(d, "worktree", "add", "-q", "-b", "feat/demo", wt)
        tp = os.path.join(wt, "tasks", "007-demo.md")
        with open(tp) as f:
            t = f.read()
        with open(tp, "w") as f:
            f.write(t.replace("## Scope\nx", "## Scope\nx, planned further in the worktree"))
        self.assertEqual(plan_check(wt).returncode, 0)
        wt_digest = plan_check(wt, "--digest", "--feature", "demo").stdout.split()[-1]
        main_digest = plan_check(d, "--digest", "--feature", "demo").stdout.split()[-1]
        self.assertNotEqual(wt_digest[:16], main_digest[:16])
        q = f"Approve plan demo at {wt_digest[:16]}?"
        resp = {"questions": [{"question": q, "options": [{"label": "Approve"}]}], "answers": {q: "Approve"}}
        payload = {"tool_name": "AskUserQuestion", "hook_event_name": "PostToolUse", "cwd": d,
                   "tool_input": {"questions": resp["questions"]}, "tool_response": resp}
        r = subprocess.run([sys.executable, APPROVAL], input=json.dumps(payload), capture_output=True, text=True)
        rec = os.path.join(d, ".reef", "approvals", "demo.json")
        self.assertTrue(os.path.exists(rec), r.stdout)
        with open(rec) as f:
            self.assertEqual(json.load(f)["digest16"], wt_digest[:16])
        self.assertFalse(os.path.exists(os.path.join(wt, ".reef", "approvals", "demo.json")), "the record lives in the main checkout only")
        rr = subprocess.run([sys.executable, RECORD, "plan-review", "demo", "PASS", "--root", wt], capture_output=True, text=True)
        self.assertEqual(rr.returncode, 0, rr.stderr)
        self.assertTrue(os.path.isfile(os.path.join(d, ".reef", "review", "plan-demo.json")), "the review record lives in the main checkout too")
        self.assertEqual(plan_check(wt, "--verify-stamp", "--feature", "demo").returncode, 0, "the guard's check in the worktree passes")
        # a digest nobody's checkout holds still writes nothing
        q2 = f"Approve plan demo at {'f' * 16}?"
        payload["tool_response"] = {"questions": [{"question": q2, "options": [{"label": "Approve"}]}], "answers": {q2: "Approve"}}
        os.unlink(rec)
        r = subprocess.run([sys.executable, APPROVAL], input=json.dumps(payload), capture_output=True, text=True)
        self.assertFalse(os.path.exists(rec))
        self.assertIn("matches no checkout", r.stdout)


class PlanReviewVerdictIsARecord(unittest.TestCase):
    """0.7: the deterministic stamp never meant the semantic review passed. For a feature with a task above light the
    guard's check needs `scripts/reef-record plan-review <slug> PASS` at the current digest."""

    def test_missing_stale_failed_and_light_only(self):
        d = project({"gates": {"test": "true"}}, {"007-demo.md": task_text(7, "demo", "design", "design")})
        self.assertEqual(plan_check(d).returncode, 0)
        digest = plan_check(d, "--digest", "--feature", "demo").stdout.split()[-1]
        os.makedirs(os.path.join(d, ".reef", "approvals"), exist_ok=True)
        with open(os.path.join(d, ".reef", "approvals", "demo.json"), "w") as f:
            json.dump({"digest16": digest[:16], "approved_at": "2026-10-16T00:00:00Z"}, f)
        r = plan_check(d, "--verify-stamp", "--feature", "demo")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("review: MISSING for 'demo'", r.stdout)
        self.assertIn("approval: OK", r.stdout)
        rec = subprocess.run([sys.executable, RECORD, "plan-review", "demo", "PASS", "--root", d], capture_output=True, text=True)
        self.assertEqual(rec.returncode, 0, rec.stderr)
        self.assertTrue(os.path.isfile(os.path.join(d, ".reef", "review", "plan-demo.json")))
        r = plan_check(d, "--verify-stamp", "--feature", "demo")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("review: OK for 'demo'", r.stdout)
        # the review binds the full digest too: the same 16 hex with another full digest is another plan
        rp = os.path.join(d, ".reef", "review", "plan-demo.json")
        with open(rp) as f:
            good = json.load(f)
        self.assertEqual(good["digest"], digest)
        with open(rp, "w") as f:
            json.dump(dict(good, digest=digest[:16] + ("0" if digest[16] != "0" else "1") + digest[17:]), f)
        r = plan_check(d, "--verify-stamp", "--feature", "demo")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("review: STALE", r.stdout)
        with open(rp, "w") as f:
            json.dump(good, f)
        # a FAIL verdict blocks
        subprocess.run([sys.executable, RECORD, "plan-review", "demo", "FAIL", "--root", d], capture_output=True, text=True)
        r = plan_check(d, "--verify-stamp", "--feature", "demo")
        self.assertEqual(r.returncode, 1)
        self.assertIn("review: FAILED", r.stdout)
        # the plan changes after a PASS: stale
        subprocess.run([sys.executable, RECORD, "plan-review", "demo", "PASS", "--root", d], capture_output=True, text=True)
        tp = os.path.join(d, "tasks", "007-demo.md")
        with open(tp) as f:
            t = f.read()
        with open(tp, "w") as f:
            f.write(t.replace("## Scope\nx", "## Scope\nx and a new line"))
        plan_check(d)
        approve_digest = plan_check(d, "--digest", "--feature", "demo").stdout.split()[-1]
        with open(os.path.join(d, ".reef", "approvals", "demo.json"), "w") as f:
            json.dump({"digest16": approve_digest[:16], "approved_at": "2026-10-16T00:00:00Z"}, f)
        r = plan_check(d, "--verify-stamp", "--feature", "demo")
        self.assertEqual(r.returncode, 1)
        self.assertIn("review: STALE", r.stdout)
        # all-light: not required
        d2 = project({"gates": {"test": "true"}}, {"008-mech.md": task_text(8, "lite", "light", "mech")})
        plan_check(d2)
        dg = plan_check(d2, "--digest", "--feature", "lite").stdout.split()[-1]
        os.makedirs(os.path.join(d2, ".reef", "approvals"), exist_ok=True)
        with open(os.path.join(d2, ".reef", "approvals", "lite.json"), "w") as f:
            json.dump({"digest16": dg[:16], "approved_at": "2026-10-16T00:00:00Z"}, f)
        r = plan_check(d2, "--verify-stamp", "--feature", "lite")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("review: not required", r.stdout)


class GuardPassRecordDoesNotStaleTheStamp(unittest.TestCase):
    def test_adversarial_guard_key_is_execution_state(self):
        # first contact (2026-10-16): the hunter's guard pass wrote `adversarial-guard:` into 101's frontmatter after the
        # merge; the stamp read it as a plan edit and the guard refused to dispatch 102
        d = project({"gates": {"test": "true"}}, {"007-demo.md": task_text(7, "demo", "critical", "design")})
        self.assertEqual(plan_check(d).returncode, 0)
        approve(d, "demo")
        self.assertEqual(plan_check(d, "--verify-stamp", "--feature", "demo").returncode, 0)
        tp = os.path.join(d, "tasks", "007-demo.md")
        with open(tp) as f:
            t = f.read()
        with open(tp, "w") as f:
            f.write(t.replace("dispatches: 0\n", "dispatches: 1\nadversarial-guard: 1c81d2f05bb2@462e73ac\nworktree: .reef/worktrees/007\n", 1))
        r = plan_check(d, "--verify-stamp", "--feature", "demo")
        self.assertEqual(r.returncode, 0, r.stdout)
        # the plan pass record is BOUND to the digest, not inside it (2026-10-18: inside, `--decided` after Approve and a
        # stamp migration voided the approval of an unchanged plan); a record that matches no form is named, not hidden
        with open(tp, "w") as f:
            f.write(t.replace("dispatches: 0\n", "dispatches: 0\nadversarial-plan: 000000000000\n", 1))
        r = plan_check(d, "--verify-stamp", "--feature", "demo")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("hunter: STALE 7", r.stdout)


class HostInput(unittest.TestCase):
    """0.7 (the owner, 2026-10-21: Reef beyond Claude Code): another host's adapter sends one normalized input, marked
    `reef_host`; the guard translates it to the payload it already checks. The caller is required: without it every
    call would be the main session's, and a judge's write would pass the reviewer lock unseen."""

    def setUp(self):
        self.d = project({"gates": {"test": "true"}, "roles": {"author": "opus"}},
                         {"007-demo.md": task_text(7, "demo", "full", "design")})

    def host(self, **fields):
        return guard({"reef_host": "opencode", "cwd": self.d, **fields})

    def test_a_missing_caller_or_an_unmapped_tool_is_refused(self):
        r = self.host(tool="shell", command="git status")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("`agent`", r.stderr)
        self.assertEqual(self.host(tool="shell", command="git status", agent="").returncode, 2)
        r = self.host(tool="patch", agent="main", path="a.py")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("patch", r.stderr)

    def test_the_caller_reaches_the_reviewer_lock_and_the_authoring_check(self):
        self.assertEqual(self.host(tool="shell", command="git status", agent="main").returncode, 0)
        r = self.host(tool="shell", command="git commit -m x", agent="reef:verifier", agent_id="a1")
        self.assertEqual(r.returncode, 2, "a judge's commit through a host adapter is still a judge's commit")
        self.assertEqual(self.host(tool="shell", command="git commit -m x", agent="main").returncode, 0, "the main session is not locked")
        hb = ".reef/ci-local/handback-701.md"
        self.assertEqual(self.host(tool="write", path=hb, content="RUN: x", agent="main").returncode, 2, "the main session never authors a hand-back")
        r = self.host(tool="write", path=hb, content="RUN: x", agent="reef:implementer", agent_id="a2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.host(tool="edit", path=hb, old="a", new="RUN: x", agent="main").returncode, 2)

    def test_a_dispatch_is_checked_like_the_agent_tool(self):
        prompt = "REEF-TASK: " + os.path.join(self.d, "tasks", "007-demo.md")
        r = self.host(tool="dispatch", subagent="reef:implementer", model="sonnet", prompt=prompt, agent="main")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("roles.author", r.stderr)


class HunterRoundCapAtDispatch(unittest.TestCase):
    """2026-10-24: a hunter plan round above hunter.plan_rounds was dispatched and paid for, and only reef-adversarial
    refused its report; the guard refuses the dispatch itself."""

    def setUp(self):
        self.d = project({"gates": {"test": "true"}}, {"007-demo.md": task_text(7, "demo", "critical", "design")})
        self.task = os.path.join(self.d, "tasks", "007-demo.md")

    def hunt(self, rnd=None):
        line = f"\npass=plan round={rnd}" if rnd is not None else "\npass=plan"
        return dispatch(self.d, "reef:loophole-hunter", f"REEF-TASK: {self.task}{line}")

    def test_a_round_above_the_cap_is_refused_before_it_runs(self):
        self.assertEqual(self.hunt(2).returncode, 0, self.hunt(2).stderr)
        self.assertEqual(self.hunt().returncode, 0, "no round named: round 1")
        r = self.hunt(3)
        self.assertEqual(r.returncode, 2)
        self.assertIn("hunter plan round 3 > hunter.plan_rounds 2", r.stderr)
        cfg = json.load(open(os.path.join(self.d, ".reef", "config.json")))
        cfg["hunter"] = {"plan_rounds": 3}
        json.dump(cfg, open(os.path.join(self.d, ".reef", "config.json"), "w"))
        self.assertEqual(self.hunt(3).returncode, 0, "the cap is the config's")


class ReviewerLock(unittest.TestCase):
    """1.3: agent_type from the payload decides; a judge never mutates."""

    def setUp(self):
        self.d = project({"gates": {"test": "true"}}, {"007-demo.md": task_text(7, "demo", "full", "design")})

    def test_verifier_denied_implementer_allowed(self):
        for cmd in ("git commit -m x", "git add -A", "git checkout -- .", "cat > x", "echo y >> notes.md", "tee out.txt",
                    "sed -i s/a/b/ f.py", "rm -f f.py", "git stash list && git reset --hard"):
            with self.subTest(cmd=cmd):
                self.assertEqual(bash(self.d, cmd, agent_type="verifier", agent_id="a1").returncode, 2, cmd)
        for cmd in ("git diff", "git log --oneline -3", "git status", "cat f.py", "python3 -m unittest -q", "grep -rn x src", "git branch", "git config --get core.hooksPath"):
            with self.subTest(cmd=cmd):
                self.assertEqual(bash(self.d, cmd, agent_type="verifier", agent_id="a1").returncode, 0, cmd)
        for cmd in ("git commit -m x", "cat > x", "sed -i s/a/b/ f.py"):
            with self.subTest(cmd=cmd):
                self.assertEqual(bash(self.d, cmd, agent_type="implementer", agent_id="a2").returncode, 0, cmd)
                self.assertEqual(bash(self.d, cmd).returncode, 0, "the main session is not locked")
        for t in ("loophole-hunter", "plan-reviewer", "Explore"):
            self.assertEqual(bash(self.d, "git commit -m x", agent_type=t, agent_id="a3").returncode, 2, t)

    def test_ci_wait_denied_for_every_subagent(self):
        for t in ("implementer", "mechanic", "verifier"):
            self.assertEqual(bash(self.d, "gh pr checks 12 --watch", agent_type=t, agent_id="a").returncode, 2, t)
            self.assertEqual(bash(self.d, "gh run watch 99", agent_type=t, agent_id="a").returncode, 2, t)
            self.assertEqual(bash(self.d, "sleep 60", agent_type=t, agent_id="a").returncode, 2, t)
            self.assertEqual(bash(self.d, "sleep 5", agent_type=t, agent_id="a").returncode, 0, t)
        self.assertEqual(bash(self.d, "gh pr checks 12 --watch").returncode, 0, "the main session: prose, not the guard")

    def test_typeless_subagent_locked_while_verifying_marker_exists(self):
        self.assertEqual(bash(self.d, "git commit -m x", agent_id="zz").returncode, 0, "no marker: a typeless call is not a judge")
        os.makedirs(os.path.join(self.d, ".reef", "verifying"))
        with open(os.path.join(self.d, ".reef", "verifying", "7"), "w") as f:
            f.write("{}")
        self.assertEqual(bash(self.d, "git commit -m x", agent_id="zz").returncode, 2)
        self.assertEqual(bash(self.d, "git diff", agent_id="zz").returncode, 0)
        self.assertEqual(bash(self.d, "git commit -m x").returncode, 0, "the main session is never locked by the marker")

    def test_allowed_verifier_dispatch_writes_the_marker(self):
        plan_check(self.d)
        approve(self.d, "demo")
        r = dispatch(self.d, "reef:verifier", "REEF-TASK: tasks/007-demo.md\nverify")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.d, ".reef", "verifying", "7")))
        r = dispatch(self.d, "reef:implementer", "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.d, ".reef", "inflight", "7")) as f:
            self.assertEqual(json.load(f)["tier"], "full")


class PlanPassLeavesNoMarker(unittest.TestCase):
    def test_a_hunter_on_a_pending_task_is_the_plan_pass_and_writes_no_marker(self):
        # 2026-10-21 (qassimha row 12): failed plan passes left verifying:1202/1204 "in flight" for hours
        d = project({"gates": {"test": "true"}}, {"007-demo.md": task_text(7, "demo", "critical", "design")})
        plan_check(d)
        approve(d, "demo")
        marker = os.path.join(d, ".reef", "verifying", "7")
        r = dispatch(d, "reef:loophole-hunter", "REEF-TASK: tasks/007-demo.md\npass=plan")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(marker), "the plan pass locks nothing and leaves nothing")
        tp = os.path.join(d, "tasks", "007-demo.md")
        with open(tp) as f:
            t = f.read()
        with open(tp, "w") as f:
            f.write(t.replace("status: pending", "status: in-progress"))
        r = dispatch(d, "reef:loophole-hunter", "REEF-TASK: tasks/007-demo.md\npass=guard")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(marker), "the guard pass on code still marks the task being judged")


class Deadline(unittest.TestCase):
    """1.4: a hung guard denies before the host's timeout."""

    def test_hang_exits_2_within_the_deadline(self):
        t0 = time.monotonic()
        r = guard({"tool_name": "Bash", "tool_input": {"command": "ls"}}, env={"REEF_GUARD_TEST_HANG": "60", "REEF_GUARD_DEADLINE": "1"})
        dt = time.monotonic() - t0
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("deadline", r.stderr)
        self.assertLess(dt, 5)

    def test_a_dispatch_has_room_for_its_checks_and_a_bash_call_keeps_the_short_limit(self):
        # 2026-10-31, the owner's project: four implementer dispatches for row 188 were denied by "guard deadline of 8s
        # exceeded" — the dispatch checks (the plan stamp, the ready set, the context) outran 8 s on a large repository, and
        # the denial did not say which one. A dispatch has its own limit under the host's longer hook timeout; Bash keeps 8 s.
        with open(os.path.join(ROOT, "hooks", "hooks.json")) as f:
            hooks = json.load(f)["hooks"]["PreToolUse"]
        host = next(h for h in hooks if h["matcher"] == "Task|Agent")["hooks"][0]["timeout"]
        self.assertGreaterEqual(host, 30)
        with open(os.path.join(ROOT, "scripts", "reef-guard.py")) as f:
            dispatch = float(re.search(r'DISPATCH_DEADLINE = .*or "([\d.]+)"', f.read()).group(1))
        self.assertLess(dispatch, host, "the guard decides a slow dispatch, never the host's timeout")
        with open(os.path.join(ROOT, "scripts", "reef-opencode.py")) as f:
            opencode = int(re.search(r"const DISPATCH_TIMEOUT_MS = (\d+);", f.read()).group(1))
        self.assertLess(dispatch * 1000, opencode, "OpenCode's dispatch timeout sits above the guard's limit too")
        env = {"REEF_GUARD_TEST_HANG": "9", "REEF_GUARD_DEADLINE": ""}
        d = tempfile.mkdtemp(prefix="reef-deadline.")
        r = guard({"tool_name": "Task", "cwd": d, "tool_input": {"subagent_type": "Explore", "prompt": "look"}}, env=env)
        self.assertNotIn("deadline", r.stderr, "nine seconds of checks fit a dispatch's limit")
        self.assertEqual(r.returncode, 0, r.stderr)
        t0 = time.monotonic()
        r = guard({"tool_name": "Bash", "cwd": d, "tool_input": {"command": "ls"}}, env=env)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertLess(time.monotonic() - t0, 12, "a Bash call keeps the 8 s limit")
        self.assertRegex(r.stderr, r"deadline of 8s exceeded in test-hang after \d", "the denial names the step that overran")
        r = guard({"tool_name": "Bash", "cwd": d, "tool_input": {"command": "ls"}}, env={"REEF_GUARD_TEST_HANG": "9", "REEF_GUARD_DEADLINE": "30"})
        self.assertRegex(r.stderr, r"deadline of 8s exceeded", "the override only lowers a limit: Bash stays under the host's 10 s")

    def test_hooks_json_carries_timeout_and_block_on_every_guard_matcher(self):
        with open(os.path.join(ROOT, "hooks", "hooks.json")) as f:
            hooks = json.load(f)["hooks"]["PreToolUse"]
        matchers = {h["matcher"] for h in hooks}
        self.assertTrue({"Bash", "Task|Agent", "Edit|Write|MultiEdit"} <= matchers, matchers)
        for h in hooks:
            for c in h["hooks"]:
                self.assertEqual(c.get("onFailure"), "block", h["matcher"])
                self.assertGreaterEqual(c.get("timeout", 0), 10, h["matcher"])
        task = next(h for h in hooks if h["matcher"] == "Task|Agent")["hooks"][0]["command"]
        self.assertIn("exit 2", task, "no python3 => a dispatch is denied, never allowed")


class GuardGuardsItself(unittest.TestCase):
    """1.5: the guard's own files and the protected config keys change only under a critical task or in the plugin repo."""

    def setUp(self):
        self.d = project({"gates": {"test": "true"}, "roles": ROLES, "caps": {"attempts": 3}}, {"007-demo.md": task_text(7, "demo", "full", "design")})
        os.makedirs(os.path.join(self.d, ".githooks"))
        with open(os.path.join(self.d, ".githooks", "pre-commit"), "w") as f:
            f.write("#!/bin/sh\n")

    def edit(self, path, **ti):
        ti.setdefault("file_path", os.path.join(self.d, path))
        return guard({"tool_name": "Edit" if "old_string" in ti else "Write", "cwd": self.d, "tool_input": ti})

    def inflight(self, tier):
        os.makedirs(os.path.join(self.d, ".reef", "inflight"), exist_ok=True)
        with open(os.path.join(self.d, ".reef", "inflight", "7"), "w") as f:
            json.dump({"id": 7, "tier": tier}, f)

    def test_full_task_editing_the_guard_denied_critical_allowed_plugin_root_allowed(self):
        self.inflight("full")
        for p in ("scripts/reef-guard.py", "scripts/reef-plan-check.py", ".githooks/pre-commit", "hooks/hooks.json"):
            with self.subTest(path=p):
                self.assertEqual(self.edit(p, content="x").returncode, 2)
                self.assertEqual(self.edit(p, old_string="a", new_string="b").returncode, 2)
                self.assertEqual(bash(self.d, f"echo x > {p}").returncode, 2)
                self.assertEqual(bash(self.d, f"sed -i s/a/b/ {p}").returncode, 2)
        self.assertEqual(bash(self.d, "python3 scripts/reef-init.py --accept scripts/reef-gate.sh").returncode, 0, "the allowed way to take a proposed script")
        self.assertEqual(bash(self.d, "cat scripts/reef-guard.py").returncode, 0)
        self.inflight("critical")
        self.assertEqual(self.edit("scripts/reef-guard.py", content="x").returncode, 0)
        self.assertEqual(bash(self.d, "echo x > scripts/reef-guard.py").returncode, 0)
        self.inflight("full")
        r = guard({"tool_name": "Write", "cwd": self.d, "tool_input": {"file_path": os.path.join(self.d, "scripts/reef-guard.py"), "content": "x"}},
                  env={"CLAUDE_PLUGIN_ROOT": self.d})
        self.assertEqual(r.returncode, 0, "Reef's own repository edits its own guard")

    def test_protected_config_keys_denied_other_keys_allowed(self):
        self.inflight("full")
        cfg_path = os.path.join(self.d, ".reef", "config.json")
        with open(cfg_path) as f:
            cfg = json.load(f)
        bad = dict(cfg, roles=dict(cfg["roles"], author="haiku"))
        self.assertEqual(self.edit(".reef/config.json", content=json.dumps(bad)).returncode, 2)
        bad = dict(cfg, caps={"attempts": 99})
        self.assertEqual(self.edit(".reef/config.json", content=json.dumps(bad)).returncode, 2)
        self.assertEqual(self.edit(".reef/config.json", old_string='"attempts": 3', new_string='"attempts": 30').returncode, 2)
        # the security review of v3 phase 4 (2026-10-26): the merge gate reads merge, ci and branches; the loop its cap —
        # an agent editing them would disarm the gate it is subject to
        for key, value in (("merge", {"by": "human"}), ("ci", {"feature_gate": "local"}), ("branches", {"base": "main", "release": "main"}), ("loop", {"rows_in_flight": 0})):
            with self.subTest(key=key):
                self.assertEqual(self.edit(".reef/config.json", content=json.dumps(dict(cfg, **{key: value}))).returncode, 2, key)
        good = dict(cfg, graph={"parallel": 4}, paths={"tasks": "tasks"})
        self.assertEqual(self.edit(".reef/config.json", content=json.dumps(good)).returncode, 0, "other keys are the owner's")
        self.assertEqual(self.edit(".reef/config.json", old_string='"attempts": 3', new_string='"attempts": 3 ').returncode, 0, "a no-op edit")
        self.assertEqual(self.edit(".reef/config.json", content="{not json").returncode, 2)
        self.inflight("critical")
        self.assertEqual(self.edit(".reef/config.json", content=json.dumps(bad)).returncode, 0)


class PlanReviewRounds(unittest.TestCase):
    def test_the_record_counts_the_rounds(self):
        # 2026-10-30 (row 7 on the current adoption): five review rounds; the hunter's pass has a cap, the reviewer's had none
        d = project({"gates": {"test": "true"}}, {"101-a.md": task_text(101, "demo", "full", "mech")})
        # the cap at 3 here, so the sequence FAIL, FAIL, PASS, FAIL counts 1, 2, 3, 1: a PASS closes the series (the review)
        with open(os.path.join(d, ".reef", "config.json"), "w") as f:
            json.dump({"gates": {"test": "true"}, "review": {"plan_rounds": 3}}, f)
        for verdict, rounds in (("FAIL", 1), ("FAIL", 2), ("PASS", 3), ("FAIL", 1)):
            r = subprocess.run([sys.executable, RECORD, "plan-review", "demo", verdict, "--root", d], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            rec = json.load(open(os.path.join(d, ".reef", "review", "plan-demo.json")))
            self.assertEqual(rec["rounds"], rounds, f"a review is a round; a PASS closes the series: {rec}")
            self.assertEqual(rec["verdict"], verdict)

    def test_a_pass_past_the_cap_is_the_owners_ruling_bound_to_his_footnote(self):
        # the security review: past the cap the reviewer runs no more — a bare PASS would dissolve the cap it answers; the
        # PASS carries the owner's footnote mark, present in the queue, like the hunter's `plan --decided`
        d = project({"gates": {"test": "true"}, "review": {"plan_rounds": 2}, "paths": {"queue": "docs/queue.md"}}, {"101-a.md": task_text(101, "demo", "full", "mech")})
        for _ in range(2):
            subprocess.run([sys.executable, RECORD, "plan-review", "demo", "FAIL", "--root", d], capture_output=True, text=True, check=True)
        r = subprocess.run([sys.executable, RECORD, "plan-review", "demo", "PASS", "--root", d], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0, "refused: " + r.stdout + r.stderr)
        self.assertIn("--decided", r.stdout + r.stderr)
        r = subprocess.run([sys.executable, RECORD, "plan-review", "demo", "PASS", "--root", d, "--decided", "68"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0, "no such footnote yet: " + r.stdout + r.stderr)
        os.makedirs(os.path.join(d, "docs"), exist_ok=True)
        with open(os.path.join(d, "docs", "queue.md"), "a") as f:
            f.write("\n⁶⁸ the owner rules: the finding is accepted as is (2026-10-30)\n")
        r = subprocess.run([sys.executable, RECORD, "plan-review", "demo", "PASS", "--root", d, "--decided", "68"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rec = json.load(open(os.path.join(d, ".reef", "review", "plan-demo.json")))
        self.assertEqual((rec["verdict"], rec["decided"]), ("PASS", "68"))


if __name__ == "__main__":
    unittest.main()
