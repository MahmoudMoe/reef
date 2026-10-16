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


if __name__ == "__main__":
    unittest.main()
