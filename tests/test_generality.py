"""Reef works on any project and any stack (the owner's rule, 2026-10-25). Two guards:

1. The generality ratchet: names of one adopted project or one stack's tools in Reef's CODE and agent-facing PROSE (comments
   and docstrings are history and do not count) are listed in tests/generality-baseline.json, and the list only shrinks — a
   new hit is red, a removed one is red until the baseline is lowered with it. Stack knowledge belongs in data
   (templates/stacks/), never in a code path.
2. The whole adoption on four stacks: a node + Next.js + Prisma project, a python + FastAPI + SQLAlchemy project, a go
   project and a ruby project (no stack profile at all) each run reef-init → measure → plan → apply → structure → doctor; every
   step finishes, and the project's own check, which reads its ADR folder by directory, still passes afterwards."""
import ast
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import tokenize
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(ROOT, "tests", "generality-baseline.json")
SCRIPTS = os.path.join(ROOT, "scripts")
TOKENS = ("ai-coach", "ci:local", "loop:close", "loop-start", "loop:start", "loop:adr", "docs/loop", "HANDOFF-FRESH",
          "design_handoff", "check:docs", "NextAuth", "getServerSession", "PrismaClient", "@prisma/client", "queryRawUnsafe",
          "dependency-cruiser", "depcruise", "app/api/", "RawUnsafe")


def code_text(path):
    """The text that runs or that an agent reads: a Python file without its comments and docstrings, a shell file without
    its comments, Markdown whole."""
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    if path.endswith(".md"):
        return text
    if path.endswith(".py") or text.startswith("#!/usr/bin/env python"):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return text
        doc_lines = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                    doc_lines.update(range(first.lineno, first.end_lineno + 1))
        comments = {}
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                comments[tok.start[0]] = tok.start[1]
        out = []
        for n, line in enumerate(text.splitlines(), 1):
            if n in doc_lines:
                continue
            out.append(line[:comments[n]] if n in comments else line)
        return "\n".join(out)
    return "\n".join(re.sub(r"(^|\s)#.*$", "", line) for line in text.splitlines())   # shell


def scanned_files():
    files = []
    for top in ("scripts", "hooks", "skills", "agents", "commands", "templates"):
        for dp, dn, fn in os.walk(os.path.join(ROOT, top)):
            dn[:] = [d for d in dn if d not in ("__pycache__", "stacks")]   # templates/stacks/: stack knowledge as data
            for f in fn:
                if not f.endswith((".pyc", ".json", ".png", ".svg")):
                    files.append(os.path.relpath(os.path.join(dp, f), ROOT))
    return sorted(files)


def hits():
    out = {}
    for rel in scanned_files():
        text = code_text(os.path.join(ROOT, rel))
        found = {t: text.count(t) for t in TOKENS if t in text}
        if found:
            out[rel] = found
    return out


class GeneralityRatchet(unittest.TestCase):
    def test_project_and_stack_names_in_reefs_code_only_shrink(self):
        with open(BASELINE, encoding="utf-8") as f:
            base = json.load(f)
        now = hits()
        grew = [f"{rel}: {t} {n} (baseline {base.get(rel, {}).get(t, 0)})" for rel, ts in now.items() for t, n in ts.items()
                if n > base.get(rel, {}).get(t, 0)]
        shrank = [f"{rel}: {t} {now.get(rel, {}).get(t, 0)} (baseline {n})" for rel, ts in base.items() for t, n in ts.items()
                  if now.get(rel, {}).get(t, 0) < n]
        self.assertEqual(grew, [], "a project's or a stack's name entered Reef's code: put stack knowledge in templates/stacks/")
        self.assertEqual(shrank, [], "removed, good: lower tests/generality-baseline.json in the same commit")


def git(d, *a):
    return subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True, capture_output=True, text=True).stdout


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


ADR = "# 1. Use a relational store\n\n## Status\nAccepted\n\n## Context\nWe need a store.\n\n## Decision\nPostgres.\n\n## Consequences\nOperate it.\n"
STACKS = {
    "node": {"package.json": json.dumps({"name": "shop", "scripts": {"test": "node -e 0", "check:docs": "node scripts/check-docs.js"},
                                         "dependencies": {"next": "16.0.0", "@prisma/client": "6.0.0"}}),
             "scripts/check-docs.js": 'const { readdirSync } = require("fs");\nif (!readdirSync("docs/adr").length) process.exit(1);\n',
             "src/app/api/orders/route.ts": "import { prisma } from '@/lib/db';\nexport const GET = () => prisma.order.findMany();\n",
             "src/lib/db.ts": "import { PrismaClient } from '@prisma/client';\nexport const prisma = new PrismaClient();\n"},
    "python": {"pyproject.toml": '[project]\nname = "shop"\nversion = "0.1.0"\ndependencies = ["fastapi", "sqlalchemy"]\n',
               "Makefile": "check-docs:\n\tpython3 tools/check_docs.py\n",
               "tools/check_docs.py": 'import os, sys\nsys.exit(0 if os.listdir("docs/adr") else 1)\n',
               "shop/db.py": "from sqlalchemy import create_engine, text\nengine = create_engine('sqlite://')\n",
               "shop/orders.py": "from .db import engine, text\ndef orders(uid):\n    return engine.execute(text(f'select * from orders where uid={uid}'))\n"},
    "go": {"go.mod": "module example.com/shop\n\ngo 1.22\n",
           "cmd/checkdocs/main.go": 'package main\n\nimport "os"\n\nfunc main() {\n\tif e, _ := os.ReadDir("docs/adr"); len(e) == 0 {\n\t\tos.Exit(1)\n\t}\n}\n',
           "internal/orders/orders.go": "package orders\n\nimport \"database/sql\"\n\nfunc All(db *sql.DB) (*sql.Rows, error) { return db.Query(\"select 1\") }\n"},
    "ruby": {"Gemfile": "source 'https://rubygems.org'\ngem 'sinatra'\n",
             "lib/check_docs.rb": 'exit(Dir.children("docs/adr").empty? ? 1 : 0)\n',
             "app/orders.rb": "class Orders\n  def all = DB.fetch('select 1').all\nend\n"},
}
# the project's own check, the same on every stack: the ADR folder its code reads by directory is still there and full
PROJECT_CHECK = "test -d docs/adr && test -n \"$(ls docs/adr)\""


def stack_project(stack):
    d = tempfile.mkdtemp(prefix=f"reef-gen-{stack}.")
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    write(d, "README.md", "# shop\n")
    write(d, "docs/adr/0001-use-a-relational-store.md", ADR)
    write(d, "notes/ideas.md", "# Ideas\nTODO maybe later.\n")
    write(d, "decisions/cache.md", "# Cache\n\n## Status\nAccepted\n\n## Context\nslow pages\n\n## Decision\nan HTTP cache\n\n## Consequences\nstale reads\n")
    for rel, text in STACKS[stack].items():
        write(d, rel, text)
    git(d, "add", "-A"); git(d, "commit", "-qm", "the project before Reef")
    return d


class AnyStack(unittest.TestCase):
    """The adoption path finishes on every stack and leaves the project's own check green."""

    def adopt(self, stack):
        d = stack_project(stack)
        run = lambda *a: subprocess.run([sys.executable, *a], capture_output=True, text=True, cwd=d)
        steps = {}
        r = run(os.path.join(SCRIPTS, "reef-init.py"), "--root", d)
        steps["init"] = r
        self.assertEqual(r.returncode, 0, f"{stack} init: {r.stdout[-800:]}{r.stderr[-800:]}")
        git(d, "add", "-A"); git(d, "commit", "-qm", "reef init")
        recal = os.path.join(d, "scripts", "reef-recalibrate")
        r = run(recal, "measure", "--json", "--repo", d)
        self.assertEqual(r.returncode, 0, f"{stack} measure: {r.stderr[-800:]}")
        steps["measure"] = json.loads(r.stdout)
        git(d, "add", "-A"); git(d, "commit", "-qm", "measure")
        r = run(recal, "plan", "--repo", d)
        self.assertEqual(r.returncode, 0, f"{stack} plan: {r.stdout[-800:]}{r.stderr[-800:]}")
        steps["plan"] = r
        git(d, "add", "-A"); git(d, "commit", "-qm", "plan")
        r = run(recal, "--apply", "--repo", d)
        self.assertIn(r.returncode, (0, 1), f"{stack} apply: {r.stdout[-800:]}{r.stderr[-800:]}")
        self.assertNotIn("Traceback", r.stdout + r.stderr, f"{stack} apply")
        steps["apply"] = r
        self.assertEqual(subprocess.run(["sh", "-c", PROJECT_CHECK], cwd=d).returncode, 0, f"{stack}: the project's own check broke")
        r = run(os.path.join(d, "scripts", "reef-structure"), "--check", "--repo", d)
        self.assertNotIn("Traceback", r.stdout + r.stderr, f"{stack} structure")
        r = run(os.path.join(d, "scripts", "reef-doctor.py") if os.path.isfile(os.path.join(d, "scripts", "reef-doctor.py"))
                else os.path.join(SCRIPTS, "reef-doctor.py"))
        self.assertNotIn("Traceback", r.stdout + r.stderr, f"{stack} doctor")
        return d, steps

    def test_node(self):
        self.adopt("node")

    def test_python(self):
        self.adopt("python")

    def test_go(self):
        self.adopt("go")

    def test_ruby_with_no_stack_profile(self):
        self.adopt("ruby")


if __name__ == "__main__":
    unittest.main()
