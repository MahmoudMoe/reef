# CLASS: code
"""reef_common — the helpers every Reef script used to carry its own copy of (docs/design/consolidation.md, step 1).

One definition each, the strictest signature that was in use: a script does
`sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` then `from reef_common import …`
(the insert is for a script loaded from another folder, or run under `python3 -I`; a direct run has it already).
A script whose callers expect another shape keeps a one-line adapter over these, never a second body.
"""
import json
import os
import re
import subprocess
import sys
import time

_ROOT = object()


def read(path, errors=None, newline=None, default=None):
    """The file's text. `errors="replace"` for a file that may carry bad bytes; `newline=""` keeps CRLF as written;
    `default` (not None) is returned instead of raising when the file cannot be read."""
    try:
        with open(path, encoding="utf-8", errors=errors, newline=newline) as f:
            return f.read()
    except OSError:
        if default is None:
            raise
        return default


def read_replace(path):
    return read(path, errors="replace")


def read_crlf(path):
    return read(path, newline="")


def read_or_empty(path):
    return read(path, errors="replace", default="")


def read_config(root):
    """`.reef/config.json` as a dict: {} when absent, unparseable or not an object (the guard's rule)."""
    try:
        with open(os.path.join(root, ".reef", "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}



def repo_root(start):
    """Walk up from a task file (or directory) to the first .reef/ or .git marker — never the caller's cwd.
    Without a marker: the directory itself, or the file's directory."""
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


def main_checkout(root, timeout=10, default=_ROOT):
    """The main checkout: the first entry of `git worktree list --porcelain`, or `root` itself (or `default`) when git
    cannot say. Machine state (approvals, records, the queue, the slot locks) lives there, never in a task worktree —
    and task worktrees live under IT, never nested in the feature worktree the task file was read from (first contact,
    2026-10-16: `.reef/worktrees/<feature>/.reef/worktrees/101`, and the feature worktree's lint walked into the nested
    build output)."""
    try:
        r = subprocess.run(["git", "-C", root, "worktree", "list", "--porcelain"], capture_output=True, text=True, timeout=timeout)
        for line in r.stdout.splitlines():
            if line.startswith("worktree "):
                return line[len("worktree "):].strip()
    except Exception:
        pass
    return root if default is _ROOT else default


def process_alive(pid):
    """True when the pid names a live process (another user's counts as alive); False for a dead or malformed pid."""
    try:
        os.kill(int(pid), 0)
    except (ProcessLookupError, ValueError, TypeError, OverflowError):   # OverflowError: a pid no process can have (the review)
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


HOLD_FILE = os.path.join(".reef", "run", "orchestrator.json")
HOLD_MINUTES = 30   # one orchestrator at a time (0.7.1): a holder idle this long is stale


def read_hold(root):
    """The loop's hold — who runs this project's loop (0.7.1, one orchestrator at a time): `{"session", "at", "pid",
    "age_s", "alive"}`, or None when nobody holds it (no file, or not a JSON object). `session` is None when the record
    names none; a `pid` that is not a number is 0 — a hold from before 0.7.2, which names no process; an `at` that is not
    a number is 0, long stale. The guard, the runner, the doctor and the loop read the hold here and nowhere else."""
    try:
        held = json.loads(read(os.path.join(root, HOLD_FILE)))
    except (OSError, ValueError):
        return None
    if not isinstance(held, dict):
        return None
    try:
        pid = int(held.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    try:
        at = float(held.get("at") or 0)
    except (TypeError, ValueError):
        at = 0.0
    session = str(held["session"]) if held.get("session") else None
    return {"session": session, "at": at, "pid": pid, "age_s": time.time() - at, "alive": bool(pid) and process_alive(pid)}


def write_hold(root, session, pid):
    """Record the hold for `session`, owned by `pid`, now — atomically (a tmp beside it, then os.replace). The guard writes it;
    the record's three fields are named here and read by read_hold, nowhere else."""
    p = os.path.join(root, HOLD_FILE)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = f"{p}.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"session": session, "at": time.time(), "pid": pid}, f)
    os.replace(tmp, p)


def drop_hold(root, session=None):
    """Remove the hold — anyone's, or only `session`'s when given (the runner drops its own session's, never another's).
    Returns the dropped holder's session ("?" when the record named none), or None when nothing was dropped."""
    h = read_hold(root)
    if h is None or (session is not None and h["session"] != session):
        return None
    try:
        os.unlink(os.path.join(root, HOLD_FILE))
    except OSError:
        return None
    return h["session"] or "?"


def table_cells(line):
    """A markdown table row's cells, stripped: `| a | b |` → ["a", "b"] — the one body behind every table a script
    reads (the queue, the journal, a task's Proof, the threat model, the cost ledger)."""
    return [c.strip() for c in line.strip().strip("|").split("|")]


def run(args, cwd, timeout=60, env=None, timeout_rc=124):
    """A command's CompletedProcess (returncode, stdout, stderr), text, captured. A timeout is `timeout_rc` (124, the
    shell's; a caller whose readers know 1 passes 1) with the reason in stderr; a command that cannot start is 1 —
    callers read the code, never catch."""
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, timeout_rc, "", f"timed out after {timeout} s")
    except OSError as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


# a pattern that covers reef-*.py AND reef_common.py: `scripts/reef*`, `scripts/reef` as a regex stem, or the whole folder
COVERS = re.compile(r"scripts/reef(?=[*.\"'|)\]\s]|$)|(?<![\w/.])scripts/?(\*\*)?(?=[\"'|)\]\s]|$)", re.M)


def lint_state(root):
    """The project's Python linters and Reef's copied scripts: (configured, gaps). `configured` names every linter config found
    (`pyproject.toml [tool.ruff]`, `ruff.toml`…); `gaps` is [(where, the line to add)] for each whose exclude does not cover
    `scripts/reef*`. 2026-10-29 (an adoption): ruff flagged 1,725 style errors in scripts/reef-*.py and CI went red; the scripts
    are rendered by reef-init and replaced on every upgrade, so their style is Reef's own. `scripts/reef-*` alone no longer
    covers them (scripts/reef_common.py). Read with a regex, not a TOML parser (the floor is Python 3.9): only the values of
    `exclude` / `extend-exclude` keys count, continuation lines of an array included (the reviews: a quote-led `include` or
    `src` line counted before). The advice extends a key the file has, never duplicates it (a TOML error), and for ruff is
    `extend-exclude`, since `exclude` would replace ruff's own defaults."""
    configured, gaps = [], []
    for name in ("pyproject.toml", "ruff.toml", ".ruff.toml"):
        try:
            text = read(os.path.join(root, name), errors="replace")
        except OSError:
            continue
        tools = ("ruff", "mypy") if name == "pyproject.toml" else ("ruff",)
        for tool in tools:
            keys = exclude_keys(text, tool if name == "pyproject.toml" else None)
            if keys is None:
                continue
            where = f"{name} [tool.{tool}]" if name == "pyproject.toml" else name
            configured.append(where)
            if COVERS.search("\n".join(keys.values())):
                continue
            if tool == "ruff":
                line = ('add  "scripts/reef*" to the extend-exclude list it has' if "extend-exclude" in keys
                        else 'add  "scripts/reef*" to the exclude list it has' if "exclude" in keys
                        else 'add  extend-exclude = ["scripts/reef*"]')
            else:
                line = 'add  scripts/reef to the exclude regex it has' if "exclude" in keys else 'add  exclude = "scripts/reef"'
            gaps.append((where, line))
    return configured, gaps


def lint_gaps(root):
    return lint_state(root)[1]


def exclude_keys(text, tool):
    """{key: value text} of `exclude` / `extend-exclude` inside the tool's tables (`[tool.<tool>…]`), or the whole file when
    tool is None (a ruff.toml, where `[lint]` is a table of ruff's own); None when no table of the tool exists."""
    out, inside, found, key, depth = {}, tool is None, tool is None, None, 0
    for line in text.splitlines():
        if key is not None:                      # inside an array value: collect until its closing bracket
            out[key] += "\n" + line
            depth += line.count("[") - line.count("]")
            if depth <= 0:
                key = None
            continue
        if re.match(r"^\s*\[", line):
            inside = tool is None or bool(re.match(rf"^\s*\[tool\.{tool}(\.|\])", line))
            found = found or inside
            continue
        m = re.match(r"^\s*(exclude|extend-exclude)\s*=\s*(.*)$", line) if inside else None
        if m:
            k, v = m.group(1), m.group(2)
            out[k] = v
            depth = v.count("[") - v.count("]")
            if depth > 0:
                key = k
    return out if found else None


APPROVE_Q = re.compile(r"Approve (?:plan [A-Za-z0-9._-]+|night \d{4}-\d\d-\d\d|proxy by day) at [0-9a-f]{16}\?")   # the hook's questions


def approval_questions(text):
    """The approval questions a text names, in order, once each — the only strings reef-approval.py --owner accepts."""
    return list(dict.fromkeys(APPROVE_Q.findall(text or "")))


def row_approval_question(root, row, row_script):
    """The approval question the row machine names for a row (reef-row.py state --json, its `detail`), or None. The
    question is accepted only when it matches APPROVE_Q whole — a slug is an agent-named folder (the reviews of #221)."""
    if not row_script or not str(row).isdigit():
        return None
    r = run([sys.executable, row_script, "state", str(row), "--json", "--repo", root], root, timeout=60)
    try:
        detail = str(json.loads(r.stdout).get("detail") or "") if r.returncode == 0 else ""
    except ValueError:
        detail = ""
    qs = approval_questions(detail)
    return qs[0] if qs else None


def git(cwd, *args, timeout=None):
    """`git -C cwd …` as run() returns it (no timeout unless given: a merge or a fetch is as long as it is)."""
    return run(["git", "-C", cwd, *args], cwd=None, timeout=timeout)
