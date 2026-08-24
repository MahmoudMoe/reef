"""Sabotage suite for scripts/reef-plan-check.py: the four advertised stacks must
all be able to pass, decoration must be impossible (vacuous OKs shown red), and
the stamp must ignore execution but never ignore the plan."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(ROOT, "scripts", "reef-plan-check.py")

TASK = """---
id: {id}
feature: demo
status: pending
complexity: mech
effort: medium
blocked-by: []
verify: gate-only
attempts: 0
dispatches: 0
last_failure_sig: ""
---
# {id} — demo

## Scope
x

## Acceptance Criteria
{acs}

## Out of scope

## Log
"""


def repo(tmp, acs="- {name} goes red then green".format(name="test_demo_works"), taskname="001-demo.md", extra_cfg=None):
    os.makedirs(os.path.join(tmp, "tasks", "done"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "docs", "adr"), exist_ok=True)
    cfg = {"gates": {"test": "true"}, "paths": {}}
    if extra_cfg:
        cfg.update(extra_cfg)
    os.makedirs(os.path.join(tmp, ".reef"), exist_ok=True)
    with open(os.path.join(tmp, ".reef", "config.json"), "w") as f:
        json.dump(cfg, f)
    with open(os.path.join(tmp, "tasks", taskname), "w") as f:
        f.write(TASK.format(id=re.match(r"R?0*(\d+)", taskname).group(1), acs=acs))
    with open(os.path.join(tmp, "CLAUDE.md"), "w") as f:
        f.write("# Demo project\nA brief.\n")
    return tmp


def run(root, *args):
    return subprocess.run([sys.executable, CHECK, root, *args], capture_output=True, text=True)


class Stacks(unittest.TestCase):
    """K3: every stack reef-init advertises must be able to phrase a passing criterion."""

    def check_ac(self, ac, should_pass):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp, acs=f"- {ac}")
        r = run(tmp)
        if should_pass:
            self.assertEqual(r.returncode, 0, f"{ac!r} rejected:\n{r.stdout}")
        else:
            self.assertEqual(r.returncode, 1, f"{ac!r} wrongly accepted:\n{r.stdout}")

    def test_pytest(self):
        self.check_ac("test_login_returns_401 goes red first", True)

    def test_jest(self):
        self.check_ac("it('rejects a bad token') in auth.test.ts goes red first", True)

    def test_go(self):
        self.check_ac("TestLoginHandler fails before the change", True)

    def test_rust(self):
        self.check_ac("auth::rejects_bad_token fails before the change", True)

    def test_prose_star_test_star_rejected(self):
        self.check_ac("the latest_figures view renders correctly", False)

    def test_no_test_at_all_rejected(self):
        self.check_ac("the feature works end to end", False)

    def test_config_override(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp, acs="- CHECK-042 proves it", extra_cfg={"plan": {"test_re": r"CHECK-\d+"}})
        self.assertEqual(run(tmp).returncode, 0)


class Decoration(unittest.TestCase):
    """Checks that could previously be satisfied without being true."""

    def test_empty_criteria_list_fails(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp, acs="")   # section exists, zero bullets
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("no criteria bullets", r.stdout)

    def test_star_bullets_are_seen(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp, acs="* nothing named here at all")
        self.assertEqual(run(tmp).returncode, 1, "a '*' bullet with no test must FAIL, not vanish")

    def test_template_decision_comment_fails(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        p = os.path.join(tmp, "tasks", "001-demo.md")
        text = open(p).read().replace("complexity: mech", "complexity: design").replace("verify: gate-only", "verify: judge")
        text = text.replace("## Scope\nx", "## Scope\nx\n\n## Decision\n<!-- design tasks: the HUMAN writes this -->")
        open(p, "w").write(text)
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("no human-written content", r.stdout)

    def test_human_ac_only_at_bullet_start_and_never_on_mech(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp, acs="- HUMAN AC: looks right in the browser\n- test_x_works goes red")
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("HUMAN AC on a gate-only", r.stdout)

    def test_all_manual_task_fails(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp, acs="- HUMAN AC: feels snappy")
        text_p = os.path.join(tmp, "tasks", "001-demo.md")
        t = open(text_p).read().replace("complexity: mech", "complexity: design").replace("verify: gate-only", "verify: judge")
        t = t.replace("## Scope\nx", "## Scope\nx\n\n## Decision\nhuman wrote this")
        open(text_p, "w").write(t)
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("no failing test = no task", r.stdout)

    def test_negative_attempts_fails(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        p = os.path.join(tmp, "tasks", "001-demo.md")
        with open(p) as f:
            t = f.read().replace("attempts: 0", "attempts: -3")
        with open(p, "w") as f:
            f.write(t)
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("non-negative", r.stdout)

    def test_stray_md_file_fails(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        open(os.path.join(tmp, "tasks", "notes.md"), "w").write("invisible before this check\n")
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("invisible", r.stdout)

    def test_adr_template_placeholder_fails(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        open(os.path.join(tmp, "docs", "adr", "0001-x.md"), "w").write(
            "# ADR 0001\n\nStatus: Proposed | Accepted | Superseded by NNNN\n\n## Context\nx\n")
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("placeholder", r.stdout)

    def test_no_adr_is_ok(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        self.assertEqual(run(tmp).returncode, 0, "a fresh bootstrap with zero ADRs must be able to pass")

    def test_open_heading_case_insensitive_and_scoped(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        brief = os.path.join(tmp, "CLAUDE.md")
        open(brief, "w").write("# Demo\n## open questions\n- who knows\n")
        self.assertEqual(run(tmp).returncode, 1, "lowercase 'open questions' must be caught")
        open(brief, "w").write("# Demo\n## OpenAPI notes\nfine\n```\n# Open Questions inside a fence\n```\n")
        self.assertEqual(run(tmp).returncode, 0, "OpenAPI / fenced content must not false-positive")


class Rollups(unittest.TestCase):
    def test_rollup_checked_and_stamped(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        with open(os.path.join(tmp, "tasks", "R01-fixups.md"), "w") as f:
            f.write(TASK.format(id="R1", acs="- test_rollup_fix goes red first"))
        r = run(tmp)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("R01-fixups.md", r.stdout)
        # and a BROKEN rollup must now be visible
        with open(os.path.join(tmp, "tasks", "R01-fixups.md"), "w") as f:
            f.write(TASK.format(id="R1", acs="- no test named"))
        self.assertEqual(run(tmp).returncode, 1)


class Stamp(unittest.TestCase):
    def test_execution_does_not_invalidate_plan_edit_does(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        self.assertEqual(run(tmp).returncode, 0)
        self.assertEqual(run(tmp, "--verify-stamp").returncode, 0)
        p = os.path.join(tmp, "tasks", "001-demo.md")
        # execution writes: status/attempts/dispatches/sig + Log — stamp must hold
        t = open(p).read().replace("status: pending", "status: done").replace("attempts: 0", "attempts: 2")
        t = t.replace("dispatches: 0", "dispatches: 4") + "\n## Log\n- ran\n"
        open(p, "w").write(t)
        self.assertEqual(run(tmp, "--verify-stamp").returncode, 0, "execution state must not invalidate the review")
        # moving to done/ must hold too (keyed by basename)
        shutil.move(p, os.path.join(tmp, "tasks", "done", "001-demo.md"))
        self.assertEqual(run(tmp, "--verify-stamp").returncode, 0, "completing a task must not invalidate the review")
        # a PLAN edit must break it
        p2 = os.path.join(tmp, "tasks", "done", "001-demo.md")
        with open(p2) as f:
            t2 = f.read()
        assert "## Scope" in t2
        with open(p2, "w") as f:
            f.write(t2.replace("## Scope\nx", "## Scope\nsomething sneaky"))
        self.assertEqual(run(tmp, "--verify-stamp").returncode, 1, "a plan edit MUST invalidate the review")


if __name__ == "__main__":
    unittest.main()
