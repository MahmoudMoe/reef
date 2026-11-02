"""Stress: retry caps, attempts and time — scripts/reef-attempt, the tick's verify/dispatch decision (the FAIL line's
`· at <UTC>` against the hand-back's and the report's mtimes), caps.task_growth, caps.context_warn and the Stop hook.

A test that FAILS here is a finding (docs/review/stress-2026-11-02.md); one that passes pins the behaviour."""
import calendar
import json
import os
import subprocess
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import write, ROOT  # noqa: E402
from test_loop import project, task, approve, loop, stop_hook  # noqa: E402

ATTEMPT = os.path.join(ROOT, "scripts", "reef-attempt")
GUARD = os.path.join(ROOT, "scripts", "reef-guard.py")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def attempt(path, *failure, cap=None):
    argv = [sys.executable, ATTEMPT] + (["--cap", str(cap)] if cap else []) + [path] + list(failure)
    return subprocess.run(argv, capture_output=True, text=True)


def fm(path, key):
    import re
    m = re.search(rf"^{key}:[ \t]*(.*)$", read(path).split("\n---\n", 1)[0], re.M)
    return m.group(1).strip() if m else None


def tick(d):
    r = loop(d, "tick", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def utc(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def add_fail(path, n, stamp):
    """The line reef-attempt writes (scripts/reef-attempt: `- attempt N FAIL: … · at <UTC>`), with a chosen time."""
    t = read(path).replace(f"attempts: {n - 1}", f"attempts: {n}", 1)
    write(os.path.dirname(os.path.dirname(path)), os.path.join("tasks", os.path.basename(path)),
          t.rstrip("\n") + f"\n- attempt {n} FAIL: gate exit 1: FAIL x.test.ts · at {stamp}\n")


def worktree(d, name, branch):
    w = os.path.join(d, ".reef", "worktrees", name)
    subprocess.run(["git", "-C", d, "worktree", "add", "-q", "-b", branch, w], check=True, capture_output=True)
    return w


class AttemptCap(unittest.TestCase):
    def test_exactly_at_the_cap_blocks_and_one_past_is_refused_without_burning(self):
        # scripts/reef-attempt: "exit 2 = BLOCKED"; "an already-blocked task is immutable until a human unblocks it —
        # recording more failures onto it would burn the counter past the cap and overwrite the very signature"
        d = project()
        p = os.path.join(d, "tasks", "101-a.md")
        r = attempt(p)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("attempt=1/3", r.stdout)
        r = attempt(p)   # a report-only call (a rejected hand-back re-dispatched ONCE) consumes nothing
        self.assertIn("attempt=1/3", r.stdout)
        self.assertEqual(fm(p, "attempts"), "0")
        self.assertEqual(attempt(p, "AC-1 failed: one").returncode, 0)
        r = attempt(p, "AC-2 failed: two")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("attempt=3/3", r.stdout, "the last allowed attempt is still dispatched")
        r = attempt(p, "AC-3 failed: three")
        self.assertEqual(r.returncode, 2)
        self.assertIn("retry cap 3 reached", r.stderr)
        self.assertEqual((fm(p, "status"), fm(p, "attempts")), ("blocked", "3"))
        sig = fm(p, "last_failure_sig")
        r = attempt(p, "AC-4 failed: four")
        self.assertEqual(r.returncode, 2)
        self.assertIn("A HUMAN must unblock it", r.stderr)
        self.assertEqual((fm(p, "attempts"), fm(p, "last_failure_sig")), ("3", sig), "one past the cap burns nothing")
        self.assertEqual(read(p).count("FAIL:"), 3)

    def test_the_same_failure_twice_stops_early_even_when_lines_and_timings_drift(self):
        # scripts/reef-attempt: signatures are normalized so "the same failure twice" guard fires on the same failure
        d = project({"gates": {"full": "true"}, "caps": {"attempts": 5}})
        p = os.path.join(d, "tasks", "101-a.md")
        self.assertEqual(attempt(p, "FAIL src/a.py:17 assert 1 == 2 (0.31s)").returncode, 0)
        r = attempt(p, "FAIL src/a.py:19 assert 1 == 2 (1.02s)")
        self.assertEqual(r.returncode, 2)
        self.assertIn("same failure signature twice", r.stderr)
        self.assertEqual(fm(p, "attempts"), "2", "stopped at 2 of 5")

    def test_a_human_reset_that_forgot_the_signature_does_not_burn_the_fresh_round(self):
        # skills/reef-task/SKILL.md: the human unblock is `attempts: 0`, `status: pending`, `last_failure_sig: ""`;
        # reef-attempt: after a reset "a stale signature must not burn the fresh round"
        d = project()
        p = os.path.join(d, "tasks", "101-a.md")
        attempt(p, "boom one")
        attempt(p, "boom one")
        self.assertEqual(fm(p, "status"), "blocked")
        write(d, "tasks/101-a.md", read(p).replace("status: blocked", "status: pending").replace("attempts: 2", "attempts: 0"))
        r = attempt(p, "boom one")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((fm(p, "attempts"), fm(p, "status")), ("1", "pending"))

    def test_a_tier_raised_between_attempts_keeps_the_count_and_escalates(self):
        # scripts/reef-attempt: "any recorded FAIL escalates to high"; adversary line for design/critical
        d = project()
        p = os.path.join(d, "tasks", "101-a.md")
        attempt(p, "AC-1 red")
        write(d, "tasks/101-a.md", read(p).replace("tier: light", "tier: design").replace("complexity: mech", "complexity: judgment"))
        r = attempt(p)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("effort=high attempt=2/3", r.stdout)
        self.assertIn("tier=design", r.stdout)
        self.assertRegex(r.stdout, r"adversary: model=|guard-pass: feature")

    def test_a_cap_lowered_on_the_main_checkout_binds_a_worktree_copy(self):
        # contract silent on caps.attempts' home; reef-attempt itself says "loop policy has ONE home, the main checkout"
        # (for hunter.*). The owner lowers caps.attempts to 2 on main after a task's worktree was cut: he expects 2.
        d = project()
        w = worktree(d, "101", "task/101")
        write(d, ".reef/config.json", json.dumps({"gates": {"full": "true"}, "paths": {"queue": "reef/queue.md", "runlog": "reef/journal.md"},
                                                  "caps": {"attempts": 2}}))
        p = os.path.join(w, "tasks", "101-a.md")
        attempt(p, "AC-1 red")
        r = attempt(p, "AC-2 red")
        self.assertEqual(r.returncode, 2, "main says caps.attempts 2; the worktree's stale copy said 3:\n" + r.stdout)


class CapAcrossCheckouts(unittest.TestCase):
    def test_a_task_capped_in_its_task_worktree_is_never_dispatched_again(self):
        # scripts/reef-loop.py all_roots: "reef-attempt runs where the task file lives"; PR 295: the round's FAIL lines
        # land in the task worktree's copy. skills/reef-task/SKILL.md: "Exit 2 = blocked: … park the task"; "A HUMAN
        # unblocks" — so the tick must not offer it and must name it parked.
        d = project()
        w = worktree(d, "101", "task/101")
        wp = os.path.join(w, "tasks", "101-a.md")
        for i, why in enumerate(("AC-1 red one", "AC-1 timeout two", "AC-1 crash three"), 1):
            r = attempt(wp, why)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(fm(wp, "status"), "blocked")
        st = tick(d)
        self.assertNotIn("101", st["dispatch_now"], "a capped task offered for dispatch again")
        self.assertNotIn("101", st["verify_now"])
        self.assertIn("101", st["parked"], "the owner is asked: the tick names it parked")
        r = attempt(os.path.join(d, "tasks", "101-a.md"))   # the path the tick's `files` hands the orchestrator
        self.assertEqual(r.returncode, 2, "reef-attempt on the main copy gave a fresh dispatch:\n" + r.stdout)

    def test_a_task_pending_but_at_the_cap_is_named_parked(self):
        # skills/reef-loop/SKILL.md: "the cap (caps.attempts) on an item — blocker to the journal, the item parked".
        # A task at the cap with status pending (the cap lowered, or a half human reset that set status only) is not
        # ready (reef-graph: attempts < cap) — and must not vanish from the tick.
        d = project()
        write(d, "tasks/101-a.md", read(os.path.join(d, "tasks", "101-a.md")).replace("attempts: 0", "attempts: 3"))
        approve(d, "1")
        st = tick(d)
        self.assertNotIn("101", st["dispatch_now"])
        self.assertIn("101", st["parked"], "at-cap but pending: the tick says nothing, the owner is never asked")

    def test_a_blocked_task_in_a_feature_worktree_is_named_parked(self):
        # the plan lives on the feature branch until the row closes (reef-loop.py tick); the tick reads that worktree's
        # ready set — its blocked tasks must reach `parked:` too, or the tick says "nothing ready" and no one is asked
        d = project()
        w = worktree(d, "1", "feat/1")
        write(w, "tasks/101-a.md", read(os.path.join(w, "tasks", "101-a.md")).replace("status: pending", "status: blocked").replace("attempts: 0", "attempts: 3"))
        # the plan is on feat/1 only (the main checkout never held it): drop it from main
        subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", "rm", "-q", "tasks/101-a.md", "tasks/102-b.md"], check=True, capture_output=True)
        subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "plan on its branch"], check=True, capture_output=True)
        approve(w, "1")
        self.assertEqual(fm(os.path.join(w, "tasks", "101-a.md"), "status"), "blocked")
        st = tick(d)
        self.assertNotIn("101", st["dispatch_now"])
        self.assertIn("101", st["parked"], "blocked on the feature branch, invisible on main")


class FailTime(unittest.TestCase):
    """reef-loop.py tick: a hand-back with no newer report is `verify now` … "unless a failure was recorded AFTER that
    hand-back … the next step is the implementer, not the judges again"."""

    def setUp(self):
        self.d = project()
        self.p = os.path.join(self.d, "tasks", "101-a.md")
        self.hb = os.path.join(self.d, ".reef", "ci-local", "handback-101.md")
        self.T = int(time.time()) - 30

    def handback(self, at):
        write(self.d, ".reef/ci-local/handback-101.md", "RUN: agent=implementer task=101\nclaims\n")
        os.utime(self.hb, (at, at))

    @unittest.expectedFailure   # open: M6 (docs/review/stress-2026-11-02.md)
    def test_a_fail_recorded_within_the_hand_backs_second_is_after_it(self):
        # hand-back at T+0.2, the gate red and the FAIL recorded at T+0.8 → the line says T (whole seconds). The
        # failure is AFTER the hand-back; the tick still says verify and the judges re-run on the same red code (PR 295's class)
        self.handback(self.T + 0.2)
        add_fail(self.p, 1, utc(self.T))
        st = tick(self.d)
        self.assertEqual(st["verify_now"], [], "a failure recorded after the hand-back, in the same second, read as before it")
        self.assertIn("101", st["dispatch_now"])

    def test_hand_back_fail_hand_back_in_one_second_verifies_round_two(self):
        add_fail(self.p, 1, utc(self.T))
        self.handback(self.T + 0.9)
        self.assertEqual(tick(self.d)["verify_now"], ["101"])

    def test_a_fail_from_an_earlier_second_never_hides_a_later_hand_back(self):
        add_fail(self.p, 1, utc(self.T - 5))
        self.handback(self.T)
        self.assertEqual(tick(self.d)["verify_now"], ["101"])

    def test_a_report_newer_than_the_hand_back_is_judged_not_redispatched_as_verify(self):
        # pinned: report newer than the hand-back, no FAIL → back to the graph's word (reef-loop.py, PR 295 test)
        self.handback(self.T)
        write(self.d, ".reef/ci-local/report-101.md", "RUN: agent=verifier task=101\nVERDICT: PASS\n")
        os.utime(os.path.join(self.d, ".reef", "ci-local", "report-101.md"), (self.T + 1, self.T + 1))
        st = tick(self.d)
        self.assertEqual(st["verify_now"], [])


class StopAndCaps(unittest.TestCase):
    def test_the_stop_hook_lets_a_turn_end_when_only_a_capped_task_remains(self):
        # reef-loop.py: --assert-no-idle exits 2 only for ready work; a blocked task is the owner's
        d = project()
        p = os.path.join(d, "tasks", "101-a.md")
        attempt(p, "x one"); attempt(p, "x two"); attempt(p, "x three")
        loop(d, "start")
        r = stop_hook(d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("101", tick(d)["parked"])

    def test_growth_exactly_at_the_cap_is_not_over(self):
        d = project({"gates": {"full": "true"}, "paths": {"queue": "reef/queue.md", "runlog": "reef/journal.md"}, "caps": {"task_growth": 20000}})
        write(d, ".reef/cost/tasks.json", json.dumps({"101": {"s1": {"growth": 20000}}}))
        self.assertEqual(tick(d)["over_growth"], [])

    @unittest.expectedFailure   # open: L2 (docs/review/stress-2026-11-02.md)
    def test_context_warn_without_a_ceiling_does_not_claim_zero_room(self):
        # contract silent: reef-guard check_context_ceiling with caps.context_warn set and no caps.context_tokens
        # tells the model "0 tokens of room … /clear BEFORE the ceiling" — there is no ceiling; it reads as "stop now"
        d = project({"gates": {"full": "true"}, "caps": {"context_warn": 5000}})
        tp = write(d, "session.jsonl", json.dumps({"type": "assistant", "requestId": "r1", "message": {"usage": {
            "input_tokens": 7000, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 1}, "content": []}}) + "\n")
        payload = {"tool_name": "Task", "cwd": d, "transcript_path": tp, "tool_input": {"subagent_type": "reef:mechanic", "prompt": "rebase"}}
        r = subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("context_warn", r.stdout)
        self.assertNotIn(" 0 tokens of room", r.stdout)


if __name__ == "__main__":
    unittest.main()
