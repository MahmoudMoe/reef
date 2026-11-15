# Hardening PR-6 — close two gaps found in review

Two holes, both "a check exists and a path skips it". (1) Without python3 the Edit/Write hook allows every edit (PR-4's
audit, row H3). (2) `reef-merge-close` runs PR-1's round check (red first, `files:`, PR-5's hand-offs) only when the task
worktree is dirty, so a task whose work is already committed on its branch merges unchecked.

## Gap 1 — the hooks without python3

### Today (`hooks/hooks.json` on main, b4df946)

| hook | without python3 | gate? |
|---|---|---|
| PreToolUse `Edit\|Write\|MultiEdit` | `exit 0` — **every edit allowed** (H3) | yes — fails open |
| PreToolUse `Bash` | denies a command matching `no-?verify\|hookspath`, allows everything else (H1) | yes — degraded |
| PreToolUse `Task\|Agent` | denies every dispatch (H2) | yes — fails closed (the pattern) |
| Stop | `exit 0` | S1–S2 are loop-discipline checks; the loop (`reef-loop.py`) cannot run without python3 either |
| PostToolUse `AskUserQuestion` (`reef-approval.py`) | `exit 0`, **nothing recorded, nothing said** | no — a record writer. A missing record fails closed downstream (no approval record = not approved, the tick asks again), but the owner's answer vanishes silently |
| SessionStart | `exit 0` | no |

### What changes

A new POSIX sh script, `scripts/reef-nopython.sh <edit|bash|approval>`, runs only when `command -v python3` fails. The
three hook commands `exec` it in that case instead of `exit 0` / the inline grep. (A script, not inline sh: the logic is
~60 lines and the JSON-escaped one-liner would be unreadable and untestable. `hooks/` keeps only `hooks.json` — decision 10
in `tests/test_contracts.py`.) It reads the hook payload from stdin with `sed` only (no python3, no jq).

**Where is "a Reef project"? (the guard's reach, #368, in sh).** A directory is in a Reef project when it or an ancestor
holds `.reef/config.json`, or it lies in a linked worktree (a `.git` *file*) whose main checkout holds one — the main
checkout read from the `gitdir:` line (`<main>/.git/worktrees/<name>` → `<main>`). Paths are resolved with `cd -P … && pwd -P`
(realpath; macOS `/var` → `/private/var`); a path that does not exist yet is placed by its nearest existing ancestor.

- **edit**: denied when the target (`tool_input.file_path`, relative to the payload's `cwd`) **or** the session (`cwd`,
  else `$PWD`) is in a Reef project. `reef-guard: python3 is required to check an edit in a Reef project — denied (install
  python3 3.9+; `command -v python3` finds none)`. Outside every Reef project: exit 0, as today.
  - the session too, not only the target (more conservative than the guard): the guard's Edit rules also look at the
    session (the implementer's plan-file rule, the queue rule), and a Reef session without python3 cannot run Reef.
  - a `file_path` the sed cannot read plainly (a JSON escape `\` in it) cannot be placed: judged inside — the guard's own
    rule for a word it cannot place.
- **bash** — the decision (flagged D2): **inside a Reef project, deny every command except a fixed allowlist of single,
  plain commands that find or install python3**; outside one, keep today's `no-?verify|hookspath` grep.
  - why not keep the grep: with Edit closed and Bash open, `printf … > scripts/reef-gate.sh`, `rm -rf .reef/approvals`,
    `git commit --no-verify` (any spelling the grep misses) do what the closed Edit hook refuses — a wall with a door.
  - why not deny all: the agent could not even tell the owner what is missing or install it.
  - the allowlist (anchored, whole command; no `; & | < > \` $( )` anywhere, no JSON escape): `command -v python3`,
    `which python3`, `type python3`, `echo $PATH` / `echo "$PATH"`, `uname [-a|-m|-s]`, `cat /etc/os-release`,
    `[sudo] apt-get|apt update`, `[sudo] apt-get|apt install [-y] python3…`, `[sudo] dnf|yum install [-y] python3…`,
    `[sudo] apk add python3…`, `brew install python[@3.x]|python3`, `xcode-select --install`, `uv python install [3.x]`,
    `pyenv install 3.x`. Reason: `reef-guard: python3 is required to check a command in a Reef project — denied; only
    finding or installing python3 runs without it (e.g. command -v python3, brew install python3, sudo apt-get install -y
    python3)`.
  - "inside" for Bash is the session's `cwd` only: a command run from outside a project that writes into one is not
    placed (sh cannot parse its targets). That residual case keeps today's grep. Stated limit.
- **approval** (PostToolUse `AskUserQuestion`) — not a gate, so it still allows (the tool already ran), but it must not be
  silent: inside a Reef project it prints `reef-approval: python3 is missing — this answer was NOT recorded as an approval;
  install python3 and ask again` and exits 2 (a PostToolUse exit 2 shows stderr to Claude). Outside: exit 0. `onFailure`
  stays `continue` (`tests/test_contracts.py` holds it).
- **Stop, SessionStart**: unchanged. Neither refuses a tool call; what they enforce is the loop's, and the loop is python.
- **Task|Agent**: unchanged (already fails closed everywhere — a dispatch needs python3 in any project).

Limits, stated: a host with no `sh` or no `sed` (the hook command itself is `sh -c`); a payload whose `cwd` or
`file_path` holds a JSON escape is judged inside; the Bash allowlist is text, not a parse — it can only be narrower than the
guard, never wider (every other command is denied). PR-4's W-config walls (when `/reef-init` writes them) stay the wall that
holds with no hook at all.

## Gap 2 — the round check on committed work

### Today (`scripts/reef-merge-close` on main)

```
dirty  = the task worktree has uncommitted changes
merged = branch exists and not dirty and branch is an ancestor of HEAD
if not merged:
    if dirty: round_check(wt, task, merge-base(tbranch, HEAD)); stage; commit
    merge --no-ff …
```

A clean worktree on an unmerged branch (a close cut off after the task worktree's commit — e.g. its merge commit refused by
the gate, or killed and recovered by #367's note; or anyone committing in the task worktree) merges with no round check.

### What changes

The round check moves out of `if dirty:` to the top of `if not merged:` — every merge path runs it exactly once per close
run, before anything is staged, committed or merged. Its base stays `merge-base(tbranch, HEAD)`.

Why that is enough, checked against `reef-claims.py round`:
- **changes**: `round_changes` is `git diff --name-only <base>` on the worktree plus untracked files — the worktree is the
  branch tip plus anything uncommitted, so it already reads `base..tip` + uncommitted. No change to `reef-claims.py`.
- **red first**: `cmd_round` writes the base's blob of each changed code file over the worktree file (backup + manifest in
  `<git-dir>/reef-red-<id>/` first), runs the test, and copies the backup back in `finally` (and from the manifest on the next
  run if killed). It never runs `git checkout`, `reset` or `commit`: the branch's commits are untouched, and after the restore
  the worktree is byte-identical to the tip, so a clean tree is clean again. A kill mid-run leaves the tree dirty with the
  manifest; the next close's round check restores it first (as today), then sees the tree clean again.
- **hand-offs**: read `every` (the same list) and `git cat-file -e <base>:<path>` — correct for committed work.

A re-run after a refused merge commit runs the round check again (the commit in the task worktree stands): once per run.

Found while testing: the check's test runs leave their artifacts (`__pycache__/`, a coverage file) in the task worktree. On
the dirty path they are swept into the task commit by `git add -A` unless ignored (as today). On a clean worktree they are
not committed (`dirty` is decided before the check), but if not ignored they make `git worktree remove` refuse after the
merge (`merged but its worktree stays — fix that and re-run`, the existing message). A project ignores its bytecode; not
changed here.

### The fast path (the row's one worktree, no task branch)

The round check runs on every fast close (base `HEAD`), and the close's own commit is the one that moves the task to
`done/`, so a close cut off after its commit is already closed. The hole: the work committed on the feature branch by hand
before the close. Then the diff against `HEAD` is empty — with a named Proof test the red check refuses (the test passes
on `HEAD`), but with no test named, scope and hand-offs pass on nothing. **Decision (flagged D4): the fast path refuses a
round that changed nothing outside the task folder**: `the round changed nothing outside the task folder — the fast path
diffs against HEAD, so work already committed on <branch> cannot be checked; nothing changed`. Exit 2.

## Decisions (flagged for the owner; the most conservative choice is implemented)

- **D1** "in a Reef project" for the no-python3 hooks = the target **or** the session's cwd (the guard looks at the target
  only; the session too is stricter).
- **D2** Bash without python3 in a Reef project: deny all but the python3 find/install allowlist (not keep-the-grep).
- **D3** the approval hook without python3 in a Reef project says the answer was not recorded (exit 2), instead of silence.
- **D4** the fast path refuses an empty round (nothing outside the task folder changed).

## Tests (each red before the change, green after)

`tests/test_hooks.sh`, the hook commands read from `hooks/hooks.json`, `PATH` holding only `sh grep sed cat echo`:
- Edit hook, no python3: target inside a Reef project → exit 2 with `python3 is required to check an edit in a Reef
  project`; target in a linked worktree of one, session outside → exit 2; session inside, target outside → exit 2; both
  outside → exit 0; an unplaceable (escaped) path → exit 2.
- Bash hook, no python3: in a Reef project `ls` → exit 2 (was 0 — the existing "innocent command allowed (degraded)" line
  changes), `command -v python3` and `sudo apt-get install -y python3` → 0, `command -v python3; rm -rf .reef` → 2; outside a
  project `ls` → 0, `git commit --no-verify` → 2.
- approval hook, no python3: in a Reef project → exit 2 with `NOT recorded`; outside → 0.

`tests/test_round_gate.py`, a critical-path close (task worktree on `task/101-add`, real git):
- the round's work committed on the task branch, worktree clean, Proof test passes on the base → exit 2, `does not fail on
  the base`, feature HEAD unchanged, branch unmerged, task worktree still clean and at the same commit.
- the same with a committed file outside `files:` → exit 2, `outside the task's files`.
- the same with an open downstream consuming a path the round never made → exit 2, `missing on the closing tree`.
- the committed work with a red-first test and declared files → closes (exit 0), merged.
- fast path: work committed on the feature branch, Proof names no test → exit 2, `changed nothing outside the task folder`.

## Out of scope

- PR-4's W1–W8 config walls; any change to `reef-guard.py`'s own rules; the Stop/SessionStart hooks; any refactor of
  merge-close or the round check.
