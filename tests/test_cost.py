"""Sabotage suite for scripts/reef-cost.py: a fixture transcript with KNOWN counts yields exactly those
counts; a compaction counts once (a boundary record plus its summary record are one compaction);
--live on a 50 MB transcript reads only the tail; --session-start reports the first turn."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COST = os.path.join(ROOT, "scripts", "reef-cost.py")


def assistant(rid, ctx_in, cache_w, cache_r, out, blocks=None, agent=None):
    """One content block of an API turn; every block of a turn repeats the same usage."""
    d = {"type": "assistant", "requestId": rid, "uuid": rid + "-u",
         "message": {"model": "claude-x", "role": "assistant", "content": blocks or [{"type": "text", "text": "hi"}],
                     "usage": {"input_tokens": ctx_in, "cache_creation_input_tokens": cache_w,
                               "cache_read_input_tokens": cache_r, "output_tokens": out}}}
    if agent:
        d["attributionAgent"] = agent
        d["isSidechain"] = True
    return d


def tool_result(tid, text):
    return {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": text}]}}


FIXTURE = [
    {"type": "user", "message": {"role": "user", "content": "do the thing"}},
    # turn 1: 3 blocks, ONE request -> one turn of context 100+900+0 = 1000
    assistant("req1", 100, 900, 0, 50, [{"type": "thinking", "thinking": "t" * 40}]),
    assistant("req1", 100, 900, 0, 50, [{"type": "text", "text": "x" * 80}]),
    assistant("req1", 100, 900, 0, 50, [{"type": "tool_use", "id": "tu1", "name": "Bash", "input": {"command": "ls"}}]),
    tool_result("tu1", "o" * 400),
    # turn 2: context 2 + 50 + 1948 = 2000
    assistant("req2", 2, 50, 1948, 10, [{"type": "tool_use", "id": "tu2", "name": "Read", "input": {"file_path": "a"}}]),
    tool_result("tu2", "r" * 1200),
    # a compaction: boundary AND summary records for the SAME event -> counts once
    {"type": "system", "subtype": "compact_boundary", "compact_metadata": {"trigger": "auto", "pre_tokens": 3000, "post_tokens": 500}},
    {"type": "user", "isCompactSummary": True, "message": {"role": "user", "content": "summary " * 20}},
    # turn 3: context 3000
    assistant("req3", 3000, 0, 0, 20),
    {"type": "attachment", "attachment": {"type": "file", "content": "a" * 200}},
    # turn 4: context 4000
    assistant("req4", 0, 0, 4000, 5),
]


def write_transcript(d, name, records):
    p = os.path.join(d, name)
    with open(p, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return p


def cost(*args, stdin=None):
    return subprocess.run([sys.executable, COST, *args], capture_output=True, text=True, input=stdin)


class KnownCounts(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-cost.")
        self.t = write_transcript(self.d, "sess.jsonl", FIXTURE)
        sub = os.path.join(self.d, "sess", "subagents")
        os.makedirs(sub)
        write_transcript(sub, "agent-abc.jsonl", [
            assistant("s1", 500, 0, 0, 7, agent="verifier"), assistant("s2", 0, 0, 800, 9, agent="verifier")])

    def test_exact_counts(self):
        r = cost(self.t, "--format", "json")
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = json.loads(r.stdout)
        s = rep["session"]
        self.assertEqual(s["turns"], 4, "four requestIds = four API turns, however many blocks each")
        self.assertEqual(s["context"], {"mean": 2500, "p50": 2000, "p90": 4000, "max": 4000})
        self.assertEqual(s["first_turn_context"], 1000)
        self.assertEqual(s["compactions"], 1, "boundary + summary of ONE compaction counts once")
        self.assertEqual(s["cache"], {"writes": 950, "reads": 5948, "uncached_input": 3102, "output": 85})
        cats = s["categories"]
        self.assertEqual(cats["tool_result:Bash"], 100)       # 400 chars / 4
        self.assertEqual(cats["tool_result:Read"], 300)
        self.assertIn("compact-summary", cats)
        self.assertIn("attachment:file", cats, "attachments are split by type")
        self.assertNotIn("attachment", cats, "no undifferentiated bucket")
        self.assertEqual(len(rep["subagents"]), 1)
        sub = rep["subagents"][0]
        self.assertEqual((sub["agent_type"], sub["turns"], sub["first_turn_context"], sub["context"]["max"]), ("verifier", 2, 500, 800))

    def test_summary_only_compaction_counts_once_too(self):
        recs = [r for r in FIXTURE if r.get("subtype") != "compact_boundary"]
        t = write_transcript(self.d, "s2.jsonl", recs)
        self.assertEqual(json.loads(cost(t, "--format", "json").stdout)["session"]["compactions"], 1)

    def test_session_start_and_live(self):
        self.assertEqual(cost(self.t, "--session-start").stdout.strip(), "session_start_tokens=1000")
        self.assertEqual(cost(self.t, "--live").stdout.strip(), "context_tokens=4000")
        payload = json.dumps({"transcript_path": self.t, "hook_event_name": "PreToolUse"})
        self.assertEqual(cost("--live", stdin=payload).stdout.strip(), "context_tokens=4000", "the hook payload names the transcript")

    def test_md_report_and_missing_file(self):
        r = cost(self.t, "--format", "md")
        self.assertIn("API turns: **4**", r.stdout)
        self.assertIn("| tool_result:Read |", r.stdout)
        self.assertEqual(cost(os.path.join(self.d, "nope.jsonl")).returncode, 2)

    def test_fix_rounds_from_done_tasks(self):
        os.makedirs(os.path.join(self.d, "tasks", "done"))
        with open(os.path.join(self.d, "tasks", "done", "101-a.md"), "w") as f:
            f.write("---\nid: 101\nfeature: csv-export\nattempts: 2\n---\n")
        with open(os.path.join(self.d, "tasks", "done", "102-b.md"), "w") as f:
            f.write("---\nid: 102\nfeature: csv-export\nattempts: 1\n---\n")
        rep = json.loads(cost(self.t, "--repo", self.d, "--format", "json").stdout)
        self.assertEqual(rep["fix_rounds"]["by_feature"], {"csv-export": 3})


class LiveReadsOnlyTheTail(unittest.TestCase):
    def test_50mb_transcript_tail_only(self):
        d = tempfile.mkdtemp(prefix="reef-cost-big.")
        p = os.path.join(d, "big.jsonl")
        # the HEAD holds thousands of turns with an absurd context; only the tail's turn is current
        head = json.dumps(assistant("old", 999999999, 0, 0, 1)) + "\n"
        with open(p, "w") as f:
            n = (50 * 1024 * 1024) // len(head) + 1
            for _ in range(n):
                f.write(head)
            f.write(json.dumps(assistant("new", 1234, 0, 0, 1)) + "\n")
        self.assertGreater(os.path.getsize(p), 50 * 1024 * 1024)
        t0 = time.monotonic()
        r = cost(p, "--live")
        dt = time.monotonic() - t0
        self.assertEqual(r.stdout.strip(), "context_tokens=1234", r.stderr)
        self.assertLess(dt, 3.0, f"--live took {dt:.1f}s on 50 MB — it parsed the whole file instead of the tail")



NOTIFICATION = os.path.join(ROOT, "tests", "fixtures", "payloads", "user-task-notification.json")


def dispatch(tid, name, prompt):
    """A tool_use block of the main session: Task or Agent, the prompt carrying the REEF line."""
    return {"type": "tool_use", "id": tid, "name": name, "input": {"description": "d", "prompt": prompt}}


def notification(tid):
    """The captured Stage 3 task-notification record, re-pointed at tool-use id `tid`."""
    with open(NOTIFICATION, encoding="utf-8") as f:
        rec = json.load(f)
    rec["message"]["content"] = rec["message"]["content"].replace("toolu_01WS5bfbwaJf93WEdgPdLtoc", tid)
    return rec


def attachment_notification(tid):
    """The OTHER shape a background agent's notification takes: an `attachment` record of type `queued_command`
    whose `prompt` is the <task-notification> text (the only form the hunter's dispatch had in the Reef row session)."""
    return {"type": "attachment", "attachment": {"type": "queued_command", "prompt":
            f"<task-notification>\n<task-id>a1</task-id>\n<tool-use-id>{tid}</tool-use-id>\n<status>completed</status>\n</task-notification>"}}


def list_result(tid, text):
    """An Agent result as real transcripts carry it: content is a list of text blocks."""
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": [{"type": "text", "text": text}]}]}}


def rows_of(path):
    r = cost(path, "--format", "json")
    assert r.returncode == 0, r.stderr
    return {row["feature"]: row for row in json.loads(r.stdout)["rows"]}


TWO_FEATURES = [
    {"type": "user", "message": {"role": "user", "content": "/reef-task"}},
    assistant("m1", 1000, 0, 0, 1),                                                            # turn 1
    assistant("m2", 0, 0, 2000, 1, [dispatch("tu_a1", "Task", "REEF-TASK: reef/features/alpha/tasks/101-a.md\ngo")]),
    tool_result("tu_a1", "alpha 101 done"),
    assistant("m3", 0, 0, 2500, 1),                                                            # turn 3
    assistant("m4", 0, 0, 3000, 1, [dispatch("tu_b", "Agent", "Effort: high.\nREEF-FEATURE: beta\n")]),
    assistant("m4", 0, 0, 3000, 1, [dispatch("tu_a2", "Task",
                                             "REEF-FEATURE: beta\nREEF-TASK: reef/features/alpha/tasks/102-b.md")]),
    list_result("tu_b", "beta planned"),
    list_result("tu_a2", "alpha 102 done"),
    # a sidechain record carrying a dispatch is never attributed
    assistant("side1", 0, 0, 9000, 1, [dispatch("tu_s", "Agent", "REEF-FEATURE: gamma")], agent="implementer"),
    assistant("m5", 0, 0, 3600, 1),                                                            # turn 5
    # a claude -p subprocess through Bash is not a Reef dispatch
    assistant("m6", 0, 0, 4000, 1, [{"type": "tool_use", "id": "tu_bash", "name": "Bash",
                                     "input": {"command": "claude -p 'REEF-TASK: reef/features/delta/tasks/1-d.md'"}}]),
    tool_result("tu_bash", "ok"),
]


class Rows(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-cost-rows.")

    def test_rows_growth_two_features(self):
        rows = rows_of(write_transcript(self.d, "two.jsonl", TWO_FEATURES))
        self.assertEqual(sorted(rows), ["alpha", "beta"], "sidechain and Bash dispatches are never attributed")
        a, b = rows["alpha"], rows["beta"]
        # alpha: turn 2 (Task) to turn 5 (after tu_a2's list-shaped result); 500 + 500 + 600 of growth
        self.assertEqual((a["first_turn"], a["last_turn"], a["growth"], a["turns"], a["dispatches"]), (2, 5, 1600, 4, 2))
        # beta: turn 4 (Agent) to turn 5; the turn both features dispatch in counts for both
        self.assertEqual((b["first_turn"], b["last_turn"], b["growth"], b["turns"], b["dispatches"]), (4, 5, 600, 2, 1))
        self.assertEqual((a["compactions"], b["compactions"]), (0, 0))

    def test_share_splits_concurrent_features_and_planning_is_before_the_first_task_dispatch(self):
        # workflow v2 phase 2 (2026-10-17): three rows planned at once — span growth charged turn 4 to both alpha and
        # beta; the share splits it, and the planning part is what the gate order is meant to shrink
        rows = rows_of(write_transcript(self.d, "two.jsonl", TWO_FEATURES))
        a, b = rows["alpha"], rows["beta"]
        # growth per turn: t1→2 1000, t2→3 500, t3→4 500, t4→5 600. alpha active t2..t4, beta active t4
        self.assertEqual((a["share"], b["share"]), (500 + 500 + 300, 300))
        self.assertEqual(a["planning_share"], 0, "alpha's first dispatch is a REEF-TASK: build from turn 2")
        self.assertEqual(b["planning_share"], 300, "beta has only a REEF-FEATURE agent: all planning")
        self.assertEqual(b["roles"], {"?": 1})
        md = cost(write_transcript(self.d, "two2.jsonl", TWO_FEATURES), "--format", "md").stdout
        self.assertIn("| alpha | 2–5 | 1,600 | 1,300 | 0 | 0 |", md)

    def test_record_keeps_feature_shares_and_growth_feature_sums_them(self):
        d = tempfile.mkdtemp(prefix="reef-cost-feat.")
        s1 = write_transcript(d, "s1.jsonl", TWO_FEATURES)
        s2 = write_transcript(d, "s2.jsonl", TWO_FEATURES)
        self.assertEqual(cost(s1, "--record", "--repo", d).returncode, 0)
        self.assertEqual(cost(s2, "--record", "--repo", d).returncode, 0)
        r = cost("growth", "--feature", "beta", "--repo", d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), "share=600 planning=600 sessions=2 roles=?×2")
        self.assertEqual(cost("growth", "--feature", "nope", "--repo", d).returncode, 1)

    def test_a_workflow_call_is_attributed_to_the_tasks_its_script_names(self):
        # graph mode (v2 phase 3): one Workflow tool call runs the tasks; its script carries their REEF-TASK: lines
        d = tempfile.mkdtemp(prefix="reef-cost-wf.")
        js = 'const TASKS = [{"implement_prompt": "REEF-TASK: reef/features/demo/tasks/101-page.md\\nEffort: medium"}, {"implement_prompt": "REEF-TASK: reef/features/other/tasks/201-x.md\\n"}]\n'
        sp = os.path.join(d, "run-abc.js")
        with open(sp, "w") as f:
            f.write(js)
        recs = [assistant("w1", 1000, 0, 0, 5, [{"type": "tool_use", "id": "tu_w", "name": "Workflow", "input": {"scriptPath": sp}}]),
                list_result("tu_w", '{"tasks": []}'), assistant("w2", 6000, 0, 0, 5)]
        j = json.loads(cost(write_transcript(d, "s.jsonl", recs), "--format", "json").stdout)
        self.assertEqual({x["task"]: x["roles"] for x in j["tasks"]}, {"101": {"workflow": 1}, "201": {"workflow": 1}})
        self.assertEqual(sorted(r["feature"] for r in j["rows"]), ["demo", "other"])
        self.assertEqual(j["rows"][0]["roles"], {"workflow": 1})

    def test_tasks_table_growth_per_task_and_dispatches_per_role(self):
        # 0.7: the first real execution could not say which role cost what; the main-session span per task and the
        # roles dispatched for it (implementer, verifier, loophole-hunter, mechanic) come from the REEF-TASK: lines
        d = tempfile.mkdtemp(prefix="reef-cost-tasks.")
        prompt101 = "REEF-TASK: reef/features/demo/tasks/101-page.md\nimplement"
        recs = [
            assistant("r1", 1000, 0, 0, 5, [dispatch("tu_i", "Task", prompt101)]),
            {"type": "assistant", "requestId": "r1", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "tu_i2", "name": "Task",
             "input": {"prompt": prompt101, "subagent_type": "reef:implementer"}}]}},
            list_result("tu_i", "done"), list_result("tu_i2", "done"),
            assistant("r2", 3000, 0, 0, 5, [{"type": "tool_use", "id": "tu_v", "name": "Task", "input": {"prompt": prompt101, "subagent_type": "reef:verifier"}}]),
            list_result("tu_v", "PASS"),
            assistant("r3", 5000, 0, 0, 5, [{"type": "tool_use", "id": "tu_h", "name": "Task", "input": {"prompt": prompt101, "subagent_type": "reef:loophole-hunter"}}]),
            list_result("tu_h", "PASS"),
            assistant("r4", 5500, 0, 0, 5, [{"type": "tool_use", "id": "tu_x", "name": "Task", "input": {"prompt": "REEF-TASK: reef/features/demo/tasks/102-upload.md\nimplement", "subagent_type": "reef:implementer"}}]),
            list_result("tu_x", "done"),
            assistant("r5", 9000, 0, 0, 5),
        ]
        path = write_transcript(d, "s.jsonl", recs)
        j = json.loads(cost(path, "--format", "json").stdout)
        by = {x["task"]: x for x in j["tasks"]}
        self.assertEqual(set(by), {"101", "102"})
        self.assertEqual(by["101"]["roles"], {"?": 1, "implementer": 1, "loophole-hunter": 1, "verifier": 1})
        self.assertEqual((by["101"]["first_turn"], by["101"]["last_turn"]), (1, 4))
        self.assertEqual(by["101"]["growth"], 4500)          # 1000 -> 3000 -> 5000 -> 5500
        self.assertEqual(by["102"]["roles"], {"implementer": 1})
        self.assertEqual(by["102"]["growth"], 3500)          # 5500 -> 9000
        md = cost(path, "--format", "md").stdout
        self.assertIn("## Tasks (main-session growth per task, dispatches per role)", md)
        self.assertIn("| 101 | 4 | 4,500 | ? ×1, implementer ×1, loophole-hunter ×1, verifier ×1 |", md)

    def test_record_folds_growth_per_task_across_sessions_and_growth_reads_it(self):
        # first full loop (2026-10-17): a task's orchestrator cost was computed by hand from the transcript, after the fact
        d = tempfile.mkdtemp(prefix="reef-cost-rec.")
        prompt = "REEF-TASK: reef/features/demo/tasks/101-page.md\nimplement"
        s1 = write_transcript(d, "s1.jsonl", [
            assistant("r1", 1000, 0, 0, 5, [{"type": "tool_use", "id": "tu_i", "name": "Task", "input": {"prompt": prompt, "subagent_type": "reef:implementer"}}]),
            list_result("tu_i", "done"), assistant("r2", 4000, 0, 0, 5)])
        s2 = write_transcript(d, "s2.jsonl", [
            assistant("q1", 2000, 0, 0, 5, [{"type": "tool_use", "id": "tu_v", "name": "Task", "input": {"prompt": prompt, "subagent_type": "reef:verifier"}}]),
            list_result("tu_v", "PASS"), assistant("q2", 3500, 0, 0, 5)])
        self.assertEqual(cost(s1, "--record", "--repo", d).returncode, 0)
        self.assertEqual(cost(s1, "--record", "--repo", d).returncode, 0, "re-recording a session replaces, never doubles")
        self.assertEqual(cost(s2, "--record", "--repo", d).returncode, 0)
        with open(os.path.join(d, ".reef", "cost", "tasks.json")) as f:
            store = json.load(f)
        self.assertEqual(set(store["101"]), {"s1", "s2"})
        r = cost("growth", "101", "--repo", d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), "growth=4500 sessions=2 roles=implementer×1,verifier×1")
        self.assertEqual(cost("growth", "999", "--repo", d).returncode, 1)

    def test_rows_absent_without_dispatch(self):
        bash_only = FIXTURE + [TWO_FEATURES[-2], TWO_FEATURES[-1]]
        for recs in (FIXTURE, bash_only):
            t = write_transcript(self.d, "none.jsonl", recs)
            j = json.loads(cost(t, "--format", "json").stdout)
            self.assertEqual(j["rows"], [])
            self.assertNotIn("rows", j["session"])
            self.assertNotIn("## Rows", cost(t, "--format", "md").stdout)
            self.assertNotIn("row feature=", cost(t).stdout)
        t = write_transcript(self.d, "none.jsonl", FIXTURE)
        self.assertEqual(cost(t).stdout, "turns=4 compactions=1 ctx_mean=2500 ctx_p50=2000 ctx_p90=4000 ctx_max=4000 "
                                         "first_turn=1000 cache_writes=950 cache_reads=5948 subagents=0\n")
        s = json.loads(cost(t, "--format", "json").stdout)["session"]
        self.assertEqual((s["turns"], s["compactions"], s["context"]["max"], s["cache"]["reads"]), (4, 1, 4000, 5948))

    def test_rows_json(self):
        t = write_transcript(self.d, "two.jsonl", TWO_FEATURES)
        j = json.loads(cost(t, "--format", "json").stdout)
        self.assertIsInstance(j["rows"], list)
        self.assertEqual([r["feature"] for r in j["rows"]], ["alpha", "beta"], "one object per feature, by first turn")
        self.assertEqual(set(j["rows"][0]), {"feature", "first_turn", "last_turn", "growth", "compactions", "turns", "dispatches", "share", "planning_share", "roles"})
        md = cost(t, "--format", "md").stdout
        self.assertIn("| feature | turns | span growth | share | planning | compactions | dispatches |", md)
        self.assertIn("| alpha | 2–5 | 1,600 | 1,300 | 0 | 0 | ? ×2 |", md)
        self.assertIn("| beta | 4–5 | 600 | 300 | 300 | 0 | ? ×1 |", md)
        txt = cost(t).stdout
        self.assertIn("row feature=alpha first_turn=2 last_turn=5 growth=1600 compactions=0 turns=4 dispatches=2", txt)

    def test_rows_growth_survives_compaction(self):
        recs = [
            assistant("c1", 1000, 0, 0, 1),
            assistant("c2", 0, 0, 2000, 1, [dispatch("tu_c", "Agent", "REEF-TASK: reef/features/gamma/tasks/101-g.md")]),
            list_result("tu_c", "Async agent launched successfully. agentId: x"),     # the launch stub, not the result
            assistant("c3", 0, 0, 5000, 1),
            {"type": "system", "subtype": "compact_boundary", "compact_metadata": {"trigger": "auto"}},
            dict(notification("tu_c"), isCompactSummary=True),                        # a summary is never a result
            assistant("c4", 800, 0, 0, 1),
            assistant("c5", 0, 0, 1500, 1),
            notification("tu_c"),
            assistant("c6", 0, 0, 1700, 1),
            assistant("c7", 0, 0, 1800, 1),
        ]
        g = rows_of(write_transcript(self.d, "compact.jsonl", recs))["gamma"]
        self.assertEqual((g["first_turn"], g["last_turn"], g["turns"], g["compactions"]), (2, 6, 5, 1))
        self.assertEqual(g["growth"], 3000 + 700 + 200)
        self.assertNotEqual(g["growth"], 1700 - 2000, "growth is not last-minus-first")

    def test_rows_span_ends_at_background_result(self):
        recs = [
            assistant("b1", 1000, 0, 0, 1),
            assistant("b2", 0, 0, 2000, 1, [dispatch("tu_x", "Agent", "REEF-TASK: reef/features/xa/tasks/101-x.md"),
                                            dispatch("tu_y", "Agent", "REEF-TASK: reef/features/ya/tasks/101-y.md")]),
            list_result("tu_x", "Async agent launched"),
            list_result("tu_y", "Async agent launched"),
            assistant("b3", 0, 0, 2200, 1),
            notification("tu_y"),                                                     # y finishes first
            assistant("b4", 0, 0, 2600, 1, [{"type": "tool_use", "id": "tu_q", "name": "Bash", "input": {"command": "cat log"}}]),
            tool_result("tu_q", "<task-notification>\n<tool-use-id>tu_x</tool-use-id>\n</task-notification>"),  # a quote
            assistant("b5", 0, 0, 2700, 1),
            notification("tu_x"),
            assistant("b6", 0, 0, 3000, 1),
            assistant("b7", 0, 0, 3100, 1),
        ]
        rows = rows_of(write_transcript(self.d, "bg.jsonl", recs))
        self.assertEqual((rows["ya"]["first_turn"], rows["ya"]["last_turn"], rows["ya"]["growth"]), (2, 4, 600))
        self.assertEqual((rows["xa"]["first_turn"], rows["xa"]["last_turn"], rows["xa"]["growth"]), (2, 6, 1000))

    def test_rows_span_ends_at_an_attachment_notification(self):
        # found by the acceptance review of this feature on the Reef row session: with the user-record shape only,
        # the hunter's span ended at the launch stub and growth read 34,098 for a true 40,840
        recs = [
            assistant("c1", 1000, 0, 0, 1),
            assistant("c2", 0, 0, 2000, 1, [dispatch("tu_h", "Agent", "REEF-TASK: reef/features/za/tasks/101-z.md")]),
            list_result("tu_h", "Async agent launched"),
            assistant("c3", 0, 0, 2500, 1),
            attachment_notification("tu_h"),
            assistant("c4", 0, 0, 3200, 1),
            assistant("c5", 0, 0, 3300, 1),
        ]
        rows = rows_of(write_transcript(self.d, "att.jsonl", recs))
        self.assertEqual((rows["za"]["first_turn"], rows["za"]["last_turn"], rows["za"]["growth"]), (2, 4, 1200))

    def test_rows_flat_layout_slug_is_the_stem(self):
        recs = [
            assistant("f1", 1000, 0, 0, 1, [dispatch("tu_f", "Task", "REEF-TASK: tasks/105-flat-thing.md")]),
            tool_result("tu_f", "done"),
            assistant("f2", 0, 0, 1500, 1),
            assistant("f3", 0, 0, 1700, 1, [dispatch("tu_g", "Agent", "REEF-TASK: /home/u/repo/tasks/106-other.md")]),
            assistant("f4", 0, 0, 1800, 1),                                           # tu_g never returns
            assistant("f5", 0, 0, 2000, 1),
        ]
        rows = rows_of(write_transcript(self.d, "flat.jsonl", recs))
        self.assertEqual(sorted(rows), ["105-flat-thing", "106-other"])
        self.assertEqual((rows["105-flat-thing"]["first_turn"], rows["105-flat-thing"]["last_turn"]), (1, 2))
        self.assertEqual((rows["106-other"]["last_turn"], rows["106-other"]["growth"]), (5, 300), "no result: final turn")

if __name__ == "__main__":
    unittest.main()
