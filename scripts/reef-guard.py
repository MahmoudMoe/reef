#!/usr/bin/env python3
"""Reef PreToolUse guard — the mechanical layer behind the plugin's "hard" rules.

Reads the hook JSON on stdin. Two duties:

1. Bash commands: deny gate bypasses. The command is TOKENIZED (shlex, shell
   operators as separators, newlines treated like `;`) and split into simple
   command segments, so the guard catches `git commit -n`, bundled short flags
   (`-anm`), `git -c core.hookspath=...` in any case, flag insertion
   (`git --no-pager commit --no-verify`), `--config-env` in both spellings, env
   smuggling (`GIT_CONFIG_KEY_0=core.hooksPath`), a second command after a
   newline, `sh -c "git commit -n"` payloads (recursed into), and `rm/mv/chmod`
   sabotage of the hook files, `git stash` (ONE stash stack serves every worktree:
   with parallel agents one agent's pop applied another's — commit to the task
   branch or open another worktree), and a GATE PIPED INTO ANOTHER COMMAND
   without pipefail (`npm test | tail` reports tail's exit code; a red gate went
   unnoticed until CI) — while ALLOWING reef-init's own install
   (`git config core.hooksPath .githooks`, `chmod +x .githooks/*`), read-only
   queries, `git merge -n` (that is --no-stat), and commit messages that merely
   mention a flag. A blocklist over a shell surface can never be complete
   (command substitution and wrapper scripts remain open): this hook is a
   TRIPWIRE; CI is the wall (see README).

2. Task/Agent dispatches of the reef implementer: refuse when the task file is
   blocked or at the retry cap, refuse when the plan stamp is stale, refuse when
   the task is NOT IN THE READY SET of the task graph (an undone `blocked-by`, a
   declared resource with no free slot, the parallel cap — computed by
   scripts/reef-graph.py loaded from THIS plugin's directory, never from a copy
   the project could delete), and — only after every check passed — advance a
   `dispatches:` odometer and mark the task `in-progress` IN THIS HOOK, under the
   graph-wide lock plus the same per-file lock reef-attempt uses. The counter moves as a side effect of
   the dispatch action itself, so a model that "forgets" scripts/reef-attempt
   still cannot loop forever (the odometer trips at 2x the cap). A denied
   dispatch never bumps the odometer. Config and stamp are resolved against the
   TASK FILE's own checkout (worktree), never the dispatching session's folder,
   and the stamp is verified for the task's own `feature:` only. A rollup
   (R<NN>) is refused when another rollup of the same feature exists: one rollup
   per feature carries acceptance, diff and CI rounds under ONE cap.

Exit 0 = allow. Exit 2 = deny (reason on stderr). Anything unparseable that
smells like a bypass is denied; anything unparseable and innocent is allowed.
"""
import fcntl
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile

DEFAULT_CAP = 3
OPS = {";", "&", "|", "&&", "||", ";;", ";&", "|&", "(", ")"}
MAX_DEPTH = 25   # bound sh -c / eval recursion so a nested payload cannot hang the hook
# git global options that consume a separate value before the subcommand
GIT_GLOBAL_VALUE_OPTS = {"-C", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix", "--config-env"}
# git-commit options that consume a separate value (their VALUES must not be inspected)
COMMIT_VALUE_OPTS = {"-m", "--message", "-F", "--file", "-t", "--template", "-c", "-C",
                     "--reedit-message", "--reuse-message", "--author", "--date",
                     "--fixup", "--squash", "--trailer", "--pathspec-from-file", "-S", "--gpg-sign"}
HOOK_PATHS = re.compile(r"(^|/)\.githooks(/|$)|(^|/)\.git/hooks(/|$)")
ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HOOKSPATH = re.compile(r"hookspath", re.I)


def deny(reason):
    print(f"reef-guard DENY: {reason}", file=sys.stderr)
    sys.exit(2)


def tokenize(cmd):
    """Tokenize a whole command in ONE pass; shell operators (incl. subshell parens) become
    their own tokens; None if unparseable. Newlines are whitespace here (shlex default), so a
    newline INSIDE a quote stays a literal message character while a newline BETWEEN commands
    just separates tokens — and default commenters='#' ends a comment exactly at its own
    line's newline. Command boundaries do not matter because check_segment scans every token
    position for git/rm/chmod, so two newline-separated commands are still both inspected."""
    lex = shlex.shlex(cmd, posix=True, punctuation_chars="();|&")
    lex.whitespace_split = True
    try:
        return list(lex)
    except ValueError:
        return None


def check_bash(cmd, depth=0):
    try:
        _check_bash(cmd, depth)
    except SystemExit:
        raise
    except Exception:
        # a guard crash must not open the gate: deny when the raw text smells
        if re.search(r"no-verify|hookspath", cmd, re.I):
            deny("guard internal error on a command that mentions a gate bypass — failing closed")


def _check_bash(cmd, depth=0):
    if depth > MAX_DEPTH:
        deny("shell nesting too deep to analyze — refusing a command that hides commands this many layers down")
    cmd = re.sub(r"\\\r?\n", " ", cmd)     # backslash line continuations JOIN a command
    cmd = re.sub(r"(\d*>&\d+|&>>?)", " ", cmd)  # fd redirections are not operators (2>&1, &>)
    toks = tokenize(cmd)                    # one pass: quotes span newlines, comments end at theirs
    if toks is None:
        # Unparseable (unbalanced quotes): flags can no longer be told apart from
        # values, so a bypass-smelling command is denied outright.
        if re.search(r"no-verify|hookspath", cmd, re.I):
            deny("unparseable command that mentions a gate bypass")
        return
    seg = []
    pipefail = "pipefail" in cmd
    for t in toks + [";"]:
        if t in OPS:
            if seg:
                check_segment(seg, depth, next_op=t, pipefail=pipefail)
            seg = []
        else:
            seg.append(t)


SHELLS = ("sh", "bash", "dash", "zsh", "ksh")
DESTRUCTIVE = ("rm", "mv", "unlink", "truncate", "shred")
# gates whose exit code IS the verdict: piping them hides it (the pipe reports the
# last command's status). Names, not paths — `sh scripts/reef-gate.sh | tail` too.
GATE_WORDS = {"reef-gate.sh", "reef-ci-local.sh", "ci:local", "pytest", "vitest", "jest",
              "cargo", "go"}
STASH_READ_ONLY = {"list", "show"}
MODE_RE = re.compile(r"^([0-7]{3,4}|[ugoa]*[-+=][rwxXstugo]+(,[ugoa]*[-+=][rwxXstugo]+)*)$")
PURE_ADD = re.compile(r"^[ugoa]*\+[rwxXst]+$")


def is_gate(seg):
    """A segment that runs a test gate: `npm test`, `npm run ci:local`, `pytest -q`,
    `cargo test`, `go test ./...`, `sh scripts/reef-gate.sh`."""
    names = [os.path.basename(t) for t in seg]
    if "npm" in names and ("test" in seg or "ci:local" in seg):
        return True
    for i, b in enumerate(names):
        if b in ("cargo", "go"):
            return "test" in seg[i + 1:i + 2]
        if b in GATE_WORDS:
            return True
    return False


def check_segment(seg, depth=0, next_op=";", pipefail=False):
    """Position-independent: `env X=y git ...`, `nohup git ...`, `nice -n5 git ...`,
    `xargs git ...`, `(git ...)` — a prefix word must never hide the real command."""
    for t in seg:
        if ENV_ASSIGN.match(t) and HOOKSPATH.search(t):
            deny(f"environment assignment smuggles hooksPath: {t!r}")
    if next_op in ("|", "|&") and not pipefail and is_gate(seg):
        deny(f"gate {' '.join(seg[:3])!r} piped into another command — the pipe reports the LAST "
             "command's exit code, so a red gate passes unnoticed; use `set -o pipefail`, or redirect "
             "to a file and read the exit code")
    for i, t in enumerate(seg):
        b = os.path.basename(t)
        rest = seg[i + 1:]
        if b == "git":
            check_git(rest)
        elif b in DESTRUCTIVE:
            for a in rest:
                if HOOK_PATHS.search(a):
                    deny(f"{b} on {a!r} disables the commit gate")
        elif b == "chmod":
            check_chmod(rest)
        elif b in SHELLS:
            for k, a in enumerate(rest):
                # -c may be bundled (-lc, -ec, -cx); the payload is the next argument
                if re.match(r"^-[a-zA-Z]*c[a-zA-Z]*$", a) and k + 1 < len(rest):
                    check_bash(rest[k + 1], depth + 1)   # `sh -c "git commit -n"` is not a tunnel
        elif b == "eval":
            check_bash(" ".join(rest), depth + 1)


def check_chmod(args):
    if not any(HOOK_PATHS.search(a) for a in args):
        return
    # reef-init's install is a pure permission ADDITION (+x). A MODE token that can strip or
    # set exec (octal, '=', or any '-x') on the hook files kills the gate silently. MODE_RE
    # tells a mode from a flag (-R/-v -> not a mode) and from a target filename, so a bare
    # '-x' (remove execute) is correctly caught while '-R' is passed through.
    for a in args:
        if MODE_RE.match(a) and not PURE_ADD.match(a):
            deny("chmod on the hook files is allowed only for pure permission additions like +x")


def check_git(args):
    sub = None
    j = 0
    while j < len(args):
        a = args[j]
        if sub is None:
            if a == "-c" and j + 1 < len(args):
                if re.match(r"^core\.hookspath(=|$)", args[j + 1], re.I):
                    deny(f"git -c {args[j + 1]!r} redirects hooks away from the gate")
                j += 2
                continue
            if re.match(r"^-ccore\.hookspath", a, re.I):
                deny(f"git {a!r} redirects hooks away from the gate")
            if a in GIT_GLOBAL_VALUE_OPTS:
                if a == "--config-env" and j + 1 < len(args) and HOOKSPATH.search(args[j + 1]):
                    deny(f"git --config-env {args[j + 1]!r} redirects hooks away from the gate")
                j += 2
                continue
            if a.startswith("--") and "=" in a and HOOKSPATH.search(a):
                deny(f"git {a!r} redirects hooks away from the gate")
            if a.startswith("-"):
                j += 1
                continue
            sub = a
            j += 1
            continue
        # ---- inside subcommand arguments ----
        if a == "--":
            return   # everything after -- is pathspecs, not flags
        if sub == "commit":
            if a == "--no-verify" or re.match(r"^-[a-zA-Z]*n[a-zA-Z]*$", a):
                # -n is the short form of --no-verify for commit; bundled clusters count
                deny(f"git commit {a!r} skips the pre-commit gate (fix the failure instead)")
            if a in COMMIT_VALUE_OPTS:
                j += 2   # never inspect option VALUES (a message may mention --no-verify)
                continue
        elif sub == "merge" and a == "--no-verify":
            # note: merge -n is --no-stat, NOT --no-verify — only the long form is a bypass
            deny("git merge --no-verify skips the pre-merge-commit gate")
        elif sub == "stash":
            action = next((t for t in args[j:] if not t.startswith("-")), "push")
            if action not in STASH_READ_ONLY:
                deny(f"git stash {action}: ONE stash stack serves every worktree, so a parallel agent's "
                     "pop applies another's work — commit to the task branch (the gate must pass) or "
                     "open another worktree")
            return
        elif sub == "config":
            check_git_config(args[j:])
            return
        j += 1
    if sub == "stash":
        deny("git stash (bare = push): ONE stash stack serves every worktree — commit to the task "
             "branch (the gate must pass) or open another worktree")


def check_git_config(seg):
    """`git config ...` — deny writes that move core.hooksPath anywhere but .githooks."""
    touches = [t for t in seg if re.search(r"(^|\.)hookspath$", t, re.I)]
    if not touches:
        return
    read_only = any(t in ("--get", "--get-all", "--get-regexp", "--list", "-l", "get", "list") for t in seg)
    unset = any(t in ("--unset", "--unset-all", "unset") for t in seg)
    if unset:
        deny("git config --unset core.hooksPath removes the commit gate")
    if read_only:
        return
    key = touches[0]
    idx = seg.index(key)
    value = next((t for t in seg[idx + 1:] if not t.startswith("-")), None)
    if value == ".githooks":
        return   # reef-init's own install — explicitly allowed
    deny(f"git config core.hooksPath {value!r} points hooks away from the gate (.githooks is the only allowed value)")


# ---------------- Task dispatch guard (the cap, enforced at the action) ----------------

FENCE = re.compile(r"\A---\r?\n(.*?\r?\n)---\r?\n", re.S)


def lock_path_for(path):
    """Same lock reef-attempt takes. Lives in tmp (never committed) and is never
    unlinked — unlink-in-finally is the classic broken lock (a third process can
    acquire a fresh inode while another still holds the old one)."""
    digest = hashlib.sha1(os.path.abspath(path).encode()).hexdigest()
    return os.path.join(tempfile.gettempdir(), f"reef-lock-{digest}")


def read_frontmatter(path):
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    m = FENCE.match(text)
    if not m:
        return None, text
    fm = {}
    for line in m.group(1).splitlines():
        # column 0 only, FIRST occurrence wins — mirrors reef-attempt's `^key:` (re.M)
        # reader exactly, so an indented or duplicated key cannot read differently across
        # the two enforcement layers
        if line[:1] in (" ", "\t", "#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            fm.setdefault(key.strip(), val.strip().strip('"'))
    return fm, text


def bump_dispatches(path, text, current, mark_in_progress=False):
    """Increment dispatches: (and set status: in-progress — the task now holds its
    resources and a parallel slot) inside the frontmatter only; unique temp + atomic replace."""
    m = FENCE.match(text)
    fm_body = m.group(1)
    if re.search(r"^dispatches:", fm_body, re.M):
        new_fm = re.sub(r"^dispatches:.*$", f"dispatches: {current + 1}", fm_body, count=1, flags=re.M)
    else:
        new_fm = fm_body + f"dispatches: {current + 1}\n"
    if mark_in_progress:
        if re.search(r"^status:", new_fm, re.M):
            new_fm = re.sub(r"^status:.*$", "status: in-progress", new_fm, count=1, flags=re.M)
        else:
            new_fm = new_fm + "status: in-progress\n"
    new_text = text[:m.start(1)] + new_fm + text[m.end(1):]
    fd, tmp = tempfile.mkstemp(prefix=".reef-guard-", dir=os.path.dirname(path) or ".")
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


def load_graph_module():
    """scripts/reef-graph.py from the PLUGIN's own directory. The project's copy is
    never consulted: `rm scripts/reef-graph.py` in a project must not open the gate."""
    import importlib.util
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reef-graph.py")
    spec = importlib.util.spec_from_file_location("reef_graph", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_cap(root):
    try:
        with open(os.path.join(root, ".reef", "config.json"), encoding="utf-8") as f:
            cap = json.load(f).get("caps", {}).get("attempts", DEFAULT_CAP)
        return int(cap)
    except Exception:
        return DEFAULT_CAP


def task_root(path, fallback):
    """The checkout the TASK FILE lives in — walk up from it to the first directory holding
    .reef/ or .git. `.git` is a FILE in a linked worktree, so existence (not isdir) is the
    test. Resolving against the dispatching session's folder checked the wrong worktree in
    both directions: it denied a reviewed worktree and passed an edited one."""
    probe = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.isdir(os.path.join(probe, ".reef")) or os.path.exists(os.path.join(probe, ".git")):
            return probe
        parent = os.path.dirname(probe)
        if parent == probe:
            return fallback   # no marker at all: the old behaviour (session folder)
        probe = parent


def check_stamp(root, feature):
    """Mechanical plan-freshness: an edited plan never dispatches unnoticed.
    Read-only; runs BEFORE the odometer bump so a stale-plan denial costs nothing.
    Scoped to the task's own feature, so another feature's tasks arriving with a merge
    of the integration branch do not force a re-review of this one."""
    script = os.path.join(root, "scripts", "reef-plan-check.py")
    if not os.path.isfile(script):
        return  # not a reef-init'd layout; nothing to verify against
    cmd = [sys.executable, script, root, "--verify-stamp"]
    if feature:
        cmd += ["--feature", feature]
    try:
        r = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=30)
    except Exception:
        return
    if r.returncode != 0:
        out = (r.stdout or r.stderr).strip()
        hint = ""
        if "unknown option" in out:
            hint = " — the project's scripts/reef-plan-check.py predates this plugin; re-copy it (reef-init step 6)"
        deny("plan stamp is stale or missing — the plan changed since its last review; "
             "run the reef-plan-review skill in the task's own worktree before dispatching ("
             + out + ")" + hint)


ROLLUP_NAME = re.compile(r"^R\d+-.*\.md$")


def check_single_rollup(path, fm):
    """One rollup file per feature: a second one would start a fresh attempts: counter
    and launder the shared cap. Mirrors scripts/reef-attempt."""
    if not ROLLUP_NAME.match(os.path.basename(path)):
        return
    feature = fm.get("feature", "")
    if not feature:
        deny(f"{path}: a rollup must name its feature: (one rollup per feature carries the cap)")
    here = os.path.dirname(os.path.abspath(path))
    tasks_dir = os.path.dirname(here) if os.path.basename(here) == "done" else here
    for d in (tasks_dir, os.path.join(tasks_dir, "done")):
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            other = os.path.join(d, f)
            if not ROLLUP_NAME.match(f) or os.path.abspath(other) == os.path.abspath(path):
                continue
            try:
                ofm, _ = read_frontmatter(other)
            except Exception:
                continue
            if ofm and ofm.get("feature", "") == feature:
                deny(f"feature {feature!r} already has rollup {os.path.relpath(other, tasks_dir)} — "
                     "reuse it (move it back from done/ if needed); a second rollup resets the cap")


# subagent name -> the .reef/config.json roles.* key whose model it must run on. The owner's
# routing (2026-10-04): fable plans, opus writes/attacks/verifies/reviews, sonnet does light
# mechanical work. Each project overrides per role; an unset role is not checked.
ROLE_OF = {"implementer": "author", "verifier": "verifier", "plan-reviewer": "plan_reviewer",
           "loophole-hunter": "adversary", "mechanic": "mechanic"}


def check_role_model(sub, tool_input, root):
    """A dispatch runs on the CONFIGURED model for its role, not on the agent file's default
    and not on whatever the orchestrator remembered: when roles.<role> is set, the Agent
    call must carry exactly that `model` parameter."""
    role = next((r for name, r in ROLE_OF.items() if name in sub), None)
    if role is None:
        return
    try:
        with open(os.path.join(root, ".reef", "config.json"), encoding="utf-8") as f:
            roles = json.load(f).get("roles", {})
    except Exception:
        return   # no readable config: nothing is configured, nothing to enforce
    if not isinstance(roles, dict) or not roles.get(role):
        return
    want = str(roles[role]).strip()
    got = str(tool_input.get("model") or "").strip()
    if got != want:
        deny(f"{sub} must run on roles.{role} = {want!r} (.reef/config.json); the Agent call "
             f"passed model={got or 'none'!r} — pass model={want!r}")


def check_dispatch(tool_input, payload):
    try:
        _check_dispatch(tool_input, payload)
    except SystemExit:
        raise
    except Exception as e:
        # ANY internal error (unwritable lock, full disk, foreign-owned tmp file)
        # must fail CLOSED — exit 1 would be a non-blocking hook error, i.e. an allow
        deny(f"guard internal error — failing closed: {e}")


def _check_dispatch(tool_input, payload):
    sub = str(tool_input.get("subagent_type") or "")
    cwd = payload.get("cwd") or os.getcwd()
    check_role_model(sub, tool_input, cwd)
    if "implementer" not in sub:
        return
    prompt = str(tool_input.get("prompt") or "")
    m = re.search(r"^REEF-TASK:[ \t]*(.+?)[ \t\r]*$", prompt, re.M)
    if not m:
        deny("implementer dispatch without a 'REEF-TASK: <task-file>' line — run scripts/reef-attempt "
             "and start the dispatch prompt with the line it prints")
    path = m.group(1)
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    if not os.path.isfile(path):
        deny(f"REEF-TASK file not found: {path}")
    root = task_root(path, cwd)
    if os.path.abspath(root) != os.path.abspath(cwd):
        check_role_model(sub, tool_input, root)
    try:
        pre_fm, _ = read_frontmatter(path)
    except Exception:
        pre_fm = None   # re-read under the lock below, which fails closed
    check_stamp(root, (pre_fm or {}).get("feature", ""))
    graph = load_graph_module()
    tasks_dir = graph.tasks_dir_for(root, graph.read_config(root), path)
    # ONE lock over the whole task set: the ready decision reads every task file, so
    # two dispatches racing for the last parallel slot or the last resource slot must
    # serialise here — the per-file lock below protects only this file's counters.
    with open(graph.graph_lock_path(tasks_dir), "a") as glock, open(lock_path_for(path), "a") as lock:
        fcntl.flock(glock, fcntl.LOCK_EX)
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            fm, text = read_frontmatter(path)
        except Exception as e:   # OSError, UnicodeDecodeError, anything: fail CLOSED
            deny(f"cannot read {path}: {e}")
        if fm is None:
            deny(f"{path} has no frontmatter fence — not a reef task file")
        check_single_rollup(path, fm)
        cap = read_cap(root)
        try:
            attempts = int(fm.get("attempts", "0") or 0)
            dispatches = int(fm.get("dispatches", "0") or 0)
        except ValueError:
            deny(f"{path}: attempts/dispatches are not integers — fix the frontmatter")
        if attempts < 0 or dispatches < 0:
            deny(f"{path}: negative attempts/dispatches would disable the caps — fix the frontmatter")
        if fm.get("status") == "blocked":
            deny(f"{path} is blocked — a HUMAN must unblock it (attempts: 0, status: pending, last_failure_sig: \"\")")
        if attempts >= cap:
            deny(f"{path} is at the retry cap ({attempts}/{cap}) — USER ACTION REQUIRED")
        if dispatches >= 2 * cap:
            deny(f"{path} was dispatched {dispatches}x against cap {cap} without enough recorded failures — "
                 "runaway-loop backstop; record failures via scripts/reef-attempt or stop")
        # the graph: dependencies done, resources free, parallel cap — a broken graph
        # (cycle, dangling id, duplicate id) has no ready set and is a denial too
        try:
            reason, _, _ = graph.check_task(path)
        except graph.GraphError as e:
            deny(f"task graph cannot be scheduled — {e}")
        if reason is not None:
            deny(f"{path} is not in the ready set — {reason}")
        # every check passed: the odometer moves and the task becomes in-progress as
        # part of the dispatch itself (it now holds its resources and a parallel slot)
        bump_dispatches(path, text, dispatches, mark_in_progress=(fm.get("status", "pending") != "in-progress"))


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    if tool == "Bash":
        check_bash(str(tool_input.get("command") or ""))
    elif tool in ("Task", "Agent"):
        check_dispatch(tool_input, payload)
    sys.exit(0)


if __name__ == "__main__":
    main()
