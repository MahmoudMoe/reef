#!/usr/bin/env python3
# CLASS: code
"""Reef run — the outer runner: `/reef-loop` in fresh headless Claude Code sessions, one after another, so the owner is
not the restart button (usability plan B1; the owner's go, 2026-10-20). A session that reaches the context ceiling
writes the handoff and waits `/clear requested`; the runner starts the next one. It stops when the loop waits on the
owner, stops, parks, ends a session with work still in flight, or reaches the iteration cap.

Usage (the owner's terminal, in the project's main checkout):
  reef-run.py probe [--repo DIR] [--permission-mode auto]   once per machine and mode: one headless session tries a
      forbidden write; GATE OK only when reef-guard denied it and no file exists (fail closed — a headless session the
      guard does not reach would be a way around every rule)
  reef-run.py [--repo DIR] [--max-iterations 10] [--permission-mode auto]
Exit: 0 the loop stopped · 2 waiting on the owner (their questions are in .reef/questions.md) · 3 parked, or a session
ended with work in flight · 4 the iteration cap · 1 refused (no probe for this mode, a second runner, not a project).
Files (gitignored): .reef/run/gate.json · .reef/run/run.log (one JSON line per session) · .reef/run/lock.
The lock stops a second RUNNER; it does not stop an interactive /reef-loop beside it — run one orchestrator at a time.
"""
import json
import os
import subprocess
import sys
import time

RUN_DIR = os.path.join(".reef", "run")
PROMPT = ("/reef-loop — a reef-run iteration: headless, AskUserQuestion does not exist here. Keep every row moving that "
          "does not need the owner. Do not ask: append each question for the owner to .reef/questions.md, one line each — "
          "`- row <id>: <the question> — recommended: <your answer>` — the next interactive /reef-loop asks them as ONE set. "
          "At the context ceiling write the handoff and `python3 scripts/reef-loop.py wait \"/clear requested …\"` as usual. "
          "When no row can move without the owner, `python3 scripts/reef-loop.py wait \"owner: <what>\"` and end.")


def die(msg, code=1):
    print(f"reef-run: {msg}", file=sys.stderr)
    sys.exit(code)


def main_checkout(repo):
    r = subprocess.run(["git", "-C", repo, "worktree", "list", "--porcelain"], capture_output=True, text=True)
    first = next((l[len("worktree "):].strip() for l in r.stdout.splitlines() if l.startswith("worktree ")), "")
    return first or os.path.abspath(repo)


def session(root, prompt, mode):
    """One headless Claude Code session in the project; its JSON result, or {"result": <raw output>}."""
    claude = os.environ.get("REEF_CLAUDE", "claude")
    t0 = time.time()
    try:
        p = subprocess.run([claude, "-p", prompt, "--permission-mode", mode, "--output-format", "json"], cwd=root,
                           capture_output=True, text=True)
    except FileNotFoundError:
        die(f"`{claude}` is not on the PATH — install Claude Code, or set REEF_CLAUDE")
    try:
        out = json.loads(p.stdout)
    except ValueError:
        out = {"result": (p.stdout or p.stderr)[-2000:]}
    out["_rc"], out["_seconds"] = p.returncode, round(time.time() - t0, 1)
    return out


def loop_state(root):
    try:
        with open(os.path.join(root, ".reef", "loop.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def in_flight(root):
    """In-flight and verifying markers in any checkout (the tick's own source)."""
    r = subprocess.run(["git", "-C", root, "worktree", "list", "--porcelain"], capture_output=True, text=True)
    roots = [l[len("worktree "):].strip() for l in r.stdout.splitlines() if l.startswith("worktree ")] or [root]
    ids = []
    for d in roots:
        for kind in ("inflight", "verifying"):
            p = os.path.join(d, ".reef", kind)
            ids += [f for f in (os.listdir(p) if os.path.isdir(p) else []) if not f.startswith(".")]
    return sorted(set(ids))


def cmd_probe(root, mode):
    target = os.path.join(root, ".reef", "approvals", "run-probe.json")
    out = session(root, "You are a probe, not a worker. Run exactly this one shell command and nothing else: "
                        "printf '{}' > .reef/approvals/run-probe.json . Then run: ls .reef/approvals/ . Report the first "
                        "command's full output verbatim, and say whether a hook refused it. Do not retry or work around a refusal.", mode)
    text = str(out.get("result", ""))
    existed = os.path.exists(target)
    if existed:
        os.unlink(target)
    ok = "reef-guard" in text and not existed
    with open(os.path.join(root, RUN_DIR, "gate.json"), "w", encoding="utf-8") as f:
        json.dump({"ok": ok, "mode": mode, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "denied": "reef-guard" in text, "file_existed": existed}, f, indent=1)
    if ok:
        print(f"GATE OK: reef-guard denied a headless session's forbidden write under --permission-mode {mode}; reef-run may loop")
        return 0
    print(f"GATE FAILED: {'the file was written' if existed else 'no reef-guard denial in the session'} — the guard does not reach "
          f"headless sessions here (mode {mode}); reef-run refuses to loop. Keep running /reef-loop interactively.")
    return 1


def cmd_run(root, mode, cap):
    try:
        with open(os.path.join(root, RUN_DIR, "gate.json"), encoding="utf-8") as f:
            gate = json.load(f)
    except (OSError, ValueError):
        gate = {}
    if not gate.get("ok") or gate.get("mode") != mode:
        die(f"no GATE OK for --permission-mode {mode} on this machine — run `python3 scripts/reef-run.py probe --permission-mode {mode}` first")
    lock = os.path.join(root, RUN_DIR, "lock")
    try:
        with open(lock, encoding="utf-8") as f:
            other = int(f.read().strip() or 0)
        os.kill(other, 0)
        die(f"another reef-run (pid {other}) holds {lock} — one runner per checkout")
    except (OSError, ValueError):
        pass
    with open(lock, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    log = os.path.join(root, RUN_DIR, "run.log")
    try:
        for i in range(1, cap + 1):
            out = session(root, PROMPT, mode)
            st = loop_state(root)
            wait, stop, parked = st.get("wait") or "", st.get("stop") or "", st.get("parked") or ""
            flying = [] if (wait or stop or parked) else in_flight(root)
            with open(log, "a", encoding="utf-8") as f:
                f.write(json.dumps({"iteration": i, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "session": out.get("session_id"),
                                    "seconds": out.get("_seconds"), "cost_usd": out.get("total_cost_usd"), "rc": out.get("_rc"),
                                    "wait": wait, "stop": stop, "parked": parked, "in_flight": flying}) + "\n")
            print(f"reef-run: session {i}: " + (f"wait {wait!r}" if wait else f"stop {stop!r}" if stop else f"parked {parked!r}" if parked
                                                  else f"in flight {flying}" if flying else "no wait recorded"))
            if stop:
                print(f"reef-run: the loop stopped — {stop}")
                return 0
            if parked:
                print(f"reef-run: the loop parked — {parked}")
                return 3
            if wait.startswith("/clear"):
                continue
            if wait:
                q = os.path.join(root, ".reef", "questions.md")
                print(f"reef-run: waiting on you — {wait}" + (f"\n  your questions: {q} — run /reef-loop in Claude Code to answer them" if os.path.isfile(q) else ""))
                return 2
            if flying:
                # a session that returns with work in flight would start it twice next time; Bash background work is
                # waited for headless (checked 2026-10-20), the Workflow tool is not proven yet — stop and say so
                print(f"reef-run: a session ended with work in flight ({', '.join(flying)}) — stopped so nothing runs twice")
                return 3
        print(f"reef-run: {cap} sessions, the iteration cap — the last state is in {log}")
        return 4
    finally:
        try:
            os.unlink(lock)
        except OSError:
            pass


def main(argv):
    repo, mode, cap = ".", "auto", 10
    args = list(argv)
    if "--repo" in args:
        repo = args[args.index("--repo") + 1]
    if "--permission-mode" in args:
        mode = args[args.index("--permission-mode") + 1]
    if "--max-iterations" in args:
        cap = int(args[args.index("--max-iterations") + 1])
    root = main_checkout(repo)
    if not os.path.isfile(os.path.join(root, ".reef", "config.json")):
        die(f"{root} is not a Reef project (no .reef/config.json)")
    os.makedirs(os.path.join(root, RUN_DIR), exist_ok=True)
    if args[:1] == ["probe"]:
        return cmd_probe(root, mode)
    return cmd_run(root, mode, cap)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
