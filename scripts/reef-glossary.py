#!/usr/bin/env python3
# CLASS: code
"""Reef glossary — the words a term replaces, checked by code; a term nothing uses, retired on the owner's approval
(hardening PR-9, docs/design/hardening-pr9-plan.md).

The glossary (`paths.glossary`, default docs/glossary.md) is a `| Term | Definition |` table; an optional third column, `Avoid`,
lists the synonyms the project stopped using, comma-separated. A two-column glossary bans nothing.

Usage:
  reef-glossary.py check [<rev>] [--repo DIR]   the worktree's added lines (tracked changes and untracked files) against
      `git merge-base <rev> HEAD` (default HEAD): an Avoid word of the base's glossary or the worktree's, whole word, any case,
      an optional plural, identifiers split (clientId, client_id), net new per file (more in the added lines than the removed).
      In a code or schema line: `glossary: FAIL — …`; in a doc file or a comment: `glossary: NIT — …`. The glossary and its
      history file are not scanned. `reef-claims.py round` runs the same check as its part (d), the FAILs refusals.
  reef-glossary.py candidates [--repo DIR]      each term no tracked file uses outside the glossary and its history, with the
      owner's question `Approve retiring glossary term <Term> at <digest16>?` (reef doctor prints these; the inbox takes them)
On the owner's approval (reef-approval.py: the AskUserQuestion hook or --owner, never --proxy) the row moves to
<glossary dir>/glossary-history.md and .reef/approvals/glossary-<slug>.json records it; the next `reef-loop.py tick` commits the
two files under the pre-commit gate (hardening PR-3's decisions 5 and 6).
Exit 0 ok · 1 a FAIL · 2 bad usage or git error.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # the shared helpers live beside this script
sys.dont_write_bytecode = True
from reef_common import main_checkout, read_config, repo_root, table_cells, load_sibling, die as _die  # noqa: E402

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
TAIL_COMMENT = re.compile(r"(?:^|\s)(?:#|//|/\*|--)(?:\s|$)")   # a comment after code on the same line
QUESTION = re.compile(r"^Approve retiring glossary term (?P<term>.+?) at (?P<digest>[0-9a-f]{16})\?$")

die = lambda msg: _die(msg, prefix="reef-glossary")


def glossary_rel(repo):
    return str((read_config(repo).get("paths") or {}).get("glossary") or "docs/glossary.md")


def history_rel(gloss):
    return os.path.join(os.path.dirname(gloss), "glossary-history.md").replace(os.sep, "/")


def parse(text):
    """[{term, avoid, row}] of the table whose header has a `Term` cell; `avoid` from a column headed `Avoid`, else []."""
    out, cols = [], None
    for line in (text or "").splitlines():
        if not line.lstrip().startswith("|"):
            if cols is not None and out:
                break
            continue
        cells = table_cells(line)
        if cols is None:
            low = [c.lower() for c in cells]
            if "term" in low:
                cols = (low.index("term"), low.index("avoid") if "avoid" in low else None)
            continue
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        t, a = cols
        term = cells[t] if t < len(cells) else ""
        if term:
            avoid = cells[a] if a is not None and a < len(cells) else ""
            out.append({"term": term, "avoid": [w.strip() for w in avoid.split(",") if w.strip()], "row": line.strip()})
    return out


def words(text):
    """`text` as lowercase words: camelCase, snake_case and kebab-case split, so a banned word inside an identifier is a word."""
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text))
    return re.sub(r"[_\-]+", " ", text).lower()


def pattern(word):
    """Whole words of `word` (several across any separator), an optional plural, on words()-normalised text."""
    parts = [re.escape(p) for p in words(word).split()]
    return re.compile(r"(?<![a-z0-9])" + r"\s+".join(parts) + r"(?:e?s)?(?![a-z0-9])") if parts else None


def git(repo, *args):
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, errors="replace")
    return r.returncode, r.stdout


def avoids(repo, base):
    """[(word, term, [the term's avoid words])]: the Avoid words of the base's glossary and the worktree's (a round cannot drop one)."""
    rel = glossary_rel(repo)
    _, at_base = git(repo, "show", f"{base}:{rel}")
    try:
        with open(os.path.join(repo, rel), encoding="utf-8") as f:
            here = f.read()
    except OSError:
        here = ""
    seen, out = {}, []
    for t in parse(at_base) + parse(here):
        for w in t["avoid"]:
            key = w.lower()
            if key not in seen:
                seen[key] = (w, t["term"], t["avoid"])
                out.append(seen[key])
    return out


def changes(repo, base):
    """{path: (added [(lineno, text)], removed [text])} of the worktree against `base`, untracked files whole."""
    out = {}
    rc, diff = git(repo, "diff", "-U0", "--no-renames", "--no-color", "--no-ext-diff", base, "--")
    if rc != 0:
        die(f"git diff {base} failed")
    path, n = None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
            if path:
                out.setdefault(path, ([], []))
        elif line.startswith("--- ") or line.startswith("diff --git"):
            continue
        elif HUNK.match(line):
            n = int(HUNK.match(line).group(1))
        elif path and line.startswith("+"):
            out[path][0].append((n, line[1:]))
            n += 1
        elif path and line.startswith("-"):
            out[path][1].append(line[1:])
    _, others = git(repo, "ls-files", "--others", "--exclude-standard", "-z")
    for p in (x for x in others.split("\0") if x):
        try:
            with open(os.path.join(repo, p), "rb") as f:
                data = f.read()
            if b"\0" in data:
                continue
            out[p] = (list(enumerate(data.decode("utf-8", "replace").splitlines(), 1)), [])
        except OSError:
            continue
    return out


def check(repo, base, skip=()):
    """(fails, nits, note): one message per net-new Avoid word the worktree added against `base`; `skip` are path prefixes."""
    repo = os.path.realpath(repo)
    banned = avoids(repo, base)
    if not banned:
        return [], [], "glossary: no Avoid words — not checked"
    claims = load_sibling("reef-claims.py", "reef_claims_for_glossary")
    rel = glossary_rel(repo)
    fails, nits = [], []
    for path, (added, removed) in sorted(changes(repo, base).items()):
        if path in (rel, history_rel(rel)) or path.startswith(".reef/") or any(path.startswith(s) for s in skip):
            continue
        doc = claims.is_doc(path)
        for w, term, all_w in banned:
            rx = pattern(w)
            left = sum(len(rx.findall(words(t))) for t in removed)   # a legacy line edited keeps its word: not new
            for n, text in added:
                code, comment = ("", text) if doc or claims.is_comment(text) else _split(text)
                for part, is_code in ((code, True), (comment, False)):
                    for _ in rx.findall(words(part)):
                        if left:
                            left -= 1
                            continue
                        msg = f'{path}:{n} uses "{w}" — the glossary says {term} (Avoid: {", ".join(all_w)})'
                        (fails if is_code else nits).append(msg)
    return fails, nits, ""


def _split(text):
    m = TAIL_COMMENT.search(text)
    return (text[:m.start()], text[m.start():]) if m else (text, "")


def used(root, term):
    """True when a tracked file other than the glossary and its history names `term` (whole words, any case, a plural)."""
    rx, rel = pattern(term), glossary_rel(root)
    first = words(term).split()
    if not rx or not first:
        return True
    rc, out = git(root, "grep", "-I", "-i", "-l", "-z", "-F", "-e", first[0], "--", ".", f":(exclude){rel}", f":(exclude){history_rel(rel)}")
    for p in (x for x in out.split("\0") if x) if rc == 0 else ():
        try:
            with open(os.path.join(root, p), encoding="utf-8", errors="replace") as f:
                if rx.search(words(f.read())):
                    return True
        except OSError:
            continue
    return False


def digest(term, row):
    return hashlib.sha256(json.dumps(["retire-term", term, row], ensure_ascii=False).encode()).hexdigest()


def question(term, row):
    return f"Approve retiring glossary term {term} at {digest(term, row)[:16]}?"


def read_glossary(root):
    try:
        with open(os.path.join(root, glossary_rel(root)), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def candidates(start):
    """[(term, question)] of the terms nothing uses outside the glossary — retirement candidates, never removed by code alone."""
    root = main_checkout(repo_root(start))
    return [(t["term"], question(t["term"], t["row"])) for t in parse(read_glossary(root)) if not used(root, t["term"])]


def slug(term):
    return re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-") or "term"


def record_path(root, term):
    return os.path.join(root, ".reef", "approvals", f"glossary-{slug(term)}.json")


def approve(root, term, digest16):
    """The owner's `Approve retiring glossary term <term> at <digest16>?`: (ok, message). The row moves to the history file;
    an unknown term, a stale digest (the row changed) or a term used since: nothing written."""
    text = read_glossary(root)
    row = next((t["row"] for t in parse(text) if t["term"] == term), None)
    if row is None:
        return False, f"glossary term {term}: no such term in {glossary_rel(root)} — nothing written"
    dg = digest(term, row)
    if dg[:16] != digest16:
        return False, f"glossary term {term}: the question's digest {digest16} is not the row's ({dg[:16]}) (stale) — nothing written"
    if used(root, term):
        return False, f"glossary term {term}: it is used outside {glossary_rel(root)} now — not a candidate, nothing written"
    rel = glossary_rel(root)
    hist = history_rel(rel)
    lines = text.splitlines(keepends=True)
    i = next(i for i, l in enumerate(lines) if l.strip() == row)
    with open(os.path.join(root, rel) + ".tmp", "w", encoding="utf-8") as f:
        f.write("".join(lines[:i] + lines[i + 1:]))
    os.replace(os.path.join(root, rel) + ".tmp", os.path.join(root, rel))
    hp = os.path.join(root, hist)
    new = not os.path.isfile(hp)
    with open(hp, "a", encoding="utf-8") as f:
        f.write(("# Glossary — history\n\nEvery retired term, never deleted. Written by scripts/reef-glossary.py on the owner's approval.\n\n" if new else "")
                + f"- {time.strftime('%Y-%m-%d', time.gmtime())} retired: {row}\n")
    os.makedirs(os.path.dirname(record_path(root, term)), exist_ok=True)
    with open(record_path(root, term), "w", encoding="utf-8") as f:
        json.dump({"action": "retire-term", "term": term, "digest16": dg[:16], "digest": dg, "by": "owner", "paths": [rel, hist],
                   "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=1)
        f.write("\n")
    return True, f"glossary term {term} retired from {rel} (kept in {hist}) — the next tick commits it"


def records(root):
    d = os.path.join(root, ".reef", "approvals")
    out = []
    for n in sorted(os.listdir(d)) if os.path.isdir(d) else ():
        if n.startswith("glossary-") and n.endswith(".json"):
            try:
                with open(os.path.join(d, n), encoding="utf-8") as f:
                    rec = json.load(f)
            except (OSError, ValueError):
                continue
            if isinstance(rec, dict) and rec.get("action") == "retire-term":
                out.append((os.path.join(d, n), rec))
    return out


def commit_pending(start):
    """On the tick: each approved retirement not yet committed is committed — its two files alone, under the pre-commit gate
    (reef-lessons.py's commit). A refusal stays on the record for the doctor; None, or the last why."""
    root = main_checkout(repo_root(start))
    why = None
    for p, rec in records(root):
        if rec.get("committed_at"):
            continue
        paths = [x for x in rec.get("paths") or [] if isinstance(x, str)]
        st = subprocess.run(["git", "-C", root, "status", "--porcelain", "--untracked-files=all", "--", *paths], capture_output=True, text=True, timeout=60)
        if st.returncode == 0 and not st.stdout.strip():
            rec.update(committed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), refused=None)
        else:
            why = load_sibling("reef-lessons.py", "reef_lessons_for_glossary").commit(
                root, [os.path.join(root, x) for x in paths], f"reef: glossary term {rec.get('term')} retired — committed on the tick (the owner's approval)")
            rec.update(committed_at=None if why else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), refused=why)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1)
            f.write("\n")
    return why


def doctor_lines(start):
    """[(level, what, fix)] for reef doctor: each candidate with the owner's command, each refused commit with its why."""
    root = main_checkout(repo_root(start))
    rel = glossary_rel(root)
    out = [("WARN", f'glossary: "{t}" appears nowhere outside {rel}, a retirement candidate', f'python3 scripts/reef-approval.py --owner "{q}"')
           for t, q in candidates(root)]
    out += [("WARN", f"glossary: the retirement of {rec.get('term')} is not committed ({str(rec['refused'])[:120]})", "python3 scripts/reef-loop.py tick")
            for _, rec in records(root) if rec.get("refused") and not rec.get("committed_at")]
    return out


def main(argv):
    repo = argv[argv.index("--repo") + 1] if "--repo" in argv and argv.index("--repo") + 1 < len(argv) else "."
    args = [a for i, a in enumerate(argv) if a != "--repo" and (i == 0 or argv[i - 1] != "--repo")]
    if args[:1] == ["check"] and len(args) <= 2:
        rc, base = git(repo, "merge-base", args[1], "HEAD") if len(args) == 2 else git(repo, "rev-parse", "HEAD")
        if rc != 0:
            die(f"no merge-base of {args[1] if len(args) == 2 else 'HEAD'} and HEAD")
        fails, nits, note = check(repo, base.strip())
        for line in ([note] if note else []) + [f"glossary: FAIL — {m}" for m in fails] + [f"glossary: NIT — {m}" for m in nits]:
            print(line)
        return 1 if fails else 0
    if args == ["candidates"]:
        for _, what, fix in doctor_lines(repo):
            print(f"{what} — {fix}")
        return 0
    print("usage: reef-glossary.py check [<rev>] [--repo DIR] | candidates [--repo DIR]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
