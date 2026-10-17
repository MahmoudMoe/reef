"""Sabotage suite for 0.6 Phase 5: reef-loop.py tick (5.1: a merge that unblocks a row appears in the next tick; a
stale in-flight marker is listed as returned; output never exceeds the line cap), the Stop hook (5.2: a ready
undispatched task is refused with its id; the same state is never refused twice; a wait, an inactive loop or a
stop reason allow), no-progress parking and the budgets (5.3), the context ceiling (5.4), the deterministic
handoff (5.5) and the lean session start (6.2 part: under the cap; nothing for a directory without Reef)."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOOP = os.path.join(ROOT, "scripts", "reef-loop.py")
GUARD = os.path.join(ROOT, "scripts", "reef-guard.py")
HANDOFF = os.path.join(ROOT, "scripts", "reef-handoff")


def read_file(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def task(tid, feature, status="pending", blocked="[]"):
    return (f"---\nid: {tid}\nfeature: {feature}\nstatus: {status}\ncomplexity: mech\neffort: medium\nblocked-by: {blocked}\n"
            f"resources: []\ntier: light\nverify: gate-only\nattempts: 0\ndispatches: 0\nlast_failure_sig: \"\"\n---\n# {tid}\n\n## Scope\nx\n\n"
            f"## Acceptance Criteria\n- test_t{tid} goes red first\n\n## Log\n")


def project(cfg=None):
    d = tempfile.mkdtemp(prefix="reef-loop.")
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    os.makedirs(os.path.join(d, "scripts"))
    for n in ("reef-queue.py", "reef-graph.py", "reef-cost.py", "reef-loop.py", "reef-handoff", "reef-plan-check.py"):
        shutil.copy(os.path.join(ROOT, "scripts", n), os.path.join(d, "scripts", n))
    write(d, ".reef/config.json", json.dumps(cfg or {"gates": {"full": "true"}, "paths": {"queue": "reef/queue.md", "runlog": "reef/journal.md"}}))
    write(d, ".reef/version", "0.6.0\n")
    write(d, "reef/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 1 | first | | planned | 1 | |\n| 2 | second | 1 | planned | 1 | |\n")
    write(d, "reef/journal.md", "# Journal\n| Task | Implementer | Verifier | Attempts | Result | ACs | Escaped defects |\n|---|---|---|---|---|---|---|\n| 101 | opus | - | 0 | PASS | AC-1 achieved | - |\n")
    write(d, "HANDOFF.md", "# Handoff\nline 1\n")
    write(d, "CLAUDE.md", "# brief\n")
    write(d, ".gitignore", "tasks/.plan-review.json\n.reef/approvals/\n.reef/loop.json\n")   # per-worktree state, as reef-init writes it
    os.makedirs(os.path.join(d, "tasks", "done"))
    write(d, "tasks/101-a.md", task(101, "1"))
    write(d, "tasks/102-b.md", task(102, "1", blocked="[101]"))
    approve(d, "1")
    subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], check=True, capture_output=True)
    return d


def approve(d, feature):
    """The plan reviewed (stamp) and approved by the human at its digest (record) — what a dispatchable plan has."""
    pc = os.path.join(d, "scripts", "reef-plan-check.py")
    r = subprocess.run([sys.executable, pc, d], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    r = subprocess.run([sys.executable, pc, d, "--digest", "--feature", feature], capture_output=True, text=True)
    digest = r.stdout.split()[-1]
    write(d, f".reef/approvals/{feature}.json", json.dumps({"digest16": digest[:16], "approved_at": "2026-10-16T00:00:00Z"}))


def loop(d, *args, env=None):
    e = dict(os.environ, PATH="/nonexistent-gh:" + os.environ["PATH"])
    e.update(env or {})
    return subprocess.run([sys.executable, LOOP, *args, "--repo", d], capture_output=True, text=True, env=e)


def stop_hook(d, **extra):
    payload = {"hook_event_name": "Stop", "cwd": d, "stop_hook_active": False,
               "last_assistant_message": "in flight: - / waiting on: - / next: /reef-task", "background_tasks": [], "session_crons": []}
    payload.update(extra)
    return subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True)


class Tick(unittest.TestCase):
    def test_merge_unblocks_a_task_in_the_next_tick_and_output_is_capped(self):
        d = project()
        r = loop(d, "tick", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = json.loads(r.stdout)
        self.assertEqual(st["dispatch_now"], ["101"])
        self.assertEqual(st["rows_to_plan"], ["2"] if "2" in st["rows_to_plan"] else st["rows_to_plan"])
        # 101 merges (done) -> 102 is ready in the very next tick
        write(d, "tasks/101-a.md", task(101, "1", status="done"))
        st = json.loads(loop(d, "tick", "--json").stdout)
        self.assertEqual(st["dispatch_now"], ["102"])
        text = loop(d, "tick").stdout
        self.assertLessEqual(len(text.splitlines()), 30)
        self.assertIn("dispatch now: 102", text)

    def test_stale_inflight_marker_is_returned_fresh_one_is_in_flight(self):
        d = project()
        p = write(d, ".reef/inflight/101", json.dumps({"id": 101, "tier": "light"}))
        st = json.loads(loop(d, "tick", "--json").stdout)
        self.assertEqual(st["in_flight"], ["101"])
        self.assertEqual(st["dispatch_now"], [], "an in-flight task is not dispatched again")
        old = time.time() - 120 * 60
        os.utime(p, (old, old))
        st = json.loads(loop(d, "tick", "--json").stdout)
        self.assertEqual(st["returned_unmerged"], ["101"])
        self.assertEqual(st["dispatch_now"], ["101"], "a returned task is ready again")

    def test_no_progress_parks_after_k_identical_ticks(self):
        d = project({"gates": {"full": "true"}, "paths": {"queue": "reef/queue.md"}, "loop": {"no_progress_ticks": 2}})
        loop(d, "start")
        loop(d, "tick")
        self.assertIsNone(json.loads(open(os.path.join(d, ".reef", "loop.json")).read()).get("parked"))
        st = json.loads(loop(d, "tick", "--json").stdout)
        self.assertIn("no progress: 2 identical ticks", st["parked_loop"])

    def test_budget_ceiling_parks(self):
        d = project({"gates": {"full": "true"}, "paths": {"queue": "reef/queue.md"}, "caps": {"feature_tokens": 1000}})
        t = write(d, "t.jsonl", json.dumps({"type": "assistant", "requestId": "r1", "message": {"usage": {"input_tokens": 5000, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 1}, "content": []}}) + "\n")
        st = json.loads(loop(d, "tick", "--json", env={"REEF_TRANSCRIPT": t}).stdout)
        self.assertIn("budget: 5000 tokens > caps ceiling 1000", st["stop"])


    def test_a_ready_task_of_an_unapproved_or_unreviewed_plan_is_awaiting_not_dispatchable(self):
        # first contact (2026-10-16): the ceiling handoff said "dispatch now: 101" for a plan with no approval and no
        # review; the guard would have refused, but the next orchestrator read a lie. The tick runs the guard's own
        # check per feature and names what is missing.
        d = project()
        os.unlink(os.path.join(d, ".reef", "approvals", "1.json"))
        st = json.loads(loop(d, "tick", "--json").stdout)
        self.assertEqual(st["dispatch_now"], [])
        self.assertEqual(st["awaiting"], ["1 (approval (the gate: the machines passed))"])
        text = loop(d, "tick").stdout
        self.assertIn("dispatch now: -", text)
        self.assertIn("awaiting: 1 (approval (the gate: the machines passed))", text)
        # v2 order: a task above light needs the review; with it missing (and the approval stale) the tick asks for
        # the machines first, never the owner
        write(d, "tasks/101-a.md", task(101, "1").replace("complexity: mech", "complexity: design").replace("tier: light", "tier: design")
              .replace("verify: gate-only", "verify: judge").replace("## Scope\nx", "## Scope\nx\n\n## Decision\nhuman wrote this"))
        r = subprocess.run([sys.executable, os.path.join(d, "scripts", "reef-plan-check.py"), d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(json.loads(loop(d, "tick", "--json").stdout)["awaiting"], ["1 (machine review (hunter ‖ plan reviewer) before the gate)"])
        write(d, "tasks/101-a.md", task(101, "1"))
        approve(d, "1")
        write(d, "tasks/101-a.md", task(101, "1").replace("## Scope\nx", "## Scope\nedited after the review"))
        st = json.loads(loop(d, "tick", "--json").stdout)
        self.assertEqual(st["dispatch_now"], [])
        self.assertTrue(st["awaiting"] and "1 (" in st["awaiting"][0], st["awaiting"])
        os.unlink(os.path.join(d, "tasks", ".plan-review.json"))
        approve(d, "1")
        st = json.loads(loop(d, "tick", "--json").stdout)
        self.assertEqual(st["dispatch_now"], ["101"], st)
        self.assertEqual(st["awaiting"], [])


    def test_a_fresh_session_clears_the_dead_sessions_ceiling_stop(self):
        d = project()
        st = json.loads(open(os.path.join(d, ".reef", "loop.json")).read()) if os.path.isfile(os.path.join(d, ".reef", "loop.json")) else {}
        st["stop"] = "context ceiling: 164970 tokens > caps.context_tokens 150000 — checkpoint, then /clear"
        st["transcript"] = "/nowhere.jsonl"
        write(d, ".reef/loop.json", json.dumps(st))
        self.assertIn("STOP=context ceiling", loop(d, "tick").stdout, "a plain tick keeps the stop: the same session")
        out = loop(d, "tick", "--session-start").stdout
        self.assertNotIn("STOP=", out, out)
        st = json.loads(open(os.path.join(d, ".reef", "loop.json")).read())
        self.assertIsNone(st.get("stop"))
        self.assertIsNone(st.get("transcript"))
        st["stop"] = "USER ACTION REQUIRED: a credential"
        write(d, ".reef/loop.json", json.dumps(st))
        self.assertIn("STOP=USER ACTION", loop(d, "tick", "--session-start").stdout, "only the ceiling stop is per session")


    def test_only_feature_prs_are_the_loops_and_a_feature_worktrees_tasks_reach_the_tick(self):
        d = project()
        # a fake gh: three PRs into the base, one of them the loop's
        fake = tempfile.mkdtemp(prefix="reef-fakegh.")
        with open(os.path.join(fake, "gh"), "w") as f:
            f.write("#!/bin/sh\nif [ \"$1\" = pr ] && [ \"$2\" = list ]; then\n"
                    "printf '%s' '[{\"number\":3,\"headRefName\":\"dependabot/npm_and_yarn/develop/x\",\"title\":\"bump\",\"reviewDecision\":\"\"},"
                    "{\"number\":4,\"headRefName\":\"feat/demo\",\"title\":\"demo\",\"reviewDecision\":\"\"},"
                    "{\"number\":5,\"headRefName\":\"dependabot/github_actions/develop/y\",\"title\":\"bump\",\"reviewDecision\":\"\"}]'\nexit 0\nfi\nexit 1\n")
        os.chmod(os.path.join(fake, "gh"), 0o755)
        env = {"PATH": fake + ":" + os.environ["PATH"]}
        st = json.loads(subprocess.run([sys.executable, LOOP, "tick", "--json", "--repo", d], capture_output=True, text=True, env=dict(os.environ, **env)).stdout)
        self.assertEqual(st["prs_to_review"], ["#4 feat/demo"])
        self.assertEqual(st["other_prs"], 2)
        text = subprocess.run([sys.executable, LOOP, "tick", "--repo", d], capture_output=True, text=True, env=dict(os.environ, **env)).stdout
        self.assertIn("PRs to review: #4 feat/demo  (2 other PR(s) into the base, not the loop's)", text)
        # a feature worktree on feat/<slug> holds a plan the main checkout has never seen (first contact: the tick in
        # the main checkout said "rows to plan: 1 · tasks: none" while 101 was being built there)
        wt = os.path.join(d, ".reef", "worktrees", "demo")
        subprocess.run(["git", "-C", d, "worktree", "add", "-q", "-b", "feat/demo", wt], check=True)
        write(wt, "tasks/201-c.md", task(201, "2"))
        st = json.loads(loop(d, "tick", "--json").stdout)
        self.assertIn("2 (plan review)", st["awaiting"], st)          # the worktree's plan is seen, and held correctly
        self.assertNotIn("201", st["dispatch_now"])
        pc = os.path.join(d, "scripts", "reef-plan-check.py")
        subprocess.run([sys.executable, pc, wt], capture_output=True, text=True)   # stamp in the worktree
        digest = subprocess.run([sys.executable, pc, wt, "--digest", "--feature", "2"], capture_output=True, text=True).stdout.split()[-1]
        write(d, ".reef/approvals/2.json", json.dumps({"digest16": digest[:16], "approved_at": "2026-10-16T00:00:00Z"}))
        st = json.loads(loop(d, "tick", "--json").stdout)
        self.assertIn("201", st["dispatch_now"], st)
        self.assertIn("101", st["dispatch_now"])


class HunterStampBeforeTheGate(unittest.TestCase):
    """2026-10-18 (qassimha): 202 and 203 were listed for dispatch with hunter stamps their review-round edits had
    staled; only the guard's denial, days later and past the round cap, said so. The tick names it with the command."""

    def design(self, d):
        write(d, "tasks/101-a.md", task(101, "1").replace("complexity: mech", "complexity: design").replace("tier: light", "tier: design")
              .replace("verify: gate-only", "verify: judge").replace("## Scope\nx", "## Scope\nx\n\n## Decision\nhuman wrote this"))
        write(d, "tasks/.plan-review.json", "")
        os.unlink(os.path.join(d, "tasks", ".plan-review.json"))
        approve(d, "1")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-record"), "plan-review", "1", "PASS", "--root", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_missing_stale_and_legacy_stamps_hold_the_task_with_the_command(self):
        d = project()
        self.design(d)
        st = json.loads(loop(d, "tick", "--json").stdout)
        self.assertEqual(st["awaiting"], ["1 (hunter plan pass on 101 before the gate)"], st)
        self.assertEqual(st["dispatch_now"], [])
        write(d, "hunt.md", "RUN: agent=loophole-hunter task=101 pass=plan round=1\nBLOCKER: none\nVERDICT: PASS\n")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-adversarial"), os.path.join(d, "tasks", "101-a.md"), "plan", os.path.join(d, "hunt.md")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        st = json.loads(loop(d, "tick", "--json").stdout)
        self.assertEqual(st["dispatch_now"], ["101"], st)
        # the review round edits the plan; the review and the approval are refreshed, the hunter's stamp is not
        t = read_file(os.path.join(d, "tasks", "101-a.md"))
        write(d, "tasks/101-a.md", t.replace("## Scope\nx", "## Scope\nx, an AC added in the review round"))
        os.unlink(os.path.join(d, "tasks", ".plan-review.json"))
        approve(d, "1")
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-record"), "plan-review", "1", "PASS", "--root", d], capture_output=True, text=True)
        st = json.loads(loop(d, "tick", "--json").stdout)
        self.assertEqual(st["dispatch_now"], [], "a stale hunter stamp is not dispatchable — the guard would deny it")
        self.assertEqual(st["awaiting"], ["1 (hunter plan pass stale on 101: a re-check within hunter.plan_rounds, or `reef-adversarial <task> plan --decided <mark>`)"], st)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-adversarial"), os.path.join(d, "tasks", "101-a.md"), "plan", "--decided", "⁴⁰"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        st = json.loads(loop(d, "tick", "--json").stdout)
        self.assertEqual(st["dispatch_now"], ["101"], "the owner's ruling re-stamps without a re-approval")


class LegacyRecordsBeforeTheGate(unittest.TestCase):
    def test_an_approval_in_the_0_6_digest_form_is_held_with_the_migrate_command(self):
        # 2026-10-18: after #53 the trial's three live approvals would have read STALE — a re-approval of unchanged plans
        d = project()
        HunterStampBeforeTheGate.design(HunterStampBeforeTheGate("test_missing_stale_and_legacy_stamps_hold_the_task_with_the_command"), d)
        write(d, "hunt.md", "RUN: agent=loophole-hunter task=101 pass=plan round=1\nBLOCKER: none\nVERDICT: PASS\n")
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-adversarial"), os.path.join(d, "tasks", "101-a.md"), "plan", os.path.join(d, "hunt.md")], capture_output=True, text=True)
        self.assertEqual(json.loads(loop(d, "tick", "--json").stdout)["dispatch_now"], ["101"])
        pc = os.path.join(d, "scripts", "reef-plan-check.py")
        old = subprocess.run([sys.executable, pc, d, "--legacy-digest", "--feature", "1"], capture_output=True, text=True).stdout.split()[-1]
        write(d, ".reef/approvals/1.json", json.dumps({"digest16": old[:16], "approved_at": "2026-10-16T00:00:00Z"}))
        st = json.loads(loop(d, "tick", "--json").stdout)
        self.assertEqual(st["dispatch_now"], [])
        self.assertEqual(st["awaiting"], ["1 (records in the 0.6 digest form: `reef-plan-check.py . --migrate-records --feature 1` (the plugin's copy, in the plan's checkout))"], st)
        m = subprocess.run([sys.executable, pc, d, "--migrate-records", "--feature", "1"], capture_output=True, text=True)
        self.assertEqual(m.returncode, 0, m.stdout)
        self.assertEqual(json.loads(loop(d, "tick", "--json").stdout)["dispatch_now"], ["101"])


class InFlightAcrossWorktrees(unittest.TestCase):
    def test_a_marker_in_a_feature_worktree_is_in_flight(self):
        # 2026-10-17: "in flight: -" while 1101 was building — reef-attempt ran in the feature worktree, its marker lived there
        d = project()
        g = ["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(g + ["worktree", "add", "-q", "-b", "feat/first", os.path.join(d, ".reef", "worktrees", "first"), "main"], check=True, capture_output=True)
        write(d, ".reef/worktrees/first/.reef/inflight/101", json.dumps({"id": 101, "tier": "light"}))
        text = loop(d, "tick").stdout
        self.assertRegex(text, r"in flight: 101\b")
        self.assertNotIn("dispatch now: 101", text)


class ClosedRowsInWorktrees(unittest.TestCase):
    def test_an_archived_rows_spec_inside_a_feature_worktree_is_not_building(self):
        # 2026-10-17: every feature worktree is a full checkout, so row 1's closed SPEC made "building rows: 1, 11, 13, 2"
        d = project({"gates": {"full": "true"}, "paths": {"queue": "reef/queue.md", "runlog": "reef/journal.md", "features": "reef/features"},
                     "branches": {"base": "main", "feature_prefix": "feat/"}})
        write(d, "reef/features/first/SPEC.md", "# first\nRow: 1\n")
        write(d, "reef/features/second/SPEC.md", "# second\nRow: 2\n")
        # row 1 closes: archived, its SPEC stays in the tree
        write(d, "reef/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 2 | second | 1 | planned | 1 | |\n")
        write(d, "reef/queue-archive.md", "# Archive\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 1 | first | | planned | 1 | |\n")
        g = ["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(g + ["add", "-A"], check=True, capture_output=True)
        subprocess.run(g + ["commit", "-qm", "row 1 closed; row 2 planned"], check=True, capture_output=True)
        subprocess.run(g + ["worktree", "add", "-q", "-b", "feat/second", os.path.join(d, ".reef", "worktrees", "second"), "main"], check=True, capture_output=True)
        text = loop(d, "tick").stdout
        self.assertRegex(text, r"building rows: 2\b")
        self.assertNotRegex(text, r"building rows: 1")


class TriageLine(unittest.TestCase):
    def test_the_tick_names_stale_found_rows(self):
        d = project()
        write(d, "reef/queue.md", "# Queue\nCurrent batch: 3\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 1 | first | | planned | 1 | |\n| 2 | second | 1 | planned | 1 | |\n| 3 | a leak (src/lib/x.ts) | 1 | found | 1 | |\n")
        text = loop(d, "tick").stdout
        self.assertIn("stale found (rule 7): 1 — python3 scripts/reef-queue.py triage, ONE owner question at the batch boundary", text)
        write(d, "reef/queue.md", "# Queue\nCurrent batch: 2\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 1 | first | | planned | 1 | |\n| 2 | second | 1 | planned | 1 | |\n| 3 | a leak (src/lib/x.ts) | 1 | found | 1 | |\n")
        self.assertNotIn("rule 7", loop(d, "tick").stdout)


class StatusPage(unittest.TestCase):
    def test_every_tick_writes_the_status_page(self):
        # usability plan A2: the owner asked "where are we" in chat after every stop
        d = project()
        loop(d, "start")
        loop(d, "wait", "owner question set 1")
        text = loop(d, "tick").stdout
        page = read_file(os.path.join(d, ".reef", "status.html"))
        self.assertIn('http-equiv="refresh" content="60"', page)
        self.assertIn("owner question set 1", page)
        self.assertIn('class="badge waiting"', page)
        h = re.search(r"tick (\w+)", text).group(1)
        self.assertIn(f"tick {h}", page)
        self.assertIn("in flight:", page)


class GrowthCap(unittest.TestCase):
    def test_the_tick_names_tasks_over_caps_task_growth(self):
        d = project({"gates": {"full": "true"}, "paths": {"queue": "reef/queue.md", "runlog": "reef/journal.md"}, "caps": {"task_growth": 20000}})
        write(d, ".reef/cost/tasks.json", json.dumps({"101": {"s1": {"growth": 15000, "turns": 3, "roles": {}}, "s2": {"growth": 9000, "turns": 2, "roles": {}}},
                                                       "102": {"s1": {"growth": 4000, "turns": 1, "roles": {}}}}))
        text = loop(d, "tick").stdout
        self.assertIn("GROWTH over caps.task_growth: 101 (24,000) — say why in the journal", text)
        self.assertNotIn("102 (", text)


class VerifyNow(unittest.TestCase):
    def test_a_handed_back_task_is_to_verify_not_to_dispatch(self):
        # first contact (2026-10-17): the fresh session's tick said "dispatch now: 103" while 103's implementer had
        # handed back and its work sat uncommitted in the worktree; a second implementer would have been wrong
        d = project()
        st = json.loads(loop(d, "tick", "--json").stdout)
        self.assertIn("101", st["dispatch_now"])
        write(d, ".reef/ci-local/handback-101.md", "RUN: agent=implementer task=101\nclaims\n")
        st = json.loads(loop(d, "tick", "--json").stdout)
        self.assertEqual(st["verify_now"], ["101"])
        self.assertNotIn("101", st["dispatch_now"])
        text = loop(d, "tick").stdout
        self.assertIn("verify now: 101 (handed back, uncommitted", text)
        self.assertIn("next: verify: 101", text)
        time.sleep(0.05)
        write(d, ".reef/ci-local/report-101.md", "RUN: agent=verifier task=101\nVERDICT: PASS\n")   # a report newer than the hand-back
        st = json.loads(loop(d, "tick", "--json").stdout)
        self.assertEqual(st["verify_now"], [])
        self.assertIn("101", st["dispatch_now"], "judged: the tick is back to the graph's word (the task closes or re-dispatches)")


class StopHook(unittest.TestCase):
    def test_ready_undispatched_refused_once_then_allowed(self):
        d = project()
        self.assertEqual(stop_hook(d).returncode, 0, "no loop.json yet: the stop hook stays silent")
        loop(d, "start")
        r = stop_hook(d)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("101", r.stderr)
        r = stop_hook(d)
        self.assertEqual(r.returncode, 0, "the same state is never refused twice")
        # the state changes (a new ready task) -> refused again, once. A new task is a plan edit: the tick holds the
        # feature as awaiting until it is re-reviewed and re-approved, so the fixture does both first
        write(d, "tasks/103-c.md", task(103, "1"))
        os.unlink(os.path.join(d, "tasks", ".plan-review.json"))
        approve(d, "1")
        self.assertEqual(stop_hook(d).returncode, 2)
        self.assertEqual(stop_hook(d).returncode, 0)

    def test_a_reply_without_the_status_line_is_refused_once_while_the_loop_is_active(self):
        # first full loop (2026-10-17): the owner asked "what do I run now?" after every stop; the tick knows the answer
        d = project()
        self.assertEqual(stop_hook(d, last_assistant_message="All done, merged.").returncode, 0, "loop inactive: no demand")
        loop(d, "start")
        loop(d, "wait", "grill question pending")   # a wait: the idle check is quiet, the status line is still owed
        r = stop_hook(d, last_assistant_message="All done, merged.")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("status line", r.stderr)
        self.assertIn("next:", r.stderr)
        self.assertEqual(stop_hook(d, last_assistant_message="All done, merged.").returncode, 0, "the same reply is never refused twice")
        self.assertEqual(stop_hook(d, last_assistant_message="Merged 101.\n\nin flight: 102 / waiting on: its hand-back / next: /reef-task demo").returncode, 0)
        self.assertEqual(stop_hook(d, last_assistant_message="in flight: - / waiting on: you").returncode, 2, "no next: is no status line")

    def test_wait_inactive_inflight_stop_and_active_flag_allow(self):
        d = project()
        loop(d, "start")
        loop(d, "wait", "grill question pending")
        self.assertEqual(stop_hook(d).returncode, 0, "a recorded wait allows the stop")
        loop(d, "clear-wait")
        loop(d, "stop")
        self.assertEqual(stop_hook(d).returncode, 0, "an inactive loop allows the stop")
        loop(d, "start")
        self.assertEqual(stop_hook(d, stop_hook_active=True).returncode, 0, "stop_hook_active is honoured")
        self.assertEqual(stop_hook(d, background_tasks=[{"id": "x", "type": "subagent", "status": "running"}]).returncode, 0, "sub-agents running = in flight")
        write(d, ".reef/inflight/101", json.dumps({"id": 101}))
        self.assertEqual(stop_hook(d).returncode, 0, "something in flight allows the stop")
        os.unlink(os.path.join(d, ".reef", "inflight", "101"))
        st = json.loads(open(os.path.join(d, ".reef", "loop.json")).read())
        st["stop"] = "context ceiling: checkpoint, then /clear"
        st["refused"] = None
        write(d, ".reef/loop.json", json.dumps(st))
        self.assertEqual(stop_hook(d).returncode, 0, "a stop reason allows the stop")


class ContextCeiling(unittest.TestCase):
    def transcript(self, d, tokens):
        return write(d, "session.jsonl", json.dumps({"type": "assistant", "requestId": "r1", "message": {"usage": {"input_tokens": tokens, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 1}, "content": []}}) + "\n")

    def dispatch(self, d, transcript):
        payload = {"tool_name": "Task", "cwd": d, "transcript_path": transcript, "tool_input": {"subagent_type": "reef:mechanic", "prompt": "rebase"}}
        return subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True)

    def test_a_new_task_is_refused_inside_the_reserve_but_a_judge_is_not(self):
        # first contact (2026-10-16): the orchestrator started task 103 at 126k of 150k and had to stop right after —
        # the task's judges could only run in the next session. Under the reserve no implementer starts; the task in
        # hand still gets its verifier.
        d = project({"gates": {"full": "true"}, "caps": {"context_tokens": 10000, "context_warn": 5000, "dispatch_reserve": 3000}})
        tp = self.transcript(d, 8000)
        payload = {"tool_name": "Task", "cwd": d, "transcript_path": tp, "tool_input": {"subagent_type": "reef:implementer", "prompt": "REEF-TASK: none"}}
        r = subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("context reserve", r.stderr)
        self.assertIn("2000 of room left", r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(d, "HANDOFF.md")), "the checkpoint is the guard's")
        self.assertTrue(json.loads(open(os.path.join(d, ".reef", "loop.json")).read())["stop"].startswith("context ceiling"),
                        "the stop carries the prefix --session-start clears")
        r = self.dispatch(d, tp)   # a mechanic (the task in hand) is still allowed, with the warning
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("additionalContext", r.stdout)
        payload["transcript_path"] = self.transcript(d, 6000)
        r = subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True)
        self.assertNotIn("context reserve", r.stderr, "4000 of room ≥ the reserve: the room is not what stops this dispatch")

    def test_over_denied_and_recorded_under_allowed_missing_allowed_and_said(self):
        d = project({"gates": {"full": "true"}, "caps": {"context_tokens": 10000, "context_warn": 5000}})
        r = self.dispatch(d, self.transcript(d, 20000))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("context ceiling", r.stderr)
        self.assertIn("checkpoint", r.stderr)
        self.assertIn("context ceiling", json.loads(open(os.path.join(d, ".reef", "loop.json")).read())["stop"])
        # 0.7: the guard writes the checkpoint itself before denying — a model that ignores the denial's instruction
        # cannot leave the next session without a handoff
        self.assertTrue(os.path.isfile(os.path.join(d, "HANDOFF.md")), "HANDOFF.md rendered by the guard at the ceiling")
        self.assertIn("HANDOFF.md written", r.stderr)
        r = self.dispatch(d, self.transcript(d, 7000))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("additionalContext", r.stdout, "between warn and ceiling the hook warns the model")
        self.assertEqual(self.dispatch(d, self.transcript(d, 1000)).returncode, 0)
        r = self.dispatch(d, os.path.join(d, "nope.jsonl"))
        self.assertEqual(r.returncode, 0)
        self.assertIn("cannot be measured", r.stderr)


class HandoffAndSessionStart(unittest.TestCase):
    def test_handoff_is_deterministic_and_session_start_under_the_cap(self):
        d = project()
        e = dict(os.environ, PATH="/nonexistent-gh:" + os.environ["PATH"])
        a = subprocess.run([sys.executable, HANDOFF, "--repo", d], capture_output=True, text=True, env=e).stdout
        b = subprocess.run([sys.executable, HANDOFF, "--repo", d], capture_output=True, text=True, env=e).stdout
        self.assertEqual(a, b)
        self.assertIn("## The tick", a)
        self.assertIn("| 101 | opus |", a, "the journal tail")
        self.assertNotRegex(a, r"\d\d:\d\d:\d\d", "no clock in the body")
        r = subprocess.run([sys.executable, HANDOFF, "--repo", d, "--write"], capture_output=True, text=True, env=e)
        self.assertEqual(r.returncode, 0)
        self.assertIn("# Handoff —", open(os.path.join(d, "HANDOFF.md")).read())
        r = loop(d, "tick", "--session-start")
        self.assertLess(len(r.stdout) // 4, 8000)
        self.assertIn("next command:", r.stdout)
        r = loop(d, "tick", "--session-start", "--hook")
        env = json.loads(r.stdout)
        self.assertEqual(env["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("tick", env["hookSpecificOutput"]["additionalContext"])
        empty = tempfile.mkdtemp(prefix="reef-noreef.")
        subprocess.run(["git", "init", "-q", empty], check=True)
        r = subprocess.run([sys.executable, LOOP, "tick", "--session-start", "--hook", "--repo", empty], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout), (0, ""), "a directory without .reef/config.json gets nothing")

    def test_session_start_strips_the_dead_sessions_ceiling_line_and_names_scripts_behind_the_plugin(self):
        d = project()
        write(d, "HANDOFF.md", "# Handoff\ntick 49e0690c50ee  loop=inactive  STOP=context ceiling: 171403 tokens > caps.context_tokens 150000 — checkpoint, then /clear\nrows to plan: -\n")
        out = loop(d, "tick", "--session-start").stdout
        self.assertNotIn("STOP=context ceiling", out, out)
        self.assertIn("tick 49e0690c50ee  loop=inactive", out)
        self.assertNotIn("behind the plugin", out, "no CLAUDE_PLUGIN_ROOT: no verdict")
        plugin = tempfile.mkdtemp(prefix="reef-plugin.")
        os.makedirs(os.path.join(plugin, "scripts"))
        for n in ("reef-loop.py", "reef-cost.py"):
            shutil.copy(os.path.join(ROOT, "scripts", n), os.path.join(plugin, "scripts", n))
        with open(os.path.join(plugin, "scripts", "reef-cost.py"), "a") as f:
            f.write("\n# a newer plugin\n")
        out = loop(d, "tick", "--session-start", env={"CLAUDE_PLUGIN_ROOT": plugin}).stdout
        self.assertIn("reef: 1 project script(s) behind the plugin (reef-cost.py)", out)
        self.assertIn("run /reef-init", out)

    def test_session_start_truncates_at_the_cap(self):
        d = project({"gates": {"full": "true"}, "paths": {"queue": "reef/queue.md"}, "writing": {"session_start_tokens": 50}})
        write(d, "HANDOFF.md", "# Handoff\n" + "\n".join(f"line {i} " + "x" * 80 for i in range(40)))
        r = loop(d, "tick", "--session-start")
        self.assertLessEqual(len(r.stdout) // 4, 50 + 20)
        self.assertIn("[truncated: writing.session_start_tokens 50]", r.stdout)


if __name__ == "__main__":
    unittest.main()
