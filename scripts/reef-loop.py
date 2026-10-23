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
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import calendar
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


def all_roots(root):
    """The main checkout and every worktree: reef-attempt runs where the task file lives, so its in-flight marker
    lands in that worktree's .reef/ (2026-10-17: 'in flight: -' while 1101 was building in a feature worktree)."""
    _, wt = run(["git", "worktree", "list", "--porcelain"], root)
    others = [l[len("worktree "):].strip() for l in wt.splitlines() if l.startswith("worktree ")]
    return [root] + [o for o in others if os.path.realpath(o) != os.path.realpath(root)]


def graph_mode(root, cfg):
    """0.7 (workflow v2, phase 4): which mode a fresh `dispatch now` task runs in. `graph.mode` is read from the MAIN
    checkout's config (loop policy has one home, like `hunter.*`): `auto` (template) = graph when this machine's probe
    recorded `GATE OK` (`.reef/graph/gate.json`, fail closed), chat otherwise; `chat` = never; `graph` = as auto, and a
    missing gate is named as BROKEN instead of falling back quietly. A fix round (`attempts` > 0) and a `verify now`
    task stay in chat mode whatever the setting: round 2 inside the graph is not designed yet. Measured 2026-10-18 on
    the trial's first graph-mode task (docs/perf/2026-10-18.md §C): the orchestrator paid one Workflow call where chat
    mode paid one turn per agent result."""
    _, wt = run(["git", "worktree", "list", "--porcelain"], root)
    first = next((l[len("worktree "):].strip() for l in wt.splitlines() if l.startswith("worktree ")), root)
    policy = config(first) if os.path.isfile(os.path.join(first, ".reef", "config.json")) else cfg
    mode = str(((policy.get("graph") or {}) if isinstance(policy.get("graph"), dict) else {}).get("mode", "auto") or "auto").strip().lower()
    if mode not in ("auto", "chat", "graph"):
        mode = "auto"
    ok = False
    try:
        with open(os.path.join(first, ".reef", "graph", "gate.json"), encoding="utf-8") as f:
            ok = bool(json.load(f).get("ok"))
    except (OSError, ValueError):
        ok = False
    return mode, ok


def markers(root, kind, stale_minutes=None):
    roots = root if isinstance(root, list) else [root]
    out, seen = [], set()
    for r in roots:
        for rec in _markers(r, kind, stale_minutes):
            if rec["id"] not in seen:
                seen.add(rec["id"])
                out.append(rec)
    return out


def _markers(root, kind, stale_minutes=None):
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


def task_feature(path):
    try:
        head = read(path)[:4000]
    except OSError:
        return ""
    m = re.search(r"^feature:[ \t]*(\S+)", head, re.M)
    return m.group(1) if m else ""


def plan_gate(root, scripts, py, tasks):
    """Split ready tasks into (dispatchable, awaiting): per feature, `reef-plan-check.py --verify-stamp --feature`
    decides — approval MISSING/STALE or stamp MISSING/STALE keeps the feature out of `dispatch now` and names why.
    Without the project's plan-check script (a layout older than reef-init) nothing is held back."""
    pc = os.path.join(scripts, "reef-plan-check.py")
    if not os.path.isfile(pc) or not tasks:
        return tasks, []
    verdict = {}
    for t in tasks:
        feat = task_feature(t.get("path", ""))
        if feat in verdict:
            continue
        rc, out = run([py, pc, root, "--verify-stamp", "--feature", feat], root, timeout=60)
        # v2 order (2026-10-17): the machines review first, the owner approves LAST — so a missing review is named
        # before a missing approval, and nothing after the gate but a HALT voids it
        hm = re.search(r"^hunter: (STALE|MISSING) (\S+)", out, re.M)
        if re.search(r"^review: FAILED", out, re.M):
            verdict[feat] = "plan review FAILED (fix the findings)"
        elif re.search(r"^review: (MISSING|STALE)", out, re.M):
            verdict[feat] = "machine review (hunter ‖ plan reviewer) before the gate"
        elif hm and hm.group(1) == "MISSING":
            verdict[feat] = f"hunter plan pass on {hm.group(2)} before the gate"
        elif hm and hm.group(1) == "STALE":
            # 2026-10-18: 202 and 203 were "dispatch now" with stamps their review-round edits had staled; the guard denied
            verdict[feat] = f"hunter plan pass stale on {hm.group(2)}: a re-check within hunter.plan_rounds, or `reef-adversarial <task> plan --decided <mark>`"
        elif rc == 0:
            verdict[feat] = None
        elif re.search(r"^approval: MISSING", out, re.M):
            verdict[feat] = "approval (the gate: the machines passed)"
        elif re.search(r"^approval: STALE", out, re.M):
            verdict[feat] = "re-approval (plan edited after approval)"
        else:
            verdict[feat] = "plan review"
    go = [t for t in tasks if verdict.get(task_feature(t.get("path", ""))) is None]
    held = sorted({f"{feat or '?'} ({why})" for feat, why in verdict.items() if why})
    return go, held


def tick(root):
    cfg = config(root)
    st = load_state(root)
    scripts = os.path.join(root, "scripts")
    py = sys.executable
    stale = int((cfg.get("loop") or {}).get("inflight_stale_minutes", 90) or 90)
    # a night (2026-10-23): rule 1's planned-before-found hid every found row while a planned one was ready, so a
    # contract naming found rows never moved them; at night the contract's Rows are what is driven, found ones too
    night = None
    if os.path.isfile(os.path.join(root, ".reef", "night", "active")):
        try:
            with open(os.path.join(root, ".reef", "night", "contract.md"), encoding="utf-8") as f:
                m = re.search(r"^Rows:\s*(.+)$", f.read(), re.M)
            night = set(re.findall(r"\d+", m.group(1))) if m else set()
        except OSError:
            night = set()
    rc_q, q_ready = run([py, os.path.join(scripts, "reef-queue.py"), "ready", "--repo", root] + (["--with-found"] if night is not None else []), root)
    rc_s, q_status = run([py, os.path.join(scripts, "reef-queue.py"), "status", "--repo", root], root)
    rc_g, g_ready = run([py, os.path.join(scripts, "reef-graph.py"), "ready", "--json", "--root", root], root)
    try:
        ready_tasks = json.loads(g_ready) if rc_g == 0 and g_ready.strip() else []
    except ValueError:
        ready_tasks = []
    roots_all = all_roots(root)
    inflight = markers(roots_all, "inflight", stale)
    verifying = markers(roots_all, "verifying", stale)
    inflight_ids = {str(m.get("id")) for m in inflight if not m["stale"]}
    returned = [m for m in inflight if m["stale"]]
    dispatch_now = [t for t in ready_tasks if str(t["id"]) not in inflight_ids and not t["id"].startswith("R")]
    # a READY task is not a DISPATCHABLE task: its plan must carry the human's approval record at the current digest
    # and a fresh review stamp (the same `--verify-stamp --feature` the guard runs at dispatch). First contact,
    # 2026-10-16: the handoff said "dispatch now: 101" for a plan nobody had approved or reviewed yet.
    dispatch_now, awaiting = plan_gate(root, scripts, py, dispatch_now)
    rows = [l.split("\t") for l in q_status.splitlines() if "\t" in l]
    to_plan = [l.split("\t") for l in q_ready.splitlines() if "\t" in l and l.split("\t")[1] == "queued"]
    if night is not None:
        to_plan = [r for r in to_plan if r[0] in night]
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
    # the loop reviews ITS PRs: heads under branches.feature_prefix (default feat/). Dependabot's and anyone else's
    # into the base are the owner's (first contact: three dependabot PRs sat in "PRs to review")
    prefix = str((cfg.get("branches") or {}).get("feature_prefix", "feat/") or "feat/")
    other_prs = [p for p in prs if not str(p.get("headRefName", "")).startswith(prefix)]
    prs = [p for p in prs if str(p.get("headRefName", "")).startswith(prefix)]
    _, wt = run(["git", "worktree", "list", "--porcelain"], root)
    worktrees = [l[len("worktree "):] for l in wt.splitlines() if l.startswith("worktree ")][1:]
    # a feature's plan lives on its branch, in its worktree, until the row closes: the main checkout's graph does not
    # see it (first contact: "rows to plan: 1 · tasks: none" while 101 was being built). Feature worktrees (branch
    # under the prefix) contribute their ready tasks and claim their rows; task worktrees (task/…) are copies and skipped
    planned_elsewhere, extra_ready = set(), []
    entry, branch = None, None
    for l in wt.splitlines() + [""]:
        if l.startswith("worktree "):
            entry, branch = l[len("worktree "):].strip(), None
        elif l.startswith("branch "):
            branch = l[len("branch "):].strip()
        elif not l and entry and entry != root and branch and branch.startswith("refs/heads/" + prefix):
            fdir = os.path.join(entry, (cfg.get("paths") or {}).get("features", "reef/features"))
            for spec in glob.glob(os.path.join(fdir, "*", "SPEC.md")):
                m = re.search(r"^Row:\s*(\d+)", read(spec), re.M)
                if m:
                    planned_elsewhere.add(m.group(1))
            rc_w, g_w = run([py, os.path.join(scripts, "reef-graph.py"), "ready", "--json", "--root", entry], entry)
            try:
                ready_w = json.loads(g_w) if rc_w == 0 and g_w.strip() else []
            except ValueError:
                ready_w = []
            ready_w = [x for x in ready_w if str(x["id"]) not in inflight_ids and not str(x["id"]).startswith("R")]
            go_w, held_w = plan_gate(entry, scripts, py, ready_w)
            seen = {str(x["id"]) for x in dispatch_now}
            extra_ready += [x for x in go_w if str(x["id"]) not in seen]
            awaiting += [h for h in held_w if h not in awaiting]
            entry = None
    dispatch_now = dispatch_now + extra_ready
    # a ready task whose implementer already handed back (handback-<id>.md in any checkout's .reef/ci-local, with no
    # report newer than it) is not to DISPATCH but to VERIFY: first contact (2026-10-17) the fresh session's tick said
    # "dispatch now: 103" over an uncommitted, handed-back worktree — a second implementer would have burnt a dispatch
    # … unless a failure was recorded AFTER that hand-back (reef-attempt's `- attempt N FAIL: … · at <UTC>` line under
    # ## Log, written by settle on a red gate or by the orchestrator on a verdict): the work was judged and failed, the
    # next step is the implementer, not the judges again (2026-10-18, qassimha 1103: a red gate counted as attempt 1
    # and the tick still said `verify now`, so graph mode could not re-dispatch and the gate would have run red again)
    verify_now = []
    by_id = {str(t["id"]): t for t in dispatch_now}
    for t in list(dispatch_now):
        tid = str(t["id"])
        failed_at = 0.0
        try:
            for m in re.finditer(r"^\s*-\s*attempt \d+ FAIL:.*· at (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\s*$", read(str(t.get("path") or "")), re.M):
                failed_at = max(failed_at, calendar.timegm(time.strptime(m.group(1), "%Y-%m-%dT%H:%M:%SZ")))
        except (OSError, ValueError):
            failed_at = 0.0
        for d_ in [root] + worktrees:
            hb = os.path.join(d_, ".reef", "ci-local", f"handback-{tid}.md")
            rp = os.path.join(d_, ".reef", "ci-local", f"report-{tid}.md")
            if os.path.isfile(hb) and (not os.path.isfile(rp) or os.path.getmtime(rp) < os.path.getmtime(hb)) and failed_at < os.path.getmtime(hb):
                verify_now.append(tid)
                dispatch_now.remove(t)
                break
    # 0.7: fresh tasks run in the graph when the mode and the gate say so; fix rounds stay in chat
    mode, gate = graph_mode(root, cfg)
    dispatch_mode = {}
    for t in dispatch_now:
        try:
            att = int((re.search(r"^attempts:[ \t]*(\d+)", read(str(t.get("path") or ""))[:4000], re.M) or [None, "0"])[1])
        except (OSError, ValueError):
            att = 0
        dispatch_mode[str(t["id"])] = "graph" if (mode != "chat" and gate) else "chat"
    # 0.7: a fix round and a handed-back task run in the graph too (generate builds the round-2 or verify-only
    # pipeline); a failed task cost the orchestrator one chat turn per agent result before (2026-10-20)
    for tid in verify_now:
        dispatch_mode[tid] = "graph" if (mode != "chat" and gate) else "chat"
    # a dispatched-and-failed task is progress: its attempts/dispatches counters are part of the tick's fingerprint
    # (2026-10-19, qassimha 1302, row 70: a graph run dispatched, ran and failed 1302 between two ticks that hashed the
    # same, and the loop parked itself for "no progress")
    counters = {}
    for tid in [str(t["id"]) for t in dispatch_now] + verify_now:
        try:
            fm = read(str((by_id.get(tid) or {}).get("path") or ""))[:4000]
            counters[tid] = "/".join((re.search(rf"^{k}:[ \t]*(\d+)", fm, re.M) or [None, "0"])[1] for k in ("attempts", "dispatches"))
        except OSError:
            counters[tid] = "?"
    # the files behind the ids, for the session-start text: 2026-10-18, after every /clear the fresh orchestrator ran
    # `find . -name "202*"` over the repository and listed .reef/hunt to locate what the tick had just named
    files = {}
    for tid in [str(t["id"]) for t in dispatch_now] + verify_now:
        t = by_id.get(tid) or {}
        tpath = str(t.get("path") or "")
        rec = {"task": os.path.relpath(tpath, root) if tpath else "?", "worktree": "", "evidence": []}
        try:
            m = re.search(r"^worktree:[ \t]*(\S+)", read(tpath)[:4000], re.M) if tpath else None
            rec["worktree"] = m.group(1) if m else ""
        except OSError:
            pass
        for d_ in [root] + worktrees:
            for name in (f"handback-{tid}.md", f"report-{tid}.md", f"report-{tid}-hunter.md"):
                fp = os.path.join(d_, ".reef", "ci-local", name)
                if os.path.isfile(fp):
                    rec["evidence"].append(os.path.relpath(fp, root))
        files[tid] = rec
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
    # a feature worktree is a full checkout, so it also carries every CLOSED row's SPEC (2026-10-17: "building rows:
    # 1, 11, 13, 2" with row 1 archived): only rows still in the queue count
    live = {r[0] for r in rows if len(r) > 1}
    planned_elsewhere = {r for r in planned_elsewhere if r in live}
    to_plan = [r for r in to_plan if r[0] not in planned_elsewhere]
    building = building + [[r] for r in sorted(planned_elsewhere) if r not in {b[0] for b in building}]
    # rule 7: found rows two batches old with no task file — the triage question is the orchestrator's at the batch boundary
    rc_t, triage = run([py, os.path.join(scripts, "reef-queue.py"), "triage", "--count", "--repo", root], root)
    triage_line = triage.strip().splitlines()[0] if rc_t == 1 and triage.strip() else ""
    # tasks whose orchestrator growth (summed over sessions, .reef/cost/tasks.json) passed caps.task_growth (0 = off)
    over = []
    cap_growth = int((cfg.get("caps") or {}).get("task_growth", 0) or 0)
    if cap_growth:
        try:
            with open(os.path.join(root, ".reef", "cost", "tasks.json"), encoding="utf-8") as f:
                store = json.load(f)
            for tid, sessions in sorted(store.items()):
                g = sum(int(s.get("growth", 0)) for s in sessions.values())
                if g > cap_growth:
                    over.append(f"{tid} ({g:,})")
        except (OSError, ValueError):
            pass
    state = {
        "rows_to_plan": [r[0] for r in to_plan], "dispatch_now": [t["id"] for t in dispatch_now], "verify_now": verify_now, "awaiting": awaiting, "files": files,
        "prs_to_review": [f"#{p['number']} {p['headRefName']}" for p in prs], "other_prs": len(other_prs),
        "rows_to_close": [r[0] for r in to_close],
        "in_flight": sorted(inflight_ids) + [f"verifying:{m['id']}" for m in verifying if not m["stale"]],
        "returned_unmerged": [m["id"] for m in returned], "parked": blocked, "building": [r[0] for r in building],
        "worktrees": len(worktrees), "wait": st.get("wait"), "active": bool(st.get("active")), "stop": stop, "over_growth": over, "triage": triage_line,
        "broken": ([] if rc_g == 0 else ["task graph broken or unreadable (reef-graph ready failed)"])
                  + (["graph.mode is `graph` but this machine has no GATE OK — python3 scripts/reef-graph-run.py probe (chat mode meanwhile)"] if (mode == "graph" and not gate and dispatch_now) else []),
        "graph_mode": mode, "graph_gate": gate, "dispatch_mode": dispatch_mode, "counters": counters,
    }
    h = hashlib.sha1(json.dumps({k: state[k] for k in ("rows_to_plan", "dispatch_now", "verify_now", "awaiting", "prs_to_review", "rows_to_close", "in_flight", "returned_unmerged", "parked", "building", "counters")}, sort_keys=True).encode()).hexdigest()[:12]
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


def next_command(state):
    """The one command the owner runs next. 2026-10-18: with 204 handed back (`verify now: 204`) the session-start text
    said `/reef-plan <row> or /reef-assess` — it looked only at rows to plan, dispatches and PRs — and the orchestrator
    echoed it as the status line's `next:` after every reply."""
    busy = any(state.get(k) for k in ("rows_to_plan", "dispatch_now", "verify_now", "prs_to_review", "rows_to_close", "returned_unmerged", "awaiting"))
    return "/reef-loop" if busy else "/reef-plan <row> or /reef-assess"


def render(state):
    dm = state.get("dispatch_mode") or {}
    g_ids = [i for i in state["dispatch_now"] if dm.get(i) == "graph"]
    c_ids = [i for i in state["dispatch_now"] if dm.get(i) != "graph"]
    why = "" if state.get("graph_mode") == "chat" else ("" if state.get("graph_gate") else " (no GATE OK — reef-graph-run.py probe)")
    disp = " · ".join(([f"dispatch (graph): {', '.join(g_ids)} — python3 scripts/reef-graph-run.py generate"] if g_ids else [])
                      + ([f"dispatch (chat): {', '.join(c_ids)} — /reef-task{why}"] if c_ids else []))
    v_graph = [i for i in state.get("verify_now") or [] if dm.get(i) == "graph"]
    nxt = (f"verify (graph): {', '.join(v_graph)} — python3 scripts/reef-graph-run.py generate") if v_graph else \
          ("verify: " + ", ".join(state["verify_now"])) if state.get("verify_now") else \
          disp if state["dispatch_now"] else \
          ("review: " + state["prs_to_review"][0]) if state["prs_to_review"] else \
          ("close: " + ", ".join(state["rows_to_close"])) if state["rows_to_close"] else \
          ("plan: " + ", ".join(state["rows_to_plan"])) if state["rows_to_plan"] else \
          ("awaiting: " + "; ".join(state.get("awaiting") or [])) if state.get("awaiting") else "nothing ready — stop or wait"
    lines = [f"tick {state['hash']}  loop={'active' if state['active'] else 'inactive'}" + (f"  wait={state['wait']!r}" if state["wait"] else "") + (f"  STOP={state['stop']}" if state["stop"] else ""),
             f"rows to plan: {', '.join(state['rows_to_plan']) or '-'}",
             f"dispatch now: {', '.join(state['dispatch_now']) or '-'}" + (f"  verify now: {', '.join(state['verify_now'])} (handed back, uncommitted — gate + verifier, no implementer)" if state.get("verify_now") else ""),
             f"awaiting: {'; '.join(state.get('awaiting') or []) or '-'}",
             f"PRs to review: {', '.join(state['prs_to_review']) or '-'}" + (f"  ({state['other_prs']} other PR(s) into the base, not the loop's)" if state.get("other_prs") else ""),
             f"rows to close: {', '.join(state['rows_to_close']) or '-'}",
             f"in flight: {', '.join(state['in_flight']) or '-'}",
             f"returned, unmerged: {', '.join(state['returned_unmerged']) or '-'}",
             f"parked: {', '.join(state['parked']) or '-'}" + (f"  LOOP PARKED: {state['parked_loop']}" if state.get("parked_loop") else ""),
             f"building rows: {', '.join(state['building']) or '-'}  worktrees: {state['worktrees']}"
             + (f"  GROWTH over caps.task_growth: {', '.join(state['over_growth'])} — say why in the journal" if state.get("over_growth") else "")
             + (f"\n{state['triage']} — python3 scripts/reef-queue.py triage, ONE owner question at the batch boundary" if state.get("triage") else ""),
             f"next: {nxt}"]
    lines += [f"BROKEN: {b}" for b in state["broken"]]
    return "\n".join(lines[:MAX_LINES]) + "\n"


def runner_section(root):
    """reef-run.py's Runner section (one renderer: the runner re-splices it between the markers on every live step); empty
    markers when reef-run.py is not beside this script."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("reef_run", os.path.join(os.path.dirname(os.path.abspath(__file__)), "reef-run.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.runner_html(root)
    except Exception:
        return "<!--runner--><!--/runner-->"


def write_status_page(root, state, text):
    """`.reef/status.html` (usability plan A2): the tick, the loop's wait or stop, the handoff's head, refreshed on
    every tick (the Stop hook ticks every turn) — what a person opens instead of asking "where are we" in chat."""
    import html
    import time as _t
    rdir = os.path.join(root, ".reef")
    if not os.path.isdir(rdir):
        return
    hand = ""
    hp = os.path.join(root, "HANDOFF.md")
    if os.path.isfile(hp):
        hand = "\n".join(read(hp).splitlines()[:60])
    badge = "STOP" if state.get("stop") else ("waiting" if state.get("wait") else ("active" if state.get("active") else "inactive"))
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="60">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Reef — {html.escape(os.path.basename(root))}</title>
<style>:root{{--bg:#fff;--fg:#182B33;--mute:#5b6b73;--line:#e3e8ea;--ok:#0E7C7B;--warn:#b5651d;--bad:#D94F35}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111a1f;--fg:#e6edf0;--mute:#9fb0b8;--line:#2a373e}}}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:15px/1.45 -apple-system,Segoe UI,sans-serif;max-width:960px}}
h1{{font-size:20px;margin:0 0 4px}} .mute{{color:var(--mute)}} pre{{background:transparent;border:1px solid var(--line);border-radius:8px;padding:12px;overflow:auto;white-space:pre-wrap}}
.badge{{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;border:1px solid var(--line)}}
.active{{color:var(--ok)}} .waiting{{color:var(--warn)}} .STOP{{color:var(--bad)}} h2{{font-size:15px;margin:18px 0 6px}}</style></head><body>
<h1>Reef — {html.escape(os.path.basename(root))} <span class="badge {badge}">{badge}</span></h1>
<div class="mute">tick {html.escape(str(state.get('hash', '')))} · written {_t.strftime('%Y-%m-%d %H:%M:%S')} · refreshes every 60 s · <code>python3 scripts/reef-loop.py tick</code> is the source</div>
{runner_section(root)}<h2>The tick</h2><pre>{html.escape(text)}</pre>
""" + (f"<h2>Waiting on</h2><pre>{html.escape(str(state.get('wait')))}</pre>" if state.get("wait") else "") \
        + (f"<h2>Stopped</h2><pre>{html.escape(str(state.get('stop')))}</pre>" if state.get("stop") else "") \
        + (f"<h2>HANDOFF.md (head)</h2><pre>{html.escape(hand)}</pre>" if hand else "") + "</body></html>\n"
    try:
        with open(os.path.join(rdir, "status.html"), "w", encoding="utf-8") as f:
            f.write(page)
    except OSError:
        pass


def scripts_behind_plugin(root):
    """Project copies of scripts/reef-* that differ from the plugin's (CLAUDE_PLUGIN_ROOT, set by Claude Code for a
    hook). First contact (2026-10-16): the project's reef-loop.py was a day behind the plugin's and nobody could tell."""
    plugin = os.environ.get("CLAUDE_PLUGIN_ROOT") or ""
    pdir = os.path.join(plugin, "scripts")
    if not plugin or not os.path.isdir(pdir):
        return []
    behind = []
    sdir = os.path.join(root, "scripts")
    for name in sorted(os.listdir(sdir) if os.path.isdir(sdir) else []):
        if not name.startswith("reef-"):
            continue
        theirs = os.path.join(pdir, name)
        if not os.path.isfile(theirs):
            continue
        try:
            with open(os.path.join(sdir, name), "rb") as a, open(theirs, "rb") as b:
                if a.read() != b.read():
                    behind.append(name)
        except OSError:
            continue
    return behind


def session_start(root, state, cfg):
    cap = int((cfg.get("writing") or {}).get("session_start_tokens", 8000) or 8000)
    head = ""
    for cand in ("HANDOFF.md",):
        p = os.path.join(root, cand)
        if os.path.isfile(p):
            head = "\n".join(read(p).splitlines()[:40])
            # the handoff was rendered by the session that hit the ceiling; its STOP line is that session's, not
            # this one's (first contact: a fresh orchestrator read "171k tokens" and planned a /clear it did not need)
            head = re.sub(r"[ \t]*STOP=context ceiling:[^\n]*", "", head)
    behind = scripts_behind_plugin(root)
    note = (f"reef: {len(behind)} project script(s) behind the plugin ({', '.join(behind[:4])}{'…' if len(behind) > 4 else ''})"
            f" — run /reef-init and accept scripts/* before dispatching\n") if behind else ""
    files = state.get("files") or {}
    flines = "".join(f"  {tid}: {r['task']}" + (f" · worktree {r['worktree']}" if r.get("worktree") else "") +
                     (f" · evidence {', '.join(r['evidence'])}" if r.get("evidence") else "") + "\n" for tid, r in sorted(files.items()))
    text = (head + "\n\n" if head else "") + note + render(state) + (f"files (read these, search for nothing):\n{flines}" if flines else "") + f"\nnext command: {next_command(state)}\n"
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
    if "--session-start" in argv and str(st.get("stop") or "").startswith("context ceiling"):
        # the ceiling stop belongs to the session that hit it; the session starting now is fresh (first contact,
        # 2026-10-16: after /clear the tick still said STOP=context ceiling: 164970 tokens, from the dead session)
        st.update(stop=None, transcript=None)
        save_state(root, st)
    state, st = tick(root)
    if "--hash" in argv:
        print(state["hash"])
        return 0
    try:
        write_status_page(root, state, render(state))
    except Exception:
        pass   # the page is a convenience; the tick never fails for it
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
        idle = (state["active"] and not state["wait"] and (state["dispatch_now"] or state.get("verify_now")) and not state["in_flight"]
                and not state["stop"] and not st.get("parked") and not state["broken"])
        if idle and st.get("refused") != state["hash"]:
            st["refused"] = state["hash"]
            save_state(root, st)
            print(f"IDLE: ready task(s) {', '.join(state['dispatch_now'] + state.get('verify_now', []))} undispatched while the loop is active — dispatch them (reef-task step 2) or record a wait (reef-loop.py wait \"<reason>\")", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
