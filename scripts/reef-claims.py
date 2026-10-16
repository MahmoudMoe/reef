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
    words = len(re.findall(r"\S+", text))
    if cap and words > cap:
        bad.append(f"{words} words > writing.report_words {cap}")
    elif not cap:
        print(f"note: report {words} words (writing.report_words unset — warn only until measured)")
    if bad:
        print("REJECTED report:")
        for b in bad:
            print(f"  - {b}")
        return 1
    print(f"ok: report covers {len(ids)} criteria with rules and evidence")
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
    die("usage: reef-claims.py check <base>..<head> <claims-file> | check --handback <file> | report <file> --task <task> | claims-only <base>..<head>")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
