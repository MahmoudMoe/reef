#!/usr/bin/env python3
"""Reef graph scheduler — the task set as a DAG that is EXECUTED, not just declared.

Usage:
  reef-graph.py ready   [--root DIR] [--json]          the ready set, one task per line
  reef-graph.py status  [--root DIR]                   every task: status, deps, resources
  reef-graph.py check   <task-file>                    exit 0 = ready to dispatch, 2 = not (reason on stderr)
  reef-graph.py worktree <task-file> [--base BRANCH]   create/reuse the task's worktree, record `worktree:`
  reef-graph.py lock <resource> [--timeout S] -- cmd   run cmd holding one slot of a shared resource

A task is READY iff (the invariant, docs/design/graph-and-setup.md §1):
  status is pending or in-progress; every blocked-by id is done; attempts < cap;
  each declared resource has a free slot once this task's own holding is discounted;
  the number of OTHER in-progress tasks is below graph.parallel.

State is the task files' frontmatter only (status, worktree) — a restart recomputes
the graph from disk. A broken graph (duplicate id, dangling blocked-by, cycle) has
NO ready set: `check` denies and `ready` exits 1, never a best-effort subset.

The PreToolUse guard (reef-guard.py) imports this file from the plugin's own directory
and takes the graph lock (graph_lock_path) around read-all -> decide -> mark
in-progress, so two dispatches racing for the last parallel slot cannot both win.
Exit codes: 0 ok, 1 broken graph / bad usage, 2 not ready, 75 lock timeout.
"""
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

DEFAULT_PARALLEL = 10
DEFAULT_CAP = 3
DEFAULT_SLOTS = 1
EX_TEMPFAIL = 75
FENCE = re.compile(r"\A---\r?\n(.*?\r?\n)---\r?\n", re.S)
TASK_NAME_RE = re.compile(r"(R?)(\d+)-.*\.md$")
ACTIVE = ("pending", "in-progress")


class GraphError(Exception):
    """The graph cannot be scheduled (not 'this task is not ready')."""


# ---------------------------------------------------------------- frontmatter

def read_frontmatter(path):
    """Column-0 keys, FIRST occurrence wins — the same reading as reef-guard.py and
    reef-attempt, so a duplicated or indented key cannot read differently here."""
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    m = FENCE.match(text)
    if not m:
        raise GraphError(f"{path}: no frontmatter fence — not a reef task file")
    fm = {}
    for line in m.group(1).splitlines():
        if line[:1] in (" ", "\t", "#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        fm.setdefault(key.strip(), val.strip().strip('"'))
    return fm, text


def parse_list(raw):
    raw = (raw or "").strip()
    if raw == "":
        return []
    if not (raw.startswith("[") and raw.endswith("]")):
        raise GraphError(f"not a list: {raw!r}")
    inner = raw[1:-1].strip()
    return [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()] if inner else []


def set_keys(path, text, updates):
    """Rewrite frontmatter keys in place (unique temp + atomic replace). Keys are
    added at the end of the fence when absent; the body is never touched."""
    m = FENCE.match(text)
    fm = m.group(1)
    for key, value in updates.items():
        if re.search(rf"^{re.escape(key)}:", fm, re.M):
            fm = re.sub(rf"^{re.escape(key)}:.*$", f"{key}: {value}", fm, count=1, flags=re.M)
        else:
            fm = fm + f"{key}: {value}\n"
    new_text = text[:m.start(1)] + fm + text[m.end(1):]
    fd, tmp = tempfile.mkstemp(prefix=".reef-graph-", dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------- layout

def repo_root(start):
    """Walk up from a task file (or directory) to the first .reef/ or .git/ marker —
    the same rule as reef-attempt; never the caller's cwd."""
    probe = os.path.abspath(start)
    if os.path.isfile(probe):
        probe = os.path.dirname(probe)
    while True:
        if os.path.isdir(os.path.join(probe, ".reef")) or os.path.exists(os.path.join(probe, ".git")):
            return probe
        parent = os.path.dirname(probe)
        if parent == probe:
            return os.path.abspath(start) if os.path.isdir(start) else os.path.dirname(os.path.abspath(start))
        probe = parent


def read_config(root):
    try:
        with open(os.path.join(root, ".reef", "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def tasks_dir_for(root, cfg, task_path=None):
    """The task file's own directory decides (done/ -> its parent); the config's
    paths.tasks is the fallback when no file is given."""
    if task_path:
        d = os.path.dirname(os.path.abspath(task_path))
        return os.path.dirname(d) if os.path.basename(d) == "done" else d
    return os.path.join(root, cfg.get("paths", {}).get("tasks", "tasks"))


def graph_lock_path(tasks_dir):
    """ONE lock for the whole task set (not the per-file lock reef-attempt takes):
    the ready decision reads every file. Lives in tmp, never unlinked."""
    digest = hashlib.sha1(os.path.abspath(tasks_dir).encode()).hexdigest()
    return os.path.join(tempfile.gettempdir(), f"reef-graph-{digest}")


def cfg_int(cfg, keys, default):
    """Integer setting at cfg[keys...]; absent -> default; present but not a positive
    integer -> GraphError (a nonsense cap must never silently become the default)."""
    node = cfg
    for k in keys:
        if not isinstance(node, dict) or k not in node:
            return default
        node = node[k]
    if isinstance(node, bool) or not isinstance(node, int):
        try:
            node = int(str(node).strip())
        except ValueError:
            raise GraphError(f".reef/config.json {'.'.join(keys)}={node!r} is not an integer")
    if node < 1:
        raise GraphError(f".reef/config.json {'.'.join(keys)}={node} must be >= 1")
    return node


def slots_for(cfg, resource):
    return cfg_int(cfg, ["resources", resource, "slots"], DEFAULT_SLOTS)


# ---------------------------------------------------------------- graph

class Task:
    __slots__ = ("path", "fm", "text", "id", "canon", "deps", "resources", "status", "attempts")

    def __init__(self, path):
        self.path = path
        self.fm, self.text = read_frontmatter(path)
        raw_id = self.fm.get("id", "")
        if not re.fullmatch(r"R?\d+", raw_id):
            raise GraphError(f"{path}: id={raw_id!r} is not NNN or RNN")
        self.id = raw_id
        self.canon = ("R" + str(int(raw_id[1:]))) if raw_id.startswith("R") else str(int(raw_id))
        try:
            self.deps = [str(int(x)) for x in parse_list(self.fm.get("blocked-by", "[]"))]
        except ValueError:
            raise GraphError(f"{path}: blocked-by must hold numeric ids")
        self.resources = parse_list(self.fm.get("resources", "[]"))
        self.status = self.fm.get("status", "pending")
        try:
            self.attempts = int(self.fm.get("attempts", "0") or 0)
        except ValueError:
            raise GraphError(f"{path}: attempts is not an integer")
        if self.attempts < 0:
            raise GraphError(f"{path}: attempts is negative")


def load_graph(tasks_dir):
    """Every task under tasks/ and tasks/done/, validated as a DAG. Raises GraphError
    on anything that makes a ready set meaningless."""
    files = []
    for d in (tasks_dir, os.path.join(tasks_dir, "done")):
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if TASK_NAME_RE.match(f):
                    files.append(os.path.join(d, f))
    tasks = {}
    for p in files:
        t = Task(p)
        if t.canon in tasks:
            raise GraphError(f"duplicate task id {t.canon}: {tasks[t.canon].path} and {p}")
        tasks[t.canon] = t
    for t in tasks.values():
        missing = [d for d in t.deps if d not in tasks]
        if missing:
            raise GraphError(f"{t.path}: blocked-by refers to missing task id(s) {missing}")
    # cycle check (iterative DFS; a deep chain must not hit the recursion limit)
    state = {}
    for start in tasks:
        if state.get(start):
            continue
        stack = [(start, iter(tasks[start].deps))]
        state[start] = 1
        path = [start]
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                state[node] = 2
                stack.pop()
                path.pop()
                continue
            if state.get(nxt) == 1:
                cyc = path[path.index(nxt):] + [nxt]
                raise GraphError("dependency cycle: " + " -> ".join(cyc))
            if not state.get(nxt):
                state[nxt] = 1
                path.append(nxt)
                stack.append((nxt, iter(tasks[nxt].deps)))
    return tasks


def not_ready_reason(tasks, t, cfg):
    """None when t is ready, else the human-readable reason."""
    cap = cfg_int(cfg, ["caps", "attempts"], DEFAULT_CAP)
    parallel = cfg_int(cfg, ["graph", "parallel"], DEFAULT_PARALLEL)
    if t.status not in ACTIVE:
        return f"status is {t.status!r} (only pending/in-progress tasks dispatch)"
    if t.attempts >= cap:
        return f"at the retry cap ({t.attempts}/{cap})"
    undone = [d for d in t.deps if tasks[d].status != "done"]
    if undone:
        return "blocked-by not done: " + ", ".join(f"{d} ({tasks[d].status})" for d in undone)
    others = [o for o in tasks.values() if o is not t and o.status == "in-progress"]
    for r in t.resources:
        holders = [o.canon for o in others if r in o.resources]
        if len(holders) >= slots_for(cfg, r):
            return f"resource {r!r} held by task(s) {', '.join(holders)} ({len(holders)}/{slots_for(cfg, r)} slots)"
    if t.status != "in-progress" and len(others) >= parallel:
        return f"parallel cap {parallel} reached (in progress: {', '.join(o.canon for o in others)})"
    return None


def ready_set(tasks, cfg):
    return [t for _, t in sorted(tasks.items(), key=lambda kv: (kv[0].startswith("R"), int(kv[0].lstrip("R"))))
            if not_ready_reason(tasks, t, cfg) is None]


def find_task(tasks, task_path):
    ap = os.path.abspath(task_path)
    for t in tasks.values():
        if os.path.abspath(t.path) == ap:
            return t
    raise GraphError(f"{task_path} is not among the task files of its tasks directory")


def check_task(task_path, cfg=None):
    """(ready: bool, reason: str|None, tasks). Raises GraphError on a broken graph."""
    root = repo_root(task_path)
    cfg = read_config(root) if cfg is None else cfg
    tasks = load_graph(tasks_dir_for(root, cfg, task_path))
    t = find_task(tasks, task_path)
    return not_ready_reason(tasks, t, cfg), tasks, t


# ---------------------------------------------------------------- commands

def cmd_ready(root, as_json):
    cfg = read_config(root)
    tasks = load_graph(tasks_dir_for(root, cfg))
    ready = ready_set(tasks, cfg)
    if as_json:
        print(json.dumps([{"id": t.canon, "path": t.path, "status": t.status,
                           "resources": t.resources} for t in ready]))
    else:
        for t in ready:
            print(f"{t.canon}\t{t.status}\t{os.path.relpath(t.path, root)}")
    return 0


def cmd_status(root):
    cfg = read_config(root)
    tasks = load_graph(tasks_dir_for(root, cfg))
    for canon, t in sorted(tasks.items(), key=lambda kv: (kv[0].startswith("R"), int(kv[0].lstrip("R")))):
        reason = not_ready_reason(tasks, t, cfg)
        state = "READY" if reason is None else ("done" if t.status == "done" else f"waiting: {reason}")
        print(f"{canon}\t{t.status}\tblocked-by={t.deps}\tresources={t.resources}\t{state}")
    return 0


def cmd_check(task_path):
    reason, _, _ = check_task(task_path)
    if reason is None:
        print(f"ready: {task_path}")
        return 0
    print(f"reef-graph NOT READY: {task_path}: {reason}", file=sys.stderr)
    return 2


def cmd_worktree(task_path, base):
    root = repo_root(task_path)
    cfg = read_config(root)
    tasks = load_graph(tasks_dir_for(root, cfg, task_path))
    t = find_task(tasks, task_path)
    wt_root = os.path.join(root, cfg.get("worktree", {}).get("dir", ".reef/worktrees"))
    wt = os.path.join(wt_root, t.canon)
    slug = re.sub(r"^R?\d+-", "", os.path.basename(t.path))[:-3]
    branch = f"task/{t.canon}-{slug}"
    if not os.path.isdir(wt):
        os.makedirs(wt_root, exist_ok=True)
        if base is None:
            base = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root,
                                  capture_output=True, text=True, check=True).stdout.strip()
        exists = subprocess.run(["git", "rev-parse", "-q", "--verify", f"refs/heads/{branch}"],
                                cwd=root, capture_output=True).returncode == 0
        args = ["git", "worktree", "add", "-q"] + (["-b", branch] if not exists else []) + [wt] + \
               ([base] if not exists else [branch])
        r = subprocess.run(args, cwd=root, capture_output=True, text=True)
        if r.returncode != 0:
            raise GraphError(f"git worktree add failed: {r.stderr.strip()}")
        setup = str(cfg.get("worktree", {}).get("setup", "") or "")
        if setup.strip():
            r = subprocess.run(["sh", "-c", setup], cwd=wt)
            if r.returncode != 0:
                raise GraphError(f"worktree.setup {setup!r} exited {r.returncode}")
    with open(graph_lock_path(tasks_dir_for(root, cfg, task_path)), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        fm, text = read_frontmatter(t.path)
        set_keys(t.path, text, {"worktree": os.path.relpath(wt, root)})
    print(f"worktree: {wt}")
    print(f"branch: {branch}")
    return 0


def cmd_lock(root, resource, timeout, command):
    """Hold ONE of N slots (N = resources.<name>.slots) while running command.
    N numbered lock files + fcntl: no flock(1) (macOS lacks it). A --timeout is
    always in force: a stuck holder is reported (exit 75), never waited for forever."""
    cfg = read_config(root)
    n = slots_for(cfg, resource)
    base = os.path.join(tempfile.gettempdir(),
                        f"reef-slot-{hashlib.sha1(os.path.abspath(root).encode()).hexdigest()}-{resource}")
    deadline = time.monotonic() + timeout
    handles = [open(f"{base}-{i}", "a") for i in range(n)]
    try:
        while True:
            for h in handles:
                try:
                    fcntl.flock(h, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    continue
                r = subprocess.run(command, cwd=root)
                return r.returncode
            if time.monotonic() >= deadline:
                print(f"reef-graph lock: no free slot of {resource!r} ({n}) within {timeout}s", file=sys.stderr)
                return EX_TEMPFAIL
            time.sleep(0.2)
    finally:
        for h in handles:
            h.close()


def usage(msg=""):
    if msg:
        print(f"reef-graph: {msg}", file=sys.stderr)
    print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
    return 1


def main(argv):
    if not argv:
        return usage()
    cmd, rest = argv[0], argv[1:]
    root = None
    as_json = False
    base = None
    timeout = 600.0
    positional = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--root" and i + 1 < len(rest):
            root = rest[i + 1]; i += 2
        elif a == "--json":
            as_json = True; i += 1
        elif a == "--base" and i + 1 < len(rest):
            base = rest[i + 1]; i += 2
        elif a == "--timeout" and i + 1 < len(rest):
            try:
                timeout = float(rest[i + 1])
            except ValueError:
                return usage("--timeout takes seconds")
            i += 2
        elif a == "--":
            positional.extend(["--"] + rest[i + 1:]); break
        else:
            positional.append(a); i += 1
    try:
        if cmd in ("ready", "status"):
            root = os.path.abspath(root or repo_root(os.getcwd()))
            return cmd_ready(root, as_json) if cmd == "ready" else cmd_status(root)
        if cmd == "check":
            if len(positional) != 1:
                return usage("check takes exactly one task file")
            if not os.path.isfile(positional[0]):
                return usage(f"task file not found: {positional[0]}")
            return cmd_check(positional[0])
        if cmd == "worktree":
            if len(positional) != 1 or not os.path.isfile(positional[0]):
                return usage("worktree takes exactly one existing task file")
            return cmd_worktree(positional[0], base)
        if cmd == "lock":
            if len(positional) < 3 or positional[1] != "--":
                return usage("lock <resource> [--timeout S] -- cmd args...")
            root = os.path.abspath(root or repo_root(os.getcwd()))
            return cmd_lock(root, positional[0], timeout, positional[2:])
        return usage(f"unknown command {cmd!r}")
    except GraphError as e:
        print(f"reef-graph BROKEN GRAPH: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
