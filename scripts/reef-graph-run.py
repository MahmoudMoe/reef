#!/usr/bin/env python3
# CLASS: code
"""Reef graph run — the task graph as a Claude Code WORKFLOW (dynamic workflow, 2.1.29x+): every ready task runs
implementer → gate → verifier ‖ hunter as a pipeline in the background, in fresh contexts, and the orchestrator reads
ONE summary instead of one agent result per 90k-context turn (workflow v2, phase 3; measured 2026-10-17: a task cost
the orchestrator 25 turns and 49k of growth in chat mode).

Usage:
  reef-graph-run.py probe       [--repo DIR]          write .reef/graph/probe.js — ONE workflow agent tries a forbidden write
  reef-graph-run.py probe-check <results.json> [--repo DIR]
                                                      the probe's return value: the guard denied it AND no file exists →
                                                      .reef/graph/gate.json ok; anything else → graph mode stays OFF
  reef-graph-run.py generate    [--repo DIR] [--tasks 101,102]
                                                      the tick's `dispatch now` tasks (or --tasks): worktree + reef-attempt
                                                      per task (the same checks and markers as chat mode), then
                                                      .reef/graph/run-<hash>.js — the script the orchestrator hands to
                                                      the Workflow tool (scriptPath). Refused while gate.json is not ok.
  reef-graph-run.py row         <row-id|slug> [--repo DIR]   (v3 phase 5b)
                                                      ONE workflow for the row: its open tasks in id order — implementer, gate,
                                                      the judges on the critical path, the close in place (reef-merge-close by
                                                      the mechanic) — then the full gate and converge, merge-base + push + PR,
                                                      the guard pass and security on the critical path, and the ONE reviewer;
                                                      .reef/graph/row-<slug>-<hash>.js. Refused at plan/approval (the owner's
                                                      steps), at merge/close (scripts), with a task in flight, or gate not ok.
  reef-graph-run.py settle      <results.json> [--repo DIR]
                                                      the workflow's return value: per task, the gate exit, the hand-back
                                                      check, the snapshot before and after the judges, the verdicts and
                                                      report files → the report checks and the guard-pass record run here;
                                                      READY TO MERGE <id> or FAIL <id>: <why> (attempt counted). A row's
                                                      result: every close checked on disk, the evidence re-read, the review
                                                      report copied and recorded (reef-record), then ROW <id> READY TO MERGE
                                                      with the one bare `gh pr merge` the orchestrator runs (the guard checks
                                                      it there; settle never merges) — or ROW <id> WAITS <state>: <why>.

Why a script and not the chat: a workflow script has no filesystem and runs only agents, so every mechanical step
(reef-attempt, the gate, the snapshot, reef-claims) is done by a `reef:mechanic` agent inside the pipeline or by
this script before and after. What the chat orchestrator keeps: the merge (single writer on the feature branch) and
the owner's questions.

The GATE (fail closed): Claude Code's PreToolUse hooks — reef-guard — must apply to workflow agents, or a workflow
is a way around every denial. The probe proves it on this machine before any real run; the probe's record is
.reef/graph/gate.json and `generate` refuses without it. Dispatch-time checks the guard makes on a Task call
(approval record, review record, model pin, in-flight marker) happen here at generation instead, through
reef-plan-check --verify-stamp and reef-attempt.
Exit 0 ok · 1 refused / a task failed · 2 usage.
"""
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time

GRAPH_DIR = os.path.join(".reef", "graph")


def die(msg, code=2):
    print(f"reef-graph-run: {msg}", file=sys.stderr)
    sys.exit(code)


def root_of(repo):
    r = subprocess.run(["git", "-C", repo, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else os.path.abspath(repo)


def run(args, cwd, timeout=120):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def script(root, name):
    p = os.path.join(root, "scripts", name)
    return p if os.path.isfile(p) else os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


def gate_ok(root):
    try:
        with open(os.path.join(root, GRAPH_DIR, "gate.json"), encoding="utf-8") as f:
            g = json.load(f)
        return bool(g.get("ok"))
    except Exception:
        return False


def js_str(s):
    return json.dumps(s)


# ---------------------------------------------------------------- probe

PROBE_SCHEMA = {"type": "object", "properties": {"denied": {"type": "boolean"}, "output": {"type": "string"}}, "required": ["denied", "output"]}


def cmd_probe(root):
    prompt = (f"You are a probe, not a worker. In the repository at {root} run EXACTLY this one shell command and nothing else: "
              f"printf '{{}}' > .reef/approvals/graph-probe.json . Then run: ls .reef/approvals/ . "
              f"Return denied=true if the first command was refused by a hook (its output names reef-guard or says DENY), "
              f"denied=false if it ran. Put both commands' full output in `output`. Do not retry, do not work around a refusal.")
    js = f"""export const meta = {{
  name: 'reef-graph-probe',
  description: 'Reef graph mode gate: does reef-guard deny a forbidden write made by a workflow agent?',
  phases: [{{ title: 'Probe' }}],
}}
const PROBE = {json.dumps(PROBE_SCHEMA)}
phase('Probe')
const r = await agent({js_str(prompt)}, {{ label: 'probe:forbidden-write', phase: 'Probe', agentType: 'reef:mechanic', schema: PROBE }})
return r
"""
    d = os.path.join(root, GRAPH_DIR)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "probe.js")
    with open(p, "w", encoding="utf-8") as f:
        f.write(js)
    print(f"probe: {p}")
    print("next: call the Workflow tool with scriptPath set to that file; save its return value as JSON to .reef/graph/probe-results.json; "
          "then `reef-graph-run.py probe-check .reef/graph/probe-results.json`")
    return 0


def cmd_probe_check(root, results_path):
    try:
        with open(results_path, encoding="utf-8") as f:
            res = json.load(f)
    except Exception as e:
        die(f"cannot read the probe's results: {e}", 1)
    leaked = os.path.join(root, ".reef", "approvals", "graph-probe.json")
    exists = os.path.isfile(leaked)
    denied = bool(isinstance(res, dict) and res.get("denied"))
    d = os.path.join(root, GRAPH_DIR)
    os.makedirs(d, exist_ok=True)
    ok = denied and not exists
    with open(os.path.join(d, "gate.json"), "w", encoding="utf-8") as f:
        json.dump({"ok": ok, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "denied": denied, "file_existed": exists}, f, indent=1)
    if exists:
        os.unlink(leaked)   # a hand-written approval record for a feature that does not exist: never left in the tree
    if ok:
        print("GATE OK: reef-guard denied the workflow agent's forbidden write and no file was created — graph mode may run (.reef/graph/gate.json)")
        return 0
    why = "the file .reef/approvals/graph-probe.json was created (removed now)" if exists else "the agent reports the write was not denied"
    print(f"GATE FAILED: {why} — PreToolUse hooks do not reach workflow agents on this machine; graph mode stays OFF (generate refuses). "
          f"Chat mode (/reef-task) keeps every guarantee.")
    return 1


# ---------------------------------------------------------------- generate

SNAP_SCHEMA = {"type": "object", "properties": {"gate_exit": {"type": "integer"}, "handback_check": {"type": "string"}, "snapshot": {"type": "string"},
                                                "notes": {"type": "string"}}, "required": ["gate_exit", "handback_check", "snapshot"]}
RESNAP_SCHEMA = {"type": "object", "properties": {"snapshot": {"type": "string"}}, "required": ["snapshot"]}
JUDGE_SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["PASS", "FAIL"]}, "report_path": {"type": "string"},
                                                 "summary": {"type": "string"}}, "required": ["verdict", "report_path"]}
REVIEW_SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["GREEN", "FAIL"]}, "report_path": {"type": "string"},
                                                  "summary": {"type": "string"}}, "required": ["verdict", "report_path"]}
CLOSE_SCHEMA = {"type": "object", "properties": {"closed": {"type": "boolean"}, "output": {"type": "string"}}, "required": ["closed", "output"]}
EVIDENCE_SCHEMA = {"type": "object", "properties": {"gate_exit": {"type": "integer"}, "converge_exit": {"type": "integer"}, "evidence": {"type": "string"},
                                                    "notes": {"type": "string"}}, "required": ["gate_exit", "converge_exit", "evidence"]}
PR_SCHEMA = {"type": "object", "properties": {"number": {"type": ["integer", "null"]}, "head": {"type": "string"}, "output": {"type": "string"}},
             "required": ["number", "head", "output"]}
MODELS = {"opus", "sonnet", "haiku"}


def ready_tasks(root, only):
    rc, out, err = run([sys.executable, script(root, "reef-loop.py"), "tick", "--json", "--repo", root], root)
    if rc != 0:
        die(f"tick failed: {err.strip() or out.strip()}", 1)
    state = json.loads(out)
    ids = [str(x) for x in state.get("dispatch_now", [])] + [str(x) for x in state.get("verify_now", [])]
    # 0.7: the tick decides the mode per task (graph.mode from the main checkout and this machine's gate); a fix round
    # and a handed-back task run here too since 2026-10-20
    dm = state.get("dispatch_mode") or {}
    chat_ids = [i for i in ids if dm.get(i, "graph") == "chat"]
    if state.get("graph_mode") == "chat":
        die("graph.mode is `chat` in the main checkout's config: /reef-task dispatches these; set `auto` or `graph` to use the graph", 1)
    for i in chat_ids:
        if not only or i in only:
            print(f"skipped {i}: chat mode (no GATE OK on this machine): /reef-task")
    if only:
        missing = [i for i in only if i not in ids]
        if missing:
            print(f"skipped (not in the tick's dispatch now — blocked, in flight, or awaiting): {', '.join(missing)}")
        ids = [i for i in ids if i in only]
    ids = [i for i in ids if i not in chat_ids]
    paths = {}
    rc, out, _ = run([sys.executable, script(root, "reef-graph.py"), "ready", "--json", "--root", root], root)
    for t in (json.loads(out) if rc == 0 and out.strip() else []):
        paths[str(t["id"])] = t["path"]
    # feature worktrees hold their own ready tasks (the tick saw them the same way)
    rc, wt, _ = run(["git", "worktree", "list", "--porcelain"], root)
    for l in wt.splitlines():
        if l.startswith("worktree ") and os.path.realpath(l[9:].strip()) != os.path.realpath(root):
            w = l[9:].strip()
            rc, out, _ = run([sys.executable, script(root, "reef-graph.py"), "ready", "--json", "--root", w], w)
            for t in (json.loads(out) if rc == 0 and out.strip() else []):
                paths.setdefault(str(t["id"]), t["path"])
    verify = set(str(x) for x in state.get("verify_now", []))
    return [(i, paths.get(i), i in verify) for i in ids], state


def last_failure(task_path):
    """The last `- attempt N FAIL: …` line under ## Log (reef-attempt writes it; settle words it), or ''."""
    try:
        with open(task_path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return ""
    fails = re.findall(r"^\s*-\s*attempt \d+ FAIL:.*$", text, re.M)
    return fails[-1].strip() if fails else ""


def plan_home(path):
    """reef-graph.py's plan_home, from this script's own directory: the feature worktree's copy of a task file."""
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("reef_graph_home", os.path.join(os.path.dirname(os.path.abspath(__file__)), "reef-graph.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod.plan_home(path)


def mark_dispatched(root, task_path, tid, implementer=True):
    """What the guard does on an allowed Task dispatch (reef-guard check_dispatch): the task becomes in-progress, its
    dispatch odometer moves, and .reef/inflight/<id> is written in the main checkout — so the tick, the Stop hook
    and the reviewer lock see a graph-mode task exactly as a chat-mode one. The status goes to the plan's home copy."""
    task_path = plan_home(task_path)
    with open(task_path, encoding="utf-8", newline="") as f:
        text = f.read()
    m = re.match(r"\A---\r?\n(.*?\r?\n)---\r?\n", text, re.S)
    fm = m.group(1) if m else ""
    feature = (re.search(r"^feature:[ \t]*(\S+)", fm, re.M) or [None, ""])[1]
    tier = (re.search(r"^tier:[ \t]*(\S+)", fm, re.M) or [None, "full"])[1]
    if m and implementer:
        new_fm = re.sub(r"^status:.*$", "status: in-progress", fm, count=1, flags=re.M)
        dm = re.search(r"^dispatches:[ \t]*(\d+)", new_fm, re.M)
        if dm:
            new_fm = new_fm[:dm.start()] + f"dispatches: {int(dm.group(1)) + 1}" + new_fm[dm.end():]
        if new_fm != fm:
            with open(task_path, "w", encoding="utf-8", newline="") as f:
                f.write(text[:m.start(1)] + new_fm + text[m.end(1):])
    d = os.path.join(root, ".reef", "inflight")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, str(tid)), "w", encoding="utf-8") as f:
        json.dump({"id": tid, "task": os.path.abspath(task_path), "feature": feature, "tier": tier, "agent": "reef:implementer (workflow)",
                   "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f)


def attempt_lines(root, task_path):
    rc, out, err = run([sys.executable, script(root, "reef-attempt"), task_path], os.path.dirname(task_path), timeout=120)
    return rc, out, err


def cmd_generate(root, only):
    if not gate_ok(root):
        die("graph mode is OFF: no .reef/graph/gate.json with ok=true — run `reef-graph-run.py probe`, hand .reef/graph/probe.js to the "
            "Workflow tool, then `probe-check` its return value. Chat mode (/reef-task) keeps every guarantee meanwhile.", 1)
    tasks, state = ready_tasks(root, only)
    if not tasks:
        print("nothing to dispatch: the tick's `dispatch now` is empty")
        return 1
    report_dir = os.path.join("/tmp", f"reef-graph-{hashlib.sha1(root.encode()).hexdigest()[:8]}")
    os.makedirs(report_dir, exist_ok=True)
    items, skipped = [], []
    for tid, path, verify_only in tasks:
        it = task_item(root, tid, path, verify_only, report_dir)
        if isinstance(it, str):
            skipped.append(it)
            continue
        items.append(it)
    for s in skipped:
        print(f"skipped {s}")
    if not items:
        return 1
    return write_graph(root, items, report_dir)


def task_item(root, tid, path, verify_only, report_dir):
    """One task's worktree, reef-attempt lines, dispatch bookkeeping and prompts — the item a workflow script carries;
    a string names why it was skipped. Shared by `generate` (the tick's ready tasks) and `row` (a row's tasks in order)."""
    if not path or not os.path.isfile(path):
        return f"{tid}: task file not found"
    tdir = os.path.dirname(os.path.dirname(os.path.abspath(path))) if os.path.basename(os.path.dirname(path)) == "tasks" else os.path.dirname(os.path.abspath(path))
    checkout = root_of(tdir)
    rc, wout, werr = run([sys.executable, script(root, "reef-graph.py"), "worktree", path], checkout, timeout=600)
    m = re.search(r"^worktree:\s*(\S+)", wout, re.M)
    if rc != 0 or not m:
        return f"{tid}: worktree: {(werr or wout).strip().splitlines()[-1] if (werr or wout).strip() else rc}"
    worktree = m.group(1) if os.path.isabs(m.group(1)) else os.path.join(checkout, m.group(1))
    rc, aout, aerr = attempt_lines(root, path)
    if rc != 0:
        return f"{tid}: reef-attempt: {(aerr or aout).strip().splitlines()[-1] if (aerr or aout).strip() else rc}"
    if True:
        get = lambda key: (re.search(rf"^{re.escape(key)}:\s*(.+)$", aout, re.M) or [None, ""])[1].strip() if re.search(rf"^{re.escape(key)}:", aout, re.M) else ""
        author_model = (re.search(r"model=(\w+)", get("author")) or [None, ""])[1]
        verifier_model = (re.search(r"model=(\w+)", get("verifier")) or [None, ""])[1]
        adversary_model = (re.search(r"model=(\w+)", get("adversary")) or [None, ""])[1]
        effort = (re.search(r"effort=(\w+)", get("dispatch")) or [None, ""])[1]
        reef_task = f"REEF-TASK: {os.path.abspath(path)}"
        # the round: a fix round re-dispatches the implementer with the failure; a report rejection or a hand-back only
        # re-judges (no implementer); after a rejected report the judge is FULL — there is no round-1 verdict to carry
        fail = last_failure(path)
        rejected = "verifier report rejected" in fail
        attempt = int((re.search(r"attempt=(\d+)/", get("dispatch")) or [None, "1"])[1])
        verify_only = verify_only or rejected
        rejudge = "" if rejected else get("rejudge")
        mark_dispatched(root, path, tid, implementer=not verify_only)
        judge = "model=" in get("verifier")   # v3: `verifier: none (fast path …)` is no judge
        hunter = bool(get("adversary"))
        items = {
            "id": tid, "task": os.path.abspath(path), "worktree": worktree, "checkout": checkout,
            "judge": judge, "hunter": hunter,
            "author_model": author_model if author_model in MODELS else None, "verifier_model": verifier_model if verifier_model in MODELS else None,
            "adversary_model": adversary_model if adversary_model in MODELS else None, "effort": effort or None,
            "implement_prompt": None if verify_only else (
                                f"{reef_task}\nEffort: {effort or 'medium'}. Work in the worktree {worktree} (the task's own checkout; the task file stays where it is). "
                                + (f"Round {attempt}: the last round failed — {fail[:400]} (gate log: {worktree}/.reef/ci-local/gate-full.log). The "
                                   f"previous round's work is uncommitted in this worktree: fix what failed, keep the rest. " if fail and attempt > 1 else "")
                                + f"Write your hand-back FILE to {worktree}/.reef/ci-local/handback-{tid}.md before your final message (writing.handback_words; evidence only); "
                                f"return that path and the RUN line only."),
            "gate_prompt": f"{reef_task}\nMechanic, in {worktree}: (1) python3 scripts/reef-claims.py check --handback .reef/ci-local/handback-{tid}.md — put its first line in handback_check, and when it is REJECTED the `- ` reason lines after it too; "
                           f"(2) sh scripts/reef-gate.sh full --failures — put its exit code in gate_exit and, if it failed, the failing block (under 60 lines) in notes; "
                           f"(3) sh scripts/reef-snapshot.sh — put the hash it prints in snapshot. Change no file. Return the JSON only.",
            "verifier_prompt": f"{reef_task}\n{get('report') or ''}\n"
                               + (f"rejudge: {rejudge}\nRound {attempt}: put round={attempt} on your RUN line.\n" if rejudge and attempt > 1 else "")
                               + f"Verify the task's work in the worktree {worktree} (read-only). Write your report FILE to "
                               f"{report_dir}/report-{tid}-verifier.md before your final message; return verdict and report_path.",
            "hunter_prompt": f"{reef_task}\n{get('hunter-report') or ''}\nGuard pass on the finished code in the worktree {worktree} (read-only): how can every check be green while "
                             f"the defect happens? Write your report FILE to {report_dir}/report-{tid}-hunter.md before your final message; return verdict (FAIL iff a BLOCKER) and report_path.",
            "resnap_prompt": f"{reef_task}\nMechanic, in {worktree}: run sh scripts/reef-snapshot.sh and return the hash it prints as snapshot. Change no file.",
        }
        return items


def write_graph(root, items, report_dir):
    tasks_json = json.dumps(items, indent=1)
    js = f"""export const meta = {{
  name: 'reef-graph',
  description: 'Reef task graph: implementer, gate, verifier and hunter per ready task, as a pipeline in fresh contexts',
  phases: [{{ title: 'Implement' }}, {{ title: 'Gate' }}, {{ title: 'Judge' }}, {{ title: 'Snapshot' }}],
}}
const TASKS = {tasks_json}
const SNAP = {json.dumps(SNAP_SCHEMA)}
const RESNAP = {json.dumps(RESNAP_SCHEMA)}
const JUDGE = {json.dumps(JUDGE_SCHEMA)}
const opt = (o) => Object.fromEntries(Object.entries(o).filter(([k, v]) => v !== null && v !== undefined))
log(`reef graph: ${{TASKS.length}} task(s): ${{TASKS.map(t => t.id).join(', ')}}`)
const results = await pipeline(TASKS,
  t => (t.implement_prompt
        ? agent(t.implement_prompt, opt({{ label: `implement:${{t.id}}`, phase: 'Implement', agentType: 'reef:implementer', model: t.author_model, effort: t.effort }}))
        : Promise.resolve(null))
        .then(text => ({{ implementer: text }})),
  (r, t) => agent(t.gate_prompt, {{ label: `gate:${{t.id}}`, phase: 'Gate', agentType: 'reef:mechanic', schema: SNAP, effort: 'low' }})
        .then(g => ({{ ...r, gate: g }})),
  (r, t) => {{
    if (!r.gate || r.gate.gate_exit !== 0 || !t.judge) return Promise.resolve({{ ...r, judges: [] }})
    const thunks = [() => agent(t.verifier_prompt, opt({{ label: `verify:${{t.id}}`, phase: 'Judge', agentType: 'reef:verifier', schema: JUDGE, model: t.verifier_model }})).then(v => ({{ role: 'verifier', ...v }}))]
    if (t.hunter) thunks.push(() => agent(t.hunter_prompt, opt({{ label: `hunt:${{t.id}}`, phase: 'Judge', agentType: 'reef:loophole-hunter', schema: JUDGE, model: t.adversary_model }})).then(h => ({{ role: 'hunter', ...h }})))
    return parallel(thunks).then(js => ({{ ...r, judges: js.filter(Boolean) }}))
  }},
  (r, t) => (r.judges && r.judges.length
      ? agent(t.resnap_prompt, {{ label: `snapshot:${{t.id}}`, phase: 'Snapshot', agentType: 'reef:mechanic', schema: RESNAP, effort: 'low' }}).then(s => s.snapshot)
      : Promise.resolve(r.gate ? r.gate.snapshot : null))
    .then(after => ({{ task: t.id, worktree: t.worktree, task_file: t.task, judge: t.judge, hunter: t.hunter, gate: r.gate || null, judges: r.judges || [], snapshot_after: after }}))
)
return {{ tasks: results.filter(Boolean), skipped: TASKS.length - results.filter(Boolean).length }}
"""
    d = os.path.join(root, GRAPH_DIR)
    os.makedirs(d, exist_ok=True)
    h = hashlib.sha1(tasks_json.encode()).hexdigest()[:10]
    p = os.path.join(d, f"run-{h}.js")
    with open(p, "w", encoding="utf-8") as f:
        f.write(js)
    print(f"graph: {len(items)} task(s): {', '.join(i['id'] for i in items)}  reports: {report_dir}")
    print(f"script: {p}")
    print(f"next: call the Workflow tool with scriptPath {p}; when it completes, `reef-graph-run.py settle <the output file its completion notice names>`")
    return 0


# ---------------------------------------------------------------- settle

def rejection(text):
    """The reasons a reef-claims check rejected, not its first line: a rejected report prints `note:` lines first and the
    reasons as `  - …` under `REJECTED …:` (2026-10-19, qassimha 1302, row 69: the attempt recorded "note: report 661
    words" and the fix round's rejudge line carried nothing actionable)."""
    lines = (text or "").strip().splitlines()
    i = next((k for k, l in enumerate(lines) if l.startswith("REJECTED")), None)
    if i is not None:
        reasons = [l.strip()[2:].strip() for l in lines[i + 1:] if l.strip().startswith("- ")]
        return "; ".join(reasons)[:250] or lines[i][:250]
    rest = [l for l in lines if l.strip() and not l.startswith("note:")]
    return (rest[0] if rest else (lines[0] if lines else ""))[:250]


def findings(report_path, tid):
    """The hunter's NEW-ROW and NOTED lines, for the orchestrator to file (2026-10-21: graph mode copied a hunter's report
    at settle and nothing said what it had found — a finding not filed is a finding dropped)."""
    row = str(int(tid) // 100) if tid.isdigit() and int(tid) >= 100 else "?"
    out = []
    with open(report_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(r"^(NEW-ROW|NOTED)\s*:\s*(.+)$", line.replace("*", "").strip())
            if m:
                out.append(f"  {m.group(1)} (hunter {tid}, row {row}): {m.group(2)[:200]}")
    return out


def cmd_settle(root, results_path):
    try:
        with open(results_path, encoding="utf-8") as f:
            res = json.load(f)
    except Exception as e:
        die(f"cannot read the results: {e}", 1)
    # the completion notice's output file holds the return value under "result" — settle it as it is, nothing typed
    # (2026-10-21: a hand-typed results file was blocked by auto mode as a possible checks bypass)
    if isinstance(res, dict) and "tasks" not in res and "result" in res:
        if not isinstance(res.get("result"), dict):
            die("the workflow ended without a result (killed or failed): its tasks stay in flight until the tick frees them "
                "after loop.inflight_stale_minutes", 1)
        res = res["result"]
    tasks = res.get("tasks") if isinstance(res, dict) else None
    if not isinstance(tasks, list):
        die("results hold no `tasks` list — save the Workflow tool's return value as it came", 1)
    if isinstance(res, dict) and res.get("row"):
        return settle_row(root, res)
    failed, filed = 0, False
    for r in tasks:
        f, found = settle_task(root, r)
        failed += f
        for line in found:
            print(line)
        filed = filed or bool(found)
    if filed:
        print("file each on branches.base: NEW-ROW → `reef-queue.py add-row --item \"…\" --source found --depends <row>`; "
              "NOTED → `reef-queue.py note \"…\" --row <row>`")
    return 1 if failed else 0


def settle_task(root, r, extra_why=(), row=False):
    """One task's result against the disk: the marker cleared, the gate and hand-back check read, the judges' reports copied
    and checked, the hunter's PASS recorded; a failure counts the attempt. Returns (1 if failed else 0, the hunter's lines)."""
    if True:
        tid, task_file, wt = str(r.get("task")), r.get("task_file") or "", r.get("worktree") or ""
        found = []
        marker = os.path.join(root, ".reef", "inflight", tid)
        if os.path.isfile(marker):
            os.unlink(marker)   # handed back: the task is no longer in flight (chat mode: /reef-task removes it on the hand-back)
        gate = r.get("gate") or {}
        why = list(extra_why)
        if not os.path.isfile(task_file):
            why.append("task file missing")
        if gate.get("gate_exit") != 0:
            why.append(f"gate exit {gate.get('gate_exit')}" + (f": {str(gate.get('notes'))[:300]}" if gate.get("notes") else ""))
        hc = str(gate.get("handback_check", "") or "")
        if not hc.lower().startswith("ok"):
            # the reasons, not the header (2026-10-20, qassimha 301: the Log said "REJECTED hand-back (…)" and nothing else)
            why.append(f"hand-back rejected: {rejection(hc)}" if hc.startswith("REJECTED") else f"hand-back: {hc[:100] or 'not checked'}")
        # a red gate or a rejected hand-back ends the pipeline before the judges (the script skips them), so their
        # absence is the task's failure, not a missing verdict (2026-10-18, qassimha 1103: settle said "no verifier
        # verdict" on a red gate, that text suppressed reef-attempt, and the orchestrator counted the attempt by hand)
        if r.get("judge") and not why:
            judges = {j.get("role"): j for j in (r.get("judges") or []) if isinstance(j, dict)}
            if "verifier" not in judges:
                why.append("no verifier verdict")
            if r.get("hunter") and "hunter" not in judges:
                why.append("no hunter verdict")
            if gate.get("snapshot") and r.get("snapshot_after") and gate.get("snapshot") != r.get("snapshot_after"):
                why.append(f"the tree changed while the judges read it ({gate.get('snapshot')[:12]} → {str(r.get('snapshot_after'))[:12]})")
            for role, j in judges.items():
                rp = j.get("report_path") or ""
                if not os.path.isfile(rp):
                    why.append(f"{role} report file missing ({rp})")
                    continue
                dest = os.path.join(wt, ".reef", "ci-local", f"report-{tid}{'' if role == 'verifier' else '-hunter'}.md")
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(rp, "rb") as a, open(dest, "wb") as b:
                    b.write(a.read())   # a copy: the agent's words unchanged
                if role == "verifier":
                    rc, out, err = run([sys.executable, script(root, "reef-claims.py"), "report", dest, "--task", task_file], root)
                    if rc != 0:
                        why.append(f"verifier report rejected: {rejection(out or err) or rc}")
                if j.get("verdict") != "PASS":
                    why.append(f"{role}: {j.get('verdict')} — {str(j.get('summary', ''))[:140]}")
                elif role == "hunter":
                    rc, out, err = run([sys.executable, script(root, "reef-adversarial"), task_file, "guard", dest], root)
                    if rc != 0:
                        why.append(f"guard-pass record refused: {err.strip().splitlines()[-1][:140] if err.strip() else rc}")
        for j in (r.get("judges") or []):
            if isinstance(j, dict) and j.get("role") == "hunter" and os.path.isfile(j.get("report_path") or ""):
                found += findings(j["report_path"], tid)
        if why:
            reason = "; ".join(why)
            print(f"FAIL {tid}: {reason}")
            if os.path.isfile(task_file) and not any(w.startswith(("no verifier", "no hunter")) for w in why):
                rc_a, out_a, err_a = run([sys.executable, script(root, "reef-attempt"), task_file, reason[:300]], os.path.dirname(task_file))
                att = re.search(r"attempt=(\d+)/(\d+)", out_a or "")
                print(f"  attempt counted: {att.group(0) if att else (err_a or out_a).strip().splitlines()[-1][:120] if (err_a or out_a).strip() else rc_a}")
            return 1, found
        if row:
            print(f"CLOSED {tid} (in {wt})")
        else:
            print(f"READY TO MERGE {tid} ({wt}) — /reef-task step 4: commit in the worktree, merge --no-ff into the feature branch, status done, its journal block in the task's Log")
        return 0, found


# ---------------------------------------------------------------- row (v3 phase 5b)
def row_module(root):
    import importlib.machinery
    sys.dont_write_bytecode = True
    return importlib.machinery.SourceFileLoader("reef_row", script(root, "reef-row.py")).load_module()


def cmd_row(root, key):
    """ONE workflow for a row (v3 phase 5b): the row's open tasks in id order, each implemented, gated, judged on the critical
    path and closed in place by the mechanic before the next starts; then the full gate and converge, merge-base + push + PR,
    the critical path's guard pass and security, and the one reviewer. The orchestrator makes three calls per row: this,
    the Workflow tool, settle. Refused at the owner's steps (plan, approval), at the scripts' (merge, close), with a task of
    the row in flight, and while graph mode is off."""
    if not gate_ok(root):
        die("graph mode is OFF: no .reef/graph/gate.json with ok=true — run `reef-graph-run.py probe`, hand .reef/graph/probe.js to the "
            "Workflow tool, then `probe-check` its return value. Chat mode (/reef-task, /reef-review) keeps every guarantee meanwhile.", 1)
    rm = row_module(root)
    st, rc = rm.state_of(root, key)
    if rc != 0:
        die(f"row {key}: {st.get('detail') or 'unknown'}", 2)
    if st["state"] not in ("build", "evidence", "review"):
        print(f"row {st['row']}: {st['state']} — {st['detail']} · not the driver's step · next: {st['next']}")
        return 1
    main = rm.main_checkout(root)
    cfg = rm.config(main)
    co, slug, fdir, rid = rm.find_folder(main, cfg, key)
    prefix = str((cfg.get("branches") or {}).get("feature_prefix", "feat/") or "feat/")
    base = str((cfg.get("branches") or {}).get("base", "main") or "main")
    rc, branch, _ = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], co)
    if branch.strip() != prefix + slug:
        print(f"row {rid}: no feature worktree on {prefix}{slug} (the folder is read from {co}) — /reef-plan {rid} creates it")
        return 1
    tasks = []
    for p in sorted(glob.glob(os.path.join(fdir, "tasks", "*.md"))):
        m = re.match(r"(R?)(\d+)-", os.path.basename(p))
        if m:
            tasks.append((m.group(1) == "R", int(m.group(2)), m.group(1) + m.group(2), p))
    tasks.sort()
    for _, _, tid, p in tasks:
        with open(p, encoding="utf-8") as f:
            if re.search(r"^status:\s*blocked", f.read(), re.M):
                print(f"row {rid}: task {tid} is blocked (at the cap or parked) — the owner unblocks it (attempts: 0, status: pending, last_failure_sig: \"\")")
                return 1
    flying = [tid for _, _, tid, _ in tasks if os.path.isfile(os.path.join(main, ".reef", "inflight", tid))]
    if flying:
        print(f"row {rid}: in flight: {', '.join(flying)} — a workflow may be running; the tick frees a stale marker after loop.inflight_stale_minutes")
        return 1
    rc, pout, _ = run([sys.executable, script(root, "reef-tier.py"), "path"] + [p for _, _, _, p in tasks], co)
    critical = pout.strip().startswith("path: critical")
    report_dir = os.path.join("/tmp", f"reef-graph-{hashlib.sha1(root.encode()).hexdigest()[:8]}")
    os.makedirs(report_dir, exist_ok=True)
    items = []
    for _, _, tid, p in tasks:
        it = task_item(root, tid, p, False, report_dir)
        if isinstance(it, str):
            print(f"skipped {it} — the row runs up to it")
            break
        it["close_prompt"] = (
            f"REEF-TASK: {it['task']}\nMechanic: the task's work is in {it['worktree']} (uncommitted). (1) Write the task's journal block to "
            f"{report_dir}/journal-{tid}.md: ONE runlog row `| {tid} | <author model> | <verifier or -> | <attempts> | PASS | <the ACs met> | - |` from the "
            f"hand-back {it['worktree']}/.reef/ci-local/handback-{tid}.md and `python3 scripts/reef-cost.py growth {tid} --repo {main}` (its growth as "
            f"the Orchestrator cell or `· growth N` on Result). (2) In the feature worktree {co}, with a 10-minute timeout and the output to a file: "
            f"`python3 scripts/reef-merge-close {it['task']} --subject \"<type>: <the task's title after the dash>\" --journal {report_dir}/journal-{tid}.md "
            f"--repo {co}` — closed is true only when its exit was 0; output is its last 10 lines. Change nothing else. Return the JSON only.")
        items.append(it)
    if not items:
        return 1
    heaviest = items[-1]["task"]
    row = {
        "row": rid, "feature": slug, "worktree": co, "main": main, "base": base, "path": "critical" if critical else "fast",
        "evidence_prompt": f"REEF-FEATURE: {slug}\nMechanic, in {co}, each output to a file: (1) sh scripts/reef-gate.sh full --failures — its exit code in gate_exit and, "
                           f"when red, the failing block (under 60 lines) in notes; (2) python3 scripts/reef-converge {slug} --repo {co} — its exit code in converge_exit, "
                           f"its `missing`/`contradicts` lines in notes; (3) python3 scripts/reef-evidence.py --repo {co} — its one line in evidence. Change no file. Return the JSON only.",
        "pr_prompt": f"REEF-FEATURE: {slug}\nMechanic, in {co}: (1) python3 scripts/reef-merge-base --repo {co} — exit 2 is a conflict for a person: number null, "
                     f"say so in output, stop; (2) git push -u origin {prefix}{slug}; (3) `gh pr view --json number` — none: `gh pr create --fill --base {base}`; "
                     f"no remote or no gh: number null, say so. head is `git rev-parse HEAD` here. Change no file. Return the JSON only.",
        "review_prompt": f"REEF-FEATURE: {slug}\nReview the feature {slug}: folder {fdir}, worktree {co}, PR head {{HEAD}} — against its SPEC.md, its diff "
                         f"against {base}, and every Proof row against the evidence (`python3 scripts/reef-evidence.py {{HEAD}}` in {co}). Write your report FILE to "
                         f"{report_dir}/review-{slug}.md: first line `HEAD: <12 hex>`, last line `VERDICT: GREEN|FAIL`; return verdict and report_path.",
        "guard_prompt": f"REEF-TASK: {heaviest}\nREEF-FEATURE: {slug}\npass=guard on the whole feature diff (`git diff {base}...HEAD` in {co}, read-only): "
                        f"how can every check be green while the defect happens? Write your report FILE to {report_dir}/guard-{slug}.md; return verdict (FAIL iff a BLOCKER) and report_path.",
        "security_prompt": f"REEF-FEATURE: {slug}\nSecurity review of the feature diff (`git diff {base}...HEAD` in {co}, read-only). Write your report FILE to "
                           f"{report_dir}/security-{slug}.md ending with `VERDICT: PASS|FAIL`; return verdict and report_path.",
    }
    tasks_json, row_json = json.dumps(items, indent=1), json.dumps(row, indent=1)
    js = f"""export const meta = {{
  name: 'reef-row',
  description: 'Reef row {rid} ({slug}): its tasks in order, each closed in place; the evidence; the PR; the one review — in fresh contexts',
  phases: [{{ title: 'Tasks' }}, {{ title: 'Evidence' }}, {{ title: 'PR' }}, {{ title: 'Review' }}],
}}
const ROW = {row_json}
const TASKS = {tasks_json}
const SNAP = {json.dumps(SNAP_SCHEMA)}
const RESNAP = {json.dumps(RESNAP_SCHEMA)}
const JUDGE = {json.dumps(JUDGE_SCHEMA)}
const REVIEW = {json.dumps(REVIEW_SCHEMA)}
const CLOSE = {json.dumps(CLOSE_SCHEMA)}
const EVIDENCE = {json.dumps(EVIDENCE_SCHEMA)}
const PR = {json.dumps(PR_SCHEMA)}
const opt = (o) => Object.fromEntries(Object.entries(o).filter(([k, v]) => v !== null && v !== undefined))
const out = {{ row: ROW.row, feature: ROW.feature, worktree: ROW.worktree, tasks: [], evidence: null, pr: null, guard: null, security: null, review: null, stopped: null }}
log(`reef row ${{ROW.row}} (${{ROW.feature}}, ${{ROW.path}} path): ${{TASKS.length}} task(s) in order: ${{TASKS.map(t => t.id).join(', ')}}`)
for (const t of TASKS) {{
  if (t.implement_prompt) await agent(t.implement_prompt, opt({{ label: `implement:${{t.id}}`, phase: 'Tasks', agentType: 'reef:implementer', model: t.author_model, effort: t.effort }}))
  const gate = await agent(t.gate_prompt, {{ label: `gate:${{t.id}}`, phase: 'Tasks', agentType: 'reef:mechanic', schema: SNAP, effort: 'low' }})
  let judges = []
  if (gate.gate_exit === 0 && t.judge) {{
    const thunks = [() => agent(t.verifier_prompt, opt({{ label: `verify:${{t.id}}`, phase: 'Tasks', agentType: 'reef:verifier', schema: JUDGE, model: t.verifier_model }})).then(v => ({{ role: 'verifier', ...v }}))]
    if (t.hunter) thunks.push(() => agent(t.hunter_prompt, opt({{ label: `hunt:${{t.id}}`, phase: 'Tasks', agentType: 'reef:loophole-hunter', schema: JUDGE, model: t.adversary_model }})).then(h => ({{ role: 'hunter', ...h }})))
    judges = (await parallel(thunks)).filter(Boolean)
  }}
  const after = judges.length
    ? (await agent(t.resnap_prompt, {{ label: `snapshot:${{t.id}}`, phase: 'Tasks', agentType: 'reef:mechanic', schema: RESNAP, effort: 'low' }})).snapshot
    : gate.snapshot
  const ok = gate.gate_exit === 0 && String(gate.handback_check || '').toLowerCase().startsWith('ok')
    && (!t.judge || (judges.length && judges.every(j => j.verdict === 'PASS') && after === gate.snapshot))
  const close = ok ? await agent(t.close_prompt, {{ label: `close:${{t.id}}`, phase: 'Tasks', agentType: 'reef:mechanic', schema: CLOSE, effort: 'low' }}) : null
  out.tasks.push({{ task: t.id, worktree: t.worktree, task_file: t.task, judge: t.judge, hunter: t.hunter, gate, judges, snapshot_after: after, close }})
  if (!ok || !close || !close.closed) {{ out.stopped = `task ${{t.id}}`; return out }}
}}
out.evidence = await agent(ROW.evidence_prompt, {{ label: 'evidence', phase: 'Evidence', agentType: 'reef:mechanic', schema: EVIDENCE, effort: 'low' }})
if (out.evidence.gate_exit !== 0) {{ out.stopped = 'evidence'; return out }}
if (out.evidence.converge_exit !== 0) {{ out.stopped = 'converge'; return out }}
out.pr = await agent(ROW.pr_prompt, {{ label: 'pr', phase: 'PR', agentType: 'reef:mechanic', schema: PR, effort: 'low' }})
const head = out.pr.head || ''
if (ROW.path === 'critical') {{
  const [g, s] = await parallel([
    () => agent(ROW.guard_prompt, {{ label: 'guard', phase: 'Review', agentType: 'reef:loophole-hunter', schema: JUDGE }}),
    () => agent(ROW.security_prompt, {{ label: 'security', phase: 'Review', agentType: 'reef:security', schema: JUDGE }}),
  ])
  out.guard = g; out.security = s
  if (g.verdict !== 'PASS' || s.verdict !== 'PASS') {{ out.stopped = 'guard'; return out }}
}}
out.review = await agent(ROW.review_prompt.split('{{HEAD}}').join(head.slice(0, 12)), {{ label: 'review', phase: 'Review', agentType: 'reef:acceptance', schema: REVIEW }})
return out
"""
    d = os.path.join(root, GRAPH_DIR)
    os.makedirs(d, exist_ok=True)
    h = hashlib.sha1((tasks_json + row_json).encode()).hexdigest()[:10]
    path = os.path.join(d, f"row-{slug}-{h}.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    print(f"row: {rid} ({slug}) tasks in order: {', '.join(i['id'] for i in items)} · path: {row['path']}  reports: {report_dir}")
    print(f"script: {path}")
    print(f"next: call the Workflow tool with scriptPath {path}; when it completes, `reef-graph-run.py settle <the output file its completion notice names>`")
    return 0


def settle_row(root, res):
    """A row's result: every task's close checked on disk, the evidence re-read, the critical path's guard pass recorded,
    the review report copied and recorded by reef-record; then the one bare merge command for the orchestrator (the guard
    checks the record, the base tip and the evidence there — a script's `gh pr merge` would pass no hook), or ROW WAITS."""
    rm = row_module(root)
    main = rm.main_checkout(root)
    cfg = rm.config(main)
    rid, slug, co = str(res.get("row")), str(res.get("feature") or ""), str(res.get("worktree") or "")
    failed = 0
    for r in res.get("tasks") or []:
        close, task_file = r.get("close") or {}, str(r.get("task_file") or "")
        extra = []
        if not close.get("closed"):
            extra.append("not closed: " + (str(close.get("output") or "").strip().splitlines() or ["the close step did not run"])[-1][:200])
        elif not task_file or os.path.isfile(task_file) or not os.path.isfile(os.path.join(os.path.dirname(task_file), "done", os.path.basename(task_file))):
            extra.append("not closed on disk: the task file is not under done/ (the mechanic's claim is not the evidence)")
        else:
            r = dict(r, task_file=os.path.join(os.path.dirname(task_file), "done", os.path.basename(task_file)))   # closed: the file moved
        f, found = settle_task(root, r, extra, row=True)
        failed += f
        for line in found:
            print(line)
    if failed:
        print(f"ROW {rid} WAITS build: {failed} task(s) failed — the attempt is counted; the next `row {rid}` re-dispatches with the failure under the cap")
        return 1
    ev = res.get("evidence") or {}
    if res.get("stopped") in ("evidence", "converge") or not ev:
        print(f"ROW {rid} WAITS evidence: {res.get('stopped') or 'no result'} — {str(ev.get('notes') or ev.get('evidence') or '')[:300]}")
        return 1
    rc, out, _ = run([sys.executable, script(root, "reef-evidence.py"), "--repo", co], co)
    if rc != 0:
        print(f"ROW {rid} WAITS evidence: {(out.strip().splitlines() or ['no evidence'])[0]} — sh scripts/reef-gate.sh full in {co}")
        return 1
    rc, head, _ = run(["git", "rev-parse", "HEAD"], co)
    head = head.strip()
    os.makedirs(os.path.join(co, ".reef", "ci-local"), exist_ok=True)

    def copied(rec, name):
        rp = str((rec or {}).get("report_path") or "")
        if not os.path.isfile(rp):
            return None
        dest = os.path.join(co, ".reef", "ci-local", name)
        with open(rp, "rb") as a, open(dest, "wb") as b:
            b.write(a.read())   # a copy: the agent's words unchanged
        return dest
    for role, name in (("guard", f"guard-{slug}.md"), ("security", f"security-{slug}.md")):
        rec = res.get(role)
        if rec:
            dest = copied(rec, name)
            if rec.get("verdict") != "PASS" or not dest:
                print(f"ROW {rid} WAITS review: {role} {rec.get('verdict')} — {str(rec.get('summary', ''))[:160]} — its findings go on the rollup")
                return 1
            if role == "guard":
                rc, out, err = run([sys.executable, script(root, "reef-adversarial"), "--feature", slug, "guard", dest], co)
                if rc != 0:
                    print(f"ROW {rid} WAITS review: the guard-pass record was refused — {(err or out).strip().splitlines()[-1][:160] if (err or out).strip() else rc}")
                    return 1
    rev = res.get("review") or {}
    dest = copied(rev, f"review-{slug}-{head[:12]}.md")
    if res.get("stopped") or not dest:
        print(f"ROW {rid} WAITS review: {res.get('stopped') or 'no report file'} — /reef-review {slug}")
        return 1
    verdict = "GREEN" if rev.get("verdict") == "GREEN" else "FAIL"
    pr = res.get("pr") or {}
    n = pr.get("number")
    if not n:
        print(f"ROW {rid} REVIEWED {verdict} at {head[:12]}, no PR ({str(pr.get('output') or '')[:160] or 'no remote'}) — nothing recorded; the owner merges")
        return 0 if verdict == "GREEN" else 1
    rc, out, err = run([sys.executable, script(root, "reef-record"), slug, verdict, "--pr", str(n), "--report", dest, "--root", main], co, timeout=120)
    if rc != 0:
        print(f"ROW {rid} WAITS review: the record was refused — {(err or out).strip().splitlines()[-1][:200] if (err or out).strip() else rc}")
        return 1
    if verdict == "FAIL":
        print(f"ROW {rid} WAITS review: FAIL — {str(rev.get('summary', ''))[:160]} — its findings go on the rollup (reef-attempt), then /reef-task")
        return 1
    if rm.merge_by(cfg) == "loop":
        print(f"ROW {rid} READY TO MERGE (PR #{n} at {head[:12]}) — run it bare, nothing chained: gh pr merge {n} --squash --delete-branch ; then python3 scripts/reef-row.py next {rid}")
    else:
        print(f"ROW {rid} REVIEWED GREEN (PR #{n} at {head[:12]}) — the owner merges (merge.by: human)")
    return 0


def main(argv):
    repo = argv[argv.index("--repo") + 1] if "--repo" in argv else "."
    if "--repo" in argv:
        i = argv.index("--repo")
        argv = argv[:i] + argv[i + 2:]
    root = root_of(repo)
    if not argv:
        die("usage: reef-graph-run.py probe | probe-check <results.json> | generate [--tasks a,b] | row <row-id|slug> | settle <results.json>  [--repo DIR]")
    cmd = argv[0]
    # a results path given relative to the project (as the `next:` lines print it) resolves against the project
    if len(argv) >= 2 and not os.path.isabs(argv[1]) and not os.path.isfile(argv[1]) and os.path.isfile(os.path.join(root, argv[1])):
        argv[1] = os.path.join(root, argv[1])
    if not os.path.isfile(os.path.join(root, ".reef", "config.json")):
        die(f"{root} is not a Reef project (no .reef/config.json)")
    if cmd == "probe":
        return cmd_probe(root)
    if cmd == "probe-check" and len(argv) >= 2:
        return cmd_probe_check(root, argv[1])
    if cmd == "generate":
        only = argv[argv.index("--tasks") + 1].split(",") if "--tasks" in argv else None
        return cmd_generate(root, [x.strip() for x in only] if only else None)
    if cmd == "row" and len(argv) >= 2:
        return cmd_row(root, argv[1])
    if cmd == "settle" and len(argv) >= 2:
        return cmd_settle(root, argv[1])
    die(f"unknown command {cmd!r}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
