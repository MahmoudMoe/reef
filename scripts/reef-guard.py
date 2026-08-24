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
   sabotage of the hook files — while ALLOWING reef-init's own install
   (`git config core.hooksPath .githooks`, `chmod +x .githooks/*`), read-only
   queries, `git merge -n` (that is --no-stat), and commit messages that merely
   mention a flag. A blocklist over a shell surface can never be complete
   (command substitution and wrapper scripts remain open): this hook is a
   TRIPWIRE; CI is the wall (see README).

2. Task/Agent dispatches of the reef implementer: refuse when the task file is
   blocked or at the retry cap, refuse when the plan stamp is stale, and — only
   after every check passed — advance a `dispatches:` odometer IN THIS HOOK,
   under the same lock reef-attempt uses. The counter moves as a side effect of
   the dispatch action itself, so a model that "forgets" scripts/reef-attempt
   still cannot loop forever (the odometer trips at 2x the cap). A denied
   dispatch never bumps the odometer.

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
OPS = {";", "&", "|", "&&", "||", ";;", ";&", "|&"}
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
    """Tokens with shell operators as separate tokens; None if unparseable."""
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=";|&")
    lex.whitespace_split = True
    try:
        return list(lex)
    except ValueError:
        return None


def check_bash(cmd):
    # a newline separates commands exactly like ';' — without this, everything after
    # the first line would be scanned as arguments of the first command
    flat = re.sub(r"\r?\n", " ; ", cmd)
    toks = tokenize(flat)
    if toks is None:
        # Unparseable (unbalanced quotes): flags can no longer be told apart from
        # values, so a bypass-smelling string is denied outright.
        if re.search(r"no-verify|hookspath", cmd, re.I):
            deny("unparseable command that mentions a gate bypass")
        return
    seg = []
    for t in toks + [";"]:
        if t in OPS:
            if seg:
                check_segment(seg)
            seg = []
        else:
            seg.append(t)


def check_segment(seg):
    k = 0
    while k < len(seg) and ENV_ASSIGN.match(seg[k]):
        if HOOKSPATH.search(seg[k]):
            deny(f"environment assignment smuggles hooksPath: {seg[k]!r}")
        k += 1
    if k >= len(seg):
        return
    base = os.path.basename(seg[k])
    args = seg[k + 1:]
    if base in ("rm", "mv", "unlink", "truncate"):
        for a in args:
            if HOOK_PATHS.search(a):
                deny(f"{base} on {a!r} disables the commit gate")
    elif base == "chmod":
        # adding a permission (+x) is reef-init's own install; any other chmod on the hooks is sabotage
        if any(HOOK_PATHS.search(a) for a in args) and not any("+" in a for a in args):
            deny("chmod that does not ADD a permission on the hook files disables the commit gate")
    elif base in ("sh", "bash", "dash", "zsh", "ksh"):
        for i, a in enumerate(args):
            if a == "-c" and i + 1 < len(args):
                check_bash(args[i + 1])   # `sh -c "git commit -n"` is not a tunnel
    elif base == "eval":
        check_bash(" ".join(args))
    elif base == "git":
        check_git(args)


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
        elif sub == "config":
            check_git_config(args[j:])
            return
        j += 1


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
        if ":" in line and not line.lstrip().startswith("#"):
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"')
    return fm, text


def bump_dispatches(path, text, current):
    """Increment dispatches: inside the frontmatter only; unique temp + atomic replace."""
    m = FENCE.match(text)
    fm_body = m.group(1)
    if re.search(r"^dispatches:", fm_body, re.M):
        new_fm = re.sub(r"^dispatches:.*$", f"dispatches: {current + 1}", fm_body, count=1, flags=re.M)
    else:
        new_fm = fm_body + f"dispatches: {current + 1}\n"
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


def read_cap(root):
    try:
        with open(os.path.join(root, ".reef", "config.json"), encoding="utf-8") as f:
            cap = json.load(f).get("caps", {}).get("attempts", DEFAULT_CAP)
        return int(cap)
    except Exception:
        return DEFAULT_CAP


def check_stamp(root):
    """Mechanical plan-freshness: an edited plan never dispatches unnoticed.
    Read-only; runs BEFORE the odometer bump so a stale-plan denial costs nothing."""
    script = os.path.join(root, "scripts", "reef-plan-check.py")
    if not os.path.isfile(script):
        return  # not a reef-init'd layout; nothing to verify against
    try:
        r = subprocess.run([sys.executable, script, root, "--verify-stamp"], cwd=root,
                           capture_output=True, text=True, timeout=30)
    except Exception:
        return
    if r.returncode != 0:
        deny("plan stamp is stale or missing — the plan changed since its last review; "
             "run the reef-plan-review skill before dispatching (" + (r.stdout or r.stderr).strip() + ")")


def check_dispatch(tool_input, payload):
    sub = str(tool_input.get("subagent_type") or "")
    if "implementer" not in sub:
        return
    prompt = str(tool_input.get("prompt") or "")
    m = re.search(r"^REEF-TASK:[ \t]*(.+?)[ \t]*$", prompt, re.M)
    if not m:
        deny("implementer dispatch without a 'REEF-TASK: <task-file>' line — run scripts/reef-attempt "
             "and start the dispatch prompt with the line it prints")
    cwd = payload.get("cwd") or os.getcwd()
    path = m.group(1)
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    if not os.path.isfile(path):
        deny(f"REEF-TASK file not found: {path}")
    check_stamp(cwd)
    with open(lock_path_for(path), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            fm, text = read_frontmatter(path)
        except Exception as e:   # OSError, UnicodeDecodeError, anything: fail CLOSED
            deny(f"cannot read {path}: {e}")
        if fm is None:
            deny(f"{path} has no frontmatter fence — not a reef task file")
        cap = read_cap(cwd)
        try:
            attempts = int(fm.get("attempts", "0") or 0)
            dispatches = int(fm.get("dispatches", "0") or 0)
        except ValueError:
            deny(f"{path}: attempts/dispatches are not integers — fix the frontmatter")
        if fm.get("status") == "blocked":
            deny(f"{path} is blocked — a HUMAN must unblock it (attempts: 0, status: pending, last_failure_sig: \"\")")
        if attempts >= cap:
            deny(f"{path} is at the retry cap ({attempts}/{cap}) — USER ACTION REQUIRED")
        if dispatches >= 2 * cap:
            deny(f"{path} was dispatched {dispatches}x against cap {cap} without enough recorded failures — "
                 "runaway-loop backstop; record failures via scripts/reef-attempt or stop")
        # every check passed: the odometer moves as part of the dispatch itself
        bump_dispatches(path, text, dispatches)


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
