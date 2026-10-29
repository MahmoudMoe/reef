#!/usr/bin/env python3
# CLASS: code
"""Reef approval — the human's plan approval as a RECORD bound to the plan's digest (PostToolUse AskUserQuestion hook).
Writes .reef/approvals/<feature>.json = {digest16, approved_at, files} only when a question `Approve plan <feature> at <16 hex>?`
is answered exactly `Approve` and the 16 hex equal the current digest (reef-plan-check.py --digest); a timeout
(afkTimeoutMs), another label or a stale digest writes nothing. Always exit 0; the guard enforces the record.
Usage: cat payload.json | reef-approval.py [--root DIR]
       reef-approval.py --owner "Approve plan <feature> at <digest16>?" | "Approve night <date> at <digest16>?" | "Approve proxy by day at <digest16>?"
         the owner, in their own terminal, where the AskUserQuestion hook does not exist (OpenCode); the guard refuses
         an agent running this script, except --proxy during a night and --proxy --day under the approved reef/proxy.md
       reef-approval.py --from-issue <row>   (v3 phase 7, queue.home: issues) the owner's approval posted on the row's issue —
         a comment whose first line is exactly `Approve plan <slug> at <digest16>?` by a collaborator with ADMIN permission, at
         the plan's current digest — becomes the record the hook would have written (`by: owner (issue #n, @login)`); run by
         the factory job before the build, or by the owner in a terminal; another author, a stale digest, no comment: nothing
       reef-approval.py --proxy --day --kind <process|wording> --row <id> --report .reef/ci-local/report-mahmoud-day-<row>.md
         (v3 phase 6) Mahmoud's decision by day, from his own report (`RUN: agent=mahmoud day=<date> kind=<kind> …`, a
         `DECIDE <question> — <answer> — <why>` line): written as the queue footnote `Mahmoud (proxy, day <date>, <kind>): …`
         on the row and logged in .reef/approvals/day-decisions.jsonl; a `WAIT` line is exit 3 (the owner's: reef-queue.py
         ask); a kind reef/proxy.md does not name, a stale or missing day approval, a foreign report: refused, nothing written
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # the shared helpers live beside this script
from reef_common import main_checkout  # noqa: E402

QUESTION = re.compile(r"^Approve plan (?P<feature>[A-Za-z0-9][A-Za-z0-9._-]*) at (?P<digest>[0-9a-f]{16})\?$")
NIGHT_Q = re.compile(r"^Approve night (?P<date>\d{4}-\d\d-\d\d) at (?P<digest>[0-9a-f]{16})\?$")
DAY_Q = re.compile(r"^Approve proxy by day at (?P<digest>[0-9a-f]{16})\?$")


def runner():
    """reef-run.py's night digest and rows — one definition, imported (the hook and --proxy must agree with it)."""
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("reef_run", os.path.join(here, "reef-run.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def worktrees(cwd):
    """Every checkout of this repository, the main one first."""
    out = []
    try:
        r = subprocess.run(["git", "-C", cwd, "worktree", "list", "--porcelain"], capture_output=True, text=True, timeout=10)
        out = [l[len("worktree "):].strip() for l in r.stdout.splitlines() if l.startswith("worktree ")]
    except Exception:
        pass
    return out or [cwd]


def feature_present(root, feature):
    """The plan lives here: a 0.6 feature folder, or a flat task file carrying `feature: <slug>`."""
    paths = {}
    try:
        with open(os.path.join(root, ".reef", "config.json"), encoding="utf-8") as f:
            paths = (json.load(f).get("paths") or {})
    except Exception:
        pass
    if os.path.isdir(os.path.join(root, paths.get("features", "reef/features"), feature)):
        return True
    tasks = os.path.join(root, paths.get("tasks", "tasks"))
    for sub in ("", "done"):
        d = os.path.join(tasks, sub)
        for name in (os.listdir(d) if os.path.isdir(d) else []):
            if name.endswith(".md"):
                try:
                    with open(os.path.join(d, name), encoding="utf-8") as f:
                        head = f.read(2000)
                except OSError:
                    continue
                if re.search(r"^feature:[ \t]*" + re.escape(feature) + r"[ \t]*$", head, re.M):
                    return True
    return False


def current_digest(root, feature):
    script = os.path.join(root, "scripts", "reef-plan-check.py")
    if not os.path.isfile(script):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reef-plan-check.py")
    r = subprocess.run([sys.executable, script, root, "--digest", "--feature", feature], capture_output=True, text=True, timeout=60)
    m = re.search(r"^digest: \S+ ([0-9a-f]{64})", r.stdout, re.M)
    return m.group(1) if m else None


def plan_files(root, feature):
    """{file: sha12} over the digest's own files (reef-plan-check.py --plan-files); {} when it cannot run."""
    script = os.path.join(root, "scripts", "reef-plan-check.py")
    if not os.path.isfile(script):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reef-plan-check.py")
    try:
        r = subprocess.run([sys.executable, script, root, "--plan-files", "--feature", feature], capture_output=True, text=True, timeout=60)
        out = json.loads(r.stdout) if r.returncode == 0 else {}
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


def plan_check_failures(root, feature):
    """The FAIL lines of reef-plan-check.py for this feature in this checkout, or [] (2026-10-17: five sentences over
    the word ceiling were found AFTER the owner approved; fixing them voided the approval and cost a second gate)."""
    script = os.path.join(root, "scripts", "reef-plan-check.py")
    if not os.path.isfile(script):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reef-plan-check.py")
    try:
        r = subprocess.run([sys.executable, script, root, "--feature", feature, "--quiet"], capture_output=True, text=True, timeout=120)
    except Exception as e:   # a check that cannot run is not a green check
        return [f"plan-check did not run: {e}"]
    if r.returncode == 0:
        return []
    fails = [l for l in r.stdout.splitlines() if l.startswith("FAIL")]
    return fails or [f"plan-check exit {r.returncode}"]


def plan_digests(cwd, feature):
    """{checkout: digest} for every checkout where the plan is present. The plan the human approves may live in a
    feature worktree while the hook runs in the main checkout (first contact, 2026-10-16: the plan had been moved to
    .reef/worktrees/<slug>, develop had no feature files, and an 'Approve' wrote nothing — the digest was computed
    in the wrong tree). The RECORD still goes to the main checkout, where plan-check and the guard read it."""
    out = {}
    for wt in worktrees(cwd):
        if feature_present(wt, feature):
            dg = current_digest(wt, feature)
            if dg:
                out[wt] = dg
    return out


def clear_question(main, feature, co, digest16):
    """The approval's own question leaves .reef/questions.md and its reef-question issue closes (2026-10-28: the owner approved in
    his terminal and three runner sessions re-read the filed question, believed it, and recorded the same wait). The row's lines
    that ask for an approval go; other rows' questions, and this row's other questions, stay. Returns how many lines went."""
    row = feature_row(co, feature)
    p = os.path.join(main, ".reef", "questions.md")
    try:
        with open(p, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return 0
    def mine(line):
        return bool(row) and re.match(rf"- row {re.escape(row)}:", line) is not None and re.search(r"approv|\bstamp\b|digest", line, re.I) is not None
    kept = [l for l in lines if not mine(l)]
    gone = len(lines) - len(kept)
    if not gone:
        return 0
    if any(l.strip() for l in kept):
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(kept) + "\n")
    else:
        os.unlink(p)
    if shutil.which("gh"):
        try:
            r = subprocess.run(["gh", "issue", "list", "--label", "reef-question", "--state", "open", "--search", f"row {row}", "--json", "number,title"],
                               cwd=main, capture_output=True, text=True, timeout=30)
            for it in (json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else []):
                if re.search(rf"row {re.escape(row)}\b", str(it.get("title", ""))) and re.search(r"approv|stamp|digest", str(it.get("title", "")), re.I):
                    subprocess.run(["gh", "issue", "close", str(it["number"]), "--comment", f"Approved: plan {feature} at {digest16} (recorded)"],
                                   cwd=main, capture_output=True, text=True, timeout=30)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return gone


def feature_row(root, feature):
    """The queue row a feature answers (`Row: N` in its SPEC.md), from the checkout that holds the plan."""
    try:
        with open(os.path.join(root, ".reef", "config.json"), encoding="utf-8") as f:
            feats = (json.load(f).get("paths") or {}).get("features", "reef/features")
    except Exception:
        feats = "reef/features"
    try:
        with open(os.path.join(root, feats, feature, "SPEC.md"), encoding="utf-8") as f:
            m = re.search(r"^Row:\s*(\d+)", f.read(), re.M)
        return m.group(1) if m else ""
    except OSError:
        return ""


def cmd_proxy(argv):
    """Super Reef: Mahmoud's plan approval, written only while the night runs (.reef/night/active), under the approved
    contract at its current digest, for a row the contract names, from Mahmoud's own report (a protected evidence path
    the main session may only copy), at the plan's current digest, with the plan check green."""
    feature = argv[argv.index("--feature") + 1] if "--feature" in argv else ""
    report = argv[argv.index("--report") + 1] if "--report" in argv else ""
    if not feature or not report:
        print("usage: reef-approval.py --proxy --feature <slug> --report .reef/ci-local/report-mahmoud-<slug>.md")
        return 2
    cwd = os.getcwd()
    root = main_checkout(cwd)
    refuse = lambda why: (print(f"reef-approval: {feature}: REFUSED — {why}; nothing written"), 1)[1]
    if not os.path.isfile(os.path.join(root, ".reef", "night", "active")):
        return refuse("no night is running (.reef/night/active is written by `reef-run.py --night` alone)")
    rr = runner()
    ok, why = rr.night_ok(root)
    if not ok:
        return refuse(why)
    if not re.search(r"(^|/)\.reef/ci-local/report-mahmoud-" + re.escape(feature) + r"\.md$", report.replace(os.sep, "/")):
        return refuse(f"the report must be Mahmoud's own file copied to .reef/ci-local/report-mahmoud-{feature}.md")
    digests = plan_digests(cwd, feature)
    if not digests:
        return refuse("no checkout holds this plan")
    where, dg = next(iter(digests.items()))
    row = feature_row(where, feature)
    if not row or row not in rr.night_rows(root):
        return refuse(f"its row ({row or 'no Row: line in SPEC.md'}) is not in tonight's contract ({', '.join(rr.night_rows(root)) or '-'})")
    try:
        with open(report if os.path.isabs(report) else os.path.join(cwd, report), encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return refuse(f"cannot read the report: {e}")
    if not re.search(r"^RUN:[ \t]*agent=mahmoud\b", text, re.M):
        return refuse("the report's first line is not `RUN: agent=mahmoud …`")
    if not re.search(r"^APPROVE plan " + re.escape(feature) + r" at " + dg[:16] + r"\b", text, re.M):
        return refuse(f"the report has no `APPROVE plan {feature} at {dg[:16]}` line (the plan's current digest)")
    fails = plan_check_failures(where, feature)
    if fails:
        return refuse(f"reef-plan-check.py FAILS in {where}: {fails[0][:160]}")
    d = os.path.join(root, ".reef", "approvals")
    os.makedirs(d, exist_ok=True)
    rec = {"digest16": dg[:16], "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "by": "mahmoud (proxy)", "night": rr.night_digest(root)[:16]}
    files = plan_files(where, feature)
    if files:
        rec["files"] = files
    with open(os.path.join(d, f"{feature}.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
        f.write("\n")
    print(f"reef-approval: {feature} approved at {dg[:16]} by mahmoud (proxy), night {rec['night']} -> .reef/approvals/{feature}.json")
    return 0


def cmd_proxy_day(argv):
    """v3 phase 6: the proxy's decision by day, under reef/proxy.md approved at its digest, for a kind that file names, from
    Mahmoud's own report under .reef/ci-local/ — the footnote carries his label, written here and never typed."""
    opt = lambda k: argv[argv.index(k) + 1] if k in argv and argv.index(k) + 1 < len(argv) else ""
    kind, row, report = opt("--kind").strip().lower(), opt("--row").strip(), opt("--report")
    if not kind or not row or not report:
        print("usage: reef-approval.py --proxy --day --kind <process|wording> --row <id> --report .reef/ci-local/report-mahmoud-day-<row>.md")
        return 2
    cwd = os.getcwd()
    root = main_checkout(cwd)
    refuse = lambda why: (print(f"reef-approval: day, row {row}: REFUSED — {why}; nothing written"), 1)[1]
    if os.path.isfile(os.path.join(root, ".reef", "night", "active")):
        return refuse("a night is running (.reef/night/active): its contract governs; the day contract waits for the morning")
    rr = runner()
    ok, why = rr.day_ok(root)
    if not ok:
        return refuse(why)
    kinds = rr.day_kinds(root)
    if kind not in kinds:
        return refuse(f"`{kind}` is the owner's (reef/proxy.md decides: {', '.join(kinds) or '-'}) — file it: `python3 scripts/reef-queue.py ask \"<question>\" --row {row} --recommended \"<answer>\"`")
    if not re.search(r"(^|/)\.reef/ci-local/report-mahmoud-day-" + re.escape(row) + r"(-[A-Za-z0-9_]+)?\.md$", report.replace(os.sep, "/")):
        return refuse(f"the report must be Mahmoud's own file copied to .reef/ci-local/report-mahmoud-day-{row}.md")
    try:
        with open(report if os.path.isabs(report) else os.path.join(cwd, report), encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return refuse(f"cannot read the report: {e}")
    run_line = re.search(r"^RUN:[ \t]*agent=mahmoud\b(.*)$", text, re.M)
    if not run_line:
        return refuse("the report's first line is not `RUN: agent=mahmoud …`")
    today = time.strftime("%Y-%m-%d")
    date = re.search(r"\bday=(\d{4}-\d\d-\d\d)", run_line.group(1))
    rkind = re.search(r"\bkind=([a-z]+)", run_line.group(1))
    if not date or not rkind or rkind.group(1) != kind:
        return refuse(f"the RUN line must carry `day=<date> kind={kind}` (a night report is not a day decision)")
    if date.group(1) != today:
        return refuse(f"the RUN line says day={date.group(1)}, today is {today} — a decision is dated by the clock, not the report")
    wait = re.search(r"^WAIT\b(.*)$", text, re.M)
    dec = re.search(r"^DECIDE (?P<q>.+?) — (?P<a>.+?) — (?P<why>.+)$", text, re.M)
    if wait:
        print(f"reef-approval: day, row {row}: WAIT — {wait.group(1).strip()[:200]} — the owner's: `python3 scripts/reef-queue.py ask \"<question>\" --row {row} --recommended \"<answer>\"`")
        return 3
    if not dec:
        return refuse("no `DECIDE <question> — <answer> — <why>` or `WAIT` line in the report")
    note = f"Mahmoud (proxy, day {today}, {kind}): {dec.group('a').strip()} — {dec.group('why').strip()}"
    import hashlib
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    log_p = os.path.join(root, ".reef", "approvals", "day-decisions.jsonl")
    try:
        with open(log_p, encoding="utf-8") as f:
            for line in f:
                try:
                    old = json.loads(line)
                except ValueError:
                    continue
                if old.get("row") == row and old.get("report_sha256") == sha:
                    return refuse(f"this report is already recorded (footnote {old.get('footnote')}) — one decision, one footnote")
    except OSError:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([sys.executable, os.path.join(here, "reef-queue.py"), "footnote", note, "--row", row, "--repo", root], capture_output=True, text=True, cwd=root)
    if r.returncode != 0:
        return refuse(f"the footnote was refused: {(r.stderr or r.stdout).strip().splitlines()[-1][:200] if (r.stderr or r.stdout).strip() else r.returncode}")
    mark = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    os.makedirs(os.path.dirname(log_p), exist_ok=True)
    with open(log_p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "row": row, "kind": kind, "question": dec.group("q").strip(),
                            "decision": dec.group("a").strip(), "why": dec.group("why").strip(), "footnote": mark, "day": rr.day_digest(root)[:16],
                            "report_sha256": sha}) + "\n")
    print(f"reef-approval: day, row {row} ({kind}): footnote {mark} — {note[:120]}")
    return 0


def cmd_from_issue(argv):
    """v3 phase 7: the plan approval from the forge. Only an admin's comment at the current digest counts (the owner's
    repository, the owner's word); the newest matching comment decides; the record is the hook's shape plus who and where."""
    import glob
    i = argv.index("--from-issue")
    row = argv[i + 1].strip() if i + 1 < len(argv) else ""
    if not row.isdigit():
        print("usage: reef-approval.py --from-issue <row>")
        return 2
    cwd = os.getcwd()
    root = main_checkout(cwd)
    try:
        with open(os.path.join(root, ".reef", "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    if (cfg.get("queue") or {}).get("home") != "issues":
        print("reef-approval: --from-issue is for queue.home: issues (the file queue's approvals are the AskUserQuestion hook's)")
        return 1
    features = str((cfg.get("paths") or {}).get("features", "reef/features") or "reef/features")
    slug = ""
    for co in worktrees(cwd):
        for spec in sorted(glob.glob(os.path.join(co, features, "*", "SPEC.md"))):
            try:
                with open(spec, encoding="utf-8") as f:
                    if re.search(r"^Row:\s*" + re.escape(row) + r"\s*$", f.read(), re.M):
                        slug = os.path.basename(os.path.dirname(spec))
            except OSError:
                continue
    if not slug:
        print(f"reef-approval: row {row}: no feature folder with `Row: {row}` yet — nothing to approve (/reef-plan {row} first)")
        return 0
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([sys.executable, os.path.join(here, "reef-queue.py"), "row-issue", row, "--repo", root], cwd=root, capture_output=True, text=True, timeout=120)
    n = r.stdout.strip().splitlines()[-1].strip() if r.returncode == 0 and r.stdout.strip() else ""
    if not n.isdigit():
        print(f"reef-approval: row {row}: {(r.stderr or r.stdout).strip().splitlines()[-1][:200] if (r.stderr or r.stdout).strip() else 'no issue'}")
        return 1
    n = int(n)
    gh = lambda *a: subprocess.run(["gh", *a], cwd=root, capture_output=True, text=True, timeout=60)
    digests = plan_digests(cwd, slug)
    if not digests:
        print(f"reef-approval: row {row}: no checkout holds the plan {slug}")
        return 1
    where, dg = next(iter(digests.items()))
    question = f"Approve plan {slug} at {dg[:16]}?"
    r = gh("api", f"repos/{{owner}}/{{repo}}/issues/{n}/comments", "--paginate", "--slurp")
    try:
        pages = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else []
    except ValueError:
        pages = []
    comments = [c for page in (pages if isinstance(pages, list) else []) for c in (page if isinstance(page, list) else [page])]
    hits = []
    for c in comments:
        if not isinstance(c, dict):
            continue
        first = (str(c.get("body") or "").strip().splitlines() or [""])[0].strip()
        m = QUESTION.match(first)
        if m and m.group("feature") == slug:
            hits.append((c, m))
    if not hits:
        print(f"reef-approval: row {row} (issue #{n}): no approval comment — the owner posts exactly this line on the issue: {question}")
        return 0
    perms = {}
    chosen = None
    for c, m in reversed(hits):   # the newest comment by an ADMIN decides; anyone else's line is noise, not a veto
        login = str((c.get("user") or {}).get("login") or "")
        if login not in perms:
            r = gh("api", f"repos/{{owner}}/{{repo}}/collaborators/{login}/permission")
            try:
                perms[login] = str(json.loads(r.stdout).get("permission") or "") if r.returncode == 0 and r.stdout.strip() else ""
            except ValueError:
                perms[login] = ""
        if perms[login] == "admin":
            chosen = (c, m, login)
            break
    if chosen is None:
        print(f"reef-approval: row {row} (issue #{n}): the approval line was posted by {', '.join('@' + k + ' (' + (v or 'no permission') + ')' for k, v in perms.items())}, "
              f"not by an admin — only the owner approves; nothing written")
        return 0
    c, m, login = chosen
    # an edited comment is not the owner's word: a write collaborator can rewrite anyone's remark (the review, 2026-10-27)
    if str(c.get("updated_at") or "") not in ("", str(c.get("created_at") or "")):
        print(f"reef-approval: row {row} (issue #{n}): @{login}'s approval comment was edited after it was posted ({c.get('updated_at')}) — not taken; the owner posts a fresh one: {question}")
        return 0
    if m.group("digest") != dg[:16]:
        print(f"reef-approval: row {row} (issue #{n}): @{login}'s comment approves {m.group('digest')}, the plan is at {dg[:16]} (stale) — the owner posts: {question}")
        return 0
    d = os.path.join(root, ".reef", "approvals")
    os.makedirs(d, exist_ok=True)
    rec = {"digest16": dg[:16], "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "by": f"owner (issue #{n}, @{login})", "comment_id": c.get("id")}
    files = plan_files(where, slug)
    if files:
        rec["files"] = files
    with open(os.path.join(d, f"{slug}.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
        f.write("\n")
    print(f"reef-approval: {slug} approved at {dg[:16]} by @{login} on issue #{n} -> .reef/approvals/{slug}.json")
    return 0


def main(argv):
    if "--from-issue" in argv:
        return cmd_from_issue(argv)
    if "--proxy" in argv:
        return cmd_proxy_day(argv) if "--day" in argv else cmd_proxy(argv)
    root = None
    if "--root" in argv:
        root = argv[argv.index("--root") + 1]
    owner = "--owner" in argv
    if owner:
        q = (argv[argv.index("--owner") + 1] if argv.index("--owner") + 1 < len(argv) else "").strip()
        if not (QUESTION.match(q) or NIGHT_Q.match(q) or DAY_Q.match(q)):
            print('usage: reef-approval.py --owner "Approve plan <feature> at <digest16>?" | "Approve night <date> at <digest16>?" | "Approve proxy by day at <digest16>?"')
            return 2
        payload = {"tool_name": "AskUserQuestion", "cwd": os.getcwd(), "tool_response": {"answers": {q: "Approve"}}}
    else:
        try:
            payload = json.load(sys.stdin)
        except Exception:
            print("reef-approval: no JSON payload — nothing written")
            return 0
    if payload.get("tool_name") != "AskUserQuestion":
        return 0
    resp = payload.get("tool_response") or {}
    if not isinstance(resp, dict):
        resp = {}
    if resp.get("afkTimeoutMs"):
        print("reef-approval: the question timed out (afkTimeoutMs) — an unanswered gate approves nothing")
        return 0
    answers = resp.get("answers") if isinstance(resp.get("answers"), dict) else None
    if answers is None:
        ti = payload.get("tool_input") or {}
        answers = ti.get("answers") if isinstance(ti.get("answers"), dict) else {}
    root = root or main_checkout(payload.get("cwd") or os.getcwd())
    wrote = 0
    for question, label in answers.items():
        dq = DAY_Q.match(str(question).strip())
        if dq:
            # v3 phase 6: the owner approves the proxy's day contract + their profile ONCE, at their digest
            if str(label).strip() != "Approve":
                print(f"reef-approval: proxy by day: answer was {label!r} — nothing written")
                continue
            rr = runner()
            dg = rr.day_digest(root)
            if not dg or dg[:16] != dq.group("digest"):
                print(f"reef-approval: proxy by day: the question's digest {dq.group('digest')} is not the files' ({dg[:16] or 'missing'}) (stale) — nothing written")
                continue
            d = os.path.join(root, ".reef", "approvals")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "day.json"), "w", encoding="utf-8") as f:
                json.dump({"digest16": dg[:16], "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=1)
                f.write("\n")
            print(f"reef-approval: proxy by day approved at {dg[:16]} (decides: {', '.join(rr.day_kinds(root)) or '-'}) -> .reef/approvals/day.json")
            wrote += 1
            continue
        n = NIGHT_Q.match(str(question).strip())
        if n:
            # super Reef (2026-10-21): the owner approves tonight's contract + their profile ONCE, at their digest
            if str(label).strip() != "Approve":
                print(f"reef-approval: night {n.group('date')}: answer was {label!r} — nothing written")
                continue
            rr = runner()
            dg = rr.night_digest(root)
            if not dg or dg[:16] != n.group("digest"):
                print(f"reef-approval: night {n.group('date')}: the question's digest {n.group('digest')} is not the contract's ({dg[:16] or 'missing'}) (stale) — nothing written")
                continue
            d = os.path.join(root, ".reef", "approvals")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "night.json"), "w", encoding="utf-8") as f:
                json.dump({"digest16": dg[:16], "date": n.group("date"), "rows": rr.night_rows(root),
                           "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=1)
                f.write("\n")
            print(f"reef-approval: night {n.group('date')} approved at {dg[:16]} (rows {', '.join(rr.night_rows(root)) or '-'}) -> .reef/approvals/night.json")
            wrote += 1
            continue
        m = QUESTION.match(str(question).strip())
        if not m:
            continue
        feature, digest16 = m.group("feature"), m.group("digest")
        if str(label).strip() != "Approve":
            print(f"reef-approval: {feature}: answer was {label!r}, not 'Approve' — nothing written")
            continue
        digests = plan_digests(payload.get("cwd") or os.getcwd(), feature)
        if not digests:
            print(f"reef-approval: {feature}: no checkout holds this plan, cannot compute its digest — nothing written")
            continue
        where = [wt for wt, dg in digests.items() if dg[:16] == digest16]
        if not where:
            seen = ", ".join(f"{dg[:16]} in {os.path.basename(wt) or wt}" for wt, dg in digests.items())
            print(f"reef-approval: {feature}: the question's digest {digest16} matches no checkout's plan ({seen}) (stale) — nothing written")
            continue
        fails = plan_check_failures(where[0], feature)
        if fails:
            print(f"reef-approval: {feature}: REFUSED — reef-plan-check.py FAILS in {where[0]}: {fails[0][:200]} — fix, re-digest, ask again; nothing written")
            continue
        d = os.path.join(root, ".reef", "approvals")
        os.makedirs(d, exist_ok=True)
        rec = {"digest16": digest16, "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        files = plan_files(where[0], feature)
        if files:
            rec["files"] = files   # 0.7: {file: sha12} — the next gate's summary names what changed since this approval
        with open(os.path.join(d, f"{feature}.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1)
            f.write("\n")
        print(f"reef-approval: {feature} approved at {digest16} (plan in {where[0]}) -> .reef/approvals/{feature}.json")
        gone = clear_question(root, feature, where[0], digest16)
        if gone:
            print(f"reef-approval: {feature}: {gone} filed question(s) answered by this approval cleared from .reef/questions.md (its reef-question issue closed)")
        wrote += 1
    if not wrote and not answers:
        print("reef-approval: no answers in the payload — nothing written")
    return 1 if owner and not wrote else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:   # a hook that crashes is a hook that blocked the human for nothing
        print(f"reef-approval: internal error — nothing written: {e}")
        sys.exit(0)
