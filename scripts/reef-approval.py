#!/usr/bin/env python3
# CLASS: code
"""Reef approval — the human's plan approval as a RECORD bound to the plan's digest (PostToolUse AskUserQuestion hook).
Writes .reef/approvals/<feature>.json = {digest16, approved_at} only when a question `Approve plan <feature> at <16 hex>?`
is answered exactly `Approve` and the 16 hex equal the current digest (reef-plan-check.py --digest); a timeout
(afkTimeoutMs), another label or a stale digest writes nothing. Always exit 0; the guard enforces the record.
Usage: cat payload.json | reef-approval.py [--root DIR]
"""
import json
import os
import re
import subprocess
import sys
import time

QUESTION = re.compile(r"^Approve plan (?P<feature>[A-Za-z0-9][A-Za-z0-9._-]*) at (?P<digest>[0-9a-f]{16})\?$")


def main_checkout(cwd):
    try:
        r = subprocess.run(["git", "-C", cwd, "worktree", "list", "--porcelain"], capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines():
            if line.startswith("worktree "):
                return line[len("worktree "):].strip()
    except Exception:
        pass
    return cwd


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


def main(argv):
    root = None
    if "--root" in argv:
        root = argv[argv.index("--root") + 1]
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
        d = os.path.join(root, ".reef", "approvals")
        os.makedirs(d, exist_ok=True)
        rec = {"digest16": digest16, "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        with open(os.path.join(d, f"{feature}.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1)
            f.write("\n")
        print(f"reef-approval: {feature} approved at {digest16} (plan in {where[0]}) -> .reef/approvals/{feature}.json")
        wrote += 1
    if not wrote and not answers:
        print("reef-approval: no answers in the payload — nothing written")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:   # a hook that crashes is a hook that blocked the human for nothing
        print(f"reef-approval: internal error — nothing written: {e}")
        sys.exit(0)
