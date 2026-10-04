#!/usr/bin/env python3
"""Reef init — the full project setup, generated from templates, idempotent.

Usage:
  reef-init.py [--root DIR] [--plugin DIR] [--name NAME] [--base BRANCH] [--release BRANCH] [--dry-run]
  reef-init.py [--root DIR] --accept <path> [<path> ...]     apply a proposed rendering (after the human said so)

What it writes (from <plugin>/templates/project and <plugin>/scripts), adapted to the detected stack:
  .reef/config.json (merged: missing keys added, nothing existing changed), AGENTS.md, CLAUDE.md
  (pointer, only when absent), .specify/constitution.md, docs/queue.md, docs/adr/README.md,
  docs/journal.md, HANDOFF.md, docs/day-zero.md, docs/glossary.md, .github/workflows/ci.yml,
  .github/dependabot.yml, scripts/reef-*.{py,sh} + reef-attempt + reef-adversarial,
  .githooks/pre-commit + pre-merge-commit, tasks/ + tasks/done/, .gitignore lines, a Makefile
  `setup:` target (appended, never rewritten).

The rule, for every file: ABSENT -> written. IDENTICAL -> skipped. DIFFERENT -> never overwritten:
the rendering goes to .reef/proposed/<path>, a unified diff is printed, and `--accept <path>`
applies it once the human has read the diff. A second run with nothing changed writes nothing.
Hooks install (`git config core.hooksPath`), the first commit and the CI offer stay with the
reef-init skill: they are decisions, not renderings.

Exit 0 = done (the summary says what was written / skipped / proposed). 1 = refused.
"""
import datetime
import difflib
import filecmp
import json
import os
import shutil
import stat
import sys

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = ["reef-gate.sh", "reef-attempt", "reef-snapshot.sh", "reef-plan-check.py", "reef-graph.py",
           "reef-adversarial", "reef-claims.py", "reef-ci-local.sh", "reef-tier.py", "reef-queue.py"]
TEMPLATES = {          # published path -> template under templates/project (or templates/)
    "AGENTS.md": "project/AGENTS.md",
    ".specify/constitution.md": "project/constitution.md",
    "docs/queue.md": "project/queue.md",
    "docs/adr/README.md": "project/adr-README.md",
    "docs/journal.md": "project/journal.md",
    "HANDOFF.md": "project/HANDOFF.md",
    "docs/day-zero.md": "project/day-zero.md",
    ".github/workflows/ci.yml": "project/ci.yml",
    ".github/dependabot.yml": "project/dependabot.yml",
    "docs/glossary.md": "glossary.md",
    ".githooks/pre-commit": "pre-commit",
    ".githooks/pre-merge-commit": "pre-commit",
}
GITIGNORE_LINES = [".reef/worktrees/", ".reef/proposed/", ".reef/ci-local/", "tasks/.plan-review.json", ".env"]
MAKEFILE_TARGET = "\nsetup: ## git hooks (once per clone) — reef\n\tgit config core.hooksPath .githooks\n\tchmod +x .githooks/*\n"


def die(msg):
    print(f"reef-init: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- stack

def detect(root):
    """Stack facts the templates need. Only what the files say; nothing guessed is a gate."""
    has = lambda *p: os.path.isfile(os.path.join(root, *p))
    facts = {"name": os.path.basename(os.path.abspath(root)), "stack": "unknown", "test": "", "fast": "",
             "build": "", "install": "", "ecosystem": "github-actions", "setup_steps": ""}
    if has("package.json"):
        try:
            with open(os.path.join(root, "package.json"), encoding="utf-8") as f:
                pkg = json.load(f)
        except Exception:
            pkg = {}
        scripts = pkg.get("scripts", {}) if isinstance(pkg, dict) else {}
        facts.update(stack="node", ecosystem="npm", install="npm ci",
                     test="npm test" if "test" in scripts else "",
                     build="npm run build" if "build" in scripts else "",
                     name=str(pkg.get("name") or facts["name"]),
                     setup_steps="      - uses: actions/setup-node@v4\n        with:\n          node-version: 22\n          cache: npm\n      - run: npm ci --no-audit --no-fund\n")
    elif has("pyproject.toml") or has("uv.lock"):
        uv = has("uv.lock")
        facts.update(stack="python", ecosystem="pip", install="uv sync" if uv else "pip install -e .",
                     test="uv run pytest -q" if uv else "pytest -q",
                     setup_steps="      - uses: actions/setup-python@v5\n        with:\n          python-version: '3.12'\n      - run: " + ("pip install uv && uv sync" if uv else "pip install -e .") + "\n")
    elif has("Cargo.toml"):
        facts.update(stack="rust", ecosystem="cargo", install="cargo fetch", test="cargo test -q", build="cargo build",
                     setup_steps="      - uses: dtolnay/rust-toolchain@stable\n")
    elif has("go.mod"):
        facts.update(stack="go", ecosystem="gomod", install="go mod download", test="go test ./...", build="go build ./...",
                     setup_steps="      - uses: actions/setup-go@v5\n        with:\n          go-version: stable\n")
    facts["date"] = datetime.date.today().isoformat()
    return facts


def render(template_text, facts):
    out = template_text
    for k, v in facts.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out


def project_config(existing, facts):
    """The plugin's config template + the generated project's keys, MERGED under the existing
    config: a key the project already has is never changed (the human may have tuned it)."""
    with open(os.path.join(PLUGIN, "templates", "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["gates"]["full"] = facts["test"]
    cfg["gates"]["extra"] = {"build": facts["build"]} if facts["build"] else {}
    cfg["branches"] = {"base": facts["base"], "release": facts["release"]}
    cfg["merge"] = {"by": "loop" if facts["base"] != facts["release"] else "human"}
    cfg["ci"] = {"feature_gate": "local" if facts["base"] != facts["release"] else "ci"}
    cfg["paths"]["runlog"] = "docs/journal.md"
    cfg["paths"]["queue"] = "docs/queue.md"
    cfg["worktree"]["setup"] = facts["install"]
    cfg["tiers"] = {"light": {"allow": ["docs/**", "README.md"], "max_lines": 80,
                              "migrations": ["migrations/**", "prisma/migrations/**", "alembic/**"]}}
    cfg["writing"] = {"task_words": {"light": 600, "full": 2500, "design": 2500}, "handback_words": 150,
                      "prompt_words": 120, "journal_words": 40000, "queue_words": 35000}

    def merge(base, over):
        for k, v in over.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                merge(base[k], v)
            elif k not in base:
                base[k] = v
        return base
    return merge(existing, cfg) if existing is not None else cfg


# ---------------------------------------------------------------- the one rule

class Writer:
    def __init__(self, root, dry):
        self.root, self.dry = root, dry
        self.written, self.skipped, self.proposed = [], [], []

    def place(self, rel, content, executable=False):
        target = os.path.join(self.root, rel)
        if os.path.exists(target):
            with open(target, "rb") as f:
                current = f.read()
            if current == content.encode("utf-8"):
                self.skipped.append(rel)
                return
            prop = os.path.join(self.root, ".reef", "proposed", rel)
            if not self.dry:
                os.makedirs(os.path.dirname(prop), exist_ok=True)
                with open(prop, "w", encoding="utf-8", newline="") as f:
                    f.write(content)
            diff = difflib.unified_diff(current.decode("utf-8", "replace").splitlines(True),
                                        content.splitlines(True), fromfile=rel, tofile=f".reef/proposed/{rel}")
            self.proposed.append((rel, "".join(diff)))
            return
        if not self.dry:
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="") as f:
                f.write(content)
            if executable:
                os.chmod(target, os.stat(target).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.written.append(rel)

    def append_lines(self, rel, lines):
        """Lines added to a file the human owns (.gitignore, Makefile): never rewritten."""
        target = os.path.join(self.root, rel)
        existing = ""
        if os.path.exists(target):
            with open(target, encoding="utf-8") as f:
                existing = f.read()
        missing = [l for l in lines if l not in existing.splitlines()]
        if not missing:
            self.skipped.append(rel)
            return
        if not self.dry:
            with open(target, "a", encoding="utf-8") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write("\n".join(missing) + "\n")
        self.written.append(f"{rel} (+{len(missing)} line(s))")


def run(root, facts, dry):
    w = Writer(root, dry)
    # config: merged, never a value changed
    cfg_path = os.path.join(root, ".reef", "config.json")
    existing = None
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception as e:
            die(f".reef/config.json is unparseable ({e}) — fix it before init can merge into it")
    merged = project_config(json.loads(json.dumps(existing)) if existing is not None else None, facts)
    if existing is not None and merged == existing:
        w.skipped.append(".reef/config.json")
    else:
        if not dry:
            os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2)
                f.write("\n")
        w.written.append(".reef/config.json" + (" (keys added)" if existing is not None else ""))
    # templates
    for rel, tpl in TEMPLATES.items():
        with open(os.path.join(PLUGIN, "templates", tpl), encoding="utf-8") as f:
            w.place(rel, render(f.read(), facts), executable=rel.startswith(".githooks/"))
    if not os.path.exists(os.path.join(root, "CLAUDE.md")):
        with open(os.path.join(PLUGIN, "templates", "project/CLAUDE.md"), encoding="utf-8") as f:
            w.place("CLAUDE.md", f.read())
    for name in SCRIPTS:
        with open(os.path.join(PLUGIN, "scripts", name), encoding="utf-8") as f:
            w.place(f"scripts/{name}", f.read(), executable=True)
    for d in ("tasks", "tasks/done", "docs/adr"):
        if not dry:
            os.makedirs(os.path.join(root, d), exist_ok=True)
    w.append_lines(".gitignore", GITIGNORE_LINES)
    mk = os.path.join(root, "Makefile")
    if os.path.isfile(mk):
        with open(mk, encoding="utf-8") as f:
            has_setup = any(l.startswith("setup:") for l in f)
        if has_setup:
            w.skipped.append("Makefile (setup: present)")
        else:
            if not dry:
                with open(mk, "a", encoding="utf-8") as f:
                    f.write(MAKEFILE_TARGET)
            w.written.append("Makefile (+setup:)")
    else:
        w.place("Makefile", MAKEFILE_TARGET.lstrip("\n"))
    return w


def accept(root, paths):
    for rel in paths:
        prop = os.path.join(root, ".reef", "proposed", rel)
        if not os.path.isfile(prop):
            die(f"nothing proposed for {rel} (run reef-init first; the diff is printed then)")
        target = os.path.join(root, rel)
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        mode = os.stat(target).st_mode if os.path.exists(target) else None
        shutil.copyfile(prop, target)
        if mode is not None:
            os.chmod(target, mode)
        os.unlink(prop)
        print(f"accepted: {rel}")


def main(argv):
    root, name, base, release, dry, to_accept = ".", None, "develop", "main", False, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--root":
            root = argv[i + 1]; i += 2
        elif a == "--plugin":
            global PLUGIN
            PLUGIN = argv[i + 1]; i += 2
        elif a == "--name":
            name = argv[i + 1]; i += 2
        elif a == "--base":
            base = argv[i + 1]; i += 2
        elif a == "--release":
            release = argv[i + 1]; i += 2
        elif a == "--dry-run":
            dry = True; i += 1
        elif a == "--accept":
            to_accept = argv[i + 1:]; break
        else:
            die(f"unknown argument {a!r}")
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        die(f"not a directory: {root}")
    if to_accept:
        accept(root, to_accept)
        return 0
    facts = detect(root)
    if name:
        facts["name"] = name
    facts["base"], facts["release"] = base, release
    w = run(root, facts, dry)
    print(f"reef-init ({'dry run, ' if dry else ''}stack: {facts['stack']}, base: {base}, release: {release})")
    for r in w.written:
        print(f"  written  {r}")
    for r in w.skipped:
        print(f"  skipped  {r}" + ("" if "(" in r else " (identical)"))
    for rel, diff in w.proposed:
        print(f"  PROPOSED {rel} differs from the rendering — NOT overwritten; see .reef/proposed/{rel}")
        print("".join("    " + l for l in diff.splitlines(True)), end="")
    if w.proposed:
        print("  to apply one after reading its diff: python3 scripts/reef-init.py --accept <path>")
    if not facts["test"]:
        print("  NOTE: no test command detected — gates.full is empty and the gate FAILS LOUDLY until you set it")
    print(f"  {len(w.written)} written, {len(w.skipped)} skipped, {len(w.proposed)} proposed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
