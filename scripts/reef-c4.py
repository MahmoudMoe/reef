#!/usr/bin/env python3
# CLASS: code
"""Reef C4 — one architecture model per project, generated from code with a proving path per element.
  reef-c4.py generate [--repo DIR] [--write]    detection → reef/architecture/workspace.dsl (Structurizr, L1/L2 views)
  reef-c4.py lint [--repo DIR] [<dsl>]          dependency-free structural lint
  reef-c4.py --diff [--repo DIR]                missing (in code, not in model) · contradicts (in model, not in code) · inferred
Cap 9 elements (the most similar pair collapsed and reported); Inferred tagged. Exit 0 · 1 drift/lint · 2 usage.
"""
import json
import os
import re
import subprocess
import sys

DSL = "reef/architecture/workspace.dsl"
CAP = 9
STORES = {"pg": "Postgres", "postgres": "Postgres", "psycopg": "Postgres", "asyncpg": "Postgres", "mysql": "MySQL", "mysql2": "MySQL",
          "sqlite3": "SQLite", "better-sqlite3": "SQLite", "aiosqlite": "SQLite", "prisma": "Database (Prisma)", "sqlalchemy": "Database (SQLAlchemy)",
          "mongoose": "MongoDB", "pymongo": "MongoDB", "redis": "Redis", "ioredis": "Redis", "diesel": "Database (Diesel)", "sqlx": "Database (sqlx)"}
QUEUES = {"amqplib": "RabbitMQ", "pika": "RabbitMQ", "kafkajs": "Kafka", "aiokafka": "Kafka", "bullmq": "Redis queue", "celery": "Celery broker", "nats": "NATS"}
EXTERNALS = {"stripe": "Stripe", "@sendgrid/mail": "SendGrid", "twilio": "Twilio", "@aws-sdk/client-s3": "S3", "boto3": "AWS", "openai": "OpenAI API",
             "anthropic": "Anthropic API", "@anthropic-ai/sdk": "Anthropic API", "@supabase/supabase-js": "Supabase", "firebase-admin": "Firebase"}
ROUTE_RE = re.compile(r"(app|router|api)\.(get|post|put|delete|patch)\(|@(app|router|bp)\.(get|post|put|delete|route)\(|r\.(GET|POST|PUT|DELETE)\(|Router::new\(\)|path\(['\"]", re.M)


def read(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def deps(root):
    """(name -> manifest path) over the stacks reef-init detects."""
    out = {}
    pkg = os.path.join(root, "package.json")
    if os.path.isfile(pkg):
        try:
            j = json.loads(read(pkg))
            for k in ("dependencies", "devDependencies"):
                for n in (j.get(k) or {}):
                    out[n] = "package.json"
        except ValueError:
            pass
    for name in ("pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod"):
        p = os.path.join(root, name)
        if os.path.isfile(p):
            # a dependency line: a name token, then a version operator (= ~ ^ [ < >) or, in go.mod, ` vN`
            for line in read(p).splitlines():
                m = re.match(r'\s*"?([A-Za-z0-9_.@/-]+)"?(\s*)(.*)$', line)
                if m and (m.group(3)[:1] in ("=", "~", "^", "[", "<", ">") or (m.group(2) and re.match(r"v\d", m.group(3)))):
                    out.setdefault(m.group(1).lower(), name)
    return out


def project_name(root):
    """The manifest's name (package.json, pyproject, Cargo.toml, go.mod), else the directory's."""
    pkg = os.path.join(root, "package.json")
    if os.path.isfile(pkg):
        try:
            n = json.loads(read(pkg)).get("name")
            if n:
                return str(n).split("/")[-1]
        except ValueError:
            pass
    for f, rx in (("pyproject.toml", r'^name\s*=\s*"([^"]+)"'), ("Cargo.toml", r'^name\s*=\s*"([^"]+)"'), ("go.mod", r"^module\s+(\S+)")):
        m = re.search(rx, read(os.path.join(root, f)), re.M)
        if m:
            return m.group(1).split("/")[-1]
    return os.path.basename(os.path.abspath(root))


def detect(root):
    """Elements: [{id, kind: person|container|store|external, name, desc, proof, inferred}]."""
    els = [{"id": "operator", "kind": "person", "name": "Operator", "desc": "uses the product", "proof": "README.md" if os.path.isfile(os.path.join(root, "README.md")) else "", "inferred": True}]
    d = deps(root)
    name = project_name(root)
    routes = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [x for x in dn if x not in (".git", "node_modules", ".venv", "venv", "dist", "build", "target", ".reef", "reef")]
        for f in fn:
            if f.endswith((".py", ".js", ".ts", ".mjs", ".go", ".rs")) and not f.endswith((".test.ts", ".test.js", "_test.go")):
                p = os.path.join(dp, f)
                if ROUTE_RE.search(read(p)[:200000]):
                    routes.append(os.path.relpath(p, root))
    if routes:
        els.append({"id": "api", "kind": "container", "name": f"{name} API", "desc": "HTTP routes", "proof": sorted(routes)[0], "inferred": False})
    front = [f for f in ("index.html", "src/App.tsx", "src/App.jsx", "src/main.tsx", "app/page.tsx", "pages/index.tsx", "templates/base.html", "templates/index.html") if os.path.isfile(os.path.join(root, f))]
    if front or any(k in d for k in ("react", "vue", "svelte", "next", "nuxt", "django", "flask", "jinja2")):
        els.append({"id": "web", "kind": "container", "name": f"{name} web", "desc": "the browser-facing surface", "proof": front[0] if front else next(("package.json" for k in ("react", "vue", "svelte", "next", "nuxt") if k in d), "pyproject.toml"), "inferred": not front})
    if not routes and not front:
        entry = next((f for f in ("main.py", "src/main.py", "cli.py", "src/main.rs", "cmd", "main.go", "src/index.ts", "src/index.js", "index.js") if os.path.exists(os.path.join(root, f))), None)
        if entry:
            els.append({"id": "app", "kind": "container", "name": f"{name}", "desc": "the application", "proof": entry, "inferred": False})
    for dep, label in STORES.items():
        if dep in d:
            els.append({"id": re.sub(r"[^a-z0-9]", "_", label.lower()), "kind": "store", "name": label, "desc": f"via {dep}", "proof": d[dep], "inferred": False})
    for dep, label in QUEUES.items():
        if dep in d:
            els.append({"id": re.sub(r"[^a-z0-9]", "_", label.lower()), "kind": "container", "name": label, "desc": f"via {dep}", "proof": d[dep], "inferred": False})
    for dep, label in EXTERNALS.items():
        if dep in d:
            els.append({"id": re.sub(r"[^a-z0-9]", "_", label.lower()), "kind": "external", "name": label, "desc": f"via {dep}", "proof": d[dep], "inferred": False})
    for infra, label in (("Dockerfile", "container image"), ("docker-compose.yml", "compose services"), ("compose.yaml", "compose services"), ("fly.toml", "Fly.io"), ("vercel.json", "Vercel"), ("serverless.yml", "serverless functions")):
        p = os.path.join(root, infra)
        if os.path.isfile(p):
            if infra.startswith(("docker-compose", "compose")):
                for m in re.finditer(r"^\s{2}([a-zA-Z0-9_-]+):\s*$", read(p), re.M):
                    svc = m.group(1)
                    if svc in ("db", "postgres", "redis", "mysql", "mongo", "rabbitmq", "kafka", "nats") and not any(e["name"].lower().startswith(svc[:4]) for e in els):
                        els.append({"id": re.sub(r"[^a-z0-9]", "_", svc), "kind": "store" if svc in ("db", "postgres", "mysql", "mongo") else "container", "name": svc, "desc": "compose service", "proof": infra, "inferred": False})
            elif label in ("Fly.io", "Vercel"):
                els.append({"id": re.sub(r"[^a-z0-9]", "_", label.lower()), "kind": "external", "name": label, "desc": "deployment target", "proof": infra, "inferred": False})
    seen, uniq = set(), []
    for e in els:
        if e["id"] not in seen:
            seen.add(e["id"])
            uniq.append(e)
    collapsed = []
    while len(uniq) > CAP:
        # the two most similar: same kind, closest names
        pairs = [(a, b) for i, a in enumerate(uniq) for b in uniq[i + 1:] if a["kind"] == b["kind"] and a["kind"] != "person"]
        if not pairs:
            break
        a, b = min(pairs, key=lambda p: sum(x != y for x, y in zip(p[0]["name"].lower(), p[1]["name"].lower())) + abs(len(p[0]["name"]) - len(p[1]["name"])))
        uniq.remove(b)
        a["desc"] += f" (+ {b['name']} collapsed)"
        collapsed.append(f"{b['name']} collapsed into {a['name']}")
    return uniq, collapsed


def to_dsl(els, name):
    lines = [f'workspace "{name}" "generated by scripts/reef-c4.py — one model, a proof per element; regenerate, never hand-edit the elements" {{', "  model {"]
    rels = []
    for e in els:
        tag = ' "Inferred"' if e["inferred"] else ""
        proof = f"  # proof: {e['proof'] or 'none'}"
        if e["kind"] == "person":
            lines.append(f'    {e["id"]} = person "{e["name"]}" "{e["desc"]}"' + (' { tags "Inferred" }' if e["inferred"] else "") + proof)
        elif e["kind"] == "external":
            lines.append(f'    {e["id"]} = softwareSystem "{e["name"]}" "{e["desc"]}" {{ tags "External"{tag} }}{proof}')
    lines.append(f'    system = softwareSystem "{name}" "the product" {{')
    containers = [e for e in els if e["kind"] in ("container", "store")]
    for e in containers:
        kind = "container"
        tags = ' { tags "Database"' + (' "Inferred"' if e["inferred"] else "") + " }" if e["kind"] == "store" else (' { tags "Inferred" }' if e["inferred"] else "")
        lines.append(f'      {e["id"]} = {kind} "{e["name"]}" "{e["desc"]}"{tags}  # proof: {e["proof"] or "none"}')
    lines.append("    }")
    if containers:
        rels.append(f'    operator -> {containers[0]["id"]} "uses"')
        for x, y in zip(containers, containers[1:]):
            rels.append(f'    {x["id"]} -> {y["id"]} "uses"')
    for e in els:
        if e["kind"] == "external" and containers:
            rels.append(f'    {containers[0]["id"]} -> {e["id"]} "calls"')
    lines += rels + ["  }", "  views {", '    systemContext system "L1" { include * autolayout lr }', '    container system "L2" { include * autolayout lr }', "  }", "}"]
    return "\n".join(lines) + "\n"


def to_mermaid(els, name, level):
    out = ["flowchart LR"]
    containers = [e for e in els if e["kind"] in ("container", "store")]
    if level == 1:
        out.append(f'  operator([Operator]) --> system["{name}"]')
        for e in els:
            if e["kind"] == "external":
                out.append(f'  system --> {e["id"]}["{e["name"]}"]')
    else:
        for e in containers:
            shape = f'[("{e["name"]}")]' if e["kind"] == "store" else f'["{e["name"]}"]'
            out.append(f"  {e['id']}{shape}")
        for x, y in zip(containers, containers[1:]):
            out.append(f"  {x['id']} --> {y['id']}")
        for e in els:
            if e["kind"] == "external" and containers:
                out.append(f'  {containers[0]["id"]} --> {e["id"]}["{e["name"]}"]')
    return "\n".join(out)


def parse_dsl(text):
    """Element ids with their proofs and tags from a workspace.dsl (ours or a hand-edited one)."""
    els = {}
    for m in re.finditer(r"^\s*(\w+)\s*=\s*(person|softwareSystem|container)\s+\"([^\"]*)\"[^\n]*?(?:#\s*proof:\s*(\S+))?\s*$", text, re.M):
        line = m.group(0)
        els[m.group(1)] = {"kind": m.group(2), "name": m.group(3), "proof": m.group(4) or "", "inferred": "Inferred" in line}
    return els


def lint(text):
    bad = []
    if text.count("{") != text.count("}"):
        bad.append(f"unbalanced braces ({text.count('{')} open, {text.count('}')} close)")
    for block in ("model", "views"):
        if not re.search(rf"^\s*{block}\s*\{{", text, re.M):
            bad.append(f"no `{block} {{` block")
    ids = re.findall(r"^\s*(\w+)\s*=\s*(?:person|softwareSystem|container)\b", text, re.M)
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        bad.append(f"duplicate identifiers: {', '.join(dup)}")
    for a, b in re.findall(r"^\s*(\w+)\s*->\s*(\w+)", text, re.M):
        for x in (a, b):
            if x not in ids and x != "system":
                bad.append(f"relationship names unknown element {x!r}")
    return bad


def main(argv):
    repo, write = ".", False
    pos = []
    i = 0
    while i < len(argv):
        if argv[i] == "--repo":
            repo = argv[i + 1]; i += 2
        elif argv[i] == "--write":
            write = True; i += 1
        else:
            pos.append(argv[i]); i += 1
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=repo, capture_output=True, text=True).stdout.strip() or os.path.abspath(repo)
    name = project_name(root)
    dsl_path = os.path.join(root, DSL)
    if pos[:1] == ["lint"]:
        p = pos[1] if len(pos) > 1 else dsl_path
        bad = lint(read(p))
        for b in bad:
            print(f"FAIL: {os.path.relpath(p, root)}: {b}")
        print("ok: DSL structure" if not bad else f"{len(bad)} lint failure(s)")
        return 1 if bad else 0
    els, collapsed = detect(root)
    if pos[:1] == ["generate"]:
        dsl = to_dsl(els, name)
        bad = lint(dsl)
        if bad:
            print("FAIL: generated DSL does not pass its own lint: " + "; ".join(bad))
            return 1
        print(dsl)
        for c in collapsed:
            print(f"collapsed: {c}")
        if write:
            os.makedirs(os.path.dirname(dsl_path), exist_ok=True)
            with open(dsl_path, "w", encoding="utf-8") as f:
                f.write(dsl)
            for lvl, fname in ((1, "context.md"), (2, "container.md")):
                with open(os.path.join(root, "reef", "architecture", fname), "w", encoding="utf-8") as f:
                    f.write(f"<!-- generated by scripts/reef-c4.py from workspace.dsl — do not edit; regenerate -->\n# C4 level {lvl}\n\n```mermaid\n{to_mermaid(els, name, lvl)}\n```\n")
            print(f"written: {DSL}, reef/architecture/context.md, reef/architecture/container.md ({len(els)} elements)")
        return 0
    if pos[:1] == ["--diff"] or "--diff" in argv:
        committed = parse_dsl(read(dsl_path))
        if not committed:
            print(f"FAIL: no committed model at {DSL} — run reef-c4.py generate --write")
            return 1
        fresh = {e["id"]: e for e in els}
        findings = []
        for eid, e in fresh.items():
            if eid not in committed and eid != "operator":
                findings.append(f"missing: {e['name']} ({e['kind']}, proof {e['proof'] or 'none'}) is in the code but not in the committed model")
        for eid, e in committed.items():
            if eid not in fresh and eid != "system":
                findings.append(f"contradicts: {e['name']} ({e['kind']}) is in the committed model but no longer detected")
        for eid, e in fresh.items():
            if eid in committed and not e["proof"] and e["kind"] != "person":
                findings.append(f"inferred: {e['name']} has no proving path")
        for lvl, fname in ((1, "context.md"), (2, "container.md")):
            p = os.path.join(root, "reef", "architecture", fname)
            if os.path.isfile(p):
                want = to_mermaid([e for e in els if e["id"] in committed or e["id"] == "operator"], name, lvl)
                have = re.search(r"```mermaid\n(.*?)\n```", read(p), re.S)
                if not have or have.group(1).strip() != to_mermaid(els, name, lvl).strip():
                    findings.append(f"contradicts: reef/architecture/{fname} differs from the export of the model (hand-edited, or the model moved) — regenerate")
        for c in collapsed:
            print(f"note: {c}")
        if findings:
            for f_ in findings:
                print(f_)
            return 1
        print(f"ok: the committed model matches the code ({len(committed)} elements)")
        return 0
    print("usage: reef-c4.py generate [--write] | lint [dsl] | --diff   [--repo DIR]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
