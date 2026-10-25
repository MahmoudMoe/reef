#!/usr/bin/env python3
# CLASS: code
"""Reef update — pull a new Reef into a project in ONE command.

Usage: reef-update.py [--repo DIR] [--plugin DIR] [--commit] [--push] [--dry-run]

1. The plugin clone (--plugin, else $CLAUDE_PLUGIN_ROOT, else this script's own repo) must be on `main` and clean;
   `git pull --ff-only` brings it up and the old..new range is printed.
2. `reef-init.py --root <project> --plugin <plugin>` refreshes the project's copies (scripts/reef-*, the rendered
   files); its summary line is printed. Proposals (files you edited) are listed with their accept/keep commands,
   never applied.
3. --commit stages ONLY Reef's own paths (scripts/reef-*, .reef/init-manifest.json, .reef/version, .githooks/*, .gitignore, the
   rendered map) and commits `reef: scripts <version> (<plugin sha>)`; --push pushes the current branch.
4. Prints the two Claude Code commands that reload the plugin.
Exit 0 ok · 1 a step failed (its line says which) · 2 usage.

Usability plan A1 (2026-10-17): the pull dance was five commands across two tools, and one of them (`--accept`)
sometimes said "nothing proposed" for reasons nobody could see.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(args, cwd, timeout=300):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).strip()


def plugin_root(arg):
    for cand in (arg, os.environ.get("CLAUDE_PLUGIN_ROOT"), os.path.dirname(HERE)):
        if cand and os.path.isfile(os.path.join(cand, ".claude-plugin", "plugin.json")):
            return os.path.abspath(cand)
    return None


def main(argv):
    opt = lambda k: argv[argv.index(k) + 1] if k in argv else None
    dry = "--dry-run" in argv
    rc, root = run(["git", "rev-parse", "--show-toplevel"], opt("--repo") or ".")
    root = root if rc == 0 else os.path.abspath(opt("--repo") or ".")
    if not os.path.isfile(os.path.join(root, ".reef", "config.json")):
        print(f"reef-update: {root} is not a Reef project (no .reef/config.json)", file=sys.stderr)
        return 2
    plugin = plugin_root(opt("--plugin"))
    if not plugin:
        print("reef-update: no plugin clone found — pass --plugin <dir>", file=sys.stderr)
        return 2
    rc, branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], plugin)
    if branch != "main":
        print(f"reef-update FAILED: the plugin clone {plugin} is on `{branch}`, not main — git -C {plugin} checkout main (the plugin runs whatever is checked out)")
        return 1
    rc, dirty = run(["git", "status", "--porcelain"], plugin)
    if dirty:
        print(f"reef-update FAILED: the plugin clone {plugin} has local changes — it is not a working tree; stash or commit them elsewhere")
        return 1
    _, old = run(["git", "rev-parse", "--short=12", "HEAD"], plugin)
    me = os.path.abspath(__file__)
    try:
        with open(me, "rb") as f:
            me_before = f.read()
    except OSError:
        me_before = None
    if dry:
        print(f"plugin: {plugin} at {old} (dry run: no pull)")
    else:
        rc, out = run(["git", "pull", "--ff-only", "-q"], plugin, timeout=600)
        if rc != 0:
            print(f"reef-update FAILED: git pull in {plugin}: {out.splitlines()[-1] if out else rc}")
            return 1
        _, new = run(["git", "rev-parse", "--short=12", "HEAD"], plugin)
        if new == old:
            print(f"plugin: {plugin} already at {new}")
        else:
            _, log = run(["git", "log", "--oneline", f"{old}..{new}"], plugin)
            print(f"plugin: {old}..{new} ({len(log.splitlines())} commit(s))")
            for l in log.splitlines()[:8]:
                print(f"  {l[:110]}")
        # this process is the copy loaded BEFORE the pull: a fix to reef-update itself would apply one pull late
        # (2026-10-18: the commit-filter fix of #55 ran old twice on the trial). The pull changed this file → run the new copy.
        try:
            with open(me, "rb") as f:
                me_after = f.read()
        except OSError:
            me_after = me_before
        if me_before is not None and me_after != me_before and "--no-reexec" not in argv:
            print("reef-update: the pull changed this script — running the new copy")
            sys.stdout.flush()
            os.execv(sys.executable, [sys.executable, me] + list(argv) + ["--no-reexec"])
    # .reef/config.json is the owner's file; reef-init only ADDS keys a new Reef ships (2026-10-18, qassimha: `graph.mode`
    # and `gates.timeout_s` sat uncommitted after a pull, so feature branches cut from the base lacked them). Committed
    # here only when it was clean before reef-init ran and every value it held is unchanged after: additions only.
    cfg_path = os.path.join(root, ".reef", "config.json")
    cfg_clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", ".reef/config.json"], cwd=root).returncode == 0
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg_before = json.load(f)
    except Exception:
        cfg_before = None
    man_path = os.path.join(root, ".reef", "init-manifest.json")
    def manifest():
        try:
            with open(man_path, encoding="utf-8") as f:
                m = json.load(f)
            return m if isinstance(m, dict) else {}
        except Exception:
            return {}
    man_before = manifest()
    dirty_before = {l[3:] for l in subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout.splitlines() if len(l) > 3}
    init = os.path.join(plugin, "scripts", "reef-init.py")
    args = [sys.executable, init, "--root", root, "--plugin", plugin] + (["--dry-run"] if dry else [])
    rc, out = run(args, root, timeout=600)
    lines = out.splitlines()
    summary = [l for l in lines if "written" in l or l.lstrip().startswith(("PROPOSED", "proposed", "skipped"))]
    for l in summary[:12]:
        print(f"init: {l.strip()}")
    if rc != 0:
        print(f"reef-update FAILED: reef-init exit {rc}" + (f": {lines[-1]}" if lines else ""))
        return 1
    r = subprocess.run(["git", "-C", root, "rev-parse", "--git-common-dir"], capture_output=True, text=True)   # reef-init's reef_dir
    g = r.stdout.strip()
    pdir = os.path.join(g if os.path.isabs(g) else os.path.join(root, g), "reef", "proposed") if r.returncode == 0 and g else os.path.join(root, ".reef", "proposed")
    props = []
    for dp, _, fn in os.walk(pdir):
        props += [os.path.relpath(os.path.join(dp, f), pdir) for f in fn if not f.endswith(".diff")]
    for p in props[:6]:
        print(f"proposal: {p} — accept: python3 {init} --root {root} --accept {p}   keep yours: --keep {p}")
    try:
        with open(os.path.join(plugin, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            version = str(json.load(f).get("version") or "?")
    except Exception:
        version = "?"
    _, sha = run(["git", "rev-parse", "--short=12", "HEAD"], plugin)
    paths = ["scripts", ".reef/init-manifest.json", ".reef/version", ".githooks", ".gitignore"]
    for cand in ("reef/README.md", "docs/REEF.md"):
        if os.path.isfile(os.path.join(root, cand)):
            paths.append(cand)
    # the porcelain lines are read RAW: run() strips the output, and the first line's status column starts with a
    # space — `.reef/init-manifest.json` sorts first, so three pulls on the trial committed the scripts and never the
    # manifest (2026-10-18). `.gitignore` carries the lines reef-init appends (status.html, cost/, graph/).
    st = subprocess.run(["git", "status", "--porcelain", "--"] + paths, cwd=root, capture_output=True, text=True)
    changed_files = [l[3:] for l in st.stdout.splitlines()
                     if len(l) > 3 and l[3:].startswith(("scripts/reef-", ".reef/", ".githooks/", ".gitignore", "reef/README.md", "docs/REEF.md"))]
    # 2026-10-21 (qassimha): reef-init rewrote AGENTS.md in place (Reef's untouched rendering) and it sat uncommitted
    for rel, h in manifest().items():
        if rel.startswith("_") or h == "owner" or rel in changed_files or rel == ".reef/config.json" or rel in dirty_before:
            continue
        if man_before.get(rel) != h and subprocess.run(["git", "ls-files", "--error-unmatch", "--", rel], cwd=root, capture_output=True).returncode == 0 \
                and subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel], cwd=root).returncode != 0:
            changed_files.append(rel)
    def only_added(old, new):
        if isinstance(old, dict) and isinstance(new, dict):
            return all(k in new and only_added(v, new[k]) for k, v in old.items())
        return old == new
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg_after = json.load(f)
    except Exception:
        cfg_after = None
    if cfg_clean and cfg_before is not None and cfg_after is not None and cfg_after != cfg_before and only_added(cfg_before, cfg_after):
        changed_files.append(".reef/config.json")
        print("config: reef-init added new keys, every value you set is unchanged — committed with Reef's files")
    elif cfg_after != cfg_before and cfg_before is not None:
        print("config: .reef/config.json changed beyond new keys (your uncommitted edits, or a value reef-init filled) — review it, then commit it")
    if not changed_files:
        print("project: nothing changed")
    elif "--commit" in argv and not dry:
        rc, out = run(["git", "add", "--"] + changed_files, root)
        if rc == 0:
            rc, out = run(["git", "commit", "-q", "-m", f"reef: scripts {version} ({sha})"], root, timeout=600)
        if rc != 0:
            print(f"reef-update FAILED: commit: {out.splitlines()[-1] if out else rc}")
            return 1
        print(f"project: committed {len(changed_files)} file(s) as 'reef: scripts {version} ({sha})'")
        if "--push" in argv:
            rc, out = run(["git", "push", "-q"], root, timeout=600)
            print("project: pushed" if rc == 0 else f"reef-update FAILED: push: {out.splitlines()[-1] if out else rc}")
            if rc != 0:
                return 1
    else:
        print(f"project: {len(changed_files)} Reef file(s) changed — commit them: git add -- {' '.join(changed_files[:6])}{' …' if len(changed_files) > 6 else ''} && git commit -m 'reef: scripts {version} ({sha})'   (or re-run with --commit)")
    print("now, in Claude Code:  /plugin marketplace update <marketplace>   then   /reload-plugins")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
