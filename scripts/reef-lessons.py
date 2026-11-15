#!/usr/bin/env python3
# CLASS: code
"""Reef lessons — the learning edge (hardening PR-3, docs/design/hardening-pr3-plan.md): a failure the loop survived becomes ONE
approved line in the file of the layer that reads it, and code counts whether its failure class comes back.

Usage:
  reef-lessons.py facts <id> [--repo DIR]            the candidate's facts (code's, never a transcript) and the draft command
  reef-lessons.py draft <id> "<layer>: <lesson>"     the model's ONE line, layer harness|loop|graph; any other shape is exit 2
  reef-lessons.py report [--repo DIR]                the `## Lessons` lines: drafts to approve, candidates to draft, landed
                                                     lessons with their recurrence, retirement proposals, each layer's cap
  reef-lessons.py lessons <layer> [--repo DIR]       the `lessons:` block of a layer's approved lines (what its reader is given)

Triggers (code, not this CLI): `reef-attempt` blocking a task on the same failure twice, and `reef-merge-close` closing a task
whose Log holds a FAIL; every FAIL and every close is also a ledger event. The owner approves `Approve lesson <id> at <16 hex>?`
and `Approve retiring lesson <id> at <16 hex>?` through reef-approval.py (the hook, or --owner in their terminal): it calls
approve() here, which lands or retires under `lessons.cap` (default 10 per layer). Records: .reef/approvals/lessons.jsonl (the
ledger), .reef/approvals/lesson-<id>[-retire].json (the owner's approval), reef/lessons/<layer>.md and reef/lessons/history.md.
"""
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # the shared helpers live beside this script
sys.dont_write_bytecode = True   # and no scripts/__pycache__ lands in a project's tree
from reef_common import main_checkout, read_config, repo_root, task_frontmatter, read, load_sibling, die as _die  # noqa: E402

LAYERS = ("harness", "loop", "graph")
READER = {"harness": "the implementer", "loop": "the orchestrator", "graph": "the planner"}
DEFAULTS = {"cap": 10, "recur": 2, "quiet_rows": 10}
MIN_CHARS, MAX_CHARS = 20, 160
ROUND_EXPECTED = "reef-claims.py round exits 0"
SETTLE_EXPECTED = "gate exit 0, the hand-back check ok, every judge PASS"
ROUND_KINDS = (("outside the task's files", "round-scope"), ("does not fail on the base", "round-not-red"),
               ("does not pass on the round's tree", "round-not-green"), ("ran no test", "round-no-test"),
               ("timed out", "round-timeout"), ("files: must be a list", "round-files-shape"))
SETTLE_KINDS = (("gate exit", "gate-red"), ("hand-back", "handback-rejected"), ("verifier report rejected", "report-rejected"),
                ("verifier:", "verifier-fail"), ("hunter:", "hunter-fail"), ("the tree changed", "tree-moved"),
                ("guard-pass record refused", "guard-pass"), ("task file missing", "task-missing"))
LINE = re.compile(r"^- (L\d+) · class (\S+) · sig (\S+) · landed (\d{4}-\d\d-\d\d) · (.+)$")
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f  ]")

die = lambda msg: _die(msg, prefix="lessons")


def now():
    t = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int(t % 1 * 1e6):06d}Z"


def home(start):
    """The main checkout of the project `start` lies in: the ledger and the layer files are its, never a worktree's."""
    return main_checkout(repo_root(start))


def ledger_path(root):
    return os.path.join(root, ".reef", "approvals", "lessons.jsonl")


def events(root):
    out = []
    try:
        with open(ledger_path(root), encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def append(root, ev):
    """One event, appended under the ledger's lock. A root without .reef/ is no Reef project: nothing is written."""
    if not os.path.isdir(os.path.join(root, ".reef")):
        return False
    p = ledger_path(root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return True


def state(root):
    """{id: candidate} folded from the ledger: its draft, its landing, its retirement."""
    out = {}
    for e in events(root):
        c = out.get(e.get("id"))
        if e.get("ev") == "candidate":
            out[e["id"]] = dict(e)
        elif c is not None and e.get("ev") == "draft":
            c.update(layer=e["layer"], lesson=e["lesson"], drafted_at=e["at"])
        elif c is not None and e.get("ev") == "landed":
            c.update(landed_at=e["at"], landed_layer=e["layer"])
        elif c is not None and e.get("ev") == "retired":
            c.update(retired_at=e["at"])
    return out


def config(root):
    cfg = read_config(root).get("lessons") or {}
    cfg = cfg if isinstance(cfg, dict) else {}
    out = {}
    for k, v in DEFAULTS.items():
        try:
            out[k] = max(1, int(cfg.get(k, v)))
        except (TypeError, ValueError):
            out[k] = v
    return out


def classes(fields):
    """The record's failure classes, a fixed vocabulary so a class recurs across tasks: the round check's refusals, graph
    settle's reasons, else the hash of the normalized EXPECTED (the same requirement failing again)."""
    exp = " ".join(fields.get("EXPECTED") or [])
    saw = fields.get("SAW") or []
    out = []
    if exp.startswith(ROUND_EXPECTED):
        for l in saw:
            if l.startswith("round: REFUSED — "):
                out.append(next((c for k, c in ROUND_KINDS if k in l), "round-other"))
    elif exp.startswith(SETTLE_EXPECTED):
        for l in saw:
            out += [next(c for k, c in SETTLE_KINDS if l.startswith(k))] if any(l.startswith(k) for k, _ in SETTLE_KINDS) else []
        out = out or ["settle-other"]
    if not out:
        norm = re.sub(r"\s+", " ", exp.lower()).strip()
        out = [f"expected-{hashlib.sha1(norm.encode()).hexdigest()[:8]}"]
    return list(dict.fromkeys(out))


def task_meta(path, text=None):
    text = read(path) if text is None else text
    fm = task_frontmatter(text) or {}
    tid = str(fm.get("id") or os.path.basename(path).split("-")[0])
    m = re.search(r"(?:^|/)features/([^/]+)/tasks/", os.path.realpath(path).replace(os.sep, "/"))
    return tid, str(fm.get("feature") or (m.group(1) if m else "")), fm


def record_fail(start, path, attempt, sig, fields):
    root = home(start)
    tid, feature, _ = task_meta(path)
    return append(root, {"ev": "fail", "at": now(), "task": tid, "feature": feature, "attempt": attempt, "sig": sig, "classes": classes(fields)})


def record_close(start, path):
    root = home(start)
    tid, feature, _ = task_meta(path)
    append(root, {"ev": "close", "at": now(), "task": tid, "feature": feature})


def attempt_module():
    return load_sibling("reef-attempt", "reef_attempt_for_lessons")


def trigger(start, path, kind, text=None, sig=None):
    """A candidate from the task's own records (trigger a: green-after-fail, b: same-failure); None when the task has no FAIL
    record or this (task, trigger, signature) has one already. Prints the facts the model drafts from."""
    root = home(start)
    if not os.path.isdir(os.path.join(root, ".reef")):
        return None
    text = read(path) if text is None else text
    tid, feature, fm = task_meta(path, text)
    am = attempt_module()
    recs = am.fail_records(text)
    if not recs:
        return None
    sig = sig or str(fm.get("last_failure_sig") or "").strip('"')
    last = recs[-1][2]
    fields = {"EXPECTED": [t for f, _, t in last if f == "EXPECTED"], "SAW": [t for f, _, t in last if f == "SAW"] or [recs[-1][1]]}
    st = state(root)
    if any(c.get("task") == tid and c.get("trigger") == kind and c.get("sig") == sig for c in st.values()):
        return None
    with open(ledger_path(root) + ".lock", "a") as lk:   # the id: one allocation at a time
        fcntl.flock(lk, fcntl.LOCK_EX)
        st = state(root)
        n = 1 + max([int(k[1:]) for k in st if re.fullmatch(r"L\d+", str(k))] or [0])
        lid = f"L{n}"
        facts = [l for l in am.dead_end_lines(text)[1:-1]]
        append(root, {"ev": "candidate", "id": lid, "at": now(), "trigger": kind, "task": tid, "feature": feature, "sig": sig,
                      "class": classes(fields)[0], "files": str(fm.get("files") or ""), "rounds": len(recs), "facts": facts})
    for line in facts_lines(root, lid):
        print(line)
    return lid


def facts_lines(root, lid):
    c = state(root).get(lid)
    if not c:
        return []
    return ([f"lesson {lid}: candidate ({c['trigger']}) — draft ONE line: python3 scripts/reef-lessons.py draft {lid} "
             f"\"<harness|loop|graph>: <the lesson>\" (harness: the implementer's round; loop: the orchestrator; graph: the plan's shape)",
             f"  task: {c['task']} (feature {c.get('feature') or '-'}) · rounds: {c.get('rounds')} FAIL"
             + (" before GREEN" if c["trigger"] == "green-after-fail" else ", the same failure twice")
             + f" · class: {c['class']} · sig: {c.get('sig') or '-'}"]
            + ([f"  files: {c['files']}"] if c.get("files") else []) + list(c.get("facts") or []) + [f"lesson {lid}: end"])


def draft(root, lid, text):
    c = state(root).get(lid)
    if not c:
        die(f"{lid} is not a candidate (reef-lessons.py report lists them); nothing written")
    if c.get("landed_at") or c.get("retired_at"):
        die(f"{lid} is already {'retired' if c.get('retired_at') else 'landed'}; nothing written")
    if "\n" in text.strip("\n") or "\r" in text:
        die("a lesson is one line; nothing written")
    text = text.strip()
    if CONTROL.search(text):
        die("a lesson carries no control character; nothing written")
    m = re.match(r"^(\w+):\s*(.*)$", text)
    if not m or m.group(1).lower() not in LAYERS:
        die("a lesson is `<layer>: <lesson>`, the layer harness, loop or graph; nothing written")
    layer, lesson = m.group(1).lower(), m.group(2).strip()
    if not MIN_CHARS <= len(lesson) <= MAX_CHARS:
        die(f"the lesson is {len(lesson)} characters — between {MIN_CHARS} and {MAX_CHARS}; nothing written")
    if lesson[0] in "#->|":
        die("the lesson is landed as a bullet: it does not start with #, -, > or |; nothing written")
    append(root, {"ev": "draft", "id": lid, "at": now(), "layer": layer, "lesson": lesson})
    c = state(root)[lid]
    print(f"lesson {lid}: drafted ({layer}) — the owner's question: {question(c, 'land')}")


def lesson_digest(c, action, layer=None, lesson=None, cls=None):
    parts = [action, c["id"], layer or c.get("landed_layer") or c.get("layer"), lesson or c.get("lesson")]
    return hashlib.sha256(json.dumps(parts + ([cls or c["class"]] if action == "land" else []), ensure_ascii=False).encode()).hexdigest()


def question(c, action):
    return f"Approve {'retiring ' if action == 'retire' else ''}lesson {c['id']} at {lesson_digest(c, action)[:16]}?"


def layer_file(root, layer):
    return os.path.join(root, "reef", "lessons", f"{layer}.md")


def file_lines(root, layer):
    try:
        return read(layer_file(root, layer)).splitlines()
    except OSError:
        return []


def record(root, lid, action="land"):
    try:
        with open(os.path.join(root, ".reef", "approvals", f"lesson-{lid}{'-retire' if action == 'retire' else ''}.json"), encoding="utf-8") as f:
            rec = json.load(f)
        return rec if isinstance(rec, dict) else {}
    except (OSError, ValueError):
        return {}


def approved(root, layer):
    """[(id, class, lesson)] of the layer file's lines whose landing record binds them, and [line] of the others (by hand)."""
    good, bad = [], []
    for l in file_lines(root, layer):
        m = LINE.match(l)
        if not m and not l.startswith("- "):
            continue
        rec = record(root, m.group(1)) if m else {}
        if m and rec.get("action") == "land" and rec.get("digest") == lesson_digest({"id": m.group(1)}, "land", layer, m.group(5), m.group(2)):
            good.append((m.group(1), m.group(2), m.group(5)))
        else:
            bad.append(l)
    return good, bad


def lessons_block(start, layer):
    """The `lessons:` block a layer's reader is given by code: its approved lines only."""
    root = home(start)
    good, _ = approved(root, layer)
    if not good:
        return []
    return ([f"lessons: {len(good)} landed ({layer}, reef/lessons/{layer}.md, approved by the owner) — pass every line through "
             f"`lessons: end` to {READER[layer]} verbatim"] + [f"  {i} ({c}): {t}" for i, c, t in good] + ["lessons: end"])


def write_layer(root, layer, lines):
    p = layer_file(root, layer)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    head = [f"# Lessons — {layer}", "", f"Read by {READER[layer]}. Written by scripts/reef-lessons.py on the owner's approval; "
            "a line edited by hand is not delivered.", "", "## Lessons"]
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        f.write("\n".join(head + lines) + "\n")
    os.replace(p + ".tmp", p)


def approve(root, action, lid, digest16):
    """The owner's approval of `Approve [retiring ]lesson <id> at <digest16>?`: (ok, message). Lands (under the cap) or retires;
    a stale digest, an undrafted or unknown id, a full layer: nothing written."""
    c = state(root).get(lid)
    if not c or not c.get("lesson"):
        return False, f"lesson {lid}: no draft to approve — nothing written"
    if action == "land" and (c.get("landed_at") or c.get("retired_at")):
        return False, f"lesson {lid}: already {'retired' if c.get('retired_at') else 'landed'} — nothing written"
    if action == "retire" and (not c.get("landed_at") or c.get("retired_at")):
        return False, f"lesson {lid}: not landed — nothing to retire, nothing written"
    dg = lesson_digest(c, action)
    if dg[:16] != digest16:
        return False, f"lesson {lid}: the question's digest {digest16} is not the {'draft' if action == 'land' else 'landed line'}'s ({dg[:16]}) (stale) — nothing written"
    layer = c.get("landed_layer") or c["layer"]
    lines = [l for l in file_lines(root, layer) if l.startswith("- ")]
    hp = os.path.join(root, "reef", "lessons", "history.md")
    touched = [os.path.relpath(layer_file(root, layer), root)] + (["reef/lessons/history.md"] if action == "retire" else [])
    if action == "land":
        lines = [l for l in lines if not l.startswith(f"- {lid} · ")]   # once, whatever an earlier cut-off run left
        cap = config(root)["cap"]
        if len(lines) >= cap:
            return False, f"lesson {lid}: layer {layer} holds {len(lines)}/{cap} lessons — retire one first (lessons.cap); nothing written"
        day = time.strftime("%Y-%m-%d", time.gmtime())
        write_layer(root, layer, lines + [f"- {lid} · class {c['class']} · sig {c.get('sig') or '-'} · landed {day} · {c['lesson']}"])
    else:
        m = recurrence(root, c)
        write_layer(root, layer, [l for l in lines if not l.startswith(f"- {lid} · ")])
        new = not os.path.isfile(hp)
        with open(hp, "a", encoding="utf-8") as f:
            f.write(("# Lessons — history\n\nEvery retired lesson, never deleted.\n\n" if new else "")
                    + f"- {time.strftime('%Y-%m-%d', time.gmtime())} retired {lid} ({layer}, class {c['class']}, recurred {m[0]} over {m[1]} rows, "
                    f"landed {c['landed_at'][:10]}): {c['lesson']}\n")
    d = os.path.join(root, ".reef", "approvals")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"lesson-{lid}{'-retire' if action == 'retire' else ''}.json"), "w", encoding="utf-8") as f:
        json.dump({"action": action, "digest16": dg[:16], "digest": dg, "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "by": "owner"}, f, indent=1)
        f.write("\n")
    # the owner's decision 6: no commit here — the AskUserQuestion hook has 30 s and the gate may not; the next tick commits
    append(root, {"ev": "landed" if action == "land" else "retired", "id": lid, "at": now(), "layer": layer, "digest16": dg[:16], "paths": touched})
    return True, (f"lesson {lid} landed in reef/lessons/{layer}.md" if action == "land" else
                  f"lesson {lid} retired from reef/lessons/{layer}.md (kept in reef/lessons/history.md)") + " — the next tick commits it"


def pending(root):
    """([landed/retired events no `committed` event covers], the last refusal's why or "") — the lesson files to commit."""
    done, out, why = set(), [], ""
    for e in events(root):
        if e.get("ev") in ("landed", "retired"):
            out.append(e)
        elif e.get("ev") == "committed":
            done |= {tuple(x) for x in e.get("items") or []}
            why = ""
        elif e.get("ev") == "commit-refused":
            why = str(e.get("why") or "")
    out = [e for e in out if (e["ev"], e["id"]) not in done]
    return out, (why if out else "")


def commit_pending(start):
    """The owner's decisions 5 and 6: on the tick, the approved lesson files written but not committed are committed — those
    paths alone, under the pre-commit gate. Idempotent; a refusal leaves the files and is logged for the report and the inbox."""
    root = home(start)
    if not os.path.isdir(os.path.join(root, ".reef")):
        return None
    todo, last = pending(root)
    if not todo:
        return None
    paths = list(dict.fromkeys(p for e in todo for p in e.get("paths") or []))
    items = [[e["ev"], e["id"]] for e in todo]
    st = subprocess.run(["git", "-C", root, "status", "--porcelain", "--untracked-files=all", "--", *paths], capture_output=True, text=True, timeout=60)
    if st.returncode == 0 and not st.stdout.strip():   # committed already (by hand, or a tick cut off after its commit)
        append(root, {"ev": "committed", "at": now(), "items": items, "paths": paths, "commit": "already"})
        return None
    subject = "reef: lessons " + ", ".join(f"{i} {ev}" for ev, i in items) + " — committed on the tick (the owner's approvals)"
    why = commit(root, [os.path.join(root, p) for p in paths], subject)
    if why:
        if why != last:   # said once per refusal, not once per tick
            append(root, {"ev": "commit-refused", "at": now(), "paths": paths, "why": why})
        return why
    append(root, {"ev": "committed", "at": now(), "items": items, "paths": paths})
    print(f"lessons: committed {', '.join(paths)} ({', '.join(f'{i} {ev}' for ev, i in items)})", file=sys.stderr)
    return None


def commit(root, paths, subject):
    """Commit these paths alone in the main checkout, under its pre-commit gate (like commit_plan, #370); None, or why not."""
    rel = [os.path.relpath(p, root) for p in paths]
    try:
        a = subprocess.run(["git", "-C", root, "add", "--", *rel], capture_output=True, text=True, timeout=60)
        if a.returncode != 0:
            return (a.stderr or a.stdout).strip()[-240:] or f"git add exit {a.returncode}"
        c = subprocess.run(["git", "-C", root, "commit", "-q", "-m", subject, "--", *rel], capture_output=True, text=True, timeout=1800)
    except (OSError, subprocess.SubprocessError) as e:
        return str(e)
    if c.returncode != 0:
        subprocess.run(["git", "-C", root, "reset", "-q", "--", *rel], capture_output=True, text=True, timeout=60)   # unstage what was added
        return (c.stderr or c.stdout).strip()[-240:] or f"git commit exit {c.returncode}"
    return None


def recurrence(root, c):
    """(recurrences of its class since it landed, distinct rows closed since)."""
    since = c.get("landed_at") or "~"
    evs = [e for e in events(root) if str(e.get("at", "")) > since]
    rec = sum(1 for e in evs if e.get("ev") == "fail" and c["class"] in (e.get("classes") or []))
    rows = {e.get("feature") or f"task {e.get('task')}" for e in evs if e.get("ev") == "close"}
    return rec, len(rows)


def report_lines(start):
    root = home(start)
    st, cfg = state(root), config(root)
    out = []
    for c in st.values():
        if c.get("retired_at") or c.get("landed_at"):
            continue
        if c.get("lesson"):
            out.append(f"- proposed: {c['id']} {c['layer']} — {c['lesson']} (class {c['class']}, from task {c['task']}, {c['trigger']}) — {question(c, 'land')}")
        else:
            out.append(f"- to draft: {c['id']} ({c['trigger']}, task {c['task']}, class {c['class']}) — python3 scripts/reef-lessons.py facts {c['id']}")
    for c in st.values():
        if c.get("landed_at") and not c.get("retired_at"):
            n, rows = recurrence(root, c)
            out.append(f"- landed: {c['id']} {c['landed_layer']} · {c['class']} · landed {c['landed_at'][:10]} · recurred {n} · {rows} rows since"
                       f" — to make room: {question(c, 'retire')}")
            why = (f"recurred {n} times since it landed: it does not work — turn it into a code check, or retire it" if n >= cfg["recur"] else
                   f"no recurrence over {rows} rows: the deletion test — retire it" if n == 0 and rows >= cfg["quiet_rows"] else "")
            if why:
                out.append(f"- retire? {c['id']} — {why} — {question(c, 'retire')}")
    todo, why = pending(root)
    if why:
        out.append(f"- not committed: {', '.join(dict.fromkeys(p for e in todo for p in e.get('paths') or []))} — {why} "
                   "(the next tick commits once the gate is green)")
    for layer in LAYERS:
        out += [f"- not approved (edited by hand, not delivered): reef/lessons/{layer}.md: {l}" for l in approved(root, layer)[1]]
    count = lambda layer: len([l for l in file_lines(root, layer) if l.startswith("- ")])
    out.append("- layers: " + " · ".join(f"{layer} {count(layer)}/{cfg['cap']}" for layer in LAYERS))
    return out


def owner_questions(start):
    """Every question the owner may answer now: a draft to land, a proposed retirement."""
    asks = [l for l in report_lines(start) if l.startswith(("- proposed: ", "- retire? "))]   # proposals only: a landed line's room-maker is the owner's pick
    return re.findall(r"Approve (?:retiring )?lesson L\d+ at [0-9a-f]{16}\?", "\n".join(asks))


def main(argv):
    repo = argv[argv.index("--repo") + 1] if "--repo" in argv and argv.index("--repo") + 1 < len(argv) else os.getcwd()
    args = [a for i, a in enumerate(argv) if a != "--repo" and (i == 0 or argv[i - 1] != "--repo")]
    root = home(repo)
    cmd = args[0] if args else ""
    if cmd == "facts" and len(args) == 2:
        lines = facts_lines(root, args[1])
        if not lines:
            die(f"{args[1]} is not a candidate")
        print("\n".join(lines))
    elif cmd == "draft" and len(args) >= 3:
        draft(root, args[1], " ".join(args[2:]) if len(args) > 3 else args[2])
    elif cmd == "report" and len(args) == 1:
        print("\n".join(report_lines(root)))
    elif cmd == "lessons" and len(args) == 2 and args[1] in LAYERS:
        print("\n".join(lessons_block(root, args[1])))
    else:
        print(__doc__.strip(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
