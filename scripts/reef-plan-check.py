#!/usr/bin/env python3
"""Reef plan check — the deterministic, blocking layer between plan approval and implementation.
Usage: reef-plan-check.py [repo-root] [--verify-stamp]
- Checks task files, ADRs, brief, and .reef/config.json for structural defects. No model, no network.
- One line per check: OK / FAIL: <what and where>. Exit 0 = all pass, 1 = at least one FAIL.
- On success writes <tasks>/.plan-review.json (sha256 over the plan artifacts + check count).
  The hash covers what PLANNING wrote, not what EXECUTION writes: task files are keyed by
  basename and stripped of status/attempts/last_failure_sig and the Log section, so completing
  a task does not invalidate the review — only editing the plan does.
  Never written on failure.
- --verify-stamp: recompute the hash, print one line, exit 0 = plan unchanged since last review,
  1 = changed or no stamp. reef-task runs this before its first dispatch.
Rule for the orchestrator: this script is deterministic; never argue with it, never work around it.
"""
import hashlib, json, os, re, subprocess, sys

STATUS = {"pending", "in-progress", "blocked", "done"}
COMPLEXITY = {"mech", "design"}
EFFORT = {"low", "medium", "high"}
VERIFY = {"judge", "gate-only"}
REQUIRED = ["id", "feature", "status", "complexity", "effort", "blocked-by", "verify", "attempts"]
TEST_RE = re.compile(r"test_[a-z0-9_]+")

results = []  # (ok, line)

def ok(line):
    results.append((True, f"OK   {line}"))

def fail(line):
    results.append((False, f"FAIL: {line}"))


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def parse_frontmatter(text):
    """Minimal YAML-subset parser for task frontmatter. Returns dict or raises ValueError."""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise ValueError("no frontmatter fence")
    fm = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"bad frontmatter line: {line!r}")
        key, _, val = line.partition(":")
        fm[key.strip()] = val.strip().strip('"')
    return fm


def parse_blocked_by(raw):
    raw = raw.strip()
    if not (raw.startswith("[") and raw.endswith("]")):
        raise ValueError(f"blocked-by not a list: {raw!r}")
    inner = raw[1:-1].strip()
    return [int(x) for x in inner.split(",")] if inner else []


def section(text, heading):
    """Body of '## <heading>' up to the next '## ' or EOF; None if absent."""
    m = re.search(rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    return m.group(1) if m else None


def criteria(text):
    """AC bullets as joined strings (continuation lines belong to their bullet)."""
    body = section(text, "Acceptance Criteria")
    if body is None:
        return None
    items = []
    for line in body.splitlines():
        if line.startswith("- "):
            items.append(line[2:])
        elif line.strip() and items:
            items[-1] += " " + line.strip()
    return items


def main():
    args = [a for a in sys.argv[1:] if a != "--verify-stamp"]
    verify_stamp = "--verify-stamp" in sys.argv[1:]
    if args:
        root = args[0]
    else:
        p = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        if p.returncode != 0:
            print("FAIL: not a git repo and no repo-root given")
            sys.exit(1)
        root = p.stdout.strip()

    cfg_path = os.path.join(root, ".reef", "config.json")
    try:
        cfg = json.loads(read(cfg_path))
    except Exception as e:
        print(f"FAIL: cannot read {cfg_path}: {e}")
        sys.exit(1)
    paths = cfg.get("paths", {})
    tasks_dir = os.path.join(root, paths.get("tasks", "tasks"))
    adr_dir = os.path.join(root, paths.get("adr", "docs/adr"))
    glossary = os.path.join(root, paths.get("glossary", "docs/glossary.md"))
    brief = next((os.path.join(root, b) for b in ("CLAUDE.md", "AGENTS.md")
                  if os.path.isfile(os.path.join(root, b))), None)
    stamp_path = os.path.join(tasks_dir, ".plan-review.json")

    # ---- collect plan artifacts (task files incl. done/, ADRs, glossary, brief, config)
    task_files = []
    for d in (tasks_dir, os.path.join(tasks_dir, "done")):
        if os.path.isdir(d):
            task_files += [os.path.join(d, f) for f in os.listdir(d)
                           if re.match(r"\d+-.*\.md$", f)]
    task_files.sort()
    adr_files = sorted(os.path.join(adr_dir, f) for f in os.listdir(adr_dir)
                       if f.endswith(".md")) if os.path.isdir(adr_dir) else []
    artifacts = task_files + adr_files + [p for p in (glossary, brief, cfg_path)
                                          if p and os.path.isfile(p)]

    def stamp_key(p):
        """Task files are keyed by BASENAME, not path: completing a task moves it to done/,
        which changes the plan not at all."""
        return os.path.basename(p) if p in task_files else os.path.relpath(p, root)

    def stamp_body(p):
        """Strip what EXECUTION writes, keep what PLANNING wrote. Otherwise every commit
        invalidates the review and the semantic pass gets paid for on every task."""
        raw = open(p, "rb").read()
        if p not in task_files:
            return raw
        text = raw.decode("utf-8", "replace")
        text = text.split("\n## Log", 1)[0]
        text = re.sub(r"^(status|attempts|last_failure_sig):.*$", "", text, flags=re.M)
        return text.encode()

    h = hashlib.sha256()
    for p in sorted(artifacts, key=stamp_key):
        h.update(stamp_key(p).encode() + b"\0")
        h.update(stamp_body(p) + b"\0")
    digest = h.hexdigest()

    if verify_stamp:
        try:
            stamp = json.loads(read(stamp_path))
        except Exception:
            print("stamp: MISSING — run reef-plan-check.py (plan never reviewed, or review failed)")
            sys.exit(1)
        if stamp.get("sha256") == digest:
            print("stamp: MATCH — plan unchanged since last review")
            sys.exit(0)
        print("stamp: STALE — plan artifacts changed since last review; re-review required")
        sys.exit(1)

    # ---- per-task parse + checks, ordered by file
    tasks = {}          # path -> frontmatter (only files that parsed)
    ids = {}            # id -> [paths]
    test_owners = {}    # test name -> [paths]
    manual = 0
    for path in task_files:
        rel = os.path.relpath(path, root)
        try:
            text = read(path)
            fm = parse_frontmatter(text)
        except Exception as e:
            fail(f"{rel}: unparseable ({e})")
            continue
        errs = [k for k in REQUIRED if k not in fm]
        for key, legal in (("status", STATUS), ("complexity", COMPLEXITY),
                           ("effort", EFFORT), ("verify", VERIFY)):
            if key in fm and fm[key] not in legal:
                errs.append(f"{key}={fm[key]!r} not in {sorted(legal)}")
        for key in ("id", "attempts"):
            if key in fm and not re.fullmatch(r"-?\d+", fm[key]):
                errs.append(f"{key}={fm[key]!r} not an integer")
        try:
            fm["_blocked"] = parse_blocked_by(fm.get("blocked-by", "[]"))
        except Exception as e:
            errs.append(str(e))
            fm["_blocked"] = []
        if errs:
            fail(f"{rel}: schema — " + "; ".join(errs))
        else:
            ok(f"{rel}: schema")
        if "id" in fm and re.fullmatch(r"-?\d+", fm.get("id", "")):
            tid = int(fm["id"])
            fm["_id"] = tid
            ids.setdefault(tid, []).append(rel)
            prefix = re.match(r"(\d+)-", os.path.basename(path)).group(1)
            if int(prefix) == tid:
                ok(f"{rel}: filename prefix matches id {tid}")
            else:
                fail(f"{rel}: filename prefix {prefix} != id {tid}")
        fm["_text"] = text
        tasks[rel] = fm

    if not task_files:
        fail(f"no task files found in {os.path.relpath(tasks_dir, root)}")

    # id uniqueness
    dupes = {i: ps for i, ps in ids.items() if len(ps) > 1}
    if dupes:
        fail("duplicate task ids — " + "; ".join(f"id {i}: {', '.join(ps)}" for i in sorted(dupes) for ps in [dupes[i]]))
    elif ids:
        ok("task ids unique")

    # blocked-by refs + cycle detection
    known = set(ids)
    graph = {}
    bad_ref = False
    for rel, fm in tasks.items():
        if "_id" not in fm:
            continue
        missing = [b for b in fm["_blocked"] if b not in known]
        if missing:
            fail(f"{rel}: blocked-by refers to missing task id(s) {missing}")
            bad_ref = True
        graph[fm["_id"]] = [b for b in fm["_blocked"] if b in known]
    if not bad_ref and tasks:
        ok("blocked-by references resolve (tasks/ + done/)")

    state, cycle = {}, None
    def visit(n, stack):
        nonlocal cycle
        state[n] = 1
        for m_ in graph.get(n, []):
            if state.get(m_) == 1:
                cycle = cycle or stack[stack.index(m_):] + [m_]
            elif state.get(m_, 0) == 0:
                visit(m_, stack + [m_])
        state[n] = 2
    for n in graph:
        if state.get(n, 0) == 0 and not cycle:
            visit(n, [n])
    if cycle:
        fail("dependency cycle: " + " -> ".join(map(str, cycle)))
    elif graph:
        ok("no dependency cycles")

    # per-task semantic checks, ordered by file
    for rel, fm in sorted(tasks.items()):
        text = fm["_text"]
        if fm.get("complexity") == "design":
            dec = section(text, "Decision")
            if dec is None or not dec.strip():
                fail(f"{rel}: complexity design but ## Decision is empty/missing")
            else:
                ok(f"{rel}: design has non-empty ## Decision")
            if fm.get("verify") != "judge":
                fail(f"{rel}: complexity design requires verify: judge (got {fm.get('verify')!r})")
            else:
                ok(f"{rel}: design -> verify: judge")
        elif fm.get("complexity") == "mech":
            if fm.get("verify") != "gate-only":
                fail(f"{rel}: complexity mech requires verify: gate-only (got {fm.get('verify')!r})")
            else:
                ok(f"{rel}: mech -> verify: gate-only")

        crits = criteria(text)
        if crits is None:
            fail(f"{rel}: no ## Acceptance Criteria section")
            continue
        untested = []
        for c in crits:
            if "HUMAN AC" in c:
                manual += 1
                continue
            names = TEST_RE.findall(c)
            if not names:
                untested.append(c[:60])
            for n in names:
                test_owners.setdefault(n, set()).add(rel)
        if untested:
            fail(f"{rel}: criterion names no test_ identifier and is not HUMAN AC — " +
                 "; ".join(f"{c!r}" for c in untested))
        else:
            ok(f"{rel}: every criterion names a test or is HUMAN AC")
    print_manual = f"manual criteria: {manual}"

    claimed_twice = {n: ps for n, ps in test_owners.items() if len(ps) > 1}
    if claimed_twice:
        fail("test name claimed by two task files — " +
             "; ".join(f"{n}: {', '.join(sorted(ps))}" for n, ps in sorted(claimed_twice.items())))
    elif test_owners:
        ok("no test name claimed by two task files")

    # config, ADRs, brief
    gate = cfg.get("gates", {}).get("test", "")
    if isinstance(gate, str) and gate.strip():
        ok(f".reef/config.json: gates.test = {gate!r}")
    else:
        fail(".reef/config.json: gates.test is empty — no deterministic gate")

    if not adr_files:
        fail(f"no ADR found under {os.path.relpath(adr_dir, root)}")
    else:
        proposed = [os.path.relpath(p, root) for p in adr_files
                    if re.search(r"^Status:\s*Proposed\s*$", read(p), re.M)]
        if proposed:
            fail("ADR still Proposed (a settled plan has only Accepted): " + ", ".join(proposed))
        else:
            ok(f"{len(adr_files)} ADR(s), none Proposed")

    if brief is None:
        fail("no project brief (CLAUDE.md or AGENTS.md) at repo root")
    else:
        rel = os.path.relpath(brief, root)
        open_h = [l for l in read(brief).splitlines() if re.match(r"^#+ .*\bOpen\b", l)]
        if open_h:
            fail(f"{rel}: 'Open' heading remains — a settled plan leaves no open questions: {open_h[0]!r}")
        else:
            ok(f"{rel}: no 'Open' heading")

    # report
    for _, line in results:
        print(line)
    print(print_manual)
    failed = sum(1 for okd, _ in results if not okd)
    print(f"{len(results)} checks, {failed} failed")
    if failed:
        sys.exit(1)
    with open(stamp_path, "w") as f:
        json.dump({"sha256": digest, "checks": len(results)}, f, indent=2)
        f.write("\n")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"FAIL: internal error: {e}")
        sys.exit(1)
