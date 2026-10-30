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
    except (ProcessLookupError, ValueError, TypeError):
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


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


LINT_LINE = {"ruff": 'exclude = ["scripts/reef*"]', "mypy": 'exclude = "scripts/reef"'}
COVERS = re.compile(r"scripts/reef\*|scripts/reef(?![-])|scripts/\*\*|\bscripts/?[\"']")   # a pattern that covers reef-*.py AND reef_common.py


def lint_gaps(root):
    """The project's Python linters that would scan Reef's copied scripts — [(config file, section, the line to add)].
    2026-10-29 (an adoption): ruff flagged 1,725 style errors in scripts/reef-*.py and CI went red; the scripts are rendered
    by reef-init and replaced on every upgrade, so their style is Reef's own. `scripts/reef-*` alone no longer covers them
    (scripts/reef_common.py). Read with a regex, not a TOML parser: the floor is Python 3.9."""
    out = []
    for name in ("pyproject.toml", "ruff.toml", ".ruff.toml"):
        p = os.path.join(root, name)
        try:
            text = read(p)
        except OSError:
            continue
        if name != "pyproject.toml":
            if not COVERS.search(section_text(text, None)):
                out.append((name, "", LINT_LINE["ruff"]))
            continue
        for tool in ("ruff", "mypy"):
            if re.search(rf"^\[tool\.{tool}(\.|\])", text, re.M) and not COVERS.search(section_text(text, tool)):
                out.append((name, f"[tool.{tool}]", LINT_LINE[tool]))
    return out


def section_text(text, tool):
    """The `exclude` values inside the tool's sections (every `[tool.<tool>…]` table), or the whole file for a ruff.toml."""
    if tool is None:
        return "\n".join(l for l in text.splitlines() if re.match(r"^\s*(exclude|extend-exclude)\s*=", l) or l.strip().startswith(('"', "'")))
    out, inside = [], False
    for line in text.splitlines():
        if re.match(r"^\[", line):
            inside = bool(re.match(rf"^\[tool\.{tool}(\.|\])", line))
            continue
        if inside and (re.match(r"^\s*(exclude|extend-exclude)\s*=", line) or line.strip().startswith(('"', "'"))):
            out.append(line)
    return "\n".join(out)


def git(cwd, *args, timeout=None):
    """`git -C cwd …` as run() returns it (no timeout unless given: a merge or a fetch is as long as it is)."""
    return run(["git", "-C", cwd, *args], cwd=None, timeout=timeout)
