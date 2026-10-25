#!/usr/bin/env python3
# CLASS: code
"""Reef init — the full project setup, generated from templates, idempotent.

Usage:
  reef-init.py [--root DIR] [--plugin DIR] [--name NAME] [--base BRANCH] [--release BRANCH] [--dry-run] [--verbose]
               [--grill answers.json]
  reef-init.py [--root DIR] --accept <path> [<path> ...]     apply a proposed rendering (after the human said so)
  reef-init.py [--root DIR] --keep <path> [<path> ...]       mark a rendered file as the project's own: never proposed again

0.6 layout: a FRESH project (no docs/queue.md, no .specify/, no docs/adr, no tasks/) gets the one tree —
reef/{constitution,queue,journal,glossary,day-zero}.md, reef/architecture/, reef/features/ — and paths.* pointing
at it; a project that already has the 0.5 layout keeps it (`reef-migrate --layout` moves it later).
--grill answers.json (3.1): the architecture grill's answers {host, shape, scale, store, auth, non_goals[], intent}
render reef/architecture/architecture.md (intent, C4 L1/L2 in Mermaid), draft ADRs for host/store/auth, the
queue's footnotes in the owner's words and batch 1 row 1 = the walking skeleton. Stack opinions (3.1b) from
templates/stacks/<stack>.md are distilled into AGENTS.md's ## Conventions — read at init, never copied. An
existing constitution (.specify/constitution.md, .specify/memory/constitution.md) or spec-kit specs/*/spec.md is
pointed at from AGENTS.md and never duplicated (3.5).

What it writes (from <plugin>/templates/project and <plugin>/scripts), adapted to the detected stack:
  .reef/config.json (merged: missing keys added, nothing existing changed), AGENTS.md, CLAUDE.md
  (pointer, only when absent), .specify/constitution.md, docs/queue.md, docs/adr/README.md,
  docs/journal.md, HANDOFF.md, docs/day-zero.md, docs/glossary.md, .github/workflows/ci.yml,
  .github/dependabot.yml, scripts/reef-*.{py,sh} + reef-attempt + reef-adversarial,
  .githooks/pre-commit + pre-merge-commit, tasks/ + tasks/done/, .gitignore lines, a Makefile
  `setup:` target (appended, never rewritten).

The rule, for every file: ABSENT -> written. IDENTICAL -> skipped. DIFFERENT -> never overwritten:
the rendering goes to <git dir>/reef/proposed/<path>, a unified diff is printed, and `--accept <path>`
applies it once the human has read the diff. A second run with nothing changed writes nothing.
Hooks install (`git config core.hooksPath`), the first commit and the CI offer stay with the
reef-init skill: they are decisions, not renderings.

Exit 0 = done (the summary says what was written / skipped / proposed). 1 = refused.
"""
import datetime
import difflib
import filecmp
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = ["reef-gate.sh", "reef-attempt", "reef-snapshot.sh", "reef-plan-check.py", "reef-graph.py",
           "reef-adversarial", "reef-claims.py", "reef-ci-local.sh", "reef-tier.py", "reef-queue.py",
           # 0.6
           "reef-converge", "reef-record", "reef-structure", "reef-recalibrate", "reef-c4.py", "reef-threat.py",
           "reef-repo", "reef-cost.py", "reef-loop.py", "reef-handoff", "reef-migrate", "reef-merge-base", "reef-merge-close",
           # 0.7 (2026-10-18: /reef-graph on the trial found no scripts/reef-graph-run.py — it was never in this list)
           "reef-graph-run.py", "reef-run.py",
           # v3 phase 2: judges read the suite's one result
           "reef-evidence.py",
           # 0.7.3: the stack profiles (data the measure and the raw-SQL gate read)
           "reef-stacks.json",
           # 2026-10-23: the night prompt runs `python3 scripts/reef-approval.py --proxy`; no project had it
           "reef-approval.py"]
# 4.5 security gates per stack: the auditor is installed by the CI template's setup steps; locally a missing tool is
# exit 77 (skipped — reef-ci-local reports a skip as exit 2, never success). They are RELEASE gates (decision 8):
# a feature PR never pays for a history secret scan or an audit.
AUDITS = {"node": "npm audit --audit-level=high",
          "python": "command -v pip-audit >/dev/null 2>&1 || exit 77; pip-audit",
          "rust": "command -v cargo-audit >/dev/null 2>&1 || exit 77; cargo audit",
          "go": "command -v govulncheck >/dev/null 2>&1 || exit 77; govulncheck ./..."}
GITLEAKS_GATE = "command -v gitleaks >/dev/null 2>&1 || exit 77; gitleaks detect --source . --log-opts=--all --no-banner"
# 0.7.2 (first adoption, 2026-10-24, item 12): injection had no deterministic check — only the security agent's judgment. A release
# gate per stack; semgrep missing is exit 77 (skipped, never success), installed by the CI template like gitleaks.
SEMGREP = {"node": "p/typescript", "python": "p/python", "rust": "p/rust", "go": "p/golang"}
SEMGREP_GATE = "command -v semgrep >/dev/null 2>&1 || exit 77; semgrep scan --config p/owasp-top-ten --config {pack} --error"
SEMGREP_SETUP = "      - run: pip install semgrep\n"
AUDIT_SETUP = {"python": "      - run: pip install pip-audit\n", "rust": "      - run: cargo install cargo-audit --locked\n",
               "go": "      - run: go install golang.org/x/vuln/cmd/govulncheck@latest\n"}
GITLEAKS_SETUP = ("      - name: gitleaks (the history secret scan)\n        run: |\n          curl -sSL https://github.com/gitleaks/gitleaks/releases/download/v8.21.2/gitleaks_8.21.2_linux_x64.tar.gz "
                  "| tar -xz gitleaks && sudo mv gitleaks /usr/local/bin/\n")
TEMPLATES_COMMON = {   # published path -> template under templates/project (or templates/)
    "AGENTS.md": "project/AGENTS.md",
    "HANDOFF.md": "project/HANDOFF.md",
    ".github/workflows/ci.yml": "project/ci.yml",
    ".github/dependabot.yml": "project/dependabot.yml",
    ".githooks/pre-commit": "pre-commit",
    ".githooks/pre-merge-commit": "pre-commit",
}
LAYOUTS = {   # the files whose place depends on the layout (0.5 flat vs 0.6 one tree); paths.* follow them
    "0.5": {"constitution": ".specify/constitution.md", "queue": "docs/queue.md", "adr_readme": "docs/adr/README.md",
            "journal": "docs/journal.md", "day_zero": "docs/day-zero.md", "glossary": "docs/glossary.md",
            "adr": "docs/adr", "tasks": "tasks", "features": None, "architecture": None, "map": "docs/REEF.md"},
    "0.6": {"constitution": "reef/constitution.md", "queue": "reef/queue.md", "adr_readme": "reef/architecture/adr/README.md",
            "journal": "reef/journal.md", "day_zero": "reef/day-zero.md", "glossary": "reef/glossary.md",
            "adr": "reef/architecture/adr", "tasks": "tasks", "features": "reef/features", "architecture": "reef/architecture/architecture.md", "map": "reef/README.md"},
}
TEMPLATE_OF = {"constitution": "project/constitution.md", "queue": "project/queue.md", "adr_readme": "project/adr-README.md",
               "journal": "project/journal.md", "day_zero": "project/day-zero.md", "glossary": "glossary.md",
               "architecture": "project/architecture.md", "map": "project/reef-README.md"}
EXISTING_CONSTITUTIONS = (".specify/constitution.md", ".specify/memory/constitution.md")
STACK_OPINIONS = {"node": "node.md", "python": "python.md", "rust": "rust.md", "go": "go.md"}
GITIGNORE_LINES = [".reef/worktrees/", ".reef/proposed/", ".reef/ci-local/", ".reef/evidence/", ".reef/approvals/", ".reef/review/",
                   ".reef/verifying/", ".reef/inflight/", ".reef/loop.json", ".reef/status.html", ".reef/cost/", ".reef/graph/", "tasks/.plan-review.json", ".env",
                   ".reef/hunt/", ".reef/run/", ".reef/questions.md", ".reef/night/", ".reef/queue.json", ".reef/queue-view.md", "scripts/__pycache__/", ".reef/recalibration/"]   # .reef/recalibration/: the plan's proposals. .reef/run/: reef-run's gate, log and lock; questions.md: the owner's open questions (the handoff reads it). .reef/hunt/: the hunter's own reports: evidence like .reef/ci-local/ (2026-10-18: 12 untracked files in the trial's status)
VERSION = "0.7.2"   # written to .reef/version; absent = a 0.5 project (every 0.6 check warns instead of failing)
MAKEFILE_TARGET = "\nsetup: ## git hooks (once per clone) — reef\n\tgit config core.hooksPath .githooks\n\tchmod +x .githooks/*\n"


def die(msg):
    print(f"reef-init: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- stack

def detect(root):
    """Stack facts the templates need. Only what the files say; nothing guessed is a gate."""
    has = lambda *p: os.path.isfile(os.path.join(root, *p))
    facts = {"name": os.path.basename(os.path.abspath(root)), "stack": "unknown", "test": "", "fast": "",
             "build": "", "install": "", "setup": "", "ecosystem": "", "setup_steps": ""}
    if has("package.json"):
        try:
            with open(os.path.join(root, "package.json"), encoding="utf-8") as f:
                pkg = json.load(f)
        except Exception:
            pkg = {}
        scripts = pkg.get("scripts", {}) if isinstance(pkg, dict) else {}
        deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})} if isinstance(pkg, dict) else {}
        # worktree.setup (0.7.2, first adoption 2026-10-24): a task worktree needs the GENERATED code too — a stale Prisma client
        # and .next types failed ~14 test files for reasons unrelated to the task. The project's `generate` script, else
        # Prisma's generator when Prisma is a dependency; never `scripts.setup` or anything that migrates a database.
        # gates.fast (0.7.2, first adoption 2026-10-24, item 4): the project's own quick checks, each only when present, never
        # invented — it stayed "" and every commit ran the full suite (66 s)
        fast = []
        if "lint" in scripts:
            fast.append("npm run lint")
        if "typecheck" in scripts:
            fast.append("npm run typecheck")
        elif "typescript" in deps and has("tsconfig.json"):
            fast.append("npx tsc --noEmit")
        if "vitest" in deps:
            fast.append("npx vitest run --changed")
        facts["fast"] = " && ".join(fast)
        # a generator the node profile names (scripts/reef-stacks.json `generate`) when the project depends on its tool
        with open(os.path.join(PLUGIN, "scripts", "reef-stacks.json"), encoding="utf-8") as f:
            gen = next((g["run"] for g in (json.load(f).get("node") or {}).get("generate") or [] if any(d in deps for d in g["when_deps"])), None)
        facts["setup"] = "npm ci && npm run generate" if "generate" in scripts else f"npm ci && {gen}" if gen else "npm ci"
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
    facts["setup"] = facts["setup"] or facts["install"]   # the other stacks: install is the whole setup
    facts["setup_steps"] = facts["setup_steps"] + AUDIT_SETUP.get(facts["stack"], "") + GITLEAKS_SETUP + (SEMGREP_SETUP if facts["stack"] in SEMGREP else "")
    # Dependabot: the stack's package entry only when there IS a stack — an unknown stack used to render the
    # github-actions ecosystem twice (first contact, 2026-10-16)
    facts["dependabot_stack_entry"] = (
        f'  - package-ecosystem: "{facts["ecosystem"]}"\n    directory: "/"\n'
        '    target-branch: "{{base}}"      # never against {{release}}: a PR there would sit and go stale\n'
        '    schedule:\n      interval: "weekly"\n    groups:\n      all-dependencies:\n        patterns: ["*"]\n'
        '    open-pull-requests-limit: 3\n') if facts["ecosystem"] else ""
    facts["date"] = datetime.date.today().isoformat()
    # 0.6: the layout — a fresh project gets the one tree; an existing 0.5 layout is kept. Once chosen it is
    # recorded in .reef/config.json paths.* and read back from there, so a second run never flips it.
    facts["layout"] = None
    try:
        with open(os.path.join(root, ".reef", "config.json"), encoding="utf-8") as f:
            q = (json.load(f).get("paths") or {}).get("queue")
        if isinstance(q, str) and q:
            facts["layout"] = "0.6" if q.startswith("reef/") else "0.5"
    except Exception:
        pass
    if facts["layout"] is None:
        legacy = any(os.path.exists(os.path.join(root, p)) for p in ("docs/queue.md", ".specify", "docs/adr"))
        facts["layout"] = "0.5" if legacy else "0.6"
    # 3.5: an existing constitution or spec tooling is read, never duplicated
    facts["constitution"] = next((p for p in EXISTING_CONSTITUTIONS if has(*p.split("/"))), None)
    import glob as _glob
    facts["speckit"] = sorted(os.path.relpath(p, root) for p in _glob.glob(os.path.join(root, "specs", "*", "spec.md")))
    # 3.1b: stack opinions distilled into AGENTS.md's ## Conventions (read from the plugin, never copied)
    facts["conventions"] = ""
    opinion = STACK_OPINIONS.get(facts["stack"])
    if opinion:
        try:
            with open(os.path.join(PLUGIN, "templates", "stacks", opinion), encoding="utf-8") as f:
                body = [l for l in f.read().splitlines() if l.startswith("- ")]
            facts["conventions"] = "\n".join(body)
        except OSError:
            pass
    return facts


# ---------------------------------------------------------------- 3.1 the architecture grill

SHAPES = {"web-app": ["browser", "api", "store"], "api": ["api", "store"], "cli": ["cli", "store"],
          "worker": ["worker", "queue", "store"], "static-site": ["browser", "cdn"]}


def grill_facts(answers, facts):
    """The grill's answers -> the architecture document's facts, the draft ADRs and the queue's first row."""
    a = {k: str(answers.get(k, "") or "").strip() for k in ("host", "shape", "scale", "store", "auth", "intent")}
    non_goals = answers.get("non_goals") or []
    name = facts["name"]
    sid = name.replace("-", "_")
    containers = SHAPES.get(a["shape"], ["app", "store"])
    if a["store"] in ("", "none"):
        containers = [c for c in containers if c != "store"]
    l1 = ["C4Context", f"  title System context — {name}", '  Person(owner, "Operator", "uses the product")',
          f'  System({sid}, "{name}", "{a["shape"] or "the system"} on {a["host"] or "the chosen host"}")',
          f'  Rel(owner, {sid}, "uses")']
    if a["auth"] and a["auth"] not in ("none", "no"):
        l1 += [f'  System_Ext(idp, "Identity", "{a["auth"]}")', f'  Rel({sid}, idp, "authenticates against")']
    l2 = ["C4Container", f"  title Containers — {name}", f'  System_Boundary(b, "{name}") {{']
    for c in containers:
        kind = "ContainerDb" if c == "store" else "Container"
        l2.append(f'    {kind}({c}, "{c}", "{a["store"] if c == "store" else c}")')
    l2.append("  }")
    for x, y in zip(containers, containers[1:]):
        l2.append(f'  Rel({x}, {y}, "calls")')
    facts.update(arch_intent=a["intent"] or f"{name}: a {a['shape'] or 'system'} for its operator, hosted on {a['host'] or 'the chosen host'}.",
                 arch_host=a["host"] or "undecided", arch_shape=a["shape"] or "undecided", arch_scale=a["scale"] or "undecided",
                 arch_store=a["store"] or "none", arch_auth=a["auth"] or "none", arch_non_goals=", ".join(non_goals) or "none stated",
                 arch_c4_l1="\n".join(l1), arch_c4_l2="\n".join(l2))
    facts["first_row"] = f"Walking skeleton: one page end to end through {', '.join(containers)}, built by the stack's generator, deployed to {a['host'] or 'the host'}"
    foot = []
    marks = "¹²³⁴⁵⁶"
    for i, (q, v) in enumerate((("host", a["host"]), ("shape", a["shape"]), ("scale", a["scale"]), ("data store", a["store"]),
                                ("auth boundary", a["auth"]), ("one-year non-goals", ", ".join(non_goals)))):
        if v:
            foot.append(f"{marks[i]} {q}: {v} ({facts['date']})")
    facts["footnotes"] = "\n".join(foot) if foot else "¹ <the owner's decision, in his words, with the date>"
    adrs = {}
    if a["shape"]:
        # the shape decision is the one everyone later argues about ("should we split services?") — written down
        # with its reason, not left implicit in the C4 diagram (first contact, 2026-10-16)
        parts = ", ".join(containers)
        adrs["draft-1-shape.md"] = (f"# ADR draft-1-shape — Shape: {a['shape']}, one deployable (a monolith)\n\nStatus: Accepted (number at merge)\n\n"
                                    f"## Context\nDay zero of {name}; the owner answered the architecture grill on {facts['date']}: shape {a['shape']}, "
                                    f"scale in one year {a['scale'] or 'undecided'}, hosted on {a['host'] or 'undecided'}.\n\n"
                                    f"## Decision\nOne deployable with the containers {parts}, built as a modular monolith: modules with explicit "
                                    f"boundaries inside one process and one repository. No services split at this scale.\n\n"
                                    f"## Alternatives rejected\n- Microservices: operational cost (deploys, networking, observability per service) with "
                                    f"nothing at this scale to pay for it.\n- Serverless functions per feature: fragments the domain before it is known.\n\n"
                                    f"## Consequences\n+ one deploy, one test suite, one gate\n- a module whose boundary is violated is a review finding, "
                                    f"not a network error — `/reef-c4` checks the element-level drift\n- splitting a service later is a queue row with its own ADR, "
                                    f"opened by a measured need (a scaling or team boundary), never by taste\n\n"
                                    f"## Diagram\n```mermaid\nflowchart LR\n  owner --> {sid}[{name}: one deployable]\n  {sid} --> " +
                                    " & ".join(c.replace("-", "_") for c in containers) + "\n```\n")
    for topic, value, title in (("hosting", a["host"], "Hosting"), ("data-store", a["store"], "Data store"), ("auth-boundary", a["auth"], "Auth boundary")):
        if value and value not in ("none", "no"):
            adrs[f"draft-1-{topic}.md"] = (f"# ADR draft-1-{topic} — {title}: {value}\n\nStatus: Accepted (number at merge)\n\n## Context\n"
                                           f"Day zero of {name}; the owner answered the architecture grill on {facts['date']}.\n\n## Decision\n{title} is {value}.\n\n"
                                           f"## Consequences\n+ one {topic.replace('-', ' ')} to operate\n- changing it later is a queue row with its own ADR\n\n"
                                           f"## Diagram\n```mermaid\nflowchart LR\n  owner --> {sid} --> {topic.replace('-', '_')}[{value}]\n```\n")
    facts["draft_adrs"] = adrs
    return facts


def render(template_text, facts):
    out = template_text
    for _ in range(2):   # a fact may itself carry placeholders (the Dependabot stack entry names {{base}})
        for k, v in facts.items():
            out = out.replace("{{" + k + "}}", str(v))
    return out


def release_gates(facts):
    g = {"c4": "python3 scripts/reef-c4.py --diff", "secret-scan": GITLEAKS_GATE}
    if facts["stack"] in AUDITS:
        g["audit"] = AUDITS[facts["stack"]]
    if facts["stack"] in SEMGREP:
        g["injection"] = SEMGREP_GATE.format(pack=SEMGREP[facts["stack"]])
    return g


def project_config(existing, facts):
    """The plugin's config template + the generated project's keys, MERGED under the existing
    config: a key the project already has is never changed (the human may have tuned it)."""
    with open(os.path.join(PLUGIN, "templates", "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["gates"]["fast"] = facts["fast"]
    cfg["gates"]["full"] = facts["test"]
    cfg["gates"]["extra"] = {"build": facts["build"]} if facts["build"] else {}
    cfg["gates"]["release"] = release_gates(facts)
    cfg["branches"] = {"base": facts["base"], "release": facts["release"]}
    cfg["merge"] = {"by": "loop" if facts["base"] != facts["release"] else "human"}
    cfg["ci"] = {"feature_gate": "local" if facts["base"] != facts["release"] else "ci"}
    lay = LAYOUTS[facts["layout"]]
    cfg["paths"]["runlog"] = lay["journal"]
    cfg["paths"]["queue"] = lay["queue"]
    cfg["paths"]["adr"] = lay["adr"]
    cfg["paths"]["glossary"] = lay["glossary"]
    cfg["paths"]["tasks"] = lay["tasks"]
    if lay["features"]:
        cfg["paths"]["features"] = lay["features"]
    cfg["worktree"]["setup"] = facts["setup"]
    # the tier table (models per role, effort, light allowlist) and the writing caps come from the
    # plugin's templates/config.json — one home; nothing is restated here

    def merge(base, over):
        for k, v in over.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict) and base[k]:
                merge(base[k], v)
            elif k not in base or (base[k] in ("", {}, None) and v not in ("", {}, None)):
                # a tuned value is never changed; a value that was never SET (the empty string init itself wrote
                # before the stack existed — first contact, 2026-10-16: `gates.full` stayed "" after the Next.js
                # scaffold arrived and the owner had to hand-edit a guarded file) is filled when the stack now says
                base[k] = v
        return base
    return merge(existing, cfg) if existing is not None else cfg


# ---------------------------------------------------------------- the one rule

MANIFEST = os.path.join(".reef", "init-manifest.json")
# another tool's block in a file Reef renders (Next.js's `<!-- BEGIN:nextjs-agent-rules --> … <!-- END:… -->` in
# AGENTS.md, written by `next dev` on every run): not Reef's, not the owner's — carried over whole on a re-render
FOREIGN_BLOCK = re.compile(r"\n*<!-- BEGIN:([\w.-]+) -->.*?<!-- END:\1 -->\n*", re.S)


def split_foreign(text):
    """(core, blocks): the text without foreign blocks, and the blocks in order."""
    blocks = [m.group(0).strip("\n") for m in FOREIGN_BLOCK.finditer(text)]
    core = FOREIGN_BLOCK.sub("\n", text).rstrip("\n") + "\n" if blocks else text
    return core, blocks


BLOCK = re.compile(r"<!-- BEGIN:([\w.-]+) -->(.*?)<!-- END:\1 -->", re.S)


def adopt_sections(content, current):
    """A kept block the TEMPLATE carries but the CURRENT file does not yet mark: the current text of that section
    (under the same heading, up to the next heading) becomes the block's body, so the first render after the block
    arrived carries the owner's words into it instead of the template's (first contact, 2026-10-17: the proposal put
    the placeholder back over the owner's decision points and reverted the Boundaries line a feature had written)."""
    for m in list(BLOCK.finditer(content)):
        name = m.group(1)
        if f"<!-- BEGIN:{name} -->" in current:
            continue
        head = content[:m.start()].rstrip("\n").splitlines()
        heading = next((l for l in reversed(head) if l.startswith("#")), None)
        if not heading or heading not in current.splitlines():
            continue
        after = current.split(heading + "\n", 1)[1]
        body = re.split(r"\n#{1,6} |\n<!-- BEGIN:", after, 1)[0].strip("\n")
        if body:
            content = content.replace(m.group(0), f"<!-- BEGIN:{name} -->{body}<!-- END:{name} -->", 1)
    return content


def with_foreign(content, blocks):
    """The current file's blocks ride into the new rendering. A block the TEMPLATE also carries (the owner's decision
    points in AGENTS.md, `reef-owner-decisions`) is replaced IN PLACE by the current one, so the owner's text survives
    a re-render (first contact, 2026-10-17: a refresh put the template's "(fill in — examples: …)" back over the
    owner's list). Any other block is appended, as before."""
    if not blocks:
        return content
    rest = []
    for b in blocks:
        name = re.match(r"<!-- BEGIN:([\w.-]+) -->", b.strip()).group(1)
        pat = re.compile(r"<!-- BEGIN:" + re.escape(name) + r" -->.*?<!-- END:" + re.escape(name) + r" -->", re.S)
        if pat.search(content):
            content = pat.sub(lambda _m: b.strip("\n"), content, count=1)
        else:
            rest.append(b)
    return content if not rest else content.rstrip("\n") + "\n\n" + "\n\n".join(rest) + "\n"


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


def reef_dir(root):
    """0.7.3 (first adoption, 2026-10-25): Reef's proposals live under the git dir — every tool, test and linter skips .git; under
    .reef/proposed/ a project test that walks the disk counted .dependency-cruiser.cjs and a .claude/ folder as its own.
    The common dir, so a linked worktree sees the same proposals. Outside a git repository: .reef/ as before."""
    r = subprocess.run(["git", "-C", root, "rev-parse", "--git-common-dir"], capture_output=True, text=True)
    g = r.stdout.strip()
    if r.returncode != 0 or not g:
        return os.path.join(root, ".reef")
    return os.path.join(g if os.path.isabs(g) else os.path.join(root, g), "reef")


def carry_old_proposals(root):
    """An older Reef left its proposals in the work tree (.reef/proposed/, .reef/recalibration/proposed/): moved once under
    the git dir; a name already there keeps the newer copy."""
    new = reef_dir(root)
    if os.path.abspath(new) == os.path.abspath(os.path.join(root, ".reef")):
        return
    for old, dst in ((os.path.join(".reef", "proposed"), "proposed"), (os.path.join(".reef", "recalibration", "proposed"), os.path.join("recalibration", "proposed"))):
        src = os.path.join(root, old)
        for dp, _, fn in os.walk(src):
            for f in fn:
                t = os.path.join(new, dst, os.path.relpath(os.path.join(dp, f), src))
                if not os.path.exists(t):
                    os.makedirs(os.path.dirname(t), exist_ok=True)
                    shutil.move(os.path.join(dp, f), t)
        shutil.rmtree(src, ignore_errors=True)


def load_manifest(root):
    """rel path -> sha256 of the content Reef itself last placed there (written or accepted). A file whose
    current bytes still match is Reef's own, untouched by anyone: a better rendering replaces it without a
    question. Anything else (edited, generated by another tool, or unknown to the manifest) is proposed."""
    try:
        with open(os.path.join(root, MANIFEST), encoding="utf-8") as f:
            m = json.load(f)
        return m if isinstance(m, dict) else {}
    except (OSError, ValueError):
        return {}


def save_manifest(root, manifest):
    p = os.path.join(root, MANIFEST)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(manifest.items())), f, indent=2)
        f.write("\n")


class Writer:
    def __init__(self, root, dry, write_once=()):
        self.root, self.dry = root, dry
        self.written, self.updated, self.skipped, self.proposed = [], [], [], []
        self.manifest = load_manifest(root)
        self.write_once = set(write_once)

    def place(self, rel, content, executable=False):
        target = os.path.join(self.root, rel)
        if rel in self.write_once and os.path.exists(target):
            # a RECORD (the handoff, the journal, the queue and its archive) is rendered once, at birth; afterwards it
            # is the project's history — never re-rendered, never proposed (first contact, 2026-10-16: init offered
            # to replace HANDOFF.md and reef/journal.md with their blank templates; accepting would have erased the
            # owner's gate decision)
            self.skipped.append(rel + " (record, never re-rendered)")
            return
        if os.path.exists(target) and self.manifest.get(rel) == "owner":
            self.skipped.append(rel + " (the project's own since `reef-init --keep`; never proposed)")
            return
        if os.path.exists(target):
            with open(target, "rb") as f:
                current = f.read()
            content = adopt_sections(content, current.decode("utf-8", "replace"))
            core, blocks = split_foreign(current.decode("utf-8", "replace"))
            own = {m.group(1) for m in re.finditer(r"<!-- BEGIN:([\w.-]+) -->", content)}   # the template's own blocks
            foreign_n = len([b for b in blocks if re.match(r"<!-- BEGIN:([\w.-]+) -->", b.strip()).group(1) not in own])
            content = with_foreign(content, blocks)   # whatever happens, another tool's blocks ride along
            if current == content.encode("utf-8"):
                self.skipped.append(rel)
                self.manifest[rel] = sha(core)
                return
            if rel != "_init" and self.manifest.get(rel) == sha(core):
                # Reef's own rendering, byte-identical to what it placed last time — nobody touched it (first
                # contact, 2026-10-16: four files init wrote on an empty repo came back as questions minutes
                # later when the stack arrived; a question about replacing one's own untouched draft is noise)
                if not self.dry:
                    with open(target, "w", encoding="utf-8", newline="") as f:
                        f.write(content)
                    self.manifest[rel] = sha(split_foreign(content)[0])
                self.updated.append(rel + (f" (+{foreign_n} foreign block(s) kept)" if foreign_n else ""))
                return
            prop = os.path.join(reef_dir(self.root), "proposed", rel)
            if not self.dry:
                os.makedirs(os.path.dirname(prop), exist_ok=True)
                with open(prop, "w", encoding="utf-8", newline="") as f:
                    f.write(content)
            diff = difflib.unified_diff(current.decode("utf-8", "replace").splitlines(True),
                                        content.splitlines(True), fromfile=rel, tofile=os.path.relpath(prop, self.root))
            self.proposed.append((rel, "".join(diff)))
            return
        if not self.dry:
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="") as f:
                f.write(content)
            if executable:
                os.chmod(target, os.stat(target).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            self.manifest[rel] = sha(split_foreign(content)[0])   # the core, as the other paths record it (the owner block is not Reef's)
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
    if not dry:
        carry_old_proposals(root)
    lay0 = LAYOUTS[facts["layout"]]
    w = Writer(root, dry, write_once={"HANDOFF.md", lay0["journal"], lay0["queue"], lay0["glossary"],
                                       os.path.join(os.path.dirname(lay0["queue"]), "queue-archive.md")})
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
    if existing is not None and "release" not in (existing.get("gates") or {}):
        # 4.5: for an existing project the security gates arrive as a PROPOSAL (reef_dir/proposed/), never as a
        # red CI on upgrade — the owner adds them to gates.release when the tools are installed
        merged["gates"].pop("release", None)
        prop = os.path.join(reef_dir(root), "proposed", "gates.release.json")
        if not dry:
            os.makedirs(os.path.dirname(prop), exist_ok=True)
            with open(prop, "w", encoding="utf-8") as f:
                json.dump({"gates": {"release": release_gates(facts)}}, f, indent=2)
                f.write("\n")
        w.proposed.append((".reef/config.json gates.release", "+ " + json.dumps(release_gates(facts)) + "\n  (release gates: C4 drift, history secret scan, dependency audit, injection scan — add to gates.release when the tools are installed; a missing tool is exit 77 = skipped, and reef-ci-local reports a skip as exit 2, not success)\n"))
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
    # the version marker: every 0.6 check reads it (absent = 0.5: warn, never fail)
    vpath = os.path.join(root, ".reef", "version")
    if not os.path.isfile(vpath):
        if not dry:
            os.makedirs(os.path.dirname(vpath), exist_ok=True)
            with open(vpath, "w", encoding="utf-8") as f:
                f.write(VERSION + "\n")
        w.written.append(".reef/version")
    else:
        w.skipped.append(".reef/version")
    # templates: the common ones, then the layout's
    lay = LAYOUTS[facts["layout"]]
    facts.setdefault("first_row", "<the first planned row, one line>")
    facts.setdefault("footnotes", "¹ <the owner's decision, in his words, with the date>")
    facts["constitution_path"] = facts.get("constitution") or lay["constitution"]
    facts["queue_path"], facts["journal_path"], facts["adr_path"] = lay["queue"], lay["journal"], lay["adr"]
    facts["day_zero_path"], facts["glossary_path"] = lay["day_zero"], lay["glossary"]
    facts["features_path"] = lay["features"] or "tasks"
    # the map (usability plan A4): the project's real worktree dir and feature prefix, from its config when it has one
    try:
        with open(os.path.join(root, ".reef", "config.json"), encoding="utf-8") as f:
            _c = json.load(f)
    except Exception:
        _c = {}
    facts.setdefault("worktrees_dir", str(((_c.get("worktree") or {}).get("dir")) or ".reef/worktrees").rstrip("/"))
    facts.setdefault("feature_prefix", str(((_c.get("branches") or {}).get("feature_prefix")) or "feat/"))
    facts.setdefault("glossary_path", lay["glossary"])
    facts.setdefault("constitution_path", facts.get("constitution") or lay["constitution"])
    targets = dict(TEMPLATES_COMMON)
    w.manifest.setdefault("_init", {"date": facts["date"], "name": facts["name"]})
    for key, tpl in TEMPLATE_OF.items():
        rel = lay.get(key)
        if rel is None:
            continue
        if key == "constitution":
            w.write_once.add(rel)   # ratified once; a record like the journal
        if key == "constitution" and facts.get("constitution"):
            w.skipped.append(f"{facts['constitution']} (existing constitution — pointed at, never duplicated)")
            continue
        if key == "architecture" and "arch_c4_l1" not in facts:
            continue   # only the grill renders the architecture document
        targets[rel] = tpl
    for rel, tpl in targets.items():
        with open(os.path.join(PLUGIN, "templates", tpl), encoding="utf-8") as f:
            w.place(rel, render(f.read(), facts), executable=rel.startswith(".githooks/"))
    for name_, text in (facts.get("draft_adrs") or {}).items():
        w.write_once.add(f"{lay['adr']}/{name_}")   # a decision record is written at birth, never re-rendered
        w.place(f"{lay['adr']}/{name_}", text)
    if lay["features"] and not dry:
        os.makedirs(os.path.join(root, lay["features"]), exist_ok=True)
    if not os.path.exists(os.path.join(root, "CLAUDE.md")):
        with open(os.path.join(PLUGIN, "templates", "project/CLAUDE.md"), encoding="utf-8") as f:
            w.place("CLAUDE.md", f.read())
    for name in SCRIPTS:
        with open(os.path.join(PLUGIN, "scripts", name), encoding="utf-8") as f:
            w.place(f"scripts/{name}", f.read(), executable=not name.endswith(".json"))
    for d in ((["tasks", "tasks/done"] if lay["features"] is None else []) + [lay["adr"]]):
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


def keep(root, paths):
    """The owner's word that a rendered file is now the project's: ci.yml after a feature added a service, a README
    rewritten by hand. Recorded in the manifest as "owner"; a refresh skips it and never proposes it again."""
    manifest = load_manifest(root)
    for rel in paths:
        if not os.path.isfile(os.path.join(root, rel)):
            die(f"no such file to keep: {rel}")
        manifest[rel] = "owner"
        print(f"kept as the project's own: {rel}")
    save_manifest(root, manifest)


def accept(root, paths):
    manifest = load_manifest(root)
    for rel in paths:
        prop = os.path.join(reef_dir(root), "proposed", rel)
        if not os.path.isfile(prop):
            die(f"nothing proposed for {rel} (run reef-init first; the diff is printed then)")
        target = os.path.join(root, rel)
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        mode = os.stat(target).st_mode if os.path.exists(target) else None
        shutil.copyfile(prop, target)
        if mode is not None:
            os.chmod(target, mode)
        os.unlink(prop)
        with open(target, "rb") as f:
            manifest[rel] = sha(split_foreign(f.read().decode("utf-8", "replace"))[0])   # accepted = Reef's own again
        print(f"accepted: {rel}")
    save_manifest(root, manifest)


def main(argv):
    if os.name == "nt" or os.environ.get("REEF_TEST_NATIVE_WINDOWS"):
        # the guard, the task graph and the attempt counter need fcntl locks, a signal timer and process groups
        print("reef-init: Reef runs on macOS or Linux; on Windows, run Claude Code inside WSL2 — native Windows lacks the file locks and timers Reef's guard needs; nothing written", file=sys.stderr)
        return 1
    root, name, base, release, dry, to_accept, to_keep, grill, queue = ".", None, "develop", "main", False, [], [], None, None
    verbose = "--verbose" in argv
    argv = [a for a in argv if a != "--verbose"]
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
        elif a == "--grill":
            grill = argv[i + 1]; i += 2
        elif a == "--queue" and i + 1 < len(argv) and argv[i + 1] in ("issues", "file"):
            queue = argv[i + 1]; i += 2
        elif a == "--accept":
            to_accept = argv[i + 1:]; break
        elif a == "--keep":
            to_keep = argv[i + 1:]; break
        else:
            die(f"unknown argument {a!r}")
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        die(f"not a directory: {root}")
    if to_accept:
        accept(root, to_accept)
        return 0
    if to_keep:
        keep(root, to_keep)
        return 0
    facts = detect(root)
    if name:
        facts["name"] = name
    # a refresh keeps the project's day zero and its name: the first init records both in the manifest (first contact,
    # 2026-10-17: a refresh re-dated four ADRs and the constitution's "Ratified" line to today and lowercased the name)
    pinned = load_manifest(root).get("_init") or {}
    if not name and pinned.get("name"):
        facts["name"] = pinned["name"]
    if pinned.get("date"):
        facts["date"] = pinned["date"]
    facts["base"], facts["release"] = base, release
    if os.path.isfile(os.path.join(root, ".reef", "config.json")) and not dry:
        # 6.3: versioned, idempotent migrations run before rendering (0.5 -> 0.6 adds keys only, writes .reef/version)
        r = subprocess.run([sys.executable, os.path.join(PLUGIN, "scripts", "reef-migrate"), "--repo", root, "--plugin", PLUGIN],
                           capture_output=True, text=True)
        for line in r.stdout.strip().splitlines():
            print("  " + line)
        if r.returncode != 0:
            die(f"migration refused: {r.stderr.strip()[:300]}")
    if grill:
        try:
            with open(grill, encoding="utf-8") as f:
                answers = json.load(f)
        except Exception as e:
            die(f"cannot read grill answers {grill}: {e}")
        grill_facts(answers, facts)
    new = not os.path.isfile(os.path.join(root, ".reef", "config.json"))
    # a repository with tracked files is an existing project even on its first init (2026-10-24, AI coach)
    existing = bool(subprocess.run(["git", "-C", root, "ls-files"], capture_output=True, text=True).stdout.strip())
    w = run(root, facts, dry)
    print(f"reef-init ({'dry run, ' if dry else ''}stack: {facts['stack']}, layout: {facts['layout']}, base: {base}, release: {release})")
    if facts.get("constitution"):
        print(f"  existing constitution: {facts['constitution']} — pointed at from AGENTS.md, not duplicated")
    if facts.get("speckit"):
        print(f"  existing specs: {', '.join(facts['speckit'][:5])} — /reef-plan reads them as input")
    if not dry:
        save_manifest(root, w.manifest)
    for r in w.written:
        print(f"  written  {r}")
    for r in w.updated:
        print(f"  updated  {r} (Reef's own rendering, untouched since it was placed — replaced without a question)")
    if verbose:
        for r in w.skipped:
            print(f"  skipped  {r}" + ("" if "(" in r else " (identical)"))
    elif w.skipped:
        # one line, not forty (first full loop, 2026-10-17: every refresh printed 38 `skipped` lines the owner had to
        # read past to find the one `PROPOSED`); --verbose lists them
        kinds = {"record": 0, "own": 0, "identical": 0}
        for r in w.skipped:
            kinds["record" if "record" in r else "own" if "project's own" in r else "identical"] += 1
        parts = [f"{kinds['identical']} identical"] + ([f"{kinds['record']} record(s)"] if kinds["record"] else []) + \
                ([f"{kinds['own']} the project's own"] if kinds["own"] else [])
        print(f"  skipped  {len(w.skipped)} ({', '.join(parts)}; --verbose lists them)")
    for rel, diff in w.proposed:
        print(f"  PROPOSED {rel} differs from the rendering — NOT overwritten; see {os.path.relpath(os.path.join(reef_dir(root), 'proposed', rel), root)}")
        print("".join("    " + l for l in diff.splitlines(True)), end="")
    if w.proposed:
        print(f"  to apply one after reading its diff: python3 {os.path.abspath(__file__)} --root {os.path.abspath(root)} --accept <path>")
    if not facts["test"]:
        print("  NOTE: no test command detected — gates.full is empty and the gate FAILS LOUDLY until you set it")
    print(f"  {len(w.written)} written, " + (f"{len(w.updated)} updated, " if w.updated else "") +
          f"{len(w.skipped)} skipped, {len(w.proposed)} proposed")
    for line in rails_report(root):
        print("  " + line)
    for line in ([] if dry else queue_home(root, queue, new, existing)):
        print("  " + line)
    return 0


def queue_home(root, choice, new, existing=False):
    """0.7.1 (the owner's go, 2026-10-24: no on-device queue unless clearly told): a new project's queue moves to the
    repository's GitHub issues unless the owner chose `--queue file`; an existing one moves only on `--queue issues`."""
    with open(os.path.join(root, ".reef", "config.json"), encoding="utf-8") as f:
        if (json.load(f).get("queue") or {}).get("home") == "issues":
            return []
    if choice == "file" or (choice is None and not new):
        return ["queue: a local file (--queue file)"] if choice == "file" else []
    hint = "`python3 scripts/reef-queue.py migrate-to-issues --apply` moves it"
    if choice is None and existing:
        # /reef-assess converts the project's specs into rows and writes them to the file: the move waits for it
        return [f"queue: a local file — an existing project: run /reef-assess first, then {hint}"]
    g = lambda *a: subprocess.run(["git", "-C", root, *a], capture_output=True, text=True).stdout.strip()
    # the project's own repository only: a folder inside another checkout would inherit that checkout's remote
    if os.path.realpath(g("rev-parse", "--show-toplevel") or "/") != os.path.realpath(root) or "github.com" not in g("remote", "get-url", "origin"):
        return [f"queue: a local file (no GitHub remote) — {hint} once the repository is on GitHub"]
    try:
        logged_in = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        logged_in = False
    if not logged_in:
        return [f"queue: a local file (gh is not logged in) — `gh auth login`, then {hint}"]
    r = subprocess.run([sys.executable, os.path.join(root, "scripts", "reef-queue.py"), "migrate-to-issues", "--apply", "--repo", root],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return [f"queue: stays a local file, the move failed ({(r.stderr or r.stdout).strip()[-200:]}) — {hint}"]
    return ["queue: the repository's GitHub issues (labelled reef-row, a batch is a milestone) — commit reef/queue.md and .reef/config.json"]


RAILS = {"pii": "critical", "money": "critical", "auth": "critical", "migration": "design"}
RANK = {"light": 0, "full": 1, "design": 2, "critical": 3}


def rails_report(root):
    """0.6 path-class rails apply to features planned under 0.6; an older in-flight task whose `touches:`
    (or a path under tiers.design/critical.paths it names in its Scope) would raise its tier is LISTED here
    so the owner can re-plan it — never refused."""
    import re
    out = []
    tdir = os.path.join(root, "tasks")
    for d in (tdir,):
        for f in (sorted(os.listdir(d)) if os.path.isdir(d) else []):
            if not re.match(r"^\d+-.*\.md$", f):
                continue
            with open(os.path.join(d, f), encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            m = re.match(r"\A---\r?\n(.*?\r?\n)---", text, re.S)
            if not m:
                continue
            fm = dict(l.partition(":")[::2] for l in m.group(1).splitlines() if ":" in l)
            tier = fm.get("tier", "").strip() or "full"
            touches = [t.strip().strip("\"'") for t in fm.get("touches", "").strip().strip("[]").split(",") if t.strip()]
            forced = max((RAILS[t] for t in touches if t in RAILS), key=lambda t: RANK[t], default=None)
            if forced and RANK.get(tier, 1) < RANK[forced]:
                out.append(f"RAILS: tasks/{f} is tier {tier} but touches {touches} would make it {forced} under 0.6 — re-plan it (not refused: planned before 0.6)")
    return out


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
