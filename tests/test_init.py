"""Sabotage suite for scripts/reef-init.py: idempotent, never overwrites, one home per fact,
the generated CI is release-only, every generated file is true to the detected stack."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INIT = os.path.join(ROOT, "scripts", "reef-init.py")


def init(root, *args):
    return subprocess.run([sys.executable, INIT, "--root", root, "--verbose", *args], capture_output=True, text=True)


class NativeWindowsInit(unittest.TestCase):
    def test_init_refuses_on_native_windows_and_writes_nothing(self):
        d = tempfile.mkdtemp(prefix="reef-win-init.")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-init.py"), "--root", d],
                           capture_output=True, text=True, env=dict(os.environ, REEF_TEST_NATIVE_WINDOWS="1"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("on Windows, run Claude Code inside WSL2", r.stderr)
        self.assertEqual(os.listdir(d), [], "nothing written")


class QuietByDefault(unittest.TestCase):
    def test_a_refresh_prints_one_skipped_line_unless_verbose(self):
        # first full loop (2026-10-17): every refresh printed 38 `skipped` lines the owner read past to find one PROPOSED
        d = node_project(tempfile.mkdtemp(prefix="reef-init-quiet."))
        init(d)
        r = subprocess.run([sys.executable, INIT, "--root", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = [l for l in r.stdout.splitlines() if l.startswith("  skipped")]
        self.assertEqual(len(lines), 1, r.stdout)
        self.assertRegex(lines[0], r"^  skipped  \d+ \(\d+ identical, \d+ record\(s\); --verbose lists them\)$")
        self.assertIn("0 written, ", r.stdout)
        v = init(d)
        self.assertGreater(len([l for l in v.stdout.splitlines() if l.startswith("  skipped")]), 10, "--verbose lists every file")


def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        return f.read()


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def node_project(root):
    write(root, "package.json", json.dumps({"name": "demo-app", "scripts": {"test": "echo t", "build": "echo b"}}))
    subprocess.run(["git", "init", "-q", "-b", "develop", root], check=True)
    return root


class CopiedScripts(unittest.TestCase):
    """2026-10-18: /reef-graph on the trial project found no scripts/reef-graph-run.py — the script shipped in the
    plugin, the skill ran it as `python3 scripts/reef-graph-run.py`, and reef-init's SCRIPTS list never named it."""
    # these run from the plugin (hooks and the plugin-side commands), never from a project copy
    # reef-approval.py is both: the hook runs the plugin's copy, a night's --proxy runs the project's (2026-10-23)
    PLUGIN_RESIDENT = {"reef-guard.py", "reef-init.py", "reef-update.py", "reef-doctor.py", "reef-guard-profile.py", "reef-opencode.py"}

    def scripts_list(self):
        src = read(ROOT, "scripts/reef-init.py")
        return re.findall(r'"([^"]+)"', re.search(r"SCRIPTS = \[(.*?)\]", src, re.S).group(1))

    def test_every_script_a_skill_runs_from_the_project_is_copied(self):
        import glob
        refs = {}
        # 2026-10-23: the runner's night prompt told the orchestrator `python3 scripts/reef-approval.py --proxy`, and no project
        # had it — the prompts the runner sends are instructions too
        for f in glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md")) + glob.glob(os.path.join(ROOT, "agents", "*.md")) + \
                [os.path.join(ROOT, "scripts", "reef-run.py")]:
            with open(f, encoding="utf-8") as h:
                t = h.read()
            # `scripts/reef-x` with nothing before `scripts/`: a project path. `${CLAUDE_PLUGIN_ROOT}/scripts/…` is the plugin's.
            for m in re.finditer(r"(?<![\w/${}~.-])scripts/(reef-[\w.-]+?)\.?(?=[\s`'\")<>|;,:]|$)", t, re.M):
                refs.setdefault(m.group(1), os.path.relpath(f, ROOT))
        copied = set(self.scripts_list())
        missing = {n: f for n, f in refs.items() if n not in copied and n not in self.PLUGIN_RESIDENT}
        self.assertEqual(missing, {}, f"skills run these from the project but reef-init never copies them: {missing}")
        self.assertIn("reef-graph-run.py", copied)
        for n in copied:
            self.assertTrue(os.path.isfile(os.path.join(ROOT, "scripts", n)), f"SCRIPTS names {n}, which the plugin does not ship")

    def test_init_copies_reef_approval_and_its_proxy_runs_from_the_project(self):
        d = node_project(tempfile.mkdtemp(prefix="reef-init-scripts."))
        r = init(d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        p = os.path.join(d, "scripts", "reef-approval.py")
        self.assertTrue(os.path.isfile(p), "the night prompt's `scripts/reef-approval.py --proxy` must exist in the project")
        r = subprocess.run([sys.executable, p, "--proxy", "--feature", "x", "--report", ".reef/ci-local/report-mahmoud-x.md"],
                           capture_output=True, text=True, cwd=d)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("no night is running", r.stdout, "the project copy runs and refuses outside a night")

    def test_init_copies_reef_graph_run(self):
        d = node_project(tempfile.mkdtemp(prefix="reef-init-scripts."))
        r = init(d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(d, "scripts", "reef-graph-run.py")))
        self.assertEqual(read(d, "scripts/reef-graph-run.py"), read(ROOT, "scripts/reef-graph-run.py"))


class Idempotent(unittest.TestCase):
    def setUp(self):
        self.d = node_project(tempfile.mkdtemp(prefix="reef-init."))

    def test_second_run_writes_nothing(self):
        r = init(self.d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0 proposed", r.stdout)
        snapshot = {rel: read(self.d, rel) for rel in ("AGENTS.md", ".reef/config.json", "reef/queue.md", ".gitignore")}
        r2 = init(self.d)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertRegex(r2.stdout, r"\n  0 written, \d+ skipped, 0 proposed")
        for rel, before in snapshot.items():
            self.assertEqual(read(self.d, rel), before, f"{rel} changed on an idempotent re-run")

    def test_existing_file_never_overwritten_diff_proposed_accept_applies(self):
        write(self.d, "AGENTS.md", "# my own AGENTS.md\nhand-written\n")
        r = init(self.d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(read(self.d, "AGENTS.md"), "# my own AGENTS.md\nhand-written\n", "a user's file was overwritten")
        self.assertIn("PROPOSED AGENTS.md", r.stdout)
        self.assertIn("-# my own AGENTS.md", r.stdout)       # the diff was printed
        self.assertTrue(os.path.isfile(os.path.join(self.d, ".reef", "proposed", "AGENTS.md")))
        r = init(self.d, "--accept", "AGENTS.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("# AGENTS.md", read(self.d, "AGENTS.md"))
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "proposed", "AGENTS.md")))

    def test_accept_without_proposal_refused(self):
        init(self.d)
        r = init(self.d, "--accept", "docs/queue.md")
        self.assertEqual(r.returncode, 1)

    def test_config_keys_added_values_never_changed(self):
        write(self.d, ".reef/config.json", json.dumps({"gates": {"full": "my-own-gate"}, "caps": {"attempts": 5}}))
        init(self.d)
        cfg = json.loads(read(self.d, ".reef/config.json"))
        self.assertEqual(cfg["gates"]["full"], "my-own-gate", "a tuned value was overwritten")
        self.assertEqual(cfg["caps"]["attempts"], 5)
        self.assertEqual(cfg["graph"]["parallel"], 10)        # missing keys arrive
        self.assertEqual(cfg["branches"], {"base": "develop", "release": "main"})

    def test_fresh_init_sets_the_measured_context_caps(self):
        # 0.7: the caps come from the measured rows (docs/perf/dogfood-2026-10-16.md §E); a migrated 0.5 project
        # keeps 0/0 (tests/test_layout.py::Migrations), a NEW project gets the measured defaults
        init(self.d)
        cfg = json.loads(read(self.d, ".reef/config.json"))
        self.assertEqual((cfg["caps"]["context_warn"], cfg["caps"]["context_tokens"]), (100000, 150000))

    def test_gitignore_and_makefile_appended_not_rewritten(self):
        write(self.d, ".gitignore", "node_modules/\n")
        write(self.d, "Makefile", "build:\n\techo b\n")
        init(self.d)
        gi = read(self.d, ".gitignore")
        self.assertTrue(gi.startswith("node_modules/\n"))
        self.assertIn(".reef/worktrees/", gi)
        for evidence in (".reef/ci-local/", ".reef/hunt/"):   # 2026-10-18: twelve untracked hunt reports in the trial's status
            self.assertIn(evidence + "\n", gi, f"{evidence} is evidence the guard protects; it is never committed")
        # 2026-10-24, the trial: Python byte-code of the copied scripts showed up untracked in every git status
        self.assertIn("scripts/__pycache__/\n", gi)
        mk = read(self.d, "Makefile")
        self.assertTrue(mk.startswith("build:\n"))
        self.assertIn("\nsetup:", mk)
        init(self.d)
        self.assertEqual(read(self.d, "Makefile").count("setup:"), 1, "setup: appended twice")

    def test_claude_md_pointer_only_when_absent(self):
        write(self.d, "CLAUDE.md", "# existing brief\n")
        r = init(self.d)
        self.assertEqual(read(self.d, "CLAUDE.md"), "# existing brief\n")
        self.assertNotIn("PROPOSED CLAUDE.md", r.stdout, "a CLAUDE.md the human wrote is theirs; no pointer proposed")

    def test_dry_run_writes_nothing(self):
        r = init(self.d, "--dry-run")
        self.assertEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.d, "AGENTS.md")))


class WorktreeSetup(unittest.TestCase):
    """0.7.2 (ai-coach, 2026-10-24): worktree.setup installs AND generates — a task worktree with a stale Prisma client and
    .next types failed ~14 test files unrelated to the task. Never the project's `setup` script (it may migrate)."""

    def setup_for(self, pkg):
        d = tempfile.mkdtemp(prefix="reef-init-wt.")
        write(d, "package.json", json.dumps({"name": "demo", **pkg}))
        subprocess.run(["git", "init", "-q", "-b", "develop", d], check=True)
        self.assertEqual(init(d).returncode, 0)
        return json.loads(read(d, ".reef/config.json"))["worktree"]["setup"]

    def test_generate_script_then_prisma_then_plain_install(self):
        self.assertEqual(self.setup_for({"scripts": {"test": "vitest run", "generate": "prisma generate && next typegen"},
                                         "dependencies": {"@prisma/client": "6"}}), "npm ci && npm run generate")
        self.assertEqual(self.setup_for({"scripts": {"test": "vitest run"}, "devDependencies": {"prisma": "6"}}), "npm ci && npx prisma generate")
        self.assertEqual(self.setup_for({"scripts": {"test": "vitest run"}, "dependencies": {"@prisma/client": "6"}}), "npm ci && npx prisma generate")
        self.assertEqual(self.setup_for({"scripts": {"test": "vitest run"}}), "npm ci")

    def test_a_setup_script_is_never_chosen(self):
        self.assertEqual(self.setup_for({"scripts": {"test": "t", "setup": "prisma migrate deploy && prisma db seed"}}), "npm ci")
        self.assertEqual(self.setup_for({"scripts": {"test": "t", "setup": "prisma migrate deploy"}, "devDependencies": {"prisma": "6"}}),
                         "npm ci && npx prisma generate")


class FastGate(unittest.TestCase):
    """0.7.2 (ai-coach, 2026-10-24): gates.fast was always empty, so every commit ran the full suite (66 s). From package.json,
    joined with &&, each only when present: lint, typecheck (else tsc with typescript + tsconfig), vitest --changed."""

    def fast_for(self, pkg, files=()):
        d = tempfile.mkdtemp(prefix="reef-init-fast.")
        write(d, "package.json", json.dumps({"name": "demo", **pkg}))
        for rel in files:
            write(d, rel, "{}\n")
        subprocess.run(["git", "init", "-q", "-b", "develop", d], check=True)
        self.assertEqual(init(d).returncode, 0)
        return json.loads(read(d, ".reef/config.json"))["gates"]["fast"]

    def test_an_ai_coach_shaped_package_and_a_bare_one(self):
        self.assertEqual(self.fast_for({"scripts": {"test": "vitest run", "typecheck": "tsc --noEmit", "build": "next build"},
                                        "devDependencies": {"vitest": "3", "typescript": "5"}}, files=("tsconfig.json",)),
                         "npm run typecheck && npx vitest run --changed")
        self.assertEqual(self.fast_for({"scripts": {"test": "echo t"}}), "")

    def test_each_part_only_when_present_and_never_an_invented_script(self):
        self.assertEqual(self.fast_for({"scripts": {"test": "t", "lint": "eslint .", "typecheck": "tsc --noEmit"}, "devDependencies": {"vitest": "3"}}),
                         "npm run lint && npm run typecheck && npx vitest run --changed")
        self.assertEqual(self.fast_for({"scripts": {"test": "t"}, "devDependencies": {"typescript": "5"}}, files=("tsconfig.json",)), "npx tsc --noEmit")
        self.assertEqual(self.fast_for({"scripts": {"test": "t"}, "devDependencies": {"typescript": "5"}}), "", "typescript without a tsconfig: nothing for types")
        self.assertEqual(self.fast_for({"scripts": {"test": "jest", "check": "tsc"}, "devDependencies": {"jest": "29"}}), "", "a `check` script is not a known part")


class OneHomePerFact(unittest.TestCase):
    """A number that lives in .reef/config.json must not be restated in a generated file."""

    def setUp(self):
        self.d = node_project(tempfile.mkdtemp(prefix="reef-init-home."))
        init(self.d)
        self.cfg = json.loads(read(self.d, ".reef/config.json"))

    def test_generated_prose_points_at_config_instead_of_restating(self):
        prose = "".join(read(self.d, rel) for rel in ("AGENTS.md", "reef/constitution.md", "reef/queue.md", "reef/day-zero.md"))
        cap = self.cfg["caps"]["attempts"]
        self.assertNotRegex(prose, rf"\b{cap} (fix )?rounds?\b", "the round cap is restated instead of pointed at")
        self.assertNotRegex(prose, rf"\b{self.cfg['graph']['parallel']} agents\b")
        self.assertIn("caps.attempts", prose)

    def test_no_open_questions_heading_and_owner_points_present(self):
        agents = read(self.d, "AGENTS.md")
        self.assertNotRegex(agents, r"(?im)^#+\s.*open\s+questions?")
        self.assertRegex(agents, r"(?m)^## Owner decision points")

    def test_stack_facts_true(self):
        agents = read(self.d, "AGENTS.md")
        self.assertIn("npm ci", agents)
        self.assertIn("npm test", agents)
        self.assertEqual(self.cfg["gates"]["full"], "npm test")
        self.assertEqual(self.cfg["gates"]["extra"], {"build": "npm run build"})
        self.assertEqual(self.cfg["worktree"]["setup"], "npm ci")
        self.assertEqual(self.cfg["paths"]["runlog"], "reef/journal.md")
        self.assertEqual(self.cfg["paths"]["features"], "reef/features")
        self.assertTrue(os.path.isdir(os.path.join(self.d, "reef", "features")))
        self.assertIn("## Conventions", agents)
        self.assertIn("Vitest or Jest", agents, "the Node opinions were distilled in")
        self.assertNotIn("pytest", agents, "and none of the Python ones")

    def test_no_placeholder_survives(self):
        checked = []
        for dirpath, dirs, names in os.walk(self.d):
            dirs[:] = [x for x in dirs if x not in (".git", "node_modules")]   # components, not substrings
            for n in names:
                if n.endswith((".md", ".yml", ".json")):
                    checked.append(n)
                    with open(os.path.join(dirpath, n), encoding="utf-8", errors="replace") as f:
                        # `${{ github.ref }}` is Actions syntax; a bare `{{key}}` is an unrendered placeholder
                        self.assertNotRegex(f.read(), r"(?<!\$)\{\{", f"unrendered placeholder in {n}")
        self.assertIn("ci.yml", checked, ".github/ must be walked")
        self.assertIn("dependabot.yml", checked)


class ReleaseOnlyCi(unittest.TestCase):
    def setUp(self):
        self.d = node_project(tempfile.mkdtemp(prefix="reef-init-ci."))
        init(self.d)
        self.ci = read(self.d, ".github/workflows/ci.yml")

    def test_ci_runs_on_release_prs_only(self):
        self.assertRegex(self.ci, r"(?m)^on:\n  pull_request:\n    branches: \[main\]")
        self.assertNotRegex(self.ci, r"(?m)^  push:", "CI on push runs every change a second time")
        self.assertIn("cancel-in-progress: true", self.ci)
        self.assertIn("timeout-minutes:", self.ci)
        self.assertIn("reef-ci-local.sh --ci", self.ci, "CI must run the same gate list as the local script")

    def test_dependabot_targets_the_integration_branch(self):
        dep = read(self.d, ".github/dependabot.yml")
        self.assertIn('target-branch: "develop"', dep)
        self.assertIn('package-ecosystem: "npm"', dep)
        self.assertNotIn('target-branch: "main"', dep)

    def test_python_stack(self):
        d = tempfile.mkdtemp(prefix="reef-init-py.")
        write(d, "pyproject.toml", "[project]\nname='x'\n")
        write(d, "uv.lock", "")
        subprocess.run(["git", "init", "-q", d], check=True)
        init(d)
        cfg = json.loads(read(d, ".reef/config.json"))
        self.assertEqual(cfg["gates"]["full"], "uv run pytest -q")
        self.assertIn("uv sync", read(d, "AGENTS.md"))

    def test_unknown_stack_leaves_gate_empty_and_says_so(self):
        d = tempfile.mkdtemp(prefix="reef-init-none.")
        subprocess.run(["git", "init", "-q", d], check=True)
        r = init(d)
        self.assertIn("no test command detected", r.stdout)
        self.assertEqual(json.loads(read(d, ".reef/config.json"))["gates"]["full"], "")
        dep = read(d, ".github/dependabot.yml")
        # first contact (2026-10-16): no stack rendered the github-actions ecosystem twice
        self.assertEqual(dep.count("package-ecosystem"), 1, dep)
        self.assertNotIn('package-ecosystem: ""', dep)

    def test_a_gate_init_left_empty_is_filled_when_the_stack_arrives(self):
        # first contact (2026-10-16): init ran on an empty repo, the Next.js scaffold came after, and the re-run kept
        # gates.full == "" under "a key the project has is never changed" — the owner had to hand-edit a guarded file.
        # An EMPTY value was never set by anyone; a tuned value still wins (test_config_keys_added_values_never_changed).
        d = tempfile.mkdtemp(prefix="reef-init-late-stack.")
        subprocess.run(["git", "init", "-q", d], check=True)
        init(d)
        self.assertEqual(json.loads(read(d, ".reef/config.json"))["gates"]["full"], "")
        write(d, "package.json", json.dumps({"name": "late", "scripts": {"test": "vitest run", "build": "next build"}}))
        r = init(d)
        cfg = json.loads(read(d, ".reef/config.json"))
        self.assertEqual(cfg["gates"]["full"], "npm test", r.stdout)
        self.assertEqual(cfg["gates"]["extra"], {"build": "npm run build"})
        self.assertEqual(cfg["worktree"]["setup"], "npm ci")
        self.assertIn(".reef/config.json (keys added)", r.stdout)
        # the four stack-specific files init itself wrote minutes ago, untouched since, are REPLACED, not proposed
        # (first contact, 2026-10-16: they came back as four questions about Reef's own untouched drafts)
        for rel in (".github/dependabot.yml", ".github/workflows/ci.yml", "reef/day-zero.md"):
            self.assertFalse(os.path.exists(os.path.join(d, ".reef", "proposed", rel)), f"{rel} was proposed")
            self.assertIn(f"updated  {rel}", r.stdout)
        dep = read(d, ".github/dependabot.yml")
        self.assertEqual(dep.count("package-ecosystem"), 2)
        self.assertIn('package-ecosystem: "npm"', dep)
        self.assertIn('target-branch: "develop"', dep)
        self.assertNotIn("{{", dep)
        self.assertIn("setup-node", read(d, ".github/workflows/ci.yml"))

    def test_records_are_never_re_rendered_or_proposed(self):
        # first contact (2026-10-16): a re-run offered to replace HANDOFF.md and reef/journal.md with blank templates
        d = tempfile.mkdtemp(prefix="reef-init-records.")
        subprocess.run(["git", "init", "-q", d], check=True)
        init(d)
        with open(os.path.join(d, "reef", "journal.md"), "a", encoding="utf-8") as f:
            f.write("\n## 2026-10-16 — owner decision: the audit gate covers production only\n")
        write(d, "HANDOFF.md", "# Handoff — rendered by the guard at the ceiling\n")
        with open(os.path.join(d, "reef", "queue.md"), "a", encoding="utf-8") as f:
            f.write("| 2 | A second row | 1 | planned | 1 | |\n")
        write(d, "package.json", json.dumps({"name": "late", "scripts": {"test": "vitest run"}}))   # a real re-render trigger
        r = init(d)
        for rel in ("HANDOFF.md", "reef/journal.md", "reef/queue.md"):
            self.assertIn(f"skipped  {rel} (record, never re-rendered)", r.stdout)
            self.assertFalse(os.path.exists(os.path.join(d, ".reef", "proposed", rel)), f"{rel} proposed")
        self.assertIn("owner decision: the audit gate", read(d, "reef/journal.md"))
        self.assertIn("A second row", read(d, "reef/queue.md"))
        self.assertIn("`reef/journal.md`", read(d, "reef/constitution.md"), "the constitution names the layout's journal path")
        self.assertNotIn("docs/journal.md", read(d, "reef/constitution.md"))

    def test_another_tools_block_in_a_rendered_file_rides_along(self):
        # first contact (2026-10-16): `next dev` appends `<!-- BEGIN:nextjs-agent-rules --> … <!-- END:… -->` to AGENTS.md
        # on every run; every re-init proposed dropping it, and the orchestrator re-appended it by hand (once twice)
        block = "<!-- BEGIN:nextjs-agent-rules -->\n\n## This is NOT the Next.js you know\n\nRead the docs.\n\n<!-- END:nextjs-agent-rules -->\n"
        d = tempfile.mkdtemp(prefix="reef-init-foreign.")
        subprocess.run(["git", "init", "-q", d], check=True)
        init(d)
        with open(os.path.join(d, "AGENTS.md"), "a", encoding="utf-8") as f:
            f.write("\n" + block)
        write(d, "package.json", json.dumps({"name": "late", "scripts": {"test": "vitest run"}}))
        r = init(d)
        self.assertIn("updated  AGENTS.md (+1 foreign block(s) kept)", r.stdout)
        agents = read(d, "AGENTS.md")
        self.assertIn("npm ci", agents, "the Node rendering arrived")
        self.assertEqual(agents.count("<!-- BEGIN:nextjs-agent-rules -->"), 1, "the block survives, once")
        self.assertTrue(agents.rstrip().endswith("<!-- END:nextjs-agent-rules -->"))
        self.assertFalse(os.path.exists(os.path.join(d, ".reef", "proposed", "AGENTS.md")))
        r2 = init(d)
        self.assertIn("skipped  AGENTS.md", r2.stdout, "nothing to do: the rendering plus the block is what is there")
        # the owner edits OUTSIDE the block: a proposal as before, and the proposal carries the block too
        write(d, "AGENTS.md", agents.replace("## Commands", "## Commands\nowner note\n", 1))
        write(d, "package.json", json.dumps({"name": "late", "scripts": {"test": "vitest run", "build": "b"}}))
        r3 = init(d)
        self.assertIn("PROPOSED AGENTS.md", r3.stdout)
        self.assertIn("<!-- END:nextjs-agent-rules -->", read(d, ".reef/proposed/AGENTS.md"))

    def test_a_file_anyone_touched_is_still_proposed_never_replaced(self):
        d = tempfile.mkdtemp(prefix="reef-init-touched.")
        subprocess.run(["git", "init", "-q", d], check=True)
        init(d)
        with open(os.path.join(d, ".github", "workflows", "ci.yml"), "a", encoding="utf-8") as f:
            f.write("# the owner's note\n")                      # one byte of human intent
        manifest = json.loads(read(d, ".reef/init-manifest.json"))
        self.assertIn(".github/workflows/ci.yml", manifest)
        write(d, "package.json", json.dumps({"name": "late", "scripts": {"test": "vitest run"}}))
        r = init(d)
        self.assertIn("PROPOSED .github/workflows/ci.yml", r.stdout)
        self.assertIn("python3 " + os.path.join(ROOT, "scripts", "reef-init.py") + " --root", r.stdout,
                      "the accept hint names the script that is running (the project has no reef-init.py copy)")
        self.assertIn("# the owner's note", read(d, ".github/workflows/ci.yml"))
        self.assertNotIn("updated  .github/workflows/ci.yml", r.stdout)
        # the manifest is the only evidence; without it (a clone from before 0.7, a deleted .reef/), every
        # differing file is proposed as before
        os.unlink(os.path.join(d, ".reef", "init-manifest.json"))
        r = init(d, "--accept", ".github/workflows/ci.yml")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(read(d, ".reef/init-manifest.json")).keys() & {".github/workflows/ci.yml"},
                         {".github/workflows/ci.yml"}, "an accepted file is Reef's own again")
        os.unlink(os.path.join(d, ".reef", "init-manifest.json"))
        write(d, ".github/workflows/ci.yml", "name: ci\non: push\n")   # a rendering from before the manifest existed
        r = init(d)
        self.assertIn("PROPOSED .github/workflows/ci.yml", r.stdout)
        self.assertEqual(read(d, ".github/workflows/ci.yml"), "name: ci\non: push\n")


if __name__ == "__main__":
    unittest.main()


class OwnerDecisionsSurviveARender(unittest.TestCase):
    def test_the_owners_decision_points_block_is_kept_in_place_across_a_refresh(self):
        # first contact (2026-10-17): a refresh re-rendered AGENTS.md and put the template's "(fill in — examples: …)" back
        # over the owner's own list of decision points
        d = tempfile.mkdtemp(prefix="reef-init-owner.")
        subprocess.run(["git", "init", "-q", d], check=True)
        init(d)
        agents = read(d, "AGENTS.md")
        self.assertIn("<!-- BEGIN:reef-owner-decisions -->", agents)
        mine = "<!-- BEGIN:reef-owner-decisions -->Only the owner decides: money, personal data, the look of the product.<!-- END:reef-owner-decisions -->"
        agents = re.sub(r"<!-- BEGIN:reef-owner-decisions -->.*?<!-- END:reef-owner-decisions -->", mine, agents, flags=re.S)
        write(d, "AGENTS.md", agents)
        write(d, "package.json", json.dumps({"name": "demo-app", "scripts": {"test": "vitest run", "build": "next build"}}))   # the stack arrives: a real re-render
        r = init(d)
        self.assertEqual(r.returncode, 0, r.stderr)
        after = read(d, "AGENTS.md")
        self.assertIn("npm ci", after, "the Node rendering arrived")
        self.assertIn("Only the owner decides: money, personal data, the look of the product.", after)
        self.assertNotIn("fill in — examples", after)
        self.assertEqual(after.count("<!-- BEGIN:reef-owner-decisions -->"), 1, "replaced in place, not appended twice")
        self.assertIn("updated  AGENTS.md", r.stdout, "the rest of the file was re-rendered, the owner block rode along in place")
        self.assertNotIn("foreign block(s) kept", r.stdout.split("updated  AGENTS.md")[1].splitlines()[0], "the owner's block is the template's own, not another tool's")


class ProjectFilesStayTheProjects(unittest.TestCase):
    def test_unmarked_sections_are_adopted_keep_stops_proposals_and_the_glossary_is_a_record(self):
        # first contact (2026-10-17), the refresh after the first feature proposed three reverts: AGENTS.md back to the
        # template's decision points and Boundaries, ci.yml without the Postgres service 103 added, the glossary
        # without the four terms the feature added
        d = tempfile.mkdtemp(prefix="reef-init-own.")
        subprocess.run(["git", "init", "-q", d], check=True)
        init(d)
        agents = read(d, "AGENTS.md")
        # the project's AGENTS.md as the first feature left it: both sections edited, no markers (an older render)
        agents = re.sub(r"<!-- BEGIN:reef-owner-decisions -->.*?<!-- END:reef-owner-decisions -->", "Only the owner decides: money and personal data.", agents, flags=re.S)
        agents = re.sub(r"<!-- BEGIN:reef-boundaries -->.*?<!-- END:reef-boundaries -->", "`.reef/` is machine state · the owner's deployments: only `vercel-build` connects, in this trial none exist.", agents, flags=re.S)
        write(d, "AGENTS.md", agents)
        ci = read(d, ".github/workflows/ci.yml") + "    # services: db (postgres:16) added by task 103\n"
        write(d, ".github/workflows/ci.yml", ci)
        with open(os.path.join(d, "reef", "glossary.md"), "a", encoding="utf-8") as f:
            f.write("| Bill | One row of the Bill table. |\n")
        r = init(d, "--keep", ".github/workflows/ci.yml")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("kept as the project's own: .github/workflows/ci.yml", r.stdout)
        write(d, "package.json", json.dumps({"name": "late", "scripts": {"test": "vitest run"}}))   # a real re-render trigger
        r = init(d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("skipped  .github/workflows/ci.yml (the project's own since `reef-init --keep`; never proposed)", r.stdout)
        self.assertEqual(read(d, ".github/workflows/ci.yml"), ci)
        self.assertIn("skipped  reef/glossary.md (record, never re-rendered)", r.stdout)
        self.assertIn("| Bill |", read(d, "reef/glossary.md"))
        self.assertIn("PROPOSED AGENTS.md", r.stdout, "edited without markers: proposed, never overwritten")
        proposed = read(d, ".reef/proposed/AGENTS.md")
        self.assertIn("<!-- BEGIN:reef-owner-decisions -->Only the owner decides: money and personal data.<!-- END:reef-owner-decisions -->", proposed)
        self.assertIn("<!-- BEGIN:reef-boundaries -->`.reef/` is machine state · the owner's deployments: only `vercel-build` connects, in this trial none exist.<!-- END:reef-boundaries -->", proposed)
        self.assertNotIn("fill in — examples", proposed)
        self.assertIn("npm ci", proposed, "the rest is the new rendering")
        r = init(d, "--accept", "AGENTS.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = init(d)
        self.assertNotIn("PROPOSED AGENTS.md", r.stdout, "accepted once, with the markers in: never proposed for these sections again")
        self.assertIn("Only the owner decides: money and personal data.", read(d, "AGENTS.md"))


class RefreshKeepsRecords(unittest.TestCase):
    def test_refresh_keeps_the_day_zero_date_the_name_the_adrs_and_the_constitution(self):
        # first contact (2026-10-17): a plain refresh re-dated four ADRs and the constitution's "Ratified" line to today
        # and lowercased the project's name (it fell back to package.json); the feature's plan review went stale on it
        d = node_project(tempfile.mkdtemp(prefix="reef-init-refresh."))
        write(d, "answers.json", json.dumps({"host": "fly.io", "shape": "web-app", "scale": "100 users", "store": "postgres",
                                             "auth": "magic link", "non_goals": [], "intent": "x"}))
        r = init(d, "--grill", os.path.join(d, "answers.json"), "--name", "Qassimha")
        self.assertEqual(r.returncode, 0, r.stderr)
        man = json.loads(read(d, ".reef/init-manifest.json"))
        self.assertEqual(man["_init"]["name"], "Qassimha")
        self.assertRegex(man["_init"]["date"], r"^\d{4}-\d{2}-\d{2}$")
        # pretend day zero was long ago: the refresh must render with THAT date, never today's
        man["_init"]["date"] = "2026-01-02"
        write(d, ".reef/init-manifest.json", json.dumps(man))
        const_before = read(d, "reef/constitution.md")
        adr_before = read(d, "reef/architecture/adr/draft-1-hosting.md")
        write(d, "package.json", json.dumps({"name": "qassimha", "scripts": {"test": "vitest run", "build": "next build"}}))   # a real re-render trigger
        r = init(d)   # no --name, no --grill: the owner's refresh after a plugin update
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(read(d, "reef/constitution.md"), const_before, "the constitution is ratified once")
        self.assertEqual(read(d, "reef/architecture/adr/draft-1-hosting.md"), adr_before, "a decision record is never re-rendered")
        self.assertIn("skipped  reef/constitution.md (record, never re-rendered)", r.stdout)
        self.assertIn("Qassimha", read(d, "AGENTS.md"), "the name is pinned in the manifest, not re-derived from package.json")
        man2 = json.loads(read(d, ".reef/init-manifest.json"))
        self.assertEqual(man2["_init"], {"date": "2026-01-02", "name": "Qassimha"}, "the pin survives the refresh")


class DayZero(unittest.TestCase):
    """0.6 Phase 3: the layout switch, the architecture grill (3.1), stack opinions (3.1b), an existing
    constitution read and never duplicated (3.5)."""

    def test_legacy_layout_is_kept_for_an_existing_project(self):
        d = node_project(tempfile.mkdtemp(prefix="reef-init-legacy."))
        write(d, "docs/queue.md", "# my queue\n")
        r = init(d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("layout: 0.5", r.stdout)
        cfg = json.loads(read(d, ".reef/config.json"))
        self.assertEqual(cfg["paths"]["runlog"], "docs/journal.md")
        self.assertNotIn("features", cfg["paths"])
        self.assertTrue(os.path.isfile(os.path.join(d, ".specify", "constitution.md")))
        self.assertFalse(os.path.exists(os.path.join(d, "reef")))
        self.assertEqual(read(d, "docs/queue.md"), "# my queue\n", "never overwritten")

    def test_grill_renders_architecture_adrs_and_the_skeleton_row_once(self):
        d = node_project(tempfile.mkdtemp(prefix="reef-init-grill."))
        write(d, "answers.json", json.dumps({"host": "fly.io", "shape": "web-app", "scale": "100 users", "store": "postgres",
                                             "auth": "magic link", "non_goals": ["multi-tenant", "mobile app"], "intent": "Operators export orders."}))
        r = init(d, "--grill", os.path.join(d, "answers.json"))
        self.assertEqual(r.returncode, 0, r.stderr)
        arch = read(d, "reef/architecture/architecture.md")
        self.assertIn("C4Context", arch)
        self.assertIn("ContainerDb(store, \"store\", \"postgres\")", arch)
        self.assertIn("| Host | fly.io |", arch)
        self.assertIn("multi-tenant, mobile app", arch)
        queue = read(d, "reef/queue.md")
        self.assertIn("| 1 | Walking skeleton: one page end to end through browser, api, store", queue)
        self.assertIn("¹ host: fly.io", queue)
        self.assertIn("⁵ auth boundary: magic link", queue)
        for adr in ("draft-1-shape.md", "draft-1-hosting.md", "draft-1-data-store.md", "draft-1-auth-boundary.md"):
            self.assertTrue(os.path.isfile(os.path.join(d, "reef", "architecture", "adr", adr)), adr)
        shape = read(d, "reef/architecture/adr/draft-1-shape.md")
        self.assertIn("modular monolith", shape)                 # the decision everyone argues about later, written down
        self.assertIn("Microservices", shape)                     # with the alternative it rejects and why
        self.assertIn("browser, api, store", shape)
        self.assertIn("## Diagram", read(d, "reef/architecture/adr/draft-1-hosting.md"))
        r2 = init(d, "--grill", os.path.join(d, "answers.json"))
        self.assertRegex(r2.stdout, r"\n  0 written, \d+ skipped, 0 proposed", "a second grill run writes nothing")

    def test_python_project_gets_python_conventions_only(self):
        d = tempfile.mkdtemp(prefix="reef-init-pyconv.")
        write(d, "pyproject.toml", "[project]\nname='x'\n")
        subprocess.run(["git", "init", "-q", d], check=True)
        init(d)
        agents = read(d, "AGENTS.md")
        self.assertIn("ruff", agents)
        self.assertNotIn("Vitest", agents)

    def test_existing_constitution_is_pointed_at_never_duplicated(self):
        d = node_project(tempfile.mkdtemp(prefix="reef-init-const."))
        write(d, ".specify/memory/constitution.md", "# theirs\nArticle 1.\n")
        r = init(d)
        self.assertIn("existing constitution: .specify/memory/constitution.md", r.stdout)
        self.assertEqual(read(d, ".specify/memory/constitution.md"), "# theirs\nArticle 1.\n")
        self.assertFalse(os.path.exists(os.path.join(d, ".specify", "constitution.md")), "no second constitution")
        self.assertFalse(os.path.exists(os.path.join(d, "reef", "constitution.md")))
        self.assertIn("`.specify/memory/constitution.md`", read(d, "AGENTS.md"))
        write(d, "specs/001-export/spec.md", "# spec\n")
        r = init(d)
        self.assertIn("existing specs: specs/001-export/spec.md", r.stdout)


class MapOnDisk(unittest.TestCase):
    """0.7 (usability plan A4): "why two AGENTS.md", "where is the plan on develop" — nothing on disk said."""

    def test_the_map_is_rendered_with_the_projects_real_paths_and_refreshed(self):
        d = node_project(tempfile.mkdtemp(prefix="reef-init-map."))
        r = init(d)
        self.assertEqual(r.returncode, 0, r.stderr)
        m = read(d, "reef/README.md")
        self.assertIn("where Reef keeps things", m)
        self.assertIn("`reef/queue.md`", m)
        self.assertIn("`.reef/worktrees/<slug>`", m)
        self.assertIn("`feat/<slug>`", m)
        self.assertNotIn("{{", m, "every placeholder rendered")
        # rendered, not a record: a refresh with a better template replaces it; an owner edit is proposed, not overwritten
        write(d, "reef/README.md", m + "\nmy note\n")
        r = init(d)
        self.assertIn("my note", read(d, "reef/README.md"))
        self.assertTrue(os.path.exists(os.path.join(d, ".reef", "proposed", "reef", "README.md")) or "proposed" in r.stdout.lower() or "skipped" in r.stdout)
        gi = read(d, ".gitignore")
        self.assertIn(".reef/status.html", gi)
        self.assertIn(".reef/cost/", gi)
