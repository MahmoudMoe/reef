"""Stress: the approval records at their seams — the owner's hook and `--owner`, Mahmoud's `--proxy` (night and autopilot)
and `--proxy --day`, `--from-issue` (a row and the day contract), the plan's digest across checkouts, a stale approval after
the plan changes, a filed question an approval answers, an agent-written contract or report in an unexpected shape, a step
that crashed half-way, and gh failing.

The state is built with the real scripts (reef-run contract, reef-plan-check, reef-queue footnote, git worktrees); only
Mahmoud's report, the owner's answer and gh are faked."""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import write, git_checked, load_script, ROOT  # noqa: E402

import test_night as N        # noqa: E402  (project(), digest(), hook(), proxy(), approve_night(), PROXY_MD)
import test_day_proxy as DP   # noqa: E402  (approve_day(), decide(), REPORT, TODAY)
import test_factory as F      # noqa: E402  (the fake forge: issues, comments, permissions)

APPROVAL = os.path.join(ROOT, "scripts", "reef-approval.py")
CHECK = os.path.join(ROOT, "scripts", "reef-plan-check.py")
SLUG = "share-links"


def full_digest(d, feature=SLUG):
    return subprocess.run([sys.executable, CHECK, d, "--digest", "--feature", feature], capture_output=True, text=True).stdout.split()[-1]


def record(d, feature=SLUG):
    p = os.path.join(d, ".reef", "approvals", f"{feature}.json")
    return json.load(open(p)) if os.path.exists(p) else None


def verify(co, feature=SLUG):
    subprocess.run([sys.executable, CHECK, co], capture_output=True, text=True)   # the stamp, as /reef-plan leaves it
    return subprocess.run([sys.executable, CHECK, co, "--verify-stamp", "--feature", feature], capture_output=True, text=True).stdout


def feature_and_task_worktrees(d):
    """The plan drafted in its feature worktree, a task worktree branched from it, then the plan amended in the feature
    worktree (row 187's shape): the task worktree and the main checkout hold the older copy."""
    wt = os.path.join(d, ".reef", "worktrees", SLUG)
    git_checked(d, "worktree", "add", "-q", "-b", f"feat/{SLUG}", wt)
    twt = os.path.join(d, ".reef", "worktrees", f"{SLUG}-1201")
    git_checked(d, "worktree", "add", "-q", "-b", "task/1201", twt, f"feat/{SLUG}")
    with open(os.path.join(wt, "reef", "features", SLUG, "SPEC.md"), "a") as f:
        f.write("\nAmended after the task worktree branched.\n")
    return wt, twt


def night_report(d, feature, dg, cwd=None):
    rel = f".reef/ci-local/report-mahmoud-{feature}.md"
    write(cwd or d, rel, f"RUN: agent=mahmoud night={DP.TODAY} question=approve\nAPPROVE plan {feature} at {dg} — slices are vertical\nVERDICT: DONE\n")
    return rel


# ---------------------------------------------------------------- the owner's hook / --owner


class OwnerHook(unittest.TestCase):
    def test_an_answer_at_a_stale_copys_digest_neither_records_nor_voids_the_plan_of_records_approval(self):
        # plan_of_record (reef-approval.py:130-135): an approval binds the feature's own worktree, else the main checkout —
        # "never the first checkout holding it: a task worktree branched before an amendment holds an older plan". --proxy
        # and --from-issue refuse the older copy's digest (test_night: "an approval of the older copy is stale, though the
        # main checkout still holds it"); the owner's own answer must be read the same way.
        d = N.project()
        wt, twt = feature_and_task_worktrees(d)
        old, new = N.digest(twt, SLUG), N.digest(wt, SLUG)
        self.assertNotEqual(old, new)
        r = N.hook(d, f"Approve plan {SLUG} at {new}?")
        self.assertIn("approved at", r.stdout, r.stdout)
        self.assertIn("approval: OK", verify(wt))
        # a wait line printed before the amendment, answered later from the terminal (`reef-approval.py --owner "<q>"`)
        r = subprocess.run([sys.executable, APPROVAL, "--owner", f"Approve plan {SLUG} at {old}?"], capture_output=True, text=True, cwd=d,
                           env=dict(os.environ, REEF_NO_RESUME="1"))
        self.assertEqual(record(d)["digest16"], new, "the older copy's answer overwrote the approval of the plan of record:\n" + r.stdout)
        self.assertNotIn("approved at", r.stdout, "an older copy's digest is stale, as --proxy says")
        self.assertIn("approval: OK", verify(wt), "the feature worktree's plan stays approved")

    def test_an_approval_binds_the_feature_worktrees_plan_and_an_edit_after_it_is_stale(self):
        # skills/reef-plan/SKILL.md:44: "a timeout, an `Edit`, a hand-written file or a later edit approves nothing"
        d = N.project()
        wt, _ = feature_and_task_worktrees(d)
        new = N.digest(wt, SLUG)
        r = N.hook(wt, f"Approve plan {SLUG} at {new}?")   # the hook fires in the feature worktree, where /reef-plan works
        self.assertIn("approved at", r.stdout, r.stdout)
        self.assertFalse(os.path.exists(os.path.join(wt, ".reef", "approvals", f"{SLUG}.json")), "the record goes to the MAIN checkout")
        self.assertEqual(record(d)["digest"], full_digest(wt))
        self.assertIn("approval: OK", verify(wt))
        with open(os.path.join(wt, "reef", "features", SLUG, "SPEC.md"), "a") as f:
            f.write("\nOne more line after the gate.\n")
        self.assertIn("approval: STALE", verify(wt))
        r = N.hook(wt, f"Approve plan {SLUG} at {new}?")
        self.assertIn("stale", r.stdout, "the same answer again approves nothing")

    def test_a_feature_worktree_named_before_the_slug_changed_is_the_plan_of_record(self):
        # 2026-11-04 (an adopted project, row 193): plan-check refused the word "feature" in the slug, the planner renamed the plan
        # folder to hiring-module-move and kept the worktree and branch hiring-feature-module. The owner approved twice in the
        # chat and the hook said "matches no checkout's plan of record (it is at none; every checkout: <digest> in
        # hiring-feature-module) (stale)" — the one feature checkout holding the plan is the plan of record, whatever its name
        d = N.project()
        old = os.path.join(d, ".reef", "worktrees", "old-name")
        git_checked(d, "worktree", "add", "-q", "-b", "feat/old-name", old)
        with open(os.path.join(old, "reef", "features", SLUG, "SPEC.md"), "a") as f:
            f.write("\nAmended in the worktree that kept its first name.\n")
        twt = os.path.join(d, ".reef", "worktrees", f"{SLUG}-1201")
        git_checked(d, "worktree", "add", "-q", "-b", "task/1201", twt, "feat/old-name")   # a task worktree holds the same plan
        dg = N.digest(old, SLUG)
        self.assertNotEqual(dg, N.digest(d, SLUG), "the main checkout holds the older copy")
        r = N.hook(d, f"Approve plan {SLUG} at {dg}?")
        self.assertIn("approved at", r.stdout, r.stdout)
        self.assertEqual(record(d)["digest"], full_digest(old))
        # two feature checkouts holding the plan: which one is of record is unknowable — refused, and the line says why
        other = os.path.join(d, ".reef", "worktrees", "second")
        git_checked(d, "worktree", "add", "-q", "-b", "feat/second", other, "feat/old-name")
        os.remove(os.path.join(d, ".reef", "approvals", f"{SLUG}.json"))
        r = N.hook(d, f"Approve plan {SLUG} at {dg}?")
        self.assertNotIn("approved at", r.stdout)
        self.assertIn("feature checkouts hold this plan", r.stdout)

    def test_two_checkouts_holding_the_identical_plan_record_once_from_the_plan_of_record(self):
        # contract: reef-approval.py:639-640 — among matching checkouts the plan of record is read first, never a task worktree
        d = N.project()
        wt = os.path.join(d, ".reef", "worktrees", SLUG)
        git_checked(d, "worktree", "add", "-q", "-b", f"feat/{SLUG}", wt)
        dg = N.digest(wt, SLUG)
        self.assertEqual(dg, N.digest(d, SLUG))
        r = N.hook(d, f"Approve plan {SLUG} at {dg}?")
        self.assertIn("approved at", r.stdout, r.stdout)
        self.assertIn(f"plan in {wt}", r.stdout.replace(os.path.realpath(wt), wt))
        self.assertNotIn("two plans share", r.stdout)

    def test_the_plan_approval_clears_its_own_question_and_keeps_the_rows_look_question(self):
        # clear_question (reef-approval.py:147-150): "The approval's own question leaves .reef/questions.md … this row's
        # other questions … stay". A design look waiting on the owner is another question (contract silent on the word
        # "approve" inside it — an owner would obviously expect the look still asked).
        d = N.project()
        dg = N.digest(d, SLUG)
        write(d, ".reef/questions.md", f"- row 12: re-approve row 12's plan at {dg} so the fix round can dispatch — recommended: approve\n"
                                       "- row 12: approve the share page's look (preview at /share)? — recommended: approve\n")
        r = N.hook(d, f"Approve plan {SLUG} at {dg}?")
        self.assertIn("approved at", r.stdout, r.stdout)
        left = open(os.path.join(d, ".reef", "questions.md")).read() if os.path.exists(os.path.join(d, ".reef", "questions.md")) else ""
        self.assertNotIn("re-approve", left)
        self.assertIn("the share page's look", left, "the plan's approval answered a question about the look:\n" + r.stdout)


# ---------------------------------------------------------------- Mahmoud's plan approval (night / autopilot)


class ProxyNight(unittest.TestCase):
    def test_a_row_the_contract_leaves_out_with_its_reason_is_not_in_tonights_contract(self):
        # skills/reef-night/SKILL.md:12: "a `Rows: <ids>` line — … one left out only with its reason"; at night "the tick
        # drives these rows and no others" and "any row not listed" is a hard limit. Mahmoud writes the contract; the reason
        # on the Rows line is the natural place for it.
        d = N.project()
        write(d, ".reef/night/contract.md", "# Night\nRows: 12 (not 3: it waits on the owner's question)\n"
                                            "Decisions: plan approvals, design looks.\nHard limits: the release to main.\n")
        N.approve_night(self, d)
        write(d, ".reef/night/active", "{}")
        rep = night_report(d, "editable-items", N.digest(d, "editable-items"))
        r = N.proxy(d, "editable-items", rep)
        self.assertEqual(r.returncode, 1, "row 3, left out of the contract by its reason, was approved by the proxy:\n" + r.stdout)
        self.assertIsNone(record(d, "editable-items"))

    def test_the_proxys_plan_approval_clears_the_question_it_answers(self):
        # clear_question (reef-approval.py:147-150, 2026-10-28): a filed approval question that outlives the record makes the
        # next sessions re-read it and record the same wait. Mahmoud's approval is "the record the hook would have written"
        # (skills/reef-night/SKILL.md:16), so it answers that question the same way.
        d = N.project()
        N.approve_night(self, d)
        write(d, ".reef/night/active", "{}")
        dg = N.digest(d, SLUG)
        write(d, ".reef/questions.md", f"- row 12: approve row 12's plan at {dg} — recommended: approve\n- row 3: rename it? — recommended: no\n")
        r = N.proxy(d, SLUG, night_report(d, SLUG, dg))
        self.assertEqual(r.returncode, 0, r.stdout)
        left = open(os.path.join(d, ".reef", "questions.md")).read()
        self.assertIn("row 3", left)
        self.assertNotIn("row 12", left, "the approved plan's question is still filed after Mahmoud's approval")

    def test_run_from_the_feature_worktree_the_proxy_reads_mains_night_and_writes_mains_record(self):
        # skills/reef-night/SKILL.md:16 + plan_digests docstring: "The RECORD still goes to the main checkout"
        d = N.project()
        N.approve_night(self, d)
        write(d, ".reef/night/active", "{}")
        wt = os.path.join(d, ".reef", "worktrees", SLUG)
        git_checked(d, "worktree", "add", "-q", "-b", f"feat/{SLUG}", wt)
        with open(os.path.join(wt, "reef", "features", SLUG, "SPEC.md"), "a") as f:
            f.write("\nAmended in the feature worktree.\n")
        rep = night_report(d, SLUG, N.digest(wt, SLUG), cwd=wt)
        r = subprocess.run([sys.executable, APPROVAL, "--proxy", "--feature", SLUG, "--report", rep], capture_output=True, text=True, cwd=wt)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(record(d)["digest"], full_digest(wt))
        self.assertIn("approval: OK", verify(wt))

    def test_the_autopilot_approves_no_row_when_the_queue_cannot_be_read(self):
        # cmd_proxy (reef-approval.py:237): "the work the owner gave is the queue's open rows, nothing beyond it (the security
        # review)". queue_open_rows returns None when the queue is unreadable and the check is skipped: fail open. Contract
        # silent on the unreadable case; #305's rule: a failed read is BROKEN, never "anything goes".
        d = N.project()
        write(d, "reef/proxy.md", N.PROXY_MD)
        DP.approve_day(self, d)
        rr = DP.load_run()
        dg = rr.day_digest(d)
        write(d, ".reef/night/autopilot", json.dumps({"pid": os.getpid(), "started": "x", "digest16": dg[:16], "digest": dg}))
        os.rename(os.path.join(d, "reef", "queue.md"), os.path.join(d, "reef", "queue.md.moved"))   # e.g. a rebase mid-flight, a renamed paths.queue
        rep = write(d, ".reef/ci-local/report-mahmoud-share-links.md",
                    f"RUN: agent=mahmoud day={DP.TODAY} kind=plan question=approve\nAPPROVE plan {SLUG} at {N.digest(d, SLUG)} — x\nVERDICT: DONE\n")
        r = N.proxy(d, SLUG, os.path.relpath(rep, d))
        self.assertEqual(r.returncode, 1, "an unreadable queue let the autopilot approve a row it cannot see is open:\n" + r.stdout)
        self.assertIsNone(record(d))


# ---------------------------------------------------------------- Mahmoud's decision by day


class ProxyDay(unittest.TestCase):
    def test_a_second_decides_line_in_proxy_md_does_not_leave_a_kind_the_owner_took_back(self):
        # day_kinds (reef-run.py:869): "The kinds reef/proxy.md's `Decides:` line names". The owner edits the seeded file by
        # appending a line (as test_day_proxy's own owner does); the file then has two. Contract silent on which wins; an
        # owner who appended `Decides: wording` would obviously expect `process` to be theirs again.
        # The owner's choice (2026-11-03): two `Decides:` lines are REFUSED, never intersected — `contract --day` names the
        # one-line shape, and neither line counts.
        d = N.project()
        DP.contract_day(d)
        with open(os.path.join(d, "reef", "proxy.md"), "a") as f:
            f.write("\nThis week I keep process myself.\nDecides: wording\n")
        r = DP.contract_day(d)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("keep ONE: `Decides:", r.stderr + r.stdout)
        self.assertEqual(DP.load_run().day_kinds(d), [], "with two Decides: lines, neither names a kind")
        r = DP.decide(d, kind="process")
        self.assertEqual(r.returncode, 1, "the first `Decides:` line won over the owner's later one:\n" + r.stdout)
        self.assertNotIn("Mahmoud (proxy, day", open(os.path.join(d, "reef", "queue.md")).read())

    def test_a_decision_killed_after_its_footnote_is_one_footnote_on_the_rerun(self):
        # cmd_proxy_day: "one decision, one footnote" (reef-approval.py:316). The footnote is written (:320) before the record
        # that makes it idempotent (:326); a run killed between them (the runner stopped, a /clear) re-runs into a second one.
        d = N.project()
        DP.approve_day(self, d)
        write(d, ".reef/ci-local/report-mahmoud-day-12.md", DP.REPORT.format(kind="process", day=DP.TODAY))
        mod = load_script("reef-approval.py")
        real_open = open

        def dying_open(p, mode="r", *a, **k):
            if str(p).endswith("day-decisions.jsonl") and "a" in mode:
                raise KeyboardInterrupt("killed")   # the process dies here
            return real_open(p, mode, *a, **k)
        mod.open = dying_open
        here = os.getcwd()
        os.environ["REEF_NO_RESUME"] = "1"
        try:
            os.chdir(d)
            with self.assertRaises(KeyboardInterrupt):
                mod.cmd_proxy_day(["--proxy", "--day", "--kind", "process", "--row", "12", "--report", ".reef/ci-local/report-mahmoud-day-12.md"])
        finally:
            os.chdir(here)
            os.environ.pop("REEF_NO_RESUME", None)
        self.assertEqual(open(os.path.join(d, "reef", "queue.md")).read().count("Mahmoud (proxy, day"), 1, "the first run wrote its footnote")
        r = DP.decide(d)   # the same report, run again
        n = open(os.path.join(d, "reef", "queue.md")).read().count("Mahmoud (proxy, day")
        self.assertEqual(n, 1, "the re-run wrote a second footnote for one decision:\n" + r.stdout)

    def test_a_crlf_report_is_one_clean_footnote(self):
        # agents/mahmoud.md:40-42 — the RUN and DECIDE lines; a report copied through a Windows editor keeps CRLF
        d = N.project()
        DP.approve_day(self, d)
        r = DP.decide(d, text=DP.REPORT.format(kind="process", day=DP.TODAY).replace("\n", "\r\n"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        q = open(os.path.join(d, "reef", "queue.md"), newline="").read()
        line = [l for l in q.split("\n") if "Mahmoud (proxy, day" in l][0]
        self.assertNotIn("\r", line)
        self.assertIn("no, keep one task — the slice is small", line)


# ---------------------------------------------------------------- the owner's approval from the forge


GH_WRAPPER = r'''#!/usr/bin/env python3
import os, sys
bad = os.environ.get("GH_FAIL_ON")
if bad and any(bad in a for a in sys.argv[1:]):
    print("HTTP 502: Bad Gateway", file=sys.stderr); sys.exit(1)
real = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gh-real")
os.execv(sys.executable, [sys.executable, real, *sys.argv[1:]])
'''


class FromIssue(F._Forge):
    def spec(self):
        return os.path.join(self.d, "reef", "features", "exact-totals", "SPEC.md")

    def dg(self):
        r = subprocess.run([sys.executable, os.path.join(self.d, "scripts", "reef-plan-check.py"), self.d, "--digest", "--feature", "exact-totals"],
                           capture_output=True, text=True)
        return r.stdout.split()[-1][:16]

    def test_a_row_line_the_plan_check_accepts_names_the_feature(self):
        # reef-plan-check.py:858 accepts `^Row:\s*\d+` (and feature_row, reef-approval.py:177, reads it the same way);
        # --from-issue matches `^Row:\s*<row>\s*$` (:424), so a SPEC with text after the id has "nothing to approve"
        # while the owner's comment sits on the issue.
        text = open(self.spec()).read()
        self.assertIn("Row: 3\n", text)
        open(self.spec(), "w").write(text.replace("Row: 3\n", "Row: 3 (split from row 2)\n"))
        r = subprocess.run([sys.executable, os.path.join(self.d, "scripts", "reef-plan-check.py"), self.d, "--feature", "exact-totals", "--quiet"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, "the plan check is green on this Row line:\n" + r.stdout)
        self.comment(f"Approve plan exact-totals at {self.dg()}?")
        r = self.approval("--from-issue", "3")
        self.assertIn("approved at", r.stdout, "the owner's approval on the issue was not found:\n" + r.stdout + r.stderr)

    def test_a_failed_comments_read_is_named_not_no_comment(self):
        # #305: "A failed gh or queue read is BROKEN, never empty". The docstring's "no comment: nothing" is a read that
        # succeeded and found none; a 502 is not the owner's silence (contract silent here; the factory logs this last line,
        # reef-factory.py:107-108, and the owner who did post is told to post again).
        os.rename(os.path.join(self.bin, "gh"), os.path.join(self.bin, "gh-real"))
        with open(os.path.join(self.bin, "gh"), "w") as f:
            f.write(GH_WRAPPER)
        os.chmod(os.path.join(self.bin, "gh"), 0o755)
        self.comment(f"Approve plan exact-totals at {self.digest}?")
        r = subprocess.run([sys.executable, APPROVAL, "--from-issue", "3"], capture_output=True, text=True, cwd=self.d,
                           env=self.env(GH_FAIL_ON="/comments"))
        self.assertIsNone(record(self.d, "exact-totals"))
        self.assertNotIn("no approval comment", r.stdout, "gh failed, and the owner is told he never commented:\n" + r.stdout)
        self.assertNotEqual(r.returncode, 0, r.stdout)

    def test_a_comment_with_crlf_and_a_leading_blank_line_is_the_owners_line(self):
        # reef-approval.py:12: "a comment whose first line is exactly `Approve plan <slug> at <digest16>?`" — a phone's
        # client sends CRLF; the first non-blank line is the line
        self.comment(f"\r\nApprove plan exact-totals at {self.digest}?\r\nThanks, ship it.\r\n")
        r = self.approval("--from-issue", "3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("approved at", r.stdout)
        self.assertEqual(record(self.d, "exact-totals")["by"], "owner (issue #12, @mahmoud)")

    def test_a_plan_edited_after_the_owners_comment_is_stale(self):
        # reef-approval.py:14: "a stale digest … nothing"
        self.comment(f"Approve plan exact-totals at {self.digest}?")
        with open(self.spec(), "a") as f:
            f.write("\nAmended after the owner's comment.\n")
        r = self.approval("--from-issue", "3")
        self.assertIn("stale", r.stdout, r.stdout)
        self.assertIsNone(record(self.d, "exact-totals"))


if __name__ == "__main__":
    unittest.main()
