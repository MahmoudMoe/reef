#!/usr/bin/env python3
# CLASS: code
"""Reef setup proof — worktree.setup proven ONCE per change, never by a row's own red (2026-10-28, the current adoption: a
fresh row worktree had no built app, 60 tests went red for reasons unrelated to the row, the orchestrator guessed a build
and the full suite ran twice per row; the design's phase 0 had left "a complete worktree.setup" to the owner's hand).
Usage: reef-setup.py state  [--repo DIR]      proven (exit 0) · unproven (exit 3: run `prove`) · INCOMPLETE (exit 1: edit worktree.setup)
       reef-setup.py prove  [--repo DIR]      a scratch worktree of the base, worktree.setup, then gates.full ONCE; the record
       reef-setup.py apply  [WT] [--repo DIR] run the PROVEN setup in a worktree (default: this one), once per digest — the marker
                                              <WT>/.reef/ci-local/setup.digest; the same digest again is a no-op
       reef-setup.py digest [--repo DIR]      the digest of worktree.setup, gates.full, the manifests and every lockfile present
The record is .reef/ci-local/setup-<digest16>.json in the main checkout (ok, base, the failing lines, seconds); its log sits
beside it; older digests' records are pruned. The digest changes with the setup command, the full gate, a manifest
(package.json, pyproject.toml, …) or a lockfile — the next row proves it again, once. The scratch worktree is removed; the
gate runs as a plain command, so no evidence and no snapshot cache are written (a gates.full that names reef-gate.sh is
refused: that script writes the base's evidence): a tree that lacks its setup is not a result about the base. The row
state machine (reef-row.py) names `prove` before /reef-plan makes the row's worktree and before a build, names `apply` for
a worktree set up under an older digest, and waits on the owner while INCOMPLETE; reef-graph.py refuses a task worktree
on the same terms and sets a new one up through `apply`. The guard keeps the worktree keys the owner's (an agent cannot
edit the command this script runs) and refuses prove/apply to a read-only judge.
Exit 0 proven or applied · 1 incomplete, or a failed step · 2 usage · 3 unproven.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # the shared helpers live beside this script
from reef_common import main_checkout, run as _run  # noqa: E402

CHANGE_SET = ("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "pyproject.toml", "uv.lock",
              "poetry.lock", "Pipfile", "Pipfile.lock", "requirements.txt", "Cargo.toml", "Cargo.lock", "go.mod", "go.sum",
              "Gemfile", "Gemfile.lock", "composer.json", "composer.lock")   # the manifests: a changed build script is a changed setup
FAIL_MARK = re.compile(r"^\s*(?:\x1b\[[0-9;]*m)*\s*(FAIL\b|AssertionError\b|✗|✘|❯|×)")   # a runner's own marker opens the line
FAIL_LINE = re.compile(r"(^|\s)(FAIL|FAILED|ERROR|AssertionError|✗|✘|❯|×)(\s|:|$)|\b\d+ (failed|errors?)\b", re.I)   # a sentence with the word


def run(args, cwd, timeout=600):
    r = _run(args, cwd, timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def parts(cfg):
    setup = str((cfg.get("worktree") or {}).get("setup", "") or "").strip()
    gates = cfg.get("gates") if isinstance(cfg.get("gates"), dict) else {}
    return setup, str(gates.get("full") or gates.get("test") or "").strip()


def digest(main, cfg):
    setup, full = parts(cfg)
    h = hashlib.sha256(f"setup={setup}\nfull={full}\n".encode())
    for name in CHANGE_SET:
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
    fails = "; ".join(str(x)[:100] for x in (rec.get("failing") or [])[:3]) or "see the log"
    step = "worktree.setup exited" if rec.get("step") == "setup" else "the full gate exited"
    print(f"setup: INCOMPLETE ({dg}) — on an untouched worktree of {str(rec.get('base', ''))[:12]} {step} {rec.get('exit')}: {fails} "
          f"(log: .reef/ci-local/setup-{dg}.log) — edit .reef/config.json worktree.setup (what the gate needs on a fresh tree), "
          "then python3 scripts/reef-setup.py prove")
    return 1


def write_record(main, dg, rec, log_text):
    os.makedirs(os.path.join(main, ".reef", "ci-local"), exist_ok=True)
    for old in os.listdir(os.path.join(main, ".reef", "ci-local")):   # one digest speaks; the rest are pruned
        if old.startswith("setup-") and old[6:22] != dg and (old.endswith(".json") or old.endswith(".log")):
            try:
                os.unlink(os.path.join(main, ".reef", "ci-local", old))
            except OSError:
                pass
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
    if re.search(r"reef-gate(\.sh)?\b", full):
        print("setup: gates.full names reef-gate.sh — that script resolves gates.full itself and writes the base's evidence; the proof runs the suite's own command: set gates.full to it")
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
    shutil.rmtree(wt, ignore_errors=True)   # a leftover folder git does not know would refuse the add forever
    run(["git", "worktree", "prune"], main, 30)
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
        # the first proof on the current adoption (2026-10-28) quoted "the closing write failed with …" from a library's stderr while the
        # real FAIL lines sat below: a marker that opens the line comes first, a sentence with the word after
        failing = ([l for l in lines if FAIL_MARK.search(l)] + [l for l in lines if FAIL_LINE.search(l) and not FAIL_MARK.search(l)] or lines[-5:])[:12] if rc_g != 0 else []
        rec = {"digest16": dg, "base": sha, "ok": rc_g == 0, "step": "gate", "exit": rc_g, "setup": setup, "gate": full,
               "failing": failing, "seconds": round(time.time() - t0), "at": at}
        write_record(main, dg, rec, out_s + out_g)
    finally:
        run(["git", "worktree", "remove", "--force", wt], main, 120)
        shutil.rmtree(wt, ignore_errors=True)
        run(["git", "worktree", "prune"], main, 30)
    if rc_g == 0:
        print(f"setup: proven ({dg}) at {sha[:12]} in {rec['seconds']} s — worktree.setup makes a tree the full gate passes -> .reef/ci-local/setup-{dg}.json")
        return 0
    print(f"setup: INCOMPLETE ({dg}) — on an untouched worktree of {sha[:12]} the full gate exited {rc_g} ({len(failing)} failing line(s) kept): "
          f"{(failing or ['no output'])[0][:160]} (log: .reef/ci-local/setup-{dg}.log) — edit .reef/config.json worktree.setup, then python3 scripts/reef-setup.py prove")
    return 1


def cmd_apply(main, cfg, wt):
    """The proven setup in ONE worktree, once per digest: the marker <wt>/.reef/ci-local/setup.digest says which digest set it up."""
    rc = cmd_state(main, cfg)
    if rc != 0:
        return rc
    dg = digest(main, cfg)
    setup, _ = parts(cfg)
    rc, top = run(["git", "rev-parse", "--show-toplevel"], wt, 30)
    if rc != 0:
        print(f"setup: {wt} is not a worktree")
        return 1
    wt = top.strip()
    marker = os.path.join(wt, ".reef", "ci-local", "setup.digest")
    try:
        with open(marker, encoding="utf-8") as f:
            if f.read().strip() == dg:
                print(f"setup: applied ({dg}) in {os.path.relpath(wt, main)} — unchanged, nothing run")
                return 0
    except OSError:
        pass
    t0 = time.time()
    gates = cfg.get("gates") if isinstance(cfg.get("gates"), dict) else {}
    rc_s, out_s = (0, "") if not setup else run(["sh", "-c", setup], wt, max(int(gates.get("timeout_s", 1200) or 1200), 3600))
    if rc_s != 0:
        print(f"setup: worktree.setup exited {rc_s} in {os.path.relpath(wt, main)}: {([l for l in out_s.splitlines() if l.strip()] or ['no output'])[-1][:160]}")
        return 1
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    with open(marker, "w", encoding="utf-8") as f:
        f.write(dg + "\n")
    print(f"setup: applied ({dg}) in {os.path.relpath(wt, main)} in {round(time.time() - t0)} s")
    return 0


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default
    cmd = argv[0] if argv and not argv[0].startswith("-") else ""
    if cmd not in ("state", "prove", "apply", "digest"):
        print("\n".join(l.strip() for l in __doc__.strip().splitlines()[3:8]), file=sys.stderr)
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
    if cmd == "apply":
        rest = [a for i, a in enumerate(argv[1:]) if not a.startswith("-") and (i == 0 or argv[i] != "--repo")]
        return cmd_apply(main_co, cfg, os.path.abspath(rest[0]) if rest else os.getcwd())
    return cmd_state(main_co, cfg) if cmd == "state" else cmd_prove(main_co, cfg)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
