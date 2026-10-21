#!/usr/bin/env python3
# CLASS: code, tripwire
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

3. 0.6 — the guard reads the TIER: a dispatch's model is resolved through the task's
   tier table (tiers.<tier>.roles.<role>, from the REEF-TASK: or REEF-FEATURE: line every
   role dispatch carries; without the line, roles.* as in 0.5); `critical` needs the
   adversarial plan pass like `design`. REVIEWER LOCK (payload agent_type, verified in
   docs/perf/payloads-2026-10-16.md): a verifier, loophole-hunter, plan-reviewer or Explore
   sub-agent gets no mutating git, no Bash write, no CI wait; a typeless sub-agent call is
   locked too while .reef/verifying/<task> exists (written here when a verifier/hunter
   dispatch is allowed). The guard GUARDS ITSELF (Edit/Write/MultiEdit matcher and Bash
   writes): scripts/reef-*, .githooks/*, hooks/hooks.json and the roles/caps/gates/tiers keys
   of .reef/config.json change only under a critical task in flight or inside the plugin's
   own repository; .reef/approvals/ and .reef/review/ are written by hooks and scripts
   only. A DEADLINE (signal alarm, REEF_GUARD_DEADLINE seconds) denies before the host's
   hook timeout: a hung guard is a denial, never an allow.

Exit 0 = allow. Exit 2 = deny (reason on stderr). Anything unparseable that
smells like a bypass is denied; anything unparseable and innocent is allowed.
"""
import os as _os
import sys as _sys

# 0.7: native Windows has no fcntl locks, no SIGALRM deadline and no process groups, and the guard cannot run there.
# Inside a Reef project it stops with the one sentence that helps; anywhere else it steps aside (the plugin's hook runs
# in every session, and a Windows user's other projects are not Reef's to block). WSL2 is Linux: os.name is "posix".
if _os.name == "nt" or _os.environ.get("REEF_TEST_NATIVE_WINDOWS"):
    try:
        import json as _json
        _cwd = str((_json.load(_sys.stdin) or {}).get("cwd") or _os.getcwd())
    except Exception:
        _cwd = _os.getcwd()
    _d = _os.path.abspath(_cwd)
    while True:
        if _os.path.isfile(_os.path.join(_d, ".reef", "config.json")):
            print("reef-guard DENY: Reef runs on macOS or Linux; on Windows, run Claude Code inside WSL2 — native Windows lacks the file locks and timers the guard needs "
                  "(README: Before you run it)", file=_sys.stderr)
            _sys.exit(2)
        _up = _os.path.dirname(_d)
        if _up == _d:
            _sys.exit(0)
        _d = _up

import fcntl
import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time

DEADLINE = float(os.environ.get("REEF_GUARD_DEADLINE", "8"))
TIER_ORDER = ["light", "full", "design", "critical"]
LOCKED_TYPES = ("verifier", "loophole-hunter", "plan-reviewer", "Explore", "security", "mahmoud")
AGENT_TYPES = LOCKED_TYPES + ("implementer", "mechanic")
MUTATING_GIT = {"commit", "add", "rm", "mv", "checkout", "switch", "restore", "reset", "merge", "rebase", "push",
                "stash", "apply", "am", "cherry-pick", "revert", "clean", "worktree", "submodule", "init", "clone"}
WRITE_HEADS = {"tee", "cp", "mv", "rm", "touch", "mkdir", "rmdir", "truncate", "dd", "install", "ln", "chmod", "chown", "shred", "unlink"}
REDIRECTS = {">", ">>", ">|"}
STATUS_LINE = re.compile(r"in flight:.*?/\s*waiting on:.*?/\s*next:\s*\S", re.S)
RECORD_DIRS = re.compile(r"(^|/)\.reef/(approvals|review|night)(/|$)")   # night (0.7, super Reef): the contract and the `active` marker
# evidence an AGENT produced: a hand-back, a verifier/hunter report, a plan review. The main session (no agent_id in
# the payload) may copy one (cp/mv from the scratchpad) but never write its content (2026-10-17: a hunter report and
# a hand-back were typed by the orchestrator "from the agent's message" — evidence nobody but the orchestrator wrote).
EVIDENCE = re.compile(r"(^|/)\.reef/(ci-local/(handback|report|hunt|plan-review)-[^/]+\.md|hunt/[^/]+\.md)$")
COPY_HEADS = {"cp", "mv", "install", "rsync"}
EVIDENCE_DENIAL = ("the main session does not write an agent's evidence ({path}): the agent writes its own file (the hand-back into "
                   "its worktree's .reef/ci-local/, a judge's report into the scratchpad) and the orchestrator copies it with cp. "
                   "Missing? Resume that agent (SendMessage) with 'write your report to <path>' — never type it from its message")
GUARD_FILES = re.compile(r"(^|/)(scripts/reef-[^/]+|\.githooks/[^/]+|hooks/hooks\.json|\.reef/config\.json)$")
PROTECTED_KEYS = ("roles", "caps", "gates", "tiers")
GH_TIMEOUT = float(os.environ.get("REEF_GH_TIMEOUT", "5"))
PR_MERGE_API = re.compile(r"repos/([^/]+)/([^/]+)/pulls/(\d+)/merge")
GOOD_VERDICTS = ("PASS", "GREEN", "APPROVED")

DEFAULT_CAP = 3
OPS = {";", "&", "|", "&&", "||", ";;", ";&", "|&", "(", ")", "\n"}
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
    their own tokens; None if unparseable. A bare newline is an operator token (a command
    separator, like `;`) while a newline INSIDE a quote stays a literal message character;
    default commenters='#' ends a comment at its own line's newline. Heredoc bodies are
    stripped (data, not commands). check_segment still scans every token position for
    git/rm/chmod, so a prefix word never hides the real command."""
    lex = shlex.shlex(cmd, posix=True, punctuation_chars="();|&<>\n")
    lex.whitespace = " \t\r"       # a bare newline is a command separator (an operator token), not whitespace
    lex.whitespace_split = True
    try:
        return strip_heredocs(list(lex))
    except ValueError:
        return None


def strip_heredocs(toks):
    """`<< WORD` / `<<- WORD`: the body (from the next newline to the line holding WORD alone) is DATA for the
    command's stdin, not commands — drop it, so a JSON payload or a script fed by heredoc is never read as the
    shell. Measured false positive (first contact, 2026-10-16): `cat > .reef/grill.json <<'EOF' … EOF` followed by
    `python3 …/scripts/reef-init.py` on the next line was denied as a write to reef-init.py."""
    out, pending, i = [], [], 0
    while i < len(toks):
        t = toks[i]
        if t == "<<" and i + 1 < len(toks):
            word = toks[i + 1]
            pending.append(word[1:] if word.startswith("-") and len(word) > 1 else word)
            i += 2
            continue
        out.append(t)
        if t == "\n" and pending:
            word = pending.pop(0)
            while i + 1 < len(toks):
                i += 1
                if toks[i] == word and (i + 1 >= len(toks) or toks[i + 1] == "\n"):
                    break
        i += 1
    return out


def check_bash(cmd, depth=0):
    try:
        _check_bash(cmd, depth)
    except SystemExit:
        raise
    except Exception:
        # a guard crash must not open the gate: deny when the raw text smells
        if re.search(r"no-verify|hookspath", cmd, re.I):
            deny("guard internal error on a command that mentions a gate bypass — failing closed")


SIMPLE_ASSIGN = re.compile(r"(?:^|[;&|\n]\s*)([A-Za-z_]\w*)=([^\s;&|'\"$`()]+)")


def expand_simple_vars(cmd):
    """`S=/tmp/claude-…/scratchpad/r2; mkdir -p $S` — the value of a plain `NAME=path` assignment made earlier in the
    SAME command stands in for `$NAME`/`${NAME}` after it, so the scratch check sees the path (2026-10-18: a judge was
    refused `mkdir -p $S` in its own scratchpad). Only unquoted, expansion-free values; anything else stays literal
    and is judged as before (a variable the guard cannot read is still a write it cannot place)."""
    out = cmd
    for m in SIMPLE_ASSIGN.finditer(cmd):
        name, value = m.group(1), m.group(2)
        tail_start = m.end()
        head, tail = out[:tail_start], out[tail_start:]
        tail = re.sub(r"\$\{" + re.escape(name) + r"\}|\$" + re.escape(name) + r"\b", value.replace("\\", "\\\\"), tail)
        out = head + tail
    return out


def _check_bash(cmd, depth=0):
    if depth > MAX_DEPTH:
        deny("shell nesting too deep to analyze — refusing a command that hides commands this many layers down")
    cmd = expand_simple_vars(cmd)
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
    if depth == 0:
        CTX.pop("cd_hint", None)
    for t in toks + [";"]:
        if t in OPS:
            if seg:
                check_segment(seg, depth, next_op=t, pipefail=pipefail)
                # `cd /abs/path && …`: later relative write targets in this command live under that path (2026-10-18:
                # a judge's `cd $S && cat > mod.ts` in its scratchpad was refused as a project write)
                k = 0
                while k < len(seg) and (ENV_ASSIGN.match(seg[k]) or seg[k] in PREFIX_WORDS):
                    k += 1
                if k + 1 < len(seg) and os.path.basename(seg[k]) == "cd" and t in (";", "&&") and os.path.isabs(seg[k + 1]):
                    CTX["cd_hint"] = seg[k + 1]
            seg = []
        else:
            seg.append(t)


def is_write(seg):
    """A segment that can change a file: a redirect, a write head, `sed -i`/`perl -i`, `git apply`."""
    if any(t in REDIRECTS for t in seg):
        return True
    i = 0
    while i < len(seg) and (ENV_ASSIGN.match(seg[i]) or seg[i] in PREFIX_WORDS or seg[i].startswith("-") or seg[i].isdigit()):
        i += 1
    if i >= len(seg):
        return False
    head, rest = os.path.basename(seg[i]), seg[i + 1:]
    if head in WRITE_HEADS:
        return True
    if head in ("sed", "perl") and any(re.match(r"^-[a-zA-Z]*i", a) for a in rest):
        return True
    return False


DEVNULL = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty")


def write_targets(seg):
    """The tokens a write segment can CHANGE: every redirect's target, and every non-flag argument after a write
    head (`cp`, `mv`, `tee`, `sed -i` …) anywhere in the segment. A guarded path that is merely RUN or READ
    (`python3 scripts/reef-init.py … > init.log`) is not a target; `2>/dev/null` is no write at all."""
    out = []
    for j, t in enumerate(seg):
        if t in REDIRECTS and j + 1 < len(seg) and seg[j + 1] not in DEVNULL:
            out.append(seg[j + 1])
    # a download's output file (0.7, /reef-pentest: the hunter attacks a running app with curl; `-o <file>` into the
    # project is a write, `-o /dev/null` is not)
    for j, t in enumerate(seg):
        head = os.path.basename(t)
        if head in ("curl", "wget"):
            flags = ("-o", "--output") if head == "curl" else ("-O", "--output-document")
            for k, a in enumerate(seg[j + 1:], start=j + 1):
                if a in flags and k + 1 < len(seg) and seg[k + 1] not in DEVNULL:
                    out.append(seg[k + 1])
                elif any(a.startswith(f + "=") for f in flags if f.startswith("--")) and a.split("=", 1)[1] not in DEVNULL:
                    out.append(a.split("=", 1)[1])
    for j, t in enumerate(seg):
        head = os.path.basename(t)
        if head in WRITE_HEADS or (head in ("sed", "perl") and any(re.match(r"^-[a-zA-Z]*i", a) for a in seg[j + 1:])):
            out += [a for a in seg[j + 1:] if not a.startswith("-") and a not in REDIRECTS]
            break
    return out


def is_scratch(path):
    """Under the temp dir or a Claude scratchpad (/tmp/claude-…/…/scratchpad, /private/tmp/… on macOS)."""
    p = os.path.abspath(os.path.expanduser(path)) if path.startswith(("/", "~")) else ""
    if not p:
        return False
    tmp = os.path.realpath(tempfile.gettempdir())
    return p.startswith((tmp + "/", "/tmp/", "/private/tmp/", "/var/folders/"))


def check_record_dirs(seg):
    """.reef/approvals/ and .reef/review/ are written by scripts/reef-approval.py and scripts/reef-record
    only: a hand-written record would be an approval nobody gave (tripwire; the digest check is the code)."""
    if any(RECORD_DIRS.search(t) for t in write_targets(seg)):
        deny("writing under .reef/approvals/, .reef/review/ or .reef/night/ by hand — these records are written by the "
             "AskUserQuestion hook, scripts/reef-record and scripts/reef-run.py, bound to a digest or a forge SHA")


def check_evidence_authoring(seg, ctx):
    if not ctx.get("main_session") or not is_write(seg):
        return
    head = next((os.path.basename(x) for x in seg if os.path.basename(x) in WRITE_HEADS), None)
    if head in COPY_HEADS:
        return   # a copy carries the agent's words unchanged
    hits = [x for x in write_targets(seg) if EVIDENCE.search(x)]
    if hits:
        deny(EVIDENCE_DENIAL.format(path=hits[0]))


def check_guard_files(seg, ctx):
    """scripts/reef-*, .githooks/*, hooks/hooks.json, .reef/config.json: a Bash write (redirect, cp, mv, sed -i …)
    is allowed only inside the plugin's own repository or under a critical task in flight. rm/mv/chmod on the
    hook files keep their 0.5 denial regardless."""
    if not is_write(seg) or any(os.path.basename(t) == "chmod" for t in seg):
        return   # chmod on the hook files is check_chmod's business (pure +x is reef-init's install)
    hits = [t for t in write_targets(seg) if GUARD_FILES.search(t)]
    if hits and not ctx.get("plugin_root") and not ctx.get("critical_inflight"):
        deny(f"Bash write to {hits[0]!r}: the guard's own files and the roles/caps/gates/tiers keys change only under "
             "a tier: critical task (none is in flight) or inside Reef's own repository — plan it as a critical task "
             "(python3 scripts/reef-init.py --accept <path> is the allowed way to take a proposed script)")


def check_reviewer_lock(seg, ctx):
    """agent_type from the payload: a judge never mutates. Also no CI wait for any Reef sub-agent."""
    agent_type = ctx.get("agent_type") or ""
    locked = any(t in agent_type for t in LOCKED_TYPES) or ctx.get("typeless_locked")
    who = agent_type or "a sub-agent without agent_type (a verifier/hunter is in flight)"
    i = 0
    while i < len(seg) and (ENV_ASSIGN.match(seg[i]) or seg[i] in PREFIX_WORDS or seg[i].startswith("-") or seg[i].isdigit()):
        i += 1
    head = os.path.basename(seg[i]) if i < len(seg) else ""
    rest = seg[i + 1:]
    if any(t in agent_type for t in AGENT_TYPES) or ctx.get("typeless_locked"):
        if head == "gh" and (rest[:2] == ["pr", "checks"] and "--watch" in rest or rest[:2] == ["run", "watch"]):
            deny(f"{who}: `gh {' '.join(rest[:2])} --watch` parks an agent on CI — the orchestrator waits with a Monitor "
                 "or a scheduled wake-up, never a sub-agent")
        if head == "sleep" and rest and re.match(r"^\d+(\.\d+)?[smh]?$", rest[0]):
            n = float(re.match(r"^\d+(\.\d+)?", rest[0]).group(0)) * {"m": 60, "h": 3600}.get(rest[0][-1], 1)
            if n >= 60:
                deny(f"{who}: sleep {rest[0]} — a sub-agent never waits a minute for the world to change")
    if not locked:
        return
    for j, t in enumerate(seg):
        if os.path.basename(t) == "git":
            args = seg[j + 1:]
            sub = next((a for a in args if not a.startswith("-")), None)
            # `git worktree list` and `git stash list` read; the other verbs of those commands write (first contact,
            # 2026-10-17: the plan-reviewer was refused `git worktree list` and re-ran its whole command without it)
            verb = next((a for a in args[args.index(sub) + 1:] if not a.startswith("-")), None) if sub in ("worktree", "stash", "submodule") else None
            if sub in MUTATING_GIT and not (sub in ("worktree", "stash", "submodule") and verb in ("list", "show", "status")):
                deny(f"{who} is read-only: `git {sub}` mutates the tree or the refs the orchestrator hash-checks")
            if sub in ("branch", "tag") and any(a in ("-d", "-D", "-m", "-M", "-c", "-C", "-f") for a in args) \
               or sub == "config" and not any(a in ("--get", "--get-all", "--list", "-l", "get", "list") for a in args):
                deny(f"{who} is read-only: `git {sub} {' '.join(args[1:3])}` writes")
            break
    targets = write_targets(seg)
    hint = ctx.get("cd_hint")
    in_scratch = lambda x: is_scratch(x) or bool(hint and not os.path.isabs(x) and not x.startswith("~") and is_scratch(os.path.join(hint, x)))
    if targets and not all(in_scratch(x) for x in targets):
        # a judge never mutates the PROJECT; its own scratch space (the session scratchpad, the temp dir) is not the
        # project — first contact, 2026-10-16: the hunter was refused `mkdir -p …/scratchpad/pk` to inspect a tarball
        deny(f"{who} is read-only: {' '.join(seg[:4])!r} writes a file — judge, don't fix")


SHELLS = ("sh", "bash", "dash", "zsh", "ksh")
DESTRUCTIVE = ("rm", "mv", "unlink", "truncate", "shred")
# gates whose exit code IS the verdict: piping them hides it (the pipe reports the
# last command's status). Names, not paths — `sh scripts/reef-gate.sh | tail` too.
STASH_READ_ONLY = {"list", "show"}
MODE_RE = re.compile(r"^([0-7]{3,4}|[ugoa]*[-+=][rwxXstugo]+(,[ugoa]*[-+=][rwxXstugo]+)*)$")
PURE_ADD = re.compile(r"^[ugoa]*\+[rwxXst]+$")


PREFIX_WORDS = {"env", "nohup", "nice", "time", "sudo", "command", "exec", "ionice", "stdbuf"}
GATE_SCRIPTS = {"reef-gate.sh", "reef-ci-local.sh"}
RUNNERS = {"pytest", "vitest", "jest"}


def is_gate(seg):
    """A segment whose COMMAND HEAD runs a test gate: `npm test`, `npm run ci:local`, `pytest -q`,
    `uv run pytest`, `npx vitest`, `python3 -m pytest`, `cargo test`, `go test ./...`,
    `sh scripts/reef-gate.sh`. Only the head counts — `grep pytest src | head` and
    `git log --grep vitest | head` merely mention a gate word and must pass."""
    i = 0
    while i < len(seg) and (ENV_ASSIGN.match(seg[i]) or seg[i] in PREFIX_WORDS
                            or seg[i].startswith("-") or seg[i].isdigit()):
        i += 1   # env assignments, wrapper words and their flags/values (`nice -n 5`)
    if i >= len(seg):
        return False
    head, rest = os.path.basename(seg[i]), seg[i + 1:]
    if head in GATE_SCRIPTS or head in RUNNERS:
        return True
    if head == "npm":
        return "test" in rest[:1] or "ci:local" in rest[:2]
    if head in ("cargo", "go"):
        return rest[:1] == ["test"]
    if head in SHELLS:
        return any(os.path.basename(a) in GATE_SCRIPTS for a in rest)
    if head == "uv":
        return rest[:1] == ["run"] and len(rest) > 1 and os.path.basename(rest[1]) in RUNNERS
    if head == "npx":
        return len(rest) > 0 and rest[0] in RUNNERS
    if head in ("python", "python3"):
        return rest[:2] == ["-m", "pytest"]
    return False


CTX = {}   # per-invocation facts the Bash checks need: agent_type, plugin_root, critical_inflight, typeless_locked


def check_segment(seg, depth=0, next_op=";", pipefail=False):
    """Position-independent: `env X=y git ...`, `nohup git ...`, `nice -n5 git ...`,
    `xargs git ...`, `(git ...)` — a prefix word must never hide the real command."""
    for t in seg:
        if ENV_ASSIGN.match(t) and HOOKSPATH.search(t):
            deny(f"environment assignment smuggles hooksPath: {t!r}")
    check_record_dirs(seg)
    check_evidence_authoring(seg, CTX)
    check_guard_files(seg, CTX)
    check_reviewer_lock(seg, CTX)
    check_forge_merge(seg, CTX)
    check_release_pr(seg, CTX)
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


def gh(args, cwd):
    """A forge call under its own deadline; any failure is a denial (fail closed)."""
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=GH_TIMEOUT, cwd=cwd)
    except FileNotFoundError:
        deny("gh is not installed — the merge check needs the forge's view of the PR")
    except subprocess.TimeoutExpired:
        deny(f"gh {' '.join(args[:2])} did not answer within {GH_TIMEOUT:g}s — refusing to merge blind")
    if r.returncode != 0:
        deny(f"gh {' '.join(args[:2])} failed ({r.returncode}): {r.stderr.strip()[:200]} — refusing to merge blind")
    return r.stdout.strip()


def git_version_ok(cwd):
    v = os.environ.get("REEF_GIT_VERSION_OVERRIDE")   # test seam: pretend an older git
    if not v:
        r = subprocess.run(["git", "--version"], capture_output=True, text=True, cwd=cwd)
        m = re.search(r"(\d+)\.(\d+)", r.stdout)
        v = f"{m.group(1)}.{m.group(2)}" if m else "0.0"
    major, minor = (int(x) for x in v.split(".")[:2])
    return (major, minor) >= (2, 38)


def _flag(rest, longs, shorts):
    """The value of `--base X`, `--base=X` or `-B X` in a gh argument list; None when absent."""
    for j, a in enumerate(rest):
        for name in longs:
            if a == name and j + 1 < len(rest):
                return rest[j + 1]
            if a.startswith(name + "="):
                return a[len(name) + 1:]
        if a in shorts and j + 1 < len(rest):
            return rest[j + 1]
    return None


def check_release_pr(seg, ctx):
    """0.7: the release PR (`gh pr create` into branches.release) opens only on a PASS security record
    (.reef/review/security-<sha12>.json, written by `reef-record security` from reef:security's report) whose
    head is the commit the PR proposes. Strict: a base that moved since the pass is a new release, audited again.
    No rule when branches.base == branches.release (no release step). A PR opened in the forge's web UI is
    outside every hook — the ledger says so."""
    i = 0
    while i < len(seg) and (ENV_ASSIGN.match(seg[i]) or seg[i] in PREFIX_WORDS):
        i += 1
    if i >= len(seg) or os.path.basename(seg[i]) != "gh" or seg[i + 1:i + 3] != ["pr", "create"]:
        return
    rest = seg[i + 3:]
    roots = sorted(ctx.get("roots") or [ctx.get("cwd") or os.getcwd()])
    cfg = next((read_config(r) for r in roots if os.path.isfile(os.path.join(r, ".reef", "config.json"))), {})
    br = cfg.get("branches") or {}
    release, base = str(br.get("release", "main") or "main"), str(br.get("base", "main") or "main")
    pr_base = _flag(rest, ("--base",), ("-B",))
    if release == base or (pr_base is not None and pr_base != release):
        return
    cwd = ctx.get("cwd") or os.getcwd()
    if pr_base == release and any(os.path.isfile(os.path.join(r, ".reef", "night", "active")) for r in roots):
        deny(f"a super Reef night is running (.reef/night/active): the release to {release} is the owner's, in the morning — "
             "Mahmoud never opens it")
    head_ref = _flag(rest, ("--head",), ("-H",))
    ref = f"refs/heads/{head_ref.split(':')[-1]}" if head_ref else "HEAD"
    r = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd=cwd, capture_output=True, text=True)
    head = r.stdout.strip()
    if pr_base is None:
        # no --base: gh targets the forge's default branch, which on a base/release project is the release branch.
        # The only PR that comes from branches.base is the release PR — name the base, or it is treated as one.
        b = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{base}^{{commit}}"], cwd=cwd, capture_output=True, text=True)
        if not head or b.stdout.strip() != head:
            return
        deny(f"gh pr create from {base} with no --base: the forge's default branch is likely {release}, so this is the release PR — "
             f"pass --base {release} (the security pass is then required) or the branch you mean")
    if r.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", head):
        deny(f"release PR into {release}: cannot resolve its head {head_ref or 'HEAD'} here — run from the main checkout")
    for root in roots:
        d = os.path.join(root, ".reef", "review")
        for f in (sorted(os.listdir(d)) if os.path.isdir(d) else []):
            if not f.startswith("security-"):
                continue
            try:
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    rec = json.load(fh)
            except Exception:
                continue
            if rec.get("kind") == "security" and str(rec.get("verdict", "")).upper() == "PASS" and rec.get("head") == head:
                return
    deny(f"release PR into {release} at {head[:12]}: no PASS security record for that commit — dispatch reef:security on "
         f"`git diff {release}...{base}`, then `scripts/reef-record security PASS --report <its report>` (a base that moved "
         f"since the pass is audited again)")


def check_forge_merge(seg, ctx):
    """merge.by: loop — `gh pr merge` / `gh api …/pulls/N/merge` only when a PASS/GREEN review record
    (.reef/review/<feature>.json, written by scripts/reef-record from the forge's own view) names the PR's
    current head. A head that moved since the record merges only when the record is still an ancestor and
    either `git merge-tree --write-tree <recorded> <base tip>` equals the forge's tree (a clean base merge)
    or every commit since is claims-only. A rebase, a code push after GREEN, a slow or failing gh: DENY."""
    i = 0
    while i < len(seg) and (ENV_ASSIGN.match(seg[i]) or seg[i] in PREFIX_WORDS or seg[i].startswith("-") or seg[i].isdigit()):
        i += 1
    if i >= len(seg) or os.path.basename(seg[i]) != "gh":
        return
    rest = seg[i + 1:]
    ident = None
    if rest[:2] == ["pr", "merge"]:
        ident = next((a for a in rest[2:] if not a.startswith("-")), None)
    elif rest[:1] == ["api"] and any(PR_MERGE_API.search(a) for a in rest[1:]) and any(a in ("-X", "--method") and "PUT" in rest for a in rest):
        ident = PR_MERGE_API.search(next(a for a in rest[1:] if PR_MERGE_API.search(a))).group(3)
    elif rest[:1] == ["api"] and any(PR_MERGE_API.search(a) for a in rest[1:]):
        ident = PR_MERGE_API.search(next(a for a in rest[1:] if PR_MERGE_API.search(a))).group(3)
    else:
        return
    roots = sorted(ctx.get("roots") or [ctx.get("cwd") or os.getcwd()])
    cfg = next((read_config(r) for r in roots if os.path.isfile(os.path.join(r, ".reef", "config.json"))), {})
    if str((cfg.get("merge") or {}).get("by", "human")).strip() != "loop":
        return   # under merge.by: human the record is evidence, not a gate (the human merges)
    cwd = ctx.get("cwd") or os.getcwd()
    view = json.loads(gh(["pr", "view", *([ident] if ident else []), "--json", "headRefOid,baseRefName,url"], cwd) or "{}")
    head, base, url = str(view.get("headRefOid", "")), str(view.get("baseRefName", "")), str(view.get("url", ""))
    m = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", url)
    if not re.fullmatch(r"[0-9a-f]{40}", head) or not m:
        deny(f"gh pr view gave no usable head/url for {ident or 'the current PR'}: {view}")
    records = []
    for r in roots:
        d = os.path.join(r, ".reef", "review")
        for f in (sorted(os.listdir(d)) if os.path.isdir(d) else []):
            try:
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    rec = json.load(fh)
            except Exception:
                continue
            if str(rec.get("verdict", "")).upper() in GOOD_VERDICTS and re.fullmatch(r"[0-9a-f]{40}", str(rec.get("sha", ""))):
                records.append(rec)
    if any(rec["sha"] == head for rec in records):
        return
    if not records:
        deny(f"no PASS/GREEN review record under .reef/review/ for PR head {head[:12]} — run scripts/reef-record <feature> GREEN after the review")
    owner, repo = m.group(1), m.group(2)
    for rec in records:
        anc = subprocess.run(["git", "merge-base", "--is-ancestor", rec["sha"], head], cwd=cwd, capture_output=True)
        if anc.returncode != 0:
            continue   # a rebase or an unrelated record: the reviewed commit is not in this head
        if not git_version_ok(cwd):
            deny("the PR head moved since the review and this git predates 2.38 (no merge-tree --write-tree) — re-review the head")
        base_tip = gh(["api", f"repos/{owner}/{repo}/git/ref/heads/{base}", "--jq", ".object.sha"], cwd)
        forge_tree = gh(["api", f"repos/{owner}/{repo}/git/commits/{head}", "--jq", ".tree.sha"], cwd)
        have = subprocess.run(["git", "cat-file", "-e", f"{base_tip}^{{commit}}"], cwd=cwd, capture_output=True).returncode == 0
        if have:
            mt = subprocess.run(["git", "merge-tree", "--write-tree", rec["sha"], base_tip], cwd=cwd, capture_output=True, text=True)
            if mt.returncode == 0 and mt.stdout.strip().splitlines()[:1] == [forge_tree]:
                return   # the only change since the review is a clean merge of the base
        claims = load_plugin_module("reef-claims.py", "reef_claims")
        try:
            import io, contextlib
            with contextlib.redirect_stdout(io.StringIO()):
                if claims.cmd_claims_only(cwd, f"{rec['sha']}..{head}") == 0:
                    return   # docs, comments, blank lines only since GREEN
        except SystemExit:
            pass
        deny(f"PR head {head[:12]} moved since the GREEN record at {rec['sha'][:12]} and the new commits are code "
             "(not a clean base merge, not claims-only) — re-review and re-record before merging")
    deny(f"the reviewed commit is not an ancestor of PR head {head[:12]} (rebased or re-pushed) — re-review and re-record the current head")


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


def load_plugin_module(filename, name):
    """A sibling script from the PLUGIN's own directory (never the project's copy)."""
    import importlib.machinery
    import importlib.util
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    loader = importlib.machinery.SourceFileLoader(name, p)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def check_adversarial_plan(path, fm, text):
    """tier: design — the loophole-hunter's pass on the PLAN is recorded (scripts/reef-adversarial)
    as adversarial-plan: <hash of the plan content>; an edited plan voids it. A mech/light task
    never needs one (the stage never runs on mech)."""
    adv = load_plugin_module("reef-adversarial", "reef_adversarial")
    if fm.get("tier") not in adv.plan_pass_tiers(path):   # hunter.plan_pass: critical (default) or design
        return
    want = adv.plan_hash(text)
    got = (fm.get("adversarial-plan") or "").strip()
    if not got:
        deny(f"{path} is tier: design with no adversarial-plan record — run the loophole-hunter on the plan "
             "and record its PASS with scripts/reef-adversarial <task> plan <report> before any code")
    if got != want:
        deny(f"{path}: the plan changed since the loophole-hunter's pass (adversarial-plan {got} != {want}) — "
             "run the hunter again on the current plan")


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
# routing (2026-10-04, opus everywhere since 2026-10-17): opus plans, writes, attacks, verifies and reviews; sonnet does light
# mechanical work. Each project overrides per role; an unset role is not checked.
ROLE_OF = {"implementer": "author", "verifier": "verifier", "plan-reviewer": "plan_reviewer",
           "loophole-hunter": "adversary", "mechanic": "mechanic", "Explore": "mechanic", "security": "security",
           "planner": "planner", "mahmoud": "proxy"}


def read_config(root):
    try:
        with open(os.path.join(root, ".reef", "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def task_tier(fm):
    return fm.get("tier") or ("light" if fm.get("complexity") == "mech" else "full")


def feature_tier(root, feature):
    """The heaviest tier among a feature's task files (flat tasks/ + done/, or the feature folder)."""
    graph = load_graph_module()
    cfg = read_config(root)
    dirs = [graph.tasks_dir_for(root, cfg)]
    feat_dir = os.path.join(root, (cfg.get("paths") or {}).get("features", "reef/features"), feature, "tasks")
    if os.path.isdir(feat_dir):
        dirs.append(feat_dir)
    best = None
    for base in dirs:
        for d in (base, os.path.join(base, "done")):
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                if not f.endswith(".md"):
                    continue
                try:
                    fm, _ = read_frontmatter(os.path.join(d, f))
                except Exception:
                    continue
                if fm and fm.get("feature") == feature:
                    t = task_tier(fm)
                    if t in TIER_ORDER and (best is None or TIER_ORDER.index(t) > TIER_ORDER.index(best)):
                        best = t
    return best


def dispatch_tier(prompt, cwd):
    """(tier, root) from the dispatch prompt's REEF-TASK: or REEF-FEATURE: line; (None, cwd) without one."""
    m = re.search(r"^REEF-TASK:[ \t]*(.+?)[ \t\r]*$", prompt, re.M)
    if m:
        path = m.group(1) if os.path.isabs(m.group(1)) else os.path.join(cwd, m.group(1))
        if os.path.isfile(path):
            root = task_root(path, cwd)
            try:
                fm, _ = read_frontmatter(path)
                return (task_tier(fm) if fm else None), root
            except Exception:
                return None, root
        return None, cwd
    m = re.search(r"^REEF-FEATURE:[ \t]*(\S+)", prompt, re.M)
    if m:
        return feature_tier(cwd, m.group(1)), cwd
    return None, cwd


def check_role_model(sub, tool_input, root, tier=None):
    """A dispatch runs on the CONFIGURED model for its role, not on the agent file's default
    and not on whatever the orchestrator remembered: when tiers.<tier>.roles.<role> (0.6) or
    roles.<role> is set, the Agent call must carry exactly that `model` parameter."""
    role = next((r for name, r in ROLE_OF.items() if name in sub), None)
    if role is None:
        return
    cfg = read_config(root)
    roles = cfg.get("roles", {}) if isinstance(cfg.get("roles", {}), dict) else {}
    tiers = cfg.get("tiers", {}) if isinstance(cfg.get("tiers", {}), dict) else {}
    want, where = None, f"roles.{role}"
    troles = (tiers.get(tier) or {}).get("roles") if tier and isinstance(tiers.get(tier), dict) else None
    if isinstance(troles, dict) and troles.get(role):
        want, where = str(troles[role]).strip(), f"tiers.{tier}.roles.{role}"
    elif roles.get(role):
        want = str(roles[role]).strip()
    if not want:
        return
    if want.lower() == "none":
        deny(f"{sub} is not dispatched for tier {tier}: {where} is 'none' (the deterministic check alone stamps)")
    got = str(tool_input.get("model") or "").strip()
    if got != want:
        deny(f"{sub} must run on {where} = {want!r} (.reef/config.json); the Agent call "
             f"passed model={got or 'none'!r} — pass model={want!r}")


def write_marker(root, sub, kind, payload):
    """Machine state the loop and the lock read: .reef/inflight/<id> (an allowed implementer dispatch) and
    .reef/verifying/<id> (an allowed verifier/hunter dispatch). Removed by /reef-task on the hand-back."""
    d = os.path.join(root, ".reef", kind)
    try:
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, str(payload["id"])), "w", encoding="utf-8") as f:
            json.dump(dict(payload, agent=sub, at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())), f)
    except OSError as e:
        deny(f"cannot record the dispatch under {d}: {e}")


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
    prompt = str(tool_input.get("prompt") or "")
    tier, troot = dispatch_tier(prompt, cwd)
    check_role_model(sub, tool_input, troot if tier else cwd, tier)
    if "implementer" not in sub:
        if tier and any(t in sub for t in ("verifier", "loophole-hunter")):
            m = re.search(r"^REEF-TASK:[ \t]*(.+?)[ \t\r]*$", prompt, re.M)
            if not m:
                # 2026-10-18: a hunter plan pass sent with REEF-FEATURE: only crashed here and read as "guard internal error"
                deny(f"{sub} dispatch without a 'REEF-TASK: <task-file>' first line — a judge is dispatched per task, the hunter's "
                     "PLAN pass included (one task file per pass; its report's RUN line names pass=plan); the guard resolves the tier, "
                     "the model and the verifying marker from that line")
            path = m.group(1) if os.path.isabs(m.group(1)) else os.path.join(cwd, m.group(1))
            fm, _ = read_frontmatter(path)
            # a hunter on a task no implementer has started is the PLAN pass: it reads plan files, there is no tree to
            # lock, and a failed pass is never recorded — its marker showed `in flight: verifying:<id>` until it went
            # stale (2026-10-21, qassimha row 12: 1202 and 1204)
            if "loophole-hunter" in sub and str(fm.get("status") or "pending").strip() == "pending":
                return
            write_marker(troot, sub, "verifying", {"id": fm.get("id", "?"), "task": os.path.abspath(path), "tier": tier})
        return
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
    if os.path.abspath(root) != os.path.abspath(cwd) and not tier:
        check_role_model(sub, tool_input, root)
    try:
        pre_fm, _ = read_frontmatter(path)
    except Exception:
        pre_fm = None   # re-read under the lock below, which fails closed
    check_stamp(root, (pre_fm or {}).get("feature", ""))
    graph = load_graph_module()
    lock_dir = graph.lock_key(root, graph.read_config(root))   # 0.6: one graph across every feature folder
    # ONE lock over the whole task set: the ready decision reads every task file, so
    # two dispatches racing for the last parallel slot or the last resource slot must
    # serialise here — the per-file lock below protects only this file's counters.
    with open(graph.graph_lock_path(lock_dir), "a") as glock, open(lock_path_for(path), "a") as lock:
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
        check_adversarial_plan(path, fm, text)
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
        write_marker(root, sub, "inflight", {"id": fm.get("id", "?"), "task": os.path.abspath(path),
                                             "feature": fm.get("feature", ""), "tier": task_tier(fm)})


# ---------------- 0.6: the guard guards itself (Edit/Write/MultiEdit) ----------------

def main_checkout(cwd):
    """The main checkout (first `git worktree list --porcelain` entry); machine state lives there."""
    try:
        r = subprocess.run(["git", "-C", cwd, "worktree", "list", "--porcelain"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            if line.startswith("worktree "):
                return line[len("worktree "):].strip()
    except Exception:
        pass
    return task_root(os.path.join(cwd, "x"), cwd)


def context_for(payload):
    """Facts the Bash and Edit checks share, computed once per hook call."""
    cwd = payload.get("cwd") or os.getcwd()
    roots = {main_checkout(cwd), task_root(os.path.join(cwd, "x"), cwd)}
    plugin = os.environ.get("CLAUDE_PLUGIN_ROOT") or ""
    plugin_root = bool(plugin) and os.path.realpath(cwd).startswith(os.path.realpath(plugin))
    critical = False
    verifying = False
    for root in roots:
        d = os.path.join(root, ".reef", "inflight")
        for f in (os.listdir(d) if os.path.isdir(d) else []):
            try:
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    critical = critical or json.load(fh).get("tier") == "critical"
            except Exception:
                continue
        v = os.path.join(root, ".reef", "verifying")
        verifying = verifying or (os.path.isdir(v) and bool(os.listdir(v)))
    return {"cwd": cwd, "roots": roots, "plugin_root": plugin_root, "critical_inflight": critical,
            "agent_type": str(payload.get("agent_type") or ""),
            "main_session": not payload.get("agent_id") and not payload.get("agent_type"),
            "typeless_locked": bool(payload.get("agent_id")) and not payload.get("agent_type") and verifying}


def check_edit(tool_input, payload, ctx):
    path = str(tool_input.get("file_path") or "")
    if not path:
        return
    rel = os.path.relpath(path, ctx["cwd"]) if os.path.isabs(path) else path
    if RECORD_DIRS.search(path) or RECORD_DIRS.search(rel):
        deny("editing under .reef/approvals/ or .reef/review/ — these records are written by the AskUserQuestion "
             "hook and scripts/reef-record, bound to a digest or a forge SHA; a hand-written one is an approval nobody gave")
    if ctx.get("main_session") and (EVIDENCE.search(path) or EVIDENCE.search(rel)):
        deny(EVIDENCE_DENIAL.format(path=rel))
    if not (GUARD_FILES.search(path) or GUARD_FILES.search(rel)):
        return
    if ctx["plugin_root"] or ctx["critical_inflight"]:
        return
    if os.path.basename(path) == "config.json":
        try:
            with open(path, encoding="utf-8") as f:
                before = json.load(f)
        except Exception:
            before = {}
        after_text = None
        if "content" in tool_input:
            after_text = str(tool_input.get("content") or "")
        else:
            try:
                with open(path, encoding="utf-8") as f:
                    cur = f.read()
            except OSError:
                cur = ""
            edits = tool_input.get("edits") or [{"old_string": tool_input.get("old_string", ""), "new_string": tool_input.get("new_string", "")}]
            for e in edits:
                cur = cur.replace(str(e.get("old_string", "")), str(e.get("new_string", "")))
            after_text = cur
        try:
            after = json.loads(after_text)
        except Exception:
            deny(".reef/config.json edit does not parse as JSON — refusing a write that could blank the gates")
        changed = [k for k in PROTECTED_KEYS if before.get(k) != after.get(k)]
        if not changed:
            return
        deny(f".reef/config.json keys {changed} change only under a tier: critical task (none is in flight) or inside "
             "Reef's own repository — plan it as a critical task")
    deny(f"{rel}: the guard's own files (scripts/reef-*, .githooks/*, hooks/hooks.json) change only under a tier: critical "
         "task (none is in flight) or inside Reef's own repository — plan it as a critical task; a proposed script is "
         "taken with python3 scripts/reef-init.py --accept <path>")


# ---------------- 0.6: the Stop hook (5.2) and the context ceiling (5.4) ----------------

def check_stop(payload):
    """Stop: refuse the turn's end only when the loop is active, no wait is recorded, ready tasks exist with free
    slots, nothing is in flight and no stop reason holds — and never twice for the same tick state
    (reef-loop.py tick --assert-no-idle keeps the refused hash). stop_hook_active is honoured."""
    if payload.get("stop_hook_active"):
        return
    cwd = payload.get("cwd") or os.getcwd()
    root = main_checkout(cwd)
    loop = os.path.join(root, "scripts", "reef-loop.py")
    st_path = os.path.join(root, ".reef", "loop.json")
    if not os.path.isfile(loop) or not os.path.isfile(st_path):
        return
    # the status line is the owner's one-line answer to "what now?": while the loop is active every reply ends with
    # `in flight: … / waiting on: … / next: <command>` (first full loop, 2026-10-17: the owner asked "what do I run
    # now?" after every stop). Refused once per message, so a reply that cannot comply is not trapped.
    msg = str(payload.get("last_assistant_message") or "")
    try:
        st = json.load(open(st_path))
    except Exception:
        st = {}
    if st.get("active") and msg.strip() and not STATUS_LINE.search(msg):
        key = hashlib.sha1(msg.encode("utf-8", "replace")).hexdigest()[:12]
        if st.get("status_refused") != key:
            st["status_refused"] = key
            try:
                with open(st_path, "w", encoding="utf-8") as f:
                    json.dump(st, f, indent=1)
            except Exception:
                pass
            deny("end the reply with the status line, on its own last line: `in flight: <ids or ->` / `waiting on: <what or ->` / "
                 "`next: <the one command the owner runs, from the tick's next command:>`")
    tp = payload.get("transcript_path")
    if st.get("active") and tp and os.path.isfile(tp):
        # the cost record: this session's per-task growth into .reef/cost/tasks.json, read by the close-out and the tick
        cost = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reef-cost.py")
        try:
            subprocess.run([sys.executable, cost, tp, "--record", "--repo", root], capture_output=True, text=True, timeout=8)
        except Exception:
            pass
    if payload.get("background_tasks"):
        return   # sub-agents still running: the world is in flight
    try:
        r = subprocess.run([sys.executable, loop, "tick", "--assert-no-idle", "--repo", root], capture_output=True, text=True, timeout=DEADLINE - 1)
    except subprocess.TimeoutExpired:
        return   # a slow tick never blocks the turn's end
    if r.returncode == 2:
        deny("the loop is active and ready work sits undispatched: " + r.stderr.strip().splitlines()[-1][:300] + "\n" + r.stdout[-600:])


def checkpoint(root, tp, stop):
    """loop.json stop + HANDOFF.md rendered from measured state, before a denial that ends the session."""
    try:
        st_p = os.path.join(root, ".reef", "loop.json")
        st = json.load(open(st_p)) if os.path.isfile(st_p) else {}
        st["stop"] = stop
        st["transcript"] = tp
        os.makedirs(os.path.dirname(st_p), exist_ok=True)
        with open(st_p, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=1)
    except Exception:
        pass
    # 0.7: the checkpoint itself is the guard's, not the model's — HANDOFF.md is rendered from measured state here,
    # before the denial, so a session cut at the ceiling never leaves the next one without a handoff
    for script in (os.path.join(root, "scripts", "reef-handoff"),
                   os.path.join(os.path.dirname(os.path.abspath(__file__)), "reef-handoff")):
        if os.path.isfile(script):
            try:
                subprocess.run([sys.executable, script, "--repo", root, "--write"], capture_output=True, text=True, timeout=20)
            except Exception:
                pass
            break


def check_context_ceiling(payload, tool_input=None):
    """Task/Agent dispatch: the dispatching session's live context (reef-cost.py --live on transcript_path) against
    caps.context_tokens (0 = off); from caps.context_warn the hook adds a warning as additionalContext. An IMPLEMENTER
    dispatch (a new task starting) is refused already when the room left is under caps.dispatch_reserve: a task
    started at 126k of 150k (first contact, 2026-10-16) is split across two sessions — its judges cannot be dispatched
    in the one that started it. Judges and mechanics stay allowed up to the ceiling: they finish the task in hand."""
    tp = payload.get("transcript_path")
    cwd = payload.get("cwd") or os.getcwd()
    cfg = read_config(main_checkout(cwd)) or read_config(cwd)
    caps = cfg.get("caps") or {}
    ceiling, warn = int(caps.get("context_tokens", 0) or 0), int(caps.get("context_warn", 0) or 0)
    reserve = int(caps.get("dispatch_reserve", 0) or 0)
    if not (ceiling or warn):
        return
    if not tp or not os.path.isfile(tp):
        print("reef-guard: no transcript_path in the payload — the context ceiling cannot be measured; allowing", file=sys.stderr)
        return
    cost = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reef-cost.py")
    try:
        r = subprocess.run([sys.executable, cost, tp, "--live"], capture_output=True, text=True, timeout=5)
    except subprocess.TimeoutExpired:
        return
    m = re.search(r"context_tokens=(\d+)", r.stdout)
    if not m:
        return
    n = int(m.group(1))
    sub = str((tool_input or {}).get("subagent_type") or "")
    if ceiling and reserve and "implementer" in sub and n <= ceiling and ceiling - n < reserve:
        checkpoint(main_checkout(cwd), tp, f"context ceiling: {n} tokens + caps.dispatch_reserve {reserve} > caps.context_tokens "
                                           f"{ceiling} — a new task was not started; /clear now (HANDOFF.md is written)")
        deny(f"/clear NOW. context reserve: this session is at {n} tokens, {ceiling - n} of room left to caps.context_tokens "
             f"{ceiling} < caps.dispatch_reserve {reserve}. A task started now is split across two sessions (its judges "
             f"cannot be dispatched in this one). Checkpoint done: HANDOFF.md written from measured state, nothing is lost. "
             f"Do nothing else here: tell the human to run /clear and paste `<the command you were running> — re-entry: see "
             f"HANDOFF.md`; the fresh orchestrator dispatches this task whole")
    if ceiling and n > ceiling:
        root = main_checkout(cwd)
        checkpoint(root, tp, f"context ceiling: {n} tokens > caps.context_tokens {ceiling} — /clear now (HANDOFF.md is written)")
        deny(f"/clear NOW. context ceiling: this session is at {n} tokens > caps.context_tokens {ceiling}. "
             f"checkpoint done: HANDOFF.md written from measured state (scripts/reef-handoff --write), nothing is lost. "
             f"Do nothing else in this session — no more Bash, no edits, no summary (the real session kept going 80k past "
             f"the ceiling): tell the human to run /clear and paste `<the command you were running> — re-entry: see HANDOFF.md`; "
             f"the fresh orchestrator resumes there")
    if warn and n > warn:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                                 "additionalContext": f"reef: context at {n} tokens (> caps.context_warn {warn}, ceiling {ceiling or 'unset'}): {max(0, (ceiling or 0) - n)} tokens of room. Finish the step in hand, then stop and /clear BEFORE the ceiling; sub-agent dispatches are refused at it, Bash is not — do not spend the room on reading."}}))


def arm_deadline():
    """A hung guard must deny, not time out into an allow (onFailure: block is the host's belt)."""
    def on_alarm(signum, frame):
        deny(f"guard deadline of {DEADLINE:g}s exceeded — failing closed")
    signal.signal(signal.SIGALRM, on_alarm)
    signal.setitimer(signal.ITIMER_REAL, DEADLINE)


def main():
    arm_deadline()
    if os.environ.get("REEF_GUARD_TEST_HANG"):
        time.sleep(60)   # the red test for the deadline: the alarm must deny before this returns
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    if payload.get("hook_event_name") == "Stop":
        try:
            check_stop(payload)
        except SystemExit:
            raise
        except Exception as e:
            print(f"reef-guard: stop check error ignored (the turn may end): {e}", file=sys.stderr)
        sys.exit(0)
    if tool == "Bash":
        try:
            CTX.update(context_for(payload))
        except Exception as e:
            deny(f"guard internal error reading its context — failing closed: {e}")
        check_bash(str(tool_input.get("command") or ""))
    elif tool in ("Task", "Agent"):
        # the ceiling first: a dispatch denied for room must not have written its inflight/verifying marker
        try:
            check_context_ceiling(payload, tool_input)
        except SystemExit:
            raise
        except Exception as e:
            print(f"reef-guard: context ceiling check error ignored: {e}", file=sys.stderr)
        check_dispatch(tool_input, payload)
    elif tool in ("Edit", "Write", "MultiEdit"):
        try:
            check_edit(tool_input, payload, context_for(payload))
        except SystemExit:
            raise
        except Exception as e:
            deny(f"guard internal error on an edit of a guarded path — failing closed: {e}")
    sys.exit(0)


if __name__ == "__main__":
    main()
