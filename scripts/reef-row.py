#!/usr/bin/env python3
# CLASS: code
"""Reef row — a queue row as a STATE MACHINE read from disk and the forge (workflow v3, phase 5): plan → approval →
build → evidence → review → merge → close, and the ONE next command. Nothing here is decided from memory or prose.
Usage: reef-row.py state <row-id|slug> [--repo DIR] [--json]        reef-row.py next <row-id|slug> [--repo DIR]
States: queued (depends not merged) · plan (no feature folder) · approval (not approved at the plan's digest) · build
(open tasks) · evidence (no green result for the feature head) · review (no GREEN record at that head) · merge (the PR
is open, or the branch is not in the base) · close (merged, row still in the queue) · closed (archived).
Exit 0 · 2 unknown row. The feature folder is found in the main checkout or any feature worktree.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys


def run(args, cwd, timeout=60):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def git(cwd, *a):
    rc, out = run(["git", *a], cwd)
    return out.strip() if rc == 0 else ""


def main_checkout(repo):
    for line in git(repo, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            return line[len("worktree "):].strip()
    return repo


def config(root):
    try:
        with open(os.path.join(root, ".reef", "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def merge_by(cfg):
    """merge.by or its v3 default: loop when ci.feature_gate is ci and base differs from release (scripts/reef-guard.py)."""
    v = str((cfg.get("merge") or {}).get("by", "") or "").strip()
    if v:
        return v
    b = cfg.get("branches") or {}
    ci = str((cfg.get("ci") or {}).get("feature_gate", "ci") or "ci") == "ci"
    return "loop" if ci and str(b.get("base", "main") or "main") != str(b.get("release", "main") or "main") else "human"


def checkouts(main, prefix):
    """{branch name: worktree} for every feature worktree (branch under branches.feature_prefix), and the main checkout."""
    out, entry, branch = {}, None, None
    for l in git(main, "worktree", "list", "--porcelain").splitlines() + [""]:
        if l.startswith("worktree "):
            entry, branch = l[len("worktree "):].strip(), None
        elif l.startswith("branch "):
            branch = l[len("branch "):].strip()
        elif not l and entry and os.path.realpath(entry) != os.path.realpath(main) and branch and branch.startswith("refs/heads/" + prefix):
            out[branch[len("refs/heads/"):]] = entry
            entry = None
    return out


def find_folder(main, cfg, key):
    """(checkout, slug, folder, row id) for a row id or a slug, or None. The row is read from the worktree on ITS branch
    (feature_prefix + slug), else the main checkout — never from another row's worktree, which holds this row's folder
    too once reef-merge-base brought the base in (the review, 2026-10-26)."""
    features = str((cfg.get("paths") or {}).get("features", "reef/features") or "reef/features")
    prefix = str((cfg.get("branches") or {}).get("feature_prefix", "feat/") or "feat/")
    wts = checkouts(main, prefix)
    found = []   # (checkout, slug, folder, row id), any checkout
    for co in list(wts.values()) + [main]:
        for spec in sorted(glob.glob(os.path.join(co, features, "*", "SPEC.md"))):
            slug = os.path.basename(os.path.dirname(spec))
            try:
                with open(spec, encoding="utf-8") as f:
                    m = re.search(r"^Row:\s*(\d+)", f.read(), re.M)
            except OSError:
                continue
            rid = m.group(1) if m else ""
            if key in (slug, rid):
                found.append((co, slug, os.path.dirname(spec), rid))
    if not found:
        return None
    for co, slug, folder, rid in found:
        if wts.get(prefix + slug) and os.path.realpath(co) == os.path.realpath(wts[prefix + slug]):
            return co, slug, folder, rid
    for co, slug, folder, rid in found:
        if os.path.realpath(co) == os.path.realpath(main):
            return co, slug, folder, rid
    return found[0]


def queue_rows(main):
    rc, out = run([sys.executable, os.path.join(main, "scripts", "reef-queue.py"), "status", "--repo", main], main)
    rows = {}
    for l in out.splitlines() if rc == 0 else []:
        parts = l.split("\t")
        if len(parts) > 1:
            rows[parts[0]] = parts[1]
    rc, out = run([sys.executable, os.path.join(main, "scripts", "reef-queue.py"), "ready", "--repo", main], main)
    ready = {l.split("\t")[0] for l in out.splitlines() if "\t" in l} if rc == 0 else set()
    return rows, ready


def archived(main, cfg):
    qpath = os.path.join(main, str((cfg.get("paths") or {}).get("queue", "docs/queue.md")))
    apath = os.path.join(os.path.dirname(qpath), "queue-archive.md")
    try:
        with open(apath, encoding="utf-8") as f:
            return set(re.findall(r"^\|\s*(\d+)\s*\|", f.read(), re.M))
    except OSError:
        return set()


def setup_state(main):
    """(exit, first line, digest) of scripts/reef-setup.py — 0 proven, 3 unproven, 1 INCOMPLETE; a project whose scripts predate
    the proof (no reef-setup.py yet) builds as before (exit 0, no digest)."""
    script = os.path.join(main, "scripts", "reef-setup.py")
    if not os.path.isfile(script):
        return 0, "", ""
    rc, out = run([sys.executable, script, "state", "--repo", main], main, timeout=60)
    _, dg = run([sys.executable, script, "digest", "--repo", main], main, timeout=60)
    return rc, (out.strip().splitlines() or [""])[0], dg.strip()


def setup_next(main, state_rc, line, co=None, dg=""):
    """The one next command the setup proof imposes, or None: `prove` while unproven, the owner's wait while INCOMPLETE, `apply`
    for a worktree set up under an older digest (its marker .reef/ci-local/setup.digest)."""
    if state_rc == 3:
        return "python3 scripts/reef-setup.py prove  (worktree.setup proven once per change)", line
    if state_rc == 1:
        return f"(wait: owner — {line})", line
    if co and dg:
        try:
            with open(os.path.join(co, ".reef", "ci-local", "setup.digest"), encoding="utf-8") as f:
                if f.read().strip() == dg:
                    return None, ""
        except OSError:
            pass
        rel = os.path.relpath(co, main) or "."
        return f"python3 scripts/reef-setup.py apply {rel}  (worktree.setup changed since this worktree was set up)", f"setup {dg} not applied in {rel}"
    return None, ""


def state_of(repo, key):
    main = main_checkout(git(repo, "rev-parse", "--show-toplevel") or os.path.abspath(repo))
    cfg = config(main)
    rows, ready = queue_rows(main)
    out = {"row": key, "slug": None, "state": None, "next": None, "detail": "", "merge_by": merge_by(cfg)}
    if key in archived(main, cfg) and key not in rows:
        out.update(state="closed", next="-", detail="archived")
        return out, 0
    found = find_folder(main, cfg, key)
    if found is None:
        if key in rows:
            if key in ready:
                st_rc, st, _ = setup_state(main)
                nxt, why = setup_next(main, st_rc, st)
                out.update(state="plan", next=nxt or f"/reef-plan {key}", detail=(why + "; " if nxt else "") + "ready, no feature folder yet")
            else:
                out.update(state="queued", next="(wait: its Depends are not merged)", detail=f"queue status {rows[key]}")
            return out, 0
        if key in archived(main, cfg):
            out.update(state="closed", next="-", detail="archived")
            return out, 0
        out.update(state="unknown", next="-", detail="no queue row, no feature folder, not archived")
        return out, 2
    co, slug, fdir, rid = found
    out.update(slug=slug, row=rid or key)
    scripts = os.path.join(co, "scripts")
    rc, dg = run([sys.executable, os.path.join(scripts, "reef-plan-check.py"), co, "--digest", "--feature", slug], co)
    digest = dg.split()[-1] if rc == 0 and dg.strip() else ""
    try:
        with open(os.path.join(main, ".reef", "approvals", f"{slug}.json"), encoding="utf-8") as f:
            approved = str(json.load(f).get("digest16", "")) == digest[:16] and bool(digest)
    except (OSError, ValueError):
        approved = False
    if not approved:
        out.update(state="approval", next=f"/reef-plan {out['row']}",
                   detail=(f"the gate: Approve plan {slug} at {digest[:16]}? — in the terminal: python3 scripts/reef-approval.py --owner "
                           f"\"Approve plan {slug} at {digest[:16]}?\"") if digest else "the plan check is red: fix it first")
        return out, 0
    open_tasks = sorted(os.path.basename(p) for p in glob.glob(os.path.join(fdir, "tasks", "*.md")))
    if open_tasks:
        # 2026-10-28: worktree.setup is proven once per change before a row builds (scripts/reef-setup.py) — a fresh worktree
        # without its setup goes red for reasons unrelated to the row, and a guessed build is a second suite run
        st_rc, st, dg = setup_state(main)
        nxt, why = setup_next(main, st_rc, st, co, dg)
        if nxt:
            out.update(state="build", next=nxt, detail=f"{len(open_tasks)} open task(s); {why}")
            return out, 0
        out.update(state="build", next="python3 scripts/reef-loop.py tick  (dispatch now / verify now → /reef-task or /reef-graph)",
                   detail=f"{len(open_tasks)} open task(s): {', '.join(open_tasks[:4])}")
        return out, 0
    head = git(co, "rev-parse", "HEAD")
    base = str((cfg.get("branches") or {}).get("base", "main") or "main")
    prefix = str((cfg.get("branches") or {}).get("feature_prefix", "feat/") or "feat/")
    merged, pr = None, None
    if shutil.which("gh") and git(main, "remote"):
        rc, prs = run(["gh", "pr", "list", "--head", prefix + slug, "--state", "all", "--json", "number,state", "--limit", "5"], main, timeout=20)
        try:
            lst = json.loads(prs) if rc == 0 and prs.strip() else []
        except ValueError:
            lst = []
        if lst:
            pr = lst[0]
            merged = pr.get("state") == "MERGED"
    if merged is None:
        fhead = git(main, "rev-parse", "-q", "--verify", f"refs/heads/{prefix}{slug}") or head
        rc, _ = run(["git", "merge-base", "--is-ancestor", fhead, base], main)
        merged = rc == 0
        if not merged:   # a squash merge leaves no ancestor: the review record's PR number against the base's subjects
            try:
                with open(os.path.join(main, ".reef", "review", f"{slug}.json"), encoding="utf-8") as f:
                    pr_no = int(json.load(f).get("pr") or 0)
            except (OSError, ValueError, TypeError):
                pr_no = 0
            subjects = git(main, "log", "--first-parent", "-200", "--format=%s", base)
            if pr_no and re.search(rf"\(#{pr_no}\)\s*$", subjects, re.M):
                merged, pr = True, {"number": pr_no, "state": "MERGED"}
    if merged:
        if out["row"] in rows:
            out.update(state="close", next="/reef-loop  (the close step: adr-number, archive, journal)",
                       detail="merged" + (f" (PR #{pr['number']})" if pr else "") + ", row still in the queue")
            return out, 0
        out.update(state="closed", next="-", detail="merged and archived")
        return out, 0
    rc, ev = run([sys.executable, os.path.join(scripts, "reef-evidence.py"), "--repo", co], co)
    if rc != 0:
        out.update(state="evidence", next=f"sh scripts/reef-gate.sh full  (in {os.path.relpath(co, main) or '.'})" if rc != 3 else "(wait: CI is running)",
                   detail=ev.strip().splitlines()[0] if ev.strip() else "no evidence")
        return out, 0
    rec = {}
    try:
        with open(os.path.join(main, ".reef", "review", f"{slug}.json"), encoding="utf-8") as f:
            rec = json.load(f)
        reviewed = str(rec.get("verdict", "")).upper() in ("GREEN", "PASS") and rec.get("sha") == head
    except (OSError, ValueError):
        reviewed = False
    if not reviewed:
        if str(rec.get("verdict", "")).upper() == "FAIL" and rec.get("sha") == head:
            # 2026-10-28: a review's findings are a ROLLUP, never a new plan (the loop sent the owner to /reef-plan for two nits)
            out.update(state="review", next=f"the rollup: tasks/R<NN>-{slug}.md from the review's blockers (reef-review § One rollup, one cap — no plan pass, no approval) → /reef-task {slug} → /reef-review {slug}",
                       detail=f"review FAIL at {head[:12]}")
            return out, 0
        out.update(state="review", next=f"/reef-review {slug}", detail=f"no GREEN record at {head[:12]}")
        return out, 0
    if pr:
        nxt = f"gh pr merge {pr['number']} --squash --delete-branch" if merge_by(cfg) == "loop" else f"(the owner merges PR #{pr['number']})"
    else:
        nxt = f"/reef-review {slug}  (push, PR into {base})"
    out.update(state="merge", next=nxt, detail=f"PR #{pr['number']} {pr.get('state')}" if pr else f"{head[:12]} is not in {base}")
    return out, 0


def main(argv):
    repo, as_json, pos = ".", False, []
    i = 0
    while i < len(argv):
        if argv[i] == "--repo":
            repo = argv[i + 1]; i += 2
        elif argv[i] == "--json":
            as_json = True; i += 1
        else:
            pos.append(argv[i]); i += 1
    if len(pos) != 2 or pos[0] not in ("state", "next"):
        print("usage: reef-row.py state|next <row-id|slug> [--repo DIR] [--json]", file=sys.stderr)
        return 2
    out, rc = state_of(os.path.abspath(repo), pos[1])
    if pos[0] == "next":
        print(out["next"])
    elif as_json:
        print(json.dumps(out, indent=1))
    else:
        print(f"row {out['row']}" + (f" ({out['slug']})" if out["slug"] else "") + f": {out['state']} — {out['detail']} · next: {out['next']}")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
