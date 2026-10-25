#!/usr/bin/env python3
# CLASS: code
"""Reef evidence — the suite's one result for a commit, READ, never made (workflow v3, phase 2).
Usage: reef-evidence.py [<commit>] [--repo DIR] [--format text|json]        (default: HEAD of this checkout)
Order: with ci.feature_gate = ci and gh reaching the forge, the commit's check-runs are the evidence (a machine the author
cannot touch); else the gate's own record, .reef/evidence/<snapshot>.json in the MAIN checkout, written only by
`scripts/reef-gate.sh full` (the guard denies every other writer) — found by this checkout's live snapshot when the
commit is HEAD, else by the snapshot a clean checkout at that commit has (HEAD + its tree + its tree).
Exit 0 green · 1 red · 3 pending (CI still running) · 2 none (run `sh scripts/reef-gate.sh full`, or wait for CI).
Text: ONE line starting `evidence:` carrying `exit 0` or `exit 1`, fit for a report's `GATE:` line as it stands.
"""
import json
import os
import shutil
import subprocess
import sys

GH_TIMEOUT = float(os.environ.get("REEF_GH_TIMEOUT", "20"))
RED = {"failure", "cancelled", "timed_out", "action_required", "startup_failure", "stale"}


def git(repo, *a):
    r = subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def main_checkout(repo):
    for line in git(repo, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            return line[len("worktree "):].strip()
    return repo


def config(root):
    try:
        with open(os.path.join(root, ".reef", "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def clean_snapshot(repo, sha):
    """What scripts/reef-snapshot.sh prints in a clean checkout at `sha`: HEAD, the index's tree, the worktree's tree."""
    tree = git(repo, "rev-parse", sha + "^{tree}")
    if not tree:
        return ""
    r = subprocess.run(["git", "-C", repo, "hash-object", "--stdin"], input=f"{sha}\n{tree}\n{tree}\n", capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def live_snapshot(repo):
    p = os.path.join(repo, "scripts", "reef-snapshot.sh")
    if not os.path.isfile(p):
        return ""
    r = subprocess.run(["sh", p], cwd=repo, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def ci_checks(repo, sha):
    """The commit's check-runs from the forge, or None when gh cannot answer (no gh, no remote, an error)."""
    if not shutil.which("gh") or not git(repo, "remote"):
        return None
    try:
        r = subprocess.run(["gh", "api", f"repos/{{owner}}/{{repo}}/commits/{sha}/check-runs"], cwd=repo,
                           capture_output=True, text=True, timeout=GH_TIMEOUT)
        runs = json.loads(r.stdout).get("check_runs") if r.returncode == 0 else None
    except Exception:
        return None
    return [{"name": c.get("name"), "status": c.get("status"), "conclusion": c.get("conclusion")} for c in runs] if isinstance(runs, list) else None


def local_record(main, snapshots):
    for snap in snapshots:
        p = os.path.join(main, ".reef", "evidence", f"{snap}.json")
        try:
            with open(p, encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict):
            rec["path"] = os.path.relpath(p, main)
            return rec
    return None


def evidence(repo, commit=None):
    root = git(repo, "rev-parse", "--show-toplevel") or os.path.abspath(repo)
    main = main_checkout(root)
    cfg = config(main)
    sha = git(root, "rev-parse", "--verify", (commit or "HEAD") + "^{commit}")
    if not sha:
        return {"source": "none", "state": "none", "commit": commit, "exit": None, "why": f"no commit {commit!r} in {root}"}
    is_head = sha == git(root, "rev-parse", "HEAD")
    out = {"commit": sha, "source": "none", "state": "none", "exit": None}
    if str((cfg.get("ci") or {}).get("feature_gate", "ci") or "ci") == "ci":
        checks = ci_checks(root, sha)
        if checks:
            out["checks"] = checks
            out["source"] = "ci"
            if any(c["conclusion"] in RED for c in checks):
                out.update(state="red", exit=1)
            elif any(c["status"] != "completed" for c in checks):
                out.update(state="pending", exit=None)
            else:
                out.update(state="green", exit=0)
            return out
    snaps = []
    if is_head or commit is None:
        live = live_snapshot(root)
        if live:
            snaps.append(live)
    clean = clean_snapshot(root, sha)
    if clean and clean not in snaps:
        snaps.append(clean)
    out["snapshot"] = snaps[0] if snaps else None
    rec = local_record(main, snaps)
    if rec is not None:
        out.update(source="local", record=rec, snapshot=rec.get("snapshot"), exit=rec.get("exit"), state="green" if rec.get("exit") == 0 else "red")
    return out


def text(e):
    c12 = (e.get("commit") or "")[:12]
    s12 = (e.get("snapshot") or "")[:12]
    if e["source"] == "ci":
        names = [c["name"] for c in e["checks"]]
        if e["state"] == "green":
            return f"evidence: ci commit {c12} exit 0 — {len(names)} check runs, all green ({', '.join(names)})"
        if e["state"] == "red":
            red = [c["name"] for c in e["checks"] if c["conclusion"] in RED]
            return f"evidence: ci commit {c12} exit 1 — failed: {', '.join(red)}"
        left = sum(1 for c in e["checks"] if c["status"] != "completed")
        return f"evidence: ci commit {c12} pending — {left} of {len(names)} check runs still running"
    if e["source"] == "local":
        r = e["record"]
        counts = ", ".join(f"{v} {k}" for k, v in (r.get("counts") or {}).items()) or (r.get("tail") or ["(no summary line)"])[-1]
        return f"evidence: local snapshot {s12} head {str(r.get('head', ''))[:12]} exit {r.get('exit')} — {counts} at {r.get('at')} ({r.get('path')})"
    return (f"evidence: none for {c12 or e.get('commit')} (snapshot {s12 or '?'}) — {e.get('why') or 'run `sh scripts/reef-gate.sh full` once (it writes .reef/evidence/<snapshot>.json), or wait for CI'}")


def main(argv):
    repo, fmt, commit = ".", "text", None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--repo":
            repo = argv[i + 1]; i += 2
        elif a == "--format":
            fmt = argv[i + 1]; i += 2
        elif a.startswith("-"):
            print(f"reef-evidence: unknown option {a!r} (usage: reef-evidence.py [<commit>] [--repo DIR] [--format text|json])", file=sys.stderr)
            return 2
        else:
            commit = a; i += 1
    e = evidence(os.path.abspath(repo), commit)
    print(json.dumps(e, indent=1) if fmt == "json" else text(e))
    return {"green": 0, "red": 1, "pending": 3}.get(e["state"], 2)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
