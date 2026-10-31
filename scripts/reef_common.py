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
import shlex
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


def merge_by(cfg):
    """merge.by or its v3 default: `loop` when ci.feature_gate is ci and base differs from release (the guard's rule) — the one
    definition the row machine, the runner and the guard's readers share (2026-10-31: three spellings had drifted)."""
    v = str((cfg.get("merge") or {}).get("by", "") or "").strip()
    if v:
        return v
    b = cfg.get("branches") or {}
    ci = str((cfg.get("ci") or {}).get("feature_gate", "ci") or "ci") == "ci"
    return "loop" if ci and str(b.get("base", "main") or "main") != str(b.get("release", "main") or "main") else "human"


def issues_mode(cfg):
    """`queue.home: issues` — the queue's rows and the owner's questions live in GitHub issues."""
    return (cfg.get("queue") or {}).get("home") == "issues"


QUESTION_LINE = re.compile(r"^- row (\d+|-)(?: #(\d+))?: (.*?)(?: — recommended: (.*))?$")
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")   # a terminal reads these; the owner's screen and paste must not (the review)
QUESTION_TITLE = re.compile(r"^question: row (\d+|-): (.*)$", re.S)


def plain(text):
    """Agent-written text as the owner's terminal may show it: control characters and line separators become spaces."""
    return CONTROL.sub(" ", str(text or "")).strip()


def question_line(row, question, recommended="", issue=""):
    """The line `reef-queue.py ask` writes to .reef/questions.md: `- row 7 #90: <question> — recommended: <answer>` — the
    issue's number since 0.7.4 on an issues queue, so every reader can name the command that answers it."""
    return f"- row {row or '-'}" + (f" #{issue}" if issue else "") + f": {plain(question)}" + (f" — recommended: {plain(recommended)}" if plain(recommended) else "")


def question_issues(root):
    """{(row, question[:180]): number} for the open reef-question issues — the title `ask` gives them — or {} when gh
    cannot say. For a line from before 0.7.4, which names no issue."""
    r = run(["gh", "issue", "list", "--label", "reef-question", "--state", "open", "--limit", "200", "--json", "number,title"], root, timeout=15)
    try:
        items = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else []
    except ValueError:
        return {}
    out = {}
    for it in items if isinstance(items, list) else []:
        m = QUESTION_TITLE.match(str(it.get("title", "")))
        if m and str(it.get("number", "")).isdigit():
            out.setdefault((m.group(1), plain(m.group(2))), str(it["number"]))
    return out


def questions(root):
    """[(row, issue, question, recommended)] from .reef/questions.md — the lines reef-queue.py ask writes, control characters
    out; `issue` is the reef-question issue's number ("" on a file queue). A line from before 0.7.4 names no issue: on an
    issues queue the open reef-question issues are asked once and the number filled in by the title `ask` gave it."""
    out = []
    for line in read(os.path.join(root, ".reef", "questions.md"), default="").splitlines():
        m = QUESTION_LINE.match(line.rstrip())
        if m:
            out.append((m.group(1), m.group(2) or "", plain(m.group(3)), plain(m.group(4))))
    if any(not issue for _, issue, _, _ in out) and issues_mode(read_config(root)):
        known = question_issues(root)
        out = [(r, issue or known.get((r, q[:180]), ""), q, rec) for r, issue, q, rec in out]
    return out


def answer_command(root, row, issue, answer):
    """The ONE terminal command that answers a filed question (2026-10-30, the current adoption: the runner named a footnote
    for a question that lived in a reef-question issue, and a footnote closes no issue): on an issues queue
    `reef-queue.py answered <#> '<answer>'`, on a file queue the footnote on its row. `answer` is the owner's text, or the
    recommended answer a reader shows for them to keep or edit. Returns (argv, the line the owner would type), or None
    for an issues queue whose line names no issue and whose issue gh could not find — the caller says where to look."""
    text = plain(answer)
    if issue:
        argv, shown = ["python3", "scripts/reef-queue.py", "answered", str(issue), text], f"python3 scripts/reef-queue.py answered {issue} {shlex.quote(text)}"
    elif issues_mode(read_config(root)):
        return None
    else:
        argv, shown = ["python3", "scripts/reef-queue.py", "footnote", text, "--row", str(row)], f"python3 scripts/reef-queue.py footnote {shlex.quote(text)} --row {row}"
    return argv, shown


def drop_question(root, row=None, issue=None, question=None, when=None):
    """Remove the question lines that match every filter given — `row`, `issue` (as written on the line), `question` (its
    text) and `when(line)` — from .reef/questions.md; the file goes when nothing is left. Returns how many lines left.
    The one body behind `answered`, `reef answer` and the approval's own clearing (the review: three filters, two policies)."""
    p = os.path.join(root, ".reef", "questions.md")
    lines = read(p, default="").splitlines()   # no file, nothing to drop
    if not lines:
        return 0
    def hit(line):
        m = QUESTION_LINE.match(line.rstrip())
        return (m is not None and (row is None or m.group(1) == str(row)) and (issue is None or (m.group(2) or "") == str(issue))
                and (question is None or plain(m.group(3)) == plain(question)) and (when is None or bool(when(line))))
    kept = [l for l in lines if not hit(l)]
    gone = len(lines) - len(kept)
    if gone:
        if any(l.strip() for l in kept):
            with open(p, "w", encoding="utf-8") as f:
                f.write("\n".join(kept) + "\n")
        else:
            os.unlink(p)
    return gone


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


# The shapes the scripts read a command in (lightening step 1, 2026-10-31: each script had its own 2–4 line adapter over run()/git();
# a script keeps its own defaults with functools.partial, its call sites unchanged).
def run_rc(args, cwd, timeout=60, env=None, timeout_rc=124):
    """(returncode, stdout)."""
    r = run(args, cwd, timeout, env, timeout_rc)
    return r.returncode, r.stdout


def run_rc3(args, cwd, timeout=60, env=None, timeout_rc=124):
    """(returncode, stdout, stderr)."""
    r = run(args, cwd, timeout, env, timeout_rc)
    return r.returncode, r.stdout, r.stderr


def run_out(args, cwd, timeout=60):
    """stdout, stripped, when the command succeeded — else ""."""
    r = run(args, cwd, timeout)
    return r.stdout.strip() if r.returncode == 0 else ""


def run_all(args, cwd, timeout=60, strip=False):
    """(returncode, stdout + stderr) — the whole of what the command said, for a log or a summary line."""
    r = run(args, cwd, timeout)
    both = (r.stdout or "") + (r.stderr or "")
    return r.returncode, both.strip() if strip else both


def git_rc(cwd, *args, timeout=None):
    """(returncode, stdout stripped)."""
    r = git(cwd, *args, timeout=timeout)
    return r.returncode, r.stdout.strip()


def git_out(cwd, *args, timeout=None, strip=True):
    """stdout (stripped, unless `strip` is off) when git succeeded — else ""."""
    r = git(cwd, *args, timeout=timeout)
    return (r.stdout.strip() if strip else r.stdout) if r.returncode == 0 else ""


def git_checked(cwd, *args, prefix, check=True, limit=200, where=False, timeout=None):
    """git as run() returns it; with `check`, a failure prints `<prefix>: git <verb> failed[ in <cwd>]: <what git said>` and exits 1."""
    r = git(cwd, *args, timeout=timeout)
    if check and r.returncode != 0:
        print(f"{prefix}: git {' '.join(str(a) for a in args[:2])} failed{' in ' + str(cwd) if where else ''}: {(r.stderr or r.stdout).strip()[:limit]}", file=sys.stderr)
        sys.exit(1)
    return r


def git_text(cwd, *args, prefix, check=True, limit=200, timeout=None):
    """git's stdout; with `check`, a failure is reported and exits 1 (git_checked)."""
    return git_checked(cwd, *args, prefix=prefix, check=check, limit=limit, timeout=timeout).stdout


def die(msg, code=2, *, prefix):
    """`<prefix>: <msg>` on stderr and exit — the one way a script refuses (lightening step 1: thirteen scripts each had their own);
    the prefix is the script's own word, always given (never read from the command line)."""
    print(f"{prefix}: {msg}", file=sys.stderr)
    sys.exit(code)


def load_sibling(name, modname=None):
    """A sibling script (reef-plan-check.py, reef-graph.py, reef-row.py) as a module, from this module's own directory — one loader
    shape (lightening step 2: four scripts carried it). No bytecode is written beside a project's scripts."""
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader(modname or re.sub(r"\W", "_", name), os.path.join(os.path.dirname(os.path.abspath(__file__)), name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    loader.exec_module(mod)
    return mod


def git_root(repo):
    """The repository's top level from inside it (`git rev-parse --show-toplevel`), else the directory itself."""
    r = git(repo, "rev-parse", "--show-toplevel")
    top = r.stdout.strip() if r.returncode == 0 else ""
    return top or os.path.abspath(repo)


def reef_dir(root):
    """0.7.3 (first adoption, 2026-10-25): Reef's proposals live under the git dir — every tool, test and linter skips .git; under
    .reef/proposed/ a project test that walks the disk counted .dependency-cruiser.cjs and a .claude/ folder as its own.
    The common dir, so a linked worktree sees the same proposals. Outside a git repository: .reef/ as before."""
    r = git(root, "rev-parse", "--git-common-dir")
    g = r.stdout.strip()
    if r.returncode != 0 or not g:
        return os.path.join(root, ".reef")
    return os.path.join(g if os.path.isabs(g) else os.path.join(root, g), "reef")


def section(text, heading):
    """Body of '## <heading>' up to the next '## ' or EOF; None if absent."""
    m = re.search(rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    return m.group(1) if m else None


SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+){1,4}$")
GENERIC_SLUGS = {"misc", "fixes", "feature", "update", "stuff", "changes", "work", "tasks", "new", "todo", "wip"}


def slug_error(slug):
    """2 to 5 kebab-case words, descriptive: no bare numbers, no generic word."""
    if not SLUG_RE.match(slug):
        return f"feature slug {slug!r} is not 2-5 kebab-case words (e.g. csv-export-for-orders)"
    words = slug.split("-")
    if all(w.isdigit() for w in words) or any(w in GENERIC_SLUGS for w in words):
        return f"feature slug {slug!r} is a number or a generic word — name the feature"
    return None


HOME_KEYS = ("adr", "queue", "runlog", "glossary", "tasks", "features", "day_zero")


def config_homes(cfg):
    """The places .reef/config.json `paths.*` names (0.7.2, first adoption 2026-10-24, item 17): init chose them, so a check accepts
    them whatever the version — `docs/adr` was flagged on a project whose config said `paths.adr: docs/adr`."""
    return [str(v).strip().strip("/") for k, v in (cfg.get("paths") or {}).items() if v and k in HOME_KEYS]


def served_dirs(root):
    """Directories a docs build serves — the docs are the product's, not Reef's."""
    out = set()
    if os.path.isfile(os.path.join(root, "mkdocs.yml")):
        with open(os.path.join(root, "mkdocs.yml"), encoding="utf-8", errors="replace") as f:
            m = re.search(r"^docs_dir:\s*(\S+)", f.read(), re.M)
        out.add((m.group(1) if m else "docs").strip("/"))
    for cand in ("docusaurus.config.js", "docusaurus.config.ts", "docusaurus.config.mjs", "docs/package.json"):
        if os.path.isfile(os.path.join(root, cand)):
            out.add("docs")
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in (".git", "node_modules", ".reef", ".venv")]
        if "conf.py" in fn and any(x.endswith((".rst", ".md")) for x in fn):
            out.add(os.path.relpath(dp, root).strip("./"))
    return {d for d in out if d}   # a Sphinx conf.py at the root names "" — not a directory


def plugin_root(arg=None):
    """The plugin clone: the argument, $CLAUDE_PLUGIN_ROOT, else this module's own repository — the first that holds a plugin manifest."""
    for cand in (arg, os.environ.get("CLAUDE_PLUGIN_ROOT"), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))):
        if cand and os.path.isfile(os.path.join(cand, ".claude-plugin", "plugin.json")):
            return os.path.abspath(cand)
    return None


def plugin_version(plugin, default="?"):
    """The plugin manifest's version, or `default` when the manifest cannot be read."""
    try:
        with open(os.path.join(plugin, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            return str(json.load(f).get("version") or default)
    except Exception:
        return default
