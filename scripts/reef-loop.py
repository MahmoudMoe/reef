#!/usr/bin/env python3
# CLASS: code
"""Reef loop — the loop engine's one read of the world: the TICK.
  reef-loop.py tick [--repo DIR] [--json] [--assert-no-idle] [--session-start [--hook]] [--hash]
  reef-loop.py start | stop | wait "<reason>" | clear-wait
The next-action set as data under 30 lines (rows to plan, dispatch now, PRs, rows to close, in flight from
.reef/inflight/ — stale after loop.inflight_stale_minutes = returned — parked, wait, stop). loop.no_progress_ticks
identical ticks with nothing in flight park the loop; caps.feature_tokens/batch_tokens via reef-cost --live.
--assert-no-idle (the Stop hook) exits 2 only for: active, no wait, ready work, nothing in flight, no stop — once per
tick hash. --session-start: handoff head + tick + next command under writing.session_start_tokens. Exit 0 · 2 · 1.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

FENCE = re.compile(r"\A---\r?\n(.*?\r?\n)---\r?\n", re.S)
MAX_LINES = 30
GH_TIMEOUT = float(os.environ.get("REEF_GH_TIMEOUT", "5"))


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def root_of(repo):
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=repo, capture_output=True, text=True)
    return r.stdout.strip() or os.path.abspath(repo)


def config(root):
    try:
        return json.loads(read(os.path.join(root, ".reef", "config.json")))
    except Exception:
        return {}


def load_state(root):
    p = os.path.join(root, ".reef", "loop.json")
    try:
        return json.loads(read(p))
    except Exception:
        return {"active": False, "wait": None, "hashes": [], "stop": None, "refused": None, "parked": None}


def save_state(root, st):
    os.makedirs(os.path.join(root, ".reef"), exist_ok=True)
    with open(os.path.join(root, ".reef", "loop.json"), "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)
        f.write("\n")


def run(cmd, cwd, timeout=20):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout
    except Exception:
        return 1, ""


def markers(root, kind, stale_minutes=None):
    d = os.path.join(root, ".reef", kind)
    out = []
    for f in (sorted(os.listdir(d)) if os.path.isdir(d) else []):
        p = os.path.join(d, f)
        age = (time.time() - os.path.getmtime(p)) / 60
        try:
            rec = json.loads(read(p))
        except Exception:
            rec = {}
        rec.update(id=f, age_min=int(age), stale=bool(stale_minutes) and age > stale_minutes)
        out.append(rec)
    return out


def tick(root):
    cfg = config(root)
    st = load_state(root)
    scripts = os.path.join(root, "scripts")
    py = sys.executable
    stale = int((cfg.get("loop") or {}).get("inflight_stale_minutes", 90) or 90)
    rc_q, q_ready = run([py, os.path.join(scripts, "reef-queue.py"), "ready", "--repo", root], root)
    rc_s, q_status = run([py, os.path.join(scripts, "reef-queue.py"), "status", "--repo", root], root)
    rc_g, g_ready = run([py, os.path.join(scripts, "reef-graph.py"), "ready", "--json", "--root", root], root)
    try:
        ready_tasks = json.loads(g_ready) if rc_g == 0 and g_ready.strip() else []
    except ValueError:
        ready_tasks = []
    inflight = markers(root, "inflight", stale)
    verifying = markers(root, "verifying", stale)
    inflight_ids = {str(m.get("id")) for m in inflight if not m["stale"]}
    returned = [m for m in inflight if m["stale"]]
    dispatch_now = [t for t in ready_tasks if str(t["id"]) not in inflight_ids and not t["id"].startswith("R")]
    rows = [l.split("\t") for l in q_status.splitlines() if "\t" in l]
    to_plan = [l.split("\t") for l in q_ready.splitlines() if "\t" in l and l.split("\t")[1] == "queued"]
    to_close = [r for r in rows if len(r) > 1 and r[1] == "done"]
    building = [r for r in rows if len(r) > 1 and r[1] == "building"]
    prs = []
    base = str((cfg.get("branches") or {}).get("base", "main") or "main")
    rc_p, out = run(["gh", "pr", "list", "--base", base, "--json", "number,headRefName,title,reviewDecision", "--limit", "20"], root, timeout=GH_TIMEOUT)
    if rc_p == 0 and out.strip():
        try:
            prs = json.loads(out)
        except ValueError:
            prs = []
    _, wt = run(["git", "worktree", "list", "--porcelain"], root)
    worktrees = [l[len("worktree "):] for l in wt.splitlines() if l.startswith("worktree ")][1:]
    parked = [l.split("\t")[0] for l in q_status.splitlines()] and []   # rows park through their tasks: status blocked
    rc_gs, g_status = run([py, os.path.join(scripts, "reef-graph.py"), "status", "--root", root], root)
    blocked = [l.split("\t")[0] for l in g_status.splitlines() if "\tblocked\t" in l]
    stop = st.get("stop")
    # 5.3 budgets through reef-cost
    caps = cfg.get("caps") or {}
    budget_note = None
    tp = os.environ.get("REEF_TRANSCRIPT") or st.get("transcript")
    if tp and os.path.isfile(tp) and (int(caps.get("feature_tokens", 0) or 0) or int(caps.get("batch_tokens", 0) or 0)):
        _, live = run([py, os.path.join(scripts, "reef-cost.py"), tp, "--live"], root)
        m = re.search(r"context_tokens=(\d+)", live)
        if m:
            n = int(m.group(1))
            ceiling = min(x for x in (int(caps.get("feature_tokens", 0) or 0), int(caps.get("batch_tokens", 0) or 0)) if x)
            if n > ceiling:
                stop = stop or f"budget: {n} tokens > caps ceiling {ceiling} — the feature/batch parks (5.3)"
                budget_note = stop
    state = {
        "rows_to_plan": [r[0] for r in to_plan], "dispatch_now": [t["id"] for t in dispatch_now],
        "prs_to_review": [f"#{p['number']} {p['headRefName']}" for p in prs], "rows_to_close": [r[0] for r in to_close],
        "in_flight": sorted(inflight_ids) + [f"verifying:{m['id']}" for m in verifying if not m["stale"]],
        "returned_unmerged": [m["id"] for m in returned], "parked": blocked, "building": [r[0] for r in building],
        "worktrees": len(worktrees), "wait": st.get("wait"), "active": bool(st.get("active")), "stop": stop,
        "broken": [] if rc_g == 0 else ["task graph broken or unreadable (reef-graph ready failed)"],
    }
    h = hashlib.sha1(json.dumps({k: state[k] for k in ("rows_to_plan", "dispatch_now", "prs_to_review", "rows_to_close", "in_flight", "returned_unmerged", "parked", "building")}, sort_keys=True).encode()).hexdigest()[:12]
    state["hash"] = h
    # no-progress parking (5.3): K identical ticks with nothing in flight
    k = int((cfg.get("loop") or {}).get("no_progress_ticks", 3) or 3)
    hashes = (st.get("hashes") or []) + [h]
    st["hashes"] = hashes[-k:]
    if len(st["hashes"]) == k and len(set(st["hashes"])) == 1 and not state["in_flight"] and state["active"] and not state["wait"]:
        st["parked"] = f"no progress: {k} identical ticks with nothing in flight — USER ACTION REQUIRED"
    state["parked_loop"] = st.get("parked")
    if budget_note:
        st["stop"] = stop
    save_state(root, st)
    return state, st


def render(state):
    nxt = ("dispatch: " + ", ".join(state["dispatch_now"])) if state["dispatch_now"] else \
          ("review: " + state["prs_to_review"][0]) if state["prs_to_review"] else \
          ("close: " + ", ".join(state["rows_to_close"])) if state["rows_to_close"] else \
          ("plan: " + ", ".join(state["rows_to_plan"])) if state["rows_to_plan"] else "nothing ready — stop or wait"
    lines = [f"tick {state['hash']}  loop={'active' if state['active'] else 'inactive'}" + (f"  wait={state['wait']!r}" if state["wait"] else "") + (f"  STOP={state['stop']}" if state["stop"] else ""),
             f"rows to plan: {', '.join(state['rows_to_plan']) or '-'}",
             f"dispatch now: {', '.join(state['dispatch_now']) or '-'}",
             f"PRs to review: {', '.join(state['prs_to_review']) or '-'}",
             f"rows to close: {', '.join(state['rows_to_close']) or '-'}",
             f"in flight: {', '.join(state['in_flight']) or '-'}",
             f"returned, unmerged: {', '.join(state['returned_unmerged']) or '-'}",
             f"parked: {', '.join(state['parked']) or '-'}" + (f"  LOOP PARKED: {state['parked_loop']}" if state.get("parked_loop") else ""),
             f"building rows: {', '.join(state['building']) or '-'}  worktrees: {state['worktrees']}",
             f"next: {nxt}"]
    lines += [f"BROKEN: {b}" for b in state["broken"]]
    return "\n".join(lines[:MAX_LINES]) + "\n"


def session_start(root, state, cfg):
    cap = int((cfg.get("writing") or {}).get("session_start_tokens", 8000) or 8000)
    head = ""
    for cand in ("HANDOFF.md",):
        p = os.path.join(root, cand)
        if os.path.isfile(p):
            head = "\n".join(read(p).splitlines()[:40])
    text = (head + "\n\n" if head else "") + render(state) + f"\nnext command: {'/reef-loop' if state['rows_to_plan'] or state['dispatch_now'] or state['prs_to_review'] else '/reef-plan <row> or /reef-assess'}\n"
    if len(text) // 4 > cap:
        text = text[: cap * 4] + f"\n[truncated: writing.session_start_tokens {cap}]\n"
    return text


def main(argv):
    repo = "."
    if "--repo" in argv:
        i = argv.index("--repo")
        repo = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    root = root_of(repo)
    if not argv:
        print("usage: reef-loop.py tick [--json|--assert-no-idle|--session-start|--hash] | start | stop | wait <reason> | clear-wait", file=sys.stderr)
        return 1
    cmd = argv[0]
    st = load_state(root)
    if cmd == "start":
        st.update(active=True, stop=None, parked=None, wait=None, hashes=[])
        save_state(root, st)
        print("loop: active")
        return 0
    if cmd == "stop":
        st.update(active=False)
        save_state(root, st)
        print("loop: inactive")
        return 0
    if cmd == "wait":
        st["wait"] = " ".join(argv[1:]) or "unspecified"
        save_state(root, st)
        print(f"loop: waiting — {st['wait']}")
        return 0
    if cmd == "clear-wait":
        st["wait"] = None
        save_state(root, st)
        print("loop: wait cleared")
        return 0
    if cmd != "tick":
        print(f"reef-loop: unknown command {cmd!r}", file=sys.stderr)
        return 1
    if not os.path.isfile(os.path.join(root, ".reef", "config.json")):
        if "--session-start" in argv:
            return 0   # a directory without Reef gets nothing injected (no output at all)
        print("reef-loop: no .reef/config.json", file=sys.stderr)
        return 1
    state, st = tick(root)
    if "--hash" in argv:
        print(state["hash"])
        return 0
    if "--json" in argv:
        print(json.dumps(state, indent=1))
        return 0
    if "--session-start" in argv:
        text = session_start(root, state, config(root))
        if "--hook" in argv:   # the SessionStart hook's envelope: additionalContext is what the model sees
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
        else:
            sys.stdout.write(text)
        return 0
    sys.stdout.write(render(state))
    if "--assert-no-idle" in argv:
        idle = (state["active"] and not state["wait"] and state["dispatch_now"] and not state["in_flight"]
                and not state["stop"] and not st.get("parked") and not state["broken"])
        if idle and st.get("refused") != state["hash"]:
            st["refused"] = state["hash"]
            save_state(root, st)
            print(f"IDLE: ready task(s) {', '.join(state['dispatch_now'])} undispatched while the loop is active — dispatch them (reef-task step 2) or record a wait (reef-loop.py wait \"<reason>\")", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
