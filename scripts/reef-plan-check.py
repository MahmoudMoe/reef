#!/usr/bin/env python3
"""Reef plan check — the deterministic, blocking layer between plan approval and implementation.
Usage: reef-plan-check.py [repo-root] [--verify-stamp [--feature SLUG]]
- Checks task files, ADRs, brief, and .reef/config.json for structural defects. No model, no network.
- One line per check: OK / FAIL: <what and where>. Exit 0 = all pass, 1 = at least one FAIL.
  On success the last line names the plan-reviewer's model (roles.plan_reviewer, default fable).
- On success writes <tasks>/.plan-review.json: one sha256 PER FEATURE over that feature's task
  files plus the ADRs, and the check count. The stamp is per-worktree state and must be
  gitignored (a tracked stamp is a FAIL). The hash covers what PLANNING wrote, not what
  EXECUTION writes: task files are keyed by basename and stripped of status/attempts/
  last_failure_sig and the Log section, so completing a task does not invalidate the review —
  only editing the plan does. Other features' tasks, the brief, the glossary and the config are
  NOT hashed: merging the integration branch changes them without changing this feature's plan.
  Never written on failure.
- --verify-stamp: recompute, print one line, exit 0 = unchanged since last review, 1 = changed
  or no stamp. With --feature SLUG only that feature is compared (the guard passes the
  dispatched task's feature); without it every feature present must match.
Rule for the orchestrator: this script is deterministic; never argue with it, never work around it.
"""
import hashlib, json, os, re, subprocess, sys

STATUS = {"pending", "in-progress", "blocked", "done"}
COMPLEXITY = {"mech", "design"}
EFFORT = {"low", "medium", "high"}
VERIFY = {"judge", "gate-only"}
TIER = {"light", "full", "design"}       # effort matched to risk; mech <=> light (design §4)
REQUIRED = ["id", "feature", "status", "complexity", "effort", "blocked-by", "verify", "attempts"]
# Test-name conventions across the stacks reef-init advertises. Left/right anchored so
# prose like "latest_figures" cannot satisfy the gate. Overridable via .reef/config.json
# plan.test_re for stacks/conventions not covered here.
DEFAULT_TEST_RE = (
    r"(?<![A-Za-z0-9_])test_[a-z0-9_]+"            # pytest
    r"|(?<![A-Za-z0-9_])Test[A-Z][A-Za-z0-9_]*"    # Go
    # Rust paths must mention 'test' in a segment — a bare foo::bar would let prose
    # like std::vec or tokio::spawn satisfy the gate vacuously
    r"|(?<![A-Za-z0-9_:])[a-z0-9_]*test[a-z0-9_]*::[a-z0-9_]+"
    r"|(?<![A-Za-z0-9_:])[a-z0-9_]+::[a-z0-9_]*test[a-z0-9_]*"
    r"|(?:\bit|\btest|\bdescribe)\((['\"]).+?\1\)"  # Jest/Vitest it('...')/test("...")
)
TASK_NAME_RE = re.compile(r"(R?)(\d+)-.*\.md$")     # NNN-slug.md and rollup RNN-slug.md
FM_RE = re.compile(r"\A(---\r?\n.*?\r?\n---\r?\n)", re.S)

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
        key = key.strip()
        if key in fm:
            # duplicate keys read DIFFERENTLY across the three readers (first-wins vs
            # last-wins) — that ambiguity is how a blocked task smuggles past the cap
            raise ValueError(f"duplicate frontmatter key {key!r}")
        fm[key] = val.strip().strip('"')
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


# CommonMark: 0-3 leading spaces is still a sibling list item; 4+ is continuation/code
BULLET = re.compile(r"^ {0,3}[-*+] +|^ {0,3}\d+[.)] +")
LOG_HEADING = re.compile(r"^##[ \t]+[Ll][Oo][Gg][ \t]*$", re.M)


def criteria(text):
    """AC bullets as joined strings (continuation lines belong to their bullet).
    Accepts -, *, + and numbered bullets so a legal list is never invisibly skipped."""
    body = section(text, "Acceptance Criteria")
    if body is None:
        return None
    items = []
    for line in body.splitlines():
        m = BULLET.match(line)
        if m:
            items.append(line[m.end():])
        elif line.strip() and items:
            items[-1] += " " + line.strip()
    return items


def strip_comments(s):
    return re.sub(r"<!--.*?-->", "", s, flags=re.S)


MERGE_BY = ("human", "loop")
FEATURE_GATE = ("ci", "local")


def parse_args(argv):
    verify, feature, args = False, None, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--verify-stamp":
            verify = True
        elif a == "--feature":
            if i + 1 >= len(argv) or not argv[i + 1].strip():
                print("FAIL: --feature requires a feature slug")
                sys.exit(1)
            feature = argv[i + 1].strip()
            i += 1
        elif a.startswith("--feature="):
            feature = a.split("=", 1)[1].strip()
        elif a.startswith("-"):
            print(f"FAIL: unknown option {a!r}")   # never let a typo become the repo root
            sys.exit(1)
        else:
            args.append(a)
        i += 1
    return verify, feature, args


def fm_value(text, key):
    """One frontmatter value, read the way reef-attempt reads it (column 0, first wins)."""
    m = FM_RE.match(text)
    if not m:
        return ""
    v = re.search(rf"^{re.escape(key)}:[ \t]*(.*)$", m.group(1), re.M)
    return v.group(1).strip().strip('"') if v else ""


def main():
    verify_stamp, feature_filter, args = parse_args(sys.argv[1:])
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
    brief = next((os.path.join(root, b) for b in ("CLAUDE.md", "AGENTS.md")
                  if os.path.isfile(os.path.join(root, b))), None)
    stamp_path = os.path.join(tasks_dir, ".plan-review.json")

    test_re = re.compile(cfg.get("plan", {}).get("test_re", "") or DEFAULT_TEST_RE)
    max_words = cfg.get("plan", {}).get("max_words", 0) or 0
    if not isinstance(max_words, int) or isinstance(max_words, bool) or max_words < 0:
        fail(f".reef/config.json: plan.max_words {max_words!r} is not a non-negative integer")
        max_words = 0

    # ---- collect plan artifacts (task files incl. done/ and rollups, ADRs)
    task_files, strays = [], []
    for d in (tasks_dir, os.path.join(tasks_dir, "done")):
        if os.path.isdir(d):
            for f in os.listdir(d):
                if TASK_NAME_RE.match(f):
                    task_files.append(os.path.join(d, f))
                elif f.endswith(".md"):
                    strays.append(os.path.relpath(os.path.join(d, f), root))
    task_files.sort()
    if strays:
        # a misnamed file would be invisible to every check AND to the stamp — refuse that
        fail("task file(s) not matching NNN-slug.md / RNN-slug.md (invisible to checks + stamp): " + ", ".join(sorted(strays)))
    basenames = {}
    for p in task_files:
        basenames.setdefault(os.path.basename(p), []).append(p)
    for b, ps in sorted(basenames.items()):
        if len(ps) > 1:
            fail(f"same task filename in tasks/ and tasks/done/ (stamp keys by basename): {b}")
    adr_files = sorted(os.path.join(adr_dir, f) for f in os.listdir(adr_dir)
                       if f.endswith(".md")) if os.path.isdir(adr_dir) else []
    # Rollups (R<NN>) are EXECUTION artifacts written by reef-review mid-run; they get
    # every structural check but must never enter the stamp — creating one would stale
    # the plan and deny the very dispatch it was created for.
    stamp_tasks = [p for p in task_files if not os.path.basename(p).startswith("R")]
    stamp_task_set = set(stamp_tasks)

    def stamp_key(p):
        """Task files are keyed by BASENAME, not path: completing a task moves it to done/,
        which changes the plan not at all."""
        return os.path.basename(p) if p in stamp_task_set else os.path.relpath(p, root)

    def stamp_body(p):
        """Strip what EXECUTION writes, keep what PLANNING wrote. Otherwise every commit
        invalidates the review and the semantic pass gets paid for on every task.
        The Log cut requires the exact '## Log' heading ('## Login' is plan content),
        and the key strip removes WHOLE LINES and only inside the frontmatter — a body
        line that happens to start with 'status:' is plan content too."""
        raw = open(p, "rb").read()
        if p not in stamp_task_set:
            return raw
        text = raw.decode("utf-8", "replace")
        # cut at the Log heading in any case/spacing — a '## log' variant would
        # otherwise hash the log body and stale the plan on the first log append
        text = LOG_HEADING.split(text, maxsplit=1)[0]
        m = FM_RE.match(text)
        if m:
            fm = re.sub(r"^(status|attempts|last_failure_sig|dispatches|worktree):.*(?:\r?\n|\Z)", "",
                        m.group(1), flags=re.M)
            text = fm + text[m.end():]
        return text.encode()

    # one digest PER FEATURE: that feature's task files + every ADR. A task whose feature:
    # cannot be read lands in the "" bucket, which is still hashed (never invisible).
    by_feature = {}
    for p in stamp_tasks:
        try:
            feat = fm_value(read(p), "feature")
        except (OSError, UnicodeDecodeError):
            feat = ""
        by_feature.setdefault(feat, []).append(p)

    def digest_for(feat):
        h = hashlib.sha256()
        for p in sorted(by_feature.get(feat, []) + adr_files, key=stamp_key):
            h.update(stamp_key(p).encode() + b"\0")
            h.update(stamp_body(p) + b"\0")
        return h.hexdigest()

    digests = {feat: digest_for(feat) for feat in by_feature}

    if verify_stamp:
        try:
            stamp = json.loads(read(stamp_path))
            stamped = stamp["features"]
            if not isinstance(stamped, dict):
                raise ValueError("features is not a mapping")
        except Exception:
            print("stamp: MISSING — run reef-plan-check.py (plan never reviewed, review failed, "
                  "or a pre-0.4 stamp)")
            sys.exit(1)
        if feature_filter is not None:
            same = feature_filter in stamped and stamped[feature_filter] == digest_for(feature_filter)
            scope = f"feature {feature_filter!r}"
        else:
            same = stamped == digests
            scope = "every feature"
        if same:
            print(f"stamp: MATCH — plan unchanged since last review ({scope})")
            sys.exit(0)
        print(f"stamp: STALE — plan artifacts changed since last review ({scope}); re-review required")
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
                           ("effort", EFFORT), ("verify", VERIFY), ("tier", TIER)):
            if key in fm and fm[key] not in legal:
                errs.append(f"{key}={fm[key]!r} not in {sorted(legal)}")
        if "id" in fm and not re.fullmatch(r"R?\d+", fm["id"]):
            errs.append(f"id={fm['id']!r} not NNN or RNN")
        if "attempts" in fm and not re.fullmatch(r"\d+", fm["attempts"]):
            errs.append(f"attempts={fm['attempts']!r} not a non-negative integer (a negative value would multiply the retry cap)")
        if "dispatches" in fm and not re.fullmatch(r"\d+", fm["dispatches"]):
            errs.append(f"dispatches={fm['dispatches']!r} not a non-negative integer (a negative value would disable the runaway backstop)")
        try:
            fm["_blocked"] = parse_blocked_by(fm.get("blocked-by", "[]"))
        except Exception as e:
            errs.append(str(e))
            fm["_blocked"] = []
        res = fm.get("resources", "[]").strip()
        if not (res.startswith("[") and res.endswith("]")):
            errs.append(f"resources not a list: {res!r}")
        # the tier is the risk the plan DECLARED; a cheap tier on a design task is the
        # mismatch this check exists for (mech <=> light; design is full or design)
        tier, cx = fm.get("tier"), fm.get("complexity")
        if tier == "light" and cx == "design":
            errs.append("tier light on a design task (light <=> mech only)")
        if tier in ("full", "design") and cx == "mech":
            errs.append(f"tier {tier} on a mech task (mech <=> light; make it design or lower the tier)")
        if errs:
            fail(f"{rel}: schema — " + "; ".join(errs))
        else:
            ok(f"{rel}: schema")
        if "id" in fm and re.fullmatch(r"R?\d+", fm.get("id", "")):
            raw_id = fm["id"]
            fname = TASK_NAME_RE.match(os.path.basename(path))
            expect = fname.group(1) + str(int(fname.group(2)))
            canon = ("R" + str(int(raw_id[1:]))) if raw_id.startswith("R") else str(int(raw_id))
            if not raw_id.startswith("R"):
                fm["_id"] = int(raw_id)          # only numeric ids join the blocked-by graph
            ids.setdefault(canon, []).append(rel)
            if canon == expect:
                ok(f"{rel}: filename prefix matches id {canon}")
            else:
                fail(f"{rel}: filename prefix {fname.group(1)}{fname.group(2)} != id {raw_id}")
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

    # blocked-by refs + cycle detection (numeric ids only; rollups take no dependents)
    known = {int(k) for k in ids if not k.startswith("R")}
    graph = {}
    bad_ref = False
    for rel, fm in tasks.items():
        # every task's refs are validated — a rollup's blocked-by can dangle too
        missing = [b for b in fm.get("_blocked", []) if b not in known]
        if missing:
            fail(f"{rel}: blocked-by refers to missing task id(s) {missing}")
            bad_ref = True
        if "_id" in fm:
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
        # the stamp ignores everything after ## Log — so nothing but log content may
        # live there, or a plan section could be edited invisibly after approval
        log_parts = LOG_HEADING.split(text, maxsplit=1)
        if len(log_parts) == 2 and re.search(r"^##[ \t]", log_parts[1], re.M):
            fail(f"{rel}: ## Log must be the LAST section — the stamp ignores everything after it")
        if max_words:
            plan_text = log_parts[0]
            fmm = FM_RE.match(plan_text)
            words = len(re.findall(r"\S+", plan_text[fmm.end():] if fmm else plan_text))
            if words > max_words:
                fail(f"{rel}: {words} words > plan.max_words {max_words} (the Log does not count) — split the slice")
        if fm.get("complexity") == "design":
            dec = section(text, "Decision")
            # comments don't count: the untouched template placeholder is an HTML comment,
            # and this check exists precisely to force the HUMAN to write the Decision
            if dec is None or not strip_comments(dec).strip():
                fail(f"{rel}: complexity design but ## Decision has no human-written content")
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
        if not crits:
            # an empty list must never pass vacuously as "every criterion is covered"
            fail(f"{rel}: ## Acceptance Criteria has no criteria bullets")
            continue
        untested, automated = [], 0
        for c in crits:
            if c.startswith("HUMAN AC"):        # opt-out marker only counts at bullet start
                if fm.get("verify") == "gate-only":
                    fail(f"{rel}: HUMAN AC on a gate-only (mech) task — nothing would ever check it")
                manual += 1
                continue
            names = [m.group(0) for m in test_re.finditer(c)]
            if not names:
                untested.append(c[:60])
            else:
                automated += 1
            for n in names:
                test_owners.setdefault(n, set()).add(rel)
        if untested:
            fail(f"{rel}: criterion names no test identifier and is not HUMAN AC — " +
                 "; ".join(f"{c!r}" for c in untested))
        elif automated == 0:
            fail(f"{rel}: every criterion is HUMAN AC — no failing test = no task")
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
    gates = cfg.get("gates", {}) if isinstance(cfg.get("gates", {}), dict) else {}
    def gate_cmd(key):
        v = gates.get(key, "")
        return v.strip() if isinstance(v, str) else ""
    # same resolution as scripts/reef-gate.sh: full -> gates.full > gates.test (legacy alias)
    full = gate_cmd("full") or gate_cmd("test")
    if full:
        ok(f".reef/config.json: full gate = {full!r}" + ("" if gate_cmd("full") else " (legacy gates.test)"))
    else:
        fail(".reef/config.json: gates.full (or legacy gates.test) is empty — no deterministic gate")

    def setting(section, key, default):
        sec = cfg.get(section, {})
        v = sec.get(key, default) if isinstance(sec, dict) else default
        return v if v not in ("", None) else default
    merge_by = setting("merge", "by", "human")
    feature_gate = setting("ci", "feature_gate", "ci")
    base = setting("branches", "base", "main")
    release = setting("branches", "release", "main")
    bad = []
    if merge_by not in MERGE_BY:
        bad.append(f"merge.by {merge_by!r} not in {list(MERGE_BY)}")
    if feature_gate not in FEATURE_GATE:
        bad.append(f"ci.feature_gate {feature_gate!r} not in {list(FEATURE_GATE)}")
    for name, v in (("branches.base", base), ("branches.release", release)):
        if not isinstance(v, str) or not v.strip():
            bad.append(f"{name} {v!r} is not a branch name")
    if merge_by == "loop" and base == release:
        bad.append(f"merge.by 'loop' with branches.base == branches.release ({base!r}) — the loop "
                   "would merge into the release branch; releases are merged by the human. "
                   "Set branches.base to the integration branch")
    if bad:
        fail(".reef/config.json: " + "; ".join(bad))
    else:
        ok(f".reef/config.json: merge.by={merge_by} ci.feature_gate={feature_gate} "
           f"branches.base={base} branches.release={release}")

    # the stamp is per-worktree state: tracked, it travels across branches and conflicts
    try:
        tr = subprocess.run(["git", "-C", root, "ls-files", "--error-unmatch", "--",
                             os.path.relpath(stamp_path, root)], capture_output=True, text=True)
        tracked = tr.returncode == 0
    except Exception:
        tracked = False
    if tracked:
        fail(f"{os.path.relpath(stamp_path, root)} is tracked by git — it is per-worktree state: "
             "`git rm --cached` it and add it to .gitignore")

    if not adr_files:
        # reef-plan makes the ADR optional ("at most ONE ... if it has non-obvious
        # decisions"); demanding one unconditionally deadlocks every fresh bootstrap
        ok("no ADRs (reef-plan treats the ADR as optional)")
    else:
        def strip_fences(text):
            out, fenced = [], False
            for l in text.splitlines():
                if l.lstrip().startswith("```"):
                    fenced = not fenced
                    continue
                if not fenced:
                    out.append(l)
            return "\n".join(out)

        def adr_status(text):
            """Status value in either layout — a '## Status' heading with the value on
            the next non-blank line (Nygard/MADR) takes precedence over an inline
            'Status: X' line; fenced code (e.g. a quoted template) never counts.
            Returns None when the ADR states no status at all."""
            text = strip_fences(text)
            lines = text.splitlines()
            for i, l in enumerate(lines):
                if re.match(r"^#+\s*Status\s*$", l, re.I):
                    for nxt in lines[i + 1:]:
                        if nxt.strip():
                            return nxt.strip()
            m = re.search(r"^\**Status\**:[ \t]*(\S.*)$", text, re.M | re.I)
            return m.group(1).strip() if m else None

        proposed, unchosen, missing_status, drafts = [], [], [], 0
        for p in adr_files:
            rel = os.path.relpath(p, root)
            # draft-<item>-<slug>.md: a parallel item's ADR, numbered at merge — it may still
            # be Proposed; a missing status or the untouched placeholder still fails
            is_draft = os.path.basename(p).startswith("draft-")
            drafts += is_draft
            status = adr_status(read(p))
            if status is None:
                missing_status.append(rel)    # an undecided ADR must not pass as settled
                continue
            words = re.findall(r"\b(proposed|accepted|superseded)\b", status, re.I)
            if len({w.lower() for w in words}) > 1 and "|" in status:
                unchosen.append(rel)          # template placeholder line left untouched
            elif words and words[0].lower() == "proposed" and not is_draft:
                proposed.append(rel)          # first word decides: 'Accepted (was Proposed)' is accepted
        if missing_status:
            fail("ADR states no Status at all (a settled plan has only Accepted): " + ", ".join(missing_status))
        if unchosen:
            fail("ADR status is still the template placeholder (pick one): " + ", ".join(unchosen))
        if proposed:
            fail("ADR still Proposed (a settled plan has only Accepted): " + ", ".join(proposed))
        if not (missing_status or unchosen or proposed):
            ok(f"{len(adr_files)} ADR(s), none Proposed" + (f" (drafts exempt: {drafts})" if drafts else ""))

    if brief is None:
        fail("no project brief (CLAUDE.md or AGENTS.md) at repo root — reef-init scaffolds one")
    else:
        rel = os.path.relpath(brief, root)
        # scan headings outside fenced code blocks, case-insensitively; only headings that
        # actually mean "unsettled" count ('OpenAPI notes' is not an open question)
        open_h, fenced = [], False
        for l in read(brief).splitlines():
            if l.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                continue
            if re.match(r"^#+\s+open\s*$", l, re.I) or \
               re.match(r"^#+\s.*\bopen\s+(questions?|issues?|items?|points?|topics?|threads?)\b", l, re.I):
                open_h.append(l)
        if open_h:
            fail(f"{rel}: open-questions heading remains — a settled plan leaves none: {open_h[0]!r}")
        else:
            ok(f"{rel}: no open-questions heading")

    # report
    for _, line in results:
        print(line)
    print(print_manual)
    failed = sum(1 for okd, _ in results if not okd)
    print(f"{len(results)} checks, {failed} failed")
    if failed:
        sys.exit(1)
    with open(stamp_path, "w") as f:
        json.dump({"features": digests, "checks": len(results)}, f, indent=2, sort_keys=True)
        f.write("\n")
    roles = cfg.get("roles", {}) if isinstance(cfg.get("roles", {}), dict) else {}
    print(f"plan-reviewer: model={roles.get('plan_reviewer') or 'fable'}")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"FAIL: internal error: {e}")
        sys.exit(1)
