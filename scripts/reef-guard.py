#!/usr/bin/env python3
"""Reef PreToolUse guard — the mechanical layer behind the plugin's "hard" rules.

Reads the hook JSON on stdin. Two duties:

1. Bash commands: deny gate bypasses. This TOKENIZES the command (shlex with shell
   operators) instead of substring-matching, so it catches `git commit -n`, bundled
   short flags (`-anm`), `git -c core.hookspath=... commit`, flag insertion
   (`git --no-pager commit --no-verify`), case games (`core.hookspath`), env
   smuggling (`GIT_CONFIG_KEY_0=core.hooksPath`), and `rm/mv/chmod` on the hook
   files — while ALLOWING reef-init's own install (`git config core.hooksPath
   .githooks`), read-only queries (`--get`), and commit messages that merely
   mention "--no-verify". A blocklist over a shell surface can never be complete:
   this hook is a TRIPWIRE; CI is the wall (see README).

2. Task/Agent dispatches of the reef implementer: refuse when the task file is
   blocked or at the retry cap, refuse when the plan stamp is stale, and advance a
   `dispatches:` odometer IN THIS HOOK — the counter moves as a side effect of the
   dispatch action itself, so a model that "forgets" scripts/reef-attempt still
   cannot loop forever (the odometer trips at 2x the cap).

Exit 0 = allow. Exit 2 = deny (reason on stderr). Anything unparseable that smells
like a bypass is denied; anything unparseable and innocent is allowed.
"""
import json
import os
import re
import shlex
import subprocess
import sys

DEFAULT_CAP = 3
OPS = {";", "&", "|", "&&", "||", ";;", ";&", "|&"}
# git global options that consume a separate value before the subcommand
GIT_GLOBAL_VALUE_OPTS = {"-C", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix", "--config-env"}
# git-commit options that consume a separate value (their VALUES must not be inspected)
COMMIT_VALUE_OPTS = {"-m", "--message", "-F", "--file", "-t", "--template", "-c", "-C",
                     "--reedit-message", "--reuse-message", "--author", "--date",
                     "--fixup", "--squash", "--trailer", "--pathspec-from-file", "-S", "--gpg-sign"}


def deny(reason):
    print(f"reef-guard DENY: {reason}", file=sys.stderr)
    sys.exit(2)


def tokenize(cmd):
    """Split a shell command into tokens; operators become their own tokens.
    Returns None when the command cannot be parsed (unbalanced quotes)."""
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=";|&")
    lex.whitespace_split = True
    try:
        return list(lex)
    except ValueError:
        return None


def check_bash(cmd):
    toks = tokenize(cmd)
    if toks is None:
        # Unparseable: conservative tripwire on the raw text. Values can no longer be
        # told apart from flags, so a bypass-smelling string is denied outright.
        if re.search(r"no-verify|hookspath", cmd, re.I):
            deny("unparseable command that mentions a gate bypass")
        return

    for t in toks:
        # env smuggling: GIT_CONFIG_KEY_0=core.hooksPath git commit ...
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t) and re.search(r"hookspath", t, re.I):
            deny(f"environment assignment smuggles hooksPath: {t!r}")

    # file-level sabotage of the hook files themselves
    for i, t in enumerate(toks):
        if os.path.basename(t) in ("rm", "mv", "unlink", "chmod", "truncate"):
            for r in toks[i + 1:]:
                if r in OPS:
                    break
                if ".githooks" in r or ".git/hooks" in r:
                    deny(f"{os.path.basename(t)} on {r!r} disables the commit gate")

    i = 0
    while i < len(toks):
        if toks[i] in OPS or os.path.basename(toks[i]) != "git":
            i += 1
            continue
        i = check_git_invocation(toks, i + 1)


def check_git_invocation(toks, j):
    """Scan one `git ...` invocation starting after the `git` token.
    Returns the index where the invocation ends (an operator or EOL)."""
    sub = None
    while j < len(toks):
        a = toks[j]
        if a in OPS:
            return j
        if sub is None:
            if a == "-c" and j + 1 < len(toks):
                if re.match(r"^core\.hookspath(=|$)", toks[j + 1], re.I):
                    deny(f"git -c {toks[j + 1]!r} redirects hooks away from the gate")
                j += 2
                continue
            if re.match(r"^-c.+", a) and re.search(r"^-ccore\.hookspath", a, re.I):
                deny(f"git {a!r} redirects hooks away from the gate")
            if a in GIT_GLOBAL_VALUE_OPTS:
                j += 2
                continue
            if a.startswith("--") and "=" in a and re.search(r"hookspath", a, re.I):
                deny(f"git {a!r} redirects hooks away from the gate")
            if a.startswith("-"):
                j += 1
                continue
            sub = a
            j += 1
            continue
        # ---- inside subcommand arguments ----
        if sub in ("commit", "merge") and (a == "--no-verify" or re.match(r"^-[a-zA-Z]*n[a-zA-Z]*$", a)):
            # -n is the short form of --no-verify; bundled clusters (-anm) count too
            deny(f"git {sub} {a!r} skips the pre-commit gate (use the gate or fix the failure)")
        if sub == "push" and a == "--no-verify":
            deny("git push --no-verify skips the pre-push gate")
        if sub == "commit" and a in COMMIT_VALUE_OPTS:
            j += 2  # never inspect option VALUES (a commit message may mention --no-verify)
            continue
        if sub == "config":
            return check_git_config(toks, j)
        j += 1
    return j


def check_git_config(toks, j):
    """`git config ...` — deny writes that move core.hooksPath anywhere but .githooks."""
    seg = []
    while j < len(toks) and toks[j] not in OPS:
        seg.append(toks[j])
        j += 1
    touches = [k for k, t in enumerate(seg) if re.search(r"(^|\.)hookspath$", t, re.I)]
    if not touches:
        return j
    read_only = any(t in ("--get", "--get-all", "--get-regexp", "--list", "-l", "get", "list") for t in seg)
    unset = any(t in ("--unset", "--unset-all", "unset") for t in seg)
    if read_only and not unset:
        return j
    if unset:
        deny("git config --unset core.hooksPath removes the commit gate")
    k = touches[0]
    value = next((t for t in seg[k + 1:] if not t.startswith("-")), None)
    if value == ".githooks":
        return j  # reef-init's own install — explicitly allowed
    deny(f"git config core.hooksPath {value!r} points hooks away from the gate (.githooks is the only allowed value)")


# ---------------- Task dispatch guard (the cap, enforced at the action) ----------------

FENCE = re.compile(r"\A---\r?\n(.*?\r?\n)---\r?\n", re.S)


def read_frontmatter(path):
    with open(path, encoding="utf-8") as f:
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
    """Increment dispatches: inside the frontmatter only; atomic replace."""
    m = FENCE.match(text)
    fm_body = m.group(1)
    if re.search(r"^dispatches:", fm_body, re.M):
        new_fm = re.sub(r"^dispatches:.*$", f"dispatches: {current + 1}", fm_body, count=1, flags=re.M)
    else:
        new_fm = fm_body + f"dispatches: {current + 1}\n"
    new_text = text[:m.start(1)] + new_fm + text[m.end(1):]
    tmp = path + ".reef-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(new_text)
    os.replace(tmp, path)


def read_cap(root):
    try:
        with open(os.path.join(root, ".reef", "config.json"), encoding="utf-8") as f:
            cap = json.load(f).get("caps", {}).get("attempts", DEFAULT_CAP)
        return int(cap)
    except Exception:
        return DEFAULT_CAP


def check_dispatch(tool_input, payload):
    sub = str(tool_input.get("subagent_type") or "")
    if "implementer" not in sub:
        return
    prompt = str(tool_input.get("prompt") or "")
    m = re.search(r"^REEF-TASK:[ \t]*(\S+)", prompt, re.M)
    if not m:
        deny("implementer dispatch without a 'REEF-TASK: <task-file>' line — run scripts/reef-attempt "
             "and start the dispatch prompt with the line it prints")
    cwd = payload.get("cwd") or os.getcwd()
    path = m.group(1)
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    if not os.path.isfile(path):
        deny(f"REEF-TASK file not found: {path}")
    try:
        fm, text = read_frontmatter(path)
    except OSError as e:
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
    check_stamp(cwd)
    bump_dispatches(path, text, dispatches)


def check_stamp(root):
    """Mechanical plan-freshness: an edited plan never dispatches unnoticed."""
    script = os.path.join(root, "scripts", "reef-plan-check.py")
    if not os.path.isfile(script):
        return  # not a reef-init'd layout; nothing to verify against
    try:
        r = subprocess.run([sys.executable, script, "--verify-stamp"], cwd=root,
                           capture_output=True, text=True, timeout=30)
    except Exception:
        return
    if r.returncode != 0:
        deny("plan stamp is stale or missing — the plan changed since its last review; "
             "run the reef-plan-review skill before dispatching (" + (r.stdout or r.stderr).strip() + ")")


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
