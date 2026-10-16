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


def current_digest(root, feature):
    script = os.path.join(root, "scripts", "reef-plan-check.py")
    if not os.path.isfile(script):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reef-plan-check.py")
    r = subprocess.run([sys.executable, script, root, "--digest", "--feature", feature], capture_output=True, text=True, timeout=60)
    m = re.search(r"^digest: \S+ ([0-9a-f]{64})", r.stdout, re.M)
    return m.group(1) if m else None


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
        current = current_digest(root, feature)
        if not current:
            print(f"reef-approval: {feature}: cannot compute the current digest — nothing written")
            continue
        if current[:16] != digest16:
            print(f"reef-approval: {feature}: the question's digest {digest16} is not the plan's {current[:16]} (stale) — nothing written")
            continue
        d = os.path.join(root, ".reef", "approvals")
        os.makedirs(d, exist_ok=True)
        rec = {"digest16": digest16, "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        with open(os.path.join(d, f"{feature}.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1)
            f.write("\n")
        print(f"reef-approval: {feature} approved at {digest16} -> .reef/approvals/{feature}.json")
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
