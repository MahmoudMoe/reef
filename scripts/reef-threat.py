#!/usr/bin/env python3
# CLASS: code
"""Reef threat — the threat model linted against the architecture.
  reef-threat.py lint  [--repo DIR]   every trust-boundary crossing in workspace.dsl has a STRIDE row in
                                      reef/architecture/threat-model.md naming mitigation AND proof, or `accepted: <reason>`
  reef-threat.py rows  [--repo DIR]   unmitigated rows as found queue rows (touches: set)
  reef-threat.py fresh [--repo DIR]   exit 0 iff the threat model is at least as new as architecture.md
"""
import os
import re
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # the shared helpers live beside this script
sys.dont_write_bytecode = True   # and no scripts/__pycache__ lands in a project's tree (reef-update, a row worktree read it as changes)
from reef_common import read_replace as read, table_cells  # noqa: E402

DSL = "reef/architecture/workspace.dsl"
TM = "reef/architecture/threat-model.md"
ARCH = "reef/architecture/architecture.md"
TEST_RE = re.compile(r"(?<![A-Za-z0-9_])test_[a-z0-9_]+|(?<![A-Za-z0-9_])Test[A-Z][A-Za-z0-9_]*|(?:\bit|\btest|\bdescribe)\((['\"]).+?\1\)|`[^`]+`")
STRIDE = {"S", "T", "R", "I", "D", "E", "SPOOFING", "TAMPERING", "REPUDIATION", "INFORMATION DISCLOSURE", "DENIAL OF SERVICE", "ELEVATION OF PRIVILEGE"}


def crossings(dsl):
    kinds = {}
    for m in re.finditer(r"^\s*(\w+)\s*=\s*(person|softwareSystem|container)\s+\"[^\"]*\"([^\n]*)$", dsl, re.M):
        line = m.group(3)
        kinds[m.group(1)] = "store" if "Database" in line else ("external" if m.group(2) == "softwareSystem" and "External" in line else m.group(2))
    out = []
    for a, b in re.findall(r"^\s*(\w+)\s*->\s*(\w+)", dsl, re.M):
        ka, kb = kinds.get(a, "?"), kinds.get(b, "?")
        if ka != kb or "external" in (ka, kb):
            out.append(f"{a} -> {b}")
    return out


def rows(tm):
    out = []
    for line in tm.splitlines():
        cells = table_cells(line)
        if len(cells) >= 5 and re.match(r"^\w+\s*->\s*\w+$", cells[0]):
            out.append({"crossing": re.sub(r"\s+", " ", cells[0]), "stride": cells[1], "threat": cells[2], "mitigation": cells[3], "proof": cells[4]})
    return out


def lint_threat(root):
    bad = []
    dsl_p, tm_p = os.path.join(root, DSL), os.path.join(root, TM)
    if not os.path.isfile(dsl_p):
        return [f"no {DSL} — run scripts/reef-c4.py generate --write first"]
    if not os.path.isfile(tm_p):
        return [f"no {TM} — /reef-threat writes it from the architecture"]
    tm = read(tm_p)
    if "```mermaid" not in tm:
        bad.append(f"{TM}: no Mermaid data-flow diagram of the trust boundaries")
    rs = rows(tm)
    covered = {r["crossing"] for r in rs}
    for c in crossings(read(dsl_p)):
        if c not in covered:
            bad.append(f"{TM}: boundary crossing `{c}` has no STRIDE row")
    for r in rs:
        if r["stride"].upper() not in STRIDE and not all(ch in "STRIDE" for ch in r["stride"].upper().replace(",", "").replace(" ", "")):
            bad.append(f"{TM}: row `{r['crossing']}` STRIDE cell {r['stride']!r} is not a STRIDE class")
        if r["mitigation"].lower().startswith("accepted:"):
            if len(r["mitigation"]) < 12:
                bad.append(f"{TM}: row `{r['crossing']}` accepts the risk without a reason")
            continue
        if not r["mitigation"] or r["mitigation"] in ("-", "—", "TODO"):
            bad.append(f"{TM}: row `{r['crossing']}` ({r['threat'][:40]}) names no mitigation and is not `accepted: <reason>`")
        if not TEST_RE.search(r["proof"]):
            bad.append(f"{TM}: row `{r['crossing']}` ({r['threat'][:40]}) names no proving test or command")
    return bad


def fresh(root):
    a, t = os.path.join(root, ARCH), os.path.join(root, TM)
    if not os.path.isfile(t):
        return False, f"no {TM}"
    if not os.path.isfile(a):
        return True, f"no {ARCH} to be older than"

    def stamp(p):
        r = subprocess.run(["git", "-C", root, "log", "-1", "--format=%ct", "--", os.path.relpath(p, root)], capture_output=True, text=True)
        return int(r.stdout.strip() or 0) or int(os.path.getmtime(p))
    return stamp(t) >= stamp(a), f"threat model {'newer than or as new as' if stamp(t) >= stamp(a) else 'OLDER than'} the architecture document"


def main(argv):
    repo = "."
    if "--repo" in argv:
        repo = argv[argv.index("--repo") + 1]
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=repo, capture_output=True, text=True).stdout.strip() or os.path.abspath(repo)
    cmd = argv[0] if argv and not argv[0].startswith("-") else "lint"
    if cmd == "lint":
        bad = lint_threat(root)
        for b in bad:
            print(f"FAIL: {b}")
        print("ok: every boundary crossing has a mitigated or accepted STRIDE row" if not bad else f"{len(bad)} threat lint failure(s)")
        return 1 if bad else 0
    if cmd == "rows":
        tm_p = os.path.join(root, TM)
        n = 0
        for r in (rows(read(tm_p)) if os.path.isfile(tm_p) else []):
            if r["mitigation"].lower().startswith("accepted:") or (r["mitigation"] not in ("", "-", "—", "TODO") and TEST_RE.search(r["proof"])):
                continue
            touches = "auth" if r["stride"].upper().startswith(("S", "E")) else ("pii" if r["stride"].upper().startswith("I") else "")
            n += 1
            print(f"| <next id> | Mitigate {r['threat'][:60]} on `{r['crossing']}` | | found | <next batch> | | touches: [{touches}]")
        print(f"{n} unmitigated row(s)")
        return 0
    if cmd == "fresh":
        ok, why = fresh(root)
        print(("ok: " if ok else "STALE: ") + why)
        return 0 if ok else 1
    print("usage: reef-threat.py lint|rows|fresh [--repo DIR]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
