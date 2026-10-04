#!/usr/bin/env python3
"""Reef queue — the outer graph: one row per unit of work, status DERIVED from the task files.

Usage:
  reef-queue.py status  [--repo DIR]            every row: derived status, depends, batch
  reef-queue.py ready   [--repo DIR] [--all]    rows that can start now (current batch unless --all)
  reef-queue.py check   [--repo DIR]            consistency: every task's feature: has a row (or is
                                                archived); no row id repeats; depends resolve; the
                                                queue and journal stay under their word ceilings
  reef-queue.py adr-number [--repo DIR]         number every docs/adr/draft-*.md (on the integration
                                                branch, at merge) and rewrite `draft-<x>` citations

The queue (paths.queue, default docs/queue.md) holds NO status column: a row is `queued` (no task
file names it as `feature:`), `building` (some task not done), `done` (every task done), or
`archived` (its id is only in docs/queue-archive.md). The table is any markdown table whose header
holds `Id` and `Depends`; `Current batch: N` names the batch that may start.
Exit 0 ok · 1 check failed / nothing to do · 2 usage.
"""
import json
import os
import re
import subprocess
import sys

FENCE = re.compile(r"\A---\r?\n(.*?\r?\n)---\r?\n", re.S)
TASK_NAME_RE = re.compile(r"R?\d+-.*\.md$")


def die(msg, code=2):
    print(f"reef-queue: {msg}", file=sys.stderr)
    sys.exit(code)


def repo_root(start):
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=start, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else os.path.abspath(start)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def config(root):
    try:
        return json.loads(read(os.path.join(root, ".reef", "config.json")))
    except Exception:
        return {}


def parse_table(text):
    """Rows of the first markdown table whose header has Id and Depends, as dicts keyed by header."""
    lines = text.splitlines()
    rows, header = [], None
    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            if "Id" in cells and "Depends" in cells and i + 1 < len(lines) and re.match(r"^\s*\|\s*-", lines[i + 1]):
                header = cells
            continue
        if re.match(r"^\s*\|\s*-", line):
            continue
        if len(cells) < len(header):
            cells += [""] * (len(header) - len(cells))
        row = dict(zip(header, cells))
        if re.fullmatch(r"\d+[a-z]?", row.get("Id", "")):
            rows.append(row)
    return rows


def current_batch(text):
    m = re.search(r"^Current batch:[ \t]*(\S+)", text, re.M)
    return m.group(1) if m else None


def task_states(root, cfg):
    """feature -> list of status values, from tasks/ and tasks/done/."""
    tdir = os.path.join(root, cfg.get("paths", {}).get("tasks", "tasks"))
    states = {}
    for d in (tdir, os.path.join(tdir, "done")):
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not TASK_NAME_RE.match(f):
                continue
            m = FENCE.match(read(os.path.join(d, f)))
            if not m:
                continue
            fm = {}
            for line in m.group(1).splitlines():
                if line[:1] in (" ", "\t", "#") or ":" not in line:
                    continue
                k, _, v = line.partition(":")
                fm.setdefault(k.strip(), v.strip().strip('"'))
            states.setdefault(fm.get("feature", ""), []).append(fm.get("status", "pending"))
    return states


def load(root):
    cfg = config(root)
    qpath = os.path.join(root, cfg.get("paths", {}).get("queue", "docs/queue.md"))
    if not os.path.isfile(qpath):
        die(f"no queue at {os.path.relpath(qpath, root)} — run /reef-init", 1)
    text = read(qpath)
    apath = os.path.join(root, os.path.dirname(cfg.get("paths", {}).get("queue", "docs/queue.md")), "queue-archive.md")
    archived = {r["Id"] for r in parse_table(read(apath))} if os.path.isfile(apath) else set()
    rows = parse_table(text)
    states = task_states(root, cfg)
    for r in rows:
        st = states.get(r["Id"], [])
        r["_status"] = "queued" if not st else ("done" if all(s == "done" for s in st) else "building")
        r["_depends"] = [d for d in re.split(r"[,\s]+", r.get("Depends", "")) if d]
    return cfg, text, rows, archived, states


def is_done(dep, rows_by_id, archived):
    if dep in archived:
        return True
    r = rows_by_id.get(dep)
    return r is not None and r["_status"] == "done"


def cmd_status(root):
    _, _, rows, archived, _ = load(root)
    for r in rows:
        print(f"{r['Id']}\t{r['_status']}\tdepends={r['_depends']}\tbatch={r.get('Batch', '')}\t{r.get('Item', '')[:70]}")
    return 0


def cmd_ready(root, all_batches):
    _, text, rows, archived, _ = load(root)
    batch = current_batch(text)
    by_id = {r["Id"]: r for r in rows}
    ready = [r for r in rows if r["_status"] != "done"
             and all(is_done(d, by_id, archived) for d in r["_depends"])
             and (all_batches or batch is None or r.get("Batch", "") == batch)]
    planned = [r for r in ready if r.get("Source", "").lower() == "planned"]
    for r in (planned or ready):
        print(f"{r['Id']}\t{r['_status']}\t{r.get('Source', '')}\t{r.get('Item', '')[:70]}")
    if ready and not planned:
        print("note: no planned row is ready — only found rows; the loop stops and escalates rather than falling through", file=sys.stderr)
    return 0


def cmd_check(root):
    cfg, text, rows, archived, states = load(root)
    bad = []
    ids = [r["Id"] for r in rows]
    for i in set(ids):
        if ids.count(i) > 1:
            bad.append(f"row id {i} repeats")
        if i in archived:
            bad.append(f"row {i} is in the queue AND the archive")
    known = set(ids) | archived
    for r in rows:
        for d in r["_depends"]:
            if d not in known:
                bad.append(f"row {r['Id']} depends on unknown row {d}")
    for feat in states:
        if feat and feat not in known:
            bad.append(f"task file(s) with feature: {feat} have no queue row (and none in the archive)")
    w = cfg.get("writing", {})
    for name, path, key in (("queue", cfg.get("paths", {}).get("queue", "docs/queue.md"), "queue_words"),
                            ("journal", cfg.get("paths", {}).get("runlog", "docs/journal.md"), "journal_words")):
        p = os.path.join(root, path)
        cap = w.get(key)
        if cap and os.path.isfile(p) and len(read(p).split()) > int(cap):
            bad.append(f"{path} is over writing.{key} = {cap} words — archive the oldest entries")
    if bad:
        print("FAIL: queue consistency")
        for b in bad:
            print(f"  - {b}")
        return 1
    print(f"ok: {len(rows)} row(s), {len(archived)} archived, task features all accounted for")
    return 0


def cmd_adr_number(root):
    cfg = config(root)
    adr = os.path.join(root, cfg.get("paths", {}).get("adr", "docs/adr"))
    if not os.path.isdir(adr):
        die("no ADR directory", 1)
    files = sorted(os.listdir(adr))
    numbered = [int(m.group(1)) for f in files for m in [re.match(r"^(\d{4})-", f)] if m]
    nxt = (max(numbered) + 1) if numbered else 1
    drafts = [f for f in files if f.startswith("draft-") and f.endswith(".md")]
    if not drafts:
        print("nothing to number")
        return 1
    renames = {}
    for f in drafts:
        m = re.match(r"^draft-([^-]+)-(.*)\.md$", f) or re.match(r"^draft-(.*)\.md$", f)
        slug = m.group(2) if m and m.lastindex == 2 else m.group(1)
        cite = f[:-3]
        new = f"{nxt:04d}-{slug}.md"
        renames[cite] = (f, new, f"{nxt:04d}")
        nxt += 1
    for cite, (old, new, num) in renames.items():
        text = read(os.path.join(adr, old))
        text = re.sub(r"Status:[ \t]*Accepted[ \t]*\(number at merge\)", "Status: Accepted", text)
        with open(os.path.join(adr, new), "w", encoding="utf-8") as fh:
            fh.write(text)
        os.unlink(os.path.join(adr, old))
        print(f"{old} -> {new}")
    # rewrite citations everywhere under docs/ and tasks/ and the brief
    for d in (os.path.join(root, "docs"), os.path.join(root, cfg.get("paths", {}).get("tasks", "tasks")), root):
        for dirpath, dirs, names in os.walk(d):
            dirs[:] = [x for x in dirs if x not in (".git", ".reef", "node_modules")]
            for n in names:
                if not n.endswith(".md"):
                    continue
                p = os.path.join(dirpath, n)
                t = read(p)
                t2 = t
                for cite, (_, _, num) in renames.items():
                    t2 = re.sub(r"\b" + re.escape(cite) + r"\b", f"ADR {num}", t2)
                if t2 != t:
                    with open(p, "w", encoding="utf-8") as fh:
                        fh.write(t2)
            if d == root:
                break
    return 0


def main(argv):
    repo = "."
    if "--repo" in argv:
        i = argv.index("--repo")
        repo = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    root = repo_root(repo)
    if not argv:
        die("usage: reef-queue.py status|ready [--all]|check|adr-number [--repo DIR]")
    cmd = argv[0]
    if cmd == "status":
        return cmd_status(root)
    if cmd == "ready":
        return cmd_ready(root, "--all" in argv)
    if cmd == "check":
        return cmd_check(root)
    if cmd == "adr-number":
        return cmd_adr_number(root)
    die(f"unknown command {cmd!r}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
