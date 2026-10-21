#!/usr/bin/env python3
# CLASS: code
"""Reef queue — the outer graph: one row per unit of work, status DERIVED from the task files.

Usage:
  reef-queue.py status  [--repo DIR]            every row: derived status, depends, batch
  reef-queue.py ready   [--repo DIR] [--all]    rows that can start now (current batch unless --all)
  reef-queue.py check   [--repo DIR]            consistency: every task's feature: has a row (or is
                                                archived); no row id repeats; depends resolve; the
                                                queue and journal stay under their word ceilings
  reef-queue.py adr-number [--repo DIR]         number every draft-*.md ADR (on the integration branch, at
                                                merge) in ONE global sequence across reef/architecture/adr/,
                                                every feature folder's adr/ and the legacy paths.adr, and
                                                rewrite `draft-<x>` citations
  reef-queue.py footnote "<text>" [--row ID] [--repo DIR]   (0.7) append the next footnote (one sequence across queue + archive), dated;
                                                 --row puts its mark on that row's Item; prints the mark
  reef-queue.py add-row --item "<text>" [--depends "1, 2"] [--source planned|found] [--batch N] [--admitted "<ground>"]
                                                 (0.7) the next id, in its batch's table (found: next batch by default); prints the id
  reef-queue.py set-depends ID "<ids>" [--repo DIR]        (0.7) replace a row's Depends cell
  reef-queue.py triage [--repo DIR] [--count]              (0.7) rule 7: found rows still queued two batches after they
                                                 entered, grouped by module, with the three outcomes as ONE owner
                                                 question; the open found vs planned count; --count prints one line
  reef-queue.py set-batch ID N [--repo DIR]                (0.7) move a row to batch N (a promotion; footnote the reason)
  reef-queue.py drop-row ID --reason "<text>" [--repo DIR] (0.7) delete a queued row (rule 7) and record the reason as a footnote
  reef-queue.py index [--repo DIR]              (0.6) regenerate <paths.features>/README.md: feature, row, batch,
                                                status, task counts, ADRs — never hand-edited
  `check` also validates (0.6) every feature folder's slug (2-5 kebab-case words, no bare number, no
  generic word) and the structure: a process document outside the layout fails.

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
SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+){1,4}$")
GENERIC_SLUGS = {"misc", "fixes", "feature", "update", "stuff", "changes", "work", "tasks", "new", "todo", "wip"}
FOLDER_FILE = re.compile(r"^(SPEC\.md|specs/[^/]+\.md|adr/[^/]+\.md|tasks/[^/]+\.md|tasks/done/[^/]+\.md)$")


def slug_error(slug):
    if not SLUG_RE.match(slug):
        return f"feature slug {slug!r} is not 2-5 kebab-case words"
    if all(w.isdigit() for w in slug.split("-")) or any(w in GENERIC_SLUGS for w in slug.split("-")):
        return f"feature slug {slug!r} is a number or a generic word"
    return None


def features_dir(root, cfg):
    return os.path.join(root, cfg.get("paths", {}).get("features", "reef/features"))


def feature_folders(root, cfg):
    fd = features_dir(root, cfg)
    return {s: os.path.join(fd, s) for s in sorted(os.listdir(fd)) if os.path.isdir(os.path.join(fd, s))} if os.path.isdir(fd) else {}


def structure_errors(root, cfg):
    """0.6 layout rules: a feature folder holds SPEC.md, specs/, adr/, tasks/ and nothing else; nothing but
    README.md sits directly under the features dir; a slug is descriptive."""
    bad = []
    fd = features_dir(root, cfg)
    for slug, fdir in feature_folders(root, cfg).items():
        e = slug_error(slug)
        if e:
            bad.append(e)
        if not os.path.isfile(os.path.join(fdir, "SPEC.md")):
            bad.append(f"{os.path.relpath(fdir, root)}: no SPEC.md")
        for dp, dn, fn in os.walk(fdir):
            dn[:] = [x for x in dn if not x.startswith(".")]
            for f in fn:
                rel = os.path.relpath(os.path.join(dp, f), fdir).replace(os.sep, "/")
                if not f.startswith(".") and not FOLDER_FILE.match(rel):
                    bad.append(f"{os.path.relpath(fdir, root)}/{rel} does not belong in a feature folder")
    if os.path.isdir(fd):
        for f in os.listdir(fd):
            if os.path.isfile(os.path.join(fd, f)) and f != "README.md":
                bad.append(f"{os.path.relpath(fd, root)}/{f}: a file outside any feature folder")
    return bad


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
    # `Current batch: 2²⁶` — the owner's footnote marker rides on the line (first contact, 2026-10-17: read as batch "2²⁶")
    m = re.search(r"^Current batch:[ \t]*(\d+)", text, re.M)
    return m.group(1) if m else None


def task_states(root, cfg):
    """feature -> list of status values, from tasks/ and tasks/done/."""
    tdir = os.path.join(root, cfg.get("paths", {}).get("tasks", "tasks"))
    states = {}
    dirs = [tdir, os.path.join(tdir, "done")]
    for fdir in feature_folders(root, cfg).values():
        dirs += [os.path.join(fdir, "tasks"), os.path.join(fdir, "tasks", "done")]
    for d in dirs:
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
    # 0.6: a feature folder's SPEC.md `Row: <id>` links the slug to its queue row — the row's status is derived
    # from the folder's tasks; the slug itself then needs no row of its own
    for slug, fdir in feature_folders(root, cfg).items():
        spec = os.path.join(fdir, "SPEC.md")
        if os.path.isfile(spec):
            m = re.search(r"^Row:\s*(\S+)", read(spec), re.M)
            if m and slug in states:
                states.setdefault(m.group(1), []).extend(states.pop(slug))
            elif m:
                states.setdefault(m.group(1), [])
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


SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
UNSUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
MARK = re.compile(r"^([⁰¹²³⁴⁵⁶⁷⁸⁹]+) ", re.M)


def queue_paths(root):
    cfg = config(root)
    q = os.path.join(root, cfg.get("paths", {}).get("queue", "docs/queue.md"))
    return cfg, q, os.path.join(os.path.dirname(q), "queue-archive.md")


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def cmd_footnote(root, text, row_id):
    """The owner's decision as the next footnote, one sequence across the queue and its archive, dated today. These
    were hand-written by the orchestrator as inline Python (first full loop, 2026-10-17: `assistant:tool_use` was the
    largest Reef-attributable share of the session, 15%); one line in, the shape guaranteed."""
    _, qpath, apath = queue_paths(root)
    if not os.path.isfile(qpath):
        die(f"no queue at {os.path.relpath(qpath, root)}", 1)
    q = read(qpath)
    marks = [int(m.translate(UNSUP)) for m in MARK.findall(q)]
    if os.path.isfile(apath):
        marks += [int(m.translate(UNSUP)) for m in MARK.findall(read(apath))]
    n = max(marks, default=0) + 1
    mark = str(n).translate(SUP)
    import datetime
    text = text.strip()
    # a decision already dated by its author keeps one date (night 2026-10-21: ⁵⁴ read "(2026-10-21) (2026-10-21)")
    line = f"{mark} {text}" + ("" if re.search(r"\(\d{4}-\d{2}-\d{2}\)$", text) else f" ({datetime.date.today().isoformat()})")
    if "## Footnotes" in q:
        head, _, tail = q.partition("## Footnotes")
        tail = tail.rstrip("\n") + "\n" + line + "\n"
        q = head + "## Footnotes" + tail
    else:
        q = q.rstrip("\n") + "\n\n## Footnotes\n" + line + "\n"
    if row_id:
        pat = re.compile(rf"^(\|\s*{re.escape(row_id)}\s*\|\s*)(.*?)(\s*\|)", re.M)
        m = pat.search(q)
        if not m:
            die(f"no row {row_id} in the queue", 1)
        q = q[:m.start()] + m.group(1) + m.group(2).rstrip() + mark + m.group(3) + q[m.end():]
    write_text(qpath, q)
    print(mark)
    return 0


def cmd_add_row(root, item, depends, source, batch, admitted):
    _, qpath, apath = queue_paths(root)
    q = read(qpath)
    ids = [int(r["Id"]) for r in parse_table(q) if r["Id"].isdigit()]
    if os.path.isfile(apath):
        ids += [int(r["Id"]) for r in parse_table(read(apath)) if r["Id"].isdigit()]
    new_id = max(ids, default=0) + 1
    cur = current_batch(q) or "1"
    if batch is None:
        batch = cur if source == "planned" or admitted else str(int(cur) + 1)   # rule 6: found work enters the next batch
    adm = admitted.strip()
    row = f"| {new_id} | {item.strip()} | {depends.strip()} | {source} | {batch} | {adm + ' ' if adm else ''}|"
    sec = re.search(rf"^## Batch {re.escape(str(batch))}\s*$(.*?)(?=^## |\Z)", q, re.M | re.S)
    if sec:
        body = sec.group(1).rstrip("\n")
        q = q[:sec.start(1)] + body + "\n" + row + "\n\n" + q[sec.end(1):]
    elif re.search(r"^## Batch \d+", q, re.M):
        block = f"## Batch {batch}\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n{row}\n\n"
        if "## Footnotes" in q:
            i = q.index("## Footnotes")
            q = q[:i] + block + q[i:]
        else:
            q = q.rstrip("\n") + "\n\n" + block
    else:
        # a flat queue (one table, no batch sections): append to the table
        lines = q.splitlines()
        last = max(i for i, l in enumerate(lines) if l.strip().startswith("|"))
        lines.insert(last + 1, row)
        q = "\n".join(lines) + "\n"
    write_text(qpath, q)
    print(new_id)
    return 0


def cmd_set_depends(root, row_id, depends):
    _, qpath, _ = queue_paths(root)
    q = read(qpath)
    pat = re.compile(rf"^(\|\s*{re.escape(row_id)}\s*\|[^|\n]*\|)([^|\n]*)(\|)", re.M)
    m = pat.search(q)
    if not m:
        die(f"no row {row_id} in the queue", 1)
    q = q[:m.start()] + m.group(1) + f" {depends.strip()} " + m.group(3) + q[m.end():]
    write_text(qpath, q)
    print(f"{row_id}\tdepends={depends.strip()}")
    return 0


PATH_RE = re.compile(r"(?<![\w/])((?:[\w.-]+/)+[\w.-]+|[\w-]+\.(?:ts|tsx|js|mjs|mts|py|md|json|yaml|yml|toml|sh|css|sql))")


def module_of(item):
    """The module a found row names: the first path in its Item, cut to two segments (`src/lib/x.ts` → `src/lib`);
    a bare file keeps its name; nothing path-like → `general`."""
    m = PATH_RE.search(item)
    if not m:
        return "general"
    parts = [p for p in m.group(1).split("/") if p]
    return "/".join(parts[:2]) if len(parts) > 1 else parts[0]


def triage_rows(rows, text):
    """Rule 7's set: `found` rows with no task file yet, whose batch is two or more behind the current one."""
    cur = current_batch(text)
    stale, open_found, open_planned = [], [], []
    for r in rows:
        if r["_status"] == "done":
            continue
        src = (r.get("Source") or "").strip().lower()
        (open_found if src == "found" else open_planned).append(r)
        b = re.match(r"\d+", r.get("Batch", "") or "")
        if src == "found" and r["_status"] == "queued" and cur and b and int(cur) - int(b.group()) >= 2:
            stale.append(r)
    return stale, open_found, open_planned


def cmd_triage(root, count_only):
    """Found-row triage as a command (usability plan B5). The first full loop had 18 of 26 open rows `found` and no
    moment that asked about them; rule 7 says a found row untouched after two batches is promoted once with a reason,
    merged into a design row, or deleted, and deletion is a first-class outcome. Prints the owner's ONE question."""
    _, text, rows, archived, _ = load(root)
    stale, open_found, open_planned = triage_rows(rows, text)
    cur = current_batch(text) or "?"
    head = f"triage: batch {cur} · open found {len(open_found)} vs planned {len(open_planned)} · stale found (rule 7): {len(stale)}"
    if count_only:
        print(head)
        return 0 if not stale else 1
    print(head)
    if len(open_found) > len(open_planned):
        print("  found rows outnumber planned ones: the roadmap is behind its findings (plan measure: found ≤ planned at batch start)")
    if not stale:
        print("  nothing to triage")
        return 0
    groups = {}
    for r in stale:
        groups.setdefault(module_of(r.get("Item", "")), []).append(r)
    print("\nONE owner question (AskUserQuestion, one entry per row; his words go to a footnote):")
    for mod in sorted(groups):
        print(f"\n## {mod}")
        for r in groups[mod]:
            item = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹ ]+$", "", r.get("Item", "")).strip()
            print(f"- row {r['Id']} (entered batch {r.get('Batch', '?')}, depends {', '.join(r['_depends']) or '-'}): {item[:140]}")
            print(f"    Promote → set-batch {r['Id']} {cur} + footnote --row {r['Id']} \"promoted: <reason>\"")
            print(f"    Merge into design row <id> → footnote --row <id> \"absorbs row {r['Id']}: …\" + drop-row {r['Id']} --reason \"merged into <id>\"")
            print(f"    Delete → drop-row {r['Id']} --reason \"<why it no longer matters>\"   (first-class outcome)")
    return 1


def cmd_set_batch(root, row_id, batch):
    _, qpath, _ = queue_paths(root)
    q = read(qpath)
    if not re.fullmatch(r"\d+", batch or ""):
        die("batch is a number")
    # the row line: Id | Item | Depends | Source | Batch | Admitted
    pat = re.compile(rf"^(\|\s*{re.escape(row_id)}\s*\|(?:[^|\n]*\|){{3}})([^|\n]*)(\|)", re.M)
    m = pat.search(q)
    if not m:
        die(f"no row {row_id} in the queue", 1)
    line_start = q.rfind("\n", 0, m.start()) + 1
    line_end = q.find("\n", m.end())
    line = q[line_start:line_end]
    new_line = line[:m.start(2) - line_start] + f" {batch} " + line[m.end(2) - line_start:]
    q = q[:line_start] + q[line_end + 1:]   # take the row line out of its table (no blank line left: it would split the table) …
    sec = re.search(rf"^## Batch {re.escape(batch)}\s*$(.*?)(?=^## |\Z)", q, re.M | re.S)
    if sec:
        body = sec.group(1).rstrip("\n")   # … and put it under its new batch heading
        q = q[:sec.start(1)] + body + "\n" + new_line + "\n\n" + q[sec.end(1):]
    else:
        q = q[:line_start] + new_line + "\n" + q[line_start:]   # a flat queue: the cell changes in place
    write_text(qpath, q)
    print(f"{row_id}\tbatch={batch}")
    return 0


def cmd_drop_row(root, row_id, reason):
    _, qpath, _ = queue_paths(root)
    _, text, rows, archived, states = load(root)
    r = next((x for x in rows if x["Id"] == row_id), None)
    if r is None:
        die(f"no row {row_id} in the queue", 1)
    if r["_status"] != "queued":
        die(f"row {row_id} is {r['_status']}: only a queued row (no task file) is dropped; a built one is archived by the close-out", 1)
    if not (reason or "").strip():
        die("--reason is the ground, recorded as a footnote (rule 7: deletion is a first-class outcome)")
    q = read(qpath)
    lines = q.splitlines()
    keep = [l for l in lines if not re.match(rf"^\|\s*{re.escape(row_id)}\s*\|", l)]
    write_text(qpath, "\n".join(keep) + "\n")
    cmd_footnote(root, f"row {row_id} deleted (rule 7): {reason.strip()} — was: {r.get('Item', '').strip()[:120]}", None)
    return 0


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
    bad += structure_errors(root, cfg)
    # 0.6 feature folders: Row: in SPEC.md must be a known row; the slug must be the row's feature name
    for slug, fdir in feature_folders(root, cfg).items():
        spec = os.path.join(fdir, "SPEC.md")
        if os.path.isfile(spec):
            m = re.search(r"^Row:\s*(\S+)", read(spec), re.M)
            if m and m.group(1) not in known:
                bad.append(f"{os.path.relpath(spec, root)}: Row: {m.group(1)} is not a queue row (nor archived)")
    # 0.6: a journal row's per-AC statuses come from a closed set; a non-achieved one says what is missing
    jpath = os.path.join(root, cfg.get("paths", {}).get("runlog", "docs/journal.md"))
    is06 = os.path.isfile(os.path.join(root, ".reef", "version"))
    if os.path.isfile(jpath):
        # the closed set applies to the table's ACs column, not to prose: "AC-9 and AC-13 were probed" in a Verified
        # paragraph is a sentence, not a status (first contact, 2026-10-17: three honest journal entries were reworded
        # to get past this check)
        ac_col = None
        for line in read(jpath).splitlines():
            if not line.lstrip().startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if "ACs" in cells:
                ac_col = cells.index("ACs")
                continue
            if ac_col is None or len(cells) <= ac_col or re.fullmatch(r"-+", cells[ac_col] or "-"):
                continue
            for m in re.finditer(r"\bAC-?\d+\s+([a-z-]+)", cells[ac_col]):
                st = m.group(1)
                if st not in ("not-verified", "partially-verified", "achieved", "contradicted"):
                    msg = f"journal: AC status {st!r} is not one of not-verified | partially-verified | achieved | contradicted"
                    (bad.append if is06 else lambda x: print(f"warning: {x}"))(msg)
                elif st != "achieved" and not ("Missing:" in line and "Next:" in line):
                    msg = f"journal: a {st} criterion needs `Missing: … Next: …` on its row: {line[:60]!r}"
                    (bad.append if is06 else lambda x: print(f"warning: {x}"))(msg)
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


def adr_dirs(root, cfg):
    """Every ADR location: the legacy paths.adr, reef/architecture/adr (project-wide) and each feature's adr/."""
    out = [os.path.join(root, cfg.get("paths", {}).get("adr", "docs/adr")), os.path.join(root, "reef", "architecture", "adr")]
    out += [os.path.join(f, "adr") for f in feature_folders(root, cfg).values()]
    seen, uniq = set(), []
    for d in out:
        if os.path.isdir(d) and os.path.abspath(d) not in seen:
            seen.add(os.path.abspath(d))
            uniq.append(d)
    return uniq


def cmd_adr_number(root):
    cfg = config(root)
    dirs = adr_dirs(root, cfg)
    if not dirs:
        die("no ADR directory", 1)
    numbered = [int(m.group(1)) for d in dirs for f in os.listdir(d) for m in [re.match(r"^(\d{4})-", f)] if m]
    nxt = (max(numbered) + 1) if numbered else 1      # ONE global sequence across every location
    drafts = sorted((d, f) for d in dirs for f in os.listdir(d) if f.startswith("draft-") and f.endswith(".md"))
    if not drafts:
        print("nothing to number")
        return 1
    renames = {}
    for d, f in drafts:
        m = re.match(r"^draft-([^-]+)-(.*)\.md$", f) or re.match(r"^draft-(.*)\.md$", f)
        slug = m.group(2) if m and m.lastindex == 2 else m.group(1)
        cite = f[:-3]
        new = f"{nxt:04d}-{slug}.md"
        renames[cite] = (os.path.join(d, f), os.path.join(d, new), f"{nxt:04d}")
        nxt += 1
    for cite, (old, new, num) in renames.items():
        text = read(old)
        text = re.sub(r"Status:[ \t]*Accepted[ \t]*\(number at merge\)", "Status: Accepted", text)
        with open(new, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.unlink(old)
        print(f"{os.path.relpath(old, root)} -> {os.path.relpath(new, root)}")
    # rewrite citations everywhere under docs/ and tasks/ and the brief
    for d in (os.path.join(root, "docs"), os.path.join(root, "reef"), os.path.join(root, cfg.get("paths", {}).get("tasks", "tasks")), root):
        for dirpath, dirs, names in os.walk(d):
            dirs[:] = [x for x in dirs if x not in (".git", ".reef", "node_modules")]
            for n in names:
                if not n.endswith(".md"):
                    continue
                p = os.path.join(dirpath, n)
                t = read(p)
                t2 = t
                for cite, (_, new, num) in renames.items():
                    # the ADR's own title says `ADR draft-x` already: never "ADR ADR 0001" (0.7 dogfood)
                    t2 = re.sub(r"\bADR[ \t]+" + re.escape(cite) + r"\b", f"ADR {num}", t2)
                    # a path citation (`adr/draft-x.md`) must keep pointing at a file that exists
                    t2 = re.sub(re.escape(cite) + r"\.md\b", os.path.basename(new), t2)
                    t2 = re.sub(r"\b" + re.escape(cite) + r"\b", f"ADR {num}", t2)
                if t2 != t:
                    with open(p, "w", encoding="utf-8") as fh:
                        fh.write(t2)
            if d == root:
                break
    return 0


def cmd_index(root):
    """<paths.features>/README.md: one page over every feature folder — generated, never hand-edited."""
    cfg = config(root)
    folders = feature_folders(root, cfg)
    fd = features_dir(root, cfg)
    if not os.path.isdir(fd):
        die(f"no features directory at {os.path.relpath(fd, root)}", 1)
    rows_by_id = {}
    try:
        _, _, rows, archived, states = load(root)
        rows_by_id = {r["Id"]: r for r in rows}
    except SystemExit:
        archived, states = set(), task_states(root, cfg)
    lines = ["# Features", "", "Generated by `python3 scripts/reef-queue.py index` — never hand-edited. One folder per queue row: "
             "`SPEC.md` (intent, FR/SC keys), `specs/` (big features), `adr/` (the feature's decisions), `tasks/` (the plan).", "",
             "| Feature | Row | Batch | Status | Tasks (done/total) | ADRs |", "|---|---|---|---|---|---|"]
    for slug, fdir in folders.items():
        spec = os.path.join(fdir, "SPEC.md")
        row = ""
        if os.path.isfile(spec):
            m = re.search(r"^Row:\s*(\S+)", read(spec), re.M)
            row = m.group(1) if m else ""
        st = states.get(row, []) or states.get(slug, [])
        status = "archived" if row in archived else ("queued" if not st else ("done" if all(x == "done" for x in st) else "building"))
        batch = rows_by_id.get(row, {}).get("Batch", "")
        adrs = sorted(f[:-3] for f in os.listdir(os.path.join(fdir, "adr"))) if os.path.isdir(os.path.join(fdir, "adr")) else []
        lines.append(f"| [{slug}]({slug}/SPEC.md) | {row} | {batch} | {status} | {sum(x == 'done' for x in st)}/{len(st)} | {', '.join(adrs) or '—'} |")
    text = "\n".join(lines) + "\n"
    out = os.path.join(fd, "README.md")
    old = read(out) if os.path.isfile(out) else None
    if old == text:
        print("index unchanged")
        return 0
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"index written: {os.path.relpath(out, root)} ({len(folders)} feature(s))")
    return 0


def main(argv):
    repo = "."
    if "--repo" in argv:
        i = argv.index("--repo")
        repo = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    root = repo_root(repo)
    if not argv:
        die("usage: reef-queue.py status|ready [--all]|check|adr-number|index|footnote <text> [--row ID]|add-row --item <text> […]|set-depends ID <ids>|triage [--count]|set-batch ID N|drop-row ID --reason <text> [--repo DIR]")
    cmd = argv[0]
    if cmd == "status":
        return cmd_status(root)
    if cmd == "ready":
        return cmd_ready(root, "--all" in argv)
    if cmd == "check":
        return cmd_check(root)
    if cmd == "adr-number":
        return cmd_adr_number(root)
    if cmd == "index":
        return cmd_index(root)
    def opt(name, default=""):
        return argv[argv.index(name) + 1] if name in argv else default
    if cmd == "footnote" and len(argv) >= 2:
        return cmd_footnote(root, argv[1], opt("--row", None))
    if cmd == "add-row" and "--item" in argv:
        src = opt("--source", "planned")
        if src not in ("planned", "found"):
            die("--source is planned or found")
        return cmd_add_row(root, opt("--item"), opt("--depends"), src, opt("--batch", None), opt("--admitted"))
    if cmd == "set-depends" and len(argv) >= 3:
        return cmd_set_depends(root, argv[1], argv[2])
    if cmd == "triage":
        return cmd_triage(root, "--count" in argv)
    if cmd == "set-batch" and len(argv) >= 3:
        return cmd_set_batch(root, argv[1], argv[2])
    if cmd == "drop-row" and len(argv) >= 2 and "--reason" in argv:
        return cmd_drop_row(root, argv[1], opt("--reason"))
    die(f"unknown command {cmd!r}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
