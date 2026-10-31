#!/usr/bin/env python3
# CLASS: code
"""Reef doctor — one screen that names what is wrong with THIS project's Reef and the command that fixes it.

Usage: reef-doctor.py [--repo DIR] [--plugin DIR] [--fetch]

Checks, each OK / WARN / FAIL with the fix on the same line:
  plugin   the plugin clone (--plugin, else $CLAUDE_PLUGIN_ROOT, else this script's own repo): on `main`, clean,
           not behind its upstream (--fetch asks the remote; without it the local view is reported as such); behind, the
           line says `a new Reef`, the commits and the newest subject, and the one fix (the owner's screen shows it as one item)
  version  the project's .reef/version against the plugin's
  scripts  scripts/reef-* in the project (and in every feature worktree) identical to the plugin's
  queue    the queue has one home: no feature worktree carries queue edits the base lacks
  worktrees  each worktree, its branch, and whether it is a feature or a task checkout
  stamp    a design/critical task's adversarial-plan is current or stale
  loop     .reef/loop.json: active, wait, stop; the status page
  tools    gh auth, docker (when a compose file exists)
  proposals  renderings waiting in <git dir>/reef/proposed/ and the command that accepts or keeps them
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
from functools import partial
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # the shared helpers live beside this script
sys.dont_write_bytecode = True   # and no scripts/__pycache__ lands in a project's tree (reef-update, a row worktree read it as changes)
from reef_common import lint_state, read_hold, git_rc, plugin_root, plugin_version  # noqa: E402

LINES = []


def say(level, what, fix=""):
    LINES.append(f"{level:<5}{what}" + (f" — {fix}" if fix else ""))


git = partial(git_rc, timeout=20)


def plugin_enabled():
    """(level, what, fix): is the Reef plugin ENABLED in Claude Code (2026-10-28: a marketplace update left it disabled and
    nothing said so — no guard in any session, and the runner's probe failed)."""
    try:
        r = subprocess.run(["claude", "plugin", "list"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return "WARN", "plugin enabled: cannot tell (`claude` is not on the PATH here)", ""
    if r.returncode != 0:
        return "WARN", f"plugin enabled: cannot tell — `claude plugin list` exited {r.returncode}: {(r.stderr or r.stdout).strip()[:100]}", ""
    block, name = "", ""
    for chunk in re.split(r"\n(?=\s*❯ )", r.stdout):
        m = re.search(r"❯\s*(reef@\S+)", chunk)
        if m:
            block, name = chunk, m.group(1)
    if not block:
        return "WARN", "plugin enabled: no reef@… plugin is installed in Claude Code", "/plugin marketplace add … then install reef"
    if re.search(r"Status:.*(disabled|✘)", block):
        return "FAIL", f"plugin enabled: NO — {name} is disabled: no guard in any session, the runner's probe fails", f"claude plugin enable {name}"
    return "OK", f"plugin enabled: {name}", ""


def update_fix(root, plugin):
    """The fix for a new Reef — the clone behind its upstream, the version, the scripts, a missing script: ONE command. The project's
    own verb where it has scripts/reef (`reef update`: pull, copies, one commit pushed, the setup re-proved, the marketplace refreshed;
    the screen lists one item for it — hands-off step 6); the plugin's script on a project without the entry point."""
    if os.path.isfile(os.path.join(root, "scripts", "reef")):
        return "python3 scripts/reef update"
    return f"python3 {plugin}/scripts/reef-update.py --repo {root} --commit"


def fetch_plugin(plugin):
    """The clone's upstream asked, unattended (the owner's screen runs this every fifteen minutes): no prompt from git or ssh, a
    forge that does not answer leaves the local view."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    if not env.get("GIT_SSH_COMMAND") and not git(plugin, "config", "core.sshCommand")[1]:   # a configured ssh command wins (the env var would override it)
        env["GIT_SSH_COMMAND"] = "ssh -oBatchMode=yes"
    try:
        subprocess.run(["git", "-C", plugin, "fetch", "-q"], capture_output=True, text=True, timeout=60, env=env, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        pass


def behind_scripts(tree, plugin):
    """Project copies of scripts/reef, scripts/reef-* and scripts/reef_* that differ from the plugin's."""
    out = []
    sdir, pdir = os.path.join(tree, "scripts"), os.path.join(plugin, "scripts")
    for name in sorted(os.listdir(pdir) if os.path.isdir(pdir) else []):
        if name != "reef" and not name.startswith(("reef-", "reef_")):
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
    state is current or stale."""
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
            state = "current" if got == adv.plan_hash(text) else "stale"
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
            fetch_plugin(plugin)
        rc_b, behind = git(plugin, "rev-list", "--count", "HEAD..@{u}")
        if br != "main":
            say("WARN", f"plugin: {plugin} is on `{br}`", f"the plugin runs whatever is checked out: git -C {plugin} checkout main && git -C {plugin} pull")
        elif dirty:
            say("WARN", f"plugin: {plugin} has local changes", "the plugin clone is not a working tree: commit elsewhere or git -C … stash")
        elif rc_b == 0 and behind.isdigit() and int(behind) > 0:
            _, subject = git(plugin, "log", "-1", "--format=%s", "HEAD..@{u}")   # the forge's text on the owner's screen: printable only
            subject = "".join(c for c in subject if c.isprintable())[:80]
            say("WARN", f"plugin: a new Reef, {behind} commit(s) since your copy" + (f": {subject}" if subject else ""), update_fix(root, plugin))
        else:
            say("OK", f"plugin: {plugin} on main, clean" + ("" if "--fetch" in argv else " (local view; --fetch asks the remote)"))
        # version
        pv = plugin_version(plugin)
        try:
            with open(os.path.join(root, ".reef", "version"), encoding="utf-8") as f:
                mv = f.read().strip()
        except OSError:
            mv = "none (a 0.5 project)"
        say("OK" if mv == pv else "WARN", f"version: project {mv}, plugin {pv}", "" if mv == pv else update_fix(root, plugin))
        # scripts, main checkout and every worktree
        b = behind_scripts(root, plugin)
        if b:
            say("WARN", f"scripts: {len(b)} project script(s) differ from the plugin's ({', '.join(b[:3])}{'…' if len(b) > 3 else ''})",
                update_fix(root, plugin))
        else:
            say("OK", "scripts: scripts/reef-* match the plugin")
    # the project's linters and Reef's copied scripts (2026-10-29: ruff on an adoption flagged 1,725 errors, CI red)
    configured, gaps = lint_state(root)
    for where, line in gaps:
        say("WARN", f"lint: {where} scans Reef's scripts (rendered, replaced on every upgrade)", line)
    if configured and not gaps:
        say("OK", "lint: the project's linters leave Reef's scripts alone")
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
    # the hunter's plan stamps
    if plugin:
        features = str((cfg.get("paths") or {}).get("features") or "reef/features")
        states = stamp_states(root, [root] + [w["path"] for w in wts[1:]], plugin, features)
        for co, rel, state in states:
            where = os.path.relpath(co, root) or "."
            if state == "stale":
                say("WARN", f"stamp: {rel} in {where}: the plan changed since the hunter's pass",
                    "the hunter's re-check within hunter.plan_rounds, or `reef-adversarial <task> plan --decided <mark>` at the gate")
        if states and all(st == "current" for _, _, st in states):
            say("OK", f"stamps: {len(states)} design/critical task(s) current")
    # loop
    try:
        with open(os.path.join(root, ".reef", "loop.json"), encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        st = {}
    state = "active" if st.get("active") else "inactive"
    if st.get("stop"):
        say("WARN", f"loop: {state}, STOP={str(st['stop'])[:90]}", "/clear, then /reef-loop re-enters from HANDOFF.md")
    elif st.get("wait"):
        say("OK", f"loop: {state}, waiting — {str(st['wait'])[:100]}")
    else:
        say("OK", f"loop: {state}")
    # 2026-10-28 (the owner, after the first night): what stopped a normal round that day, each with the one command
    held = read_hold(root)
    if held is not None:
        alive = held["alive"]
        say("OK" if alive else "WARN", f"hold: session {(held['session'] or '?')[:8]} holds the loop (process {held['pid'] or '?'} {'alive' if alive else 'dead'}) (a dead session's hold; the runner takes one over by itself)",
            "" if alive else "python3 scripts/reef-loop.py unlock")
    else:
        say("OK", "hold: nobody holds the loop")
    try:
        with open(os.path.join(root, ".reef", "run", "gate.json"), encoding="utf-8") as f:
            gate = json.load(f)
    except (OSError, ValueError):
        gate = {}
    say("OK" if gate.get("ok") else "WARN", f"gate probe: GATE OK for --permission-mode {gate.get('mode')}" if gate.get("ok") else "gate probe: none — the runner refuses to start",
        "" if gate.get("ok") else "python3 scripts/reef-run.py probe")
    gmode = str(((cfg.get("graph") or {}) if isinstance(cfg.get("graph"), dict) else {}).get("mode", "auto") or "auto").strip().lower()
    if gmode != "chat":   # 2026-10-31: the owner's project had graph.mode auto, no graph gate, every row built in chat mode, and no line said so
        try:
            with open(os.path.join(root, ".reef", "graph", "gate.json"), encoding="utf-8") as f:
                ggate = json.load(f)
        except (OSError, ValueError):
            ggate = {}
        headless = "the runner's sessions build in chat mode either way: a headless session has no Workflow tool"
        say("OK" if ggate.get("ok") else "WARN",
            f"graph gate: GATE OK — a row you build yourself (/reef-loop, /reef-graph) runs as one workflow; {headless}" if ggate.get("ok")
            else f"graph gate: FAILED ({ggate.get('why') or 'the hooks did not reach the workflow agent'}) — your own sessions build in chat mode too" if ggate
            else f"graph gate: none — graph.mode {gmode}: /reef-graph once, in a Claude Code session in this project, proves it for the rows you build yourself; {headless}")
    setup_s = os.path.join(root, "scripts", "reef-setup.py")
    if os.path.isfile(setup_s):
        try:
            r_s = subprocess.run([sys.executable, setup_s, "state", "--repo", root], capture_output=True, text=True, timeout=60)
            line = (r_s.stdout.strip().splitlines() or ["setup: ?"])[0]
            say("OK" if r_s.returncode == 0 else "WARN", line[:140],
                "" if r_s.returncode == 0 else "python3 scripts/reef-setup.py prove" if r_s.returncode == 3 else "edit .reef/config.json worktree.setup, then python3 scripts/reef-setup.py prove")
        except (OSError, subprocess.TimeoutExpired):
            say("WARN", "setup: reef-setup.py state did not run", "")
    else:
        say("WARN", "setup: scripts/reef-setup.py is missing (the proof that a fresh worktree passes the gate)", update_fix(root, plugin))
    say(*plugin_enabled())
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
    # .env (0.7.2, first adoption 2026-10-24): Prisma loads the checkout's .env; with two keys set, the base branch failed 21 tests
    # that pass in CI. One line, key NAMES only, no automatic double run.
    full = str((cfg.get("gates") or {}).get("full", "") or "")
    if full and os.path.isfile(os.path.join(root, ".env")):
        with open(os.path.join(root, ".env"), encoding="utf-8", errors="replace") as f:
            keys = [m.group(1) for m in re.finditer(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", f.read(), re.M)]
        say("WARN", f"env: the local gate reads .env ({len(keys)} key(s): {', '.join(keys)}), CI does not",
            f"compare once: {' '.join(k + '=' for k in keys)} {full}")
    # proposals
    r = subprocess.run(["git", "-C", root, "rev-parse", "--git-common-dir"], capture_output=True, text=True)   # reef-init's reef_dir
    g = r.stdout.strip()
    pdir = os.path.join(g if os.path.isabs(g) else os.path.join(root, g), "reef", "proposed") if r.returncode == 0 and g else os.path.join(root, ".reef", "proposed")
    props = []
    for dp, _, fn in os.walk(pdir):
        props += [os.path.relpath(os.path.join(dp, f), pdir) for f in fn if not f.endswith(".diff")]
    if props:
        say("WARN", f"proposals: {len(props)} rendering(s) waiting ({props[0]}{'…' if len(props) > 1 else ''}; --keep instead of --accept keeps yours)",
            f"python3 {plugin}/scripts/reef-init.py --root {root} --accept {props[0]}")   # a project has no scripts/reef-init.py (2026-10-31)
    else:
        say("OK", "proposals: none")
    for l in LINES[:40]:
        print(l)
    return 1 if any(l.startswith("FAIL") for l in LINES) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
