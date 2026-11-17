#!/usr/bin/env python3
# CLASS: code
"""Reef ADR selection (hardening PR-8, docs/design/hardening-pr8-plan.md) — an agent reads the ADRs that touch its files, not every
decision the project ever accepted.

Usage:
  reef-adrs.py task <task-file>                 the implementer's `adrs:` block (reef-attempt prints it; the guard checks it)
  reef-adrs.py feature <slug> [--repo DIR]      the planner's list: the feature's own Accepted ADRs + the project's that meet the
                                                union of its tasks' files: (every project ADR while no task declares files:)
  reef-adrs.py paths <path>... [--repo DIR]     the verifier's list: the Accepted ADRs on the diff's names

An ADR declares what it governs in a `Paths:` line (under `Status:`): `files:` patterns, the round check's matcher (`dir/` a
prefix, else an fnmatch glob; `*` = every path). No line, an empty one or the template's `<…>` placeholder = undeclared, and an
undeclared ADR is listed for every reader: a missing declaration never drops a decision (plan-check WARNs on it). Only an
Accepted ADR is a candidate (Proposed and Superseded are not — as "every Accepted ADR" before).

Candidates: the task's feature `adr/` (task/feature), every feature's `adr/` (paths), `reef/architecture/adr/`, `paths.adr`.
Exit 0 with the block on stdout (nothing when no Accepted ADR exists); 2 on unusable input.
"""
import fnmatch
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True
from reef_common import read_config, repo_root, task_frontmatter, die as _die  # noqa: E402

GLOB = "*?["
ARCH = os.path.join("reef", "architecture", "adr")
END = "adrs: end"


def die(msg):
    _die(msg, prefix="reef-adrs")


def match(path, pat):
    """The round check's matcher (reef-claims.py round, (b)): `dir/` a prefix, else an fnmatch glob."""
    return path.startswith(pat) if pat.endswith("/") else fnmatch.fnmatchcase(path, pat)


def meet(a, b):
    """Can one repo path match both patterns? A concrete path is checked with the round's matcher; two patterns meet when one's
    literal prefix (up to the first glob character) starts the other's — sound (a path matching both starts with both
    prefixes), so it may over-include and never misses."""
    concrete = lambda x: not x.endswith("/") and not any(c in x for c in GLOB)
    if concrete(a):
        return match(a, b)
    if concrete(b):
        return match(b, a)
    lit = lambda x: x[:min([x.index(c) for c in GLOB if c in x] or [len(x)])]
    la, lb = lit(a), lit(b)
    return la.startswith(lb) or lb.startswith(la)


def entries(value):
    """A `files:` / `Paths:` value as its patterns: brackets, quotes and backticks dropped, comma-separated."""
    return [x.strip().strip("\"'`") for x in value.strip().strip("[]").split(",") if x.strip().strip("\"'`")]


def unfenced(text):
    out, fenced = [], False
    for l in text.splitlines():
        if l.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced:
            out.append(l)
    return out


def adr_fields(text):
    """(accepted, paths): accepted = the first of proposed/accepted/superseded in the Status is `accepted` (a `## Status` heading's
    next line or a `Status:` line, as plan-check reads it); paths = the Paths: patterns, or None when undeclared."""
    lines, status, paths = unfenced(text), None, None
    for i, l in enumerate(lines):
        if status is None and re.match(r"^#+\s*Status\s*$", l, re.I):
            status = next((n.strip() for n in lines[i + 1:] if n.strip()), "")
        m = re.match(r"^\**Status\**:[ \t]*(\S.*)$", l, re.I)
        if status is None and m:
            status = m.group(1)
        p = re.match(r"^\**Paths\**:[ \t]*(.*)$", l, re.I)
        if paths is None and p:
            paths = entries(p.group(1))
    words = re.findall(r"\b(proposed|accepted|superseded)\b", status or "", re.I)
    if paths is not None and (not paths or any("<" in x for x in paths)):
        paths = None
    return bool(words) and words[0].lower() == "accepted", paths


def accepted(root, dirs):
    """[(rel, paths)] of the Accepted ADRs in dirs, by repo-relative path."""
    seen, out = set(), []
    for d in dirs:
        d = os.path.realpath(d)
        if d in seen or not os.path.isdir(d):
            continue
        seen.add(d)
        for f in os.listdir(d):
            if not f.endswith(".md") or f == "README.md":
                continue
            p = os.path.join(d, f)
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    ok, paths = adr_fields(fh.read())
            except OSError as e:
                die(f"cannot read {p}: {e}")
            if ok:
                out.append((os.path.relpath(p, root), paths))
    return sorted(out)


def project_dirs(root):
    cfg = read_config(root)
    legacy = str((cfg.get("paths") or {}).get("adr") or "").strip()
    return [os.path.join(root, ARCH)] + ([os.path.join(root, legacy)] if legacy else [])


def features_dir(root):
    return os.path.join(root, str((read_config(root).get("paths") or {}).get("features") or "reef/features"))


def block(head, picked):
    return [head] + [f"  {rel} (Paths: {', '.join(p) if p is not None else 'not declared — loaded for every task'})"
                     for rel, p in picked] + [END]


def pick(cands, pats):
    return [(rel, p) for rel, p in cands if p is None or any(meet(a, b) for a in p for b in pats)]


def task_block(path):
    """The implementer's `adrs:` block for a task file — the lines reef-attempt prints and the guard requires, verbatim."""
    try:
        with open(path, encoding="utf-8") as f:
            fm = task_frontmatter(f.read())
    except (OSError, UnicodeDecodeError) as e:
        die(f"cannot read {path}: {e}")
    if fm is None:
        die(f"{path} has no frontmatter fence — not a reef task file")
    root = os.path.realpath(repo_root(path))
    here = os.path.dirname(os.path.realpath(path))
    if os.path.basename(here) == "done":
        here = os.path.dirname(here)
    dirs = project_dirs(root)
    fdir = os.path.dirname(here) if os.path.basename(here) == "tasks" else None
    if fdir and fdir != root:
        dirs.insert(0, os.path.join(fdir, "adr"))
    cands = accepted(root, dirs)
    if not cands:
        return []
    pats = entries(fm.get("files", ""))
    if not pats:
        return block(f"adrs: {len(cands)} of {len(cands)} Accepted ADRs — the task declares no files:, so every one is read; "
                     f"pass every line through `{END}` verbatim", cands)
    got = pick(cands, pats)
    tail = ("read each, nothing else; pass every line through `adrs: end` verbatim" if got else "read none")
    return block(f"adrs: {len(got)} of {len(cands)} Accepted ADRs touch this task's files: — {tail}", got)


def feature_block(root, slug):
    if not slug or "/" in slug or slug.startswith("."):
        die(f"not a feature slug: {slug!r}")
    fdir = os.path.join(features_dir(root), slug)
    own = accepted(root, [os.path.join(fdir, "adr")])
    proj = [c for c in accepted(root, project_dirs(root)) if c not in own]
    if not own and not proj:
        return []
    pats = []
    for sub in ("tasks", os.path.join("tasks", "done")):
        d = os.path.join(fdir, sub)
        for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if f.endswith(".md"):
                with open(os.path.join(d, f), encoding="utf-8", errors="replace") as fh:
                    pats += entries((task_frontmatter(fh.read()) or {}).get("files", ""))
    got = pick(proj, pats) if pats else proj
    why = "the project's on its tasks' files:" if pats else "every project ADR (no task declares files: yet)"
    return block(f"adrs: {len(own) + len(got)} of {len(own) + len(proj)} Accepted ADRs for feature {slug} — its own, and {why}; "
                 "read each, nothing else", sorted(own + got))


def paths_block(root, paths):
    fd = features_dir(root)
    dirs = project_dirs(root) + ([os.path.join(fd, s, "adr") for s in sorted(os.listdir(fd))] if os.path.isdir(fd) else [])
    cands = accepted(root, dirs)
    if not cands:
        return []
    got = pick(cands, paths)
    return block(f"adrs: {len(got)} of {len(cands)} Accepted ADRs touch the {len(paths)} path(s) given — check the diff against each", got)


def main(argv):
    args, repo = list(argv), None
    if "--repo" in args:
        i = args.index("--repo")
        if i + 1 >= len(args):
            die("--repo needs a directory")
        repo = args[i + 1]
        del args[i:i + 2]
    if not args or args[0] not in ("task", "feature", "paths"):
        die("usage: reef-adrs.py task <task-file> | feature <slug> [--repo DIR] | paths <path>... [--repo DIR]")
    root = os.path.realpath(repo_root(repo or os.getcwd()))
    if args[0] == "task":
        if len(args) != 2 or not os.path.isfile(args[1]):
            die(f"task file not found: {args[1:] or '(none)'}")
        out = task_block(args[1])
    elif args[0] == "feature":
        if len(args) != 2:
            die("usage: reef-adrs.py feature <slug> [--repo DIR]")
        out = feature_block(root, args[1])
    else:
        out = paths_block(root, args[1:])
    for line in out:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
