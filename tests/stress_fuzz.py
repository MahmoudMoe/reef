"""Stress suite, round three: a seeded FUZZ of every file an agent (or the owner) writes that a script then trusts.

For each file kind: valid samples (taken from the agents' Output blocks and the existing suites), seeded mutations, and the
PROPERTY every reader must hold for every mutant — it reads the SAME meaning as the original when the mutation is meaning-
preserving (CRLF, trailing spaces, quotes, …), the mutant's own meaning when the mutation changes it, or it REFUSES loudly
(a non-zero exit, a None/'' the callers die on, a failed `reef-queue.py check`). It never silently reads a DIFFERENT meaning:
PASS where the last verdict is FAIL, another row, another head, a different status.

Each mutation class is classified up front, per kind (the `SAME` / `REFUSE` / `IS` column of each table below). One test per
reader and mutation class; its failure message names up to three mutants. A failing test is a finding (see the findings file);
a passing one is coverage. Seed fixed: the same mutants every run.
"""
import contextlib
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import ROOT, git, load_script, write  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.dont_write_bytecode = True
import reef_common as RC  # noqa: E402

SEED = 20261103
CLAIMS = os.path.join(ROOT, "scripts", "reef-claims.py")
RECORD = os.path.join(ROOT, "scripts", "reef-record")
ADV = os.path.join(ROOT, "scripts", "reef-adversarial")

REFUSED = "<REFUSED>"
SAME, REFUSE = "SAME", "REFUSE"          # expectations; ("IS", meaning) = the mutant's own meaning


def IS(m):
    return ("IS", m)


# ------------------------------------------------------------------ generic text mutations

def crlf(t):
    return t.replace("\r\n", "\n").replace("\n", "\r\n")


def mixed(t, rng):
    out = []
    for line in t.split("\n")[:-1]:
        out.append(line + ("\r\n" if rng.random() < 0.5 else "\n"))
    out.append(t.split("\n")[-1])
    s = "".join(out)
    return s if s != t and s != crlf(t) else crlf(t).replace("\r\n", "\n", 1)


def bom(t):
    return "﻿" + t


def trailing(t, rng, only=None):
    lines = t.split("\n")
    idx = [i for i, l in enumerate(lines) if l.strip() and (only is None or re.match(only, l))]
    for i in rng.sample(idx, max(1, len(idx) // 2)) if idx else []:
        lines[i] += rng.choice([" ", "  ", "\t", " \t "])
    return "\n".join(lines)


def last_idx(lines, pat):
    found = [i for i, l in enumerate(lines) if re.match(pat, l)]
    return found[-1] if found else None


def first_idx(lines, pat):
    found = [i for i, l in enumerate(lines) if re.match(pat, l)]
    return found[0] if found else None


def edit_line(t, pat, fn, last=True):
    lines = t.split("\n")
    i = (last_idx if last else first_idx)(lines, pat)
    if i is None:
        return None
    lines[i] = fn(lines[i])
    return "\n".join(lines)


def insert_after(t, pat, new, last=False):
    lines = t.split("\n")
    i = (last_idx if last else first_idx)(lines, pat)
    if i is None:
        return None
    lines[i + 1:i + 1] = new.split("\n")
    return "\n".join(lines)


def insert_before(t, pat, new, last=True):
    lines = t.split("\n")
    i = (last_idx if last else first_idx)(lines, pat)
    if i is None:
        return None
    lines[i:i] = new.split("\n")
    return "\n".join(lines)


CYR = {"A": "А", "E": "Е", "P": "Р", "S": "Ѕ", "I": "І", "C": "С", "T": "Т", "O": "О",
       "a": "а", "e": "е", "o": "о", "s": "ѕ", "p": "р", "c": "с"}
ARABIC = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
FULL = str.maketrans("0123456789", "０１２３４５６７８９")
SUPS = "¹²³⁴⁵⁶⁷⁸⁹"


def lookalike(word, rng):
    pos = [i for i, c in enumerate(word) if c in CYR]
    i = rng.choice(pos)
    return word[:i] + CYR[word[i]] + word[i + 1:]


# ------------------------------------------------------------------ report mutations (verifier, acceptance, security, hunter)

V_LINE = r"VERDICT:"


def report_ops(opposite):
    """(class, fn(text, rng) -> mutant | None, expectation). `opposite(v)` is the verdict word that would flip the meaning."""
    def val(line):
        return line.split(":", 1)[1].strip()

    def opp(t):
        lines = t.split("\n")
        return opposite(val(lines[last_idx(lines, V_LINE)]))

    def truncated(t, rng):
        lines = t.split("\n")
        i = last_idx(lines, V_LINE)
        end = len("\n".join(lines[:i + 1]))      # the end of the last VERDICT line's value
        cut = rng.randrange(len(lines[0]) + 1, len(t))
        return t[:cut], (SAME if cut >= end else REFUSE)

    return [
        ("crlf", lambda t, r: crlf(t), SAME),
        ("mixed_endings", mixed, SAME),
        ("bom", lambda t, r: bom(t), SAME),
        ("trailing_spaces", lambda t, r: trailing(t, r), SAME),
        ("tab_after_colon", lambda t, r: edit_line(t, V_LINE, lambda l: l.replace("VERDICT: ", "VERDICT:\t", 1)), SAME),
        ("extra_section", lambda t, r: insert_after(t, r"(RUN|HEAD):", "\n## Notes\n- unrelated: the build took 41 s\n"), SAME),
        ("verdict_value_case", lambda t, r: edit_line(t, V_LINE, lambda l: "VERDICT: " + r.choice([str.lower, str.title])(val(l))), SAME),
        ("verdict_value_quoted", lambda t, r: edit_line(t, V_LINE, lambda l: "VERDICT: " + r.choice(["'{}'", '"{}"', "`{}`"]).format(val(l))), SAME),
        ("verdict_key_case", lambda t, r: edit_line(t, V_LINE, lambda l: r.choice(["verdict:", "Verdict:"]) + l[len("VERDICT:"):]), SAME),
        ("verdict_markdown", lambda t, r: edit_line(t, V_LINE, lambda l: r.choice(["- {}", "**{}**", "* {}"]).format(l)), SAME),
        ("verdict_key_lookalike", lambda t, r: edit_line(t, V_LINE, lambda l: lookalike("VERDICT", r) + l[len("VERDICT"):]), SAME),
        ("verdict_value_lookalike", lambda t, r: edit_line(t, V_LINE, lambda l: "VERDICT: " + lookalike(val(l), r)), SAME),
        ("verdict_empty_value", lambda t, r: edit_line(t, V_LINE, lambda l: "VERDICT:"), REFUSE),
        ("verdict_fenced_after", lambda t, r: t.rstrip("\n") + f"\nExample of the expected output:\n```\nVERDICT: {opp(t)}\n```\n", SAME),
        ("verdict_quoted_after", lambda t, r: t.rstrip("\n") + f"\n> VERDICT: {opp(t)}\n", SAME),
        ("verdict_duplicate_earlier", lambda t, r: insert_before(t, V_LINE, f"VERDICT: {opp(t)}"), SAME),   # the LAST one wins
        ("verdict_duplicate_same", lambda t, r: edit_line(t, V_LINE, lambda l: l + "\n" + l), SAME),
        ("truncated", truncated, None),
    ]


def other_verdict(v):
    return "FAIL" if v.upper() in ("PASS", "GREEN") else "PASS"


def other_green(v):
    return "FAIL" if v.upper() in ("PASS", "GREEN") else "GREEN"


def blocker_ops():
    return [
        ("blocker_key_case", lambda t, r: edit_line(t, r"BLOCKER\b", lambda l: r.choice(["Blocker", "blocker"]) + l[len("BLOCKER"):], last=False), SAME),
        ("blocker_markdown", lambda t, r: edit_line(t, r"BLOCKER\b", lambda l: r.choice(["- **BLOCKER**", "**Blocker**", "- Blocker"]) + l[len("BLOCKER"):],
                                                     last=False), SAME),
        ("blocker_lookalike", lambda t, r: edit_line(t, r"BLOCKER\b", lambda l: lookalike("BLOCKER", r) + l[len("BLOCKER"):], last=False), SAME),
    ]


# ------------------------------------------------------------------ the mutant table

def build(kind, samples, ops, n_target, rng):
    """[(sample name, class, mutant, expectation)], each op on each sample at least once, then seeded repeats up to n_target."""
    out, seen = [], set()

    def one(name, text, cls, fn, exp):
        try:
            res = fn(text, rng)
        except (ValueError, IndexError):
            return
        if res is None:
            return
        if isinstance(res, tuple):
            res, exp = res
        if res == text or (name, res) in seen:
            return
        seen.add((name, res))
        out.append((name, cls, res, exp))

    for name, text in samples.items():
        for cls, fn, exp in ops:
            if cls.startswith("blocker") and "BLOCKER" not in text.replace("BLOCKER: none", ""):
                continue
            one(name, text, cls, fn, exp)
    tries = 0
    while len(out) < n_target and tries < n_target * 20:
        tries += 1
        name = rng.choice(sorted(samples))
        cls, fn, exp = rng.choice(ops)
        if cls.startswith("blocker") and "BLOCKER" not in samples[name].replace("BLOCKER: none", ""):
            continue
        one(name, samples[name], cls, fn, exp)
    return out


def violates(got, orig, exp):
    if got == REFUSED:
        return False
    if exp == SAME:
        return got != orig
    if exp == REFUSE:
        return True
    return got != exp[1]


# ================================================================== the kinds

H40 = "3f2a9c1d7e5b4a6c8d9e0f1a2b3c4d5e6f708192"
OLD40 = "0b1c2d3e4f5a69788796a5b4c3d2e1f00f1e2d3c"

VERIFIER = {
    "pass": ("RUN: agent=verifier task=101 round=1\n"
             "RULE AC1: PASS iff test_guard_refuses goes red first — `pytest tests/test_guard.py::test_guard_refuses`\n"
             "AC1 PASS — tests/test_guard.py:12 test_guard_refuses, exit 0\n"
             "VERDICT: PASS\n"),
    # verifier.md: "ends `VERDICT: PASS` or `VERDICT: FAIL` + concrete feedback"; a round-2 report quoting round 1's
    "fail_quoting_pass": ("RUN: agent=verifier task=101 round=2\n"
                          "RULE AC1: PASS iff test_guard_refuses goes red first — `pytest tests/test_guard.py::test_guard_refuses`\n"
                          "Round 1 said:\n```\nAC1 PASS — tests/test_guard.py:12\nVERDICT: PASS\n```\n"
                          "AC1 FAIL — tests/test_guard.py:12 asserts nothing after the fix\n"
                          "VERDICT: FAIL\n"
                          "- feedback: assert the exit code at tests/test_guard.py:14\n"),
}
VERIFIER_MEANING = {"pass": "PASS", "fail_quoting_pass": "FAIL"}

ACCEPT = {
    "green": (f"HEAD: {H40[:12]}\nRUN: agent=acceptance feature=share-page\nGATE: green at {H40[:12]}\n"
              "FR-1 PASS — tests/test_share.py:10 test_share_link\nNIT: rename helper\nVERDICT: GREEN\n"),
    "green_old_head": (f"HEAD: {OLD40[:12]}\nRUN: agent=acceptance feature=share-page\nGATE: green at {OLD40[:12]}\n"
                       "FR-1 PASS — tests/test_share.py:10 test_share_link\nVERDICT: GREEN\n"),
    "fail_quoting_green": (f"HEAD: {H40[:12]}\nRUN: agent=acceptance feature=share-page\nGATE: green at {H40[:12]}\n"
                           f"Last round:\n```\nHEAD: {OLD40[:12]}\nVERDICT: GREEN\n```\n"
                           "AC-3 FAIL — its Proof test tests something else\nBLOCKER: data — the link leaks the owner id\nVERDICT: FAIL\n"),
}
ACCEPT_MEANING = {"green": "BOUND", "green_old_head": REFUSED, "fail_quoting_green": REFUSED}

HUNTER = {
    "pass": "RUN: agent=loophole-hunter task=1 pass=plan round=1\nDEFECT: x\nBLOCKER: none\nNONE: tried y\nVERDICT: PASS\n",
    "pass_with_blocker": ("RUN: agent=loophole-hunter task=1 pass=plan round=1\nDEFECT: the stripper misses a heredoc\n"
                          "BLOCKER: a heredoc body is not stripped — will happen: tests/x.sh:3 — fix: strip it\nVERDICT: PASS\n"),
    "fail_quoting_pass": ("RUN: agent=loophole-hunter task=1 pass=plan round=1\nDEFECT: x\nThe verifier's report:\n```\n"
                          "RUN: agent=verifier task=1\nVERDICT: PASS\n```\nBLOCKER: the check reads the first line only — will happen: a.py:3 — fix: last\n"
                          "VERDICT: FAIL\n"),
}
HUNTER_MEANING = {"pass": "RECORDED", "pass_with_blocker": REFUSED, "fail_quoting_pass": REFUSED}


def security_samples(h12):
    run = f"RUN: agent=security range=release...main head={h12}"
    return {
        "pass": f"{run}\nSPINE: docs/threat.md\nHIGH src/a.py:3 — the cookie is not SameSite — set it\nNIT src/b.py:1 — a name — rename\nVERDICT: PASS\n",
        "pass_with_blocker": (f"{run}\nSPINE: docs/threat.md\nBLOCKER src/auth.py:9 — a session never expires — expire it\n"
                              "VERDICT: PASS\n"),
        "fail_quoting_pass": (f"{run}\nSPINE: docs/threat.md\nThe last release's pass:\n```\nVERDICT: PASS\n```\n"
                              "BLOCKER src/auth.py:9 — a session never expires — expire it\nVERDICT: FAIL\n"),
        "pass_old_head": f"RUN: agent=security range=release...main head={OLD40[:12]}\nSPINE: docs/threat.md\nVERDICT: PASS\n",
    }


SECURITY_MEANING = {"pass": "RECORDED", "pass_with_blocker": REFUSED, "fail_quoting_pass": REFUSED, "pass_old_head": REFUSED}


def head_ops():
    return [
        # SAME, not REFUSE: the report opens with HEAD (acceptance.md:3, :24) — reclassified in docs/review/stress-2026-11-03-hard.md
        ("head_duplicate_conflicting", lambda t, r: insert_after(t, r"RUN:", f"HEAD: {r.choice([OLD40, H40])[:12]}"), SAME),
        ("head_key_case", lambda t, r: edit_line(t, r"HEAD:", lambda l: "Head:" + l[5:], last=False), SAME),
        ("head_upper_hex", lambda t, r: edit_line(t, r"HEAD:", lambda l: "HEAD: " + l[6:].upper(), last=False), SAME),
        ("head_fullwidth_digit", lambda t, r: edit_line(t, r"HEAD:", lambda l: "HEAD: " + l[6:].translate(FULL), last=False), SAME),
    ]


def run_ops():
    return [
        # head=\S+ so the {HEAD12} placeholder is replaced; SAME: the RUN line is the first line (security.md:32) — reclassified in
        # docs/review/stress-2026-11-03-hard.md
        ("run_duplicate_conflicting", lambda t, r: insert_after(t, r"RUN:", re.sub(r"head=\S+", f"head={r.choice([OLD40, H40])[:12]}",
                                                                                     t.split("\n")[first_idx(t.split("\n"), r"RUN:")])), SAME),
        ("run_head_quoted", lambda t, r: edit_line(t, r"RUN:", lambda l: re.sub(r"head=(\w+)", r"head='\1'", l), last=False), SAME),
    ]


# ------------------------------------------------------------------ task frontmatter

TASK = ("---\nid: 7\nfeature: 12\nstatus: done\ncomplexity: design\ntier: critical\nverify: judge\nblocked-by: [5, 6]\n"
        "attempts: 1\nworktree: .reef/worktrees/7\n---\n# 7\n\n## Scope\nthe defect\n\n## Acceptance Criteria\n- AC1 the test goes red\n\n## Log\n")
TASK_PENDING = TASK.replace("status: done", "status: pending")
FM_KEYS = ("id", "feature", "status", "tier", "verify", "blocked-by")


def fm_meaning(text):
    m = {}
    for k in FM_KEYS:
        mm = re.search(rf"^{k}: (.*)$", text, re.M)
        m[k] = mm.group(1) if mm else None
    m["blocked-by"] = norm_list(m["blocked-by"])
    return m


def norm_list(raw):
    if raw is None:
        return None
    return tuple(x.strip().strip("'\"") for x in raw.strip().strip("[]").split(",") if x.strip())


def fm_set(t, key, line):
    """Replace the frontmatter line of `key` (first) by `line`."""
    return edit_line(t, rf"{re.escape(key)}:", lambda l: line, last=False)


def fm_ops():
    def q(t, r, quote):
        k = r.choice(["id", "feature", "status", "tier", "verify"])
        return fm_set(t, k, f"{k}: {quote}{fm_meaning(t)[k]}{quote}")

    def changed(t, **kv):
        m = fm_meaning(t)
        m.update(kv)
        return m

    def trunc(t, r):
        close = t.index("\n---\n", 4) + 5
        cut = r.randrange(5, len(t))
        return t[:cut], (SAME if cut >= close else REFUSE)

    return [
        ("crlf", lambda t, r: crlf(t), SAME),
        ("mixed_endings", mixed, SAME),
        ("bom", lambda t, r: bom(t), SAME),
        ("trailing_spaces", lambda t, r: trailing(t, r, only=r"[a-z-]+:"), SAME),
        ("tab_after_colon", lambda t, r: edit_line(t, rf"{r.choice(FM_KEYS[:5])}: ", lambda l: l.replace(": ", ":\t", 1), last=False), SAME),
        ("value_quoted_double", lambda t, r: q(t, r, '"'), SAME),
        ("value_quoted_single", lambda t, r: q(t, r, "'"), SAME),
        ("value_case", lambda t, r: r.choice([lambda: fm_set(t, "status", "status: " + fm_meaning(t)["status"].title()),
                                              lambda: fm_set(t, "tier", "tier: Critical"),
                                              lambda: fm_set(t, "verify", "verify: Judge")])(), SAME),
        ("key_case", lambda t, r: fm_set(t, "status", "Status: " + fm_meaning(t)["status"]), SAME),
        ("key_lookalike", lambda t, r: fm_set(t, "status", "ѕtatus: " + fm_meaning(t)["status"]), SAME),
        ("duplicate_key_later", lambda t, r: insert_after(t, r"worktree:", "status: " + ("pending" if "done" in t else "done")), SAME),   # first wins
        ("duplicate_key_earlier", lambda t, r: (insert_after(t, r"id:", "status: " + ("pending" if "status: done" in t else "done")),
                                                IS(changed(t, status="pending" if "status: done" in t else "done"))), None),
        ("duplicate_key_indented", lambda t, r: insert_after(t, r"worktree:", "  status: pending"), SAME),
        ("duplicate_key_comment", lambda t, r: insert_after(t, r"id:", "# status: pending"), SAME),
        ("empty_value", lambda t, r: fm_set(t, "status", r.choice(["status:", "status: ", 'status: ""'])), REFUSE),
        ("unicode_digit_feature", lambda t, r: fm_set(t, "feature", "feature: " + "12".translate(r.choice([ARABIC, FULL]))), SAME),
        ("unicode_digit_id", lambda t, r: fm_set(t, "id", "id: " + "7".translate(r.choice([ARABIC, FULL]))), SAME),
        ("truncated", trunc, None),
        ("extra_section", lambda t, r: t + "\n## Notes\nstatus: pending\nfeature: 99\n", SAME),
    ]


# ------------------------------------------------------------------ hand-back

HANDBACK = {
    "ok": ("RUN: agent=implementer task=101 model=m\n"
           "- the guard refuses a heredoc — true at scripts/guard.py:12\n"
           "- its test goes red first — true at tests/test_guard.py:30-34\n"),
    "no_claims": "RUN: agent=implementer task=101 model=m\nDone. All good, tests pass.\n",
}
HANDBACK_MEANING = {"ok": "OK", "no_claims": REFUSED}


def handback_ops():
    return [
        ("crlf", lambda t, r: crlf(t), SAME),
        ("mixed_endings", mixed, SAME),
        ("bom", lambda t, r: bom(t), SAME),
        ("trailing_spaces", lambda t, r: trailing(t, r), SAME),
        ("extra_section", lambda t, r: t + "\n## Notes\n- the build took 41 s\n", SAME),
        ("run_key_case", lambda t, r: edit_line(t, "RUN:", lambda l: "run:" + l[4:], last=False), SAME),
        ("run_quoted", lambda t, r: edit_line(t, "RUN:", lambda l: "> " + l, last=False), SAME),
        ("claim_in_fence", lambda t, r: t + "Example claim shape:\n```\n- x — true at a.py:1\n```\n", SAME),
        ("claim_in_quote", lambda t, r: t + "> - x — true at a.py:1\n", SAME),
        ("empty", lambda t, r: "", REFUSE),
    ]


# ------------------------------------------------------------------ journal block

JTASK = ("---\nid: 7\nfeature: share-page\nstatus: done\n---\n# 7\n\n## Log\n- round 1: gate green\n"
         "<!-- journal -->\n| 7 | sonnet | - | 1 | gate green | AC1 | - |\n<!-- /journal -->\n")
JOURNAL_MEANING = ("| 7 | sonnet | - | 1 | gate green | AC1 | - |",)


def journal_ops():
    def trunc(t, r):
        start = t.index("<!-- journal -->")
        end = t.index("<!-- /journal -->") + len("<!-- /journal -->")
        cut = r.randrange(start + 1, len(t))
        return t[:cut], (SAME if cut >= end else REFUSE)

    return [
        ("crlf", lambda t, r: crlf(t), SAME),
        ("mixed_endings", mixed, SAME),
        ("trailing_spaces", lambda t, r: trailing(t, r, only=r"<!--"), SAME),
        ("marker_case", lambda t, r: t.replace("<!-- journal -->", "<!-- Journal -->"), SAME),
        ("marker_spacing", lambda t, r: t.replace("<!-- journal -->", r.choice(["<!--journal-->", "<!--  journal -->"])), SAME),
        ("example_in_fence", lambda t, r: t.replace("- round 1: gate green\n", "- round 1: gate green\n- the block's shape:\n```\n"
                                                    "<!-- journal -->\n| id | model | … |\n<!-- /journal -->\n```\n"), SAME),
        ("example_in_quote", lambda t, r: t.replace("- round 1: gate green\n", "- round 1: gate green\n"
                                                    "> <!-- journal -->\n> | id | model | … |\n> <!-- /journal -->\n"), SAME),
        ("block_duplicate_same", lambda t, r: t + "<!-- journal -->\n| 7 | sonnet | - | 1 | gate green | AC1 | - |\n<!-- /journal -->\n", SAME),
        ("block_indented_in_list", lambda t, r: t.replace("<!-- journal -->\n|", "  <!-- journal -->\n  |").replace("\n<!-- /journal -->", "\n  <!-- /journal -->"), SAME),
        ("truncated", trunc, None),
    ]


# ------------------------------------------------------------------ queue table

QUEUE = ("# Queue\n\nCurrent batch: 2\n\n"
         "| Id | Item | Depends | Batch | Source |\n|---|---|---|---|---|\n"
         "| 3 | export the csv | | 1 | planned |\n"
         "| 12 | share page | 3 | 2 | planned |\n"
         "| 14 | dark mode | | 2 | found |\n"
         "| 15 | share analytics | 12, 14 | 2 | planned |\n")


def queue_meaning_of(text):
    """The meaning the sample states: (current batch, ((id, depends, batch), …))."""
    return ("2", (("3", (), "1"), ("12", ("3",), "2"), ("14", (), "2"), ("15", ("12", "14"), "2")))


def queue_ops():
    def row_line(t, rid):
        return rf"\| {rid} \|"

    def drop_row_id(t, r):
        rid = r.choice(["14", "15"])
        return edit_line(t, row_line(t, rid), lambda l: l.replace(f"| {rid} |", "|  |", 1), last=False)

    return [
        ("crlf", lambda t, r: crlf(t), SAME),
        ("mixed_endings", mixed, SAME),
        ("bom", lambda t, r: bom(t), SAME),
        ("trailing_spaces", lambda t, r: trailing(t, r), SAME),
        ("tabs_in_cells", lambda t, r: t.replace(" | ", r.choice(["\t|\t", " |\t", "\t| "])), SAME),
        ("batch_cell_quoted", lambda t, r: edit_line(t, r"\| 15 \|", lambda l: l.replace("| 2 |", r.choice(["| '2' |", '| "2" |']), 1), last=False), SAME),
        ("current_batch_quoted", lambda t, r: t.replace("Current batch: 2", r.choice(["Current batch: '2'", 'Current batch: "2"'])), SAME),
        ("current_batch_duplicate", lambda t, r: t.replace("Current batch: 2\n", "Current batch: 2\nCurrent batch: 3\n"), REFUSE),
        ("current_batch_key_case", lambda t, r: t.replace("Current batch:", r.choice(["current batch:", "Current Batch:"])), SAME),
        ("current_batch_unicode_digit", lambda t, r: t.replace("Current batch: 2", "Current batch: " + "2".translate(r.choice([ARABIC, FULL]))), SAME),
        ("header_case", lambda t, r: t.replace("| Id |", r.choice(["| id |", "| ID |"])), SAME),
        ("row_duplicate_conflicting", lambda t, r: t + "| 14 | dark mode | 3 | 2 | found |\n", REFUSE),
        ("row_id_unicode_digit", lambda t, r: edit_line(t, r"\| 15 \|", lambda l: l.replace("| 15 |", "| " + "15".translate(r.choice([ARABIC, FULL])) + " |", 1), last=False), SAME),
        ("row_id_superscript", lambda t, r: edit_line(t, r"\| 15 \|", lambda l: l.replace("| 15 |", "| 15" + r.choice(SUPS) + " |", 1), last=False), SAME),
        ("row_id_empty", drop_row_id, REFUSE),
        ("depends_unicode_digit", lambda t, r: t.replace("| 12, 14 |", "| 12, " + "14".translate(r.choice([ARABIC, FULL])) + " |"), SAME),
        ("table_in_fence", lambda t, r: t.replace("Current batch: 2\n", "Current batch: 2\n\nA row looks like:\n```\n| Id | Item | Depends |\n|---|---|---|\n"
                                                  "| 99 | an example row | |\n```\n"), SAME),
        ("table_in_quote", lambda t, r: t.replace("Current batch: 2\n", "Current batch: 2\n\n> | Id | Item | Depends |\n> |---|---|---|\n> | 99 | an example | |\n"), SAME),
        ("extra_section", lambda t, r: t + "\n## Notes\n- the owner reorders on Mondays\n", SAME),
    ]


# ------------------------------------------------------------------ proxy.md / night contract

NIGHT = "# Night 2026-11-03\n\nRows: 12, 14 (not 3: it waits on the owner's question)\nLimits: no release, no money\n"
PROXY = ("# The proxy by day\nThe owner's proxy decides these.\nDecides: process, wording, plan\n"
         "- process: a task's order\nNever: product, money\n")
NIGHT_MEANING, PROXY_MEANING = ("12", "14"), ("process", "wording", "plan")


def contract_ops(key):
    def ln(t):
        return t.split("\n")[first_idx(t.split("\n"), key + ":")]

    def value(t):
        return ln(t).split(":", 1)[1].strip()

    ops = [
        ("crlf", lambda t, r: crlf(t), SAME),
        ("mixed_endings", mixed, SAME),
        ("bom", lambda t, r: bom(t), SAME),
        ("trailing_spaces", lambda t, r: trailing(t, r), SAME),
        ("tab_after_colon", lambda t, r: t.replace(f"{key}: ", f"{key}:\t"), SAME),
        ("value_quoted", lambda t, r: t.replace(ln(t), f"{key}: " + r.choice(["\"{}\"", "'{}'"]).format(value(t))), SAME),
        ("key_case", lambda t, r: t.replace(f"{key}:", r.choice([key.lower(), key.upper()]) + ":"), SAME),
        ("key_lookalike", lambda t, r: t.replace(f"{key}:", lookalike(key, r) if any(c in CYR for c in key) else "Ｒows" + ":"), SAME),
        ("line_duplicate_conflicting", lambda t, r: t + f"{key}: " + ("3" if key == "Rows" else "process") + "\n", REFUSE),
        ("line_in_fence", lambda t, r: t + "An earlier draft:\n```\n" + f"{key}: " + ("3, 12" if key == "Rows" else "plan, question") + "\n```\n", SAME),
        ("line_in_quote", lambda t, r: t + "> " + f"{key}: " + ("3" if key == "Rows" else "question") + "\n", SAME),
        ("empty_value", lambda t, r: t.replace(ln(t), f"{key}:"), REFUSE),
        ("extra_section", lambda t, r: t + "\n## Why\n- the owner sleeps\n", SAME),
    ]
    if key == "Rows":
        ops += [
            ("row_unicode_digit", lambda t, r: t.replace("Rows: 12", "Rows: " + "12".translate(r.choice([ARABIC, FULL]))), SAME),
            ("row_footnote_mark", lambda t, r: t.replace("Rows: 12,", "Rows: 12" + r.choice(SUPS) + ","), SAME),
            ("rows_and_separator", lambda t, r: t.replace("Rows: 12, 14", "Rows: 12 and 14"), SAME),
        ]
    else:
        ops += [("value_case", lambda t, r: t.replace("Decides: process, wording, plan", "Decides: Process, Wording, Plan"), SAME)]
    return ops


# ------------------------------------------------------------------ SPEC.md Row line

SPEC = "# Share page\n\nRow: 12\n\n## Intent\nThe owner shares a page.\n\n## Requirements\n- FR-1 a link\n"


def spec_ops():
    return [
        ("crlf", lambda t, r: crlf(t), SAME),
        ("mixed_endings", mixed, SAME),
        ("bom", lambda t, r: bom(t), SAME),
        ("trailing_spaces", lambda t, r: trailing(t, r), SAME),
        ("tab_after_colon", lambda t, r: t.replace("Row: 12", "Row:\t12"), SAME),
        ("value_quoted", lambda t, r: t.replace("Row: 12", r.choice(["Row: '12'", 'Row: "12"', "Row: `12`"])), SAME),
        ("key_case", lambda t, r: t.replace("Row: 12", r.choice(["row: 12", "ROW: 12"])), SAME),
        ("key_lookalike", lambda t, r: t.replace("Row: 12", r.choice(["Ｒow: 12", "Rоw: 12"])), SAME),
        ("row_unicode_digit", lambda t, r: t.replace("Row: 12", "Row: " + "12".translate(r.choice([ARABIC, FULL]))), SAME),
        ("row_footnote_mark", lambda t, r: t.replace("Row: 12", "Row: 12" + r.choice(SUPS)), SAME),
        ("row_with_note", lambda t, r: t.replace("Row: 12", "Row: 12 (split from row 3)"), SAME),
        ("row_duplicate_conflicting", lambda t, r: t.replace("Row: 12\n", "Row: 12\nRow: 14\n"), REFUSE),
        ("row_in_fence_before", lambda t, r: t.replace("Row: 12\n", "```\nRow: 3\n```\nRow: 12\n"), SAME),
        ("row_in_quote_before", lambda t, r: t.replace("Row: 12\n", "> Row: 3\nRow: 12\n"), SAME),
        ("empty_value_numbered_next", lambda t, r: t.replace("Row: 12\n\n## Intent\nThe owner", "Row:\n1. the owner"), REFUSE),
        ("extra_section", lambda t, r: t + "\n## Notes\n- split from row 3\n", SAME),
    ]


# ================================================================== readers

class Env:
    """Scratch worlds the subprocess and in-process readers run in, made once."""
    _made = None

    @classmethod
    def get(cls):
        if cls._made is None:
            cls._made = cls()
        return cls._made

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="reef-fuzz.")
        # security: a repo with a main branch head
        self.sec = os.path.join(self.tmp, "sec")
        os.makedirs(self.sec)
        subprocess.run(["git", "init", "-q", "-b", "main", self.sec], check=True)
        write(self.sec, "README.md", "x\n")
        git(self.sec, "add", "-A", check=True)
        git(self.sec, "commit", "-qm", "init", check=True)
        self.sec_head = git(self.sec, "rev-parse", "HEAD", check=True).stdout.strip()
        # hunter: a project with a critical task
        self.adv = os.path.join(self.tmp, "adv")
        write(self.adv, ".reef/config.json", json.dumps({"gates": {"test": "true"}}))
        # queue / journal / spec worlds
        self.q = os.path.join(self.tmp, "q")
        write(self.q, ".reef/config.json", "{}")
        self.queue = load_script("reef-queue.py", "reef_queue_fuzz")
        self.graph = load_script("reef-graph.py", "reef_graph_fuzz")
        self.run = load_script("reef-run.py", "reef_run_fuzz")
        self.cache = {}

    def fresh(self, name):
        d = os.path.join(self.tmp, name)
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        return d


def raw_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def quiet(fn, *a):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            rc = fn(*a)
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 2
    return rc, out.getvalue()


# --- report readers

def r_report_verdict(text):
    v = RC.report_verdict(text)
    return v or REFUSED


def r_claims_verdict(text):
    e = Env.get()
    p = os.path.join(e.tmp, "report.md")
    raw_write(p, text)
    rc = subprocess.run([sys.executable, CLAIMS, "verdict", p], capture_output=True, text=True, timeout=30).returncode
    return {0: "PASS", 1: "FAIL"}.get(rc, REFUSED)


def r_acceptance_binding(text):
    return "BOUND" if RC.report_binding(text, "acceptance", H40, ("GREEN", "PASS"), feature="share-page") == "" else REFUSED


def r_security_record(text):
    e = Env.get()
    p = os.path.join(e.tmp, "security.md")
    raw_write(p, text.replace("{HEAD12}", e.sec_head[:12]))
    shutil.rmtree(os.path.join(e.sec, ".reef"), ignore_errors=True)
    r = subprocess.run([sys.executable, RECORD, "security", "PASS", "--report", p, "--root", e.sec], capture_output=True, text=True, timeout=30)
    return "RECORDED" if r.returncode == 0 else REFUSED


def r_hunter_record(text):
    e = Env.get()
    task = ("---\nid: 1\nfeature: demo\nstatus: pending\ncomplexity: design\neffort: medium\nblocked-by: []\nresources: []\n"
            "tier: critical\nverify: judge\nattempts: 0\ndispatches: 0\n---\n# 1\n\n## Scope\nthe defect\n\n## Acceptance Criteria\n- x\n\n## Log\n")
    tp = os.path.join(e.adv, "tasks", "001-t.md")
    raw_write(tp, task)
    rp = os.path.join(e.adv, "hunt.md")
    raw_write(rp, text)
    r = subprocess.run([sys.executable, ADV, tp, "plan", rp], capture_output=True, text=True, timeout=30, cwd=e.adv)
    return "RECORDED" if r.returncode == 0 else REFUSED


# --- frontmatter readers

def r_fm_common(text):
    fm = RC.task_frontmatter(text)
    if fm is None:
        return REFUSED
    m = {k: fm.get(k) for k in FM_KEYS}
    m["blocked-by"] = norm_list(m["blocked-by"])
    return m


def r_fm_graph(text):
    e = Env.get()
    p = os.path.join(e.tmp, "graph", "tasks", "007-t.md")
    raw_write(p, text)
    try:
        fm, _ = e.graph.read_frontmatter(p)
        m = {k: fm.get(k) for k in FM_KEYS}
        m["blocked-by"] = tuple(e.graph.parse_list(fm.get("blocked-by"))) if fm.get("blocked-by") is not None else None
    except Exception as ex:   # GraphError: loud
        if type(ex).__name__ == "GraphError":
            return REFUSED
        raise
    return m


def r_fm_queue_states(text):
    """reef-queue's own frontmatter copy (task_states): what `status`/`ready` derive a row's state from."""
    e = Env.get()
    d = e.fresh("states")
    raw_write(os.path.join(d, "tasks", "007-t.md"), text)
    st = e.queue.task_states(d, {}, worktrees=False)
    return {"feature": next(iter(st)) if len(st) == 1 else None, "status": (st[next(iter(st))][0] if len(st) == 1 else None)}


def project_fs(m):
    return {"feature": m["feature"], "status": m["status"] or "pending"} if isinstance(m, dict) else m


# --- hand-back

def r_handback(text):
    e = Env.get()
    p = os.path.join(e.tmp, "handback.md")
    raw_write(p, text)
    rc = subprocess.run([sys.executable, CLAIMS, "check", "--handback", p, "--repo", e.tmp], capture_output=True, text=True, timeout=30).returncode
    return "OK" if rc == 0 else REFUSED


# --- journal

def r_journal(text):
    e = Env.get()
    d = e.fresh("journal")
    write(d, ".reef/config.json", "{}")
    write(d, "reef/features/share-page/SPEC.md", "# Share page\n\nRow: 12\n")
    raw_write(os.path.join(d, "reef/features/share-page/tasks/done/007-share-page.md"), text)
    rc, _ = quiet(e.queue.cmd_journal, d, "share-page")
    if rc:
        return REFUSED
    jp = os.path.join(d, "docs", "journal.md")
    body = RC.read(jp) if os.path.isfile(jp) else ""
    return tuple(l for l in body.splitlines() if l.strip() and l != "# Journal")


# --- queue

def r_queue(text):
    """`reef-queue.py check` failing is the loud refusal; else what status/ready read: the current batch and every row."""
    e = Env.get()
    d = e.fresh("queue")
    write(d, ".reef/config.json", "{}")
    raw_write(os.path.join(d, "docs", "queue.md"), text)
    rc, _ = quiet(e.queue.cmd_check, d)
    if rc:
        return REFUSED
    try:
        _, qtext, rows, _, _ = e.queue.load(d)
    except SystemExit:
        return REFUSED
    return (e.queue.current_batch(qtext), tuple((r["Id"], tuple(r["_depends"]), r["Batch"]) for r in rows))


# --- contracts

def r_night_rows(text):
    e = Env.get()
    d = e.fresh("night")
    raw_write(os.path.join(d, ".reef", "night", "contract.md"), text)
    return tuple(e.run.night_rows(d)) or REFUSED


def r_day_kinds(text):
    e = Env.get()
    d = e.fresh("day")
    raw_write(os.path.join(d, "reef", "proxy.md"), text)
    return tuple(e.run.day_kinds(d)) or REFUSED


# --- SPEC Row

def r_spec_row(text):
    return RC.spec_row(text) or REFUSED


def r_spec_queue(text):
    """reef-queue's own `Row:` reader (task_states / check): the row a done task of the folder counts for; check failing refuses."""
    e = Env.get()
    d = e.fresh("specq")
    write(d, ".reef/config.json", "{}")
    raw_write(os.path.join(d, "reef/features/share-page/SPEC.md"), text)
    write(d, "reef/features/share-page/tasks/done/007-share-page.md", "---\nid: 7\nfeature: share-page\nstatus: done\n---\n# 7\n")
    write(d, "docs/queue.md", "Current batch: 2\n\n| Id | Item | Depends | Batch |\n|---|---|---|---|\n| 3 | a | | 1 |\n| 12 | share page | | 2 |\n| 14 | b | | 2 |\n")
    rc, _ = quiet(e.queue.cmd_check, d)
    if rc:
        return REFUSED
    st = e.queue.task_states(d, {}, worktrees=False)
    keys = [k for k, v in st.items() if v == ["done"]]
    return keys[0] if len(keys) == 1 else REFUSED


# ================================================================== the suite

RNG = random.Random(SEED)
SEC_SAMPLES = security_samples("{HEAD12}")

KINDS = {
    # kind: (samples, sample meanings, ops, mutants, readers {name: (fn, project)})
    "verifier": (VERIFIER, VERIFIER_MEANING, report_ops(other_verdict), 50,
                 {"report_verdict": r_report_verdict, "claims_verdict": r_claims_verdict}),
    "acceptance": (ACCEPT, ACCEPT_MEANING, report_ops(other_green) + head_ops() + blocker_ops(), 60,
                   {"report_binding": r_acceptance_binding}),
    "security": (SEC_SAMPLES, SECURITY_MEANING, report_ops(other_verdict) + run_ops() + blocker_ops(), 60,
                 {"record_security": r_security_record}),
    "hunter": (HUNTER, HUNTER_MEANING, report_ops(other_verdict) + blocker_ops(), 55,
               {"adversarial_plan": r_hunter_record}),
    "frontmatter": ({"done": TASK, "pending": TASK_PENDING}, {"done": fm_meaning(TASK), "pending": fm_meaning(TASK_PENDING)}, fm_ops(), 60,
                    {"task_frontmatter": r_fm_common, "graph_read_frontmatter": r_fm_graph, "queue_task_states": r_fm_queue_states}),
    "handback": (HANDBACK, HANDBACK_MEANING, handback_ops(), 30, {"claims_handback": r_handback}),
    "journal": ({"block": JTASK}, {"block": JOURNAL_MEANING}, journal_ops(), 30, {"queue_journal": r_journal}),
    "queue": ({"queue": QUEUE}, {"queue": queue_meaning_of(QUEUE)}, queue_ops(), 45, {"queue_status": r_queue}),
    "night": ({"night": NIGHT}, {"night": NIGHT_MEANING}, contract_ops("Rows"), 35, {"night_rows": r_night_rows}),
    "proxy": ({"proxy": PROXY}, {"proxy": PROXY_MEANING}, contract_ops("Decides"), 35, {"day_kinds": r_day_kinds}),
    "spec": ({"spec": SPEC}, {"spec": "12"}, spec_ops(), 35, {"spec_row": r_spec_row, "queue_row_reader": r_spec_queue}),
}

PROJECT = {"queue_task_states": project_fs}

MUTANTS = {k: build(k, v[0], v[2], v[3], RNG) for k, v in KINDS.items()}


def reading(kind, reader, text):
    e = Env.get()
    key = (kind, reader, text)
    if key not in e.cache:
        e.cache[key] = KINDS[kind][4][reader](text)
    return e.cache[key]


def show(text):
    return repr(text if len(text) < 260 else text[:120] + " … " + text[-120:])


class Samples(unittest.TestCase):
    """Every reader reads every valid sample as the sample states — else the fuzz below means nothing (a test bug, not a finding)."""

    def test_every_reader_reads_every_sample_as_stated(self):
        for kind, (samples, meanings, _, _, readers) in KINDS.items():
            for reader in readers:
                proj = PROJECT.get(reader, lambda m: m)
                for name, text in samples.items():
                    with self.subTest(kind=kind, reader=reader, sample=name):
                        self.assertEqual(reading(kind, reader, text), proj(meanings[name]))


class Fuzz(unittest.TestCase):
    """One test per reader and mutation class (generated below)."""


def make_test(kind, reader, cls):
    def test(self):
        samples, meanings, _, _, _ = KINDS[kind]
        proj = PROJECT.get(reader, lambda m: m)
        bad = []
        for name, c, mutant, exp in MUTANTS[kind]:
            if c != cls:
                continue
            got = reading(kind, reader, mutant)
            orig = proj(meanings[name])
            want = (exp[0], proj(exp[1])) if isinstance(exp, tuple) else exp
            if violates(got, orig, want):
                bad.append(f"  sample {name!r}: expected {('the original ' + repr(orig) + ' or a refusal') if want == SAME else ('a refusal' if want == REFUSE else repr(want[1]) + ' or a refusal')}"
                           f"; read {got!r}\n    mutant: {show(mutant)}")
        self.assertFalse(bad, f"{kind} · {reader} · {cls}: {len(bad)} mutant(s) read a different meaning, silently:\n" + "\n".join(bad[:3]))
    return test


# (kind, reader, class) judged INVALID in docs/review/stress-2026-11-03-hard.md: the class cannot reach the reader. Skipped, never deleted from the op
# tables: every mutant comes from ONE shared random.Random(SEED), so deleting an op would shift every later kind's mutants.
OUT_OF_CONTRACT = {
    ("frontmatter", "task_frontmatter", "value_case"),
    ("frontmatter", "task_frontmatter", "key_case"),
    ("frontmatter", "task_frontmatter", "key_lookalike"),
    ("frontmatter", "task_frontmatter", "empty_value"),
    ("frontmatter", "graph_read_frontmatter", "value_case"),
    ("frontmatter", "graph_read_frontmatter", "key_case"),
    ("frontmatter", "graph_read_frontmatter", "key_lookalike"),
    ("frontmatter", "graph_read_frontmatter", "empty_value"),
    ("frontmatter", "queue_task_states", "value_case"),
    ("frontmatter", "queue_task_states", "key_case"),
    ("frontmatter", "queue_task_states", "key_lookalike"),
    ("frontmatter", "queue_task_states", "empty_value"),
    ("frontmatter", "queue_task_states", "bom"),
    ("frontmatter", "queue_task_states", "truncated"),
    ("hunter", "adversarial_plan", "blocker_lookalike"),
    ("security", "record_security", "blocker_lookalike"),
    ("journal", "queue_journal", "marker_case"),
    ("journal", "queue_journal", "marker_spacing"),
    ("journal", "queue_journal", "trailing_spaces"),
    ("journal", "queue_journal", "block_duplicate_same"),
    ("journal", "queue_journal", "truncated"),
}

# test name -> open cluster id in docs/review/stress-2026-11-03-hard.md. Each is wrapped in unittest.expectedFailure; a fix PR removes its
# entries, and an entry its fix closed goes red as an unexpected success. `grep -n "open: " tests/stress_fuzz.py` lists them.
OPEN = {
    "test_verifier__report_verdict__verdict_fenced_after": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_verifier__report_verdict__verdict_key_case": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_verifier__report_verdict__verdict_markdown": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_verifier__report_verdict__verdict_value_quoted": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_verifier__report_verdict__verdict_empty_value": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_verifier__report_verdict__verdict_key_lookalike": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_verifier__report_verdict__verdict_value_lookalike": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_verifier__claims_verdict__verdict_fenced_after": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_verifier__claims_verdict__verdict_key_case": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_verifier__claims_verdict__verdict_markdown": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_verifier__claims_verdict__verdict_value_quoted": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_verifier__claims_verdict__verdict_empty_value": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_verifier__claims_verdict__verdict_key_lookalike": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_verifier__claims_verdict__verdict_value_lookalike": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_acceptance__report_binding__verdict_fenced_after": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_acceptance__report_binding__verdict_key_case": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_acceptance__report_binding__verdict_markdown": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_acceptance__report_binding__verdict_value_quoted": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_acceptance__report_binding__verdict_empty_value": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_acceptance__report_binding__verdict_key_lookalike": "H1 (docs/review/stress-2026-11-03-hard.md)",   # open: H1
    "test_security__record_security__blocker_key_case": "M1 (docs/review/stress-2026-11-03-hard.md)",   # open: M1
    "test_hunter__adversarial_plan__blocker_key_case": "M1 (docs/review/stress-2026-11-03-hard.md)",   # open: M1
    "test_spec__spec_row__empty_value_numbered_next": "M5 (docs/review/stress-2026-11-03-hard.md)",   # open: M5
    "test_spec__spec_row__row_in_fence_before": "M5 (docs/review/stress-2026-11-03-hard.md)",   # open: M5
    "test_spec__spec_row__row_duplicate_conflicting": "M5 (docs/review/stress-2026-11-03-hard.md)",   # open: M5
    "test_spec__queue_row_reader__row_in_fence_before": "M5 (docs/review/stress-2026-11-03-hard.md)",   # open: M5
    "test_spec__queue_row_reader__row_duplicate_conflicting": "M5 (docs/review/stress-2026-11-03-hard.md)",   # open: M5
    "test_queue__queue_status__current_batch_key_case": "M6 (docs/review/stress-2026-11-03-hard.md)",   # open: M6
    "test_queue__queue_status__current_batch_quoted": "M6 (docs/review/stress-2026-11-03-hard.md)",   # open: M6
    "test_queue__queue_status__current_batch_duplicate": "M6 (docs/review/stress-2026-11-03-hard.md)",   # open: M6
    "test_queue__queue_status__header_case": "M6 (docs/review/stress-2026-11-03-hard.md)",   # open: M6
    "test_queue__queue_status__table_in_fence": "M6 (docs/review/stress-2026-11-03-hard.md)",   # open: M6
    "test_queue__queue_status__row_id_empty": "M6 (docs/review/stress-2026-11-03-hard.md)",   # open: M6
    "test_queue__queue_status__batch_cell_quoted": "M6 (docs/review/stress-2026-11-03-hard.md)",   # open: M6
    "test_handback__claims_handback__claim_in_fence": "L1 (docs/review/stress-2026-11-03-hard.md)",   # open: L1
    "test_handback__claims_handback__claim_in_quote": "L1 (docs/review/stress-2026-11-03-hard.md)",   # open: L1
    "test_journal__queue_journal__example_in_fence": "L2 (docs/review/stress-2026-11-03-hard.md)",   # open: L2
    "test_journal__queue_journal__example_in_quote": "L2 (docs/review/stress-2026-11-03-hard.md)",   # open: L2
    "test_night__night_rows__row_footnote_mark": "L3 (docs/review/stress-2026-11-03-hard.md)",   # open: L3
    "test_proxy__day_kinds__value_quoted": "L3 (docs/review/stress-2026-11-03-hard.md)",   # open: L3
    "test_frontmatter__graph_read_frontmatter__value_quoted_single": "L4 (docs/review/stress-2026-11-03-hard.md)",   # open: L4
    "test_frontmatter__queue_task_states__value_quoted_single": "L4 (docs/review/stress-2026-11-03-hard.md)",   # open: L4
    "test_frontmatter__task_frontmatter__unicode_digit_id": "L5 (docs/review/stress-2026-11-03-hard.md)",   # open: L5
    "test_frontmatter__task_frontmatter__unicode_digit_feature": "L5 (docs/review/stress-2026-11-03-hard.md)",   # open: L5
    "test_frontmatter__graph_read_frontmatter__unicode_digit_id": "L5 (docs/review/stress-2026-11-03-hard.md)",   # open: L5
    "test_frontmatter__graph_read_frontmatter__unicode_digit_feature": "L5 (docs/review/stress-2026-11-03-hard.md)",   # open: L5
    "test_frontmatter__queue_task_states__unicode_digit_feature": "L5 (docs/review/stress-2026-11-03-hard.md)",   # open: L5
    "test_queue__queue_status__current_batch_unicode_digit": "L5 (docs/review/stress-2026-11-03-hard.md)",   # open: L5
    "test_queue__queue_status__row_id_unicode_digit": "L5 (docs/review/stress-2026-11-03-hard.md)",   # open: L5
    "test_night__night_rows__row_unicode_digit": "L5 (docs/review/stress-2026-11-03-hard.md)",   # open: L5
    "test_spec__spec_row__row_unicode_digit": "L5 (docs/review/stress-2026-11-03-hard.md)",   # open: L5
}

for _kind, (_s, _m, _ops, _n, _readers) in KINDS.items():
    _classes = sorted({c for _, c, _, _ in MUTANTS[_kind]})
    for _reader in _readers:
        for _cls in _classes:
            _name = f"test_{_kind}__{_reader}__{_cls}"
            _t = make_test(_kind, _reader, _cls)
            if (_kind, _reader, _cls) in OUT_OF_CONTRACT:
                _t = unittest.skip(f"out of contract: INVALID in docs/review/stress-2026-11-03-hard.md")(_t)
            elif _name in OPEN:
                _t = unittest.expectedFailure(_t)
            setattr(Fuzz, _name, _t)
_names = {n for n in dir(Fuzz) if n.startswith("test_")}
assert set(OPEN) <= _names, sorted(set(OPEN) - _names)
assert {f"test_{k}__{r}__{c}" for k, r, c in OUT_OF_CONTRACT} <= _names, "an OUT_OF_CONTRACT class names no test"


def tearDownModule():
    if Env._made is not None:
        shutil.rmtree(Env._made.tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
