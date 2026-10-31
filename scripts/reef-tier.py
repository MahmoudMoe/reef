#!/usr/bin/env python3
# CLASS: code
"""Reef tier — effort matched to risk, recomputed from the DIFF; it can only make it heavier.

Usage:
  reef-tier.py <task-file> [--base BRANCH] [--repo DIR] [--write]

Computes the tier the diff <base>...HEAD deserves and compares it with the task's declared `tier:`:
  light  iff every changed path (the task files under paths.tasks are the spec, not the change,
         and are ignored) matches a glob in .reef/config.json tiers.light.allow,
         none matches tiers.light.migrations, no docs/adr/draft-* is touched, and the added
         product lines (files not matching tiers.tests) are <= tiers.light.max_lines (default 80)
  full   otherwise (the default — an undeclared tier is full)
  design (0.6) when a changed path matches tiers.design.paths (auth, crypto, secrets, migrations) or the
         task's touches: names migration; critical when a path matches tiers.critical.paths (the guard's
         own files) or touches: names pii, money or auth. The rails apply to features planned under 0.6;
         an older task is listed, not refused (--rails-warn).
Declared lighter than computed -> exit 1 ("declared light, computed full"). An EMPTY diff is refused
(exit 1): there is nothing to tier. --write raises `tier:` in the task file to the computed one.
Exit 0 ok · 1 refused · 2 usage/git error.

  reef-tier.py path <task-file>...     (workflow v3, phase 3) the PATH the tier decides for a feature's tasks:
         `fast` when every task is light or full and none touches auth/pii/money/migration — the deterministic
         check is the plan review, one worktree per row, no per-task verifier, one reviewer at the end;
         `critical` otherwise — the hunter's plan pass, the plan-reviewer, a verifier per task, security per feature.
         Rollups (R*) are fix rounds, not tasks of the plan. Prints one line; exit 2 without a task file.
"""
import fnmatch
import os
import re
import subprocess
import sys
import json
from functools import partial
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # the shared helpers live beside this script
sys.dont_write_bytecode = True   # and no scripts/__pycache__ lands in a project's tree (reef-update, a row worktree read it as changes)
from reef_common import die as _die  # noqa: E402

FENCE = re.compile(r"\A---\r?\n(.*?\r?\n)---\r?\n", re.S)
ORDER = {"light": 0, "full": 1, "design": 2, "critical": 3}
DEFAULT_TESTS = ["tests/**", "test/**", "**/*.test.*", "**/*_test.*", "**/test_*.py", "**/*.spec.*"]


die = partial(_die, prefix="reef-tier")


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


TOUCHES = {"pii": "critical", "money": "critical", "auth": "critical", "migration": "design"}


def cmd_path(files):
    """One rule, one parser: scripts/reef-plan-check.py's feature_path beside this script (the guard calls the same)."""
    files = [p for p in files if not re.match(r"^R\d+[-.]", os.path.basename(p))]
    if not files:
        die("usage: reef-tier.py path <task-file>... (no task file given, or only rollups)")
    for p in files:
        if not os.path.isfile(p):
            die(f"cannot read {p}")
    import importlib.machinery
    import importlib.util
    pc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reef-plan-check.py")
    loader = importlib.machinery.SourceFileLoader("reef_plan_check", pc)
    spec = importlib.util.spec_from_loader("reef_plan_check", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    loader.exec_module(mod)
    path, why = mod.feature_path(files)
    print(f"path: critical — {why}" if path == "critical" else f"path: fast ({why})")
    return 0


def compute(rows, tiers, tasks_dir="tasks", touches=()):
    rows = [(p, a) for p, a in rows if not (p == tasks_dir or p.startswith(tasks_dir.rstrip("/") + "/"))
            and not re.search(r"(^|/)reef/features/[^/]+/tasks/", p)]
    if not rows:
        return (None, [])
    light = tiers.get("light", {}) if isinstance(tiers, dict) else {}
    # 0.6 path-class rails: the heaviest class any changed path (or declared touch) falls in wins
    forced, why = None, []
    for cls, key in (("critical", "critical"), ("design", "design")):
        globs = (tiers.get(key, {}) or {}).get("paths", []) if isinstance(tiers, dict) and isinstance(tiers.get(key, {}), dict) else []
        hit = [p for p, _ in rows if matches(p, globs)]
        if hit and (forced is None or ORDER[cls] > ORDER[forced]):
            forced, why = cls, [f"{p}: matches tiers.{key}.paths" for p in hit[:5]]
    for t in touches:
        if t in TOUCHES and (forced is None or ORDER[TOUCHES[t]] > ORDER[forced]):
            forced, why = TOUCHES[t], [f"touches: {t} -> {TOUCHES[t]}"]
    if forced:
        return (forced, why)
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
    if argv and argv[0] == "path":
        return cmd_path(argv[1:])
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
    tm = re.search(r"^touches:[ \t]*\[(.*)\]", m.group(1), re.M)
    touches = [t.strip().strip("\"'") for t in tm.group(1).split(",") if t.strip()] if tm else []
    if declared not in ORDER:
        die(f"{task}: tier={declared!r} not in light/full/design/critical", 1)
    cfg = {}
    try:
        with open(os.path.join(subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=repo, capture_output=True,
                                              text=True, check=True).stdout.strip(), ".reef", "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        pass
    tiers = cfg.get("tiers", {})
    rows = numstat(repo, base)
    computed, reasons = compute(rows, tiers, cfg.get("paths", {}).get("tasks", "tasks"), touches)
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
