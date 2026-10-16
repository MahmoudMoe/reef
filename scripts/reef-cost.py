#!/usr/bin/env python3
# CLASS: code
"""Reef cost — what a session cost, from the Claude Code transcript (stdlib only).
Usage: reef-cost.py [<transcript.jsonl>] [--repo DIR] [--format text|md|json] | --session-start | --live
       (cat hook-payload.json | reef-cost.py --live  reads transcript_path from the payload)
Turns = one per requestId; context = input + cache writes + cache reads; a compaction counts once (boundary record,
else summary record); --live reads the last 256 KB only. Exit 0; 2 on a missing transcript. See README "Measured".
"""
import glob
import json
import os
import re
import sys

TAIL_BYTES = 256 * 1024
FENCE = re.compile(r"\A---\r?\n(.*?\r?\n)---\r?\n", re.S)


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
                cats["attachment"] = cats.get("attachment", 0) + est_tokens(d.get("rendered") or d.get("attachment"))
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


def render_md(rep, subs, rounds):
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
    if rounds is not None:
        out += ["", "## Fix rounds per feature (done tasks' attempts:)", ""]
        out += [f"- {f or '(no feature)'}: {n}" for f, n in sorted(rounds["by_feature"].items())] or ["- none recorded"]
        out.append(f"- journal Attempts column total: {rounds['journal_attempts']}")
    return "\n".join(out) + "\n"


def main(argv):
    path, repo, fmt, mode = None, None, "text", None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--repo":
            repo = argv[i + 1]; i += 2
        elif a == "--format":
            fmt = argv[i + 1]; i += 2
        elif a in ("--live", "--session-start"):
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
    if mode == "--session-start":
        rep = analyse(path)
        print(f"session_start_tokens={rep['first_turn_context']}")
        return 0
    rep = analyse(path)
    subs = [analyse(p) for p in subagent_paths(path)]
    rounds = fix_rounds(repo) if repo else None
    if fmt == "json":
        print(json.dumps({"session": rep, "subagents": subs, "fix_rounds": rounds}, indent=1))
    elif fmt == "md":
        sys.stdout.write(render_md(rep, subs, rounds))
    else:
        c = rep["context"]
        print(f"turns={rep['turns']} compactions={rep['compactions']} ctx_mean={c['mean']} ctx_p50={c['p50']} "
              f"ctx_p90={c['p90']} ctx_max={c['max']} first_turn={rep['first_turn_context']} "
              f"cache_writes={rep['cache']['writes']} cache_reads={rep['cache']['reads']} subagents={len(subs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
