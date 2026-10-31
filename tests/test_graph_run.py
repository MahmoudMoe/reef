"""reef-graph-run (0.7, workflow v2 phase 3): the task graph as a Claude Code workflow — gated, bookkept like a chat dispatch,
settled with the same checks."""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import test_loop as T  # noqa: E402  (the loop's project fixture: an approved, reviewed light task 101)


def graph_project():
    d = T.project()
    for n in ("reef-attempt", "reef-claims.py", "reef-adversarial", "reef-snapshot.sh", "reef-gate.sh", "reef-graph-run.py"):
        shutil.copy(os.path.join(ROOT, "scripts", n), os.path.join(d, "scripts", n))
    return d


def g(d, *args):
    return subprocess.run([sys.executable, os.path.join(d, "scripts", "reef-graph-run.py"), *args, "--repo", d], capture_output=True, text=True)


def pass_gate(d):
    g(d, "probe")
    with open(os.path.join(d, ".reef", "graph", "probe-results.json"), "w") as f:
        json.dump({"denied": True, "output": "reef-guard DENY: writing under .reef/approvals/"}, f)
    return g(d, "probe-check", ".reef/graph/probe-results.json")


class Gate(unittest.TestCase):
    def test_generate_refuses_until_the_probe_proves_the_hooks_reach_workflow_agents(self):
        d = graph_project()
        r = g(d, "generate")
        self.assertEqual(r.returncode, 1)
        self.assertIn("graph mode is OFF", r.stderr)
        r = g(d, "probe")
        self.assertEqual(r.returncode, 0, r.stderr)
        js = open(os.path.join(d, ".reef", "graph", "probe.js")).read()
        self.assertIn("export const meta", js)
        self.assertIn(".reef/approvals/graph-probe.json", js)
        self.assertIn("agentType: 'reef:mechanic'", js)
        # the agent says it was not denied → gate failed, graph mode stays off
        with open(os.path.join(d, ".reef", "graph", "probe-results.json"), "w") as f:
            json.dump({"denied": False, "output": "wrote it"}, f)
        r = g(d, "probe-check", ".reef/graph/probe-results.json")
        self.assertEqual(r.returncode, 1)
        self.assertIn("GATE FAILED", r.stdout)
        self.assertEqual(g(d, "generate").returncode, 1)
        # denied but the file exists anyway → failed, and the forged record is removed
        os.makedirs(os.path.join(d, ".reef", "approvals"), exist_ok=True)
        open(os.path.join(d, ".reef", "approvals", "graph-probe.json"), "w").write("{}")
        with open(os.path.join(d, ".reef", "graph", "probe-results.json"), "w") as f:
            json.dump({"denied": True, "output": "x"}, f)
        r = g(d, "probe-check", ".reef/graph/probe-results.json")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(d, ".reef", "approvals", "graph-probe.json")))
        # the agent's flag alone is not a denial: the guard's own words must be in the output (the runner reads this unattended)
        with open(os.path.join(d, ".reef", "graph", "probe-results.json"), "w") as f:
            json.dump({"denied": True, "output": "I did not run it"}, f)
        r = g(d, "probe-check", ".reef/graph/probe-results.json")
        self.assertEqual(r.returncode, 1); self.assertIn("guard's own words", r.stdout)
        # no result at all: FAILED, recorded (the runner probes once, not at every start), the cause named
        r = g(d, "probe-check", ".reef/graph/no-such-results.json")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        rec = json.load(open(os.path.join(d, ".reef", "graph", "gate.json")))
        self.assertFalse(rec["ok"]); self.assertIn("Workflow tool", rec["why"]); self.assertIn("Workflow tool", r.stdout)
        # no result AND a leaked file: the leak names itself, and is removed
        open(os.path.join(d, ".reef", "approvals", "graph-probe.json"), "w").write("{}")
        r = g(d, "probe-check", ".reef/graph/no-such-results.json")
        self.assertEqual(r.returncode, 1); self.assertIn("was created", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(d, ".reef", "approvals", "graph-probe.json")))
        # denied and no file → ok
        r = pass_gate(d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("GATE OK", r.stdout)
        self.assertTrue(json.load(open(os.path.join(d, ".reef", "graph", "gate.json")))["ok"])


class Generate(unittest.TestCase):
    def test_the_script_carries_the_tasks_and_the_dispatch_is_bookkept_like_the_guards(self):
        d = graph_project()
        pass_gate(d)
        r = g(d, "generate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("graph: 1 task(s): 101", r.stdout)
        scripts = glob.glob(os.path.join(d, ".reef", "graph", "run-*.js"))
        self.assertEqual(len(scripts), 1)
        js = open(scripts[0]).read()
        self.assertTrue(js.startswith("export const meta = {"))
        self.assertTrue(("REEF-TASK: " + os.path.join(d, "tasks", "101-a.md")) in js or ("REEF-TASK: " + os.path.join(os.path.realpath(d), "tasks", "101-a.md")) in js,
                        "the task's REEF-TASK: line (macOS: /var/folders resolves to /private/var/folders)")
        self.assertIn("agentType: 'reef:implementer'", js)
        self.assertIn("agentType: 'reef:mechanic'", js)
        self.assertIn("sh scripts/reef-gate.sh full --failures", js, "the judges read a tree the FULL gate passed, as in chat mode (cached when the implementer ran it on the same snapshot)")
        self.assertNotIn("reef-gate.sh fast", js)
        self.assertIn("pipeline(TASKS", js)
        self.assertIn('"judge": false', js, "a gate-only task has no judge stage")
        self.assertNotIn("Date.now", js)
        # what the guard does on a chat dispatch happened here
        task = open(os.path.join(d, "tasks", "101-a.md")).read()
        self.assertIn("status: in-progress", task)
        self.assertIn("dispatches: 1", task)
        self.assertTrue(os.path.isfile(os.path.join(d, ".reef", "inflight", "101")))
        tick = subprocess.run([sys.executable, os.path.join(d, "scripts", "reef-loop.py"), "tick", "--repo", d], capture_output=True, text=True).stdout
        self.assertIn("in flight: 101", tick)
        self.assertIn("dispatch now: -", tick)
        # nothing left to dispatch now
        r = g(d, "generate")
        self.assertEqual(r.returncode, 1)
        self.assertIn("nothing to dispatch", r.stdout)


    def judged(self, d, log="", attempts=0):
        t = (T.task(101, "1").replace("complexity: mech", "complexity: design").replace("tier: light", "tier: full")
             .replace("verify: gate-only", "verify: judge").replace("## Scope\nx", "## Scope\nx\n\n## Decision\nhuman words")
             .replace("attempts: 0", f"attempts: {attempts}"))
        T.write(d, "tasks/101-a.md", t.rstrip("\n") + ("\n" + log + "\n" if log else "\n"))
        T.approve(d, "1")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-record"), "plan-review", "1", "PASS", "--root", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)   # a task above light dispatches only on a plan-review PASS at its digest

    def script_of(self, d):
        js = open(sorted(glob.glob(os.path.join(d, ".reef", "graph", "run-*.js")), key=os.path.getmtime)[-1]).read()
        return json.loads(js[js.index("const TASKS = ") + len("const TASKS = "):js.index("\nconst SNAP")])[0]

    def test_a_fix_round_runs_in_the_graph_with_its_failure_and_its_rejudge_line(self):
        # 2026-10-20: a task that failed once cost the orchestrator 170-260k in chat; round 2 now runs as a workflow
        d = graph_project()
        pass_gate(d)
        self.judged(d, "- attempt 1 FAIL: AC-1 test_t101 missing · at 2026-10-20T10:00:00Z", attempts=1)
        r = g(d, "generate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        t = self.script_of(d)
        self.assertIn("Round 2: the last round failed — - attempt 1 FAIL: AC-1 test_t101 missing", t["implement_prompt"])
        self.assertIn(".reef/ci-local/gate-full.log", t["implement_prompt"])
        self.assertIn("keep the rest", t["implement_prompt"])
        self.assertIn("rejudge: AC-1", t["verifier_prompt"])
        self.assertIn("round=2", t["verifier_prompt"])
        self.assertIn("dispatches: 1", open(os.path.join(d, "tasks", "101-a.md")).read(), "an implementer dispatch is counted")

    def test_a_rejected_report_or_a_hand_back_is_re_judged_in_full_without_an_implementer(self):
        d = graph_project()
        pass_gate(d)
        self.judged(d, "- attempt 1 FAIL: verifier report rejected: no `RULE AC1:` line for criterion 1 · at 2026-10-20T10:00:00Z", attempts=1)
        r = g(d, "generate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        t = self.script_of(d)
        self.assertIsNone(t["implement_prompt"], "the code was not judged wrong: no implementer")
        self.assertNotIn("rejudge:", t["verifier_prompt"], "no valid round-1 report to carry: a full judge")
        self.assertIn("dispatches: 0", open(os.path.join(d, "tasks", "101-a.md")).read(), "a judge-only run is not an implementer dispatch")
        js = open(sorted(glob.glob(os.path.join(d, ".reef", "graph", "run-*.js")), key=os.path.getmtime)[-1]).read()
        self.assertIn("t.implement_prompt\n        ? agent(", js, "the workflow skips the implementer stage when it has no prompt")
        # a hand-back waiting for its judge (verify now) runs the same way
        d = graph_project()
        pass_gate(d)
        self.judged(d)
        T.write(d, ".reef/ci-local/handback-101.md", "RUN: agent=implementer task=101\n")
        r = g(d, "generate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIsNone(self.script_of(d)["implement_prompt"])

    def test_generate_refuses_under_mode_chat(self):
        d = graph_project()
        pass_gate(d)
        cfg = json.load(open(os.path.join(d, ".reef", "config.json")))
        cfg["graph"] = {"mode": "chat"}
        T.write(d, ".reef/config.json", json.dumps(cfg))
        r = g(d, "generate")
        self.assertEqual(r.returncode, 1)
        self.assertIn("graph.mode is `chat`", r.stderr)


class Settle(unittest.TestCase):
    def results(self, d, **gate):
        wt = os.path.join(d, ".reef", "worktrees", "101")
        os.makedirs(os.path.join(wt, ".reef", "ci-local"), exist_ok=True)
        gt = {"gate_exit": 0, "handback_check": "ok: hand-back 3 lines", "snapshot": "abc"}
        gt.update(gate)
        res = {"tasks": [{"task": "101", "task_file": os.path.join(d, "tasks", "101-a.md"), "worktree": wt, "judge": False, "hunter": False,
                          "gate": gt, "judges": [], "snapshot_after": "abc"}], "skipped": 0}
        p = os.path.join(d, ".reef", "graph", "results.json")
        with open(p, "w") as f:
            json.dump(res, f)
        return p

    def test_ready_clears_the_marker_and_a_failed_gate_counts_an_attempt(self):
        d = graph_project()
        pass_gate(d)
        g(d, "generate")
        r = g(d, "settle", self.results(d))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("READY TO MERGE 101", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(d, ".reef", "inflight", "101")), "handed back: no longer in flight")
        r = g(d, "settle", self.results(d, gate_exit=1, notes="FAIL tests/x"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL 101: gate exit 1: FAIL tests/x", r.stdout)
        self.assertIn("attempts: 1", open(os.path.join(d, "tasks", "101-a.md")).read(), "the failure is counted the way a chat round is")
        r = g(d, "settle", self.results(d, handback_check="REJECTED hand-back (chat mode: re-dispatch once, no attempt consumed; graph mode: "
                                                          "settle counts one attempt):\n  - no claims list ('<sentence> — true at <path>:<line>' lines)"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("hand-back rejected: no claims list", r.stdout, "the reason, not the header (2026-10-20, 301)")
        self.assertIn("FAIL: hand-back rejected: no claims list", open(os.path.join(d, "tasks", "101-a.md")).read(), "the next round reads it")

    def test_the_notices_output_file_is_settled_as_it_is_and_a_killed_run_is_refused(self):
        # 2026-10-21: a hand-typed results file was blocked by auto mode; the completion notice names a file holding
        # {"result": <the return value>, …}; the night's killed run left `result: null`
        d = graph_project()
        pass_gate(d)
        g(d, "generate")
        res = json.load(open(self.results(d)))
        out = os.path.join(d, "wf.output")
        json.dump({"summary": "reef graph", "agentCount": 4, "result": res, "workflowProgress": []}, open(out, "w"))
        r = g(d, "settle", out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("READY TO MERGE 101", r.stdout)
        json.dump({"summary": "reef graph", "result": None}, open(out, "w"))
        r = g(d, "settle", out)
        self.assertEqual(r.returncode, 1)
        self.assertIn("ended without a result", r.stderr)

    def test_settle_prints_the_hunters_new_rows_and_notes_so_none_is_dropped(self):
        # 2026-10-21: graph mode copied the hunter's report and nothing said what it found
        d = graph_project()
        pass_gate(d)
        g(d, "generate")
        rp = os.path.join(d, "report-101-hunter.md")
        with open(rp, "w") as f:
            f.write("RUN: agent=loophole-hunter task=101 pass=guard\nDEFECT: x\nBLOCKER: none\n"
                    "**NEW-ROW:** a flood of wrong tokens locks the bill row — will happen, not this item's: bills.ts:80 — queue it\n"
                    "NOTED: two joins in one ms list in either order — possible: same-ms commits — worst case: cosmetic\nVERDICT: PASS\n")
        p = self.results(d)
        res = json.load(open(p))
        res["tasks"][0]["judges"] = [{"role": "hunter", "verdict": "PASS", "report_path": rp, "summary": "PASS"}]
        json.dump(res, open(p, "w"))
        r = g(d, "settle", p)
        self.assertIn("  NEW-ROW (hunter 101, row 1): a flood of wrong tokens locks the bill row", r.stdout)
        self.assertIn("  NOTED (hunter 101, row 1): two joins in one ms list in either order", r.stdout)
        self.assertIn("file each on branches.base", r.stdout)

    def test_a_rejected_report_records_the_reasons_not_the_note_before_them(self):
        """2026-10-19, qassimha 1302 (row 69): reef-claims printed `note: report 661 words` before its REJECTED reasons, settle
        kept the first line, and the fix round's Log said nothing about what to fix."""
        d = graph_project()
        pass_gate(d)
        g(d, "generate")
        rp = os.path.join(d, "report-101-verifier.md")
        with open(rp, "w") as f:
            f.write("RUN: agent=verifier task=101\nVERDICT: PASS\n")
        p = self.results(d)
        res = json.load(open(p))
        res["tasks"][0]["judge"] = True
        res["tasks"][0]["judges"] = [{"role": "verifier", "verdict": "PASS", "report_path": rp, "summary": "PASS"}]
        json.dump(res, open(p, "w"))
        r = g(d, "settle", p)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("verifier report rejected: no `RULE AC1:` line for criterion 1", r.stdout)
        self.assertNotIn("note: report", r.stdout)
        self.assertIn("- attempt 1 FAIL: verifier report rejected: no `RULE AC1:` line", open(os.path.join(d, "tasks", "101-a.md")).read(),
                      "the fix round reads the reasons")

    def test_a_red_gate_on_a_judged_task_counts_the_attempt_and_names_the_gate_not_a_missing_verdict(self):
        """2026-10-18, qassimha 1103: the pipeline skips the judges on a red gate, settle added "no verifier verdict",
        and that text suppressed reef-attempt — the task kept attempts: 0 and the next dispatch never saw the failure."""
        d = graph_project()
        pass_gate(d)
        g(d, "generate")
        p = self.results(d, gate_exit=1, notes="FAIL src/lib/decode.test.ts: Hook timed out in 10000ms (beforeAll at decode.test.ts:30)")
        res = json.load(open(p))
        res["tasks"][0]["judge"] = True      # a judged task whose judges never ran
        json.dump(res, open(p, "w"))
        r = g(d, "settle", p)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("FAIL 101: gate exit 1: FAIL src/lib/decode.test.ts", r.stdout)
        self.assertNotIn("no verifier verdict", r.stdout, "the judges were skipped by design; the gate is the failure")
        self.assertIn("attempt counted: attempt=2/3", r.stdout)
        task = open(os.path.join(d, "tasks", "101-a.md")).read()
        self.assertIn("attempts: 1", task)
        self.assertIn("- attempt 1 FAIL: gate exit 1: FAIL src/lib/decode.test.ts", task, "the failure's words reach the next dispatch")
        # a green gate with no verdict is still a pipeline defect, not an attempt
        p = self.results(d)
        res = json.load(open(p)); res["tasks"][0]["judge"] = True; json.dump(res, open(p, "w"))
        r = g(d, "settle", p)
        self.assertIn("no verifier verdict", r.stdout)
        self.assertIn("attempts: 1", open(os.path.join(d, "tasks", "101-a.md")).read(), "not counted twice")


class PlanHome(unittest.TestCase):
    """2026-10-24 (qassimha 502): a re-dispatch marked the task worktree's copy of 502 in-progress; the feature worktree's
    copy, which the tick reads, stayed pending, so the tick offered 502 again and the two copies stood in the way of the
    merge. The dispatch status goes to the plan's home: the feature worktree's copy."""

    def test_a_task_worktree_path_resolves_to_the_feature_copy_and_is_marked_there(self):
        import importlib.machinery
        import importlib.util
        d = tempfile.mkdtemp(prefix="reef-home.")
        g = ["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(["git", "init", "-q", "-b", "develop", d], check=True)
        os.makedirs(os.path.join(d, ".reef"))
        with open(os.path.join(d, ".reef", "config.json"), "w") as f:
            json.dump({"worktree": {"dir": ".reef/worktrees"}}, f)
        rel = os.path.join("reef", "features", "demo", "tasks", "101-a.md")
        os.makedirs(os.path.dirname(os.path.join(d, rel)))
        with open(os.path.join(d, rel), "w") as f:
            f.write("---\nid: 101\nfeature: demo\nstatus: pending\ndispatches: 0\ntier: full\n---\n# 101\n")
        subprocess.run(g + ["add", "-A"], check=True, capture_output=True)
        subprocess.run(g + ["commit", "-qm", "plan"], check=True, capture_output=True)
        feat, task = os.path.join(d, ".reef", "worktrees", "demo"), os.path.join(d, ".reef", "worktrees", "101")
        subprocess.run(g + ["worktree", "add", "-q", "-b", "feat/demo", feat], check=True, capture_output=True)
        subprocess.run(["git", "-C", feat, "worktree", "add", "-q", "-b", "task/101", task], check=True, capture_output=True)
        loader = importlib.machinery.SourceFileLoader("reef_graph_run_t", os.path.join(ROOT, "scripts", "reef-graph-run.py"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        self.assertEqual(os.path.realpath(mod.plan_home(os.path.join(task, rel))), os.path.realpath(os.path.join(feat, rel)))
        self.assertEqual(mod.plan_home(os.path.join(feat, rel)), os.path.join(feat, rel), "the home copy is its own home")
        self.assertEqual(mod.plan_home(os.path.join(d, rel)), os.path.join(d, rel), "the main checkout's copy is left alone")
        mod.mark_dispatched(d, os.path.join(task, rel), "101")
        self.assertIn("status: in-progress", open(os.path.join(feat, rel)).read(), "the feature copy, which the tick reads")
        self.assertIn("status: pending", open(os.path.join(task, rel)).read(), "the task worktree's copy is never edited")
        self.assertIn("dispatches: 1", open(os.path.join(feat, rel)).read())


if __name__ == "__main__":
    unittest.main()
