#!/usr/bin/env python3
# CLASS: code
"""Reef setup proof — worktree.setup proven ONCE per change, never by a row's own red (2026-10-28, the current adoption: a
fresh row worktree had no built app, 60 tests went red for reasons unrelated to the row, the orchestrator guessed a build
and the full suite ran twice per row; the design's phase 0 had left "a complete worktree.setup" to the owner's hand).
Usage: reef-setup.py state  [--repo DIR]   proven (exit 0) · unproven (exit 3: run `prove`) · INCOMPLETE (exit 1: edit worktree.setup)
       reef-setup.py prove  [--repo DIR]   a scratch worktree of the base, worktree.setup, then gates.full ONCE; the record
       reef-setup.py digest [--repo DIR]   the digest of worktree.setup, gates.full and every lockfile present
The record is .reef/ci-local/setup-<digest16>.json in the main checkout (ok, base, the failing lines, seconds); its log sits
beside it. The digest changes with the setup command, the full gate or a lockfile — the next row proves it again, once.
The scratch worktree is removed; the gate runs as a plain command, so no evidence and no snapshot cache are written: a
tree that lacks its setup is not a result about the base. The row state machine (reef-row.py) names `prove` before a
build and waits on the owner while INCOMPLETE; reef-graph.py refuses a task worktree on the same terms.
Exit 0 proven · 1 incomplete, or a failed step · 2 usage · 3 unproven.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

LOCKFILES = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "uv.lock", "poetry.lock", "Pipfile.lock",
             "requirements.txt", "Cargo.lock", "go.sum", "Gemfile.lock", "composer.lock")
FAIL_LINE = re.compile(r"(^|\s)(FAIL|FAILED|ERROR|AssertionError|✗|✘|❯|×)(\s|:|$)|\b\d+ (failed|errors?)\b", re.I)


def run(args, cwd, timeout=600):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout} s"
    except OSError as e:
        return 1, str(e)


def main_checkout(repo):
    rc, out = run(["git", "worktree", "list", "--porcelain"], repo, 30)
    for line in out.splitlines():
        if line.startswith("worktree "):
            return line[len("worktree "):].strip()
    return os.path.abspath(repo)


def parts(cfg):
    setup = str((cfg.get("worktree") or {}).get("setup", "") or "").strip()
    gates = cfg.get("gates") if isinstance(cfg.get("gates"), dict) else {}
    return setup, str(gates.get("full") or gates.get("test") or "").strip()


def digest(main, cfg):
    setup, full = parts(cfg)
    h = hashlib.sha256(f"setup={setup}\nfull={full}\n".encode())
    for name in LOCKFILES:
        p = os.path.join(main, name)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                h.update(f"{name}={hashlib.sha256(f.read()).hexdigest()}\n".encode())
    return h.hexdigest()[:16]


def record_path(main, dg):
    return os.path.join(main, ".reef", "ci-local", f"setup-{dg}.json")


def cmd_state(main, cfg):
    dg = digest(main, cfg)
    try:
        with open(record_path(main, dg), encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        print(f"setup: unproven ({dg}) — python3 scripts/reef-setup.py prove   (worktree.setup, gates.full or a lockfile changed, or never proven)")
        return 3
    if rec.get("ok"):
        print(f"setup: proven ({dg}) at {str(rec.get('base', ''))[:12]} in {rec.get('seconds', '?')} s — worktree.setup makes a tree the full gate passes")
        return 0
    fails = "; ".join(str(x)[:100] for x in (rec.get("failing") or [])[:3]) or "see the log beside the record"
    step = "worktree.setup exited" if rec.get("step") == "setup" else "the full gate exited"
    print(f"setup: INCOMPLETE ({dg}) — on an untouched worktree of {str(rec.get('base', ''))[:12]} {step} {rec.get('exit')}: {fails} "
          "— edit .reef/config.json worktree.setup (what the gate needs on a fresh tree), then python3 scripts/reef-setup.py prove")
    return 1


def write_record(main, dg, rec, log_text):
    os.makedirs(os.path.join(main, ".reef", "ci-local"), exist_ok=True)
    with open(record_path(main, dg), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
        f.write("\n")
    with open(record_path(main, dg)[:-5] + ".log", "w", encoding="utf-8") as f:
        f.write(log_text)


def cmd_prove(main, cfg):
    dg = digest(main, cfg)
    setup, full = parts(cfg)
    if not full:
        print("setup: gates.full is empty — nothing can prove a setup; set the full gate first")
        return 1
    base = str((cfg.get("branches") or {}).get("base", "main") or "main")
    rc, _ = run(["git", "rev-parse", "-q", "--verify", f"refs/remotes/origin/{base}"], main, 30)
    ref = f"origin/{base}" if rc == 0 else base
    rc, sha = run(["git", "rev-parse", "-q", "--verify", ref + "^{commit}"], main, 30)
    if rc != 0:
        print(f"setup: the base {ref!r} is not a commit in {main}")
        return 1
    sha = sha.strip()
    wt_dir = str((cfg.get("worktree") or {}).get("dir", ".reef/worktrees") or ".reef/worktrees")
    wt = os.path.join(main, wt_dir, f".setup-{dg}")
    run(["git", "worktree", "remove", "--force", wt], main, 60)
    os.makedirs(os.path.join(main, wt_dir), exist_ok=True)
    rc, out = run(["git", "worktree", "add", "-q", "--detach", wt, sha], main, 120)
    if rc != 0:
        print(f"setup: git worktree add failed: {out.strip()[:200]}")
        return 1
    gates = cfg.get("gates") if isinstance(cfg.get("gates"), dict) else {}
    timeout = int(gates.get("timeout_s", 1200) or 1200)
    t0, at = time.time(), time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        rc_s, out_s = (0, "") if not setup else run(["sh", "-c", setup], wt, max(timeout, 3600))
        if rc_s != 0:
            tail = [l for l in out_s.splitlines() if l.strip()][-5:]
            rec = {"digest16": dg, "base": sha, "ok": False, "step": "setup", "exit": rc_s, "setup": setup, "gate": full,
                   "failing": tail, "seconds": round(time.time() - t0), "at": at}
            write_record(main, dg, rec, out_s)
            print(f"setup: INCOMPLETE ({dg}) — worktree.setup exited {rc_s} on a fresh worktree of {sha[:12]}: {(tail or ['no output'])[-1][:160]}")
            return 1
        rc_g, out_g = run(["sh", "-c", full], wt, timeout)
        lines = [l.rstrip() for l in out_g.splitlines() if l.strip()]
        failing = ([l for l in lines if FAIL_LINE.search(l)] or lines[-5:])[:12] if rc_g != 0 else []
        rec = {"digest16": dg, "base": sha, "ok": rc_g == 0, "step": "gate", "exit": rc_g, "setup": setup, "gate": full,
               "failing": failing, "seconds": round(time.time() - t0), "at": at}
        write_record(main, dg, rec, out_s + out_g)
    finally:
        run(["git", "worktree", "remove", "--force", wt], main, 120)
        run(["git", "worktree", "prune"], main, 30)
    if rc_g == 0:
        print(f"setup: proven ({dg}) at {sha[:12]} in {rec['seconds']} s — worktree.setup makes a tree the full gate passes -> .reef/ci-local/setup-{dg}.json")
        return 0
    print(f"setup: INCOMPLETE ({dg}) — on an untouched worktree of {sha[:12]} the full gate exited {rc_g} ({len(failing)} failing line(s) kept): "
          f"{(failing or ['no output'])[0][:160]} — edit .reef/config.json worktree.setup, then python3 scripts/reef-setup.py prove")
    return 1


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default
    cmd = argv[0] if argv and not argv[0].startswith("-") else ""
    if cmd not in ("state", "prove", "digest"):
        print(__doc__.strip().splitlines()[3].strip(), file=sys.stderr)
        return 2
    main_co = main_checkout(os.path.abspath(opt("--repo", ".")))
    try:
        with open(os.path.join(main_co, ".reef", "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        print(f"reef-setup: {main_co} is not a Reef project (no .reef/config.json)", file=sys.stderr)
        return 1
    if cmd == "digest":
        print(digest(main_co, cfg))
        return 0
    return cmd_state(main_co, cfg) if cmd == "state" else cmd_prove(main_co, cfg)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
