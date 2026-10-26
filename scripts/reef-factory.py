#!/usr/bin/env python3
# CLASS: code
"""Reef factory — one row built in the Actions sandbox (workflow v3, phase 7): the ONE command the offered workflow runs, so
the YAML is checkout + install + this, and every decision below is under the suite.
Usage: reef-factory.py row (--issue <#n> | --row <id>) [--actor <login>] [--max-iterations 4] [--permission-mode auto] [--repo DIR]
In order, each refusal printed and the job ended before the model runs:
  1. the row: the issue's `[id]` title (reef-queue.py issue-row) or the given id (digits only);
  2. who asked: the actor (the labeler or dispatcher) and the issue's author must both have ADMIN permission on the repository
     — a triage collaborator can label an issue, and the issue's body is the planner's spec (the review, 2026-10-27);
  3. the base branch must be protected (`branches/<base>/protection` answers): the loop merges only under branch protection;
  4. resume: every `origin/<feature_prefix>*` branch without a worktree gets one under worktree.dir — the plan and the work
     of the last job live on the forge, never only on a runner;
  5. the probe (reef-run.py probe) must say GATE OK: the guard reaches a headless session here, or nothing runs;
  6. the owner's approval from the issue (reef-approval.py --from-issue; nothing to approve is not a failure);
  7. the build (reef-run.py --row <id>): exit 2 waits on the owner, 3 parked, 4 the cap — the labels say which; 1 is a refusal;
  8. every local feature branch pushed (the next job resumes from it); 9. the row's state as its label (reef-queue.py label-state).
Exit 0 built or waiting · 1 a refusal or a failed step · 2 usage.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(args, cwd, timeout=7200, env=None):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
        return r.returncode, r.stdout, r.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)


def say(line):
    print(f"reef-factory: {line}", flush=True)


def main_checkout(repo):
    rc, out, _ = run(["git", "-C", repo, "worktree", "list", "--porcelain"], repo, timeout=30)
    for line in out.splitlines():
        if line.startswith("worktree "):
            return line[len("worktree "):].strip()
    return repo


def script(name):
    return os.path.join(HERE, name)


def permission(root, login):
    rc, out, _ = run(["gh", "api", f"repos/{{owner}}/{{repo}}/collaborators/{login}/permission"], root, timeout=60)
    try:
        return str(json.loads(out).get("permission") or "") if rc == 0 and out.strip() else ""
    except ValueError:
        return ""


def cmd_row(root, cfg, issue, row, actor, cap, mode):
    if (cfg.get("queue") or {}).get("home") != "issues":
        say("the factory builds rows that are issues (queue.home: issues) — reef-queue.py migrate-to-issues first")
        return 1
    base = str((cfg.get("branches") or {}).get("base", "main") or "main")
    prefix = str((cfg.get("branches") or {}).get("feature_prefix", "feat/") or "feat/")
    wt_dir = str((cfg.get("worktree") or {}).get("dir", ".reef/worktrees") or ".reef/worktrees")
    # 1. the row
    if issue:
        rc, out, err = run([sys.executable, script("reef-queue.py"), "issue-row", issue, "--repo", root], root, timeout=120)
        if rc != 0:
            say(f"issue #{issue} is not a row — {(err or out).strip().splitlines()[-1][:160] if (err or out).strip() else rc}; nothing built")
            return 1
        row = out.strip().splitlines()[-1].strip()
    if not row or not row.isdigit():
        say("a row id is digits")
        return 2
    rc, out, _ = run([sys.executable, script("reef-queue.py"), "row-issue", row, "--repo", root], root, timeout=120)
    issue = out.strip().splitlines()[-1].strip() if rc == 0 and out.strip() else ""
    # 2. who asked
    rc, out, _ = run(["gh", "issue", "view", issue, "--json", "author"], root, timeout=60) if issue else (1, "", "")
    try:
        author = str((json.loads(out).get("author") or {}).get("login") or "") if rc == 0 and out.strip() else ""
    except ValueError:
        author = ""
    for who, role in ((actor, "the actor"), (author, "the issue's author")):
        if not who:
            say(f"{role} is unknown — nothing built (pass --actor; the issue must be a row)")
            return 1
        perm = permission(root, who)
        if perm != "admin":
            say(f"{role} @{who} has {perm or 'no'} permission on the repository, not admin — nothing built: only the owner starts the factory")
            return 1
    # 3. branch protection
    rc, out, err = run(["gh", "api", f"repos/{{owner}}/{{repo}}/branches/{base}/protection"], root, timeout=60)
    if rc != 0:
        say(f"{base} is not a protected branch ({(err or out).strip().splitlines()[-1][:120] if (err or out).strip() else rc}) — the loop merges only under branch protection; nothing built")
        return 1
    # 4. resume
    run(["git", "fetch", "-q", "origin"], root, timeout=600)
    rc, out, _ = run(["git", "for-each-ref", "--format=%(refname:short)", f"refs/remotes/origin/{prefix}"], root, timeout=30)
    rc2, local, _ = run(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/"], root, timeout=30)
    have = set(local.split())
    for ref in out.split():
        branch = ref[len("origin/"):]
        if branch in have:
            continue
        slug = branch[len(prefix):]
        wt = os.path.join(root, wt_dir, slug)
        rc, _, err = run(["git", "worktree", "add", "-q", "--track", "-b", branch, wt, ref], root, timeout=120)
        say(f"resumed {branch} in {os.path.relpath(wt, root)}" if rc == 0 else f"could not resume {branch}: {err.strip()[:160]}")
    # 5. the probe
    rc, out, err = run([sys.executable, script("reef-run.py"), "probe", "--permission-mode", mode, "--repo", root], root, timeout=1800)
    if rc != 0 or "GATE OK" not in out:
        say(f"the guard does not reach a headless session here — nothing runs: {(out or err).strip().splitlines()[-1][:200] if (out or err).strip() else rc}")
        return 1
    # 6. the approval from the issue
    rc, out, err = run([sys.executable, script("reef-approval.py"), "--from-issue", row], root, timeout=120)
    say((out or err).strip().splitlines()[-1][:200] if (out or err).strip() else f"approval step exit {rc}")
    # 7. the build
    rc, out, err = run([sys.executable, script("reef-run.py"), "--row", row, "--max-iterations", str(cap), "--permission-mode", mode, "--repo", root],
                       root, timeout=6 * 3600)
    for line in (out or "").strip().splitlines()[-6:]:
        print(line)
    built = rc != 1
    if not built:
        say(f"the runner refused: {(err or out).strip().splitlines()[-1][:200] if (err or out).strip() else rc}")
    # 8. the branches to the forge
    rc2, local, _ = run(["git", "for-each-ref", "--format=%(refname:short)", f"refs/heads/{prefix}"], root, timeout=30)
    for branch in local.split():
        rc3, _, err = run(["git", "push", "-q", "origin", branch], root, timeout=600)
        say(f"pushed {branch}" if rc3 == 0 else f"push {branch} failed: {err.strip()[:160]}")
    # 9. the label
    rc4, out, err = run([sys.executable, script("reef-queue.py"), "label-state", row, "--repo", root], root, timeout=120)
    say((out or err).strip().splitlines()[-1][:200] if (out or err).strip() else f"label-state exit {rc4}")
    return 0 if built else 1


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default
    if not argv or argv[0] != "row":
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    root = main_checkout(os.path.abspath(opt("--repo", ".")))
    try:
        with open(os.path.join(root, ".reef", "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        print(f"reef-factory: {root} is not a Reef project (no .reef/config.json)", file=sys.stderr)
        return 1
    issue, row = str(opt("--issue", "") or "").lstrip("#"), str(opt("--row", "") or "")
    if not issue and not row:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    if (issue and not issue.isdigit()) or (row and not row.isdigit()):
        say("--issue and --row take digits")
        return 2
    return cmd_row(root, cfg, issue, row, str(opt("--actor", "") or ""), int(opt("--max-iterations", "4")), str(opt("--permission-mode", "auto")))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
