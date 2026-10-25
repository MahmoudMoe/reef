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


class MaxAcs(unittest.TestCase):
    def test_unset_warns_above_eight_and_set_fails(self):
        # 2026-10-17: 1302 carried 21 criteria; one slice a verifier judges in one sitting is the unit
        acs = "\n".join(f"- test_c{i} goes red then green" for i in range(9))
        tmp = repo(tempfile.mkdtemp(prefix="reef-pc."), acs=acs)
        r = run(tmp)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("9 acceptance criteria (8 is the slice", r.stdout)
        tmp = repo(tempfile.mkdtemp(prefix="reef-pc."), acs=acs, extra_cfg={"plan": {"max_acs": 8}})
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("9 acceptance criteria > plan.max_acs 8 — split the task", r.stdout)
        tmp = repo(tempfile.mkdtemp(prefix="reef-pc."), acs="\n".join(f"- test_c{i} goes red then green" for i in range(8)), extra_cfg={"plan": {"max_acs": 8}})
        self.assertEqual(run(tmp).returncode, 0)


class Quiet(unittest.TestCase):
    def test_quiet_prints_fail_and_summary_only(self):
        tmp = repo(tempfile.mkdtemp(prefix="reef-pc."))
        r = run(tmp, "--quiet")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("OK   ", r.stdout)
        self.assertRegex(r.stdout, r"\d+ checks, 0 failed")
        with open(os.path.join(tmp, "tasks", "001-demo.md")) as f:
            t = f.read()
        with open(os.path.join(tmp, "tasks", "001-demo.md"), "w") as f:
            f.write(t.replace("status: pending", "status: nonsense"))
        r = run(tmp, "--quiet")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL", r.stdout)
        self.assertNotIn("OK   ", r.stdout)


class DoneFolderAndStatusAgree(unittest.TestCase):
    def test_done_folder_without_done_status_and_the_reverse_fail(self):
        # first contact (2026-10-17): 103 was merged and moved to done/ with `status: in-progress` and no Log line; the
        # orchestrator caught it by eye. The folder and the status are one fact — the checker holds them together.
        tmp = repo(tempfile.mkdtemp(prefix="reef-pc."))
        p = os.path.join(tmp, "tasks", "001-demo.md")
        shutil.move(p, os.path.join(tmp, "tasks", "done", "001-demo.md"))
        r = run(tmp)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("under tasks/done/ with status='pending'", r.stdout)
        p2 = os.path.join(tmp, "tasks", "done", "001-demo.md")
        with open(p2) as f:
            done_text = f.read().replace("status: pending", "status: done")
        with open(p2, "w") as f:
            f.write(done_text)
        self.assertEqual(run(tmp).returncode, 0, "done/ + status: done is the close-out's shape")
        shutil.move(p2, p)
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("status: done but not under tasks/done/", r.stdout)


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
        self.check_ac("auth_tests::rejects_bad_token fails before the change", True)

    def test_rust_prose_paths_rejected(self):
        # round-2 finding: a bare foo::bar matched prose like std::vec
        self.check_ac("uses std::vec and tokio::spawn correctly", False)

    def test_prose_star_test_star_rejected(self):
        self.check_ac("the latest_figures view renders correctly", False)

    def test_no_test_at_all_rejected(self):
        self.check_ac("the feature works end to end", False)

    def test_config_override(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp, acs="- CHECK-042 proves it", extra_cfg={"plan": {"test_re": r"CHECK-\d+"}})
        self.assertEqual(run(tmp).returncode, 0)


class RefactorKind(unittest.TestCase):
    """0.7.2 (ai-coach, item 15): `kind: refactor` names what it splits and the size it ends under; any other kind is refused."""

    def task(self, extra):
        d = repo(tempfile.mkdtemp(prefix="reef-pc-refactor."))
        with open(os.path.join(d, "tasks", "001-demo.md")) as f:
            t = f.read()
        with open(os.path.join(d, "tasks", "001-demo.md"), "w") as f:
            f.write(t.replace("attempts: 0\n", "attempts: 0\n" + extra))
        return run(d)

    def test_a_refactor_task_needs_its_splits_line_and_an_unknown_kind_is_refused(self):
        r = self.task("kind: refactor\n")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("kind: refactor needs `splits: <file>[, <file>] under <N> lines`", r.stdout)
        r = self.task("kind: refactor\nsplits: src/lib/interface/ar.ts, src/lib/big.ts under 400 lines\n")
        self.assertEqual(r.returncode, 0, r.stdout)
        r = self.task("kind: feature\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("kind='feature' not in ['refactor']", r.stdout)


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

    def test_rules_prints_the_projects_numbers_in_under_40_lines(self):
        # 0.7 (docs/design/plan-cost.md): the planner runs --rules once instead of reading this script's source
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp, extra_cfg={"writing": {"sentence_words": 17, "criterion_words": 41}, "plan": {"max_tasks": 7}})
        r = run(tmp, "--rules")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertLessEqual(len(r.stdout.splitlines()), 40)
        for needle in ("sentence_words 17", "criterion_words 41", "max_tasks 7", "Proof", "touches", "Approve plan"):
            self.assertIn(needle, r.stdout)
        self.assertNotIn("FAIL", r.stdout)

    def test_adr_readme_is_not_an_adr(self):
        # 0.7: reef-init writes adr/README.md on every fresh 0.6 project; it has no Status and must not
        # be read as an undecided ADR, or the first plan check of every new project fails
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        for d in (os.path.join(tmp, "docs", "adr"), os.path.join(tmp, "reef", "architecture", "adr")):
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "README.md"), "w") as f:
                f.write("# Architecture decision records\n\nOne short file per decision.\n")
        r = run(tmp)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("README.md", r.stdout)

    def test_commonmark_bullet_indentation(self):
        # round-3 overturned round-2 here: per CommonMark, 0-3 leading spaces is a
        # SIBLING list item (a real criterion); 4+ spaces is a continuation
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp, acs="- test_a covers the cases\n 2) untested sibling criterion")
        self.assertEqual(run(tmp).returncode, 1, "a 1-space-indented numbered item is a criterion and it names no test")
        tmp2 = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp2, acs="- test_a covers the cases:\n    2) genuinely a wrapped continuation line")
        self.assertEqual(run(tmp2).returncode, 0)

    def test_duplicate_frontmatter_key_fails(self):
        # round-3: dup keys read first-wins in one reader and last-wins in another
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        p = os.path.join(tmp, "tasks", "001-demo.md")
        with open(p) as f:
            t = f.read()
        with open(p, "w") as f:
            f.write(t.replace("attempts: 0\n", "attempts: 0\nattempts: 9\n"))
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("duplicate frontmatter key", r.stdout)

    def test_log_must_be_last_section(self):
        # round-3: a '## Log' above plan sections exempted them from the stamp
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        p = os.path.join(tmp, "tasks", "001-demo.md")
        with open(p) as f:
            t = f.read()
        with open(p, "w") as f:
            f.write(t.replace("## Scope\nx", "## Log\n- early\n\n## Scope\nx"))
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("LAST section", r.stdout)

    def test_reviewer_notes_are_outside_the_digest_and_only_the_log_may_follow(self):
        # 2026-10-17: 28 plan-review advisories applied as plan edits re-ran three hunters, approvals and reviews.
        # Advisories now ride in `## Reviewer notes`, which the stamp ignores like the Log.
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        p = os.path.join(tmp, "tasks", "001-demo.md")
        before = run(tmp, "--digest", "--feature", "demo").stdout.split()[-1]
        with open(p) as f:
            t = f.read()
        with open(p, "w") as f:
            f.write(t.replace("## Log\n", "## Reviewer notes\n- A3: AC-12 is only true until 203 lands — assert it per task\n\n## Log\n"))
        self.assertEqual(run(tmp).returncode, 0, run(tmp).stdout)
        self.assertEqual(run(tmp, "--digest", "--feature", "demo").stdout.split()[-1], before, "notes change no digest")
        with open(p, "a") as f:
            f.write("- attempt 1\n")
        self.assertEqual(run(tmp, "--digest", "--feature", "demo").stdout.split()[-1], before, "the Log after the notes is still the Log")
        # a plan section hidden after the notes would be edited invisibly: refused
        with open(p, "w") as f:
            f.write(t.replace("## Log\n", "## Reviewer notes\n- x\n\n## Scope\nmore\n\n## Log\n"))
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("only ## Log may follow ## Reviewer notes", r.stdout)

    def test_adr_status_line_is_outside_the_digest(self):
        # 2026-10-17: "Status: Accepted (number at merge)" written after the gate voided two approvals
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        adr = os.path.join(tmp, "docs", "adr", "draft-demo.md")
        with open(adr, "w") as f:
            f.write("# Demo boundary\n\nStatus: Proposed (number at merge)\n\n## Context\none\n\n## Decision\ntwo\n")
        before = run(tmp, "--digest", "--feature", "demo").stdout.split()[-1]
        with open(adr, "w") as f:
            f.write("# Demo boundary\n\nStatus: Accepted (number at merge)\n\n## Context\none\n\n## Decision\ntwo\n")
        self.assertEqual(run(tmp, "--digest", "--feature", "demo").stdout.split()[-1], before)
        with open(adr, "w") as f:
            f.write("# Demo boundary\n\nStatus: Accepted (number at merge)\n\n## Context\none\n\n## Decision\nthree\n")
        self.assertNotEqual(run(tmp, "--digest", "--feature", "demo").stdout.split()[-1], before, "a decision still counts")

    def test_lowercase_log_heading_still_cut_from_stamp(self):
        # round-3: '## log' hashed the log body, so every append staled the plan
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        p = os.path.join(tmp, "tasks", "001-demo.md")
        with open(p) as f:
            t = f.read()
        with open(p, "w") as f:
            f.write(t.replace("## Log\n", "## log\n"))
        self.assertEqual(run(tmp).returncode, 0)
        with open(p, "a") as f:
            f.write("- executed attempt 1\n")
        self.assertEqual(run(tmp, "--verify-stamp").returncode, 0,
                         "a log append under '## log' must not stale the stamp")

    def test_negative_dispatches_fails(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        p = os.path.join(tmp, "tasks", "001-demo.md")
        with open(p) as f:
            t = f.read()
        with open(p, "w") as f:
            f.write(t.replace("dispatches: 0", "dispatches: -999"))
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("dispatches", r.stdout)

    def test_adr_without_status_fails(self):
        # round-3: an ADR that never wrote a Status passed as 'none Proposed'
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        with open(os.path.join(tmp, "docs", "adr", "0001-x.md"), "w") as f:
            f.write("# ADR 0001\n\n## Context\nundecided\n")
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("no Status", r.stdout)

    def test_adr_fenced_template_quote_ignored(self):
        # round-3: a quoted template inside ``` outranked the real '## Status/Accepted'
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        with open(os.path.join(tmp, "docs", "adr", "0001-x.md"), "w") as f:
            f.write("# ADR 0001\n\n## Status\n\nAccepted\n\n## Context\nquoting the template:\n"
                    "```\nStatus: Proposed | Accepted | Superseded by NNNN\n```\n")
        self.assertEqual(run(tmp).returncode, 0)

    def test_adr_status_heading_layout_detected(self):
        # Nygard/MADR layout: '## Status' heading with the value on the next line
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        with open(os.path.join(tmp, "docs", "adr", "0001-x.md"), "w") as f:
            f.write("# ADR 0001\n\n## Status\n\nProposed\n\n## Context\nx\n")
        r = run(tmp)
        self.assertEqual(r.returncode, 1, "heading-layout Proposed must be caught")
        self.assertIn("Proposed", r.stdout)

    def test_adr_accepted_mentioning_proposed_is_ok(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        with open(os.path.join(tmp, "docs", "adr", "0001-x.md"), "w") as f:
            f.write("# ADR 0001\n\nStatus: Accepted (was Proposed until 2026-08)\n\n## Context\nx\n")
        self.assertEqual(run(tmp).returncode, 0)

    def test_rollup_dangling_blocked_by_fails(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        body = TASK.format(id="R1", acs="- test_rollup_fix goes red first").replace("blocked-by: []", "blocked-by: [99]")
        with open(os.path.join(tmp, "tasks", "R01-fixups.md"), "w") as f:
            f.write(body)
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing task id", r.stdout)

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
    def test_rollup_creation_and_edits_never_stale_the_stamp(self):
        # round-2 finding: rollups are EXECUTION artifacts; hashing them denied the
        # very dispatch they were created for
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        self.assertEqual(run(tmp).returncode, 0)
        with open(os.path.join(tmp, "tasks", "R01-fixups.md"), "w") as f:
            f.write(TASK.format(id="R1", acs="- test_rollup_fix goes red first"))
        self.assertEqual(run(tmp, "--verify-stamp").returncode, 0,
                         "creating a rollup mid-run must not stale the plan stamp")

    def test_guard_dispatches_append_never_stales_the_stamp(self):
        # round-2 finding: the odometer append changed the digest because the strip
        # kept the newline
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        self.assertEqual(run(tmp).returncode, 0)
        p = os.path.join(tmp, "tasks", "001-demo.md")
        with open(p) as f:
            t = f.read()
        with open(p, "w") as f:   # simulate reef-guard appending the odometer key
            f.write(t.replace("---\n# ", "dispatches: 3\n---\n# ", 1))
        self.assertEqual(run(tmp, "--verify-stamp").returncode, 0,
                         "the guard's own odometer write must not stale the stamp")

    def test_login_heading_is_plan_content_not_log(self):
        # round-2 finding: '\n## Log' prefix-matched '## Login' and hid plan content
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp, acs="- test_login_works goes red first")
        p = os.path.join(tmp, "tasks", "001-demo.md")
        with open(p) as f:
            t = f.read()
        with open(p, "w") as f:
            f.write(t.replace("## Out of scope", "## Login flow\nplan detail here\n\n## Out of scope"))
        self.assertEqual(run(tmp).returncode, 0)
        with open(p) as f:
            t = f.read()
        with open(p, "w") as f:
            f.write(t.replace("plan detail here", "sneaky post-approval edit"))
        self.assertEqual(run(tmp, "--verify-stamp").returncode, 1,
                         "an edit under '## Login' is a PLAN edit and must stale the stamp")

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


def add_task(tmp, name, tid, feature, acs="- test_{f}_{i}_works goes red first"):
    text = TASK.format(id=tid, acs=acs.format(f=feature, i=tid)).replace("feature: demo", f"feature: {feature}")
    with open(os.path.join(tmp, "tasks", name), "w") as f:
        f.write(text)
    return os.path.join(tmp, "tasks", name)


def edit(path, old, new):
    with open(path) as f:
        t = f.read()
    assert old in t, f"{old!r} not in {path}"
    with open(path, "w") as f:
        f.write(t.replace(old, new))


ADV = os.path.join(ROOT, "scripts", "reef-adversarial")
DESIGN_TASK = TASK.replace("complexity: mech", "complexity: design\ntier: critical").replace("verify: gate-only", "verify: judge") \
    .replace("## Scope\nx", "## Scope\nx\n\n## Decision\nhuman wrote this")


class PathDecidesTheReview(unittest.TestCase):
    """Workflow v3, phase 3a (2026-10-25): the plan-reviewer agent reviewed every row heavier than light — one more judge on
    rows whose risk the tier already said was ordinary. On the FAST path (every task light or full, no auth/pii/money/
    migration touch) the deterministic check is the review: --verify-stamp says `review: not required`, --needs-agent
    exits 3. A risk touch or a design/critical task is the CRITICAL path: the record is required, as before."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reef-pc-path.")
        repo(self.tmp)
        self.p = os.path.join(self.tmp, "tasks", "002-full.md")
        with open(self.p, "w") as f:
            f.write(DESIGN_TASK.replace("tier: critical", "tier: full").format(id=2, acs="- test_full_works goes red then green"))
        self.assertEqual(run(self.tmp).returncode, 0, run(self.tmp).stdout)

    def test_fast_path_needs_no_plan_reviewer_and_a_risk_touch_makes_it_critical(self):
        out = run(self.tmp, "--verify-stamp", "--feature", "demo").stdout
        self.assertIn("review: not required for 'demo' (fast path: tiers light, full; no risk touch", out)
        r = run(self.tmp, "--needs-agent", "--feature", "demo")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("plan-reviewer: none (fast path", r.stdout)
        edit(self.p, "tier: full\n", "tier: design\n")   # a risk touch forces at least design, so a design task is the critical path's shape
        self.assertEqual(run(self.tmp).returncode, 0, run(self.tmp).stdout)
        out = run(self.tmp, "--verify-stamp", "--feature", "demo").stdout
        self.assertIn("review: MISSING for 'demo'", out, "a design task is the critical path: the plan-reviewer's record is required")
        r = run(self.tmp, "--needs-agent", "--feature", "demo")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("plan-reviewer: model=", r.stdout)


class HunterStampOutsideTheDigest(unittest.TestCase):
    """2026-10-18 (qassimha): `plan --decided` after Approve and a stamp migration changed the approval digest of a plan
    nobody had edited; and 202/203 reached the gate with stamps their review-round edits had staled, unnamed."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reef-pc-hunter.")
        repo(self.tmp)
        self.p = os.path.join(self.tmp, "tasks", "001-demo.md")
        with open(self.p, "w") as f:
            f.write(DESIGN_TASK.format(id=1, acs="- test_demo_works goes red then green"))
        self.assertEqual(run(self.tmp).returncode, 0, run(self.tmp).stdout)
        self.report = os.path.join(self.tmp, "hunt.md")
        with open(self.report, "w") as f:
            f.write("RUN: agent=loophole-hunter task=1 pass=plan round=1\nDEFECT: x\nBLOCKER: none\nVERDICT: PASS\n")

    def digest(self):
        return run(self.tmp, "--digest", "--feature", "demo").stdout.split()[-1]

    def hunter_line(self):
        out = run(self.tmp, "--verify-stamp", "--feature", "demo").stdout
        m = re.search(r"^hunter: .*$", out, re.M)
        return m.group(0) if m else out

    def test_the_stamp_and_a_decision_change_neither_the_digest_nor_the_review_stamp(self):
        before = self.digest()
        self.assertIn("hunter: MISSING 1", self.hunter_line())
        r = subprocess.run([sys.executable, ADV, self.p, "plan", self.report], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.digest(), before, "the hunter's plan pass is bound to the digest, not inside it")
        self.assertEqual(run(self.tmp, "--verify-stamp", "--feature", "demo").stdout.count("stamp: MATCH"), 1)
        self.assertIn("hunter: OK (1 critical task(s))", self.hunter_line())
        r = subprocess.run([sys.executable, ADV, self.p, "plan", "--decided", "³⁰"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.digest(), before, "an owner ruling re-stamps without voiding the approval of the same text")

    def test_a_plan_edit_after_the_pass_is_named_stale(self):
        subprocess.run([sys.executable, ADV, self.p, "plan", self.report], capture_output=True, text=True)
        edit(self.p, "## Scope\nx", "## Scope\nx, widened in the review round")
        self.assertEqual(run(self.tmp).returncode, 0)   # the review round re-stamps the review; the hunter's record stays
        self.assertRegex(self.hunter_line(), r"^hunter: STALE 1 — .*--decided")

    def test_a_mech_task_and_a_done_task_need_no_hunter(self):
        with open(self.p, "w") as f:
            f.write(TASK.format(id=1, acs="- test_demo_works goes red then green"))
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertIn("hunter: n/a", self.hunter_line())



class ExternalApiFacts(unittest.TestCase):
    """2026-10-18: the 203 implementer spent 35 of 54 turns on the Anthropic SDK because the task named the API and
    resources: [heavy] carried no fact. A task naming an SDK/API without a doc URL or a version in resources: is a WARN."""

    def warns(self, scope, resources="[]", extra_cfg=None):
        tmp = tempfile.mkdtemp(prefix="reef-pc-api.")
        repo(tmp, extra_cfg=extra_cfg)
        p = os.path.join(tmp, "tasks", "001-demo.md")
        with open(p) as f:
            t = f.read()
        with open(p, "w") as f:
            f.write(t.replace("## Scope\nx", f"## Scope\n{scope}").replace("blocked-by: []\n", f"blocked-by: []\nresources: {resources}\n"))
        r = run(tmp)
        self.assertEqual(r.returncode, 0, r.stdout)
        return [l for l in r.stdout.splitlines() if l.startswith("WARN") and "external API" in l]

    def test_an_sdk_without_facts_warns_and_a_doc_or_version_clears_it(self):
        w = self.warns("Decode the receipt with @anthropic-ai/sdk (vision).")
        self.assertEqual(len(w), 1, w)
        self.assertIn("@anthropic-ai/sdk", w[0])
        self.assertIn("resources:", w[0])
        self.assertEqual(self.warns("Decode the receipt with @anthropic-ai/sdk (vision).", "[\"@anthropic-ai/sdk 0.135.0\", heavy]"), [])
        self.assertEqual(self.warns("Call the Stripe API for the refund.", "[\"https://docs.stripe.com/api/refunds\"]"), [])
        self.assertEqual(self.warns("Call the Stripe API for the refund."), self.warns("Call the Stripe API for the refund.") and self.warns("Call the Stripe API for the refund."))
        self.assertEqual(len(self.warns("POST to https://api.example.com/v2/items with fetch.")), 1)

    def test_a_local_api_route_is_not_an_external_api_and_the_pattern_is_configurable(self):
        self.assertEqual(self.warns("Add the /api/bills route and its handler."), [], "a Next.js API route is the project's own")
        self.assertEqual(len(self.warns("Talk to the Acme billing service.", extra_cfg={"plan": {"external_api_re": "acme billing"}})), 1)


class FeatureStamp(unittest.TestCase):
    """0.4.0: the stamp hashes only the tasks of ONE feature plus the ADRs, so merging the
    integration branch (other features' tasks, the brief, the glossary) stales nothing."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(self.tmp)
        add_task(self.tmp, "002-other.md", 2, "other")
        self.assertEqual(run(self.tmp).returncode, 0)

    def test_other_feature_edit_does_not_stale_this_feature(self):
        edit(os.path.join(self.tmp, "tasks", "002-other.md"), "## Scope\nx", "## Scope\nedited elsewhere")
        self.assertEqual(run(self.tmp, "--verify-stamp", "--feature", "demo").returncode, 0,
                         "another feature's plan edit must not stale this feature")
        self.assertEqual(run(self.tmp, "--verify-stamp", "--feature", "other").returncode, 1,
                         "the edited feature itself must be stale")
        self.assertEqual(run(self.tmp, "--verify-stamp").returncode, 1,
                         "without --feature every feature must match")

    def test_new_feature_arriving_does_not_stale_this_feature(self):
        add_task(self.tmp, "003-third.md", 3, "third")
        self.assertEqual(run(self.tmp, "--verify-stamp", "--feature", "demo").returncode, 0)
        self.assertEqual(run(self.tmp, "--verify-stamp", "--feature", "third").returncode, 1)

    def test_adr_edit_stales_every_feature(self):
        adr = os.path.join(self.tmp, "docs", "adr", "0001-x.md")
        with open(adr, "w") as f:
            f.write("# ADR 0001\n\nStatus: Accepted\n\n## Context\nx\n")
        self.assertEqual(run(self.tmp, "--verify-stamp", "--feature", "demo").returncode, 1)
        self.assertEqual(run(self.tmp, "--verify-stamp", "--feature", "other").returncode, 1)

    def test_this_feature_edit_stales_it(self):
        edit(os.path.join(self.tmp, "tasks", "001-demo.md"), "## Scope\nx", "## Scope\nsneaky")
        self.assertEqual(run(self.tmp, "--verify-stamp", "--feature", "demo").returncode, 1)

    def test_moving_a_task_to_another_feature_stales_both(self):
        edit(os.path.join(self.tmp, "tasks", "002-other.md"), "feature: other", "feature: demo")
        self.assertEqual(run(self.tmp, "--verify-stamp", "--feature", "demo").returncode, 1)
        self.assertEqual(run(self.tmp, "--verify-stamp", "--feature", "other").returncode, 1)

    def test_documented_scope_brief_glossary_config_do_not_stale(self):
        # DELIBERATE (README, enforcement map): merges touch the brief, the glossary and the
        # config on every integration; hashing them re-reviewed every feature per merge
        with open(os.path.join(self.tmp, "CLAUDE.md"), "a") as f:
            f.write("\nA line another feature's merge added.\n")
        os.makedirs(os.path.join(self.tmp, "docs"), exist_ok=True)
        with open(os.path.join(self.tmp, "docs", "glossary.md"), "w") as f:
            f.write("| Term | Definition |\n|---|---|\n| Other | from another feature |\n")
        self.assertEqual(run(self.tmp, "--verify-stamp", "--feature", "demo").returncode, 0)

    def test_unknown_option_fails_loudly(self):
        r = run(self.tmp, "--verify-stmap")
        self.assertEqual(r.returncode, 1)
        self.assertIn("unknown option", r.stdout)


class StampTracking(unittest.TestCase):
    def test_tracked_stamp_fails(self):
        # a committed stamp travels across branches and conflicts on every merge; it is
        # per-worktree state and must be gitignored
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        subprocess.run(["git", "init", "-q", "-b", "main", tmp], check=True)
        self.assertEqual(run(tmp).returncode, 0)
        subprocess.run(["git", "-C", tmp, "add", "tasks/.plan-review.json"], check=True)
        r = run(tmp)
        self.assertEqual(r.returncode, 1, "a stamp tracked by git must fail the check")
        self.assertIn("tracked", r.stdout)

    def test_untracked_stamp_ok(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        subprocess.run(["git", "init", "-q", "-b", "main", tmp], check=True)
        self.assertEqual(run(tmp).returncode, 0)
        self.assertEqual(run(tmp).returncode, 0)


class DraftAdr(unittest.TestCase):
    def write_adr(self, tmp, name, status):
        with open(os.path.join(tmp, "docs", "adr", name), "w") as f:
            f.write(f"# ADR\n\nStatus: {status}\n\n## Context\nx\n")

    def test_draft_adr_may_be_proposed(self):
        # parallel items draft ADRs as draft-<item>-<slug>.md; the number is given at merge
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        self.write_adr(tmp, "draft-333-model-route.md", "Proposed")
        r = run(tmp)
        self.assertEqual(r.returncode, 0, f"a draft ADR must be exempt from the Proposed check:\n{r.stdout}")

    def test_numbered_adr_still_cannot_be_proposed(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        self.write_adr(tmp, "draft-333-model-route.md", "Proposed")
        self.write_adr(tmp, "0007-settled.md", "Proposed")
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("0007-settled.md", r.stdout)
        self.assertNotIn("draft-333", r.stdout.split("ADR still Proposed")[1])

    def test_draft_adr_placeholder_and_missing_status_still_fail(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        self.write_adr(tmp, "draft-1-x.md", "Proposed | Accepted | Superseded by NNNN")
        self.assertEqual(run(tmp).returncode, 1)
        tmp2 = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp2)
        with open(os.path.join(tmp2, "docs", "adr", "draft-2-y.md"), "w") as f:
            f.write("# ADR\n\n## Context\nno status\n")
        self.assertEqual(run(tmp2).returncode, 1)

    def test_accepted_number_at_merge_is_ok(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        self.write_adr(tmp, "draft-333-model-route.md", "Accepted (number at merge)")
        self.assertEqual(run(tmp).returncode, 0)


class Config(unittest.TestCase):
    def check(self, extra, should_pass, needle=None):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp, extra_cfg=extra)
        r = run(tmp)
        self.assertEqual(r.returncode, 0 if should_pass else 1, f"{extra}:\n{r.stdout}")
        if needle:
            self.assertIn(needle, r.stdout)
        return r

    def test_merge_by_must_be_human_or_loop(self):
        self.check({"merge": {"by": "robot"}}, False, "merge.by")

    def test_ci_feature_gate_must_be_ci_or_local(self):
        self.check({"ci": {"feature_gate": "sometimes"}}, False, "ci.feature_gate")

    def test_loop_merge_into_the_release_branch_fails(self):
        # merge.by=loop merges into the integration branch only; with base == release the
        # loop would merge releases, which stay the human's
        self.check({"merge": {"by": "loop"}}, False, "release")
        self.check({"merge": {"by": "loop"}, "branches": {"base": "develop", "release": "main"}}, True)

    def test_defaults_pass(self):
        self.check({"merge": {"by": "human"}, "ci": {"feature_gate": "local"}}, True)

    def test_gates_full_alone_is_a_gate(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        with open(os.path.join(tmp, ".reef", "config.json"), "w") as f:
            json.dump({"gates": {"fast": "", "full": "true"}, "paths": {}}, f)
        r = run(tmp)
        self.assertEqual(r.returncode, 0, f"gates.full alone must count as the gate:\n{r.stdout}")

    def test_gates_fast_alone_is_not_a_full_gate(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        with open(os.path.join(tmp, ".reef", "config.json"), "w") as f:
            json.dump({"gates": {"fast": "true"}, "paths": {}}, f)
        self.assertEqual(run(tmp).returncode, 1)

    def test_plan_reviewer_model_printed_from_config_on_the_critical_path(self):
        # changed on purpose for v3 phase 3a (2026-10-25): the fixture's one mech task is the fast path, which dispatches no
        # plan-reviewer; the configured model is printed for a plan on the critical path
        r = self.check({"roles": {"plan_reviewer": "opus"}}, True)
        self.assertIn("plan-reviewer: none (fast path", r.stdout)
        tmp = repo(tempfile.mkdtemp(prefix="reef-pc."), extra_cfg={"roles": {"plan_reviewer": "opus"}})
        with open(os.path.join(tmp, "tasks", "002-crit.md"), "w") as f:
            f.write(DESIGN_TASK.format(id=2, acs="- test_crit_works goes red then green"))
        r = run(tmp)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("plan-reviewer: model=opus", r.stdout)

    def test_plan_reviewer_model_defaults_to_agent_default(self):
        tmp = repo(tempfile.mkdtemp(prefix="reef-pc."))
        with open(os.path.join(tmp, "tasks", "002-crit.md"), "w") as f:
            f.write(DESIGN_TASK.format(id=2, acs="- test_crit_works goes red then green"))
        r = run(tmp)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("plan-reviewer: model=opus", r.stdout)


class MaxWords(unittest.TestCase):
    def test_task_over_max_words_fails(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp, extra_cfg={"plan": {"max_words": 20}})
        edit(os.path.join(tmp, "tasks", "001-demo.md"), "## Scope\nx", "## Scope\n" + "word " * 40)
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("max_words", r.stdout)

    def test_log_does_not_count_and_unset_means_no_limit(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp, extra_cfg={"plan": {"max_words": 60}})
        with open(os.path.join(tmp, "tasks", "001-demo.md"), "a") as f:
            f.write("log " * 500)
        self.assertEqual(run(tmp).returncode, 0, "the Log is execution history, not plan length")
        tmp2 = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp2)
        edit(os.path.join(tmp2, "tasks", "001-demo.md"), "## Scope\nx", "## Scope\n" + "word " * 2000)
        self.assertEqual(run(tmp2).returncode, 0)
class BriefPointer(unittest.TestCase):
    """0.5.0: reef-init writes a one-line CLAUDE.md pointer; the brief the checks read is AGENTS.md."""

    def test_pointer_claude_md_yields_to_agents_md(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        with open(os.path.join(tmp, "CLAUDE.md"), "w") as f:
            f.write("See [AGENTS.md](AGENTS.md) — the single instruction layer.\n")
        with open(os.path.join(tmp, "AGENTS.md"), "w") as f:
            f.write("# brief\n\n## Open questions\n- unsettled\n")
        r = run(tmp)
        self.assertEqual(r.returncode, 1, "an open-questions heading in AGENTS.md hid behind the CLAUDE.md pointer")
        self.assertIn("AGENTS.md: open-questions heading remains", r.stdout)

    def test_real_claude_md_still_wins(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)   # writes a real CLAUDE.md brief
        with open(os.path.join(tmp, "AGENTS.md"), "w") as f:
            f.write("# other\n\n## Open questions\n- x\n")
        self.assertEqual(run(tmp).returncode, 0)


class TierWordCap(unittest.TestCase):
    """0.5.0: writing.task_words[tier] is the task file's word cap (one home); plan.max_words is the fallback."""

    def test_light_cap_applies_to_mech_tasks(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp, acs="- test_demo_works goes red first; " + " ".join(["word"] * 30),
             extra_cfg={"writing": {"task_words": {"light": 20, "full": 500}}, "plan": {"max_words": 0}})
        r = run(tmp)
        self.assertEqual(r.returncode, 1, "a mech (light) task over writing.task_words.light must fail")
        self.assertIn("writing.task_words.light 20", r.stdout)
        p = os.path.join(tmp, "tasks", "001-demo.md")
        with open(p) as f:
            t = f.read()
        with open(p, "w") as f:   # declare full: the full cap (500) applies
            f.write(t.replace("complexity: mech", "complexity: design\ntier: full").replace("verify: gate-only", "verify: judge")
                     .replace("## Scope", "## Decision\nhuman wrote this\n\n## Scope"))
        self.assertEqual(run(tmp).returncode, 0)

    def test_bad_task_words_fails_loudly(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp, extra_cfg={"writing": {"task_words": {"light": "many"}}})
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("writing.task_words", r.stdout)


class Graph05(unittest.TestCase):
    """0.5.0: the graph's execution keys never stale the plan; the tier matches the complexity."""

    def _edit(self, tmp, old, new):
        p = os.path.join(tmp, "tasks", "001-demo.md")
        with open(p) as f:
            t = f.read()
        assert old in t, old
        with open(p, "w") as f:
            f.write(t.replace(old, new, 1))

    def test_worktree_and_in_progress_never_stale_the_stamp(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        self.assertEqual(run(tmp).returncode, 0)
        # what reef-graph worktree and the guard write at dispatch
        self._edit(tmp, "status: pending", "status: in-progress")
        self._edit(tmp, "---\n# ", "worktree: .reef/worktrees/1\n---\n# ")
        self.assertEqual(run(tmp, "--verify-stamp").returncode, 0,
                         "dispatch state (in-progress, worktree:) must not force a plan re-review")

    def test_resources_are_plan_content(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        self.assertEqual(run(tmp).returncode, 0)
        self._edit(tmp, "blocked-by: []", "blocked-by: []\nresources: [db]")
        self.assertEqual(run(tmp, "--verify-stamp").returncode, 1,
                         "declaring a new shared resource changes the collision plan — re-review")
        self._edit(tmp, "resources: [db]", "resources: db")
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("resources not a list", r.stdout)

    def test_tier_must_match_complexity(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        self._edit(tmp, "blocked-by: []", "blocked-by: []\ntier: full")
        r = run(tmp)
        self.assertEqual(r.returncode, 1, "a mech task cannot claim the full tier (mech <=> light)")
        self.assertIn("tier full on a mech task", r.stdout)
        self._edit(tmp, "tier: full", "tier: light")
        self.assertEqual(run(tmp).returncode, 0)
        self._edit(tmp, "tier: light", "tier: cheap")
        self.assertIn("tier='cheap' not in", run(tmp).stdout)

    def test_light_tier_on_design_task_fails(self):
        tmp = tempfile.mkdtemp(prefix="reef-pc.")
        repo(tmp)
        self._edit(tmp, "complexity: mech", "complexity: design\ntier: light")
        self._edit(tmp, "verify: gate-only", "verify: judge")
        self._edit(tmp, "## Scope", "## Decision\nthe human decided\n\n## Scope")
        r = run(tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("tier light on a design task", r.stdout)


if __name__ == "__main__":
    unittest.main()
