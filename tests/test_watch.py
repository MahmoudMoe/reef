"""Sabotage suite for scripts/reef-watch: the one-screen report a human or a scheduled observer reads when nobody
was in the session. Known fixture state yields exactly those counts; the output is deterministic and under the line
cap; a transcript's per-feature growth appears; a judge report that reef-claims rejects is named; no config is exit 2."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCH = os.path.join(ROOT, "scripts", "reef-watch")

TASK = ("---\nid: {id}\nfeature: demo-feature\nstatus: {status}\ncomplexity: mech\neffort: low\nblocked-by: []\nresources: []\n"
        "tier: full\ntouches: []\nverify: judge\nattempts: {attempts}\ndispatches: 1\nlast_failure_sig: \"\"\n---\n# {id} — t\n\n"
        "## Scope\nx.\n\n## Decision\n\n## Acceptance Criteria\n- AC-1 (FR-1): it works.\n\n## Proof\n| AC | Proof |\n|---|---|\n| AC-1 | `test_x` |\n\n## Out of scope\n\n## Log\n")


def write(d, rel, text):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def project():
    d = tempfile.mkdtemp(prefix="reef-watch.")
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    write(d, ".reef/config.json", json.dumps({"gates": {"full": "true"}, "caps": {"attempts": 3, "context_warn": 5000, "context_tokens": 9000},
                                              "paths": {"features": "reef/features", "queue": "reef/queue.md", "runlog": "reef/journal.md"}}))
    write(d, ".reef/version", "0.6.0\n")
    write(d, "reef/features/demo-feature/SPEC.md", "# Demo — SPEC\n\nRow: 1\nSlug: demo-feature\n")
    write(d, "reef/features/demo-feature/tasks/done/101-a.md", TASK.format(id=101, status="done", attempts=1))
    write(d, "reef/features/demo-feature/tasks/102-b.md", TASK.format(id=102, status="in-progress", attempts=3))
    write(d, "reef/features/demo-feature/tasks/103-c.md", TASK.format(id=103, status="blocked", attempts=2))
    write(d, "reef/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n"
                              "| 1 | demo feature | | planned | 1 | |\n| 2 | a hole the hunter found | 1 | found | 2 | |\n")
    write(d, "reef/journal.md", "# Journal\n\n| Task | Implementer | Verifier | Attempts | Result | ACs | Escaped defects |\n|---|---|---|---|---|---|---|\n"
                                "| 101-a | opus | opus PASS | 1/3 | merged 2026-10-15 | AC-1 achieved | — |\n"
                                "| 099-z | opus | opus PASS | 1/3 | merged 2026-09-01 | AC-1 achieved | — |\n")
    write(d, ".reef/loop.json", json.dumps({"active": True, "stop": "context ceiling: 9500 tokens > caps.context_tokens 9000 — checkpoint, then /clear"}))
    write(d, ".reef/ci-local/report-101.md", "RUN: agent=verifier task=101\nlooks fine\nVERDICT: PASS\n")   # no RULE, no evidence: rejected
    for name in ("reef-cost.py", "reef-claims.py", "reef-loop.py", "reef-queue.py", "reef-graph.py"):
        with open(os.path.join(ROOT, "scripts", name)) as f:
            write(d, f"scripts/{name}", f.read())
    return d


def transcript(d):
    def turn(rid, ctx, blocks=None):
        return {"type": "assistant", "requestId": rid, "uuid": rid, "message": {"role": "assistant", "content": blocks or [{"type": "text", "text": "x"}],
                                                                                  "usage": {"input_tokens": ctx, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 1}}}
    recs = [
        turn("r1", 1000),
        turn("r2", 2000, [{"type": "tool_use", "id": "tu1", "name": "Agent", "input": {"prompt": "REEF-TASK: reef/features/demo-feature/tasks/102-b.md\nimplement"}}]),
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu1", "content": [{"type": "text", "text": "done"}]}]}},
        turn("r3", 6000),
    ]
    tdir = os.path.join(d, "transcripts")
    os.makedirs(tdir)
    with open(os.path.join(tdir, "abcd1234-session.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    return tdir


def watch(*args):
    return subprocess.run([sys.executable, WATCH, *args], capture_output=True, text=True)


class Watch(unittest.TestCase):
    def test_known_state_yields_exactly_those_counts(self):
        d = project()
        tdir = transcript(d)
        with open(os.path.join(tdir, "ffff0000-empty.jsonl"), "w") as f:
            f.write(json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}) + "\n")   # aborted: no turn
        r = watch("--repo", d, "--transcripts", tdir, "--since", "2026-10-01")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("tasks: blocked 1, done 1, in-progress 1 · attempts used 6 (max 3, cap 3)", out)
        self.assertIn("AT CAP: 102-b.md", out)
        self.assertIn("BLOCKED: 103-c.md", out)
        self.assertIn("journal: 2 row(s), 1 since 2026-10-01: 101-a", out)
        self.assertIn("queue: 2 open row(s), 1 found: a hole the hunter found", out)
        self.assertIn("STOP: context ceiling: 9500 tokens", out)
        self.assertIn("sessions: 1 transcript(s)", out)
        self.assertIn("3 turns, first 1,000, max 6,000 OVER WARN · demo-feature growth 4,000 over 1 dispatch(es)", out)
        self.assertIn("reports: 1 judge report(s), 1 rejected by reef-claims: report-101.md", out)
        self.assertLessEqual(len(out.splitlines()), 60)

    def test_deterministic_and_json(self):
        d = project()
        tdir = transcript(d)
        a = watch("--repo", d, "--transcripts", tdir).stdout
        b = watch("--repo", d, "--transcripts", tdir).stdout
        self.assertEqual(a, b)
        j = json.loads(watch("--repo", d, "--transcripts", tdir, "--json").stdout)
        self.assertEqual(j["lines"], a.splitlines())

    def test_not_a_reef_project_is_exit_2(self):
        d = tempfile.mkdtemp(prefix="reef-watch-none.")
        r = watch("--repo", d)
        self.assertEqual(r.returncode, 2)
        self.assertIn("no .reef/config.json", r.stderr)


if __name__ == "__main__":
    unittest.main()
