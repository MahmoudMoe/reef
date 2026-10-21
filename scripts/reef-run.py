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
  reef-run.py [--repo DIR] [--max-iterations 10] [--permission-mode auto] [--night]
  reef-run.py contract [--from FILE]   (super Reef) install tonight's contract into .reef/night/contract.md and print
      the night digest (contract + reef/owner.md) and the exact question /reef-night asks: `Approve night <date> at <16 hex>?`
  --night: a delegated night (/reef-night): refuses without .reef/approvals/night.json at the CURRENT night digest; owner
      decisions inside the contract go to reef:mahmoud (the owner's proxy); `.reef/night/active` exists while it runs
      (the guard then refuses a release PR); `.reef/night/report.md` at exit — every proxy decision and every merge.
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
NIGHT_DIR = os.path.join(".reef", "night")
NIGHT_PROMPT = (" SUPER REEF NIGHT (.reef/night/contract.md, approved by the owner; /reef-night has the rules): every owner decision "
                "INSIDE the contract goes to reef:mahmoud (model roles.proxy), never to questions.md. A plan approval: Mahmoud writes "
                "its report, you `cp` it to .reef/ci-local/report-mahmoud-<slug>.md, then `python3 scripts/reef-approval.py --proxy "
                "--feature <slug> --report <that file>`. A design look, a product question, a post-round-2 hole, triage: "
                "`python3 scripts/reef-queue.py footnote \"Mahmoud (proxy, night <date>): <decision> — <why>\" --row <id>`. A WAIT "
                "(outside the contract, or a hard limit): questions.md, and keep the other rows moving.")
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
    """In-flight and verifying markers in any checkout, newer than loop.inflight_stale_minutes (90) — the tick's own
    rule: an older marker is a returned agent, not running work (2026-10-21: row 12's leftover markers would have stopped
    the runner with "work in flight" while nothing ran)."""
    try:
        with open(os.path.join(root, ".reef", "config.json"), encoding="utf-8") as f:
            stale = int(((json.load(f).get("loop") or {}).get("inflight_stale_minutes", 90)) or 90)
    except (OSError, ValueError, AttributeError):
        stale = 90
    r = subprocess.run(["git", "-C", root, "worktree", "list", "--porcelain"], capture_output=True, text=True)
    roots = [l[len("worktree "):].strip() for l in r.stdout.splitlines() if l.startswith("worktree ")] or [root]
    ids, now = [], time.time()
    for d in roots:
        for kind in ("inflight", "verifying"):
            p = os.path.join(d, ".reef", kind)
            for f in (os.listdir(p) if os.path.isdir(p) else []):
                if not f.startswith(".") and now - os.path.getmtime(os.path.join(p, f)) < stale * 60:
                    ids.append(f)
    return sorted(set(ids))


def night_digest(root):
    """sha256 over the contract and the owner's profile, in one place (the hook and --proxy import this): an edit to
    either after the owner's approval approves nothing."""
    import hashlib
    h = hashlib.sha256()
    for rel in (os.path.join(NIGHT_DIR, "contract.md"), os.path.join("reef", "owner.md")):
        try:
            with open(os.path.join(root, rel), "rb") as f:
                h.update(rel.encode() + b"\0" + f.read() + b"\0")
        except OSError:
            return ""
    return h.hexdigest()


def night_rows(root):
    """The queue row ids the contract names on its `Rows:` line."""
    import re
    try:
        with open(os.path.join(root, NIGHT_DIR, "contract.md"), encoding="utf-8") as f:
            m = re.search(r"^Rows:\s*(.+)$", f.read(), re.M)
    except OSError:
        return []
    return [x for x in re.findall(r"\d+", m.group(1))] if m else []


def night_ok(root):
    """(ok, why): night.json carries the current night digest."""
    try:
        with open(os.path.join(root, ".reef", "approvals", "night.json"), encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return False, "no .reef/approvals/night.json — run /reef-night in Claude Code first (the owner approves tonight's contract)"
    dg = night_digest(root)
    if not dg or rec.get("digest16") != dg[:16]:
        return False, f"the contract or reef/owner.md changed since the owner approved it ({rec.get('digest16')} vs {dg[:16] or 'missing'}) — /reef-night again"
    return True, ""


def personal_profile():
    """The owner's profile across projects (REEF_OWNER_PROFILE, else ~/.reef/owner.md): who they are everywhere, so a
    new project's first night does not start from nothing (the owner, 2026-10-21)."""
    return os.environ.get("REEF_OWNER_PROFILE") or os.path.join(os.path.expanduser("~"), ".reef", "owner.md")


def cmd_contract(root, src):
    import shutil
    os.makedirs(os.path.join(root, NIGHT_DIR), exist_ok=True)
    mine, theirs = os.path.join(root, "reef", "owner.md"), personal_profile()
    if not os.path.isfile(mine) and os.path.isfile(theirs):
        os.makedirs(os.path.dirname(mine), exist_ok=True)
        shutil.copyfile(theirs, mine)
        print(f"owner profile: seeded reef/owner.md from {theirs} — Mahmoud adds this project's decisions; you approve both with the night")
    if src:
        shutil.copyfile(src, os.path.join(root, NIGHT_DIR, "contract.md"))
    dg = night_digest(root)
    if not dg:
        die("no .reef/night/contract.md, or no reef/owner.md — /reef-night drafts both")
    print(f"night digest: {dg}")
    print(f"rows: {', '.join(night_rows(root)) or '-'}")
    print(f"question: Approve night {time.strftime('%Y-%m-%d')} at {dg[:16]}?")
    return 0


def morning_report(root, started, log):
    """Every proxy decision and every merge since `started` — the owner reverses a decision by deleting its record or
    footnote, a merge only by `git revert` on the base branch, so they are listed apart."""
    import glob
    lines = [f"# Night report — {time.strftime('%Y-%m-%d %H:%M')}", ""]
    appr = []
    for p in sorted(glob.glob(os.path.join(root, ".reef", "approvals", "*.json"))):
        try:
            rec = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if str(rec.get("by", "")).startswith("mahmoud") and str(rec.get("approved_at", "")) >= started:
            appr.append(f"- plan `{os.path.basename(p)[:-5]}` approved at {rec.get('digest16')} — undo: delete {os.path.relpath(p, root)}")
    lines += ["## Mahmoud's plan approvals", *(appr or ["- none"]), ""]
    foot = []
    try:
        cfg = json.load(open(os.path.join(root, ".reef", "config.json"), encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    queue = os.path.join(root, (cfg.get("paths") or {}).get("queue", "docs/queue.md"))
    try:
        foot = [f"- {l.strip()}" for l in open(queue, encoding="utf-8") if "Mahmoud (proxy" in l]
    except OSError:
        pass
    lines += ["## Mahmoud's other decisions (queue footnotes — undo: edit the footnote)", *(foot or ["- none"]), ""]
    base = str((cfg.get("branches") or {}).get("base", "main") or "main")
    r = subprocess.run(["git", "-C", root, "log", "--merges", "--format=- %h %s", f"--since={started}", base], capture_output=True, text=True)
    lines += [f"## Merges into {base} (undo: git revert -m 1 <sha>)", *(r.stdout.splitlines() or ["- none"]), ""]
    q = os.path.join(root, ".reef", "questions.md")
    lines += ["## Waiting for you", *(open(q, encoding="utf-8").read().splitlines() if os.path.isfile(q) else ["- nothing"]), ""]
    sessions = [json.loads(l) for l in open(log, encoding="utf-8")] if os.path.isfile(log) else []
    tonight = [x for x in sessions if str(x.get("at", "")) >= started]
    cost = sum(float(x.get("cost_usd") or 0) for x in tonight)
    lines += [f"Sessions: {len(tonight)} · cost: ${cost:.2f} · log: {os.path.relpath(log, root)}"]
    with open(os.path.join(root, NIGHT_DIR, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"reef-run: the night report — {os.path.join(NIGHT_DIR, 'report.md')}")


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


def cmd_run(root, mode, cap, night=False):
    if night:
        ok, why = night_ok(root)
        if not ok:
            die(why)
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
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    active = os.path.join(root, NIGHT_DIR, "active")
    if night:
        with open(active, "w", encoding="utf-8") as f:
            f.write(json.dumps({"pid": os.getpid(), "started": started, "digest16": night_digest(root)[:16]}))
    try:
        for i in range(1, cap + 1):
            out = session(root, PROMPT + (NIGHT_PROMPT if night else ""), mode)
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
        for p in (lock, active if night else None):
            try:
                if p:
                    os.unlink(p)
            except OSError:
                pass
        if night:
            morning_report(root, started, log)


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
    os.makedirs(os.path.join(root, NIGHT_DIR), exist_ok=True)
    if args[:1] == ["probe"]:
        return cmd_probe(root, mode)
    if args[:1] == ["contract"]:
        return cmd_contract(root, args[args.index("--from") + 1] if "--from" in args else None)
    return cmd_run(root, mode, cap, night="--night" in args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
