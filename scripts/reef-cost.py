#!/usr/bin/env python3
# CLASS: code
"""Reef cost — what a session cost, from the Claude Code transcript (stdlib only).
Usage: reef-cost.py [<transcript.jsonl>] [--repo DIR] [--format text|md|json] | --session-start | --live
       reef-cost.py <transcript.jsonl> --record [--repo DIR]   (0.7) fold this session's per-task growth into .reef/cost/tasks.json
       reef-cost.py growth <task-id> [--repo DIR]             (0.7) the task's orchestrator growth so far, across sessions
       reef-cost.py growth --feature <slug> [--repo DIR]      (0.7) the feature's share and planning share, across sessions
       reef-cost.py rows [--repo DIR] [--since ISO] [--format text|md|json]   (v3 phase 1) the pipeline per merged row
       (cat hook-payload.json | reef-cost.py --live  reads transcript_path from the payload)
Turns = one per requestId; context = input + cache writes + cache reads; a compaction counts once (boundary record,
else summary record); --live reads the last 256 KB only. Rows: per feature dispatched through Task/Agent
(REEF-TASK:/REEF-FEATURE:), main-session growth = sum of positive context deltas over its span. Exit 0; 2 on a missing transcript. See README "Measured".
rows (v3 phase 1): per row merged into branches.base since --since — lead time (the plan's first commit -> the approval record ->
the merge; the forge's PR when gh reaches it, else git), tokens (.reef/cost/features.json), full-suite runs (the gate's
.reef/ci-local/runs.jsonl), rollups and reverts; per batch the process-to-product commit ratio and the security FAILs.
"""
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from functools import partial

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True
from reef_common import table_cells, die as _die, git_out as _git_out  # noqa: E402

TAIL_BYTES = 256 * 1024
FENCE = re.compile(r"\A---\r?\n(.*?\r?\n)---\r?\n", re.S)
REEF_TASK = re.compile(r"^REEF-TASK:[ \t]*(.+?)[ \t\r]*$", re.M)      # the guard's own regexes
REEF_FEATURE = re.compile(r"^REEF-FEATURE:[ \t]*(\S+)", re.M)
NOTIFIED_ID = re.compile(r"<tool-use-id>\s*([^<\s]+)\s*</tool-use-id>")


die = partial(_die, prefix="reef-cost")


def ctx(usage):
    return sum(int(usage.get(k, 0) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))


def est_tokens(obj):
    """chars/4 over the text the model saw — an estimate for SHARES, never billed tokens."""
    if isinstance(obj, str):
        return len(obj) // 4
    if isinstance(obj, dict):
        return sum(est_tokens(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(est_tokens(v) for v in obj)
    return 0


# attachments that are standing context (the harness's system prompt and what rides with it), never growth
STANDING = {"prompt_snapshot", "skill_listing", "environment", "deferred_tools_record", "session_context", "instructions", "advisor_tool"}


def analyse(path):
    """One transcript -> dict. Turns are keyed by requestId (every content block of one API call
    repeats the same usage), so a 3-block reply is ONE turn."""
    turns, seen, tool_names, cats = [], {}, {}, {}
    boundaries = summaries = 0
    standing = {}
    first_turn = None
    agent_type = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            t = d.get("type")
            if t == "assistant":
                msg = d.get("message") or {}
                rid = d.get("requestId") or msg.get("id") or d.get("uuid")
                usage = msg.get("usage") or {}
                agent_type = agent_type or d.get("attributionAgent")
                if rid not in seen and usage:
                    seen[rid] = {"ctx": ctx(usage), "out": int(usage.get("output_tokens", 0) or 0),
                                 "write": int(usage.get("cache_creation_input_tokens", 0) or 0),
                                 "read": int(usage.get("cache_read_input_tokens", 0) or 0),
                                 "fresh": int(usage.get("input_tokens", 0) or 0), "model": msg.get("model", "")}
                    turns.append(seen[rid])
                    first_turn = first_turn if first_turn is not None else seen[rid]["ctx"]
                for b in msg.get("content") or []:
                    if not isinstance(b, dict):
                        continue
                    kind = b.get("type")
                    if kind == "tool_use":
                        tool_names[b.get("id")] = b.get("name", "?")
                        cats["assistant:tool_use"] = cats.get("assistant:tool_use", 0) + est_tokens(b.get("input"))
                    elif kind == "text":
                        cats["assistant:text"] = cats.get("assistant:text", 0) + est_tokens(b.get("text"))
                    elif kind == "thinking":
                        cats["assistant:thinking"] = cats.get("assistant:thinking", 0) + est_tokens(b.get("thinking"))
            elif t == "user":
                if d.get("isCompactSummary"):
                    summaries += 1
                    cats["compact-summary"] = cats.get("compact-summary", 0) + est_tokens((d.get("message") or {}).get("content"))
                    continue
                content = (d.get("message") or {}).get("content")
                if isinstance(content, str):
                    cats["prompt"] = cats.get("prompt", 0) + est_tokens(content)
                    continue
                for b in content or []:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_result":
                        name = tool_names.get(b.get("tool_use_id"), "?")
                        cats[f"tool_result:{name}"] = cats.get(f"tool_result:{name}", 0) + est_tokens(b.get("content"))
                    else:
                        cats["prompt"] = cats.get("prompt", 0) + est_tokens(b)
            elif t == "attachment":
                # by type: a `file` diff view, a `queued_command` notification, a `skill_listing`, … — the real planning
                # session (2026-10-16) had 54% of its context under one undifferentiated "attachment" bucket
                akind = str((d.get("attachment") or {}).get("type") or "?") if isinstance(d.get("attachment"), dict) else "?"
                n = est_tokens(d.get("rendered") or d.get("attachment"))
                if akind in STANDING:
                    # the system prompt, the skill list, the environment: paid on EVERY turn, recorded a few times in the
                    # transcript, and no growth at all (2026-10-18: two prompt snapshots read as "37% of the context")
                    st = standing.setdefault(akind, {"items": 0, "per_item": 0})
                    st["items"] += 1
                    st["per_item"] = max(st["per_item"], n)
                    continue
                k = f"attachment:{akind}"
                cats[k] = cats.get(k, 0) + n
            elif t == "system" and d.get("subtype") == "compact_boundary":
                boundaries += 1
    ctxs = sorted(x["ctx"] for x in turns)

    def pct(p):   # nearest-rank: the smallest value with at least p of the turns at or below it
        return ctxs[max(0, min(len(ctxs) - 1, -(-int(p * 100) * len(ctxs) // 100) - 1))] if ctxs else 0
    return {
        "path": path, "agent_type": agent_type, "turns": len(turns), "first_turn_context": first_turn or 0,
        "context": {"mean": (sum(ctxs) // len(ctxs)) if ctxs else 0, "p50": pct(0.5), "p90": pct(0.9), "max": ctxs[-1] if ctxs else 0},
        "compactions": boundaries if boundaries else summaries,
        "cache": {"writes": sum(x["write"] for x in turns), "reads": sum(x["read"] for x in turns),
                  "uncached_input": sum(x["fresh"] for x in turns), "output": sum(x["out"] for x in turns)},
        "categories": dict(sorted(cats.items(), key=lambda kv: -kv[1])),
        "standing": standing,
        "models": sorted({x["model"] for x in turns if x["model"]}),
    }


def feature_slug(prompt):
    """The feature a dispatch prompt names: its REEF-TASK: line wins over its REEF-FEATURE: line."""
    m = REEF_TASK.search(prompt)
    if m:
        p = m.group(1)
        if "/features/" in p and "/tasks/" in p:
            return p.rsplit("/tasks/", 1)[0].rsplit("/", 1)[-1]
        return os.path.splitext(os.path.basename(p))[0]
    m = REEF_FEATURE.search(prompt)
    return m.group(1) if m else None


def feature_rows(path):
    """Per feature: the main-session span from its first Task/Agent dispatch turn to the latest turn
    after one of its dispatches' results (a task-notification for the id, else its tool_result)."""
    turn_pos, turn_ctx, turn_of = [], [], {}
    dispatches = []                     # (feature, tool_use id, dispatch turn, role, planning?)
    task_dispatches = []                # (task id, role, tool_use id, dispatch turn) — 0.7, per task and role
    notified, returned = {}, {}         # tool_use id -> record position
    boundary_pos, summary_pos = [], []
    with open(path, encoding="utf-8", errors="replace") as f:
        for pos, line in enumerate(f):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict):
                continue
            t = d.get("type")
            if t == "system" and d.get("subtype") == "compact_boundary":
                boundary_pos.append(pos)
                continue
            if t == "user" and d.get("isCompactSummary"):
                summary_pos.append(pos)
                continue
            if t == "attachment":
                # a background agent's notification also arrives as an `attachment` of type `queued_command` whose
                # `prompt` is the <task-notification> text — the only form the hunter's dispatch had in the Reef row
                # session (found by the acceptance review of this very feature; growth read 34,098 for a true 40,840)
                a = d.get("attachment") or {}
                pr = a.get("prompt") if isinstance(a, dict) else None
                if a.get("type") == "queued_command" and isinstance(pr, str) and pr.lstrip().startswith("<task-notification>"):
                    for tid in NOTIFIED_ID.findall(pr):
                        notified.setdefault(tid, pos)
                continue
            if d.get("isSidechain") or t not in ("assistant", "user"):
                continue
            msg = d.get("message") or {}
            content = msg.get("content")
            if t == "assistant":
                rid = d.get("requestId") or msg.get("id") or d.get("uuid")
                if rid not in turn_of and msg.get("usage"):
                    turn_pos.append(pos)
                    turn_ctx.append(ctx(msg["usage"]))
                    turn_of[rid] = len(turn_pos)
                for b in content if isinstance(content, list) else []:
                    if not isinstance(b, dict) or b.get("type") != "tool_use":
                        continue
                    if b.get("name") == "Workflow":
                        # graph mode (v2 phase 3): one Workflow call runs many tasks; its script (inline or at scriptPath,
                        # written by reef-graph-run) carries their REEF-TASK: lines — each is a dispatch of role `workflow`
                        inp = b.get("input") or {}
                        src = inp.get("script") or ""
                        sp = inp.get("scriptPath")
                        if not src and isinstance(sp, str) and os.path.isfile(sp):
                            try:
                                with open(sp, encoding="utf-8", errors="replace") as sf:
                                    src = sf.read()
                            except OSError:
                                src = ""
                        for tpath in sorted(set(re.findall(r"REEF-TASK:[ \t]*([^\s\\\"]+)", src))):
                            feat_w = feature_slug(f"REEF-TASK: {tpath}")
                            turn_w = turn_of.get(rid, max(len(turn_pos), 1))
                            if feat_w:
                                dispatches.append((feat_w, b.get("id"), turn_w, "workflow", False))
                            tid_w = re.match(r"^(R?\d+)", os.path.basename(tpath))
                            if tid_w:
                                task_dispatches.append((tid_w.group(1), "workflow", b.get("id"), turn_w))
                        continue
                    if b.get("name") not in ("Task", "Agent"):
                        continue
                    prompt = (b.get("input") or {}).get("prompt")
                    feat = feature_slug(prompt) if isinstance(prompt, str) else None
                    if feat:
                        role_f = str((b.get("input") or {}).get("subagent_type") or "?").split(":")[-1]
                        # planning roles work on the plan (no REEF-TASK: line): planner, plan-reviewer, the hunter's plan
                        # pass, a general-purpose amendment agent; a REEF-TASK: dispatch is build
                        planning = not REEF_TASK.search(prompt)
                        dispatches.append((feat, b.get("id"), turn_of.get(rid, max(len(turn_pos), 1)), role_f, planning))
                        tm = REEF_TASK.search(prompt)
                        if tm:
                            tid_m = re.match(r"^(R?\d+)", os.path.basename(tm.group(1)))
                            role = str((b.get("input") or {}).get("subagent_type") or "?").split(":")[-1]
                            if tid_m:
                                task_dispatches.append((tid_m.group(1), role, b.get("id"), turn_of.get(rid, max(len(turn_pos), 1))))
            elif isinstance(content, str):
                if content.startswith("<task-notification>"):
                    for tid in NOTIFIED_ID.findall(content):
                        notified.setdefault(tid, pos)
            else:
                for b in content or []:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        returned.setdefault(b.get("tool_use_id"), pos)
    n = len(turn_pos)
    if not n:
        return []

    def result_turn(tid):
        pos = notified.get(tid, returned.get(tid))
        if pos is None:
            return n
        return next((i + 1 for i, p in enumerate(turn_pos) if p > pos), n)

    spans, roles_of, build_start = {}, {}, {}
    for feat, tid, turn, role_f, planning in dispatches:
        first, last, count = spans.get(feat, (turn, turn, 0))
        spans[feat] = (min(first, turn), max(last, turn, result_turn(tid)), count + 1)
        r = roles_of.setdefault(feat, {})
        r[role_f] = r.get(role_f, 0) + 1
        if not planning:
            build_start[feat] = min(build_start.get(feat, turn), turn)
    # 0.7 (workflow v2, phase 2): features run concurrently, so a span's growth over-counts — the turn both features
    # dispatch in is charged to both. `share` splits each turn's growth equally among the features active in it
    # (sums to at most the session's growth); `planning_share` is the part before the feature's first REEF-TASK dispatch.
    active = {}
    for feat, (first, last, _) in spans.items():
        for i in range(min(first, n), min(last, n)):
            active.setdefault(i, []).append(feat)
    share, planning_share = {}, {}
    for i, feats in active.items():
        g = max(0, turn_ctx[i] - turn_ctx[i - 1]) / len(feats)
        for feat in feats:
            share[feat] = share.get(feat, 0.0) + g
            if i < build_start.get(feat, n + 1):
                planning_share[feat] = planning_share.get(feat, 0.0) + g
    rows = []
    for feat, (first, last, count) in spans.items():
        first, last = min(first, n), min(last, n)
        lo, hi = turn_pos[first - 1], turn_pos[last - 1]
        b = sum(1 for p in boundary_pos if lo < p < hi)
        s = sum(1 for p in summary_pos if lo < p < hi)
        rows.append({"feature": feat, "first_turn": first, "last_turn": last,
                     "growth": sum(max(0, turn_ctx[i] - turn_ctx[i - 1]) for i in range(first, last)),
                     "share": int(round(share.get(feat, 0.0))), "planning_share": int(round(planning_share.get(feat, 0.0))),
                     "compactions": b if b else s, "turns": last - first + 1, "dispatches": count,
                     "roles": dict(sorted(roles_of.get(feat, {}).items()))})
    # 0.7: per task, the roles dispatched for it and the main-session growth over its span — where execution is
    # expensive (first real execution: one task, 43 orchestrator turns, 64k growth, and no way to say which role)
    tspans = {}
    for task, role, tid, turn in task_dispatches:
        first, last, roles = tspans.get(task, (turn, turn, {}))
        roles[role] = roles.get(role, 0) + 1
        tspans[task] = (min(first, turn), max(last, turn, result_turn(tid)), roles)
    tasks = []
    for task, (first, last, roles) in tspans.items():
        first, last = min(first, n), min(last, n)
        tasks.append({"task": task, "first_turn": first, "last_turn": last,
                      "growth": sum(max(0, turn_ctx[i] - turn_ctx[i - 1]) for i in range(first, last)),
                      "turns": last - first + 1, "roles": dict(sorted(roles.items()))})
    feature_rows.tasks = sorted(tasks, key=lambda r: (r["first_turn"], r["task"]))
    return sorted(rows, key=lambda r: (r["first_turn"], r["feature"]))


def subagent_paths(path):
    base = os.path.splitext(os.path.abspath(path))[0]
    return sorted(glob.glob(os.path.join(base, "subagents", "agent-*.jsonl")))


def fix_rounds(repo):
    """attempts: per feature from every done task file (flat tasks/done and feature folders), plus
    the journal's Attempts column when the table is there."""
    rounds = {}
    pats = ["tasks/done/*.md", "*/*/tasks/done/*.md", "reef/features/*/tasks/done/*.md"]
    for pat in pats:
        for p in glob.glob(os.path.join(repo, pat)):
            try:
                with open(p, encoding="utf-8") as f:
                    m = FENCE.match(f.read())
            except OSError:
                continue
            if not m:
                continue
            fm = dict(l.partition(":")[::2] for l in m.group(1).splitlines() if ":" in l)
            feat = fm.get("feature", "").strip()
            try:
                rounds[feat] = rounds.get(feat, 0) + int(fm.get("attempts", "0").strip() or 0)
            except ValueError:
                pass
    journal = 0
    for cand in ("docs/journal.md", "reef/journal.md", "docs/runlog.md"):
        p = os.path.join(repo, cand)
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    cells = table_cells(line)
                    if len(cells) >= 4 and cells[3].isdigit():
                        journal += int(cells[3])
            break
    return {"by_feature": rounds, "journal_attempts": journal}


def live_context(path):
    """The latest turn's context from the file TAIL (seek -256 KB): a 50 MB transcript is never parsed."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.seek(max(0, size - TAIL_BYTES))
        chunk = f.read()
    lines = chunk.split(b"\n")
    if size > TAIL_BYTES:
        lines = lines[1:]   # the first piece is a cut line
    for raw in reversed(lines):
        if not raw.strip():
            continue
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        if d.get("type") == "assistant" and (d.get("message") or {}).get("usage"):
            return ctx(d["message"]["usage"])
    return None


def render_md(rep, subs, rounds, rows=()):
    c, k = rep["context"], rep["cache"]
    out = [f"# reef-cost — {os.path.basename(rep['path'])}", "",
           f"- API turns: **{rep['turns']}** · compactions: **{rep['compactions']}** · models: {', '.join(rep['models']) or '?'}",
           f"- context per turn (tokens): mean {c['mean']:,} · p50 {c['p50']:,} · p90 {c['p90']:,} · max {c['max']:,}",
           f"- first-turn context (session start): **{rep['first_turn_context']:,}**",
           f"- cache: writes {k['writes']:,} · reads {k['reads']:,} · uncached input {k['uncached_input']:,} · output {k['output']:,}",
           "", "## Context share by category (chars/4, an estimate)", "", "| category | ~tokens | share |", "|---|---|---|"]
    total = sum(rep["categories"].values()) or 1
    for name, n in list(rep["categories"].items())[:12]:
        out.append(f"| {name} | {n:,} | {100 * n // total}% |")
    if rep.get("standing"):
        names = {"prompt_snapshot": "system prompt", "skill_listing": "skill list", "environment": "environment"}
        out += ["", "standing context, paid on every turn and never growth: " + " · ".join(
            f"{names.get(k, k)} ~{v['per_item']:,}" + (f" (recorded {v['items']}×)" if v["items"] > 1 else "")
            for k, v in sorted(rep["standing"].items(), key=lambda kv: -kv[1]["per_item"]))]
    if subs:
        out += ["", "## Sub-agents", "", "| agent | type | turns | first-turn ctx | max ctx | output |", "|---|---|---|---|---|---|"]
        for s in subs:
            out.append(f"| {os.path.basename(s['path'])[6:-6]} | {s['agent_type'] or '?'} | {s['turns']} | "
                       f"{s['first_turn_context']:,} | {s['context']['max']:,} | {s['cache']['output']:,} |")
    if rows:
        out += ["", "## Rows (main-session context per feature)", "",
                "share = the span's growth split equally among the features active in each turn (sums to the session); "
                "planning = the share before the feature's first REEF-TASK dispatch.", "",
                "| feature | turns | span growth | share | planning | compactions | dispatches |", "|---|---|---|---|---|---|---|"]
        out += [f"| {r['feature']} | {r['first_turn']}–{r['last_turn']} | {r['growth']:,} | {r['share']:,} | {r['planning_share']:,} | {r['compactions']} | "
                + (", ".join(f"{k} ×{v}" for k, v in r["roles"].items()) or str(r["dispatches"])) + " |" for r in rows]
    tasks = getattr(feature_rows, "tasks", [])
    if tasks:
        out += ["", "## Tasks (main-session growth per task, dispatches per role)", "",
                "| task | turns | growth | dispatches |", "|---|---|---|---|"]
        out += [f"| {x['task']} | {x['turns']} | {x['growth']:,} | " + ", ".join(f"{k} ×{v}" for k, v in x["roles"].items()) + " |" for x in tasks]
    if rounds is not None:
        out += ["", "## Fix rounds per feature (done tasks' attempts:)", ""]
        out += [f"- {f or '(no feature)'}: {n}" for f, n in sorted(rounds["by_feature"].items())] or ["- none recorded"]
        out.append(f"- journal Attempts column total: {rounds['journal_attempts']}")
    return "\n".join(out) + "\n"


COST_FILE = os.path.join(".reef", "cost", "tasks.json")
FEATURE_COST_FILE = os.path.join(".reef", "cost", "features.json")


def record_growth(path, repo):
    """Fold this transcript's per-task main-session growth into <repo>/.reef/cost/tasks.json, keyed by task then by
    transcript (a task that spans two sessions adds up; re-recording the same session replaces its number). The
    Stop hook calls it every turn; the close-out reads it (first full loop, 2026-10-17: the cost of a task was
    computed by hand from the transcript after the fact, and never reached the journal)."""
    rows = feature_rows(path)
    tasks = getattr(feature_rows, "tasks", []) or []
    key = os.path.splitext(os.path.basename(path))[0]
    fout = os.path.join(repo, FEATURE_COST_FILE)
    try:
        with open(fout, encoding="utf-8") as f:
            fstore = json.load(f)
    except (OSError, ValueError):
        fstore = {}
    if not isinstance(fstore, dict):
        fstore = {}
    for r in rows:
        fstore.setdefault(str(r["feature"]), {})[key] = {"share": int(r["share"]), "planning_share": int(r["planning_share"]),
                                                            "turns": int(r["turns"]), "roles": r["roles"]}
    if rows:
        os.makedirs(os.path.dirname(fout), exist_ok=True)
        with open(fout, "w", encoding="utf-8") as f:
            json.dump(fstore, f, indent=1, sort_keys=True)
    out = os.path.join(repo, COST_FILE)
    try:
        with open(out, encoding="utf-8") as f:
            store = json.load(f)
    except (OSError, ValueError):
        store = {}
    if not isinstance(store, dict):
        store = {}
    for x in tasks:
        entry = store.setdefault(str(x["task"]), {})
        entry[key] = {"growth": int(x["growth"]), "turns": int(x["turns"]), "roles": x["roles"]}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=1, sort_keys=True)
    return store


def feature_growth_of(repo, feature):
    try:
        with open(os.path.join(repo, FEATURE_COST_FILE), encoding="utf-8") as f:
            store = json.load(f)
    except (OSError, ValueError):
        return None
    sessions = store.get(str(feature)) if isinstance(store, dict) else None
    if not sessions:
        return None
    roles = {}
    for s in sessions.values():
        for k, v in (s.get("roles") or {}).items():
            roles[k] = roles.get(k, 0) + int(v)
    return {"share": sum(int(s.get("share", 0)) for s in sessions.values()),
            "planning": sum(int(s.get("planning_share", 0)) for s in sessions.values()), "sessions": len(sessions), "roles": roles}


def growth_of(repo, task):
    try:
        with open(os.path.join(repo, COST_FILE), encoding="utf-8") as f:
            store = json.load(f)
    except (OSError, ValueError):
        return None
    sessions = store.get(str(task)) if isinstance(store, dict) else None
    if not sessions:
        return None
    roles = {}
    for s in sessions.values():
        for k, v in (s.get("roles") or {}).items():
            roles[k] = roles.get(k, 0) + int(v)
    return {"growth": sum(int(s.get("growth", 0)) for s in sessions.values()), "sessions": len(sessions), "roles": roles}


# ---- v3 phase 1 (2026-10-25): the pipeline per merged row, from the repository's own history — the baseline every later
# phase is scored against. Nothing here writes; gh is used only when it reaches the forge, git is the fallback.
MERGE_SUBJECT = re.compile(r"\(#(\d+)\)\s*$|^Merge pull request #(\d+)")
# a commit is "process" when every path it touches is Reef's own: its folders, its scripts, the hooks, the instruction
# files, the queue, the journal — plus whatever .reef/config.json paths.* names (tasks, adr, glossary, runlog, queue, features)
PROCESS_ROOTS = (".reef/", ".githooks/", ".claude/", "scripts/reef-", "reef/", "docs/adr/", "docs/queue.md", "docs/journal.md",
                 "docs/runlog.md", "CLAUDE.md", "AGENTS.md", "HANDOFF.md")


def iso(s):
    """An aware datetime, or None; a date or a time without a zone is read as UTC (`--since 2026-10-20`)."""
    try:
        d = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)


def canon_id(x):
    """A task id as reef-graph names it on a branch: 007 -> 7, R01 -> R1."""
    x = str(x)
    if x.startswith("R") and x[1:].isdigit():
        return "R" + str(int(x[1:]))
    return str(int(x)) if x.isdigit() else x


def minutes(a, b):
    return None if a is None or b is None else int(round((b - a).total_seconds() / 60))


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    m = xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
    return int(m) if m == int(m) else m


def fmt_min(m):
    if m is None:
        return "–"
    m = int(m)
    return f"{m}m" if m < 60 else f"{m // 60}h{m % 60:02d}m"


def is_process(path, roots):
    for r in roots:
        if r.endswith("/") or r.endswith("-"):
            if path.startswith(r):
                return True
        elif path == r or path.startswith(r + "/"):
            return True
    return False


git_out = partial(_git_out, strip=False)


def forge_pr(repo, n, cache):
    """The forge's record of PR n through gh: created_at, merged_at, head ref, its commits and the first one's author
    date. None without gh, without a remote, or on any error — the caller falls back to git."""
    if n in cache:
        return cache[n]
    info = None
    if not cache.get("_down") and shutil.which("gh") and git_out(repo, "remote").strip():
        try:
            api = lambda path: json.loads(subprocess.run(["gh", "api", path], cwd=repo, capture_output=True, text=True, timeout=10).stdout)
            pr = api(f"repos/{{owner}}/{{repo}}/pulls/{n}")
            commits = api(f"repos/{{owner}}/{{repo}}/pulls/{n}/commits?per_page=250")
            if isinstance(pr, dict) and pr.get("number") == n and isinstance(commits, list):
                dates = [((c.get("commit") or {}).get("author") or {}).get("date") for c in commits if isinstance(c, dict)]
                info = {"created": pr.get("created_at"), "merged": pr.get("merged_at"), "head_ref": (pr.get("head") or {}).get("ref"),
                        "commits": [c.get("sha") for c in commits if isinstance(c, dict)], "first_commit": min((d for d in dates if d), default=None)}
        except Exception:
            info = None
        if info is None:
            cache["_down"] = True   # one failure says the forge is out of reach: git answers the rest of this run
    cache[n] = info
    return info


def pipeline_rows(repo, since):
    """{"since", "base", "rows": [...], "batch": {...}} — see the module docstring."""
    try:
        with open(os.path.join(repo, ".reef", "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    paths_cfg = cfg.get("paths") if isinstance(cfg.get("paths"), dict) else {}
    base = str((cfg.get("branches") or {}).get("base", "main") or "main")
    prefix = str((cfg.get("branches") or {}).get("feature_prefix", "feat/") or "feat/")
    features = str(paths_cfg.get("features", "reef/features") or "reef/features").strip("/")
    roots = list(PROCESS_ROOTS) + [str(v).strip("/") for v in paths_cfg.values() if isinstance(v, str) and v.strip("/")]
    try:
        with open(os.path.join(repo, ".reef", "cost", "features.json"), encoding="utf-8") as f:
            shares = json.load(f)
    except (OSError, ValueError):
        shares = {}
    runs = []
    try:
        with open(os.path.join(repo, ".reef", "ci-local", "runs.jsonl"), encoding="utf-8") as f:
            for line in f:
                try:
                    runs.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    commits = []   # (sha, date, subject, paths) on the base's first-parent line since `since`
    for chunk in git_out(repo, "log", "--first-parent", "-m", "--name-only", f"--since={since}", "--format=%x1e%H%x1f%cI%x1f%s", base).split("\x1e"):
        lines = chunk.strip("\n").splitlines()
        if not lines or "\x1f" not in lines[0]:
            continue
        sha, date, subj = lines[0].split("\x1f", 2)
        commits.append((sha, date, subj, [l for l in lines[1:] if l.strip()]))
    process = product = 0
    for _, _, _, cpaths in commits:
        if cpaths:
            if all(is_process(p, roots) for p in cpaths):
                process += 1
            else:
                product += 1
    rows, cache = [], {}
    for sha, date, subj, cpaths in commits:
        m = MERGE_SUBJECT.search(subj)
        if not m or subj.startswith("Revert"):
            continue
        n = int(m.group(1) or m.group(2))
        slug = next((p[len(features) + 1:].split("/")[0] for p in cpaths if p.startswith(features + "/") and "/" in p[len(features) + 1:]), None)
        pr = forge_pr(repo, n, cache)
        if not slug and pr and pr.get("head_ref"):
            ref = str(pr["head_ref"])
            slug = ref[len(prefix):] if ref.startswith(prefix) else ref
        slug = slug or f"pr-{n}"
        merged = iso(date)
        plan_at = iso(pr["first_commit"]) if pr and pr.get("first_commit") else None
        if plan_at is None:
            first = git_out(repo, "log", "--all", "--diff-filter=A", "--format=%aI", "--reverse", "--", f"{features}/{slug}").splitlines()
            plan_at = iso(first[0]) if first else None
        approved_at = None
        try:
            with open(os.path.join(repo, ".reef", "approvals", f"{slug}.json"), encoding="utf-8") as f:
                approved_at = iso(json.load(f).get("approved_at"))
        except (OSError, ValueError, AttributeError):
            pass
        pr_at = iso(pr["created"]) if pr and pr.get("created") else None
        tokens = sum(int(x.get("share", 0) or 0) for x in (shares.get(slug) or {}).values() if isinstance(x, dict))
        fdir = os.path.join(repo, features, slug)
        task_ids = {canon_id(os.path.basename(t).split("-")[0]) for t in glob.glob(os.path.join(fdir, "tasks", "*.md")) + glob.glob(os.path.join(fdir, "tasks", "done", "*.md"))}
        heads = set(pr["commits"]) if pr else set()
        if git_out(repo, "rev-parse", "-q", "--verify", f"refs/heads/{prefix}{slug}").strip():
            heads |= set(git_out(repo, "rev-list", f"{base}..{prefix}{slug}").split())

        def mine(rec):
            br = str(rec.get("branch") or "")
            return rec.get("head") in heads or br == prefix + slug or (br.startswith("task/") and canon_id(br[5:].split("-")[0]) in task_ids)
        suite_runs = sum(1 for rec in runs if rec.get("mode") == "full" and mine(rec))
        rollups = len(glob.glob(os.path.join(fdir, "tasks", "done", "R*.md")))
        for t in glob.glob(os.path.join(repo, "tasks", "done", "R*.md")):
            try:
                with open(t, encoding="utf-8") as f:
                    fm = FENCE.match(f.read())
                rollups += bool(fm and re.search(rf"^feature:[ \t]*{re.escape(slug)}[ \t]*$", fm.group(1), re.M))
            except OSError:
                pass
        names = re.compile(r"#%d\)|(?<![A-Za-z0-9_-])%s(?![A-Za-z0-9_-])" % (n, re.escape(slug)))
        reverts = sum(1 for _, _, s2, _ in commits if s2.startswith("Revert") and names.search(s2))
        rows.append({"feature": slug, "pr": n, "merge": sha, "plan_at": plan_at.isoformat() if plan_at else None,
                     "approved_at": approved_at.isoformat() if approved_at else None, "pr_at": pr_at.isoformat() if pr_at else None,
                     "merged_at": merged.isoformat() if merged else None,
                     "lead_min": minutes(plan_at, merged), "plan_to_approval_min": minutes(plan_at, approved_at),
                     "approval_to_merge_min": minutes(approved_at, merged), "pr_to_merge_min": minutes(pr_at, merged),
                     "tokens": tokens, "suite_runs": suite_runs, "rollups": rollups, "reverts": reverts})
    rows.reverse()   # oldest first
    since_dt = iso(since)
    fails = 0
    for p in glob.glob(os.path.join(repo, ".reef", "review", "security-*.json")):
        try:
            with open(p, encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError):
            continue
        at = iso(rec.get("recorded_at"))
        if rec.get("verdict") == "FAIL" and (since_dt is None or at is None or at >= since_dt):
            fails += 1
    # v3 phase 6 — the owner's questions per batch: footnotes added to the queue file in the window, the owner's against the
    # proxy's day decisions (`Mahmoud (proxy, day …)`); a night's proxy footnotes are neither
    queue_rel = str(paths_cfg.get("queue", "docs/queue.md") or "docs/queue.md").strip("/")
    marks = set()   # one count per footnote mark: an edited footnote (the owner's undo) is the same question, not a second
    for line in git_out(repo, "log", "--first-parent", base, f"--since={since}", "-p", "--format=", "--", queue_rel).splitlines():
        m = re.match(r"\+([\u2070-\u2079\u00b9\u00b2\u00b3]+) (.*)", line)
        if m and not re.search(r"\(proxy\b", m.group(2), re.I) and not re.match(r"row \d+ deleted \(rule 7\)", m.group(2)):
            marks.add(m.group(1))
    owner_q = len(marks)
    proxy_day = 0   # the proxy's day decisions: their record, not a grep of the label
    try:
        with open(os.path.join(repo, ".reef", "approvals", "day-decisions.jsonl"), encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                at = iso(rec.get("at"))
                if since_dt is None or at is None or at >= since_dt:
                    proxy_day += 1
    except OSError:
        pass
    batch = {"rows": len(rows), "process_commits": process, "product_commits": product, "security_fails": fails,
             "owner_questions": owner_q, "proxy_day_decisions": proxy_day,
             "rollups": sum(r["rollups"] for r in rows), "reverts": sum(r["reverts"] for r in rows),
             "lead_min_median": median(r["lead_min"] for r in rows),
             "approval_to_merge_min_median": median(r["approval_to_merge_min"] for r in rows),
             "tokens_median": median(r["tokens"] for r in rows if r["tokens"]),
             "suite_runs_median": median(r["suite_runs"] for r in rows)}
    batch["lead_min_median_text"] = fmt_min(batch["lead_min_median"])
    batch["approval_to_merge_min_median_text"] = fmt_min(batch["approval_to_merge_min_median"])
    return {"since": since, "base": base, "rows": rows, "batch": batch}


def render_rows_md(rep):
    b = rep["batch"]
    out = ["| row | PR | plan → merge | plan → approval | approval → merge | tokens | full-suite runs | rollups | reverts |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in rep["rows"]:
        out.append(f"| {r['feature']} | #{r['pr']} | {fmt_min(r['lead_min'])} | {fmt_min(r['plan_to_approval_min'])} | "
                   f"{fmt_min(r['approval_to_merge_min'])} | {r['tokens']:,} | {r['suite_runs']} | {r['rollups']} | {r['reverts']} |")
    tok = f"{int(b['tokens_median']):,}" if b["tokens_median"] is not None else "–"
    out.append("")
    out.append(f"rows {b['rows']} since {rep['since']} into {rep['base']} · process : product commits {b['process_commits']} : {b['product_commits']} · "
               f"security FAILs {b['security_fails']} · medians: plan → merge {fmt_min(b['lead_min_median'])}, approval → merge "
               f"{fmt_min(b['approval_to_merge_min_median'])}, tokens {tok}, full-suite runs {b['suite_runs_median'] if b['suite_runs_median'] is not None else '–'}")
    return "\n".join(out) + "\n"


def cmd_rows(argv):
    repo, since, fmt = ".", None, "text"
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--repo":
            repo = argv[i + 1]; i += 2
        elif a == "--since":
            since = argv[i + 1]; i += 2
        elif a == "--format":
            fmt = argv[i + 1]; i += 2
        else:
            die(f"rows: unknown option {a!r} (usage: rows [--repo DIR] [--since ISO] [--format text|md|json])")
    if since is None:
        since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # 2026-10-28: git fills a bare date's missing time with NOW (`--since=2026-10-28` at 14:00 means 14:00), so the morning's
    # merged row vanished from `rows --since <today>`; the window is one instant, read once here, UTC
    since_dt = iso(since)
    if since_dt is None:
        die(f"rows: --since {since!r} is not a date or an ISO time")
    since = since_dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rep = pipeline_rows(os.path.abspath(repo), since)
    if fmt == "json":
        print(json.dumps(rep, indent=1))
    elif fmt == "md":
        sys.stdout.write(render_rows_md(rep))
    else:
        for r in rep["rows"]:
            print(f"row feature={r['feature']} pr={r['pr']} lead_min={r['lead_min']} plan_to_approval_min={r['plan_to_approval_min']} "
                  f"approval_to_merge_min={r['approval_to_merge_min']} tokens={r['tokens']} suite_runs={r['suite_runs']} rollups={r['rollups']} reverts={r['reverts']}")
        b = rep["batch"]
        print(f"batch rows={b['rows']} process_commits={b['process_commits']} product_commits={b['product_commits']} security_fails={b['security_fails']} "
              f"lead_min_median={b['lead_min_median']} approval_to_merge_min_median={b['approval_to_merge_min_median']} tokens_median={b['tokens_median']} suite_runs_median={b['suite_runs_median']} "
              f"owner_questions={b['owner_questions']} proxy_day_decisions={b['proxy_day_decisions']}")
    return 0


def main(argv):
    if argv and argv[0] == "rows":
        return cmd_rows(argv[1:])
    if argv and argv[0] == "growth" and len(argv) >= 3 and argv[1] == "--feature":
        repo = argv[argv.index("--repo") + 1] if "--repo" in argv else "."
        g = feature_growth_of(repo, argv[2])
        if g is None:
            print(f"growth: no record for feature {argv[2]} (the Stop hook records after a turn with a dispatch naming it)")
            return 1
        print(f"share={g['share']} planning={g['planning']} sessions={g['sessions']} roles=" + ",".join(f"{k}×{v}" for k, v in sorted(g["roles"].items())))
        return 0
    if argv and argv[0] == "growth" and len(argv) >= 2:
        repo = argv[argv.index("--repo") + 1] if "--repo" in argv else "."
        g = growth_of(repo, argv[1])
        if g is None:
            print(f"growth: no record for task {argv[1]} (the Stop hook records after a turn with a dispatch)")
            return 1
        print(f"growth={g['growth']} sessions={g['sessions']} roles=" + ",".join(f"{k}×{v}" for k, v in sorted(g["roles"].items())))
        return 0
    path, repo, fmt, mode = None, None, "text", None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--repo":
            repo = argv[i + 1]; i += 2
        elif a == "--format":
            fmt = argv[i + 1]; i += 2
        elif a in ("--live", "--session-start", "--record"):
            mode = a; i += 1
        elif a.startswith("-"):
            die(f"unknown option {a!r}")
        else:
            path = a; i += 1
    if path is None and not sys.stdin.isatty():
        try:
            path = json.load(sys.stdin).get("transcript_path")
        except Exception:
            path = None
    if not path:   # 2026-11-01: a bare call said `transcript not found: None` and the session gave up on the numbers
        die("no transcript given — `reef-cost.py rows --since <ISO date>` is the pipeline per merged row, `growth --feature <slug>` a feature's share")
    if not os.path.isfile(path):
        die(f"transcript not found: {path!r}")
    if mode == "--live":
        n = live_context(path)
        if n is None:
            die("no assistant turn with usage in the transcript tail")
        print(f"context_tokens={n}")
        return 0
    if mode == "--record":
        store = record_growth(path, repo or ".")
        print(f"recorded {len(getattr(feature_rows, 'tasks', []) or [])} task(s) into {COST_FILE} ({len(store)} task(s) on file)")
        return 0
    if mode == "--session-start":
        rep = analyse(path)
        print(f"session_start_tokens={rep['first_turn_context']}")
        return 0
    rep = analyse(path)
    subs = [analyse(p) for p in subagent_paths(path)]
    rounds = fix_rounds(repo) if repo else None
    rows = feature_rows(path)
    if fmt == "json":
        print(json.dumps({"session": rep, "subagents": subs, "fix_rounds": rounds, "rows": rows,
                          "tasks": getattr(feature_rows, "tasks", [])}, indent=1))
    elif fmt == "md":
        sys.stdout.write(render_md(rep, subs, rounds, rows))
    else:
        c = rep["context"]
        print(f"turns={rep['turns']} compactions={rep['compactions']} ctx_mean={c['mean']} ctx_p50={c['p50']} "
              f"ctx_p90={c['p90']} ctx_max={c['max']} first_turn={rep['first_turn_context']} "
              f"cache_writes={rep['cache']['writes']} cache_reads={rep['cache']['reads']} subagents={len(subs)}")
        for r in rows:
            print(f"row feature={r['feature']} first_turn={r['first_turn']} last_turn={r['last_turn']} growth={r['growth']} "
                  f"compactions={r['compactions']} turns={r['turns']} dispatches={r['dispatches']} share={r['share']} planning={r['planning_share']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
