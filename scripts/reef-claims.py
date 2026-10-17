#!/usr/bin/env python3
# CLASS: code
"""Reef claims — a fix round's sentences bound to its own diff, and "nothing after GREEN".

Usage:
  reef-claims.py check <base>..<head> <claims-file> [--repo DIR]
      Every non-empty line of the claims file is "<sentence> — true at <path>:<line>[-<line>]".
      Each must point INSIDE this round's diff: a file the range changed, a line the range
      added. Exit 1 listing every claim that does not, and when the list is empty while the
      diff added lines (a fix round ends with a claims list, covering only that round).
  reef-claims.py check --handback <file> [--repo DIR]            (0.6, 2.7)
      The implementer's hand-back: at most writing.handback_words (150) words and a claims list (at least
      one well-formed claim line). Over the cap or without claims: exit 1 — reef-task re-dispatches once
      with "shorten, evidence only"; no attempt is consumed.
  reef-claims.py report <file> --task <task-file> [--repo DIR]      (0.6, 2.7)
      A verifier's or hunter's report: the `RUN:` header, one `RULE AC<n>` line per criterion of the task
      (citing its Proof row's test or command when the task has a ## Proof table), evidence per AC
      (a path:line, a test name or a command) on every PASS/FAIL line, and writing.report_words when set
      (0 = unmeasured: warn only). Exit 1 names what is missing.
  reef-claims.py claims-only <base>..<head> [--repo DIR]
  reef-claims.py blocking-fixed <plan-review-report> <since-rev> [--repo DIR]   every BLOCKING path:line changed since <since-rev>
      Exit 0 iff the range, stripped of documentation files and of comment/blank lines, is
      EMPTY — the only commit allowed after a GREEN verdict. Exit 1 names the first code
      lines that make it a code change (then it is a BLOCKER or a new queue row, never a
      fourth round: 44% of measured fix rounds came after GREEN).

Measured on 2026-10-03: 24 review rounds blocked on a false sentence against 14 on a code
defect. A claim that names a line the round did not touch is the shape of those 24.
Exit 0 ok · 1 claims rejected / code after GREEN · 2 bad usage or git error.
"""
import os
import re
import subprocess
import sys

CLAIM = re.compile(r"^(?P<sentence>.+?)\s+(?:—|--|-)\s*true at\s+(?P<path>[^\s:]+):(?P<a>\d+)(?:-(?P<b>\d+))?\s*$")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
HEADER = re.compile(r"^diff --git a/(.*) b/(.*)$")
DOC_EXT = (".md", ".markdown", ".txt", ".rst", ".adoc")
DOC_DIRS = ("docs/", "tasks/", "specs/", "evidence/")
COMMENT_START = ("#", "//", "/*", "*", "*/", "--", "<!--", "-->", ";", '"""', "'''", "`")


def die(msg, code=2):
    print(f"reef-claims: {msg}", file=sys.stderr)
    sys.exit(code)


def git_diff(repo, rng):
    r = subprocess.run(["git", "diff", "-U0", "--no-color", "--no-ext-diff", rng, "--"],
                       cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        die(f"git diff {rng} failed: {r.stderr.strip()}")
    return r.stdout


def parse(diff):
    """path -> (set of ADDED new-side line numbers, [added text lines], [removed text lines])"""
    files, cur, new_line = {}, None, 0
    for line in diff.splitlines():
        m = HEADER.match(line)
        if m:
            cur = m.group(2)
            files.setdefault(cur, (set(), [], []))
            continue
        if cur is None:
            continue
        m = HUNK.match(line)
        if m:
            new_line = int(m.group(1))
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            files[cur][0].add(new_line)
            files[cur][1].append(line[1:])
            new_line += 1
        elif line.startswith("-"):
            files[cur][2].append(line[1:])
    return files


def is_doc(path):
    return path.lower().endswith(DOC_EXT) or any(path.startswith(d) or f"/{d}" in path for d in DOC_DIRS)


def is_comment(text):
    s = text.strip()
    return s == "" or any(s.startswith(c) for c in COMMENT_START)


def cmd_check(repo, rng, claims_path):
    files = parse(git_diff(repo, rng))
    added_any = any(f[0] for f in files.values())
    try:
        with open(claims_path, encoding="utf-8") as f:
            lines = [l.rstrip("\n") for l in f if l.strip()]
    except OSError as e:
        die(f"cannot read {claims_path}: {e}")
    bad = []
    for l in lines:
        m = CLAIM.match(l)
        if not m:
            bad.append(f"not a claim ('<sentence> — true at <path>:<line>'): {l!r}")
            continue
        p, a = m.group("path"), int(m.group("a"))
        b = int(m.group("b") or a)
        if p not in files:
            bad.append(f"{p}:{a} — the round did not change {p}: {m.group('sentence')!r}")
        elif not any(n in files[p][0] for n in range(a, b + 1)):
            bad.append(f"{p}:{a} — not a line this round added: {m.group('sentence')!r}")
    if not lines and added_any:
        bad.append("the claims list is empty while the round added lines — every fix round ends with its claims")
    if bad:
        print("REJECTED claims (each must be true at a line THIS round added):")
        for b_ in bad:
            print(f"  - {b_}")
        return 1
    print(f"ok: {len(lines)} claim(s), each inside {rng}")
    return 0


def cmd_claims_only(repo, rng):
    files = parse(git_diff(repo, rng))
    offenders = []
    for path, (_, added, removed) in sorted(files.items()):
        if is_doc(path):
            continue
        for text in added + removed:
            if not is_comment(text):
                offenders.append(f"{path}: {text.strip()[:80]!r}")
                if len(offenders) >= 5:
                    break
        if len(offenders) >= 5:
            break
    if offenders:
        print(f"NOT claims-only: {rng} changes code (a BLOCKER or a new queue row, never a fourth round):")
        for o in offenders:
            print(f"  - {o}")
        return 1
    print(f"ok: {rng} is claims-only (docs, comments, blank lines)")
    return 0


def read_cfg(repo):
    try:
        import json
        with open(os.path.join(repo, ".reef", "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def cmd_handback(repo, path):
    cap = int((read_cfg(repo).get("writing") or {}).get("handback_words", 150) or 150)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        die(f"cannot read {path}: {e}")
    words = len(re.findall(r"\S+", text))
    claims = [l for l in text.splitlines() if CLAIM.match(l.strip())]
    bad = []
    if words > cap:
        bad.append(f"{words} words > writing.handback_words {cap} — shorten, evidence only")
    if not claims:
        bad.append("no claims list ('<sentence> — true at <path>:<line>' lines) — a fix round ends with its claims")
    if not re.search(r"^RUN:\s*agent=", text, re.M):
        bad.append("no `RUN: agent=… task=…` header")
    if bad:
        print("REJECTED hand-back (re-dispatch once, no attempt consumed):")
        for b in bad:
            print(f"  - {b}")
        return 1
    print(f"ok: hand-back {words} words, {len(claims)} claim(s)")
    return 0


def cmd_report(repo, path, task_path):
    cfg = read_cfg(repo)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        with open(task_path, encoding="utf-8") as f:
            task = f.read()
    except OSError as e:
        die(f"cannot read: {e}")
    body = re.search(r"^##\s+Acceptance Criteria\s*$(.*?)(?=^##\s|\Z)", task, re.M | re.S)
    acs = [l for l in (body.group(1) if body else "").splitlines() if re.match(r"^\s*[-*+]\s+|^\s*\d+[.)]\s+", l)]
    acs = [l for l in acs if "HUMAN AC" not in l]
    ids = []
    for i, l in enumerate(acs, 1):
        m = re.search(r"\bAC-?(\d+)\b", l)
        ids.append(m.group(1) if m else str(i))
    proof = re.search(r"^##\s+Proof\s*$(.*?)(?=^##\s|\Z)", task, re.M | re.S)
    proof_rows = {}
    if proof:
        for l in proof.group(1).splitlines():
            cells = [c.strip() for c in l.strip().strip("|").split("|")]
            m = re.match(r"^\**AC-?(\d+)\**$", cells[0]) if len(cells) >= 2 else None
            if m and not re.match(r"^-+$", cells[1]):
                proof_rows[m.group(1)] = cells[1].strip("`")
    bad = []
    if not re.search(r"^RUN:\s*agent=(verifier|loophole-hunter)\b.*\btask=", text, re.M):
        bad.append("no `RUN: agent=verifier|loophole-hunter task=<id>` header")
    hunter = bool(re.search(r"^RUN:\s*agent=loophole-hunter\b", text, re.M))
    if hunter:
        # the hunter judges a defect class, not criteria: its shape is DEFECT / BLOCKER / NEW-ROW / NONE / VERDICT
        # (agents/loophole-hunter.md); demanding RULE AC lines of it rejected every live hunter report (0.7 dogfood)
        ids = []
        if not re.search(r"^\**DEFECT\**:", text, re.M):
            bad.append("no `DEFECT:` line (the hunter names the defect class it attacked)")
        blockers = [l for l in text.splitlines() if re.match(r"^\**BLOCKER\**:\s*(?!none\b)\S", l, re.I)]
        verdict_fail = re.search(r"^VERDICT:\s*FAIL\b", text, re.M)
        if verdict_fail and not blockers:
            bad.append("VERDICT: FAIL with no BLOCKER line")
        for l in blockers:
            if not re.search(r"[\w/.-]+\.[a-z]+:\d+|`[^`]+`", l):
                bad.append("a BLOCKER without a citation (a path:line or a command in backticks)")
                break
    rules = {m.group(1): m.group(2) for m in re.finditer(r"^RULE\s+AC-?(\d+)\s*:(.*)$", text, re.M)}
    for n in ids:
        if n not in rules:
            bad.append(f"no `RULE AC{n}:` line for criterion {n}")
        elif n in proof_rows:
            token = re.search(r"[A-Za-z_][\w./:-]*", proof_rows[n])
            if token and token.group(0) not in rules[n] and proof_rows[n] not in rules[n]:
                bad.append(f"RULE AC{n} does not cite its Proof row ({proof_rows[n][:40]!r})")
        verdicts = [l for l in text.splitlines() if re.search(rf"\bAC-?{n}\b", l) and re.search(r"\b(PASS|FAIL)\b", l) and not l.lstrip().startswith("RULE")]
        if not verdicts:
            bad.append(f"no PASS/FAIL verdict line for AC{n}")
        elif not any(re.search(r"[\w/.-]+\.[a-z]+:\d+|\btest_[a-z0-9_]+|`[^`]+`|exit\s+\d|Ran \d+|\d+ passed", v) for v in verdicts):
            bad.append(f"AC{n} verdict carries no evidence (a path:line, a test name, a command or its output)")
    if not re.search(r"^VERDICT:\s*(PASS|FAIL)\b", text, re.M):
        bad.append("no `VERDICT: PASS|FAIL` line")
    cap = int((cfg.get("writing") or {}).get("report_words", 0) or 0)
    # RULE lines are the contract and their length is the plan's (one per criterion), so they are free; the budget
    # grows 40 words per criterion past 8 (the cap was measured on 6-7 criteria; a 15-criterion task's honest report
    # ran 1693 words and was rejected into a rewrite round, first contact 2026-10-16)
    words = len(re.findall(r"\S+", "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("RULE "))))
    budget = report_budget(cap, len(ids))
    if cap and words > budget:
        extra = f" + {budget - cap} ({len(ids)} criteria)" if budget > cap else ""
        bad.append(f"{words} words (RULE lines free) > writing.report_words {cap}{extra}")
    elif not cap:
        print(f"note: report {words} words (writing.report_words unset — warn only until measured)")
    if bad:
        print("REJECTED report:")
        for b in bad:
            print(f"  - {b}")
        return 1
    print(f"ok: report covers {len(ids)} criteria with rules and evidence")
    return 0


def report_budget(cap, n_criteria):
    """The report's word budget: writing.report_words plus 40 per criterion past 8; RULE lines never count."""
    return cap + 40 * max(0, int(n_criteria) - 8) if cap else 0


DIMENSIONS = ("type safety", "module boundaries", "framework opinionation", "test signal", "lint baseline")
PROOF = re.compile(r"`[^`]+`|[\w./-]+\.[A-Za-z]+:\d+|\b[\w./-]+/[\w./-]+\b")


CITE = re.compile(r"(?<![\w/])((?:[\w.-]+/)*[\w.-]+\.(?:md|ts|tsx|js|py|json|yml|yaml|toml|sh|mts))[:#](\d+)")


def cmd_blocking_fixed(repo, report_path, since):
    """Every `path:line` a plan review's BLOCKING section cites must have changed since <since> (the HEAD before the
    orchestrator applied the fixes): the cited line's text, as it was in <since>, is no longer in the file. First contact
    (2026-10-17): one cited line (an ADR's Consequences) was left as it was, the fresh reviewer failed on it again, and
    the round rule stopped the loop — a 4-minute review spent on a one-line miss a grep would have caught."""
    try:
        with open(report_path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        die(f"cannot read: {e}")
    m = re.search(r"^#*\s*\**BLOCKING\**[^\n]*$(.*?)(?=^#*\s*\**ADVISORY\**|^VERDICT:|\Z)", text, re.M | re.S)
    section = m.group(1) if m else ""
    cites = []
    for path, line in CITE.findall(section):
        if (path, int(line)) not in cites:
            cites.append((path, int(line)))
    if not cites:
        print("blocking-fixed: no path:line citations in the BLOCKING section — nothing to check (the reviewer cites "
              "`path:line`; a shorthand like `prisma:34` cannot be checked)")
        return 0
    bad, skipped, ok_n = [], [], 0
    for path, line in cites:
        r = subprocess.run(["git", "-C", repo, "show", f"{since}:{path}"], capture_output=True, text=True)
        if r.returncode != 0:
            skipped.append(f"{path}:{line} (not in {since})")
            continue
        old_lines = r.stdout.splitlines()
        if line < 1 or line > len(old_lines):
            skipped.append(f"{path}:{line} (no such line in {since})")
            continue
        old = old_lines[line - 1].strip()
        try:
            with open(os.path.join(repo, path), encoding="utf-8") as f:
                now = [l.strip() for l in f.read().splitlines()]
        except OSError:
            ok_n += 1          # the file is gone: the line is gone with it
            continue
        if old and old in now:
            bad.append(f"{path}:{line} unchanged since {since}: {old[:90]!r}")
        else:
            ok_n += 1
    for s in skipped:
        print(f"note: skipped {s}")
    if bad:
        print("NOT FIXED — the reviewer will fail on the same line again; change it before re-dispatching:")
        for b in bad:
            print(f"  - {b}")
        return 1
    print(f"ok: {ok_n} cited line(s) changed since {since}")
    return 0


def cmd_assess(repo, root):
    """`/reef-assess`'s output as DATA: architecture.md and conventions.md carry the four observed sections and every
    top-level claim is `Observed — <proof>` (a path:line, a path or a command in backticks) or `Inferred — …`;
    day-zero.md carries the harnessability table: the five dimensions, 0/1 each, the sum and the level consistent.
    The fixture replay (tests/test_assess.py) is the judge-eval analogue for the Explore agents."""
    root = os.path.abspath(root)
    arch_p = os.path.join(root, "reef", "architecture", "architecture.md")
    conv_p = os.path.join(root, "reef", "architecture", "conventions.md")
    dz_p = os.path.join(root, "reef", "day-zero.md")
    bad = []
    texts = {}
    for p in (arch_p, conv_p, dz_p):
        try:
            with open(p, encoding="utf-8") as f:
                texts[p] = f.read()
        except OSError:
            bad.append(f"missing {os.path.relpath(p, root)}")
    if bad:
        print("REJECTED assess:\n  - " + "\n  - ".join(bad))
        return 1
    arch, conv, dz = texts[arch_p], texts[conv_p], texts[dz_p]
    for name, text, heads in (("architecture.md", arch, [r"how it works"]),
                              ("conventions.md", conv, [r"lint", r"type", r"test", r"error", r"logging", r"naming", r"module layout", r"how it was pushed"])):
        for h in heads:
            if not re.search(r"^#{1,3}\s+.*" + h, text, re.M | re.I):
                bad.append(f"{name}: no section for '{h}'")
        fenced, advice = False, False
        for i, l in enumerate(text.splitlines(), 1):
            if l.startswith("```"):
                fenced = not fenced
                continue
            if l.startswith("#"):
                # the recommendation sections (Open, Gap to target, what the constitution should take) hold
                # proposals, not observations — only the observed sections must label every claim
                advice = bool(re.search(r"(?i)\b(open|gap to target|should take|next steps?)\b", l))
                continue
            if fenced or advice or not re.match(r"^- ", l):
                continue
            body = re.sub(r"^- \**", "", l)
            if re.match(r"(?i)inferred\b", body):
                continue
            if not re.match(r"(?i)observed\b", body):
                bad.append(f"{name}:{i}: a claim without Observed/Inferred: {l[:70]!r}")
            elif not PROOF.search(body):
                bad.append(f"{name}:{i}: Observed without a proving path or command: {l[:70]!r}")
    m = re.search(r"^##\s+Harnessability\s*[—-]\s*(high|moderate|low)\s*\((\d)/5\)", dz, re.M | re.I)
    if not m:
        bad.append("day-zero.md: no `## Harnessability — high|moderate|low (N/5)` heading")
    else:
        level, n = m.group(1).lower(), int(m.group(2))
        rows = {}
        for l in dz.splitlines():
            cells = [c.strip() for c in l.strip().strip("|").split("|")]
            if len(cells) >= 3 and cells[0].lower() in DIMENSIONS:
                rows[cells[0].lower()] = cells
        for d in DIMENSIONS:
            if d not in rows:
                bad.append(f"day-zero.md: harnessability table lacks '{d}'")
            else:
                if rows[d][1] not in ("0", "1"):
                    bad.append(f"day-zero.md: '{d}' scores {rows[d][1]!r}, not 0 or 1")
                if not rows[d][2]:
                    bad.append(f"day-zero.md: '{d}' has no Observed cell")
        total = sum(int(r[1]) for r in rows.values() if r[1] in ("0", "1"))
        if len(rows) == 5 and total != n:
            bad.append(f"day-zero.md: the heading says {n}/5 but the dimensions sum to {total}")
        want = "high" if total == 5 else ("moderate" if total >= 3 else "low")
        if len(rows) == 5 and level != want:
            bad.append(f"day-zero.md: {total}/5 is '{want}', the heading says '{level}'")
    if bad:
        print("REJECTED assess:")
        for b in bad[:20]:
            print(f"  - {b}")
        return 1
    claims = sum(1 for t in (arch, conv) for l in t.splitlines() if re.match(r"^- \**(Observed|Inferred)", l, re.I))
    print(f"ok: assess — four observed sections, {claims} labelled claims, harnessability {m.group(1).lower()} ({m.group(2)}/5) consistent")
    return 0


def main(argv):
    repo = "."
    if "--repo" in argv:
        i = argv.index("--repo")
        if i + 1 >= len(argv):
            die("--repo needs a directory")
        repo = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if not argv:
        die("usage: reef-claims.py check <base>..<head> <claims-file> | claims-only <base>..<head>")
    if argv[0] == "check" and len(argv) == 3 and argv[1] == "--handback":
        return cmd_handback(repo, argv[2])
    if argv[0] == "report" and len(argv) == 4 and argv[2] == "--task":
        return cmd_report(repo, argv[1], argv[3])
    if argv[0] == "check" and len(argv) == 3:
        return cmd_check(repo, argv[1], argv[2])
    if argv[0] == "claims-only" and len(argv) == 2:
        return cmd_claims_only(repo, argv[1])
    if argv[0] == "blocking-fixed" and len(argv) == 3:
        return cmd_blocking_fixed(repo, argv[1], argv[2])
    if argv[0] == "assess" and len(argv) in (1, 2):
        return cmd_assess(repo, argv[1] if len(argv) == 2 else repo)
    die("usage: reef-claims.py check <base>..<head> <claims-file> | check --handback <file> | report <file> --task <task> | claims-only <base>..<head> | blocking-fixed <review-report> <since-rev> | assess [<project-root>]")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
