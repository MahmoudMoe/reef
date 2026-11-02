"""Stress: the close (scripts/reef-merge-close) and the records agents hand to scripts — interrupted closes, odd task-file
shapes, verifier/reviewer reports in odd shapes, reef-claims, reef-queue journal, reef-record, reef-attempt's Log.
A FAILING test here is a finding (docs/review/stress-2026-11-02.md); a passing one pins behaviour."""
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import write, git, ROOT  # noqa: E402
import test_merge_close as tmc  # noqa: E402  (module only: its classes stay out of this namespace)
import test_record as trec  # noqa: E402

CLOSE = os.path.join(ROOT, "scripts", "reef-merge-close")
CLAIMS = os.path.join(ROOT, "scripts", "reef-claims.py")
QUEUE = os.path.join(ROOT, "scripts", "reef-queue.py")
ATTEMPT = os.path.join(ROOT, "scripts", "reef-attempt")
RECORD = os.path.join(ROOT, "scripts", "reef-record")
TASK_REL = "reef/features/demo/tasks/101-slice.md"
DONE_REL = "reef/features/demo/tasks/done/101-slice.md"


def read(d, rel):
    with open(os.path.join(d, rel), encoding="utf-8", newline="") as f:
        return f.read()


def run(*args, **kw):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, **kw)


class _Close(unittest.TestCase):
    """test_merge_close.MergeClose's world (main on main, feature worktree on feat/demo, task worktree with uncommitted work)."""
    setUp = tmc.MergeClose.setUp
    close = tmc.MergeClose.close

    def merging(self):
        return git(self.feat, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0

    def judged(self, extra=""):
        t = tmc.TASK.replace("attempts: 0\n", "attempts: 0\nworktree: .reef/worktrees/101\nverify: judge\n" + extra)
        write(self.feat, TASK_REL, t.replace("complexity: mech\ntier: light", "complexity: design\ntier: critical"))
        write(self.wt, ".gitignore", ".reef/ci-local/\n")

    def report(self, text, hb_offset=None):
        p = write(self.wt, ".reef/ci-local/report-101.md", text)
        if hb_offset is not None:
            h = write(self.wt, ".reef/ci-local/handback-101.md", "RUN: agent=implementer task=101\nround 2\n")
            now = time.time()
            os.utime(h, (now, now))
            os.utime(p, (now + hb_offset, now + hb_offset))
        return p


class InterruptedClose(_Close):
    """reef-merge-close docstring: "In order, each step skipped when already done" and "the rest resumes" — a re-run after a
    half-way stop finishes the close."""

    def test_a_close_killed_during_worktree_setup_resumes_on_one_rerun(self):
        # a real crash mid-merge: `npm ci` killed / the runner's session ends while worktree.setup runs (step 2). The
        # merge is left in progress (MERGE_HEAD, staged files). The docstring promises each step is skipped when done.
        marker = os.path.join(self.tmp, "killed-once")
        write(self.feat, ".reef/config.json", json.dumps({"branches": {"base": "main"}, "worktree": {
            "setup": f"if [ ! -f {marker} ]; then touch {marker}; kill -9 $PPID; fi"}}))
        git(self.feat, "commit", "-qam", "setup that dies once")
        r1 = self.close()
        self.assertNotEqual(r1.returncode, 0, "the first run was killed")
        self.assertTrue(self.merging(), "precondition: the crash left a merge in progress")
        r2 = self.close()
        self.assertEqual(r2.returncode, 0, "one re-run resumes the close: " + r2.stdout + r2.stderr)
        self.assertFalse(self.merging())
        self.assertIn("status: done", git(self.feat, "show", f"HEAD:{DONE_REL}").stdout)

    def test_a_stale_done_copy_refuses_before_the_merge_starts(self):
        # step 3's `git mv` fails when tasks/done/<name> already exists (an earlier half-close, a hand copy). The fast path
        # checks this first ("already exists — nothing changed"); the critical path must leave no merge in progress either
        # ("A conflict or a gate refusal aborts the merge and leaves the tree as it was").
        write(self.feat, DONE_REL, "stale\n")
        r = self.close()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertFalse(self.merging(), "a refused close leaves no merge in progress: " + r.stderr)
        self.assertIn("status: in-progress", read(self.feat, TASK_REL), "the task file as it was")

    def test_a_merge_commit_refused_once_then_rerun_closes_with_one_journal_block(self):
        # coverage: the gate refuses the merge commit once; the re-run closes, the journal block lands once
        flag = os.path.join(self.tmp, "refused-once")
        hook = write(self.main, ".git/hooks/pre-commit",
                     f"#!/bin/sh\ngit rev-parse --abbrev-ref HEAD | grep -q '^feat/' || exit 0\n"
                     f"[ -f {flag} ] && exit 0\ntouch {flag}; echo 'gate: red' >&2; exit 1\n")
        os.chmod(hook, 0o755)
        self.assertEqual(self.close().returncode, 2)
        r = self.close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        done = git(self.feat, "show", f"HEAD:{DONE_REL}").stdout
        self.assertEqual(done.count("<!-- journal -->"), 1)
        self.assertEqual(done.count("| 101 | PASS |"), 1)

    def test_a_worktree_that_will_not_go_resumes_after_the_merge(self):
        # coverage: "{tbranch} is merged but its worktree stays … fix that and re-run (the rest resumes)"
        git(self.main, "worktree", "lock", self.wt)
        r = self.close()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("worktree stays", r.stderr)
        git(self.main, "worktree", "unlock", self.wt)
        r = self.close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(self.wt))
        self.assertEqual(git(self.feat, "rev-list", "--merges", "--count", "HEAD").stdout.strip(), "1", "one merge, not two")


class TaskFileShapes(_Close):

    def test_quoted_verify_judge_still_requires_the_verifiers_pass(self):
        # every other frontmatter reader strips the quotes (reef-plan-check.py:140, reef-graph.py:68, reef-attempt:171,
        # reef-queue.py:174, reef-guard.py:1229) — `verify: "judge"` IS a judged task to the rest of Reef.
        # reef-merge-close docstring: "a judged task on the critical path closes only with the verifier's PASS report"
        self.judged()
        write(self.feat, TASK_REL, read(self.feat, TASK_REL).replace("verify: judge", 'verify: "judge"'))
        r = self.close()
        self.assertEqual(r.returncode, 2, "closed a judged task with no verifier report: " + r.stdout)
        self.assertIn("verifier's PASS report", r.stderr)

    def test_a_quoted_worktree_key_finds_the_task_worktree(self):
        # same quoting rule; reef-graph.py reads `worktree: ".reef/worktrees/101"` as the path without quotes
        write(self.feat, TASK_REL, read(self.feat, TASK_REL).replace("worktree: .reef/worktrees/101", 'worktree: ".reef/worktrees/101"'))
        r = self.close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(self.wt))

    def test_a_crlf_task_file_keeps_crlf_in_its_frontmatter(self):
        # contract silent for the close; reef-attempt's TaskFile: "Newlines are preserved byte-for-byte … a CRLF task file
        # is not silently rewritten". The close rewrites `status:` with `.*$`, which eats the line's \r.
        write(self.feat, TASK_REL, "")
        with open(os.path.join(self.feat, TASK_REL), "w", newline="") as f:
            f.write(tmc.TASK.replace("attempts: 0\n", "attempts: 0\nworktree: .reef/worktrees/101\n").replace("\n", "\r\n"))
        r = self.close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        fm = read(self.feat, DONE_REL).split("---", 2)[1]
        bare = [l for l in fm.split("\n")[1:-1] if not l.endswith("\r")]
        self.assertEqual(bare, [], "frontmatter lines lost their CR")

    def test_a_log_line_quoting_the_journal_marker_does_not_swallow_the_block(self):
        # reef-merge-close docstring step 3: "the journal file's text between <!-- journal --> markers under the task's
        # ## Log". The skip test is `"<!-- journal -->" not in body` — a FAIL line that quotes the marker (a plan-check
        # failure about markers, recorded by reef-attempt) is not a block.
        out = run(ATTEMPT, os.path.join(self.feat, TASK_REL),
                  "plan-check: 101-slice.md: <!-- journal --> block not closed", cwd=self.feat)
        self.assertIn("attempt 1 FAIL", read(self.feat, TASK_REL), out.stdout + out.stderr)
        r = self.close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("| 101 | PASS | growth 3 |", git(self.feat, "show", f"HEAD:{DONE_REL}").stdout, "the runlog row was dropped")

    def test_a_unicode_and_pipe_journal_row_survives_the_close_and_the_copy(self):
        # coverage: a cell with unicode and an escaped pipe goes through the close and reef-queue.py journal unchanged
        row = "| 101 | PASS | naïve café — 3 rounds · a\\|b |"
        write(self.tmp, "journal.md", row + "\n")
        r = self.close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(row, git(self.feat, "show", f"HEAD:{DONE_REL}").stdout)

    def test_a_row_for_another_id_is_refused(self):
        # coverage: PR 300 — "has no runlog row `| 101 | …`"
        write(self.tmp, "journal.md", "| 102 | PASS | wrong task |\n")
        r = self.close()
        self.assertEqual(r.returncode, 1)
        self.assertIn("| 101 |", r.stderr)


class VerifierReports(_Close):
    """agents/verifier.md: the report "ends `VERDICT: PASS` or `VERDICT: FAIL` + concrete feedback" — the LAST VERDICT
    line is the verdict."""

    def test_a_report_ending_in_fail_does_not_close_even_if_an_earlier_line_says_pass(self):
        self.judged()
        self.report("RUN: agent=verifier task=101 round=2\nround 1 was `VERDICT: PASS` on old code:\nVERDICT: PASS\n"
                    "AC1 FAIL — tests/test_a.py:1 regressed\nVERDICT: FAIL\n")
        r = self.close()
        self.assertEqual(r.returncode, 2, "a FAIL report closed the task: " + r.stdout)

    def test_claims_verdict_reads_the_last_verdict(self):
        p = write(self.tmp, "rep.md", "RUN: agent=verifier task=101\nVERDICT: PASS\nAC1 FAIL — a.py:1\nVERDICT: FAIL\n")
        self.assertEqual(run(CLAIMS, "verdict", p).returncode, 1, "reef-claims verdict says PASS on a report ending FAIL")

    def test_claims_verdict_and_the_close_agree_on_a_lowercase_pass(self):
        # contract silent: the orchestrator reads `reef-claims.py verdict` (exit 0 = PASS) and then closes; the two
        # readers of one report must not disagree (verdict upper()s, the close wants `PASS` exactly)
        self.judged()
        p = self.report("RUN: agent=verifier task=101\nRULE AC1: PASS iff x\nAC1 pass — tests/test_a.py:1\nVERDICT: pass\n")
        v = run(CLAIMS, "verdict", p).returncode
        c = self.close().returncode
        self.assertEqual((v == 0), (c == 0), f"reef-claims verdict exit {v}, reef-merge-close exit {c}")

    def test_empty_report_refuses_and_verdict_says_no_verdict(self):
        self.judged()
        p = self.report("")
        self.assertEqual(run(CLAIMS, "verdict", p).returncode, 2)
        self.assertEqual(self.close().returncode, 2)

    def test_a_report_one_second_older_than_the_handback_is_stale(self):
        # coverage: "a PASS older than the last hand-back judged an earlier round"
        self.judged()
        self.report("RUN: agent=verifier task=101\nVERDICT: PASS\n", hb_offset=-1)
        r = self.close()
        self.assertEqual(r.returncode, 2)
        self.assertIn("predates", r.stderr)

    def test_a_report_with_the_handbacks_exact_mtime_closes(self):
        # coverage: the comparison is strict (>), so the same mtime is not stale
        self.judged()
        self.report("RUN: agent=verifier task=101\nVERDICT: PASS\n", hb_offset=0)
        r = self.close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_skeleton_on_a_quoted_id_names_the_bare_id(self):
        # every frontmatter reader strips the quotes; the skeleton's RUN header should say task=101, not task="101"
        write(self.feat, TASK_REL, read(self.feat, TASK_REL).replace("id: 101", 'id: "101"'))
        sk = run(CLAIMS, "skeleton", "--task", os.path.join(self.feat, TASK_REL)).stdout
        self.assertIn("RUN: agent=verifier task=101 ", sk)

    def test_skeleton_round_trips_on_a_crlf_task(self):
        # coverage: a CRLF task's skeleton, filled, is accepted by `report`
        task = write(self.tmp, "101-crlf.md", "")
        with open(task, "w", newline="") as f:
            f.write(tmc.TASK.replace("- AC-1 (FR-1): it works\n", "- AC-1 (FR-1): it works\n- AC-2: also\n").replace("\n", "\r\n"))
        sk = run(CLAIMS, "skeleton", "--task", task).stdout
        self.assertIn("RULE AC2:", sk)
        filled = sk.replace("<<fill: PASS iff …; FAIL otherwise>>", "PASS iff ok").replace(
            "<<fill: PASS or FAIL>> — <<fill: evidence on this line: a path:line, a test name, or a command in backticks and its exit>>",
            "PASS — `pytest -q` exit 0").replace("<<fill: PASS or FAIL>>", "PASS")
        r = run(CLAIMS, "report", write(self.tmp, "r.md", filled), "--task", task, "--repo", self.feat)
        self.assertEqual(r.returncode, 0, r.stdout)


class JournalCopy(unittest.TestCase):
    """reef-queue.py cmd_journal: "the row's close, on the base, copies them in task order. Idempotent: a block already there
    is skipped." """

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-jc.")
        subprocess.run(["git", "init", "-q", "-b", "main", self.d], check=True)
        write(self.d, ".reef/config.json", json.dumps({"paths": {"features": "reef/features"}}))
        write(self.d, "reef/features/demo/SPEC.md", "# demo\n")
        for tid in (9, 10, 11):
            write(self.d, f"reef/features/demo/tasks/done/{tid}-t.md",
                  f"---\nid: {tid}\nstatus: done\n---\n# t\n\n## Log\n\n<!-- journal -->\n| {tid} | PASS | ok |\n<!-- /journal -->\n")
        write(self.d, "docs/journal.md", "# Journal\n")

    def test_a_first_copy_into_a_project_without_the_journal_folder_writes_it(self):
        # cmd_journal reads a missing journal as "# Journal\n" (the first row's close on a fresh project); its folder
        # missing too should not end in a traceback with nothing copied
        os.remove(os.path.join(self.d, "docs/journal.md")); os.rmdir(os.path.join(self.d, "docs"))
        r = self.journal()
        self.assertEqual(r.returncode, 0, r.stderr[-300:])
        self.assertIn("| 9 | PASS | ok |", self.text())

    def journal(self):
        return run(QUEUE, "journal", "demo", "--repo", self.d)

    def text(self):
        return read(self.d, "docs/journal.md")

    def test_blocks_are_copied_in_task_order_and_once(self):
        r = self.journal()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        t = self.text()
        self.assertTrue(t.index("| 9 |") < t.index("| 10 |") < t.index("| 11 |"), "task order is 9, 10, 11:\n" + t)
        self.journal()
        self.assertEqual(self.text(), t, "idempotent")

class GreenRecord(trec._Repo, unittest.TestCase):
    """reef-record docstring: "GREEN/PASS needs --report: the reviewer's report naming the PR head (its first 12 hex) and its
    `VERDICT:` line"; agents/acceptance.md: the report "opens with HEAD and ends with VERDICT"."""

    def rec(self, body):
        p = write(self.tmp, "review.md", body)
        return subprocess.run([sys.executable, RECORD, "demo", "GREEN", "--root", self.d, "--report", p],
                              capture_output=True, text=True, env=self.env())

    def test_a_report_ending_fail_is_not_recorded_green(self):
        head = trec.git(self.d, "rev-parse", "feat")[:12]
        r = self.rec(f"RUN: agent=acceptance feature=demo\nHEAD: {head}\nprevious round: VERDICT: GREEN\nVERDICT: GREEN\n"
                     "BLOCKER: correctness — app.py:1 x is wrong\nVERDICT: FAIL\n")
        self.assertEqual(r.returncode, 2, "recorded GREEN from a report ending FAIL: " + r.stdout)

    def test_a_report_whose_head_line_names_an_older_commit_is_not_bound_to_the_new_head(self):
        head = trec.git(self.d, "rev-parse", "feat")[:12]
        old = trec.git(self.d, "rev-parse", "main")[:12]
        r = self.rec(f"RUN: agent=acceptance feature=demo\nHEAD: {old}\n- NIT: the fix {head} is pushed but not reviewed here\nVERDICT: GREEN\n")
        self.assertEqual(r.returncode, 2, "a review of the old head was bound to the new head: " + r.stdout)
        self.assertIn("not the PR head", r.stderr)

    def test_a_good_report_records(self):
        # coverage
        head = trec.git(self.d, "rev-parse", "feat")[:12]
        r = self.rec(f"RUN: agent=acceptance feature=demo\nHEAD: {head}\nVERDICT: GREEN\n")
        self.assertEqual(r.returncode, 0, r.stderr)


class SecurityRecord(trec._Repo, unittest.TestCase):
    """agents/security.md: "FAIL iff a BLOCKER", and "Bullets, not paragraphs … one fact per bullet"."""

    def sec(self, body):
        p = write(self.tmp, "security.md", body)
        return subprocess.run([sys.executable, RECORD, "security", "PASS", "--report", p, "--root", self.d],
                              capture_output=True, text=True, env=self.env())

    def test_a_bulleted_blocker_fails_the_pass(self):
        r = self.sec("RUN: agent=security range=release...main\n- BLOCKER src/a.ts:1 — token in URL — move to header\nVERDICT: PASS\n")
        self.assertEqual(r.returncode, 2, "PASS recorded over a BLOCKER bullet: " + r.stdout)


class AttemptLog(unittest.TestCase):
    """reef-attempt append_log and the counter's lock."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-at.")
        subprocess.run(["git", "init", "-q", "-b", "main", self.d], check=True)
        write(self.d, ".reef/config.json", json.dumps({"caps": {"attempts": 9}}))
        self.task = write(self.d, "tasks/101-slice.md", tmc.TASK)

    def fail(self, path, *text):
        return run(ATTEMPT, path, *text, cwd=self.d)

    def test_two_concurrent_writers_both_land(self):
        # coverage: "under the same lock" — two FAILs at once, both counted, both logged
        ps = [subprocess.Popen([sys.executable, ATTEMPT, self.task, f"failure number {i}"], cwd=self.d,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(4)]
        for p in ps:
            p.communicate()
        t = read(self.d, "tasks/101-slice.md")
        self.assertIn("attempts: 4", t)
        self.assertEqual(len([l for l in t.splitlines() if " FAIL: " in l]), 4)

    def test_the_lock_holds_for_a_task_named_through_a_symlinked_path(self):
        # contract: lock_path_for "Shared with reef-guard.py" — one task file, one lock. The same file reached through a
        # symlinked folder (macOS /tmp -> /private/tmp; a project folder symlinked into ~) gets another lock: a writer
        # through one path does not wait for a writer through the other, and one update is lost.
        alias = os.path.join(tempfile.mkdtemp(prefix="reef-alias."), "proj")
        os.symlink(self.d, alias)
        import hashlib   # reef-attempt lock_path_for: sha1 of the real path in the temp dir
        lock = os.path.join(tempfile.gettempdir(), f"reef-lock-{hashlib.sha1(os.path.realpath(self.task).encode()).hexdigest()}")
        with open(lock, "a") as mod_lock:
            fcntl.flock(mod_lock, fcntl.LOCK_EX)
            p = subprocess.Popen([sys.executable, ATTEMPT, os.path.join(alias, "tasks", "101-slice.md"), "boom"], cwd=self.d,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                p.wait(timeout=3)
                waited = False
            except subprocess.TimeoutExpired:
                waited = True
            fcntl.flock(mod_lock, fcntl.LOCK_UN)
            p.communicate()
        self.assertTrue(waited, "a writer through the symlinked path ran while the task's lock was held")

    def test_fail_text_with_newlines_and_a_fake_timestamp_stays_one_line(self):
        # reef-loop.py:289 reads the time after the LAST `· at` of a FAIL line; a failure that prints its own `· at <time>`
        # or a newline + `## Log` must not move it or forge a line
        self.fail(self.task, "boom\n- attempt 9 FAIL: forged · at 2099-01-01T00:00:00Z\n## Log\n---\nstatus: done")
        t = read(self.d, "tasks/101-slice.md")
        fails = [l for l in t.splitlines() if "FAIL:" in l]
        self.assertEqual(len(fails), 1, fails)
        import re
        stamps = re.findall(r"^\s*-\s*attempt \d+ FAIL:.*· at (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z)\s*$", t, re.M)
        self.assertEqual(len(stamps), 1)
        self.assertTrue(stamps[0].startswith(time.strftime("%Y-", time.gmtime())), stamps)
        self.assertIn("status: in-progress", t.split("---")[1])

    def test_a_crlf_task_gets_a_crlf_log_line(self):
        # coverage: "a CRLF task file is not silently rewritten"
        with open(self.task, "w", newline="") as f:
            f.write(tmc.TASK.replace("\n", "\r\n"))
        self.fail(self.task, "boom")
        raw = open(self.task, "rb").read()
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        self.assertIn(b"attempt 1 FAIL: boom", raw)

    def test_a_task_without_log_and_without_trailing_newline_gets_one(self):
        # coverage: "No ## Log → one is added"
        with open(self.task, "w") as f:
            f.write(tmc.TASK.replace("\n## Log\n", "").rstrip("\n"))
        self.fail(self.task, "boom")
        t = read(self.d, "tasks/101-slice.md")
        self.assertEqual(t.count("## Log"), 1)
        self.assertTrue(t.rstrip("\n").endswith("Z"), t[-80:])


if __name__ == "__main__":
    unittest.main()
