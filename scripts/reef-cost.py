#!/usr/bin/env python3
# CLASS: code
"""Reef cost — what a session cost, from the Claude Code transcript (stdlib only).
Usage: reef-cost.py [<transcript.jsonl>] [--repo DIR] [--format text|md|json] | --session-start | --live
       reef-cost.py <transcript.jsonl> --record [--repo DIR]   (0.7) fold this session's per-task growth into .reef/cost/tasks.json
       reef-cost.py growth <task-id> [--repo DIR]             (0.7) the task's orchestrator growth so far, across sessions
       (cat hook-payload.json | reef-cost.py --live  reads transcript_path from the payload)
Turns = one per requestId; context = input + cache writes + cache reads; a compaction counts once (boundary record,
else summary record); --live reads the last 256 KB only. Rows: per feature dispatched through Task/Agent
(REEF-TASK:/REEF-FEATURE:), main-session growth = sum of positive context deltas over its span. Exit 0; 2 on a missing transcript. See README "Measured".
"""
import glob
import json
import os
import re
import sys

TAIL_BYTES = 256 * 1024
FENCE = re.compile(r"\A---\r?\n(.*?\r?\n)---\r?\n", re.S)
REEF_TASK = re.compile(r"^REEF-TASK:[ \t]*(.+?)[ \t\r]*$", re.M)      # the guard's own regexes
REEF_FEATURE = re.compile(r"^REEF-FEATURE:[ \t]*(\S+)", re.M)
NOTIFIED_ID = re.compile(r"<tool-use-id>\s*([^<\s]+)\s*</tool-use-id>")


def die(msg):
    print(f"reef-cost: {msg}", file=sys.stderr)
    sys.exit(2)


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


def analyse(path):
    """One transcript -> dict. Turns are keyed by requestId (every content block of one API call
    repeats the same usage), so a 3-block reply is ONE turn."""
    turns, seen, tool_names, cats = [], {}, {}, {}
    boundaries = summaries = 0
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
                k = f"attachment:{akind}"
                cats[k] = cats.get(k, 0) + est_tokens(d.get("rendered") or d.get("attachment"))
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
    dispatches = []                     # (feature, tool_use id, dispatch turn)
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
                    if not (isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in ("Task", "Agent")):
                        continue
                    prompt = (b.get("input") or {}).get("prompt")
                    feat = feature_slug(prompt) if isinstance(prompt, str) else None
                    if feat:
                        dispatches.append((feat, b.get("id"), turn_of.get(rid, max(len(turn_pos), 1))))
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

    spans = {}
    for feat, tid, turn in dispatches:
        first, last, count = spans.get(feat, (turn, turn, 0))
        spans[feat] = (min(first, turn), max(last, turn, result_turn(tid)), count + 1)
    rows = []
    for feat, (first, last, count) in spans.items():
        first, last = min(first, n), min(last, n)
        lo, hi = turn_pos[first - 1], turn_pos[last - 1]
        b = sum(1 for p in boundary_pos if lo < p < hi)
        s = sum(1 for p in summary_pos if lo < p < hi)
        rows.append({"feature": feat, "first_turn": first, "last_turn": last,
                     "growth": sum(max(0, turn_ctx[i] - turn_ctx[i - 1]) for i in range(first, last)),
                     "compactions": b if b else s, "turns": last - first + 1, "dispatches": count})
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
                    cells = [c.strip() for c in line.strip().strip("|").split("|")]
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
    if subs:
        out += ["", "## Sub-agents", "", "| agent | type | turns | first-turn ctx | max ctx | output |", "|---|---|---|---|---|---|"]
        for s in subs:
            out.append(f"| {os.path.basename(s['path'])[6:-6]} | {s['agent_type'] or '?'} | {s['turns']} | "
                       f"{s['first_turn_context']:,} | {s['context']['max']:,} | {s['cache']['output']:,} |")
    if rows:
        out += ["", "## Rows (main-session context per feature)", "",
                "| feature | first turn | last turn | growth | compactions | turns | dispatches |", "|---|---|---|---|---|---|---|"]
        out += [f"| {r['feature']} | {r['first_turn']} | {r['last_turn']} | {r['growth']:,} | {r['compactions']} | "
                f"{r['turns']} | {r['dispatches']} |" for r in rows]
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


def record_growth(path, repo):
    """Fold this transcript's per-task main-session growth into <repo>/.reef/cost/tasks.json, keyed by task then by
    transcript (a task that spans two sessions adds up; re-recording the same session replaces its number). The
    Stop hook calls it every turn; the close-out reads it (first full loop, 2026-10-17: the cost of a task was
    computed by hand from the transcript after the fact, and never reached the journal)."""
    feature_rows(path)
    tasks = getattr(feature_rows, "tasks", []) or []
    out = os.path.join(repo, COST_FILE)
    try:
        with open(out, encoding="utf-8") as f:
            store = json.load(f)
    except (OSError, ValueError):
        store = {}
    if not isinstance(store, dict):
        store = {}
    key = os.path.splitext(os.path.basename(path))[0]
    for x in tasks:
        entry = store.setdefault(str(x["task"]), {})
        entry[key] = {"growth": int(x["growth"]), "turns": int(x["turns"]), "roles": x["roles"]}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=1, sort_keys=True)
    return store


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


def main(argv):
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
    if not path or not os.path.isfile(path):
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
                  f"compactions={r['compactions']} turns={r['turns']} dispatches={r['dispatches']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
