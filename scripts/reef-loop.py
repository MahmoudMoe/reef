#!/usr/bin/env python3
# CLASS: code
"""Reef loop — the loop engine's one read of the world: the TICK.
  reef-loop.py tick [--repo DIR] [--json] [--assert-no-idle] [--session-start [--hook]] [--hash]
  reef-loop.py start | stop | wait "<reason>" | clear-wait | unlock      (wait renders HANDOFF.md first — v3)
  (0.7.1) the guard lets one session hold the loop; `wait` and `stop` release it, `unlock` takes it over for this session
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
import shutil
import subprocess
import sys
import calendar
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # the shared helpers live beside this script
sys.dont_write_bytecode = True   # and no scripts/__pycache__ lands in a project's tree (reef-update, a row worktree read it as changes)
from reef_common import read_config as config, read_replace as read, main_checkout, drop_hold, process_alive, run_rc, run_rc3, git_root, checkouts, task_copies, task_frontmatter, report_verdict, read_or_empty, spec_row  # noqa: E402

FENCE = re.compile(r"\A---\r?\n(.*?\r?\n)---\r?\n", re.S)
MAX_LINES = 30
GH_TIMEOUT = float(os.environ.get("REEF_GH_TIMEOUT", "5"))


def release_hold(root):
    """One orchestrator at a time (0.7.1): the session holding the loop lets go; returns who held it."""
    return drop_hold(main_checkout(root))


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


run = lambda cmd, cwd, timeout=20: run_rc(cmd, cwd, timeout, timeout_rc=1)   # the readers know 1


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
    if os.environ.get("REEF_RUNNER") or runner_alive(first):   # a headless session (the runner's: REEF_RUNNER=1, or its live lock) has no Workflow tool — measured
        return "chat", False                                   # 2026-10-31 on a live probe, "The Workflow tool isn't available to me": under the runner every row builds in chat mode
    ok = False
    gate = os.path.join(first, ".reef", "graph", "gate.json")
    try:
        if os.path.dirname(os.path.realpath(gate)) != os.path.join(os.path.realpath(os.path.join(first, ".reef")), "graph"):   # a symlinked folder: not the probe's record
            return mode, False
        with open(gate, encoding="utf-8") as f:
            ok = bool(json.load(f).get("ok"))
    except (OSError, ValueError):
        ok = False
    return mode, ok


def runner_alive(root):
    """The runner's lock names a live process: this session runs under it (the lock is the runner's own record; an env line can be unset)."""
    try:
        with open(os.path.join(root, ".reef", "run", "lock"), encoding="utf-8") as f:
            pid = int(f.read().strip() or 0)
        return bool(pid) and process_alive(pid)
    except (OSError, ValueError):
        return False


def markers(root, kind, stale_minutes=None):
    """One marker per id across the checkouts: the freshest (2026-11-02, the stress test H2: the first found won, so round 1's
    stale marker in main shadowed round 2's fresh one in the feature worktree and the task read as returned)."""
    best = {}
    for r in (root if isinstance(root, list) else [root]):
        for rec in _markers(r, kind, stale_minutes):
            if rec["id"] not in best or rec["mtime"] > best[rec["id"]]["mtime"]:
                best[rec["id"]] = rec
    return list(best.values())


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
        rec.update(id=f, mtime=os.path.getmtime(p), age_min=int(age), stale=bool(stale_minutes) and age > stale_minutes)
        out.append(rec)
    return out


FAIL_AT = re.compile(r"^\s*-\s*attempt \d+ FAIL:.*· at (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?Z\s*$", re.M)   # a sub-second stamp read too (M6)


def task_evidence(roots, tid, path):
    """The newest of each record of one task across every checkout (2026-11-02, the stress test H2: a hand-back and its report
    were paired inside one checkout, and a PASS fell back to `dispatch now`): the hand-back, the report and its last VERDICT,
    the newest FAIL in any copy of the task file, and the status and attempts of its newest copy (H6: a copy blocked in the
    task worktree bound none of the others)."""
    ev = {"handback": 0.0, "report": 0.0, "verdict": "", "failed": 0.0, "status": "", "attempts": 0}
    for r in roots:
        for k in ("handback", "report"):
            p = os.path.join(r, ".reef", "ci-local", f"{k}-{tid}.md")
            try:
                if os.path.getmtime(p) > ev[k]:
                    ev[k] = os.path.getmtime(p)
                    ev["verdict"] = report_verdict(read(p)) if k == "report" else ev["verdict"]
            except OSError:
                continue
    newest = -1.0
    for c in (task_copies(path, roots) if path else []):
        try:
            text, mt = read(c), os.path.getmtime(c)
            for m in FAIL_AT.finditer(text):
                ev["failed"] = max(ev["failed"], calendar.timegm(time.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")) + float(m.group(2) or 0))
        except (OSError, ValueError):
            continue
        if mt > newest:
            fm = task_frontmatter(text) or {}
            newest, ev["status"] = mt, fm.get("status", "")
            ev["attempts"] = int(fm["attempts"]) if str(fm.get("attempts") or "").isdigit() else 0
    return ev


def graph_reads(root, scripts, py, cos):
    """The task graph of every checkout that holds a plan, read once each — the main checkout and each feature worktree
    (2026-11-02, the stress test H1: a feature worktree only added its `ready` list, so its broken graph, its blocked task and a
    task done on its branch were invisible). Returns ({checkout: ready tasks}, {id: (checkout, status, state)}, broken): a
    feature worktree's line for an id overrides main's when it differs — the copy that moved is the plan's home."""
    ready, lines, broken, base = {}, {}, [], {}
    for co in cos:
        rc, out = run([py, os.path.join(scripts, "reef-graph.py"), "ready", "--json", "--root", co], co)
        _, status = run([py, os.path.join(scripts, "reef-graph.py"), "status", "--root", co], co)
        try:
            ready[co] = json.loads(out) if rc == 0 and out.strip() else []
        except ValueError:
            rc = 1
        if rc != 0:
            ready[co] = []
            broken.append("task graph broken or unreadable (reef-graph ready failed" + (f" in {os.path.relpath(co, root)}" if co != root else "") + ")")
            continue
        for l in status.splitlines():
            p = l.split("\t")
            if len(p) < 5:
                continue
            if co == root:
                base[p[0]] = l
            if co == root or base.get(p[0]) != l:
                lines[p[0]] = (co, p[1], p[4])
    return ready, lines, broken


def orphan_rows(root, cfg, prefix, base, feats):
    """{row: (branch, re-attach command)} for a feature branch that carries a plan and has no worktree (2026-11-02, the stress
    test H1: the tick said `plan: 1` over feat/first, which held an approved plan, and /reef-plan would cut the branch afresh).
    A branch already in the base is a leftover, not a plan."""
    out = {}
    fpath = str((cfg.get("paths") or {}).get("features", "reef/features") or "reef/features")
    wtdir = str((cfg.get("worktree") or {}).get("dir") or ".reef/worktrees")
    for b in run(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/"], root)[1].split():
        if not b.startswith(prefix) or b in feats or run(["git", "merge-base", "--is-ancestor", b, base], root)[0] == 0:
            continue
        for f in run(["git", "ls-tree", "-r", "--name-only", b, "--", fpath], root)[1].splitlines():
            rid = spec_row(run(["git", "show", f"{b}:{f}"], root)[1]) if f.endswith("/SPEC.md") else ""
            if rid:
                out[rid] = (b, f"git worktree prune && git worktree add {wtdir}/{b[len(prefix):]} {b}")
    return out


def task_feature(path):
    try:
        head = read(path)[:4000]
    except OSError:
        return ""
    m = re.search(r"^feature:[ \t]*(\S+)", head, re.M)
    return m.group(1) if m else ""


APPROVAL_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")   # reef-approval.py's QUESTION: the only slug a record can carry


def plan_gate(root, scripts, py, tasks):
    """Split ready tasks into (dispatchable, awaiting): per feature, `reef-plan-check.py --verify-stamp --feature`
    decides — approval MISSING/STALE or stamp MISSING/STALE keeps the feature out of `dispatch now` and names why.
    Without the project's plan-check script (a layout older than reef-init) nothing is held back; with it, the one beside
    this script decides — the copy only marks the layout, as in the guard."""
    if not os.path.isfile(os.path.join(scripts, "reef-plan-check.py")) or not tasks:
        return tasks, []
    pc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reef-plan-check.py")
    verdict, command = {}, {}
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
        elif re.search(r"^approval: (MISSING|STALE)", out, re.M):
            # 2026-10-29 (row 9 on the current adoption): the hold named the state and no command, and the owner's own
            # loop session wrote the wait as "run reef-approval.py --owner … in a terminal". Every wait names the exact
            # line the owner types: the digest comes from the same check (--digest), so the command is never stale.
            why = "approval (the gate: the machines passed)" if re.search(r"^approval: MISSING", out, re.M) else "re-approval (plan edited after approval)"
            # the reviews (2026-10-29): the digest is on the approval line itself (`plan is <16 hex>`) — no second process,
            # so the hold is the same text every tick; and the slug is rendered into the owner's shell line only when it
            # is one the approval question accepts (reef-approval.py QUESTION) — anything else is named, never quoted
            m = re.search(r"^approval: (?:MISSING|STALE) .*plan is ([0-9a-f]{16})", out, re.M)
            if m and APPROVAL_SLUG.fullmatch(feat):
                command[feat] = f'python3 scripts/reef-approval.py --owner "Approve plan {feat} at {m.group(1)}?"'
            elif m:
                why += "; the slug is not one an approval can name ([A-Za-z0-9._-]) — fix `feature:` in its tasks"
            verdict[feat] = why
        else:
            verdict[feat] = "plan review"
    go = [t for t in tasks if verdict.get(task_feature(t.get("path", ""))) is None]
    # the command stands AFTER the hold's closing paren: the owner copies the line as printed (the review of #210)
    held = sorted({f"{feat or '?'} ({why})" + (f" — {command[feat]}" if feat in command else "") for feat, why in verdict.items() if why})
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
        try:   # the runner's one reader of the contract's Rows: line (stress round two M5)
            night = set(runner_module().night_rows(root))
        except Exception:
            night = set()
    os.environ.pop("REEF_QUEUE_SNAPSHOT_SINCE", None)   # the first read of the tick syncs; the rest read its snapshot
    t0 = time.time()
    rc_q, q_ready = run([py, os.path.join(scripts, "reef-queue.py"), "ready", "--repo", root] + (["--with-found"] if night is not None else []), root)
    if rc_q == 0:
        os.environ["REEF_QUEUE_SNAPSHOT_SINCE"] = str(t0)
    rc_s, q_status = run([py, os.path.join(scripts, "reef-queue.py"), "status", "--repo", root], root)
    roots_all = all_roots(root)
    inflight = markers(roots_all, "inflight", stale)
    verifying = markers(roots_all, "verifying", stale)
    # a failed read is named, never read as an empty answer (2026-11-02, stress H4); `ready` and `status` are two syncs, so a
    # row is to plan only when the status read agrees it is queued
    failed = [f"{what} failed (exit {rc}) — its answer is not read as empty" for what, rc in (("reef-queue.py ready", rc_q), ("reef-queue.py status", rc_s)) if rc]
    rows = [l.split("\t") for l in q_status.splitlines() if "\t" in l]
    live = {r[0] for r in rows if len(r) > 1 and r[1] == "queued"}
    to_plan = [l.split("\t") for l in q_ready.splitlines() if "\t" in l and l.split("\t")[1] == "queued" and l.split("\t")[0] in live]
    if night is not None:
        to_plan = [r for r in to_plan if r[0] in night]
    to_close = [r for r in rows if len(r) > 1 and r[1] == "done"]
    building = [r for r in rows if len(r) > 1 and r[1] == "building"]
    base = str((cfg.get("branches") or {}).get("base", "main") or "main")
    rc_p, out, err = run_rc3(["gh", "pr", "list", "--base", base, "--json", "number,headRefName,title,reviewDecision", "--limit", "20"], root, GH_TIMEOUT, timeout_rc=1)
    try:
        prs = json.loads(out.strip() or "[]") if rc_p == 0 else None
    except ValueError:
        prs = None
    if not isinstance(prs, list):
        prs = []
        # the PR read is optional where there is no GitHub to read: no gh, gh not logged in (exit 4), or no GitHub remote
        if shutil.which("gh") and rc_p != 4 and not re.search(r"no git remotes found|known GitHub host", err):
            failed.append(f"gh pr list failed (exit {rc_p}) or answered no list — the loop's PRs are unknown")
    prs = [p for p in prs if isinstance(p, dict)]
    # the loop reviews ITS PRs: heads under branches.feature_prefix (default feat/). Dependabot's and anyone else's
    # into the base are the owner's (first contact: three dependabot PRs sat in "PRs to review")
    prefix = str((cfg.get("branches") or {}).get("feature_prefix", "feat/") or "feat/")
    other_prs = [p for p in prs if not str(p.get("headRefName", "")).startswith(prefix)]
    prs = [p for p in prs if str(p.get("headRefName", "")).startswith(prefix)]
    _, wt = run(["git", "worktree", "list", "--porcelain"], root)
    worktrees = [l[len("worktree "):] for l in wt.splitlines() if l.startswith("worktree ")][1:]
    # ONE read per checkout that holds a plan (graph_reads): a feature's plan lives on its branch, in its worktree, until the
    # row closes (first contact: "rows to plan: 1 · tasks: none" while 101 was being built). Task worktrees (task/…) are
    # copies: their records count (task_evidence), their graphs do not
    feats = {b: w for b, w in checkouts(root, prefix).items() if os.path.isdir(w)}   # a worktree deleted by hand reads as none
    cos = [root] + list(feats.values())
    ready_by, lines, broken = graph_reads(root, scripts, py, cos)
    broken = failed + broken
    in_queue = {r[0]: r for r in rows if len(r) > 1}
    done_rows = {r[0] for r in to_close}
    heads = {str(p.get("headRefName", "")) for p in prs}
    names = lambda d: [f for f in (os.listdir(d) if os.path.isdir(d) else []) if re.match(r"R?\d+-.*\.md$", f)]
    fpath = str((cfg.get("paths") or {}).get("features", "reef/features") or "reef/features")
    row_of, planned_elsewhere, to_review, half_closed, unclean = {}, set(), {}, {}, []
    for co in cos:
        for spec in sorted(glob.glob(os.path.join(co, fpath, "*", "SPEC.md"))):
            slug, rid = os.path.basename(os.path.dirname(spec)), spec_row(read(spec))
            row_of[slug] = rid or row_of.get(slug, "")
            # a feature worktree is a full checkout, so it also carries every CLOSED row's SPEC (2026-10-17: "building rows:
            # 1, 11, 13, 2" with row 1 archived), and a merged row's: only rows still in the queue and not done in the base count
            if co == root or rid not in in_queue or rid in done_rows:
                # its own worktree still there with the row archived: a close killed part-way (2026-11-03, hard M3) — reef-row names the rest
                if co != root and rid and rid not in in_queue and feats.get(prefix + slug) == co and [rid, "done"] not in to_close and \
                        re.search(rf"^\|\s*{re.escape(rid)}\s*\|", read_or_empty(os.path.join(root, os.path.dirname(str((cfg.get("paths") or {}).get("queue") or "docs/queue.md")), "queue-archive.md")), re.M):
                    to_close.append([rid, "done"])
                continue
            planned_elsewhere.add(rid)
            tdir = os.path.join(os.path.dirname(spec), "tasks")
            # a close killed before its commit (2026-11-03, hard M2/H2): `status: done` outside done/, or moved there uncommitted —
            # merge-close resumes it; the review waits for a clean tree (the full gate tests the tree, the record binds the head)
            dirty = run(["git", "status", "--porcelain", "--untracked-files=all"], co)[1]
            for p in [os.path.join(tdir, f) for f in names(tdir)] + [os.path.join(tdir, "done", f) for f in names(os.path.join(tdir, "done"))]:
                if (os.path.dirname(p) == tdir or os.path.relpath(p, co) in dirty) and (task_frontmatter(read(p)) or {}).get("status") == "done":
                    half_closed[re.match(r"R?\d+", os.path.basename(p)).group()] = (co, p)
            if names(os.path.join(tdir, "done")) and not names(tdir) and next(b for b, w in feats.items() if w == co) not in heads:
                if not dirty.strip():
                    to_review[rid] = slug   # every task done on its branch and no PR: the review is next (2026-11-02, H1; reef-loop §2.3)
                elif not any(c == co for c, _ in half_closed.values()):
                    unclean.append(f"row {rid}: {os.path.relpath(co, root)} has uncommitted changes — commit them, then /reef-review {slug}")
    # per ready task, the newest of each record across every checkout decides (task_evidence): handed back → VERIFY, not a second
    # implementer (first contact, 2026-10-17: "dispatch now: 103" over an uncommitted, handed-back worktree) — unless a FAIL or a
    # report is newer: the work was judged (2026-10-18, qassimha 1103; 2026-11-01, task 19101's FAIL in the task worktree's copy);
    # a PASS newer than both → merge-close, never a second implementer; blocked or at the cap in its newest copy → parked (2026-11-02, H2/H6)
    mk = {str(m["id"]): m for m in inflight}
    cap = int((cfg.get("caps") or {}).get("attempts", 3) or 3)
    by_id, home_of, verify_now, close_now, dispatch_now, capped = {}, {}, [], [], [], []
    for co in cos:
        for t in ready_by[co]:
            tid = str(t["id"])
            if tid in by_id or tid.startswith("R") or lines.get(tid, (co,))[0] != co:
                continue
            by_id[tid], home_of[tid] = t, co
            ev = task_evidence(roots_all, tid, str(t.get("path") or ""))
            m = mk.get(tid)
            live_m = bool(m) and not m["stale"]
            hb = ev["handback"]
            if ev["status"] == "blocked" or ev["attempts"] >= cap:
                capped.append(tid)
            elif hb and hb > max(ev["report"], ev["failed"]) and not (live_m and m["mtime"] > hb):
                verify_now.append(tid)   # handed back after its marker: the session died before the `rm` (H2)
            elif live_m:
                continue
            elif ev["report"] > max(hb, ev["failed"]) and ev["verdict"] == "PASS":
                close_now.append(tid)
            else:
                dispatch_now.append(t)
    for tid, (co, p) in sorted(half_closed.items()):
        if tid not in by_id:
            by_id[tid], home_of[tid] = {"id": tid, "path": p}, co
            close_now.append(tid)   # its PASS (or gate) was in: the close was under way
    # a READY task is not a DISPATCHABLE task: its row's Depends must be merged (2026-11-02, H1: row 2, planned early in its own
    # worktree, was offered while row 1 still built), and its plan must carry the human's approval record at the current digest
    # and a fresh review stamp (the same `--verify-stamp --feature` the guard runs at dispatch). First contact, 2026-10-16: the
    # handoff said "dispatch now: 101" for a plan nobody had approved or reviewed yet.
    awaiting, ok = [], set()
    for co in cos:
        go, held = plan_gate(co, scripts, py, [by_id[i] for i in verify_now + close_now + [str(t["id"]) for t in dispatch_now] if home_of[i] == co])
        ok |= {str(t["id"]) for t in go}
        awaiting += [h for h in held if h not in awaiting]
    awaiting += unclean
    deps = {r[0]: re.findall(r"'([^']+)'", r[2]) for r in rows if len(r) > 2}
    for tid in sorted(ok):
        feat = task_feature(str(by_id[tid].get("path") or ""))
        undone = [d for d in deps.get(row_of.get(feat, feat), []) if d in in_queue and in_queue[d][1] != "done"]
        if undone:
            ok.discard(tid)
            note = f"{feat} (row {row_of.get(feat, feat)} Depends on {', '.join(undone)}, not merged)"
            awaiting += [note] if note not in awaiting else []
    verify_now, close_now = [i for i in verify_now if i in ok], [i for i in close_now if i in ok]
    dispatch_now = [t for t in dispatch_now if str(t["id"]) in ok]
    for rid, (b, cmd) in sorted(orphan_rows(root, cfg, prefix, base, feats).items()):
        if rid in in_queue and rid not in done_rows:
            planned_elsewhere.add(rid)
            awaiting.append(f"row {rid}: {b} carries its plan and has no worktree — {cmd}")
    # a marker of a task done in its home is history, and one older than its hand-back came back (2026-11-02, H2)
    status_of = {i: v[1] for i, v in lines.items()}
    inflight_ids = {i for i, m in mk.items() if not m["stale"] and status_of.get(i) != "done" and i not in verify_now}
    returned = [m for m in inflight if m["stale"] and status_of.get(str(m["id"])) != "done"]
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
    for tid in [str(t["id"]) for t in dispatch_now] + verify_now + close_now:
        try:
            fm = read(str((by_id.get(tid) or {}).get("path") or ""))[:4000]
            counters[tid] = "/".join((re.search(rf"^{k}:[ \t]*(\d+)", fm, re.M) or [None, "0"])[1] for k in ("attempts", "dispatches"))
        except OSError:
            counters[tid] = "?"
    # the files behind the ids, for the session-start text: 2026-10-18, after every /clear the fresh orchestrator ran
    # `find . -name "202*"` over the repository and listed .reef/hunt to locate what the tick had just named
    files = {}
    for tid in [str(t["id"]) for t in dispatch_now] + verify_now + close_now:
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
    # rows park through their tasks: blocked or at the retry cap in any checkout that holds a plan, or in a ready task's newest
    # copy (2026-11-02, H1/H6: blocked in a feature worktree, or pending at the cap, the tick said nothing and no one was asked)
    blocked = sorted({i for i, (_, s, why) in lines.items() if s == "blocked" or "at the retry cap" in why} | set(capped),
                     key=lambda x: (x.startswith("R"), len(x), x))
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
    to_plan = [r for r in to_plan if r[0] not in planned_elsewhere]
    building = building + [[r] for r in sorted(planned_elsewhere) if r not in {b[0] for b in building}]
    # v3 phase 4 — finish before starting: at most loop.rows_in_flight rows (default 2; 0 = no cap) between plan and close
    # (building, or done and awaiting close); a new row is planned only when there is room, the rest are named as held
    cap_rows = int((cfg.get("loop") or {}).get("rows_in_flight", 2) or 0)
    rows_in_flight = sorted({b[0] for b in building} | {r[0] for r in to_close}, key=lambda x: (len(x), x))
    held_rows = []
    if cap_rows:
        room = max(0, cap_rows - len(rows_in_flight))
        held_rows, to_plan = [r[0] for r in to_plan[room:]], to_plan[:room]
    # rule 7: found rows two batches old with no task file — the triage question is the orchestrator's at the batch boundary
    rc_t, triage = run([py, os.path.join(scripts, "reef-queue.py"), "triage", "--count", "--repo", root], root)
    triage_line = triage.strip().splitlines()[0] if rc_t == 1 and triage.strip() else ""
    os.environ.pop("REEF_QUEUE_SNAPSHOT_SINCE", None)
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
        "rows_to_plan": [r[0] for r in to_plan], "rows_held": held_rows, "rows_in_flight": rows_in_flight, "rows_cap": cap_rows,
        "dispatch_now": [t["id"] for t in dispatch_now], "verify_now": verify_now, "close_now": close_now, "awaiting": awaiting, "files": files,
        "prs_to_review": [f"#{p['number']} {p['headRefName']}" for p in prs], "other_prs": len(other_prs),
        "rows_to_review": sorted(to_review, key=lambda x: (len(x), x)), "review_slugs": to_review,
        "rows_to_close": [r[0] for r in to_close],
        "in_flight": sorted(inflight_ids) + [f"verifying:{m['id']}" for m in verifying if not m["stale"]],
        "returned_unmerged": [m["id"] for m in returned], "parked": blocked, "building": [r[0] for r in building],
        "worktrees": len(worktrees), "wait": st.get("wait"), "active": bool(st.get("active")), "stop": stop, "over_growth": over, "triage": triage_line,
        "broken": broken
                  + (["graph.mode is `graph` but this machine has no GATE OK — /reef-graph once, in a session with the Workflow tool, from the main checkout (chat mode meanwhile)"] if (mode == "graph" and not gate and dispatch_now) else []),
        "graph_mode": mode, "graph_gate": gate, "dispatch_mode": dispatch_mode, "counters": counters,
    }
    h = hashlib.sha1(json.dumps({k: state[k] for k in ("rows_to_plan", "dispatch_now", "verify_now", "close_now", "awaiting", "prs_to_review", "rows_to_review", "rows_to_close", "in_flight", "returned_unmerged", "parked", "building", "counters")}, sort_keys=True).encode()).hexdigest()[:12]
    state["hash"] = h
    # no-progress parking (5.3): K identical ticks with nothing in flight
    k = int((cfg.get("loop") or {}).get("no_progress_ticks", 3) or 3)
    prev = (st.get("hashes") or [])[-1:]
    if st.get("parked") and str(st["parked"]).startswith("no progress") and prev and prev[0] != h:
        # 2026-10-28 (row 46): the loop parked while a fix round was built in a worktree the tick did not see, then told the
        # owner only he could unpark it. The park is the tick's own: a tick that differs from the one that parked is progress
        st["parked"] = None
        print(f"unparked: the tick changed since the park ({prev[0]} → {h}) — progress", file=sys.stderr)   # stderr: --json keeps its one document
    hashes = (st.get("hashes") or []) + [h]
    st["hashes"] = hashes[-k:]
    if len(st["hashes"]) == k and len(set(st["hashes"])) == 1 and not state["in_flight"] and state["active"] and not state["wait"]:
        st["parked"] = (f"no progress: {k} identical ticks with nothing in flight — fix the cause, then python3 scripts/reef-loop.py start "
                        "(the tick unparks itself once it changes)")
    state["parked_loop"] = st.get("parked")
    if budget_note:
        st["stop"] = stop
    save_state(root, st)
    return state, st


def next_command(state):
    """The one command the owner runs next. 2026-10-18: with 204 handed back (`verify now: 204`) the session-start text
    said `/reef-plan <row> or /reef-assess` — it looked only at rows to plan, dispatches and PRs — and the orchestrator
    echoed it as the status line's `next:` after every reply."""
    busy = any(state.get(k) for k in ("rows_to_plan", "dispatch_now", "verify_now", "close_now", "prs_to_review", "rows_to_review", "rows_to_close", "returned_unmerged", "awaiting"))
    return "/reef-loop" if busy else "/reef-plan <row> or /reef-assess"


def render_status_page(state):
    dm = state.get("dispatch_mode") or {}
    g_ids = [i for i in state["dispatch_now"] if dm.get(i) == "graph"]
    c_ids = [i for i in state["dispatch_now"] if dm.get(i) != "graph"]
    why = "" if state.get("graph_mode") == "chat" else ("" if state.get("graph_gate") else " (no GATE OK — /reef-graph once, in a session with the Workflow tool, from the main checkout; chat keeps every guarantee)")
    disp = " · ".join(([f"dispatch (graph): {', '.join(g_ids)} — python3 scripts/reef-graph-run.py generate"] if g_ids else [])
                      + ([f"dispatch (chat): {', '.join(c_ids)} — /reef-task{why}"] if c_ids else []))
    v_graph = [i for i in state.get("verify_now") or [] if dm.get(i) == "graph"]
    nxt = (f"verify (graph): {', '.join(v_graph)} — python3 scripts/reef-graph-run.py generate") if v_graph else \
          ("verify: " + ", ".join(state["verify_now"])) if state.get("verify_now") else \
          (f"merge-close: {', '.join(state['close_now'])} — the PASS is on record (reef-task step 4, scripts/reef-merge-close)") if state.get("close_now") else \
          disp if state["dispatch_now"] else \
          ("review: " + state["prs_to_review"][0]) if state["prs_to_review"] else \
          (f"review: row {state['rows_to_review'][0]} — /reef-review {state['review_slugs'][state['rows_to_review'][0]]} (every task done on its branch, no PR)") if state.get("rows_to_review") else \
          ("close: " + ", ".join(state["rows_to_close"])) if state["rows_to_close"] else \
          ("plan: " + ", ".join(state["rows_to_plan"])) if state["rows_to_plan"] else \
          ("awaiting: " + "; ".join(state.get("awaiting") or [])) if state.get("awaiting") else \
          ("BROKEN: " + state["broken"][0]) if state.get("broken") else "nothing ready — stop or wait"
    lines = [f"tick {state['hash']}  loop={'active' if state['active'] else 'inactive'}" + (f"  wait={state['wait']!r}" if state["wait"] else "") + (f"  STOP={state['stop']}" if state["stop"] else ""),
             f"rows to plan: {', '.join(state['rows_to_plan']) or '-'}"
             + (f" (held by loop.rows_in_flight {state['rows_cap']}: {', '.join(state['rows_held'])}; in flight: {', '.join(state['rows_in_flight'])})" if state.get("rows_held") else ""),
             f"dispatch now: {', '.join(state['dispatch_now']) or '-'}" + (f"  verify now: {', '.join(state['verify_now'])} (handed back, uncommitted — gate + verifier, no implementer)" if state.get("verify_now") else ""),
             f"awaiting: {'; '.join(state.get('awaiting') or []) or '-'}",
             f"PRs to review: {', '.join(state['prs_to_review']) or '-'}" + (f"  ({state['other_prs']} other PR(s) into the base, not the loop's)" if state.get("other_prs") else "")
             + (f"  rows to review (no PR yet): {', '.join(state['rows_to_review'])}" if state.get("rows_to_review") else ""),
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


def runner_module():
    """reef-run.py beside this script, loaded as a module."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("reef_run", os.path.join(os.path.dirname(os.path.abspath(__file__)), "reef-run.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def runner_section(root):
    """reef-run.py's Runner section (one renderer: the runner re-splices it between the markers on every live step); empty
    markers when reef-run.py is not beside this script."""
    try:
        return runner_module().runner_html(root)
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
        if not name.startswith(("reef-", "reef_")):
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
    text = (head + "\n\n" if head else "") + note + render_status_page(state) + (f"files (read these, search for nothing):\n{flines}" if flines else "") + f"\nnext command: {next_command(state)}\n"
    if len(text) // 4 > cap:
        text = text[: cap * 4] + f"\n[truncated: writing.session_start_tokens {cap}]\n"
    return text


def main(argv):
    if "-h" in argv or "--help" in argv:   # 0.7 (2026-10-24): `footnote --help` wrote a footnote reading "--help"
        print(__doc__.strip())
        return 0
    repo = "."
    if "--repo" in argv:
        i = argv.index("--repo")
        repo = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    root = main_checkout(git_root(repo))   # the loop's ONE state, whichever checkout the caller stands in (2026-11-02, the stress test H5)
    if not argv:
        print("usage: reef-loop.py tick [--json|--assert-no-idle|--session-start|--hash] | start | stop [<reason>] | wait <reason> | clear-wait", file=sys.stderr)
        return 1
    cmd = argv[0]
    st = load_state(root)
    if cmd == "start":
        st.update(active=True, stop=None, parked=None, wait=None, hashes=[])
        save_state(root, st)
        print("loop: active")
        return 0
    if cmd == "stop":   # `stop "<reason>"` (2026-10-29): reef-run.py stop ending an orphaned session says why here
        st.update(active=False, **({"stop": argv[1]} if len(argv) > 1 and argv[1] else {}))
        save_state(root, st)
        release_hold(root)
        print("loop: inactive")
        return 0
    if cmd == "wait":
        text = " ".join(" ".join(argv[1:]).split())
        if len(text) > 200 and not text.startswith(("/clear", "job:")):   # 2026-11-01: a 600-character wait, cut mid-sentence on the owner's phone
            print(f"reef-loop: an owner wait is one line, at most 200 characters ({len(text)} given): the row and what it needs — the commands come "
                  "from the questions filed with `reef-queue.py ask`; nothing recorded", file=sys.stderr)
            return 2
        # v3 phase 5: every wait renders HANDOFF.md from measured state first — a session never ends on a hand-written
        # handoff (the guard refuses one) or on none
        hs = os.path.join(root, "scripts", "reef-handoff")
        if os.path.isfile(hs):
            rc_h, out_h = run([sys.executable, hs, "--repo", root, "--write"], root, timeout=60)
            print((out_h.strip().splitlines() or ["HANDOFF.md written"])[-1] if rc_h == 0 else f"HANDOFF.md NOT written (reef-handoff exit {rc_h})")
        else:
            print("HANDOFF.md not rendered: scripts/reef-handoff is missing (reef-update copies it)")
        st["wait"] = " ".join(argv[1:]) or "unspecified"
        save_state(root, st)
        release_hold(root)   # the /clear hand-over: the next session starts at once
        print(f"loop: waiting — {st['wait']}")
        return 0
    if cmd == "clear-wait":
        st["wait"] = None
        save_state(root, st)
        print("loop: wait cleared")
        return 0
    if cmd == "unlock":
        held = release_hold(root)
        print(f"loop: unlocked (held by session {held})" if held else "loop: nobody held it")
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
        write_status_page(root, state, render_status_page(state))
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
    sys.stdout.write(render_status_page(state))
    if "--assert-no-idle" in argv:
        idle = (state["active"] and not state["wait"] and (state["dispatch_now"] or state.get("verify_now") or state.get("close_now")) and not state["in_flight"]
                and not state["stop"] and not st.get("parked") and not state["broken"])
        if idle and st.get("refused") != state["hash"]:
            st["refused"] = state["hash"]
            save_state(root, st)
            print(f"IDLE: ready task(s) {', '.join(state['dispatch_now'] + state.get('verify_now', []) + state.get('close_now', []))} undispatched while the loop is active — dispatch them (reef-task step 2) or record a wait (reef-loop.py wait \"<reason>\")", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
