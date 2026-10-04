#!/usr/bin/env python3
"""Reef tier — effort matched to risk, recomputed from the DIFF; it can only make it heavier.

Usage:
  reef-tier.py <task-file> [--base BRANCH] [--repo DIR] [--write]

Computes the tier the diff <base>...HEAD deserves and compares it with the task's declared `tier:`:
  light  iff every changed path (the task files under paths.tasks are the spec, not the change,
         and are ignored) matches a glob in .reef/config.json tiers.light.allow,
         none matches tiers.light.migrations, no docs/adr/draft-* is touched, and the added
         product lines (files not matching tiers.tests) are <= tiers.light.max_lines (default 80)
  full   otherwise (the default — an undeclared tier is full)
  design is never computed: it is declared (a mechanism that failed twice, privacy, money, a guard)
Declared lighter than computed -> exit 1 ("declared light, computed full"). An EMPTY diff is refused
(exit 1): there is nothing to tier. --write raises `tier:` in the task file to the computed one.
Exit 0 ok · 1 refused · 2 usage/git error.
"""
import fnmatch
import os
import re
import subprocess
import sys
import json

FENCE = re.compile(r"\A---\r?\n(.*?\r?\n)---\r?\n", re.S)
ORDER = {"light": 0, "full": 1, "design": 2}
DEFAULT_TESTS = ["tests/**", "test/**", "**/*.test.*", "**/*_test.*", "**/test_*.py", "**/*.spec.*"]


def die(msg, code=2):
    print(f"reef-tier: {msg}", file=sys.stderr)
    sys.exit(code)


def matches(path, globs):
    for g in globs:
        if fnmatch.fnmatch(path, g):
            return True
        if g.endswith("/**") and (path.startswith(g[:-3] + "/") or path == g[:-3]):
            return True
        if g.startswith("**/") and fnmatch.fnmatch(os.path.basename(path), g[3:]):
            return True
    return False


def numstat(repo, base):
    r = subprocess.run(["git", "diff", "--numstat", f"{base}...HEAD", "--"], cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        die(f"git diff {base}...HEAD failed: {r.stderr.strip()}")
    rows = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added = 0 if parts[0] == "-" else int(parts[0])
        rows.append((parts[2], added))
    return rows


def compute(rows, tiers, tasks_dir="tasks"):
    rows = [(p, a) for p, a in rows if not (p == tasks_dir or p.startswith(tasks_dir.rstrip("/") + "/"))]
    if not rows:
        return (None, [])
    light = tiers.get("light", {}) if isinstance(tiers, dict) else {}
    allow = light.get("allow", [])
    migrations = light.get("migrations", [])
    tests = tiers.get("tests", DEFAULT_TESTS) if isinstance(tiers, dict) else DEFAULT_TESTS
    max_lines = int(light.get("max_lines", 80))
    reasons = []
    product = 0
    for path, added in rows:
        if matches(path, migrations):
            reasons.append(f"{path}: a migration")
        if re.match(r"^docs/adr/draft-", path):
            reasons.append(f"{path}: a draft ADR")
        if not matches(path, allow):
            reasons.append(f"{path}: not in tiers.light.allow")
        if not matches(path, tests):
            product += added
    if product > max_lines:
        reasons.append(f"{product} product lines added > tiers.light.max_lines {max_lines}")
    return ("full", reasons) if reasons else ("light", [])


def main(argv):
    base, repo, write, task = "main", None, False, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--base":
            base = argv[i + 1]; i += 2
        elif a == "--repo":
            repo = argv[i + 1]; i += 2
        elif a == "--write":
            write = True; i += 1
        elif task is None:
            task = a; i += 1
        else:
            die(f"unexpected argument {a!r}")
    if task is None or not os.path.isfile(task):
        die("usage: reef-tier.py <task-file> [--base BRANCH] [--repo DIR] [--write]")
    repo = repo or os.path.dirname(os.path.abspath(task))
    with open(task, encoding="utf-8", newline="") as f:
        text = f.read()
    m = FENCE.match(text)
    if not m:
        die(f"{task}: no frontmatter fence", 1)
    dm = re.search(r"^tier:[ \t]*(\S+)", m.group(1), re.M)
    declared = dm.group(1).strip('"') if dm else "full"
    if declared not in ORDER:
        die(f"{task}: tier={declared!r} not in light/full/design", 1)
    cfg = {}
    try:
        with open(os.path.join(subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=repo, capture_output=True,
                                              text=True, check=True).stdout.strip(), ".reef", "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        pass
    tiers = cfg.get("tiers", {})
    rows = numstat(repo, base)
    computed, reasons = compute(rows, tiers, cfg.get("paths", {}).get("tasks", "tasks"))
    if computed is None:
        die(f"empty diff against {base} (task files aside) — nothing to tier (push the work first)", 1)
    if ORDER[declared] >= ORDER[computed]:
        print(f"ok: declared {declared}, computed {computed}")
        return 0
    print(f"REFUSED: declared {declared}, computed {computed} — a tier can only get heavier:")
    for r in reasons[:10]:
        print(f"  - {r}")
    if write:
        new = re.sub(r"^tier:.*$", f"tier: {computed}", m.group(1), count=1, flags=re.M) if dm else m.group(1) + f"tier: {computed}\n"
        with open(task, "w", encoding="utf-8", newline="") as f:
            f.write(text[:m.start(1)] + new + text[m.end(1):])
        print(f"  tier: raised to {computed} in {task} (the plan stamp is now stale — re-review)")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
