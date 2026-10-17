#!/usr/bin/env python3
# CLASS: code
"""Reef doctor — one screen that names what is wrong with THIS project's Reef and the command that fixes it.

Usage: reef-doctor.py [--repo DIR] [--plugin DIR] [--fetch]

Checks, each OK / WARN / FAIL with the fix on the same line:
  plugin   the plugin clone (--plugin, else $CLAUDE_PLUGIN_ROOT, else this script's own repo): on `main`, clean,
           not behind its upstream (--fetch asks the remote; without it the local view is reported as such)
  version  the project's .reef/version against the plugin's
  scripts  scripts/reef-* in the project (and in every feature worktree) identical to the plugin's
  queue    the queue has one home: no feature worktree carries queue edits the base lacks
  worktrees  each worktree, its branch, and whether it is a feature or a task checkout
  stamp    a design/critical task's adversarial-plan is current, a 0.6 stamp (--migrate) or stale
  loop     .reef/loop.json: active, wait, stop; the status page
  tools    gh auth, docker (when a compose file exists)
  proposals  renderings waiting in .reef/proposed/ and the command that accepts or keeps them
Exit 0 = no FAIL · 1 = at least one FAIL · 2 = not a Reef project.

Usability plan A1 (2026-10-17): the owner typed `--accept` and `--keep` by trial, pulled the plugin on the wrong
branch, and asked "why two AGENTS.md" — nothing on disk named the state or the fix.
"""
import importlib.machinery
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LINES = []


def say(level, what, fix=""):
    LINES.append(f"{level:<5}{what}" + (f" — {fix}" if fix else ""))


def git(cwd, *args, timeout=20):
    try:
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except Exception as e:
        return 1, str(e)


def plugin_root(arg):
    for cand in (arg, os.environ.get("CLAUDE_PLUGIN_ROOT"), os.path.dirname(HERE)):
        if cand and os.path.isfile(os.path.join(cand, ".claude-plugin", "plugin.json")):
            return os.path.abspath(cand)
    return None


def plugin_version(plugin):
    try:
        with open(os.path.join(plugin, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            return str(json.load(f).get("version") or "?")
    except Exception:
        return "?"


def behind_scripts(tree, plugin):
    """Project copies of scripts/reef-* that differ from the plugin's."""
    out = []
    sdir, pdir = os.path.join(tree, "scripts"), os.path.join(plugin, "scripts")
    for name in sorted(os.listdir(pdir) if os.path.isdir(pdir) else []):
        if not name.startswith("reef-"):
            continue
        mine = os.path.join(sdir, name)
        if not os.path.isfile(mine):
            continue
        try:
            with open(mine, "rb") as a, open(os.path.join(pdir, name), "rb") as b:
                if a.read() != b.read():
                    out.append(name)
        except OSError:
            continue
    return out


def stamp_states(root, checkouts, plugin, features):
    """Every design/critical task file in each checkout with an adversarial-plan stamp: (checkout, rel, state) where
    state is current / legacy (the 0.6 form, before the cut moved to ## Reviewer notes) / stale (neither)."""
    import glob
    import importlib.util
    spec = importlib.util.spec_from_loader("reef_adversarial", importlib.machinery.SourceFileLoader(
        "reef_adversarial", os.path.join(plugin, "scripts", "reef-adversarial")))
    adv = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(adv)
    except Exception:
        return []
    out = []
    for co in checkouts:
        for p in sorted(glob.glob(os.path.join(co, features, "*", "tasks", "*.md"))):
            try:
                with open(p, encoding="utf-8", newline="") as f:
                    text = f.read()
            except OSError:
                continue
            fm = adv.frontmatter(text) or {}
            got = (fm.get("adversarial-plan") or "").strip()
            if fm.get("tier") not in ("design", "critical") or not got:
                continue
            state = "current" if got == adv.plan_hash(text) else ("legacy" if got == adv.legacy_plan_hash(text) else "stale")
            out.append((co, os.path.relpath(p, co), state))
    return out


def worktrees(root):
    rc, out = git(root, "worktree", "list", "--porcelain")
    items, cur = [], {}
    for l in out.splitlines() + [""]:
        if l.startswith("worktree "):
            cur = {"path": l[len("worktree "):].strip(), "branch": ""}
        elif l.startswith("branch "):
            cur["branch"] = l[len("branch refs/heads/"):].strip() if l.startswith("branch refs/heads/") else l[len("branch "):]
        elif not l and cur:
            items.append(cur)
            cur = {}
    return items


def main(argv):
    repo = argv[argv.index("--repo") + 1] if "--repo" in argv else "."
    rc, root = git(repo, "rev-parse", "--show-toplevel")
    root = root if rc == 0 else os.path.abspath(repo)
    cfg_path = os.path.join(root, ".reef", "config.json")
    if not os.path.isfile(cfg_path):
        print(f"reef-doctor: {root} has no .reef/config.json — not a Reef project (run /reef-init)", file=sys.stderr)
        return 2
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    base = str((cfg.get("branches") or {}).get("base", "main") or "main")
    prefix = str((cfg.get("branches") or {}).get("feature_prefix", "feat/") or "feat/")
    queue = str((cfg.get("paths") or {}).get("queue", "docs/queue.md"))
    plugin = plugin_root(argv[argv.index("--plugin") + 1] if "--plugin" in argv else None)

    # plugin
    if not plugin:
        say("FAIL", "plugin: no plugin clone found", "pass --plugin <dir> (the clone /plugin marketplace points at)")
    else:
        _, br = git(plugin, "rev-parse", "--abbrev-ref", "HEAD")
        _, dirty = git(plugin, "status", "--porcelain")
        if "--fetch" in argv:
            git(plugin, "fetch", "-q", timeout=60)
        rc_b, behind = git(plugin, "rev-list", "--count", "HEAD..@{u}")
        if br != "main":
            say("WARN", f"plugin: {plugin} is on `{br}`", f"the plugin runs whatever is checked out: git -C {plugin} checkout main && git -C {plugin} pull")
        elif dirty:
            say("WARN", f"plugin: {plugin} has local changes", "the plugin clone is not a working tree: commit elsewhere or git -C … stash")
        elif rc_b == 0 and behind.isdigit() and int(behind) > 0:
            say("WARN", f"plugin: {behind} commit(s) behind its upstream", f"python3 {plugin}/scripts/reef-update.py --repo {root} --commit")
        else:
            say("OK", f"plugin: {plugin} on main, clean" + ("" if "--fetch" in argv else " (local view; --fetch asks the remote)"))
        # version
        pv = plugin_version(plugin)
        try:
            with open(os.path.join(root, ".reef", "version"), encoding="utf-8") as f:
                mv = f.read().strip()
        except OSError:
            mv = "none (a 0.5 project)"
        say("OK" if mv == pv else "WARN", f"version: project {mv}, plugin {pv}", "" if mv == pv else "python3 scripts/reef-init.py --root . --plugin <plugin> brings the project's copy up")
        # scripts, main checkout and every worktree
        b = behind_scripts(root, plugin)
        if b:
            say("WARN", f"scripts: {len(b)} project script(s) differ from the plugin's ({', '.join(b[:3])}{'…' if len(b) > 3 else ''})",
                f"python3 {plugin}/scripts/reef-update.py --repo {root} --commit")
        else:
            say("OK", "scripts: scripts/reef-* match the plugin")
    # worktrees
    wts = worktrees(root)
    for w in wts[1:]:
        kind = "feature" if w["branch"].startswith(prefix) else ("task" if w["branch"].startswith("task/") else "other")
        note = ""
        if plugin:
            bw = behind_scripts(w["path"], plugin)
            if bw:
                note = f"{len(bw)} script(s) behind the plugin — the loop rebases it on {base}; or git -C {w['path']} merge {base}"
        if kind == "feature":
            rc_f, fork = git(root, "merge-base", base, w["branch"])
            if rc_f == 0 and fork:
                rc_d, diff = git(root, "diff", "--name-only", fork, w["branch"], "--", queue, os.path.join(os.path.dirname(queue), "queue-archive.md"))
                if rc_d == 0 and diff.strip():
                    say("FAIL", f"queue: {w['branch']} carries queue edits the base lacks ({diff.strip().splitlines()[0]})",
                        f"the queue has one home, {base}: git -C {w['path']} checkout {base} -- {queue}")
        say("WARN" if note else "OK", f"worktree: {os.path.relpath(w['path'], root)} [{w['branch'] or 'detached'}] ({kind})", note)
    if len(wts) <= 1:
        say("OK", "worktrees: none (nothing building)")
    # the hunter's plan stamps (2026-10-18: the cut moved and every earlier stamp read as "the plan changed")
    if plugin:
        features = str((cfg.get("paths") or {}).get("features") or "reef/features")
        states = stamp_states(root, [root] + [w["path"] for w in wts[1:]], plugin, features)
        for co, rel, state in states:
            if state == "legacy":
                say("WARN", f"stamp: {rel} carries a 0.6 adversarial-plan (the plan is unchanged)",
                    f"cd {co} && python3 {os.path.join(plugin, 'scripts', 'reef-adversarial')} {rel} plan --migrate  (the plugin's copy: a worktree's scripts/ lags)")
            elif state == "stale":
                say("WARN", f"stamp: {rel}: the plan changed since the hunter's pass",
                    "the hunter's re-check within hunter.plan_rounds, or `reef-adversarial <task> plan --decided <mark>` at the gate")
        if states and all(st == "current" for _, _, st in states):
            say("OK", f"stamps: {len(states)} design/critical task(s) current")
        # records written before 2026-10-18 carry the 0.6 digest form (the hunter's stamp inside); the plugin's plan-check names them
        import glob
        pc = os.path.join(plugin, "scripts", "reef-plan-check.py")
        legacy_recs = 0
        for co in [root] + [w["path"] for w in wts[1:]]:
            for spec in sorted(glob.glob(os.path.join(co, features, "*", "SPEC.md"))):
                slug = os.path.basename(os.path.dirname(spec))
                try:
                    r = subprocess.run([sys.executable, pc, co, "--verify-stamp", "--feature", slug], capture_output=True, text=True, timeout=60)
                except Exception:
                    continue
                if re.search(r"^(stamp|approval|review): LEGACY", r.stdout, re.M):
                    legacy_recs += 1
                    say("WARN", f"records: {slug} in {os.path.relpath(co, root) or '.'} carry the 0.6 digest form (the plan is unchanged)",
                        f"cd {co} && python3 {pc} . --migrate-records --feature {slug}  (after its scripts/ match the plugin)")
        if not legacy_recs:
            say("OK", "records: every approval and review record in the current digest form")
    # loop
    try:
        with open(os.path.join(root, ".reef", "loop.json"), encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        st = {}
    state = "active" if st.get("active") else "inactive"
    if st.get("stop"):
        say("WARN", f"loop: {state}, STOP={str(st['stop'])[:90]}", "/clear, then /reef:loop re-enters from HANDOFF.md")
    elif st.get("wait"):
        say("OK", f"loop: {state}, waiting — {str(st['wait'])[:100]}")
    else:
        say("OK", f"loop: {state}")
    page = os.path.join(root, ".reef", "status.html")
    say("OK" if os.path.isfile(page) else "WARN", f"status page: {page}" if os.path.isfile(page) else "status page: not written yet",
        "" if os.path.isfile(page) else "the next tick writes it (python3 scripts/reef-loop.py tick)")
    # tools
    try:
        rc_gh = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=20).returncode
        say("OK" if rc_gh == 0 else "WARN", "gh: authenticated" if rc_gh == 0 else "gh: not authenticated", "" if rc_gh == 0 else "gh auth login (the loop reviews and merges PRs through gh)")
    except Exception:
        say("WARN", "gh: not installed", "install the GitHub CLI; the loop reviews and merges PRs through it")
    if any(os.path.isfile(os.path.join(root, n)) for n in ("compose.yaml", "compose.yml", "docker-compose.yml")):
        try:
            rc_d = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=20).returncode
            say("OK" if rc_d == 0 else "WARN", "docker: running" if rc_d == 0 else "docker: not running", "" if rc_d == 0 else "start Docker before a task that needs the database")
        except Exception:
            say("WARN", "docker: not installed", "the project has a compose file; its tests need Docker")
    # proposals
    pdir = os.path.join(root, ".reef", "proposed")
    props = []
    for dp, _, fn in os.walk(pdir):
        props += [os.path.relpath(os.path.join(dp, f), pdir) for f in fn if not f.endswith(".diff")]
    if props:
        say("WARN", f"proposals: {len(props)} rendering(s) waiting ({props[0]}{'…' if len(props) > 1 else ''})",
            f"python3 scripts/reef-init.py --accept {props[0]}  (or --keep {props[0]} to keep yours)")
    else:
        say("OK", "proposals: none")
    for l in LINES[:40]:
        print(l)
    return 1 if any(l.startswith("FAIL") for l in LINES) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
