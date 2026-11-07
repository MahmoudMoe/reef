"""Hard tests, round three — a CRASH-RESUME end-to-end property over a whole row.

One fixture project (file queue, no issues) with one queued row. A driver reads ONLY `reef-loop.py tick --json` (and, for a
row past its build, `reef-row.py state --json`, the loop skill's "a row's one next step") and performs the step it names with
the real scripts: the planner's files + reef-plan-check (the stamp), reef-approval --owner (the gate), reef-attempt + the
guard's Agent dispatch (the in-flight marker, the odometer), the implementer's code and hand-back, reef-claims --handback,
reef-gate fast, reef-merge-close, reef-merge-base, gh pr create, reef-gate full, the acceptance report + reef-record, the
guard's `gh pr merge` check, the merge, and the close (adr-number, the archive, reef-queue journal, worktrees removed). Only
the agents' outputs and gh are faked (gh keeps its PRs in a JSON file and merges into the base locally).

The golden run records the end state. Then for every step boundary k and each fault that applies there, the project is
restored to its state before step k and re-run from there with the fault: a crash part-way through the step (a prefix of its
effects), one failed gh call, a stale older copy of the task files in a task worktree, or the same step run twice. The tick
then drives to the end. The end state must equal the golden one, or Reef must stop on a named BROKEN or wait — never a
different end state, never a second PR, never a doubled attempt or journal row.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import write, IDENTITY  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, "scripts", "reef-guard.py")
SCRIPTS = ("reef_common.py", "reef-graph-run.py", "reef-graph.py", "reef-loop.py", "reef-queue.py", "reef-plan-check.py", "reef-attempt",
           "reef-claims.py", "reef-adversarial", "reef-snapshot.sh", "reef-gate.sh", "reef-row.py", "reef-evidence.py", "reef-tier.py",
           "reef-merge-close", "reef-record", "reef-cost.py", "reef-handoff", "reef-merge-base", "reef-approval.py")
SLUG = "crash-row-one"
ROW = "1"
TASK = """---
id: {id}
feature: crash-row-one
status: pending
complexity: mech
effort: medium
blocked-by: {blocked}
resources: []
tier: light
verify: gate-only
attempts: 0
dispatches: 0
last_failure_sig: ""
---
# {id} — {title}

## Scope
x

## Acceptance Criteria
- AC-1 (FR-1): it works

## Proof
| AC | Proof |
|---|---|
| AC-1 | `{proof}` |

## Out of scope

## Log
"""
TASKS = (("101", "slice", "the slice", "[]", "test_it_works"), ("102", "second", "the second", "[101]", "test_second_works"))
SPEC = ("# crash row one\nRow: 1\n\n## Scope\nOne slice.\n\n## Non-goals\n- none\n\n## Already shipped\nnone\n\n"
        "## Requirements\n- FR-1 [backend]: it works.\n\n## Success criteria\n- SC-1: green.\n\n## Architecture impact\nnone\n")
# the implementer's work per task: files and the hand-back's one claim
WORK = {"101": {"src/a.py": "a = 2\n", "tests/test_a.py": "def test_it_works():\n    pass\n"},
        "102": {"src/b.py": "b = 1\n", "tests/test_b.py": "def test_second_works():\n    pass\n"}}
CLAIM = {"101": "a is two — true at src/a.py:1", "102": "b exists — true at src/b.py:1"}

FAKE_GH = r'''#!/usr/bin/env python3
"""fake gh: PRs live in $GH_STATE (JSON); a merge squashes the head into the base in $GH_REPO (the forge and the base are one);
`fail` in the state is a list of substrings — the first call whose argv matches one exits 1 once (HTTP 502)."""
import json, os, re, subprocess, sys
repo, state_p = os.environ["GH_REPO"], os.environ["GH_STATE"]
a = sys.argv[1:]
line = " ".join(a)
try:
    st = json.load(open(state_p))
except (OSError, ValueError):
    st = {"prs": [], "next": 7, "fail": [], "calls": []}
st.setdefault("calls", []).append(line)
def save():
    json.dump(st, open(state_p, "w"), indent=1)
for i, pat in enumerate(st.get("fail") or []):
    if pat in line:
        st["fail"].pop(i); st.setdefault("failed", []).append(line); save()
        sys.stderr.write("HTTP 502: Bad Gateway (fake)\n"); sys.exit(1)
save()
def g(*x, cwd=repo):
    return subprocess.run(["git", "-C", cwd, *x], capture_output=True, text=True)
rev = lambda x: g("rev-parse", x).stdout.strip()
def opt(name, default=None):
    return a[a.index(name) + 1] if name in a and a.index(name) + 1 < len(a) else default
def view(p):
    head = rev(p["head"]) if p["state"] == "OPEN" else p.get("merged_head", "")
    return {"number": p["number"], "state": p["state"], "headRefName": p["head"], "baseRefName": p["base"], "headRefOid": head,
            "url": f"https://github.com/o/r/pull/{p['number']}", "title": p["title"], "reviewDecision": ""}
def pick(fields, d):
    return {k: d.get(k) for k in fields.split(",")} if fields else d
if a[:2] == ["pr", "list"]:
    prs = st["prs"]
    state = opt("--state", "open").upper()
    if state != "ALL":
        prs = [p for p in prs if p["state"] == state]
    if opt("--base"):
        prs = [p for p in prs if p["base"] == opt("--base")]
    if opt("--head"):
        prs = [p for p in prs if p["head"] == opt("--head")]
    print(json.dumps([pick(opt("--json"), view(p)) for p in prs])); sys.exit(0)
if a[:2] == ["pr", "view"]:
    ident = a[2] if len(a) > 2 and not a[2].startswith("-") else None
    if ident:
        p = next((p for p in st["prs"] if str(p["number"]) == ident.lstrip("#")), None)
    else:
        br = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True).stdout.strip()
        p = next((p for p in reversed(st["prs"]) if p["head"] == br), None)
    if not p:
        sys.stderr.write("no pull requests found\n"); sys.exit(1)
    print(json.dumps(pick(opt("--json"), view(p)))); sys.exit(0)
if a[:2] == ["pr", "create"]:
    head = opt("--head") or subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True).stdout.strip()
    if any(p["head"] == head and p["state"] == "OPEN" for p in st["prs"]):
        sys.stderr.write(f'a pull request for branch "{head}" into branch "main" already exists\n'); sys.exit(1)
    n = st["next"]; st["next"] += 1
    st["prs"].append({"number": n, "head": head, "base": opt("--base", "main"), "state": "OPEN", "title": opt("--title", head)})
    save(); print(f"https://github.com/o/r/pull/{n}"); sys.exit(0)
if a[:2] == ["pr", "merge"]:
    p = next((p for p in st["prs"] if str(p["number"]) == a[2].lstrip("#")), None)
    if not p or p["state"] != "OPEN":
        sys.stderr.write("pull request is not open\n"); sys.exit(1)
    head = rev(p["head"])
    r = g("merge", "--squash", p["head"])
    if r.returncode != 0:
        g("reset", "--hard", "-q"); sys.stderr.write("merge failed: " + r.stderr); sys.exit(1)
    r = g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", f"{p['title']} (#{p['number']})")
    if r.returncode != 0:
        g("reset", "--hard", "-q"); sys.stderr.write("commit failed: " + r.stdout + r.stderr); sys.exit(1)
    p.update(state="MERGED", merged_head=head); save()
    print(f"merged #{p['number']}"); sys.exit(0)
if a[:1] == ["api"]:
    m = re.search(r"commits/([0-9a-f]+)/check-runs", a[1])
    if m:
        print(json.dumps({"total_count": 0, "check_runs": []})); sys.exit(0)
    m = re.search(r"git/commits/([0-9a-f]+)", a[1])
    if m:
        print(rev(m.group(1) + "^{tree}")); sys.exit(0)
    m = re.search(r"git/ref/heads/(\S+)", a[1])
    if m:
        print(rev(m.group(1))); sys.exit(0)
sys.stderr.write("fake gh: unknown call " + line + "\n"); sys.exit(1)
'''


FIXED_DATE = "2026-11-01T00:00:00Z"   # every commit's date: the same content makes the same sha in every run (the fingerprint)


GITENV = dict(os.environ, GIT_AUTHOR_DATE=FIXED_DATE, GIT_COMMITTER_DATE=FIXED_DATE)


def git(d, *a):
    """`git -C d …` with the test identity and the fixed date."""
    return subprocess.run(["git", "-C", d, *IDENTITY, *a], capture_output=True, text=True, env=GITENV)


class Stop(Exception):
    """Reef stopped on a named BROKEN or wait: an acceptable end of a faulted run when it is NAMED."""


class Stall(AssertionError):
    """The tick names nothing and the row is not closed: Reef sits silently in a state that is neither the end nor a named wait."""


class Driver:
    """The orchestrator, made of the tick and the real scripts. One instance per project directory."""

    def __init__(self, tmp):
        self.tmp = tmp
        self.main = os.path.join(tmp, "main")
        self.co = os.path.join(self.main, ".reef", "worktrees", SLUG)
        self.bin = os.path.join(tmp, "bin")
        self.state = os.path.join(tmp, "gh.json")
        self.env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"], GH_REPO=self.main, GH_STATE=self.state,
                        REEF_GH_TIMEOUT="10", GIT_AUTHOR_DATE=FIXED_DATE, GIT_COMMITTER_DATE=FIXED_DATE)
        for k in ("REEF_RUNNER", "REEF_TRANSCRIPT", "CLAUDE_PLUGIN_ROOT"):
            self.env.pop(k, None)
        self.log = []

    # ---------------- the fixture ----------------
    def build(self):
        os.makedirs(os.path.join(self.main, "scripts"))
        for n in SCRIPTS:
            shutil.copy(os.path.join(ROOT, "scripts", n), os.path.join(self.main, "scripts", n))
        write(self.main, ".reef/config.json", json.dumps({
            "gates": {"full": "echo '1 passed'", "fast": "echo '1 passed'"}, "ci": {"feature_gate": "local"}, "merge": {"by": "loop"},
            "branches": {"base": "main", "release": "release"}, "graph": {"mode": "chat"}, "worktree": {"dir": ".reef/worktrees"},
            "paths": {"queue": "reef/queue.md", "features": "reef/features", "runlog": "reef/journal.md"}}))
        write(self.main, ".reef/version", "0.6.0\n")
        write(self.main, ".gitignore", ".reef/worktrees/\n.reef/approvals/\n.reef/review/\n.reef/evidence/\n.reef/ci-local/\n.reef/inflight/\n"
                                       ".reef/verifying/\n.reef/graph/\n.reef/loop.json\n.reef/run/\n.reef/hold*\n.reef/cost/\n.reef/locks/\n"
                                       ".reef/status.html\ntasks/.plan-review.json\nreef/features/*/tasks/.plan-review.json\nscripts/__pycache__/\n")
        write(self.main, "reef/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n"
                                          "| 1 | crash row one | | planned | 1 | |\n")
        write(self.main, "reef/queue-archive.md", "# Queue archive\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n")
        write(self.main, "reef/journal.md", "# Journal\n| Task | Implementer | Verifier | Attempts | Result | ACs | Escaped defects |\n|---|---|---|---|---|---|---|\n")
        write(self.main, "CLAUDE.md", "# brief\n")
        write(self.main, "src/a.py", "a = 1\n")
        write(self.main, "reef/architecture/adr/README.md", "# ADRs\n")
        git(self.main, "init", "-q", "-b", "main")
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            git(self.main, "config", k, v)
        git(self.main, "add", "-A")
        git(self.main, "commit", "-qm", "init")
        git(self.main, "remote", "add", "origin", "https://github.com/o/r.git")
        os.makedirs(self.bin)
        with open(os.path.join(self.bin, "gh"), "w") as f:
            f.write(FAKE_GH)
        os.chmod(os.path.join(self.bin, "gh"), 0o755)
        with open(self.state, "w") as f:
            json.dump({"prs": [], "next": 7, "fail": [], "calls": []}, f)

    # ---------------- reading ----------------
    def py(self, script, *args, cwd=None, inp=None):
        return subprocess.run([sys.executable, os.path.join(self.main, "scripts", script), *args], cwd=cwd or self.main,
                              capture_output=True, text=True, env=self.env, input=inp, timeout=120)

    def tick(self):
        r = self.py("reef-loop.py", "tick", "--json")
        try:
            return json.loads(r.stdout)
        except ValueError:
            raise AssertionError(f"tick printed no JSON (exit {r.returncode}): {r.stdout[-800:]} {r.stderr[-800:]}")

    def row_state(self):
        r = self.py("reef-row.py", "state", ROW, "--json")
        try:
            return json.loads(r.stdout)
        except ValueError:
            raise AssertionError(f"reef-row printed no JSON (exit {r.returncode}): {r.stdout[-500:]} {r.stderr[-500:]}")

    def gh_state(self):
        with open(self.state) as f:
            return json.load(f)

    def arm_gh_failure(self, pattern):
        st = self.gh_state()
        st.setdefault("fail", []).append(pattern)
        with open(self.state, "w") as f:
            json.dump(st, f)

    def task_path(self, tid, where=None):
        base = os.path.join(where or self.co, "reef", "features", SLUG, "tasks")
        name = next(f"{t[0]}-{t[1]}.md" for t in TASKS if t[0] == tid)
        for p in (os.path.join(base, name), os.path.join(base, "done", name)):
            if os.path.isfile(p):
                return p
        return os.path.join(base, name)

    # ---------------- choosing the step from the tick ----------------
    def choose(self, t):
        """(step, arg) from the tick: the loop skill's order — a broken read stops, the owner's gate, plan, verify/close, dispatch,
        an agent's return, the review, the row's own next step (evidence, review, merge, close)."""
        if t.get("broken"):
            return "broken", "; ".join(t["broken"])
        for a in t.get("awaiting") or []:
            m = re.search(r"— (python3 scripts/reef-approval\.py --owner \"(.+)\")$", a)
            if m:
                return "approve", m.group(2)
            if a.startswith(SLUG) and ("machine review" in a or "plan review" in a):
                return "plan_review", SLUG
        if t.get("awaiting"):
            return "wait", "awaiting: " + "; ".join(t["awaiting"])
        if t.get("rows_to_plan"):
            return "plan", t["rows_to_plan"][0]
        if t.get("verify_now"):
            return "verify", str(t["verify_now"][0])
        if t.get("close_now"):
            return "verify", str(t["close_now"][0])
        if t.get("dispatch_now"):
            return "dispatch", str(t["dispatch_now"][0])
        live = [i for i in t.get("in_flight") or [] if not str(i).startswith("verifying:")]
        if live:
            return "agent", str(live[0])
        if t.get("parked"):
            return "wait", f"parked: {t['parked']}"
        if t.get("rows_to_review"):
            return "pr", t["rows_to_review"][0]
        if t.get("prs_to_review") or t.get("rows_to_close") or t.get("building"):
            s = self.row_state()
            st, nxt = s.get("state"), s.get("next") or ""
            if st == "evidence" and nxt.startswith("sh scripts/reef-gate.sh full"):
                return "evidence", None
            if st == "review" and nxt.startswith("/reef-review"):
                return "review", None
            if st == "merge" and nxt.startswith("gh pr merge"):
                return "merge", nxt
            if st == "merge" and nxt.startswith("/reef-review"):
                return "pr", ROW
            if st == "close":
                return "close", None
            if st == "build" and nxt.startswith("python3 scripts/reef-loop.py tick"):
                return "stall", f"the tick names nothing; reef-row says `{st}: {nxt}` ({s.get('detail')})"
            return "wait", f"row {st}: {nxt} ({s.get('detail')})"
        return None, None

    # ---------------- the steps, each with its crash prefixes ----------------
    def step(self, name, arg, crash=None):
        getattr(self, "do_" + name)(arg, crash)

    def do_broken(self, arg, crash):
        raise AssertionError("not a step")

    def do_plan(self, row, crash):
        """/reef-plan on the fast path: the worktree first, the planner's files there, the check (the stamp)."""
        if not os.path.isdir(self.co):
            r = git(self.main, "worktree", "add", "-q", "-b", f"feat/{SLUG}", self.co, "main")
            assert r.returncode == 0, r.stderr
        write(self.co, f"reef/features/{SLUG}/SPEC.md", SPEC)
        for tid, short, title, blocked, proof in TASKS:
            write(self.co, f"reef/features/{SLUG}/tasks/{tid}-{short}.md", TASK.format(id=tid, title=title, blocked=blocked, proof=proof))
        if crash == "files":
            return
        git(self.co, "add", "-A")
        git(self.co, "commit", "-qm", f"plan: {SLUG}")
        self.do_plan_review(SLUG, None)

    def do_plan_review(self, slug, crash):
        """The fast path's machine review is the check alone: it writes the stamp."""
        if git(self.co, "status", "--porcelain", "reef/features").stdout.strip():
            git(self.co, "add", "-A", "reef/features")
            git(self.co, "commit", "-qm", f"plan: {SLUG}")
        r = self.py("reef-plan-check.py", self.co, cwd=self.co)
        assert r.returncode == 0, r.stdout + r.stderr

    def do_approve(self, question, crash):
        r = self.py("reef-approval.py", "--owner", question)
        assert r.returncode == 0 and "approved" in r.stdout, r.stdout + r.stderr

    def do_dispatch(self, tid, crash):
        """reef-attempt prints the dispatch; the guard (the PreToolUse hook on the Agent call) marks it in flight."""
        task = self.task_path(tid)
        r = self.py("reef-attempt", task, cwd=self.co)
        if r.returncode != 0:
            raise Stop(f"reef-attempt {tid}: exit {r.returncode}: {r.stdout.strip()[-300:]}")
        model = re.search(r"^author:\s*(?:model=)?(\S+)", r.stdout, re.M)
        header = re.search(r"^REEF-TASK: .*$", r.stdout, re.M)
        assert header, r.stdout
        if crash == "attempt-only":
            return
        tool_input = {"subagent_type": "reef:implementer", "prompt": header.group(0) + "\nimplement", "description": "implement"}
        if model:
            tool_input["model"] = model.group(1)
        g = subprocess.run([sys.executable, GUARD], input=json.dumps({"tool_name": "Task", "cwd": self.co, "tool_input": tool_input}),
                           capture_output=True, text=True, env=self.env, cwd=self.co)
        if g.returncode != 0:
            raise Stop(f"guard denied the dispatch of {tid}: {g.stderr.strip()[-400:]}")

    def do_agent(self, tid, crash):
        """The implementer returns: its code and its hand-back; then the orchestrator `rm`s the marker."""
        for rel, text in WORK[tid].items():
            write(self.co, rel, text)
        if crash == "code-only":
            return
        write(self.co, f".reef/ci-local/handback-{tid}.md", f"RUN: agent=implementer task={tid}\n{CLAIM[tid]}\n")
        if crash == "no-rm":
            return
        for d in (self.co, self.main):
            p = os.path.join(d, ".reef", "inflight", tid)
            if os.path.exists(p):
                os.remove(p)

    def do_verify(self, tid, crash):
        """gate-only: the hand-back checked, the fast gate in the row's worktree, then reef-merge-close in place."""
        hb = os.path.join(self.co, ".reef", "ci-local", f"handback-{tid}.md")
        r = self.py("reef-claims.py", "check", "--handback", hb, "--repo", self.co, cwd=self.co)
        assert r.returncode == 0, r.stdout + r.stderr
        for d in (self.co, self.main):   # the hand-back is in: the marker is history (reef-task § 2)
            p = os.path.join(d, ".reef", "inflight", tid)
            if os.path.exists(p):
                os.remove(p)
        r = subprocess.run(["sh", "scripts/reef-gate.sh", "fast", "--failures"], cwd=self.co, capture_output=True, text=True, env=self.env)
        assert r.returncode == 0, r.stdout + r.stderr
        if crash == "gated":
            return
        journal = write(self.tmp, f"journal-{tid}.md", f"| {tid} | opus | - | 0 | gate green | AC-1 | - |\n")
        task = self.task_path(tid)
        name = os.path.basename(task)
        if crash in ("fm", "mv"):
            # reef-merge-close killed after it rewrote the task file (status done + the journal block), [and after its git mv];
            # its first effect is the recovery note the next close restores from
            gd = subprocess.run(["git", "rev-parse", "--absolute-git-dir"], cwd=self.co, capture_output=True, text=True).stdout.strip()
            with open(os.path.join(gd, f"reef-close-{name[:-3]}.json"), "w") as f:
                json.dump({"task": task, "dest": os.path.join(os.path.dirname(task), "done", name), "text": open(task).read()}, f)
            git(self.co, "add", "-A")
            text = open(task).read().replace("status: in-progress", "status: done").replace("status: pending", "status: done")
            text += f"\n<!-- journal -->\n{open(journal).read().strip()}\n<!-- /journal -->\n"
            with open(task, "w") as f:
                f.write(text)
            if crash == "mv":
                dest = os.path.join(os.path.dirname(task), "done", name)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                git(self.co, "mv", task, dest)
            return
        r = subprocess.run([sys.executable, os.path.join(self.co, "scripts", "reef-merge-close"), task, "--subject", f"feat: {name[:-3]}",
                            "--journal", journal, "--repo", self.co], capture_output=True, text=True, cwd=self.co, env=self.env)
        if r.returncode != 0:
            raise Stop(f"reef-merge-close {tid}: exit {r.returncode}: {(r.stdout + r.stderr).strip()[-400:]}")

    def do_pr(self, row, crash):
        """/reef-review step 1: the base's tip in, push (the fake forge reads the local branch), the PR — `gh pr view` first."""
        r = subprocess.run([sys.executable, os.path.join(self.co, "scripts", "reef-merge-base"), "--repo", self.co], cwd=self.co,
                           capture_output=True, text=True, env=self.env)
        if r.returncode != 0:
            raise Stop(f"reef-merge-base: exit {r.returncode}: {(r.stdout + r.stderr).strip()[-300:]}")
        if crash == "merged-base":
            return
        v = subprocess.run(["gh", "pr", "view", "--json", "number,state"], cwd=self.co, capture_output=True, text=True, env=self.env)
        if v.returncode == 0 and json.loads(v.stdout).get("state") == "OPEN":
            return   # update, never duplicate (reef-review § 1)
        c = subprocess.run(["gh", "pr", "create", "--fill", "--base", "main", "--head", f"feat/{SLUG}", "--title", f"feat: {SLUG}"],
                           cwd=self.co, capture_output=True, text=True, env=self.env)
        if c.returncode != 0:
            raise Stop(f"gh pr create: exit {c.returncode}: {c.stderr.strip()}")

    def do_evidence(self, arg, crash):
        r = subprocess.run(["sh", "scripts/reef-gate.sh", "full"], cwd=self.co, capture_output=True, text=True, env=self.env)
        assert r.returncode == 0, r.stdout + r.stderr

    def do_review(self, arg, crash):
        """The ONE reviewer's report, copied, recorded by reef-record against the forge's head."""
        head = git(self.co, "rev-parse", "HEAD").stdout.strip()
        rep = write(self.co, f".reef/ci-local/review-{SLUG}-{head[:12]}.md",
                    f"HEAD: {head[:12]}\nRUN: agent=acceptance feature={SLUG}\n- FR-1 PASS test_it_works\nVERDICT: GREEN\n")
        if crash == "report-only":
            return
        r = subprocess.run([os.path.join(self.co, "scripts", "reef-record"), SLUG, "GREEN", "--report", rep], cwd=self.co,
                           capture_output=True, text=True, env=self.env)
        if r.returncode != 0:
            raise Stop(f"reef-record: exit {r.returncode}: {(r.stdout + r.stderr).strip()[-300:]}")

    def do_merge(self, cmd, crash):
        """The row's one bare merge, through the guard's check first (as the PreToolUse hook would run it)."""
        g = subprocess.run([sys.executable, GUARD], input=json.dumps({"tool_name": "Bash", "cwd": self.main, "tool_input": {"command": cmd}}),
                           capture_output=True, text=True, env=self.env, cwd=self.main)
        if g.returncode != 0:
            raise Stop(f"guard denied `{cmd}`: {g.stderr.strip()[-400:]}")
        r = subprocess.run(cmd.split(), cwd=self.main, capture_output=True, text=True, env=self.env)
        if r.returncode != 0:
            raise Stop(f"`{cmd}`: exit {r.returncode}: {r.stderr.strip()}")

    def do_close(self, arg, crash):
        """reef-loop § 2.4 on the base, the single writer: adr-number, the row to the archive, the journal, the worktrees removed."""
        r = self.py("reef-queue.py", "adr-number", "--repo", self.main)
        assert r.returncode == 0 or "nothing to number" in r.stdout + r.stderr, r.stdout + r.stderr
        q = os.path.join(self.main, "reef", "queue.md")
        arch = os.path.join(self.main, "reef", "queue-archive.md")
        lines = open(q).read().splitlines(keepends=True)
        rowline = [l for l in lines if re.match(rf"^\|\s*{ROW}\s*\|", l)]
        if rowline:
            with open(q, "w") as f:
                f.write("".join(l for l in lines if l not in rowline))
            if rowline[0] not in open(arch).read():
                with open(arch, "a") as f:
                    f.write(rowline[0])
        if crash == "archived":
            return
        r = self.py("reef-queue.py", "journal", SLUG, "--repo", self.main)
        assert r.returncode == 0, r.stdout + r.stderr
        if crash == "journaled":
            return
        git(self.main, "add", "-A")
        git(self.main, "commit", "-qm", f"close row {ROW}: {SLUG}")
        if crash == "committed":
            return
        if os.path.isdir(self.co):
            git(self.main, "worktree", "remove", "--force", self.co)
        git(self.main, "worktree", "prune")
        git(self.main, "branch", "-D", f"feat/{SLUG}")

    # ---------------- the drive ----------------
    def drive(self, start=0, fault=None, max_steps=40, snaps=None, converged=None):
        """Tick → step until the tick names nothing. `fault` = (k, kind, detail) applied at the k-th step of this drive
        counted from `start`. Returns the list of (step, arg). Raises Stop on a named BROKEN / wait."""
        steps, broken_in_a_row, armed, last_stop = [], 0, False, None
        k = start
        for _ in range(max_steps):
            if snaps is not None:
                snaps(k)
            if fault and fault[0] == k and fault[1] in ("gh", "stale") and not armed:
                armed = True
                self.arm_gh_failure(fault[2]) if fault[1] == "gh" else self.plant_stale_copy()
            t = self.tick()
            name, arg = self.choose(t)
            if name is None:
                return steps
            if name == "broken":
                broken_in_a_row += 1
                self.log.append(("broken", arg))
                if broken_in_a_row > 2:
                    raise Stop(f"BROKEN: {arg}")
                continue   # a failed read is transient: the orchestrator ticks again
            broken_in_a_row = 0
            if name == "wait":
                raise Stop(f"wait: {arg}")
            if name == "stall":
                raise Stall(f"STALL after {self.log}: {arg}")
            crash = fault[2] if fault and fault[0] == k and fault[1] == "crash" else None
            try:
                self.step(name, arg, crash)
            except Stop as e:   # a step's named refusal: the orchestrator ticks again once; the same refusal twice is the stop
                self.log.append((name, arg, f"refused: {str(e)[:200]}"))
                if last_stop == str(e):
                    raise
                last_stop = str(e)
                continue
            last_stop = None
            self.check_invariants()
            steps.append((name, arg))
            self.log.append((name, arg, crash))
            if fault and fault[0] == k and fault[1] == "dup":
                try:
                    self.step(name, arg, None)
                    self.log.append((name, arg, "dup"))
                except (Stop, AssertionError) as e:   # the second run refused, named: that is the point of the fault
                    self.log.append((name, arg, f"dup refused: {str(e)[:200]}"))
            k += 1
            if converged is not None and converged(k):
                return steps
        raise AssertionError(f"no end after {max_steps} steps: {self.log[-6:]}")

    def check_invariants(self):
        """After every step: a GREEN record binds a head that carries the row's work, every task closed in it (an owner's
        obvious expectation: the review reviewed the code that merges)."""
        try:
            rec = json.load(open(os.path.join(self.main, ".reef", "review", f"{SLUG}.json")))
        except OSError:
            return
        if str(rec.get("verdict")).upper() != "GREEN":
            return
        files = git(self.main, "ls-tree", "-r", "--name-only", rec["sha"]).stdout.split()
        missing = [p for w in WORK.values() for p in w if p not in files]
        open_tasks = [p for p in files if re.match(rf"reef/features/{SLUG}/tasks/\d+-[^/]+\.md$", p)]
        if missing or open_tasks:
            raise AssertionError(f"a GREEN record at {rec['sha'][:12]} binds a head without the row's work: missing {missing}, "
                                 f"open task files {open_tasks}; log {self.log}")

    def plant_stale_copy(self):
        """An older copy of the plan left in a task worktree (a fresh-start critical-path attempt, abandoned): its task files say
        pending, attempts 0, and are newer on disk than the plan of record."""
        if not os.path.isdir(self.co) or git(self.main, "rev-parse", "-q", "--verify", f"refs/heads/feat/{SLUG}").returncode != 0:
            return
        first = git(self.main, "log", "--format=%H", "--grep", f"plan: {SLUG}", f"feat/{SLUG}").stdout.split()
        if not first:
            return
        wt = os.path.join(self.main, ".reef", "worktrees", "101")
        if not os.path.isdir(wt):
            git(self.main, "worktree", "add", "-q", "-b", "task/101-slice", wt, first[-1])

    # ---------------- the fingerprint: the whole project, minus logs and clocks ----------------
    SKIP_FILES = re.compile(r"(^|/)(\.git|loop\.json|status\.html|runs\.jsonl|gate-[a-z]+\.log|hold[^/]*)$")

    def fingerprint(self):
        """The state the next tick reads, as one string: every ref, every worktree's HEAD and status, every file under the main
        checkout and its worktrees (not .git, not scripts/, not the loop's own hashes or the gate's logs), timestamps blanked,
        and the forge's PRs. A planted stale worktree is left out (it is the fault's, not Reef's)."""
        out = [git(self.main, "for-each-ref", "--format=%(refname) %(objectname)").stdout]
        out = ["\n".join(l for l in out[0].splitlines() if "task/101-slice" not in l)]
        for l in git(self.main, "worktree", "list", "--porcelain").stdout.splitlines():
            if l.startswith("worktree ") and not l.endswith("/worktrees/101"):
                w = l[len("worktree "):]
                out.append(os.path.relpath(w, self.tmp) + " " + git(w, "rev-parse", "HEAD").stdout.strip() + "\n" + git(w, "status", "--porcelain").stdout)
        for dp, dns, fns in os.walk(self.main):
            rel = os.path.relpath(dp, self.main)
            dns[:] = sorted(n for n in dns if n not in (".git", "__pycache__") and not (n == "scripts") and os.path.join(rel, n) != ".reef/worktrees/101")
            for n in sorted(fns):
                rp = os.path.normpath(os.path.join(rel, n))
                if self.SKIP_FILES.search(rp):
                    continue
                try:
                    with open(os.path.join(dp, n), encoding="utf-8", errors="replace") as f:
                        text = f.read()
                except OSError:
                    continue
                text = re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z?", "T", text)
                text = re.sub(r'"seconds": [\d.]+', '"seconds": 0', text)
                out.append(f"== {rp}\n{text}")
        gh = self.gh_state()
        out.append(json.dumps([gh.get("prs"), gh.get("next")], sort_keys=True))
        return "\n".join(out)

    # ---------------- the end state ----------------
    def end_state(self):
        def norm(text):
            return re.sub(r"^dispatches: \d+\n", "", text, flags=re.M)
        tree = {}
        for p in git(self.main, "ls-files").stdout.split():
            if p.startswith("scripts/"):
                continue
            with open(os.path.join(self.main, p), encoding="utf-8", errors="replace") as f:
                tree[p] = norm(f.read())
        gh = self.gh_state()
        rec = {}
        try:
            rec = json.load(open(os.path.join(self.main, ".reef", "review", f"{SLUG}.json")))
        except OSError:
            pass
        journal = tree.get("reef/journal.md", "")
        return {
            "tree": tree,
            "status": git(self.main, "status", "--porcelain", "--untracked-files=no").stdout,
            "branches": sorted(b for b in git(self.main, "for-each-ref", "--format=%(refname:short)", "refs/heads/").stdout.split()),
            "worktrees": len([l for l in git(self.main, "worktree", "list", "--porcelain").stdout.splitlines() if l.startswith("worktree ")]),
            "prs": [(p["number"], p["head"], p["state"]) for p in gh["prs"]],
            "record": (rec.get("verdict"), rec.get("sha") == next((p.get("merged_head") for p in gh["prs"]), None)),
            "journal_rows": {tid: len(re.findall(rf"^\|\s*{tid}\s*\|", journal, re.M)) for tid, *_ in TASKS},
            "attempts": {tid: (re.search(r"^attempts: (\d+)", tree.get(f"reef/features/{SLUG}/tasks/done/{tid}-{s}.md", ""), re.M) or [None, "?"])[1]
                         for tid, s, *_ in TASKS},
            "row": self.row_state().get("state"),
        }


GOLDEN_STEPS = ["plan", "approve", "dispatch", "agent", "verify", "dispatch", "agent", "verify", "pr", "evidence", "review", "merge", "close"]
# per step kind: the crash prefixes that make sense there (a kill part-way through the step)
CRASHES = {"plan": ["files"], "dispatch": ["attempt-only"], "agent": ["code-only", "no-rm"], "verify": ["gated", "fm", "mv"],
           "pr": ["merged-base"], "review": ["report-only"], "close": ["archived", "journaled", "committed"]}
# per step kind: the gh call that fails once at that boundary (the tick's own `gh pr list` where the step itself calls none)
GH_FAIL = {"pr": "pr create", "review": "pr view", "merge": "pr merge", "close": "pr list --head", "evidence": "pr list --head"}


class _E2E(unittest.TestCase):
    golden = None
    snapdir = None
    tmp = None

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="reef-e2e.")
        cls.snapdir = tempfile.mkdtemp(prefix="reef-e2e-snaps.")
        d = Driver(cls.tmp)
        d.build()

        cls.fps = {}

        def snap(k):
            dst = os.path.join(cls.snapdir, str(k))
            if not os.path.exists(dst):
                shutil.copytree(cls.tmp, dst, symlinks=True)
                cls.fps[k] = d.fingerprint()
        cls.steps = d.drive(snaps=snap)
        cls.fps[len(cls.steps)] = d.fingerprint()
        cls.golden = d.end_state()
        cls.golden_log = list(d.log)

    @classmethod
    def tearDownClass(cls):
        for p in (cls.tmp, cls.snapdir):
            shutil.rmtree(p, ignore_errors=True)

    def restore(self, k):
        shutil.rmtree(self.tmp)
        shutil.copytree(os.path.join(self.snapdir, str(k)), self.tmp, symlinks=True)
        return Driver(self.tmp)

    def run_fault(self, k, kind, detail):
        d = self.restore(k)
        seen = {}

        def converged(j):
            fp = d.fingerprint()
            hit = [i for i, g in self.fps.items() if i > k and g == fp]
            if hit:
                seen["at"] = hit[0]
            return bool(hit)
        try:
            d.drive(start=k, fault=(k, kind, detail), converged=converged)
            if "at" in seen:
                return f"CONVERGED at golden step {seen['at']} | log {d.log}"
        except Stop as e:
            # a named stop is acceptable — but never with a second PR or a doubled attempt/journal row on disk
            st = d.end_state()
            self.assertLessEqual(len(st["prs"]), 1, f"a second PR: {st['prs']}")
            self.assertTrue(all(n <= 1 for n in st["journal_rows"].values()), st["journal_rows"])
            return f"STOP {e} | log {d.log}"
        if kind == "dup" and GOLDEN_STEPS[k] == "dispatch":
            self.assertTrue(any(isinstance(e[2], str) and e[2].startswith("dup refused") for e in d.log if len(e) > 2),
                            f"a second implementer dispatch of a task already in flight (its marker live, its session alive) was "
                            f"allowed: two implementers on one worktree; log {d.log}")
        st = d.end_state()
        for key in ("prs", "journal_rows", "attempts", "record", "row", "branches", "worktrees", "status"):
            self.assertEqual(st[key], self.golden[key], f"{key} diverged after {kind}:{detail} at step {k} ({self.steps[k][0]}); log {d.log}")
        self.assertEqual(sorted(st["tree"]), sorted(self.golden["tree"]), f"files diverged after {kind}:{detail} at step {k}")
        for p in st["tree"]:
            self.assertEqual(st["tree"][p], self.golden["tree"][p], f"{p} diverged after {kind}:{detail} at step {k}")
        return f"OK at the end | log {d.log}"


class Golden(_E2E):
    def test_the_tick_drives_the_row_from_queued_to_merged_and_closed(self):
        self.assertEqual([s for s, _ in self.steps], GOLDEN_STEPS, self.golden_log)
        g = self.golden
        self.assertEqual(g["prs"], [(7, f"feat/{SLUG}", "MERGED")])
        self.assertEqual(g["record"], ("GREEN", True))
        self.assertEqual(g["journal_rows"], {"101": 1, "102": 1})
        self.assertEqual(g["attempts"], {"101": "0", "102": "0"})
        self.assertEqual(g["row"], "closed")
        self.assertEqual(g["branches"], ["main"])
        self.assertEqual(g["worktrees"], 1)
        self.assertIn("| 1 | crash row one |", g["tree"]["reef/queue-archive.md"])
        self.assertNotIn("| 1 | crash row one |", g["tree"]["reef/queue.md"])


def _make(k, kind, detail):
    def t(self):
        out = self.run_fault(k, kind, detail)
        if os.environ.get("REEF_E2E_VERBOSE"):
            print(f"\nOUTCOME step{k:02d} {GOLDEN_STEPS[k]} {kind}:{detail}: {out}")
    t.__name__ = f"test_step{k:02d}_{GOLDEN_STEPS[k]}_{kind}_{re.sub(r'[^a-z0-9]+', '_', detail.lower()).strip('_')}"
    return t


# the second task's dispatch and agent steps are the first's again: only its close (the row's last task) gets its own faults
SECOND = {5: [], 6: [], 7: [("crash", "fm"), ("crash", "mv")]}
# test name -> open cluster id in docs/review/stress-2026-11-03-hard.md. Each is wrapped in unittest.expectedFailure; a fix PR removes its
# entries, and an entry its fix closed goes red as an unexpected success. `grep -n "open: " tests/stress_e2e.py` lists them.
OPEN = {
}
# `dup` only where a second run is not refused or idempotent by design (dispatch, verify, review); the rest were redundant
# by construction and passed (trimmed per docs/review/stress-2026-11-03-hard.md, "stress_e2e.py runtime")
DUP_STEPS = (2, 4, 10)
for _k, _s in enumerate(GOLDEN_STEPS):
    _faults = ([("dup", "twice")] if _k in DUP_STEPS else []) + [("crash", c) for c in CRASHES.get(_s, [])]
    if _k in SECOND:
        _faults = SECOND[_k]
    if _s in GH_FAIL or _k == 4:   # the tick's own `gh pr list` fails the same way at every boundary: step 4 stands for them
        _faults.append(("gh", GH_FAIL.get(_s, "pr list --base")))
    if _k == 4:
        _faults.append(("stale", "task-worktree"))
    for _kind, _detail in _faults:
        _t = _make(_k, _kind, _detail)
        if _t.__name__ in OPEN:
            _t = unittest.expectedFailure(_t)
        setattr(Golden, _t.__name__, _t)
_names = {n for n in dir(Golden) if n.startswith("test_")}
assert set(OPEN) <= _names, sorted(set(OPEN) - _names)


if __name__ == "__main__":
    unittest.main()
