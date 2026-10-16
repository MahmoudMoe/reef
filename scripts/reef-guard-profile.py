#!/usr/bin/env python3
# CLASS: code
"""Reef guard profile — p50/p95/max wall time of reef-guard.py per matcher over the recorded payloads.
Usage: reef-guard-profile.py [--runs N] [--out docs/perf/guard-profile-<date>.md] [--check hooks/hooks.json]
Recommended timeout = max(10, ceil(5 × p95)) s; --check exits 1 when hooks.json is below it.
"""
import datetime
import glob
import json
import math
import os
import subprocess
import sys
import tempfile
import time

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(PLUGIN, "scripts", "reef-guard.py")


def payloads(scratch):
    out = {"Bash": [], "Task|Agent": [], "Edit|Write|MultiEdit": [], "Stop": []}
    for p in glob.glob(os.path.join(PLUGIN, "tests", "fixtures", "payloads", "*.json")):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        d["cwd"] = scratch
        if d.get("hook_event_name") == "PreToolUse" and d.get("tool_name") == "Bash":
            out["Bash"].append(d)
        elif d.get("hook_event_name") == "PreToolUse" and d.get("tool_name") == "Agent":
            d["tool_input"]["subagent_type"] = "reef:verifier"
            out["Task|Agent"].append(d)
        elif d.get("hook_event_name") == "Stop":
            out["Stop"].append(d)
    out["Bash"].append({"tool_name": "Bash", "cwd": scratch, "hook_event_name": "PreToolUse",
                        "tool_input": {"command": "set -o pipefail; npm test 2>&1 | tail -5 && git commit -m 'x' && gh pr merge 12 --squash"}})
    out["Edit|Write|MultiEdit"].append({"tool_name": "Edit", "cwd": scratch, "hook_event_name": "PreToolUse",
                                        "tool_input": {"file_path": os.path.join(scratch, ".reef", "config.json"),
                                                       "old_string": '"parallel": 10', "new_string": '"parallel": 4'}})
    return out


def main(argv):
    runs, out, check = 30, None, None
    i = 0
    while i < len(argv):
        if argv[i] == "--runs":
            runs = int(argv[i + 1]); i += 2
        elif argv[i] == "--out":
            out = argv[i + 1]; i += 2
        elif argv[i] == "--check":
            check = argv[i + 1]; i += 2
        else:
            print(f"unknown option {argv[i]}", file=sys.stderr); return 2
    scratch = tempfile.mkdtemp(prefix="reef-profile.")
    subprocess.run(["git", "init", "-q", scratch], check=True)
    os.makedirs(os.path.join(scratch, ".reef"))
    with open(os.path.join(scratch, ".reef", "config.json"), "w") as f:
        json.dump({"gates": {"full": "true"}, "roles": {"verifier": "opus"}, "merge": {"by": "loop"}, "graph": {"parallel": 10}}, f)
    rows = []
    for matcher, items in payloads(scratch).items():
        if not items:
            continue
        times = []
        for k in range(runs):
            d = items[k % len(items)]
            t0 = time.monotonic()
            subprocess.run([sys.executable, GUARD], input=json.dumps(d), capture_output=True, text=True,
                           env=dict(os.environ, REEF_GH_TIMEOUT="0.5", PATH="/nonexistent:" + os.environ.get("PATH", "")))
            times.append(time.monotonic() - t0)
        times.sort()
        p50, p95, mx = times[len(times) // 2], times[min(len(times) - 1, math.ceil(0.95 * len(times)) - 1)], times[-1]
        rows.append((matcher, p50, p95, mx, max(10, math.ceil(5 * p95))))
    date = datetime.date.today().isoformat()
    lines = [f"# Guard profile — {date}", "", f"`python3 scripts/reef-guard-profile.py --runs {runs}` on {sys.platform}, python {sys.version.split()[0]}; "
             "wall time of one `reef-guard.py` invocation per matcher over the recorded payloads. Rule: `timeout` ≥ 5 × p95, floor 10 s.", "",
             "| matcher | p50 (ms) | p95 (ms) | max (ms) | timeout (s) |", "|---|---|---|---|---|"]
    for m, p50, p95, mx, rec in rows:
        lines.append(f"| `{m}` | {p50 * 1000:.0f} | {p95 * 1000:.0f} | {mx * 1000:.0f} | {rec} |")
    text = "\n".join(lines) + "\n"
    sys.stdout.write(text)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
    if check:
        with open(check, encoding="utf-8") as f:
            hooks = json.load(f)["hooks"]
        bad = []
        for m, _, _, _, rec in rows:
            for ev in hooks.values():
                for entry in ev:
                    if entry.get("matcher", "") == m or (m == "Stop" and "matcher" not in entry):
                        for h in entry["hooks"]:
                            if h.get("timeout", 0) < rec:
                                bad.append(f"{m}: timeout {h.get('timeout')} < recommended {rec}")
        if bad:
            print("PROFILE MISMATCH: " + "; ".join(bad))
            return 1
        print("ok: every matcher's timeout covers 5 x p95")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
