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
  reef-run.py [--repo DIR] [--max-iterations 10] [--permission-mode auto] [--night] [--host opencode]
  --host opencode: each session is `opencode run --command reef-loop --format json` (scripts/reef-opencode.py install
               first); the probe and the gate are per host (`probe --host opencode`)
  reef-run.py watch [--repo DIR]   the live steps of the run in progress (any terminal; Ctrl-C to leave)
  reef-run.py status [--repo DIR]  one look: running or not, the night, the last steps and the last session
  --detach: after every check passes, the runner leaves the session that started it (its own process session,
            output to .reef/run/runner.out) and the command returns at once, so /reef-night can start the night
  reef-run.py contract [--from FILE]   (super Reef) install tonight's contract into .reef/night/contract.md and print
      the night digest (contract + reef/owner.md) and the exact question /reef-night asks: `Approve night <date> at <16 hex>?`
  --night: a delegated night (/reef-night): refuses without .reef/approvals/night.json at the CURRENT night digest; owner
      decisions inside the contract go to reef:mahmoud (the owner's proxy); `.reef/night/active` exists while it runs
      (the guard then refuses a release PR); `.reef/night/report.md` at exit — every proxy decision and every merge.
Exit: 0 the loop stopped · 2 waiting on the owner (their questions are in .reef/questions.md) · 3 parked, or a session
ended with work in flight · 4 the iteration cap · 1 refused (no probe for this mode, a second runner, not a project).
Files (gitignored): .reef/run/gate.json · .reef/run/run.log (one JSON line per session) · .reef/run/lock ·
.reef/run/live.log (one line per step of the current run: an agent out and back with its verdict, the orchestrator's
own words, a decision, a merge — what the terminal shows, and the Runner section of .reef/status.html).
The lock stops a second RUNNER; it does not stop an interactive /reef-loop beside it — run one orchestrator at a time.
"""
import html
import json
import os
import re
import subprocess
import sys
import time

RUN_DIR = os.path.join(".reef", "run")
LIVE = os.path.join(RUN_DIR, "live.log")
# the commands that decide or merge — every other Bash call is noise in the live view
KEY_BASH = re.compile(r"reef-approval\.py --proxy|reef-queue\.py footnote|reef-record |gh pr (create|merge)|git merge |reef-loop\.py wait")
NIGHT_DIR = os.path.join(".reef", "night")
# `claude -p` waits for background agents and workflows after the last turn only 10 idle minutes by default, then exits
# and kills them (night 2026-10-21: 1201 and 1202 cut off mid-build, the run record `killed`). Documented knob
# (code.claude.com/docs/en/headless, Claude Code 2.1.182+); the clock restarts on every background result.
BG_WAIT_MS = "10800000"
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


def steps(ev, names, verdicts):
    """The live lines one stream-json event is worth (2026-10-21: the owner watched a silent terminal for an hour). An
    agent or workflow starting, its sub-agent's hand-back verdict, its end; the orchestrator's own words; a decision or
    merge command. A sub-agent's own steps stay out."""
    kind, sub_, parent = ev.get("type"), ev.get("subtype"), ev.get("parent_tool_use_id")
    if kind == "system" and sub_ == "task_started":
        names[ev.get("tool_use_id")] = ev.get("description") or "a task"
        return [f"→ {names[ev.get('tool_use_id')]} ({ev.get('subagent_type') or ev.get('task_type') or 'task'})"]
    if kind == "system" and sub_ == "task_notification":
        tid = ev.get("tool_use_id")
        return [f"← {names.get(tid, 'a task')}: {verdicts.pop(tid, None) or ev.get('status') or 'ended'}"]
    msg = ev.get("message")
    blocks = msg.get("content") if isinstance(msg, dict) else None
    if kind != "assistant" or not isinstance(blocks, list):
        return []
    out = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        if parent:
            if b.get("type") == "tool_use" and b.get("name") == "SubagentHandback":
                m = re.search(r"VERDICT:\s*(\S+)", str((b.get("input") or {}).get("message", "")))
                verdicts[parent] = m.group(1) if m else "returned"
        elif b.get("type") == "text" and b.get("text", "").strip():
            out.append(b["text"].strip().splitlines()[0][:160])
        elif b.get("type") == "tool_use" and b.get("name") == "Bash" and KEY_BASH.search((b.get("input") or {}).get("command", "")):
            i = b["input"]
            out.append("· " + (i.get("description") or i["command"])[:140])
    return out


def oc_steps(ev):
    """The live lines one `opencode run --format json` event is worth (shapes: docs/perf/opencode-probe-2026-10-21.md): a
    task call arrives once, completed, with the sub-agent's output; the orchestrator's words; a decision or merge command."""
    part = ev.get("part") or {}
    if ev.get("type") == "text" and str(part.get("text") or "").strip():
        return [str(part["text"]).strip().splitlines()[0][:160]]
    if ev.get("type") != "tool_use":
        return []
    state = part.get("state") or {}
    i = state.get("input") or {}
    if part.get("tool") == "task":
        m = re.search(r"VERDICT:\s*(\S+)", str(state.get("output") or ""))
        return [f"↔ {i.get('description') or 'a task'} ({i.get('subagent_type') or 'task'}): {m.group(1) if m else state.get('status') or 'ended'}"]
    if part.get("tool") == "bash" and KEY_BASH.search(str(i.get("command") or "")):
        return ["· " + str(i.get("description") or i["command"])[:140]]
    return []


def session_opencode(root, prompt, say=None):
    """One headless OpenCode session (`opencode run --format json`): /reef-loop runs as its command; returns the session id,
    the summed step cost and the last words, the shape `session` returns."""
    oc = os.environ.get("REEF_OPENCODE", "opencode")
    msg = ["--command", "reef-loop", prompt[len("/reef-loop"):].lstrip(" —")] if prompt.startswith("/reef-loop") else [prompt]
    t0 = time.time()
    try:
        p = subprocess.Popen([oc, "run", "--format", "json"] + msg, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except FileNotFoundError:
        die(f"`{oc}` is not on the PATH — install OpenCode (npm install -g opencode-ai), or set REEF_OPENCODE")
    raw, sid, cost, last = [], "", 0.0, ""
    for line in p.stdout:
        try:
            ev = json.loads(line)
        except ValueError:
            raw.append(line)
            continue
        if not isinstance(ev, dict):
            continue
        sid = sid or str(ev.get("sessionID") or "")
        part = ev.get("part") or {}
        if ev.get("type") == "step_finish":
            cost += float(part.get("cost") or 0)
        if ev.get("type") == "text" and str(part.get("text") or "").strip():
            last = str(part["text"])
        try:
            lines = oc_steps(ev) if say else []
        except Exception as e:
            lines = [f"(an event the runner could not read: {type(e).__name__})"]
        for text in lines:
            say(text)
    p.wait()
    return {"session_id": sid, "total_cost_usd": round(cost, 6), "result": last or "".join(raw)[-2000:],
            "_rc": p.returncode, "_seconds": round(time.time() - t0, 1)}


def session(root, prompt, mode, say=None):
    """One headless Claude Code session in the project, streamed: each event's live lines go to `say`; returns the last
    `result` event (session_id, total_cost_usd, result), or {"result": <raw output>}. Mode `opencode`: an OpenCode one."""
    if mode == "opencode":
        return session_opencode(root, prompt, say)
    claude = os.environ.get("REEF_CLAUDE", "claude")
    t0 = time.time()
    try:
        p = subprocess.Popen([claude, "-p", prompt, "--permission-mode", mode, "--output-format", "stream-json", "--verbose"],
                             cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             env=dict(os.environ, REEF_RUNNER="1",
                                      CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=os.environ.get("CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS", BG_WAIT_MS)))
    except FileNotFoundError:
        die(f"`{claude}` is not on the PATH — install Claude Code, or set REEF_CLAUDE")
    out, raw, names, verdicts = None, [], {}, {}
    for line in p.stdout:
        try:
            ev = json.loads(line)
        except ValueError:
            raw.append(line)
            continue
        if not isinstance(ev, dict):
            continue
        if ev.get("type") == "result":
            out = ev
        try:
            lines = steps(ev, names, verdicts) if say else []
        except Exception as e:   # 2026-10-23: one event of an unexpected shape killed the runner mid-night
            lines = [f"(an event the runner could not read: {type(e).__name__})"]
        for text in lines:
            say(text)
    p.wait()
    out = dict(out) if out else {"result": "".join(raw)[-2000:]}
    out["_rc"], out["_seconds"] = p.returncode, round(time.time() - t0, 1)
    return out


def runner_html(root):
    """The Runner section of .reef/status.html: running or not, the last ten live lines (the session number is in each)."""
    try:
        with open(os.path.join(root, LIVE), encoding="utf-8") as f:
            tail = f.read().splitlines()[-10:]
    except OSError:
        return "<!--runner--><!--/runner-->"
    try:
        with open(os.path.join(root, RUN_DIR, "lock"), encoding="utf-8") as f:
            pid = int(f.read().strip() or 0)
        os.kill(pid, 0)
        head = f"running (pid {pid}) · <code>python3 scripts/reef-run.py watch</code> follows it"
    except (OSError, ValueError):
        head = "not running · the last run's steps"
    return (f"<!--runner--><h2>Runner</h2><div class=\"mute\">{head}</div><pre>{html.escape(chr(10).join(tail))}</pre>"
            "<!--/runner-->")


def refresh_status(root):
    """Re-splice the Runner section into the tick's status page between its markers (the tick owns the rest)."""
    p = os.path.join(root, ".reef", "status.html")
    try:
        with open(p, encoding="utf-8") as f:
            page = f.read()
    except OSError:
        return
    new = re.sub(r"<!--runner-->.*?<!--/runner-->", lambda _: runner_html(root), page, count=1, flags=re.S)
    if new != page:
        with open(p, "w", encoding="utf-8") as f:
            f.write(new)


def cmd_watch(root):
    """Follow .reef/run/live.log: the last 20 lines, then each new one (a new run truncates it — start again from 0)."""
    p, pos = os.path.join(root, LIVE), 0
    try:
        with open(p, encoding="utf-8") as f:
            lines = f.read().splitlines()
            pos = f.tell()
        print("\n".join(lines[-20:]) or "reef-run: no live steps yet", flush=True)
    except OSError:
        print(f"reef-run: no {LIVE} yet — it appears when a run starts", flush=True)
    try:
        while True:
            time.sleep(1)
            size = os.path.getsize(p) if os.path.exists(p) else 0
            if size < pos:
                pos = 0
            if size > pos:
                with open(p, encoding="utf-8") as f:
                    f.seek(pos)
                    print(f.read(), end="", flush=True)
                    pos = f.tell()
    except KeyboardInterrupt:
        return 0


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
    # 2026-10-21 (qassimha): last night's approval, rows 3 and 12 both closed since, still passed; the night ran one
    # 29-second session and waited. An approval is for one night, and a contract with no open row has nothing to do.
    import datetime
    try:
        at = datetime.datetime.fromisoformat(str(rec.get("approved_at", "")).replace("Z", "+00:00"))
        age_h = (datetime.datetime.now(datetime.timezone.utc) - at).total_seconds() / 3600
    except ValueError:
        age_h = None
    if age_h is None or age_h > NIGHT_HOURS:
        return False, (f"the contract was approved {rec.get('approved_at') or 'at no recorded time'}, more than {NIGHT_HOURS} h ago: "
                       "that was another night's — run /reef-night for tonight")
    rows, open_ids = night_rows(root), queue_open_rows(root)
    if rows and open_ids is not None and not set(rows) & open_ids:
        return False, f"every row of the contract ({', '.join(rows)}) is closed — run /reef-night for tonight"
    return True, ""


NIGHT_HOURS = 16


def queue_open_rows(root):
    """The ids of the queue's open rows (paths.queue; a closed row has moved to the archive), or None if unreadable."""
    import re
    try:
        with open(os.path.join(root, ".reef", "config.json"), encoding="utf-8") as f:
            rel = (json.load(f).get("paths") or {}).get("queue", "docs/queue.md")
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            return {m.group(1) for m in re.finditer(r"^\|\s*(\d+)\s*\|", f.read(), re.M)}
    except (OSError, ValueError):
        return None


def ready_rows(root):
    """Every ready row of the current batch, planned and found (reef-queue.py ready --with-found)."""
    q = os.path.join(root, "scripts", "reef-queue.py")
    if not os.path.isfile(q):
        q = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reef-queue.py")
    r = subprocess.run([sys.executable, q, "ready", "--with-found", "--repo", root], capture_output=True, text=True)
    return [l.split("\t")[0] for l in r.stdout.splitlines() if "\t" in l]


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
    left = [r for r in ready_rows(root) if r not in night_rows(root)]
    if left:
        print(f"WARN ready rows not in tonight's contract, which the night will not touch: {', '.join(left)} — add them, or say why not")
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


def detach(root):
    """--detach (the owner, 2026-10-24: why a manual terminal step?): fork, setsid, fork again, stdio to runner.out. The
    caller gets the runner's pid and returns; the runner outlives the Claude session or terminal that started it
    (proved live: a beater started from `claude -p` kept running after that session ended)."""
    out = os.path.join(root, RUN_DIR, "runner.out")
    r, w = os.pipe()
    if os.fork():
        os.close(w)
        pid = os.read(r, 32).decode().strip()
        print(f"reef-run: detached (pid {pid}) — it runs on after this session ends. Follow it: python3 scripts/reef-run.py "
              f"status (or watch, in a terminal); its output: .reef/run/runner.out")
        sys.exit(0)
    os.close(r)
    os.setsid()
    if os.fork():
        os._exit(0)
    os.write(w, str(os.getpid()).encode())
    os.close(w)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
    os.dup2(fd, 1)
    os.dup2(fd, 2)


def cmd_status(root):
    """Running or not (the lock's process), the night, the last live lines, the last session's record."""
    try:
        with open(os.path.join(root, RUN_DIR, "lock"), encoding="utf-8") as f:
            pid = int(f.read().strip() or 0)
        os.kill(pid, 0)
        state = f"running (pid {pid})"
    except (OSError, ValueError):
        state = "not running"
    night = "a night is active" if os.path.isfile(os.path.join(root, NIGHT_DIR, "active")) else "no night active"
    print(f"reef-run: {state}; {night}")
    try:
        with open(os.path.join(root, LIVE), encoding="utf-8") as f:
            for line in f.read().splitlines()[-15:]:
                print("  " + line)
    except OSError:
        print("  (no live log yet)")
    try:
        with open(os.path.join(root, RUN_DIR, "run.log"), encoding="utf-8") as f:
            rec = json.loads(f.read().splitlines()[-1])
        end = rec.get("wait") or rec.get("stop") or rec.get("parked") or ""
        print(f"last session: {rec.get('at')} · {rec.get('seconds')} s · ${rec.get('cost_usd') or 0:.2f}" + (f" · ended on: {end[:160]}" if end else ""))
    except (OSError, ValueError, IndexError):
        pass
    return 0


def cmd_run(root, mode, cap, night=False, detached=False):
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
    if detached:
        detach(root)   # every refusal above printed to the caller; from here on the runner is on its own
    with open(lock, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    log = os.path.join(root, RUN_DIR, "run.log")
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    active = os.path.join(root, NIGHT_DIR, "active")
    if night:
        with open(active, "w", encoding="utf-8") as f:
            f.write(json.dumps({"pid": os.getpid(), "started": started, "digest16": night_digest(root)[:16]}))
    live = os.path.join(root, LIVE)
    open(live, "w", encoding="utf-8").close()
    i = 0

    def say(text):
        line = f"{time.strftime('%H:%M')} s{i} {text}"
        print(line, flush=True)
        with open(live, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        refresh_status(root)

    try:
        for i in range(1, cap + 1):
            say("session started" + (" (night)" if night else ""))
            out = session(root, PROMPT + (NIGHT_PROMPT if night else ""), mode, say)
            st = loop_state(root)
            wait, stop, parked = st.get("wait") or "", st.get("stop") or "", st.get("parked") or ""
            flying = [] if (wait or stop or parked) else in_flight(root)
            with open(log, "a", encoding="utf-8") as f:
                f.write(json.dumps({"iteration": i, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "session": out.get("session_id"),
                                    "seconds": out.get("_seconds"), "cost_usd": out.get("total_cost_usd"), "rc": out.get("_rc"),
                                    "wait": wait, "stop": stop, "parked": parked, "in_flight": flying}) + "\n")
            cost = out.get("total_cost_usd")
            say("session ended: " + (f"wait {wait!r}" if wait else f"stop {stop!r}" if stop else f"parked {parked!r}" if parked
                                     else f"in flight {flying}" if flying else "no wait recorded")
                + f" · {out.get('_seconds')} s" + (f" · ${cost:.2f}" if isinstance(cost, (int, float)) else ""))
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
                print(f"reef-run: waiting on you — {wait}" + (f"\n  your questions: {q} — run /reef-loop in {'OpenCode' if mode == 'opencode' else 'Claude Code'} to answer them" if os.path.isfile(q) else ""))
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
        refresh_status(root)
        if night:
            morning_report(root, started, log)


def main(argv):
    repo, mode, cap = ".", "auto", 10
    args = list(argv)
    if "--repo" in args:
        repo = args[args.index("--repo") + 1]
    if "--permission-mode" in args:
        mode = args[args.index("--permission-mode") + 1]
    if "--host" in args:
        host = args[args.index("--host") + 1]
        if host not in ("claude", "opencode"):
            die(f"--host {host!r}: claude or opencode")
        mode = "opencode" if host == "opencode" else mode
    if "--max-iterations" in args:
        cap = int(args[args.index("--max-iterations") + 1])
    root = main_checkout(repo)
    if not os.path.isfile(os.path.join(root, ".reef", "config.json")):
        die(f"{root} is not a Reef project (no .reef/config.json)")
    os.makedirs(os.path.join(root, RUN_DIR), exist_ok=True)
    os.makedirs(os.path.join(root, NIGHT_DIR), exist_ok=True)
    if args[:1] == ["watch"]:
        return cmd_watch(root)
    if args[:1] == ["status"]:
        return cmd_status(root)
    if args[:1] == ["probe"]:
        return cmd_probe(root, mode)
    if args[:1] == ["contract"]:
        return cmd_contract(root, args[args.index("--from") + 1] if "--from" in args else None)
    return cmd_run(root, mode, cap, night="--night" in args, detached="--detach" in args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
