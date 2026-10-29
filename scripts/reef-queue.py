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
  reef-queue.py add-rows --file rows.json [--repo DIR]     (0.7.2) a chain of rows in one pass: a JSON list of {item, depends,
                                                 source, batch, admitted, priority}; `@prev` in depends is the id just allocated
  reef-queue.py set-depends ID "<ids>" [--repo DIR]        (0.7) replace a row's Depends cell
  reef-queue.py triage [--repo DIR] [--count]              (0.7) rule 7: found rows still queued two batches after they
                                                 entered, grouped by module, with the three outcomes as ONE owner
                                                 question; the open found vs planned count; --count prints one line
  reef-queue.py note "<finding>" [--row ID] [--repo DIR]   (0.7) a hunter's NOTED finding — possible, may never happen —
                                                 recorded in noted-risks.md beside the queue instead of queued; refused
                                                 for a security, privacy, money or data-loss finding (always a row); prints n<k>
  reef-queue.py promote-note n<k> [--batch N] [--repo DIR] (0.7) that note as a found row (Depends its row); the note keeps
                                                 `→ row <id>` — a note is never deleted; prints the row id
  reef-queue.py set-batch ID N [--repo DIR]                (0.7) move a row to batch N (a promotion; footnote the reason)
  reef-queue.py drop-row ID --reason "<text>" [--repo DIR] (0.7) delete a queued row (rule 7) and record the reason as a footnote
  reef-queue.py journal <slug> [--repo DIR]     (0.7.1) on the base at the row's close: every task's `<!-- journal -->`
                                                block from its task file's Log appended to paths.runlog once
  reef-queue.py index [--repo DIR]              (0.6) regenerate <paths.features>/README.md: feature, row, batch,
                                                status, task counts, ADRs — never hand-edited
  reef-queue.py close ID --pr N [--repo DIR]               (0.7.1, issues) close the row's issue as completed, "merged in #N"
  reef-queue.py admit <issue> [--source planned|found] [--batch N]   (0.7.1, issues) a plain issue becomes the next row; (0.7.2)
                                                 one by a non-collaborator is copied into an issue of the owner's and closed with a link
  reef-queue.py demote ID [--repo DIR]                     (0.7.1, issues) a queued found row that may never happen becomes a
                                                 note; its issue closes as not planned; security, privacy, money, data loss refused
  reef-queue.py ask "<question>" --row ID [--recommended "<answer>"]   (0.7.2) a question for the owner: its line in
                                                 .reef/questions.md and, on issues, an issue labelled reef-question assigned to the owner
  reef-queue.py answered <#issue> "<answer>"       (0.7.2, issues) close the question's issue with the owner's answer
  reef-queue.py issue-row <#issue>                 (v3 phase 7, issues) the row id of an issue (the factory reads it)
  reef-queue.py row-issue ID                       (v3 phase 7, issues) the issue number of a row; refused when two issues carry the id
  reef-queue.py label-state ID                     (v3 phase 7, issues) the row's state (reef-row.py) as ONE label on its issue:
                                                   reef-waiting-owner (plan, approval, a merge that is the owner's), reef-building
                                                   (build, evidence), reef-review (review, merge); reef-ready is consumed
  reef-queue.py next-id [--repo DIR]                       (0.7.1) the next row id, in either mode
  reef-queue.py import-rows [--apply] [--repo DIR]         (0.7.1, issues) rows another tool wrote into the queue file
                                                 (reef-recalibrate) become issues, their ids kept; a dry run without --apply
  reef-queue.py set-priority ID p1|p2|p3|none             (0.7.1, issues) the row's priority label; add-row and admit take --priority
  reef-queue.py migrate-to-issues [--apply] [--repo DIR]   (0.7.1) the open rows to the repository's issues; a dry run
                                                 without --apply. Footnotes, notes and the archive stay files
  `queue.home: issues` (0.7.1): a row is an issue labelled `reef-row` titled `[<id>] <item>`, its body `Depends:` and
  `Admitted:` lines, a `found` or `planned` label; a batch is a milestone `Batch N`, the current batch the lowest open one;
  a closed issue is archived. `ready` orders by priority (`p1`, then none or `p2`, then `p3`), then planned before found,
  then id; a found row labelled `p1` counts as planned (the owner promoted it). A found row with no priority label is
  untriaged: `triage` lists them all, `triage --count` exits 1 once one has waited more than 7 days; `check` warns when
  the current batch holds more open rows than `queue.batch_max` (default 10). Every read syncs `.reef/queue.json` first (a failing gh: the last snapshot, said on stderr);
  every write goes to gh and fails closed. Every sync reads the collaborators (0.7.2): an open row whose issue's author is
  not one is excluded and warned about (an unreadable list keeps the last good one; none ever read: no trust check, said).
  `check` also validates (0.6) every feature folder's slug (2-5 kebab-case words, no bare number, no
  generic word) and the structure: a process document outside the layout fails.

The queue (paths.queue, default docs/queue.md) holds NO status column: a row is `queued` (no task
file names it as `feature:`), `building` (some task not done), `done` (every task done), or
`archived` (its id is only in docs/queue-archive.md). The table is any markdown table whose header
holds `Id` and `Depends`; `Current batch: N` names the batch that may start.
Exit 0 ok · 1 check failed / nothing to do · 2 usage.
"""
import fcntl
import json
import os
import re
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # the shared helpers live beside this script
from reef_common import config, repo_root, read  # noqa: E402

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


ROW_TITLE = re.compile(r"^\[(\d+)\]\s*(.*)$", re.S)
BATCH_MS = re.compile(r"^Batch (\d+)$")
LABEL = "reef-row"
LABELS = {LABEL: "0e8a16", "planned": "1d76db", "found": "fbca04", "p1": "b60205", "p2": "d93f0b", "p3": "c5def5",
          "reef-note": "c2e0c6", "reef-question": "5319e7"}
NOTE = "reef-note"   # 0.7.2 (item 8): on issues a note is an issue with this label, never a row
STATE_LABELS = {"reef-ready": "0052cc", "reef-building": "fbca04", "reef-review": "5319e7", "reef-waiting-owner": "d93f0b"}   # v3 phase 7: the
# factory's trigger and the row's state — created when first applied, not by the migration (its label set is the queue's own)
PRIORITIES = ("p1", "p2", "p3")
_SNAPS = {}


def issues_mode(cfg):
    return (cfg.get("queue") or {}).get("home") == "issues"


class GhError(Exception):
    pass


def gh(root, *args, read=False):
    """A read (the sync, inside the tick) waits 15 s, then the snapshot answers; a write waits 60 s."""
    t = os.environ.get("REEF_GH_READ_TIMEOUT", "15") if read else os.environ.get("REEF_GH_TIMEOUT", "60")
    try:
        r = subprocess.run(["gh", *args], cwd=root, capture_output=True, text=True, timeout=int(t))
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GhError(str(e))
    if r.returncode != 0:
        raise GhError((r.stderr or r.stdout).strip()[:300])
    return r.stdout


def gh_write(root, *args):
    _SNAPS.clear()
    try:
        return gh(root, *args)
    except GhError as e:
        die(f"gh {' '.join(args[:2])} failed, nothing more written: {e}", 1)


def field(body, name):
    m = re.search(rf"^{name}:[ \t]*(.*)$", body or "", re.M)
    return m.group(1).strip() if m else ""


def batch_of(milestone):
    m = BATCH_MS.match((milestone or {}).get("title", ""))
    return m.group(1) if m else ""


def sync(root):
    """The labelled issues and the milestones into .reef/queue.json; a failing gh reads the last snapshot."""
    if root in _SNAPS:
        return _SNAPS[root]
    snap_p = os.path.join(root, ".reef", "queue.json")
    try:
        issues = json.loads(gh(root, "issue", "list", "--label", LABEL, "--state", "all", "--limit", "1000",
                               "--json", "number,title,body,state,stateReason,labels,milestone,createdAt,author", read=True))
        ms = json.loads(gh(root, "api", "repos/{owner}/{repo}/milestones?state=all&per_page=100", read=True))
    except (GhError, ValueError) as e:
        if not os.path.isfile(snap_p):
            die(f"the queue is on issues, gh failed and there is no snapshot: {e}", 1)
        print(f"reef-queue: gh failed ({e}); reading the last snapshot, .reef/queue.json", file=sys.stderr)
        return json.loads(read(snap_p))
    collab = collaborators(root, snap_p)
    try:   # the last id this checkout allocated outlives the re-read: GitHub's list lags a just-created issue (item 20)
        last_id = int(json.loads(read(snap_p)).get("last_id") or 0) if os.path.isfile(snap_p) else 0
    except (ValueError, TypeError):
        last_id = 0
    open_b = sorted(int(b) for x in ms for b in [batch_of(x)] if b and x.get("state") == "open")
    snap = {"current_batch": str(open_b[0]) if open_b else None, "milestones": {x["title"]: x["number"] for x in ms},
            "rows": [], "closed": [], "dropped": [], "unadmitted": [], "untrusted": [], "collaborators": collab, "last_id": last_id}
    for i in issues:
        m = ROW_TITLE.match((i.get("title") or "").strip())
        if not m:
            snap["unadmitted"].append(i["number"])
            continue
        b = i.get("body") or ""
        row = {"Id": m.group(1), "Item": field(b, "Item") or m.group(2).strip(), "Depends": field(b, "Depends"),
               "Source": "found" if any(lb.get("name") == "found" for lb in i.get("labels") or []) else "planned",
               "Batch": batch_of(i.get("milestone")), "Admitted": field(b, "Admitted"), "_issue": i["number"], "_created": i.get("createdAt", ""),
               "Priority": next((p for p in PRIORITIES if any(lb.get("name") == p for lb in i.get("labels") or [])), ""),
               "_author": (i.get("author") or {}).get("login", "")}
        if i.get("state") == "OPEN" and collab is not None and row["_author"] not in collab:   # 0.7.2, item 9
            snap["untrusted"].append(row)
            print(f"reef-queue: row {row['Id']} (#{i['number']}, by @{row['_author']}) excluded: its author is not a collaborator", file=sys.stderr)
            continue
        snap["rows" if i.get("state") == "OPEN" else "dropped" if i.get("stateReason") == "NOT_PLANNED" else "closed"].append(row)
    os.makedirs(os.path.dirname(snap_p), exist_ok=True)
    write_text(snap_p, json.dumps(snap, indent=1) + "\n")
    write_view(root, snap)
    _SNAPS[root] = snap
    return snap


def collaborators(root, snap_p):
    """The repository's collaborators (0.7.2, the owner's go 2026-10-24, item 9): the trust check's list. Unreadable (a
    403: the token lacks push access, or gh is down): the last snapshot's list, said on stderr; none ever read: no check."""
    try:
        return gh(root, "api", "repos/{owner}/{repo}/collaborators", "--paginate", "--jq", ".[].login", read=True).split()
    except GhError as e:
        last = json.loads(read(snap_p)).get("collaborators") if os.path.isfile(snap_p) else None
        print(f"reef-queue: collaborators unreadable ({e}); " + ("keeping the last good list" if last is not None else
              "no trust check: every row's author is taken on trust"), file=sys.stderr)
        return last


def write_view(root, snap):
    """A read-only view of the queue at every sync (0.7.2, the owner's go 2026-10-24, item 10): read it offline, edit the
    issues. Gitignored, so it never conflicts and never drifts into a second queue."""
    import datetime
    rank = {"p1": 1, "p3": 3}
    rows = sorted(snap["rows"], key=lambda r: (int(r.get("Batch") or 0), rank.get(r.get("Priority", ""), 2), int(r["Id"])))
    cell = lambda x: str(x or "").replace("|", "/")
    lines = ["# Queue — a read-only view", "",
             f"Generated from the repository's issues by reef-queue.py, {datetime.datetime.now():%Y-%m-%d %H:%M}: edit the issues, "
             "never this file.", "", f"Current batch: {snap.get('current_batch') or '-'}", "",
             "| Id | Item | Priority | Source | Batch | Depends | Issue |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {r['Id']} | {cell(r.get('Item'))[:120]} | {cell(r.get('Priority'))} | {cell(r.get('Source'))} | {cell(r.get('Batch'))} | "
              f"{cell(r.get('Depends'))} | #{r['_issue']} |" for r in rows]
    write_text(os.path.join(root, ".reef", "queue-view.md"), "\n".join(lines) + "\n")


def row_issue(root, row_id):
    r = next((x for x in sync(root)["rows"] if x["Id"] == row_id), None)
    if r is None:
        die(f"no open row {row_id} among the issues labelled {LABEL}", 1)
    return str(r["_issue"])


def next_id(root, snap):
    _, _, apath = queue_paths(root)
    ids = [int(r["Id"]) for r in snap["rows"] + snap["closed"] + snap.get("dropped", []) + snap.get("untrusted", [])]
    ids += [int(r["Id"]) for r in parse_table(read(apath)) if r["Id"].isdigit()] if os.path.isfile(apath) else []
    return max(ids + [int(snap.get("last_id") or 0)], default=0) + 1


def allocate_id(root, snap):
    """The next row id, RESERVED (0.7.2, first adoption 2026-10-24, item 20): six add-rows in a row made issues titled [3] [3] [4] [4]
    [5] [5], because GitHub's issue list lags a just-created issue. The last allocated id is kept in .reef/queue.json under a
    file lock and counts like a row's; the snapshot's re-read carries it over."""
    snap_p = os.path.join(root, ".reef", "queue.json")
    os.makedirs(os.path.dirname(snap_p), exist_ok=True)
    with open(snap_p + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            on_disk = json.loads(read(snap_p)) if os.path.isfile(snap_p) else {}
        except ValueError:
            on_disk = {}
        snap["last_id"] = max(int(snap.get("last_id") or 0), int(on_disk.get("last_id") or 0))
        new_id = next_id(root, snap)
        snap["last_id"] = new_id
        on_disk = on_disk or dict(snap)
        on_disk["last_id"] = new_id
        write_text(snap_p, json.dumps(on_disk, indent=1) + "\n")
    return new_id


def settle_id(root, snap, new_id, number, title):
    """After `issue create`: if another open row issue carries the same [id] (two sessions, one lagging list), the NEWER issue
    — this one — is retitled to the next free id, and the change is printed (item 20)."""
    for _ in range(3):
        try:
            issues = json.loads(gh(root, "issue", "list", "--label", LABEL, "--state", "open", "--limit", "1000", "--json", "number,title", read=True))
        except (GhError, ValueError):
            return new_id
        others = [i["number"] for i in issues if i["number"] != number
                  for m in [ROW_TITLE.match((i.get("title") or "").strip())] if m and m.group(1) == str(new_id)]
        if not others or min(others) > number:   # no clash, or this issue is the older one: the other session retitles
            return new_id
        for i in issues:   # every id now on the forge counts before the next allocation
            m = ROW_TITLE.match((i.get("title") or "").strip())
            if m:
                snap["last_id"] = max(int(snap.get("last_id") or 0), int(m.group(1)))
        fresh = allocate_id(root, snap)
        gh_write(root, "issue", "edit", str(number), "--title", f"[{fresh}] {title}")
        print(f"reef-queue: #{number} was [{new_id}] like #{min(others)}; retitled to [{fresh}]", file=sys.stderr)
        new_id = fresh
    return new_id


def ensure_labels(root, *names):
    for n in names:
        gh_write(root, "label", "create", n, "--force", "--color", {**LABELS, **STATE_LABELS}[n])


def ensure_milestone(root, snap, batch):
    t = f"Batch {batch}"
    if t not in snap["milestones"]:
        snap["milestones"][t] = json.loads(gh_write(root, "api", "repos/{owner}/{repo}/milestones", "-f", f"title={t}"))["number"]
    return t


def issue_text(item, depends, admitted):
    """Title and body of a row's issue: the title without footnote marks, cut past 200 characters; the whole Item, marks
    included, in the body whenever the title differs."""
    item = " ".join(item.split())
    plain = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", "", item).strip()
    short = plain if len(plain) <= 200 else plain[:197].rsplit(" ", 1)[0] + "…"
    return short, f"Depends: {depends.strip()}\nAdmitted: {admitted.strip()}\n" + (f"Item: {item}\n" if short != item else "")


def load(root):
    cfg = config(root)
    apath = os.path.join(root, os.path.dirname(cfg.get("paths", {}).get("queue", "docs/queue.md")), "queue-archive.md")
    archived = {r["Id"] for r in parse_table(read(apath))} if os.path.isfile(apath) else set()
    if issues_mode(cfg):
        snap = sync(root)
        text = f"Current batch: {snap['current_batch']}\n" if snap["current_batch"] else ""
        rows = sorted((dict(r) for r in snap["rows"]), key=lambda r: int(r["Id"]))
        archived |= {r["Id"] for r in snap["closed"]}
    else:
        qpath = os.path.join(root, cfg.get("paths", {}).get("queue", "docs/queue.md"))
        if not os.path.isfile(qpath):
            die(f"no queue at {os.path.relpath(qpath, root)} — run /reef-init", 1)
        text = read(qpath)
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
    if row_id and issues_mode(config(root)):
        gh_write(root, "issue", "comment", row_issue(root, row_id), "--body", line)
    elif row_id:
        pat = re.compile(rf"^(\|\s*{re.escape(row_id)}\s*\|\s*)(.*?)(\s*\|)", re.M)
        m = pat.search(q)
        if not m:
            die(f"no row {row_id} in the queue", 1)
        q = q[:m.start()] + m.group(1) + m.group(2).rstrip() + mark + m.group(3) + q[m.end():]
    write_text(qpath, q)
    print(mark)
    return 0


def add_row(root, item, depends, source, batch, admitted, priority=""):
    cfg, qpath, apath = queue_paths(root)
    if issues_mode(cfg):
        snap = sync(root)
        new_id, cur = allocate_id(root, snap), snap["current_batch"] or "1"
        if batch is None:
            batch = cur if source == "planned" or admitted else str(int(cur) + 1)   # rule 6
        title, body = issue_text(item, depends, admitted)
        ensure_labels(root, LABEL, source, *([priority] if priority else []))
        url = gh_write(root, "issue", "create", "--title", f"[{new_id}] {title}", "--body", body, "--label", LABEL, "--label", source,
                       *(["--label", priority] if priority else []), "--milestone", ensure_milestone(root, snap, batch)).strip()
        number = url.rstrip("/").rsplit("/", 1)[-1]
        return settle_id(root, snap, new_id, int(number), title) if number.isdigit() else new_id
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
    return new_id


def cmd_add_row(root, item, depends, source, batch, admitted, priority=""):
    print(add_row(root, item, depends, source, batch, admitted, priority))
    return 0


def cmd_add_rows(root, path):
    """A chain of rows in one pass (item 20c): `@prev` in a row's depends is the id allocated just before it."""
    try:
        rows = json.loads(read(path))
    except (OSError, ValueError) as e:
        die(f"add-rows: {e}")
    if not isinstance(rows, list) or not all(isinstance(r, dict) and r.get("item") for r in rows):
        die("add-rows: a JSON list of objects, each with an item")
    prev = None
    for r in rows:
        if r.get("source", "planned") not in ("planned", "found") or r.get("priority", "") not in ("",) + PRIORITIES:
            die("add-rows: source is planned or found; priority is p1, p2 or p3")
        dep = str(r.get("depends") or "")
        if "@prev" in dep and prev is None:
            die("add-rows: @prev in the first row has nothing to point at")
        dep = dep.replace("@prev", str(prev)) if prev is not None else dep
        prev = add_row(root, r["item"], dep, r.get("source", "planned"), r.get("batch"), str(r.get("admitted") or ""), r.get("priority", ""))
        print(prev)
    return 0


# found rows outran their closing (the owner, 2026-10-21: 77 of qassimha's 82 open rows were found, 11 from one row's
# hunters in one night): a hole that may never happen is recorded, not queued — and nothing important is dropped, so a
# finding in these classes is always a row, whatever its odds
SAFETY = re.compile(r"\b(auth\w*|sessions?|cookies?|csrf|xss|inject\w*|secrets?|passwords?|credentials?|pii|personal data|"
                    r"privacy|leak\w*|payments?|charges?|refunds?|data loss|permissions?|bypass\w*|attack\w*)\b", re.I)
NOTES_HEAD = ("# Noted risks\n\nFindings that may never happen, recorded instead of queued (`reef-queue.py note`). "
              "`reef-queue.py promote-note n<k>` makes one a found row. A note is never deleted.\n\n")


def notes_path(root):
    _, qpath, _ = queue_paths(root)
    return os.path.join(os.path.dirname(qpath), "noted-risks.md")


def open_notes(root):
    p = notes_path(root)
    return [l for l in read(p).splitlines() if re.match(r"^- n\d+ · ", l) and " → row " not in l] if os.path.isfile(p) else []


def note_text(text):
    text = " ".join(text.split()).replace("|", "/")
    if not text:
        die("note: the finding, one line")
    m = SAFETY.search(text)
    if m:
        die(f"'{m.group(0)}': a security, privacy, money or data-loss finding is always a queue row — "
            f"add-row --item \"…\" --source found", 1)
    return text


def next_note(root):
    p = notes_path(root)
    body = read(p) if os.path.isfile(p) else NOTES_HEAD
    return p, body, max((int(x) for x in re.findall(r"(?m)^- n(\d+) · ", body)), default=0) + 1


def cmd_note(root, text, row_id):
    import datetime
    text = note_text(text)
    if issues_mode(config(root)):
        ensure_labels(root, NOTE)
        url = gh_write(root, "issue", "create", "--title", f"note: {text[:200]}", "--label", NOTE, "--body",
                       f"Row: {row_id or '-'}\nNoted: {datetime.date.today().isoformat()}\n\n{text}\n").strip()
        print("#" + url.rstrip("/").rsplit("/", 1)[-1])
        return 0
    p, body, n = next_note(root)
    write_text(p, body.rstrip("\n") + f"\n- n{n} · row {row_id or '-'} · {datetime.date.today().isoformat()} · {text}\n")
    print(f"n{n}")
    return 0


def cmd_demote(root, row_id):
    """A queued found row that may never happen becomes a note (0.7.1, issues): the issue closes as not planned with the
    note's id, the note keeps the row's text. Checked before anything is written: a safety finding stays a row."""
    if not issues_mode(config(root)):
        die("demote is for queue.home: issues", 1)
    r = next((x for x in load(root)[2] if x["Id"] == row_id), None)
    if r is None or r["_status"] != "queued":
        die(f"row {row_id} is {'not an open row' if r is None else r['_status']}: only a queued row becomes a note", 1)
    text = note_text(f"{r.get('Item', '').strip()} (was row {row_id})")
    if issues_mode(config(root)):   # item 8: the row's own issue becomes the note, relabelled
        ensure_labels(root, NOTE)
        gh_write(root, "issue", "edit", str(r["_issue"]), "--remove-label", LABEL, "--add-label", NOTE)
        gh_write(root, "issue", "comment", str(r["_issue"]), "--body", "demoted to a note (may never happen)")
        print(f"#{r['_issue']}")
        return 0
    n = next_note(root)[2]
    gh_write(root, "issue", "close", str(r["_issue"]), "--reason", "not planned", "--comment", f"demoted to note n{n} (may never happen)")
    return cmd_note(root, text, row_id)


def cmd_promote_note(root, nid, batch):
    if issues_mode(config(root)):   # item 8: the note's issue becomes a found row, relabelled
        snap = sync(root)
        i = json.loads(gh_write(root, "issue", "view", nid.lstrip("#"), "--json", "number,title,body,labels"))
        if NOTE not in [lb.get("name") for lb in i.get("labels") or []]:
            die(f"#{i['number']} is not a note (no {NOTE} label)", 1)
        new_id, cur = next_id(root, snap), snap["current_batch"] or "1"
        row = field(i.get("body"), "Row")
        text = re.sub(r"^note:\s*", "", i["title"]).strip()
        body = (f"Depends: {row}\n" if row and row != "-" else "") + (i.get("body") or "")
        ensure_labels(root, LABEL, "found")
        gh_write(root, "issue", "edit", str(i["number"]), "--title", f"[{new_id}] {text} (noted #{i['number']})", "--body", body,
                 "--remove-label", NOTE, "--add-label", LABEL, "--add-label", "found",
                 "--milestone", ensure_milestone(root, snap, batch or str(int(cur) + 1)))
        print(new_id)
        return 0
    p = notes_path(root)
    body = read(p) if os.path.isfile(p) else ""
    m = re.search(rf"(?m)^- {re.escape(nid)} · row (\S+) · \S+ · (.*)$", body)
    if not m:
        die(f"no note {nid} in {os.path.relpath(p, root)}", 1)
    if " → row " in m.group(0):
        die(f"note {nid} is already a row ({m.group(0).rsplit(' → ', 1)[1]})", 1)
    new_id = add_row(root, f"{m.group(2).strip()} (noted {nid})", "" if m.group(1) == "-" else m.group(1), "found", batch, "")
    write_text(p, body.replace(m.group(0), f"{m.group(0)} → row {new_id}", 1))
    print(new_id)
    return 0


def cmd_set_depends(root, row_id, depends):
    cfg, qpath, _ = queue_paths(root)
    if issues_mode(cfg):
        n = row_issue(root, row_id)
        b = json.loads(gh_write(root, "issue", "view", n, "--json", "body"))["body"] or ""
        line = f"Depends: {depends.strip()}"
        b = re.sub(r"^Depends:.*$", line, b, count=1, flags=re.M) if re.search(r"^Depends:", b, re.M) else line + "\n" + b
        gh_write(root, "issue", "edit", n, "--body", b)
        print(f"{row_id}\tdepends={depends.strip()}")
        return 0
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


def triage_issues(root, count_only):
    """On issues (0.7.1, the owner's go 2026-10-24): a found row with no priority label is untriaged; giving it a priority
    IS the decision. The tick's line once one has waited more than 7 days; the list groups them all by module."""
    import datetime
    _, text, rows, _, _ = load(root)
    now = datetime.datetime.now(datetime.timezone.utc)
    age = lambda r: (now - datetime.datetime.fromisoformat(r["_created"].replace("Z", "+00:00"))).days if r.get("_created") else 0
    found = [r for r in rows if r.get("Source") == "found"]
    un = [r for r in found if not r.get("Priority")]
    oldest = max((age(r) for r in un), default=0)
    try:
        notes = len(json.loads(gh(root, "issue", "list", "--label", NOTE, "--state", "open", "--json", "number", read=True)))
    except (GhError, ValueError):
        notes = 0
    print(f"triage: batch {current_batch(text) or '?'} · open found {len(found)} vs planned {len(rows) - len(found)} · untriaged found: "
          f"{len(un)}" + (f" (oldest {oldest} day(s))" if un else "") + (f" · noted risks: {notes} open (issues labelled {NOTE})" if notes else ""))
    if count_only or not un:
        return 1 if un and (oldest > 7 or not count_only) else 0
    print("\nONE owner question (AskUserQuestion, one entry per row; a priority label is the decision):")
    groups = {}
    for r in un:
        groups.setdefault(module_of(r.get("Item", "")), []).append(r)
    for mod in sorted(groups):
        print(f"\n## {mod}")
        for r in groups[mod]:
            print(f"- row {r['Id']} (#{r['_issue']}, batch {r.get('Batch') or '?'}, {age(r)} day(s)): {r.get('Item', '')[:140]}")
            print(f"    Keep → set-priority {r['Id']} p1|p2|p3")
            print(f"    Merge into design row <id> → footnote --row <id> \"absorbs row {r['Id']}: …\" + drop-row {r['Id']} --reason \"merged into <id>\"")
            print(f"    Drop → drop-row {r['Id']} --reason \"<why it no longer matters>\"   (first-class outcome)")
            print(f"    Note → demote {r['Id']}   (may never happen; security, privacy, money and data loss stay rows)")
    return 1


def cmd_triage(root, count_only):
    """Found-row triage as a command (usability plan B5). The first full loop had 18 of 26 open rows `found` and no
    moment that asked about them; rule 7 says a found row untouched after two batches is promoted once with a reason,
    merged into a design row, or deleted, and deletion is a first-class outcome. Prints the owner's ONE question."""
    if issues_mode(config(root)):
        return triage_issues(root, count_only)
    _, text, rows, archived, _ = load(root)
    stale, open_found, open_planned = triage_rows(rows, text)
    cur = current_batch(text) or "?"
    head = f"triage: batch {cur} · open found {len(open_found)} vs planned {len(open_planned)} · stale found (rule 7): {len(stale)}"
    notes = open_notes(root)
    if notes:
        head += f" · noted risks: {len(notes)} open ({os.path.relpath(notes_path(root), root)}; promote-note n<k> makes one a row)"
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
    cfg, qpath, _ = queue_paths(root)
    if not re.fullmatch(r"\d+", batch or ""):
        die("batch is a number")
    if issues_mode(cfg):
        n = row_issue(root, row_id)
        gh_write(root, "issue", "edit", n, "--milestone", ensure_milestone(root, sync(root), batch))
        print(f"{row_id}\tbatch={batch}")
        return 0
    q = read(qpath)
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
    if issues_mode(config(root)):
        gh_write(root, "issue", "close", str(r["_issue"]), "--reason", "not planned", "--comment", f"dropped (rule 7): {reason.strip()}")
    else:
        keep = [l for l in read(qpath).splitlines() if not re.match(rf"^\|\s*{re.escape(row_id)}\s*\|", l)]
        write_text(qpath, "\n".join(keep) + "\n")
    cmd_footnote(root, f"row {row_id} deleted (rule 7): {reason.strip()} — was: {r.get('Item', '').strip()[:120]}", None)
    return 0


def cmd_status(root):
    _, _, rows, archived, _ = load(root)
    for r in rows:
        print(f"{r['Id']}\t{r['_status']}\tdepends={r['_depends']}\tbatch={r.get('Batch', '')}\t{r.get('Item', '')[:70]}")
    return 0


def cmd_ready(root, all_batches, with_found=False):
    _, text, rows, archived, _ = load(root)
    batch = current_batch(text)
    by_id = {r["Id"]: r for r in rows}
    ready = [r for r in rows if r["_status"] != "done"
             and all(is_done(d, by_id, archived) for d in r["_depends"])
             and (all_batches or batch is None or r.get("Batch", "") == batch)]
    first = lambda r: r.get("Source", "").lower() == "planned" or r.get("Priority") == "p1"   # a p1 found row: promoted
    ready.sort(key=lambda r: ({"p1": 1, "p3": 3}.get(r.get("Priority", ""), 2), 0 if first(r) else 1, int(re.match(r"\d+", r["Id"]).group())))
    planned = [r for r in ready if first(r)]
    # --with-found (a night, 2026-10-23): the found rows too, after the planned ones — the contract names what is driven
    for r in (ready if with_found else (planned or ready)):   # ready is in priority order (2026-10-24)
        print(f"{r['Id']}\t{r['_status']}\t{r.get('Source', '')}\t{r.get('Item', '')[:70]}")
    if ready and not planned and not with_found:
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
    cur, bmax = current_batch(text), int((cfg.get("queue") or {}).get("batch_max", 10) or 0)
    n_cur = sum(1 for r in rows if cur and (r.get("Batch") or "").strip() == cur)
    if bmax and n_cur > bmax:
        print(f"warning: batch {cur} holds {n_cur} open row(s), over queue.batch_max {bmax} — a sprint is 5 to 10 rows")
    stray = len(file_rows(root)) if issues_mode(cfg) else 0
    if stray:
        print(f"warning: {stray} row(s) in {cfg.get('paths', {}).get('queue', 'docs/queue.md')} while the queue is on issues — "
              "python3 scripts/reef-queue.py import-rows --apply makes them issues")
    for n in sync(root)["unadmitted"] if issues_mode(cfg) else []:
        print(f"warning: #{n} is labelled {LABEL} but its title has no [id] — the owner admits it: reef-queue.py admit {n}")
    for r in sync(root).get("untrusted", []) if issues_mode(cfg) else []:
        print(f"warning: row {r['Id']} (#{r['_issue']}, by @{r['_author']}) is excluded — its author is not a collaborator: "
              "close its issue, or add-row the item yourself")
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
            # a note in parentheses is not a status (2026-10-24, the trial, twice: "(AC3, AC4 rendered on the server …)"
            # read "rendered" as one, and the agent rewrote an honest caveat as "achieved")
            for m in re.finditer(r"\bAC-?\d+\s+([a-z-]+)", re.sub(r"\([^()]*\)", " ", cells[ac_col])):
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


def file_rows(root):
    _, qpath, _ = queue_paths(root)
    return parse_table(read(qpath)) if os.path.isfile(qpath) else []


def cmd_next_id(root):
    """The next row id in either mode, rows still waiting in the file included (reef-recalibrate numbers its rows here)."""
    cfg, _, apath = queue_paths(root)
    if issues_mode(cfg):
        n = next_id(root, sync(root))
    else:
        rows = file_rows(root) + (parse_table(read(apath)) if os.path.isfile(apath) else [])
        n = max((int(r["Id"]) for r in rows if r["Id"].isdigit()), default=0) + 1
    print(max([n] + [int(r["Id"]) + 1 for r in file_rows(root) if r["Id"].isdigit()]))
    return 0


def cmd_import_rows(root, apply):
    """Rows in the queue file while the queue is on issues become issues, ids kept (2026-10-24, AI coach: /reef-assess
    appends a converted spec's row to the file, inside its one revertable commit)."""
    cfg, qpath, _ = queue_paths(root)
    if not issues_mode(cfg):
        die("import-rows is for queue.home: issues; the file queue already holds its rows", 1)
    rows = file_rows(root)
    if not rows:
        print("nothing to import")
        return 0
    snap = sync(root)
    have = {r["Id"]: r["_issue"] for r in snap["rows"] + snap["closed"] + snap.get("dropped", [])}
    clash = next((r for r in rows if r["Id"] in have), None)
    if clash:
        die(f"row {clash['Id']} is already issue #{have[clash['Id']]} — give the file's row a new id (reef-queue.py next-id)", 1)
    rel = os.path.relpath(qpath, root)
    if not apply:
        print(f"would create {len(rows)} issue(s) from {rel} — a dry run; --apply creates them")
        return 0
    ensure_labels(root, *LABELS)
    for r in sorted(rows, key=lambda r: int(re.match(r"\d+", r["Id"]).group())):
        title, body = issue_text(r.get("Item", ""), r.get("Depends", ""), r.get("Admitted", ""))
        src = "found" if (r.get("Source") or "").strip().lower() == "found" else "planned"
        b = re.match(r"\d+", r.get("Batch", "") or "")
        gh_write(root, "issue", "create", "--title", f"[{r['Id']}] {title}", "--body", body, "--label", LABEL, "--label", src,
                 "--milestone", ensure_milestone(root, snap, b.group() if b else (snap["current_batch"] or "1")))
    out, skip = [], False
    for line in read(qpath).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.strip().startswith("|") else []
        skip = ("Id" in cells and "Depends" in cells) or (skip and bool(cells))
        if not skip:
            out.append(line)
    write_text(qpath, re.sub(r"\n{3,}", "\n\n", "\n".join(out)) + "\n")
    print(f"created {len(rows)} issue(s); the rows left {rel}")
    return 0


def cmd_ask(root, question, row_id, recommended):
    """A question for the owner (0.7.2, the owner's go 2026-10-24, item 7): the line the runner, the handoff and the next
    interactive /reef-loop read, and on issues an issue assigned to the owner, so a question reaches them on GitHub too."""
    q = " ".join(question.split())
    if not q:
        die("ask: the question, one line")
    line = f"- row {row_id or '-'}: {q}" + (f" — recommended: {recommended.strip()}" if recommended.strip() else "")
    p = os.path.join(root, ".reef", "questions.md")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    if not issues_mode(config(root)):
        print(".reef/questions.md")
        return 0
    ensure_labels(root, "reef-question")
    url = gh_write(root, "issue", "create", "--title", f"question: row {row_id or '-'}: {q[:180]}", "--label", "reef-question",
                   "--assignee", "@me", "--body", line[2:] + "\n").strip()
    print("#" + url.rstrip("/").rsplit("/", 1)[-1])
    return 0


def cmd_answered(root, number, answer):
    if not issues_mode(config(root)):
        die("answered is for queue.home: issues; the file queue keeps questions in .reef/questions.md", 1)
    gh_write(root, "issue", "close", number.lstrip("#"), "--reason", "completed", "--comment", f"answered: {answer.strip()}")
    print(f"#{number.lstrip('#')}\tanswered")
    return 0


def cmd_row_issue(root, row_id):
    rows = [x for x in sync(root)["rows"] if x["Id"] == row_id]
    if len(rows) > 1:
        die(f"row {row_id} has {len(rows)} open issues (#{', #'.join(str(x['_issue']) for x in rows)}) — one row, one issue: close the duplicate", 1)
    print(row_issue(root, row_id))
    return 0


def cmd_issue_row(root, number):
    n = int(number.lstrip("#"))
    snap = sync(root)
    r = next((x for x in snap["rows"] + snap.get("closed", []) if int(x.get("_issue") or 0) == n), None)
    if r is None:
        die(f"issue #{n} is not a row (no `[id]` title with the label {LABEL})", 1)
    print(r["Id"])
    return 0


def cmd_label_state(root, row_id):
    """v3 phase 7: the row's state, read by reef-row.py (disk and forge), as one label on its issue — the factory's log a
    person reads from the issue list; the trigger label reef-ready is consumed."""
    if not issues_mode(config(root)):
        die("label-state is for queue.home: issues", 1)
    n = row_issue(root, row_id)
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([sys.executable, os.path.join(here, "reef-row.py"), "state", row_id, "--json", "--repo", root], capture_output=True, text=True, cwd=root)
    try:
        st = json.loads(r.stdout)
    except ValueError:
        die(f"reef-row.py state {row_id}: {(r.stderr or r.stdout).strip()[:200]}", 1)
    state = str(st.get("state") or "")
    label = ("reef-waiting-owner" if state in ("plan", "approval") or (state == "merge" and st.get("merge_by") != "loop")
             else "reef-building" if state in ("build", "evidence") else "reef-review" if state in ("review", "merge", "close") else None)
    try:
        current = [l.get("name") for l in json.loads(gh(root, "issue", "view", n, "--json", "labels", read=True)).get("labels") or []]
    except (GhError, ValueError):
        current = []
    args = []
    if label and label not in current:
        ensure_labels(root, label)
        args += ["--add-label", label]
    for l in STATE_LABELS:
        if l in current and l != label:
            args += ["--remove-label", l]
    if args:
        gh_write(root, "issue", "edit", n, *args)
    print(f"{row_id}\t{state}\t{label or '-'}\t#{n}")
    return 0


def cmd_close(root, row_id, pr):
    if not issues_mode(config(root)):
        die("close is for queue.home: issues; the file queue moves the row to its archive (rule 5)", 1)
    gh_write(root, "issue", "close", row_issue(root, row_id), "--reason", "completed", "--comment", f"merged in #{pr.lstrip('#')}")
    print(f"{row_id}\tclosed")
    return 0


def cmd_set_priority(root, row_id, prio):
    if prio not in PRIORITIES + ("none",):
        die("priority is p1, p2, p3 or none")
    if not issues_mode(config(root)):
        die("set-priority is for queue.home: issues", 1)
    r = next((x for x in sync(root)["rows"] if x["Id"] == row_id), None)
    if r is None:
        die(f"no open row {row_id} among the issues labelled {LABEL}", 1)
    args = ["--remove-label", r["Priority"]] if r.get("Priority") and r["Priority"] != prio else []
    if prio != "none":
        ensure_labels(root, prio)
        args += ["--add-label", prio]
    if args:
        gh_write(root, "issue", "edit", str(r["_issue"]), *args)
    print(f"{row_id}\tpriority={prio}")
    return 0


def cmd_admit(root, number, source, batch, priority=""):
    """A plain issue (an idea, triaged) becomes the next row: `[id]` in its title, the labels, its batch's milestone."""
    if not issues_mode(config(root)):
        die("admit is for queue.home: issues", 1)
    snap = sync(root)
    i = json.loads(gh_write(root, "issue", "view", number.lstrip("#"), "--json", "number,title,body,labels,author"))
    if ROW_TITLE.match(i["title"].strip()):
        die(f"#{i['number']} is already a row: {i['title']}", 1)
    new_id, cur = next_id(root, snap), snap["current_batch"] or "1"
    batch = batch or (cur if source == "planned" else str(int(cur) + 1))
    ensure_labels(root, LABEL, source, *([priority] if priority else []))
    ms, author = ensure_milestone(root, snap, batch), (i.get("author") or {}).get("login", "")
    if snap.get("collaborators") is None or author not in snap["collaborators"]:
        # 0.7.2 (item 9): an outsider keeps editing their own issue, whose body every reader parses — the row is a copy the
        # owner authors (the original's text quoted, so none of its lines reads as a field), the original closed with a link
        title, body = issue_text(i["title"], "", "")
        body += f"\nFrom #{i['number']} by @{author or '?'}:\n" + "\n".join("> " + l for l in (i.get("body") or "").splitlines()) + "\n"
        url = gh_write(root, "issue", "create", "--title", f"[{new_id}] {title}", "--body", body, "--label", LABEL, "--label", source,
                       *(["--label", priority] if priority else []), "--milestone", ms).strip()
        gh_write(root, "issue", "close", str(i["number"]), "--reason", "not planned",
                 "--comment", f"admitted as #{url.rstrip('/').rsplit('/', 1)[-1]} (row {new_id}), a copy: its author is not a collaborator")
    else:
        gh_write(root, "issue", "edit", str(i["number"]), "--title", f"[{new_id}] {i['title'].strip()}", "--add-label", LABEL,
                 "--add-label", source, *(["--add-label", priority] if priority else []), "--milestone", ms)
    print(new_id)
    return 0


def cmd_migrate(root, apply):
    """The file queue's open rows to issues, in id order; labels and milestones first (a batch before the current one
    closed); the queue file keeps its rules and footnotes, loses its row tables; queue.home becomes issues. A re-run
    after a failure skips the rows that already have an issue."""
    cfg, qpath, apath = queue_paths(root)
    if issues_mode(cfg):
        die("the queue is already on issues", 1)
    q = read(qpath)
    rows, cur = parse_table(q), int(current_batch(q) or 1)
    for r in [r for r in rows if re.fullmatch(r"<[^<>]*>", r.get("Item", "").strip())]:   # a fresh init's `<the first … row>`
        rows.remove(r)
        print(f"skipped row {r['Id']}: the template's placeholder, {r['Item'].strip()}")
    num = lambda r: int((re.match(r"\d+", r.get("Batch", "")) or re.match(r"\d+", str(cur))).group())
    batches = sorted({num(r) for r in rows} | {cur})
    print(f"{len(rows)} open row(s); milestones {', '.join(f'Batch {b}' for b in batches)} (current: Batch {cur}); labels {LABEL}, planned, found")
    if not apply:
        print(f"would create {len(rows)} issue(s) — a dry run; --apply creates them")
        return 0
    ensure_labels(root, *LABELS)
    have = {m.group(1) for i in json.loads(gh_write(root, "issue", "list", "--label", LABEL, "--state", "all", "--limit", "1000",
                                                     "--json", "number,title")) for m in [ROW_TITLE.match(i["title"])] if m}
    ms = {x["title"]: x for x in json.loads(gh_write(root, "api", "repos/{owner}/{repo}/milestones?state=all&per_page=100"))}
    for b in batches:
        t = f"Batch {b}"
        if t not in ms:
            ms[t] = json.loads(gh_write(root, "api", "repos/{owner}/{repo}/milestones", "-f", f"title={t}"))
        if b < cur and ms[t].get("state") == "open":
            gh_write(root, "api", "-X", "PATCH", f"repos/{{owner}}/{{repo}}/milestones/{ms[t]['number']}", "-f", "state=closed")
    made = 0
    for r in sorted(rows, key=lambda r: int(r["Id"])):
        if r["Id"] in have:
            continue
        title, body = issue_text(r.get("Item", ""), r.get("Depends", ""), r.get("Admitted", ""))
        src = "found" if (r.get("Source") or "").strip().lower() == "found" else "planned"
        gh_write(root, "issue", "create", "--title", f"[{r['Id']}] {title}", "--body", body, "--label", LABEL, "--label", src,
                 "--milestone", f"Batch {num(r)}")
        made += 1
    pointer = (f"Rows: this repository's issues labelled `{LABEL}`, titled `[<id>] <item>` (`queue.home: issues`); a batch "
               "is a milestone, the current batch the lowest open one. This file keeps the rules and the footnotes.")
    q = re.sub(r"^## Batch \d+[^\n]*\n.*?(?=^## |\Z)", "", q, flags=re.M | re.S)
    q = re.sub(r"^Current batch:.*$", pointer, q, count=1, flags=re.M) if re.search(r"^Current batch:", q, re.M) else q.replace("\n", f"\n\n{pointer}\n", 1)
    write_text(qpath, q)
    cfg.setdefault("queue", {})["home"] = "issues"
    write_text(os.path.join(root, ".reef", "config.json"), json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
    print(f"created {made} issue(s); {os.path.relpath(qpath, root)} keeps its rules and footnotes; queue.home: issues — "
          f"commit both: git add -- {os.path.relpath(qpath, root)} .reef/config.json")
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


JOURNAL_BLOCK = re.compile(r"<!-- journal -->\n(.*?)\n?<!-- /journal -->", re.S)


def cmd_journal(root, slug):
    """A feature branch never edits the journal (2026-10-24, the trial: two features appended to it, their PRs conflicted,
    and a hand-resolved conflict ended in a GREEN re-recorded with no review). Each task's block waits in its task file's
    Log; the row's close, on the base, copies them in task order. Idempotent: a block already there is skipped."""
    cfg = config(root)
    fdir = feature_folders(root, cfg).get(slug)
    if not fdir:
        die(f"no feature folder {slug!r}", 1)
    files = sorted(os.path.join(dp, f) for sub in ("tasks", os.path.join("tasks", "done")) for dp in [os.path.join(fdir, sub)]
                   if os.path.isdir(dp) for f in os.listdir(dp) if TASK_NAME_RE.match(f))
    blocks = [m.group(1).strip() for p in sorted(files, key=os.path.basename) for m in JOURNAL_BLOCK.finditer(read(p))]
    jpath = os.path.join(root, cfg.get("paths", {}).get("runlog", "docs/journal.md"))
    text = read(jpath) if os.path.isfile(jpath) else "# Journal\n"
    new = [b for b in blocks if b not in text]
    if new:
        write_text(jpath, text.rstrip("\n") + "\n\n" + "\n\n".join(new) + "\n")
    print(f"journal: {len(new)} block(s) appended, {len(blocks) - len(new)} already there")
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
    if "-h" in argv or "--help" in argv:   # 0.7 (2026-10-24): `footnote --help` wrote a footnote reading "--help"
        print(__doc__.strip())
        return 0
    repo = "."
    if "--repo" in argv:
        i = argv.index("--repo")
        repo = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    root = repo_root(repo)
    if not argv:
        die("usage: reef-queue.py status|ready [--all] [--with-found]|check|adr-number|index|footnote <text> [--row ID]|add-row --item <text> […]|set-depends ID <ids>|triage [--count]|note <text> [--row ID]|promote-note n<k> [--batch N]|set-batch ID N|drop-row ID --reason <text>|close ID --pr N|admit <issue>|set-priority ID p1|p2|p3|none|demote ID|migrate-to-issues [--apply] [--repo DIR]")
    cmd = argv[0]
    if cmd == "status":
        return cmd_status(root)
    if cmd == "ready":
        return cmd_ready(root, "--all" in argv, "--with-found" in argv)
    if cmd == "check":
        return cmd_check(root)
    if cmd == "adr-number":
        return cmd_adr_number(root)
    if cmd == "index":
        return cmd_index(root)
    if cmd == "journal" and len(argv) >= 2:
        return cmd_journal(root, argv[1])
    def opt(name, default=""):
        return argv[argv.index(name) + 1] if name in argv else default
    if cmd == "footnote" and len(argv) >= 2:
        return cmd_footnote(root, argv[1], opt("--row", None))
    if cmd == "add-row" and "--item" in argv:
        src = opt("--source", "planned")
        if src not in ("planned", "found"):
            die("--source is planned or found")
        if opt("--priority") not in ("",) + PRIORITIES:
            die("--priority is p1, p2 or p3")
        return cmd_add_row(root, opt("--item"), opt("--depends"), src, opt("--batch", None), opt("--admitted"), opt("--priority"))
    if cmd == "add-rows" and "--file" in argv:
        return cmd_add_rows(root, opt("--file"))
    if cmd == "set-depends" and len(argv) >= 3:
        return cmd_set_depends(root, argv[1], argv[2])
    if cmd == "triage":
        return cmd_triage(root, "--count" in argv)
    if cmd == "note" and len(argv) >= 2:
        return cmd_note(root, argv[1], opt("--row", None))
    if cmd == "promote-note" and len(argv) >= 2:
        return cmd_promote_note(root, argv[1], opt("--batch", None))
    if cmd == "set-batch" and len(argv) >= 3:
        return cmd_set_batch(root, argv[1], argv[2])
    if cmd == "close" and len(argv) >= 2 and "--pr" in argv:
        return cmd_close(root, argv[1], opt("--pr"))
    if cmd == "issue-row" and len(argv) >= 2:
        return cmd_issue_row(root, argv[1])
    if cmd == "row-issue" and len(argv) >= 2:
        return cmd_row_issue(root, argv[1])
    if cmd == "label-state" and len(argv) >= 2:
        return cmd_label_state(root, argv[1])
    if cmd == "admit" and len(argv) >= 2:
        if opt("--source", "planned") not in ("planned", "found") or opt("--priority") not in ("",) + PRIORITIES:
            die("--source is planned or found; --priority is p1, p2 or p3")
        return cmd_admit(root, argv[1], opt("--source", "planned"), opt("--batch", None), opt("--priority"))
    if cmd == "demote" and len(argv) >= 2:
        return cmd_demote(root, argv[1])
    if cmd == "set-priority" and len(argv) >= 3:
        return cmd_set_priority(root, argv[1], argv[2])
    if cmd == "ask" and len(argv) >= 2:
        return cmd_ask(root, argv[1], opt("--row", None), opt("--recommended"))
    if cmd == "answered" and len(argv) >= 3:
        return cmd_answered(root, argv[1], argv[2])
    if cmd == "next-id":
        return cmd_next_id(root)
    if cmd == "import-rows":
        return cmd_import_rows(root, "--apply" in argv)
    if cmd == "migrate-to-issues":
        return cmd_migrate(root, "--apply" in argv)
    if cmd == "drop-row" and len(argv) >= 2 and "--reason" in argv:
        return cmd_drop_row(root, argv[1], opt("--reason"))
    die(f"unknown command {cmd!r}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
