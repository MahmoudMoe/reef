"""Contract suite: the settings and rules that live in PROSE (skill text, agent text,
templates) cannot drift away silently. These tests do not prove an orchestrator obeys the
prose — the README's enforcement map says which rules are prose — they prove the prose
and the shipped defaults still say what the code and the config expect."""
import glob
import json
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()
def scripts():
    """Every script under scripts/ (the entry point included), the shared module too; never .sh/.json."""
    return [f for f in sorted(glob.glob(os.path.join(ROOT, "scripts", "reef*"))) if not f.endswith((".sh", ".json"))]


def read_file(path):
    return open(path, encoding="utf-8").read()


class Version(unittest.TestCase):
    def test_one_version_everywhere(self):
        plugin = json.loads(read(".claude-plugin", "plugin.json"))["version"]
        market = json.loads(read(".claude-plugin", "marketplace.json"))
        badge = re.search(r"badge/version-([0-9.]+)-", read("README.md")).group(1)
        versions = {plugin, market["metadata"]["version"], market["plugins"][0]["version"], badge}
        # pinned on purpose: a version bump edits this line too, in the same commit
        self.assertEqual(versions, {"0.7.3"})


class MigrateTo070(unittest.TestCase):
    def test_a_0_6_project_walks_to_0_7_with_no_gap(self):
        import subprocess
        import sys
        import tempfile
        d = tempfile.mkdtemp(prefix="reef-migrate.")
        os.makedirs(os.path.join(d, ".reef"))
        with open(os.path.join(d, ".reef", "config.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(d, ".reef", "version"), "w") as f:
            f.write("0.6.0\n")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-migrate"), "--repo", d, "--plugin", ROOT],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(open(os.path.join(d, ".reef", "version")).read().strip(), "0.7.3", "0.6.0 -> 0.7.0 -> 0.7.1 -> 0.7.2 -> 0.7.3, no gap")


class ConfigTemplate(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads(read("templates", "config.json"))

    def test_defaults_preserve_computed_merge_and_ci(self):
        # changed on purpose for v3 phase 4 (2026-10-26): merge.by is no longer pinned to human in the template; its default
        # is computed (loop under ci.feature_gate ci on a two-branch project, else human) — see FinishBeforeStarting
        self.assertNotIn("merge", self.cfg)
        self.assertEqual(self.cfg["ci"]["feature_gate"], "ci")
        self.assertEqual(self.cfg["branches"], {"base": "main", "release": "main"})

    def test_fast_and_full_gates(self):
        self.assertIn("fast", self.cfg["gates"])
        self.assertIn("full", self.cfg["gates"])

    def test_model_per_role_defaults_match_agent_frontmatter(self):
        roles = self.cfg["roles"]
        for role, agent in (("author", "implementer"), ("verifier", "verifier"),
                            ("plan_reviewer", "plan-reviewer"), ("mechanic", "mechanic"), ("security", "security"), ("proxy", "mahmoud")):
            front = re.search(r"^model:\s*(\S+)", read("agents", f"{agent}.md"), re.M).group(1)
            self.assertEqual(roles[role], front, f"roles.{role} default must equal the agent's frontmatter")


    def test_mahmoud_runs_on_opus_at_high_effort(self):
        # 2026-11-01, the owner: fable has usage limits for now; the proxy runs on opus (Opus 5.5) at high effort
        front = read("agents", "mahmoud.md")
        self.assertEqual(re.search(r"^model:\s*(\S+)", front, re.M).group(1), "opus")
        self.assertRegex(front, r"(?m)^effort:\s*high$")
        self.assertEqual(self.cfg["roles"]["proxy"], "opus")

class SecurityPassIsReefs(unittest.TestCase):
    """0.7 (2026-10-19): the release's security pass named `code-security`, an agent that lived in the author's own
    ~/.claude/agents and nowhere in Reef; for anyone else the step did nothing and nothing recorded that it ran."""

    def test_the_agent_ships_read_only_with_the_terse_rule_and_the_loop_records_it(self):
        text = read("agents", "security.md")
        tools = re.search(r"^tools:\s*(.+)$", text, re.M).group(1)
        self.assertNotRegex(tools, r"\b(Edit|Write|MultiEdit|NotebookEdit)\b", "the auditor is read-only")
        self.assertIn("**Terse (0.7, the owner's rule).**", text)
        self.assertIn("VERDICT: PASS | FAIL", text)
        loop = read("skills", "reef-loop", "SKILL.md")
        self.assertIn("reef:security", loop)
        self.assertIn("scripts/reef-record security", loop)
        self.assertNotIn("code-security", loop, "the release step names Reef's own agent, not one from a personal folder")
        guard = read("scripts", "reef-guard.py")
        self.assertRegex(guard, r'"security":\s*"security"', "ROLE_OF routes reef:security to roles.security")
        self.assertRegex(guard, r'LOCKED_TYPES = \([^)]*"security"', "the judge lock covers it")


class PentestOnDemand(unittest.TestCase):
    """0.7 (the owner, 2026-10-19): the hunter's pass=system — the live attack — was described in its own definition and
    the README as "once per release", and no step dispatched it. It is now a standalone command the owner runs at will."""

    def test_the_skill_drives_the_live_attack_from_the_threat_model_inside_the_owners_target(self):
        text = read("skills", "reef-pentest", "SKILL.md")
        for needle in ("pass=system", "reef/architecture/threat-model.md", "reef-threat.py lint", "roles.adversary",
                       "the owner named", "production", "--source found", ".reef/hunt/pentest-"):
            self.assertIn(needle, text, needle)
        self.assertNotIn("REEF-TASK: <", text, "the live attack is not a task's judge")
        self.assertNotIn("once per release", read("agents", "loophole-hunter.md"), "no step runs it per release")


class PlatformsSaidPlainly(unittest.TestCase):
    def test_the_readme_the_site_and_the_manual_say_macos_linux_or_wsl2(self):
        # 0.7 (2026-10-20): native Windows cannot run the guard; every page a new user reads says so, in the requirements
        self.assertIn("**macOS or Linux. On Windows, run Claude Code inside WSL2.**", read("README.md"))
        self.assertIn("macOS or Linux. On Windows, run Claude Code inside WSL2.", read("docs", "index.html"))
        self.assertIn("WSL2", read("docs", "manual", "ar", "index.html"))


class GateLineIsComputed(unittest.TestCase):
    def test_the_plan_gate_shows_the_scripts_summary_beside_the_exact_question(self):
        text = read("skills", "reef-plan", "SKILL.md")
        self.assertIn("`Approve plan <slug> at <digest16>?`", text, "the question the hook records stays exact")
        self.assertIn("--summary --feature <slug>", text)
        self.assertIn("`--summary` line VERBATIM", text)


class DocsForTwoHosts(unittest.TestCase):
    """0.7 (the owner, 2026-10-21: instructions for Claude Code and OpenCode): host facts have one home, the README's
    `## Hosts` table; the site fetches it; the Arabic manual links it; the ledger says which rules carry to another
    host. OpenCode's status names what is proven: the adapter live, no feature built on it yet (2026-10-23)."""

    def table(self, heading):
        md = read("README.md")
        part = md.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]
        return [[c.strip() for c in l.strip().strip("|").split("|")] for l in part.splitlines() if l.startswith("|") and "|---" not in l]

    def test_the_hosts_table_names_both_hosts_and_opencode_is_planned(self):
        rows = self.table("Hosts")
        self.assertEqual(rows[0], ["", "Claude Code", "OpenCode"])
        status = dict((r[0], r[1:]) for r in rows[1:])["Status"]
        self.assertEqual(status, ["supported", "early: built and verified live; no feature built on it yet"], "OpenCode's status says what is and is not proven")

    def test_every_ledger_row_says_which_host_enforces_it(self):
        md = read("README.md")
        ledger = md.split("| Rule | Enforced by | Host | Layer |", 1)[1].split("</details>", 1)[0]
        rows = [l for l in ledger.splitlines() if l.startswith("| ")]
        self.assertGreaterEqual(len(rows), 40)
        hosts = {}
        for r in rows:
            host = r.rstrip().rstrip("|").rsplit(" | ", 2)[-2].strip()
            self.assertIn(host, ("portable", "Claude Code"), r[:80])
            hosts[r[2:40]] = host
        for rule in ("The missing dispatch", "Plan approval is the HUMAN's", "Context ceiling:", "Session start under"):
            self.assertEqual(next(h for k, h in hosts.items() if k.startswith(rule)), "Claude Code", rule)

    def test_the_site_fetches_the_hosts_table_and_the_manual_links_it(self):
        self.assertIn("hosts: 'Hosts'", read("docs", "assets", "site.js"))
        site = read("docs", "index.html")
        self.assertIn('id="hosts-table"', site)
        self.assertIn('<a href="#hosts">Hosts</a>', site)
        self.assertIn("https://github.com/MahmoudMoe/reef#hosts", site, "the fallback when the fetch fails")
        ar = read("docs", "manual", "ar", "index.html")
        self.assertIn("https://github.com/MahmoudMoe/reef#hosts", ar)
        self.assertIn("OpenCode", ar)


class BulletsNotParagraphs(unittest.TestCase):
    """0.7 (the owner, 2026-10-21: "the planning, spec, queue write-up is too big"): every agent that writes English,
    the orchestrator's AGENTS.md and the plan templates ask for bullets, fragments fine, grammar optional; the
    structured lines the scripts parse stay exact."""

    def test_every_writing_agent_the_orchestrator_and_the_templates_ask_for_bullets(self):
        for name in ("implementer", "verifier", "loophole-hunter", "plan-reviewer", "planner", "security", "mahmoud"):
            text = read("agents", f"{name}.md")
            self.assertIn("**Bullets, not paragraphs (0.7, the owner's rule).**", text, name)
            self.assertIn("`RUN:`, `RULE AC<n>`, `VERDICT`, Proof rows, frontmatter", text, name)
        self.assertIn("is bullets, not paragraphs", read("templates", "project", "AGENTS.md"))
        self.assertIn("only the owner's words in a footnote stay as written", read("templates", "project", "AGENTS.md"))
        for t in ("spec.md", "task.md"):
            text = read("templates", t)
            self.assertIn("<bullets:", text, t)
            self.assertNotIn("one paragraph", text, t)
            self.assertNotIn("two or three sentences", text, t)


class NightLooks(unittest.TestCase):
    """2026-10-23 (qassimha): every night kept the preview look for the owner (AGENTS.md: "the look of his own product"),
    so a row blocked on a look waited all night. The owner: Mahmoud may approve a preview look by default, logged, undoable."""

    def test_a_preview_look_is_delegated_by_default_and_logged_as_mahmouds_footnote(self):
        skill = read("skills", "reef-night", "SKILL.md")
        self.assertIn("A preview look is delegated by default", skill)
        self.assertIn("only a footnote or a profile line keeping a named look", skill)
        agent = read("agents", "mahmoud.md")
        self.assertIn("A design look is yours at night by default", agent)
        self.assertIn("writes it as your footnote (the owner undoes it by editing that footnote)", agent)
        self.assertIn("anything the owner has explicitly kept for themselves in a footnote", agent, "a named keep still holds")

    def test_the_contract_names_every_ready_row_found_ones_too(self):
        skill = read("skills", "reef-night", "SKILL.md")
        self.assertIn("by default every ready row of the current batch, planned and found (`python3 scripts/reef-queue.py ready --with-found`", skill)
        self.assertIn("at night the tick drives these rows and no others", skill)


class NightStartsItself(unittest.TestCase):
    def test_reef_night_starts_the_detached_runner_and_hands_over(self):
        # 2026-10-24, the owner: "why don't I have /reef-night instead of a manual thing in the terminal?"
        skill = read("skills", "reef-night", "SKILL.md")
        self.assertIn("run `python3 scripts/reef-run.py --night --detach` yourself", skill)
        self.assertIn("`python3 scripts/reef-run.py status`", skill)
        self.assertIn("do no more loop work in this session", skill)
        self.assertNotIn("(in a terminal, in the project; `--max-iterations 2`", skill, "no manual terminal step")


class NightDocs(unittest.TestCase):
    """2026-10-24: the README, the site and the Arabic manual still told the owner to start the night by hand in a terminal
    after #108 made /reef-night start it; they now say how the night works."""

    def test_the_three_surfaces_say_reef_night_starts_it_and_how_to_follow_it(self):
        readme = read("README.md")
        self.assertIn("`/reef-night` starts the runner itself, detached from the session", readme)
        self.assertIn("`python3 scripts/reef-run.py status` shows it from anywhere", readme)
        self.assertIn("An approval holds 16 hours", readme)
        self.assertIn("the API-price equivalent, not a bill", readme)
        self.assertIn("preview looks — his by default", readme)
        self.assertNotIn("`/reef-night`, then `python3 scripts/reef-run.py --night`", readme)
        site = read("docs", "index.html")
        self.assertIn("it starts the runner itself, detached", site)
        self.assertNotIn("then <code>python3 scripts/reef-run.py --night</code> works while you sleep", site)
        ar = read("docs", "manual", "ar", "index.html")
        self.assertIn("python3 scripts/reef-run.py status", ar)
        self.assertIn("الموافقة صالحة 16 ساعة", ar)
        self.assertNotIn("ثم <code>python3 scripts/reef-run.py --night</code>", ar)


class HunterRoundInThePrompt(unittest.TestCase):
    def test_the_plan_skill_writes_the_round_the_guard_reads(self):
        self.assertIn("A plan-pass hunter's prompt carries `pass=plan round=<n>`", read("skills", "reef-plan", "SKILL.md"))


class AssessNeedsInit(unittest.TestCase):
    def test_the_assess_skill_stops_before_init_ran(self):
        # 0.7.2 (ai-coach, 2026-10-24): /reef-assess ran before /reef-init and called project scripts only init installs
        skill = read("skills", "reef-assess", "SKILL.md")
        self.assertIn("`test -f scripts/reef-recalibrate && test -f .reef/config.json` or STOP: \"run /reef-init first\"", skill)
        self.assertLess(skill.index("run /reef-init first"), skill.index("## 1. Understand"), "the prerequisite is step 0, before any reading")


class InitKeepsYours(unittest.TestCase):
    def test_on_an_existing_project_the_skill_recommends_the_projects_files_and_measures_before_an_accept(self):
        # 0.7.2 (ai-coach, 2026-10-24, item 8): Reef's renderings, accepted, broke 62 tests in 11 files
        skill = read("skills", "reef-init", "SKILL.md")
        self.assertIn('On an existing project the recommended answer for every proposed file is "keep yours"; before recommending an accept, '
                      "run `gates.full` with that proposal applied in a scratch worktree and report the result", skill)
        self.assertIn("When the project keeps its own ci.yml, name the missing Reef release step (`sh scripts/reef-ci-local.sh --ci --release`); "
                      "when its AGENTS.md lacks the `.reef/**` exclusions, say so.", skill)



class ProposalsUnderTheGitDir(unittest.TestCase):
    def test_every_reader_facing_text_names_the_git_dir_never_the_work_tree(self):
        # 0.7.3 (ai-coach, 2026-10-25): a project test that walks the disk counted Reef's .reef/proposed/ files as its own;
        # the proposals moved under <git dir>/reef/, and every text that tells a reader where to look says so
        for parts in (("skills", "reef-init", "SKILL.md"), ("README.md",), ("templates", "project", "reef-README.md"),
                      ("templates", "project", "day-zero.md"), ("docs", "index.html"), ("docs", "manual", "ar", "index.html")):
            text = read(*parts)
            self.assertIn(".git/reef/proposed/", text, "/".join(parts))
            self.assertNotIn(".reef/proposed/", text.replace(".git/reef/proposed/", ""), "/".join(parts))


class AssessAdoptsInPlace(unittest.TestCase):
    def test_the_assess_skill_keeps_the_projects_documents_in_place(self):
        # 0.7.3 (the owner's rule: Reef works on any project): adoption moves no document; `plan --move` is a later row
        skill = read("skills", "reef-assess", "SKILL.md")
        self.assertIn("The project's documents stay in place (`keep`, with what `plan --move` would do); only the old process converts", skill)
        self.assertIn("Moving a document into Reef's tree is a later queue row (`plan --move`, one folder at a time, after its readers are retired", skill)
        self.assertIn("every check-family command (`check`, `check:*`, `check-*`, from any task runner)", skill)
        self.assertNotIn(".reef/proposed/", skill)

class AssessMeasures(unittest.TestCase):
    def test_the_assess_skill_counts_before_it_scores(self):
        # 0.7.2 (ai-coach, 2026-10-24, item 10): module boundaries were scored by feel; the largest files were tests and data
        skill = read("skills", "reef-assess", "SKILL.md")
        self.assertIn("Then `python3 scripts/reef-recalibrate measure` — counts, not judgments, into `reef/day-zero.md` `## Measured`", skill)
        self.assertIn("module boundaries and lint baseline read from those counts", skill)


class RefactorKind(unittest.TestCase):
    def test_the_implementer_keeps_a_refactors_tests(self):
        # 0.7.2 (ai-coach, item 15): a refactor task's behaviour-preservation proof is deterministic, the agent is told the rule
        self.assertIn("A `kind: refactor` task preserves behaviour: no assertion line of an existing test changes", read("agents", "implementer.md"))


class PlanIsMeasuredFirst(unittest.TestCase):
    def test_the_assess_skill_measures_the_plan_before_the_one_question(self):
        # 0.7.2 (ai-coach, 2026-10-24, item 16): the owner approved a plan whose cost nobody measured
        skill = read("skills", "reef-assess", "SKILL.md")
        self.assertIn("Run `python3 scripts/reef-recalibrate plan --measure` first", skill)
        # 0.7.3 (the owner, 2026-10-25): the default became "keep every document in place"
        self.assertIn("recommend the smallest plan with zero errors. Moving a document into Reef's tree is a later queue row", skill)


class AdoptionHandOff(unittest.TestCase):
    def test_the_assess_skill_hands_off_with_the_apply_line_and_never_pushes_before_it(self):
        # 0.7.2 (ai-coach, 2026-10-24, item 18): assess asked to push and merge without saying the replacement was deferred
        skill = read("skills", "reef-assess", "SKILL.md")
        self.assertIn("\"Reef's tree is complete\", or \"partial: N documents outside it — rows #a–#b, blocked by …\" — never ask to push or merge before that line", skill)
        self.assertIn("The plan refuses while the old loop has work in flight", skill)


class SecurityPerItem(unittest.TestCase):
    def test_a_design_or_critical_tasks_review_dispatches_the_security_agent(self):
        # 0.7.2 (ai-coach, 2026-10-24, item 22): the release pass alone reached the sensitive code once per release
        skill = read("skills", "reef-review", "SKILL.md")
        # v3 phase 3c: phrased by the path (a design/critical task, or a risk touch, IS the critical path)
        self.assertIn("the critical path — dispatches `reef:security` (model `roles.security`) on that feature diff before the GREEN record", skill)
        self.assertIn("`review.security_per_item: off` in `.reef/config.json` opts a project out", skill)
        with open(os.path.join(ROOT, "templates", "config.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["review"]["security_per_item"], "on", "the default is on; the project opts out")


class OneReviewer(unittest.TestCase):
    """v3 phase 3c: one fresh judge per concern — the acceptance agent is the row's ONE reviewer (the spec, the diff, every
    criterion against its named test in the evidence); the separate diff review and its key are gone; the hunter's guard
    pass and the security agent run once per feature, on the critical path."""

    def test_the_review_skill_has_one_reviewer_and_no_diff_review(self):
        skill = read("skills", "reef-review", "SKILL.md")
        self.assertNotIn("## 3. Diff review", skill)
        self.assertNotIn("diff_review", skill)
        self.assertIn("ONE reviewer", skill)
        self.assertIn("scripts/reef-tier.py path", skill)
        self.assertLessEqual(len(skill.splitlines()), 60)
        agent = read("agents", "acceptance.md")
        self.assertIn("scripts/reef-evidence.py", agent)
        self.assertIn("## Proof", agent)
        self.assertRegex(agent, r"(?i)git diff <branches\.base>\.\.\.HEAD")
        self.assertLessEqual(len(agent.splitlines()), 60)
        with open(os.path.join(ROOT, "templates", "config.json"), encoding="utf-8") as f:
            self.assertNotIn("diff_review", json.load(f)["review"], "the key is gone with the step")
        for p in (("skills", "reef-loop", "SKILL.md"), ("templates", "project", "AGENTS.md"), ("README.md",), ("skills", "reef-review", "SKILL.md"), ("docs", "manual", "ar", "index.html")):
            self.assertNotIn("diff review", read(*p), "/".join(p))
            self.assertNotIn("diff_review", read(*p), "/".join(p))
        # the review (2026-10-26): the reviewer is told the head, the base branch, and what red or pending evidence means
        self.assertIn("scripts/reef-evidence.py <PR head>", agent)
        self.assertIn("`branches.base` in `.reef/config.json`", agent)
        self.assertRegex(agent, r"(?i)red.{0,60}never re-run")
        self.assertIn("pending", agent)


class RollupNoPlanHunter(unittest.TestCase):
    def test_the_review_skill_says_a_rollup_gets_no_plan_pass(self):
        self.assertIn("A rollup gets no hunter plan pass, whatever its tier", read("skills", "reef-review", "SKILL.md"))


class SizeBudget(unittest.TestCase):
    """0.7 (the owner, 2026-10-20: "is Reef creating technical debt?"): config keys, skill and agent prose, and script lines
    grew with every fix and nothing was removed. tests/size-budget.json holds the ceiling; a PR that grows a number
    edits that file in the same diff, with its reason in the CHANGELOG — the raise is a reviewed line, never silent.
    docs/design/lightening.md step 0 (2026-10-31, the owner: "a plan to wipe duplication and keep it from coming back"): two more
    numbers ratchet the same way — `duplicate_defs`, a function name defined in more than one script (each definition past the
    first; two exemptions, both named here: the guard's own copies of helpers other scripts own — it must run when any other
    script is broken — and a script's `cmd_<verb>` subcommand handlers, one per CLI by convention, step 2), and `orphan_scripts`, a script that no
    skill, agent, hook, command, template or other script names. A new duplicate or orphan is a raise someone has to write down."""

    SCRIPT_FILES = staticmethod(lambda root: sorted(glob.glob(os.path.join(root, "scripts", "reef-*")) + glob.glob(os.path.join(root, "scripts", "reef_common.py")) + [os.path.join(root, "scripts", "reef")]))
    GUARD_OWN = {"main_checkout", "merge_by", "read_frontmatter", "feature_row", "lock_path_for", "check_single_rollup", "feature_path", "gh"}   # the guard keeps its own copies of helpers other scripts own, on purpose: it must run when any other script is broken (the critical path)

    @classmethod
    def duplicate_defs(cls, root=None):
        """{name: [files]} for every top-level function defined in more than one script (the guard's own copies excepted), and the count of definitions past the first."""
        defs = {}
        for f in cls.SCRIPT_FILES(root or ROOT):
            name = os.path.basename(f)
            for m in re.finditer(r"^def ([A-Za-z_]\w*)\(", open(f, encoding="utf-8", errors="ignore").read(), re.M):
                if m.group(1) == "main" or m.group(1).startswith("cmd_") or (name == "reef-guard.py" and m.group(1) in cls.GUARD_OWN):
                    continue   # cmd_<verb>: a script's own subcommand handlers, one per CLI by convention (lightening step 2)
                defs.setdefault(m.group(1), []).append(name)
        dup = {k: v for k, v in defs.items() if len(v) > 1}
        return dup, sum(len(v) - 1 for v in dup.values())

    @classmethod
    def orphan_scripts(cls, root=None):
        """Scripts named by no skill, agent, hook, command, template or OTHER script (a script only tests run is an orphan too — the consolidation plan's definition)."""
        root = root or ROOT
        namers = []
        for d in ("skills", "agents", "hooks", "commands", "templates"):
            namers += [f for f in glob.glob(os.path.join(root, d, "**", "*"), recursive=True) if os.path.isfile(f)]
        scripts = cls.SCRIPT_FILES(root)
        texts = {f: open(f, encoding="utf-8", errors="replace").read() for f in namers + scripts}
        out = []
        for f in scripts:
            name = os.path.basename(f)
            if name in ("reef", "reef_common.py"):
                continue   # the entry point and the shared module: named by their nature
            if not any(name in t for g, t in texts.items() if g != f):
                out.append(name)
        return sorted(out)

    @classmethod
    def measure(cls):
        def n(d):
            return sum(n(v) if isinstance(v, dict) and v else 1 for v in d.values())
        keys = n(json.loads(read("templates", "config.json")))
        words = sum(len(open(f, encoding="utf-8").read().split()) for f in glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md")) + glob.glob(os.path.join(ROOT, "agents", "*.md")))
        lines = sum(len(open(f, encoding="utf-8", errors="ignore").read().splitlines()) for f in glob.glob(os.path.join(ROOT, "scripts", "reef-*")) + glob.glob(os.path.join(ROOT, "scripts", "reef_*.py")))
        return {"config_keys": keys, "prose_words": words, "script_lines": lines, "duplicate_defs": cls.duplicate_defs()[1], "orphan_scripts": len(cls.orphan_scripts())}

    def test_reef_does_not_grow_without_a_reviewed_raise(self):
        budget = json.loads(read("tests", "size-budget.json"))
        now = self.measure()
        for k in ("duplicate_defs", "orphan_scripts"):
            self.assertIn(k, budget, f"tests/size-budget.json pins {k} too (lightening step 0)")
        print("\nsize: " + " · ".join(f"{k} {now[k]}/{budget[k]}" for k in ("config_keys", "prose_words", "script_lines", "duplicate_defs", "orphan_scripts")))
        over = {k: (now[k], budget[k]) for k in budget if now[k] > budget[k]}
        dup, _ = self.duplicate_defs()
        self.assertEqual(over, {}, "Reef grew past tests/size-budget.json — cut something, or raise the number in that file in this "
                                   "PR with the reason in the CHANGELOG" + (f"; duplicate definitions: {dup}" if "duplicate_defs" in over else "")
                                   + (f"; orphan scripts: {self.orphan_scripts()}" if "orphan_scripts" in over else ""))

    def test_the_pins_see_a_new_duplicate_and_a_new_orphan(self):
        """The measurement itself, on a planted tree: one more definition of `run` counts one; a script nothing names counts one."""
        import shutil, tempfile
        dup, count = self.duplicate_defs()
        self.assertNotIn("merge_by", dup, "the guard's own copy is the one exception, by design")
        guard = read("scripts", "reef-guard.py")
        for name in self.GUARD_OWN:
            self.assertRegex(guard, rf"(?m)^def {name}\(", f"the exception list names a helper the guard no longer defines: {name} — drop it from GUARD_OWN")
        orphans = self.orphan_scripts()
        self.assertNotIn("reef-run.py", orphans); self.assertNotIn("reef-doctor.py", orphans)
        # a planted copy of the tree with one more duplicate and one orphan: both numbers move by one
        with tempfile.TemporaryDirectory(prefix="reef-pins.") as tmp:
            for d in ("scripts", "skills", "agents", "hooks", "commands", "templates"):
                shutil.copytree(os.path.join(ROOT, d), os.path.join(tmp, d), ignore=shutil.ignore_patterns("__pycache__"))
            with open(os.path.join(tmp, "scripts", "reef-nobody.py"), "w") as f:
                f.write("def run(args):\n    pass\n")
            dup2, count2 = self.duplicate_defs(tmp); orphans2 = self.orphan_scripts(tmp)
        self.assertEqual(count2, count + 1, "one more definition of `run`")
        self.assertEqual(orphans2, orphans + ["reef-nobody.py"], "a script nothing names")

class ProseCarriesRulesNotHistory(unittest.TestCase):
    """Lightening step 5: a skill or agent states the rule; the day it was learned lives in the CHANGELOG. The CHANGELOG keeps
    0.7 and after; the releases before it live in docs/changelog-archive.md."""

    def test_no_skill_or_agent_carries_a_dated_note(self):
        for f in sorted(glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md")) + glob.glob(os.path.join(ROOT, "agents", "*.md"))):
            text = read_file(f)
            dated = re.findall(r"(?<![/\w-])20\d\d-\d\d-\d\d", text)   # a date inside a path (docs/perf/2026-10-18.md) is a pointer, not a note
            self.assertEqual(dated, [], f"{os.path.relpath(f, ROOT)}: a dated history note — the rule stays, the story goes to the CHANGELOG")

    def test_the_changelog_keeps_0_7_and_after_and_names_the_archive(self):
        log = read("CHANGELOG.md")
        versions = re.findall(r"(?m)^## (\d+)\.(\d+)\.(\d+)", log)
        self.assertTrue(versions)
        self.assertTrue(all((int(a), int(b)) >= (0, 7) for a, b, _ in versions), "a release before 0.7 belongs in docs/changelog-archive.md")
        self.assertIn("docs/changelog-archive.md", log)
        archive = read("docs", "changelog-archive.md")
        self.assertIn("## 0.6.0", archive); self.assertIn("## 0.5.0", archive)


class HandbackShapeIsTold(unittest.TestCase):
    def test_the_implementer_is_told_the_claims_list_the_check_requires(self):
        # 2026-10-20 (qassimha 301): the definition listed the hand-back's contents without the claims list; the check
        # rejected it and graph mode counted an attempt
        self.assertIn("a `Claims:` list — one line per claim, `<sentence> — true at <path>:<line>`", read("agents", "implementer.md"))
        self.assertIn("graph mode: settle counts one attempt", read("scripts", "reef-claims.py"))


class SuperReefIsHonest(unittest.TestCase):
    def test_mahmoud_is_read_only_terse_and_the_night_is_approved_once_by_its_exact_question(self):
        text = read("agents", "mahmoud.md")
        tools = re.search(r"^tools:\s*(.+)$", text, re.M).group(1)
        self.assertNotRegex(tools, r"\b(Edit|Write|MultiEdit|NotebookEdit)\b")
        self.assertIn("**Terse (0.7, the owner's rule).**", text)
        for limit in ("the release to the default branch", "secrets and credentials", "outside the contract"):
            self.assertIn(limit, text)
        skill = read("skills", "reef-night", "SKILL.md")
        self.assertIn("`Approve night <YYYY-MM-DD> at <digest16>?`", skill)
        self.assertIn("Mahmoud (proxy, night <date>)", skill, "a proxy footnote is labeled, never the owner's words")
        self.assertRegex(read("scripts", "reef-guard.py"), r'LOCKED_TYPES = \([^)]*"mahmoud"')
        self.assertIn("name: reef-night", read("skills", "reef-night", "SKILL.md"))


class ReviewSkill(unittest.TestCase):
    def setUp(self):
        self.text = read("skills", "reef-review", "SKILL.md")

    def test_honours_merge_by(self):
        self.assertIn("merge.by", self.text)
        self.assertRegex(self.text, r"release.*human|human.*release")

    def test_honours_ci_feature_gate_and_base_branch(self):
        self.assertIn("ci.feature_gate", self.text)
        self.assertIn("branches.base", self.text)
        self.assertNotIn("main...HEAD", self.text, "the diff base is the configured branch, not hard-coded main")

    def test_a_loop_merge_is_one_bare_command_the_owner_authorizes(self):
        # 2026-10-21: `cd … && gh pr merge 10 … | tail -3; gh pr view …` was refused by auto mode as self-approval;
        # a permission rule matches only a bare command, and the guard's GREEN record stays the gate
        self.assertIn("one bare command, `gh pr merge <n> --squash --delete-branch`", self.text)
        self.assertIn("`Bash(gh pr merge *)`", self.text)
        self.assertIn(".claude/settings.local.json", self.text)

    def test_one_rollup_one_cap(self):
        self.assertNotIn("--cap 5", self.text, "acceptance, diff and CI share ONE cap")
        self.assertNotRegex(self.text, r"cap 5\b")


class ScriptsOrchestrate(unittest.TestCase):
    """v3 phase 5: /reef-loop reads a row's state and next step from scripts/reef-row.py; a wait renders the handoff by
    itself and the skill no longer tells the orchestrator to write one; reef-init copies the row script."""

    def test_the_loop_skill_names_the_row_script_and_the_wait_renders_the_handoff(self):
        text = read("skills", "reef-loop", "SKILL.md")
        self.assertIn("scripts/reef-row.py", text)
        self.assertRegex(text, r"(?i)wait.{0,80}renders `HANDOFF\.md`")
        self.assertNotIn("reef-handoff --write", text, "the wait does it; nobody is told to write a handoff")
        self.assertLessEqual(len(text.splitlines()), 60)
        self.assertIn("reef-row.py", read("scripts", "reef-init.py"))


class FinishBeforeStarting(unittest.TestCase):
    """v3 phase 4: /reef-loop names the rows-in-flight cap; /reef-review's loop merge runs reef-merge-base first and the
    guard refuses a head without the base's tip or without green evidence; merge.by's default is said once, by the rule."""

    def test_the_skills_say_the_cap_the_merge_base_and_the_default(self):
        loop_text = read("skills", "reef-loop", "SKILL.md")
        self.assertIn("loop.rows_in_flight", loop_text)
        self.assertIn("scripts/reef-merge-base", loop_text)
        review = read("skills", "reef-review", "SKILL.md")
        self.assertRegex(review, r"`merge\.by` \(default: `loop` when `ci\.feature_gate` is `ci`")
        self.assertIn("scripts/reef-merge-base", review)
        with open(os.path.join(ROOT, "templates", "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertNotIn("merge", cfg, "the default is computed; the template no longer pins human")
        self.assertEqual(cfg["loop"]["rows_in_flight"], 2)


class ThePathSizesTheBuild(unittest.TestCase):
    """v3 phase 3b: /reef-task names the path; on the fast path one worktree per row, tasks in order, the commit gate per
    commit, no verifier per task, the full gate once at the end; the close commits in place."""

    def test_reef_task_has_the_fast_path(self):
        text = read("skills", "reef-task", "SKILL.md")
        self.assertIn("## The path", text)
        self.assertIn("verifier: none", text)
        self.assertRegex(text, r"(?i)one task at a time")
        self.assertIn("once per row, in `/reef-review`", text)   # the fast path's full run moved to the review (#270)
        self.assertLessEqual(len(text.splitlines()), 60)


class ThePathSizesThePlanReview(unittest.TestCase):
    """v3 phase 3a: /reef-plan runs the plan-reviewer and the hunter's plan pass on the critical path only; on the fast path
    reef-plan-check alone is the review, and the gate accepts `review: not required`."""

    def test_reef_plan_names_the_path_and_the_gate_accepts_not_required(self):
        text = read("skills", "reef-plan", "SKILL.md")
        self.assertIn("scripts/reef-tier.py path", text)
        self.assertRegex(text, r"(?i)fast.{0,120}reef-plan-check\.py.{0,40}(alone|is the review)")
        self.assertIn("review: not required", text)
        self.assertLessEqual(len(text.splitlines()), 60)


class EvidenceIsReadNotMade(unittest.TestCase):
    """v3 phase 2 retires the 0.7.1 rule "a judge runs the gate once, fresh": the evidence is now written only by the gate
    (or by CI) and the guard denies every other writer, so a judge READS it and runs the gate only when there is none."""

    def test_the_verifier_and_reef_verify_read_the_evidence_and_run_the_gate_only_when_none(self):
        for path in (("skills", "reef-verify", "SKILL.md"), ("agents", "verifier.md")):
            text = read(*path)
            self.assertIn("scripts/reef-evidence.py", text, "/".join(path))
            self.assertNotIn("REEF_GATE_NO_CACHE", text, "/".join(path) + ": the forced fresh run is retired")
            self.assertRegex(text, r"(?i)none.{0,40}run `sh scripts/reef-gate.sh fast` once", "/".join(path))   # the full suite is the row's, once (#270)
            self.assertLessEqual(len(text.splitlines()), 60, "/".join(path))


class VerifierRulesFirst(unittest.TestCase):
    def test_rule_per_criterion_before_the_diff(self):
        for path in (("skills", "reef-verify", "SKILL.md"), ("agents", "verifier.md")):
            text = read(*path)
            self.assertRegex(text, r"(?i)before (reading|you read|opening) the diff", "/".join(path))
            self.assertIn("RULE AC", text, "/".join(path))


class Lessons(unittest.TestCase):
    """0.5.0: the measured lessons that are prose live where the README says they live."""

    def test_attack_the_last_fix_first(self):
        for path in (("agents", "verifier.md"), ("agents", "loophole-hunter.md"), ("skills", "reef-verify", "SKILL.md")):
            self.assertRegex(read(*path), r"(?i)last (round's|fix round's) fix", "/".join(path))

    def test_cannot_verify_needs_the_probe(self):
        self.assertRegex(read("agents", "verifier.md"), r"(?i)cannot verify here.*probe")

    def test_after_green_only_claims(self):
        text = read("skills", "reef-review", "SKILL.md")
        self.assertIn("claims-only", text)
        self.assertRegex(text, r"(?i)never a fourth round")

    def test_a_hole_that_may_never_happen_is_noted_not_queued_except_the_safety_classes(self):
        # the owner, 2026-10-21: found rows outran their closing; "I'm worried we drop important fixes"
        text = read("agents", "loophole-hunter.md")
        self.assertIn("NOTED: <hole> — possible: <why> — worst case: <one line>", text)
        self.assertIn("NEW-ROW: <hole> — will happen, not this item's", text)
        self.assertIn("security, privacy, money or data loss, which is always a NEW-ROW however unlikely", text)
        for p in (("skills", "reef-task", "SKILL.md"), ("skills", "reef-plan", "SKILL.md"), ("skills", "reef-review", "SKILL.md"), ("agents", "mahmoud.md")):
            self.assertIn("reef-queue.py note", read(*p), p)
        # the release security pass's NEW-ROWs had no filing line: a security finding "not this release's" was dropped
        self.assertIn("each `NEW-ROW` becomes a found row, `reef-queue.py add-row --source found` — a security finding is never a note",
                      read("skills", "reef-loop", "SKILL.md"))

    def test_hunter_ranks_by_cost_and_stops(self):
        text = read("agents", "loophole-hunter.md")
        self.assertRegex(text, r"(?i)rank every hole by its real cost")
        self.assertRegex(text, r"(?i)worst case costs less than another pass.*stop")

    def test_expensive_measurements_once_per_release(self):
        text = read("templates", "project", "AGENTS.md")
        self.assertRegex(text, r"(?i)once per release, on the frozen integration branch")
        self.assertIn("by test name, never by file", text)
        self.assertRegex(text, r"(?i)names the merge that caused it")

    def test_adversary_role_matches_agent(self):
        roles = json.loads(read("templates", "config.json"))["roles"]
        front = re.search(r"^model:\s*(\S+)", read("agents", "loophole-hunter.md"), re.M).group(1)
        self.assertEqual(roles["adversary"], front)


class InitSkill(unittest.TestCase):
    def test_init_skill_runs_the_script_and_never_overwrites(self):
        text = read("skills", "reef-init", "SKILL.md")
        self.assertIn("scripts/reef-init.py", text)
        self.assertRegex(text, r"(?i)never overwrit")
        self.assertIn("--accept", text)

    def test_every_project_template_is_rendered_by_init(self):
        import ast
        src = read("scripts", "reef-init.py")
        for name in os.listdir(os.path.join(ROOT, "templates", "project")):
            self.assertIn(f"project/{name}", src, f"templates/project/{name} is not wired into reef-init.py")


class LedgerClasses(unittest.TestCase):
    """0.6 item 1.6: every script carries `# CLASS: code|tripwire`; each README ledger row classed code or
    tripwire names a script whose header carries that class; the hook timeouts match the measured profile."""

    def headers(self):
        out = {}
        for d, pat in (("scripts", "reef-"), ("templates", "pre-commit")):
            for n in os.listdir(os.path.join(ROOT, d)):
                if n.startswith(pat) and not n.endswith(".json"):   # scripts/reef-stacks.json (0.7.3) is data, not a script
                    with open(os.path.join(ROOT, d, n), encoding="utf-8") as f:
                        head = "".join(f.readline() for _ in range(3))
                    m = re.search(r"^# CLASS: ([a-z, ]+)$", head, re.M)
                    out[n] = {c.strip() for c in m.group(1).split(",")} if m else None
        return out

    def test_every_script_has_a_class_header(self):
        for name, classes in self.headers().items():
            self.assertIsNotNone(classes, f"{name}: no `# CLASS: code|tripwire` header in its first 3 lines")
            self.assertTrue(classes <= {"code", "tripwire"}, f"{name}: {classes}")

    def test_ledger_rows_name_a_script_of_their_class(self):
        headers = self.headers()
        rows = [l for l in read("README.md").splitlines() if l.startswith("|") and "|---" not in l]
        checked = 0
        for row in rows:
            cells = [c.strip() for c in row.strip("|").split("|")]
            if len(cells) < 3 or cells[0] == "Rule":
                continue
            layer = cells[-1].lower()
            cls = "code" if "code" in layer else ("tripwire" if "tripwire" in layer else None)
            if cls is None or "prose" in layer and cls == "code" and "mechanism" not in layer and "hash" not in layer:
                continue
            names = set(re.findall(r"(reef-[a-z-]+(?:\.py|\.sh)?|pre-commit)", row))
            named = {n for n in names if n in headers}
            if not named:
                continue
            self.assertTrue(any(cls in (headers[n] or set()) for n in named),
                            f"ledger row classed {cls!r} names {sorted(named)} but none carries that class: {row[:90]}")
            checked += 1
        self.assertGreaterEqual(checked, 8, "the ledger lost its script-naming rows")

    def test_hook_timeouts_match_the_profile(self):
        import glob
        profiles = sorted(glob.glob(os.path.join(ROOT, "docs", "perf", "guard-profile-*.md")))
        self.assertTrue(profiles, "docs/perf/guard-profile-<date>.md is missing — the 2026-10-16 measurement the hook timeouts rest on")
        table = {}
        for l in read("docs", "perf", os.path.basename(profiles[-1])).splitlines():
            m = re.match(r"\| `([^`]+)` \| \d+ \| \d+ \| \d+ \| (\d+) \|", l)
            if m:
                table[m.group(1)] = int(m.group(2))
        self.assertTrue(table)
        hooks = json.loads(read("hooks", "hooks.json"))["hooks"]
        for ev, entries in hooks.items():
            for e in entries:
                key = e.get("matcher", ev)
                for h in e["hooks"]:
                    if key in table:
                        self.assertGreaterEqual(h["timeout"], table[key], f"{key}: hooks.json timeout below the profile")
                    # a GUARD matcher (PreToolUse) fails closed; Stop/SessionStart/PostToolUse must never wedge the
                    # session on a hook failure, so they continue
                    self.assertEqual(h.get("onFailure"), "block" if ev == "PreToolUse" else "continue", f"{ev}/{key}")
                    self.assertIn("timeout", h, f"{ev}/{key}: every hook carries a timeout")


class LeanStart(unittest.TestCase):
    """0.6 item 6.2: a session starts under writing.session_start_tokens and reads nothing else — the generated
    AGENTS.md stays <= 80 lines and every skill's re-entry section names only the handoff head and the tick."""

    def test_rendered_agents_md_under_80_lines(self):
        import subprocess, sys, tempfile
        d = tempfile.mkdtemp(prefix="reef-agents-lines.")
        with open(os.path.join(d, "package.json"), "w") as f:
            json.dump({"name": "x", "scripts": {"test": "t"}}, f)
        subprocess.run(["git", "init", "-q", d], check=True)
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-init.py"), "--root", d], capture_output=True, text=True)
        with open(os.path.join(d, "AGENTS.md")) as f:
            n = len(f.read().splitlines())
        self.assertLessEqual(n, 80, f"AGENTS.md renders to {n} lines")

    def test_reentry_sections_name_only_the_handoff_head_and_the_tick(self):
        forbidden = ("reef-queue.py status", "reef-graph.py status", "gh pr list", "git worktree list", "journal", "constitution", "read the queue")
        for name in os.listdir(os.path.join(ROOT, "skills")):
            text = read("skills", name, "SKILL.md")
            m = re.search(r"^## Re-entry.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
            if not m:
                continue
            body = m.group(1).lower()
            self.assertTrue("tick" in body or "handoff" in body, f"{name}: re-entry names neither the tick nor the handoff")
            for f_ in forbidden:
                self.assertNotIn(f_, body.replace("never read", "").replace("nothing else is read", ""), f"{name}: re-entry reads {f_!r} at start")

    def test_no_hook_files_were_added_and_no_skill_or_agent_over_60_lines(self):
        self.assertEqual(sorted(os.listdir(os.path.join(ROOT, "hooks"))), ["hooks.json"], "decision 10: no new hook files")
        for d in ("skills", "agents"):
            for dp, dn, fn in os.walk(os.path.join(ROOT, d)):
                for f in fn:
                    if f.endswith(".md"):
                        with open(os.path.join(dp, f)) as fh:
                            n = len(fh.read().splitlines())
                        self.assertLessEqual(n, 60, f"{os.path.relpath(os.path.join(dp, f), ROOT)}: {n} lines > 60")


class Templates(unittest.TestCase):
    def test_runlog_has_no_subagent_tokens_column(self):
        self.assertNotIn("Subagent tokens", read("templates", "runlog.md"))

    def test_precommit_runs_the_fast_gate(self):
        self.assertIn("reef-gate.sh fast", read("templates", "pre-commit"))

    def test_init_gitignores_the_stamp(self):
        self.assertIn(".plan-review.json", read("skills", "reef-init", "SKILL.md"))


if __name__ == "__main__":
    unittest.main()


class RowDriver(unittest.TestCase):
    """v3 phase 5b: the graph skill names the row driver (three calls per row) and keeps the merge the orchestrator's one bare
    command; the loop skill sends a row in build to it."""

    def test_the_graph_skill_names_the_row_driver_and_the_merge_stays_the_orchestrators(self):
        text = read("skills", "reef-graph", "SKILL.md")
        self.assertIn("reef-graph-run.py row <row>", text)
        self.assertIn("closed in place by the mechanic", text)
        self.assertRegex(text, r"ROW <id> READY TO MERGE")
        self.assertIn("you run that one command bare", text)
        self.assertLessEqual(len(text.splitlines()), 60)
        loop = read("skills", "reef-loop", "SKILL.md")
        self.assertIn("reef-graph-run.py row <row>", loop)
        self.assertLessEqual(len(loop.splitlines()), 60)
        self.assertIn("def cmd_row", read("scripts", "reef-graph-run.py"))


class ProxyByDay(unittest.TestCase):
    """v3 phase 6: the loop skill sends a process or wording question to the proxy under the approved reef/proxy.md and has the
    script write his footnote; the proxy agent names the day's kinds and the WAIT; the owner's kinds are named in both."""

    def test_the_loop_skill_and_the_proxy_agent_name_the_day_contract_and_the_owners_kinds(self):
        loop = read("skills", "reef-loop", "SKILL.md")
        self.assertIn("reef-run.py contract --day", loop)
        self.assertIn("--proxy --day", loop)
        self.assertIn("Approve proxy by day at <digest16>?", loop)
        self.assertRegex(loop, r"Product, money, data, look, security and the release are never his")
        self.assertLessEqual(len(loop.splitlines()), 60)
        agent = read("agents", "mahmoud.md")
        self.assertIn("reef/proxy.md", agent)
        self.assertIn("`process`", agent); self.assertIn("`wording`", agent)
        self.assertIn("day=<date> kind=<kind>", agent)
        self.assertLessEqual(len(agent.splitlines()), 60)
        self.assertIn("def check_day_footnote", read("scripts", "reef-guard.py"))


class Factory(unittest.TestCase):
    """v3 phase 7: the run skill names the offered factory workflow, its trigger label, the approval from the issue and the
    state labels; the template exists and reef-init offers it."""

    def test_the_run_skill_and_the_template_name_the_factory(self):
        text = read("skills", "reef-run", "SKILL.md")
        for needle in ("reef-factory.yml", "reef-ready", "--from-issue", "label-state", "reef-waiting-owner", "ANTHROPIC_API_KEY"):
            self.assertIn(needle, text, needle)
        self.assertLessEqual(len(text.splitlines()), 60)
        tpl = read("templates", "project", "reef-factory.yml")
        self.assertIn("reef-ready", tpl); self.assertIn("scripts/reef-factory.py row", tpl)
        self.assertNotIn("reef-run.py probe", tpl, "the YAML runs one command; the probe is the script's step, under the suite")
        self.assertIn("reef-factory.py", read("scripts", "reef-init.py"))
        self.assertIn('"project/reef-factory.yml"', read("scripts", "reef-init.py"))


class FinishedTasksKeepStructuralChecks(unittest.TestCase):
    """2026-10-28 (the current adoption, rows 3 and 46): the v3 proof rule and the read-first checks ran on tasks under
    tasks/done/ — shipped, judged and merged under the rules of their time — and no plan in the project could be approved.
    The rule (a finished task keeps the structural checks only; --feature scopes the authoring rules) has two homes that
    must say it: the check's docstring, and the planner's skill where it runs the check."""

    def test_the_rule_is_said_where_the_planner_reads_it(self):
        self.assertIn("a finished task under `tasks/done/` keeps the structural checks only", read("skills", "reef-plan", "SKILL.md"))
        check = read("scripts", "reef-plan-check.py")
        self.assertIn("A FINISHED task (under tasks/done/ with `status: done`) keeps the structural checks only", check)
        self.assertIn("`--feature SLUG` scopes them to that feature's tasks", check)
        self.assertIn("a finished task never reopens", check)
class WorkflowV3Docs(unittest.TestCase):
    """2026-10-28: the README, the site and the Arabic manual still described the v2 pipeline (every task verified by a
    fresh judge, you merge the feature PR, nine roles) after workflow v3 phases 1–7 landed. The three surfaces carry
    the path by risk, the evidence once per commit, the one reviewer, the loop's merge, the runner's questions file and
    the offered factory — each in its own register."""

    def test_the_readme_describes_the_v3_pipeline(self):
        md = read("README.md")
        for needle in ("fast path", "critical path", "`.reef/evidence/<snapshot>.json`", "one reviewer", "the loop merges",
                       "`.reef/questions.md`", "reef-factory.yml", "reef-row.py", "Approve proxy by day at <digest16>?",
                       "`loop.rows_in_flight`", "`converge.test_cmd`"):
            self.assertIn(needle, md, needle)
        self.assertNotIn("has a fresh context\nverify every task", md, "the v2 claim: a verifier per task on every row")
        self.assertNotIn("By default you merge the feature PR", md)

    def test_the_site_describes_the_v3_pipeline(self):
        site = read("docs", "index.html")
        for needle in ("fast path", "critical path", "<code>.reef/evidence/", "one reviewer", "the loop merges",
                       "<code>.reef/questions.md</code>", "reef-factory.yml", "reef-row.py", "Approve proxy by day at &lt;digest16&gt;?"):
            self.assertIn(needle, site, needle)
        self.assertNotIn("has a fresh context verify every task", site)
        self.assertNotIn("By default you merge the feature PR yourself", site)
        self.assertNotIn("Nine roles", site)

    def test_the_arabic_manual_describes_the_v3_pipeline(self):
        ar = read("docs", "manual", "ar", "index.html")
        for needle in ("المسار السريع", "المسار الحرج", ".reef/evidence/", "reef-factory.yml", "reef-row.py",
                       "Approve proxy by day at &lt;digest16&gt;?", ".reef/questions.md", "loop.rows_in_flight", "converge.test_cmd"):
            self.assertIn(needle, ar, needle)
        self.assertNotIn("القضاة الثلاثة", ar, "v3 has one reviewer on the fast path; the judges are not three everywhere")


class SetupProvenOnce(unittest.TestCase):
    """2026-10-28 (the current adoption): a fresh row worktree had no built app, 60 tests went red for reasons unrelated to the
    row, and the orchestrator guessed a build. worktree.setup is proven once per change by scripts/reef-setup.py; the planner's
    skill says so where it starts the setup, the row machine names the proof before a build, reef-init copies the script,
    and the stack profile carries what a fresh tree needs (no project name in Reef)."""

    def test_the_proof_has_its_homes(self):
        self.assertIn("proven once per change", read("skills", "reef-plan", "SKILL.md"))
        self.assertIn("proven ONCE per change", read("scripts", "reef-setup.py"))
        self.assertIn("reef-setup.py prove", read("scripts", "reef-row.py"))
        self.assertIn("reef-setup.py", read("scripts", "reef-graph.py"))
        self.assertIn('"reef-setup.py"', read("scripts", "reef-init.py"))
        stacks = json.loads(read("scripts", "reef-stacks.json"))
        self.assertTrue(stacks["node"].get("setup"), "the node profile names what a fresh tree needs beyond install and generate")
        for entry in stacks["node"]["setup"]:
            self.assertTrue(entry.get("when_deps") and entry.get("run") and entry.get("why"))
class FactorySkill(unittest.TestCase):
    """2026-10-28 (the owner: "can tickets fire an agent on GitHub, and is there a shortcut inside Reef?"): the factory had
    no skill and the owner's four setup steps lived only in a workflow header. `/reef-factory` is the one command (status,
    a row to build, a row's state and log), the workflow takes a subscriber token or an API key, and the README, the site
    and the manual say so where their other commands live."""

    def test_the_skill_the_template_and_the_three_surfaces(self):
        skill = read("skills", "reef-factory", "SKILL.md")
        self.assertLessEqual(len(skill.splitlines()), 60)
        for needle in ("reef-init.py --accept .github/workflows/reef-factory.yml", "gh secret list", "CLAUDE_CODE_OAUTH_TOKEN",
                       "ANTHROPIC_API_KEY", "claude setup-token", "--add-label reef-ready", "gh run list --workflow reef-factory.yml",
                       "Approve plan <slug> at <digest16>?", "branches/", "REEF_TOKEN"):
            self.assertIn(needle, skill, needle)
        tpl = read("templates", "project", "reef-factory.yml")
        self.assertIn("ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}", tpl)
        self.assertIn("CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}", tpl)
        for parts in (("README.md",), ("docs", "index.html"), ("docs", "manual", "ar", "index.html")):
            text = read(*parts)
            self.assertIn("/reef-factory", text, parts)
            self.assertIn("reef-ready", text, parts)
            self.assertIn("CLAUDE_CODE_OAUTH_TOKEN", text, parts)


class EveryStopNamesItsCommand(unittest.TestCase):
    """2026-10-28 (the owner, after the first night: "so many locks and guardrails … stopping me from normal rounds"): he was
    stopped seven times, each by a message without the one command — "approve it in an interactive session" twice. A stop
    that does not name the command is a bug: no Reef text may say it, and the runner's own waits carry theirs."""

    def test_no_reef_text_sends_the_owner_to_an_interactive_session(self):
        for sub in ("scripts", "skills", "agents", "commands", "templates"):
            for dp, _, fn in os.walk(os.path.join(ROOT, sub)):
                for f in fn:
                    text = open(os.path.join(dp, f), encoding="utf-8", errors="ignore").read().lower()
                    self.assertNotIn("interactive session", text, f"{os.path.join(dp, f)} sends the owner to 'an interactive session' instead of naming the command")

    def test_the_runner_and_the_row_name_the_terminal_command(self):
        run_py = read("scripts", "reef-run.py")
        self.assertIn("def owner_wait_lines", run_py)
        self.assertIn('reef-approval.py --owner', run_py)
        self.assertIn("taking over the loop held by session", run_py)
        self.assertIn("no progress — two sessions ended on the same wait", run_py)
        self.assertIn("answered when the row's state moved past it", run_py, "the runner's sessions trust the row machine over the questions file")
        row = read("scripts", "reef-row.py")
        self.assertIn('reef-approval.py --owner', row)
        self.assertIn("the rollup: tasks/R<NN>-", row)
        self.assertIn('"reef"', read("scripts", "reef-init.py"), "the entry point is copied to projects")
        for v in ("status", "doctor", "run", "night", "autopilot", "watch", "stop", "setup", "update", "factory", "cost"):
            self.assertIn(f'("{v}",', read("scripts", "reef"))
        self.assertIn("`reef --all`", read("README.md"))
        self.assertIn("<code>reef --all</code>", read("docs", "manual", "ar", "index.html"))
        self.assertIn("`reef run`", read("skills", "reef-run", "SKILL.md"))


class TheRunSkillStarts(unittest.TestCase):
    """2026-10-28, the owner's first round alone: /reef-run read the loop's recorded wait, decided the runner "would stop straight
    away", refused to start it, and told the owner to approve "<slug>" — a placeholder. A recorded wait is the runner's to clear
    (its first session reads the row machine); a line printed to the owner carries real values or names where they are."""

    def test_a_recorded_wait_is_no_reason_and_no_placeholder_reaches_the_owner(self):
        skill = read("skills", "reef-run", "SKILL.md")
        self.assertIn("A recorded wait in `.reef/loop.json` is not a reason to hold back", skill)
        self.assertIn("never a placeholder", skill)



class TheGateHoldsItsResourcesOnce(unittest.TestCase):
    """2026-10-28 (row 6 on the current adoption): reef-gate.sh holds `gates.resources` for its whole run, and the task skill
    and the mechanic told agents to wrap heavy suites in `reef-graph.py lock heavy` as well — the inner lock waited the
    whole timeout for its own holder and exited 75. The lock is re-entrant now, and the prose says the gate holds its own."""

    def test_the_task_skill_and_the_mechanic_say_the_gate_holds_its_resources(self):
        for p in (("skills", "reef-task", "SKILL.md"), ("agents", "mechanic.md")):
            text = read(*p)
            self.assertIn("the gate holds `gates.resources` itself", text, p)
            self.assertNotIn("heavy suites through `scripts/reef-graph.py lock heavy", text, p)
        self.assertIn("outside the gate", read("agents", "mechanic.md"))
        self.assertLessEqual(len(read("skills", "reef-task", "SKILL.md").splitlines()), 60)


class ImplementerNeverEditsATaskFile(unittest.TestCase):
    """2026-10-29 (row 9 on the current adoption): the implementer refreshed line numbers inside task files and every close
    moved the plan's digest. The brief says it; the guard enforces it (tests/test_guard.py TaskFilesAreThePlan)."""

    def test_the_brief_says_a_moved_line_goes_in_the_hand_back(self):
        text = read("agents", "implementer.md")
        self.assertIn("Never edit a task file", text)
        self.assertIn("voids the approval", text)
        self.assertIn("hand-back", text)
        # the security review: a ledger row per denial
        ledger = read("README.md")
        self.assertIn("An implementer never edits the plan it builds", ledger)


class OneHomePerHelper(unittest.TestCase):
    """docs/design/consolidation.md step 1 (2026-10-29): scripts/reef_common.py holds the one body of main_checkout, run, git,
    config/read_config, repo_root, process_alive and read; a script imports it beside the sys.path line and keeps at most a
    one-shape adapter (no subprocess, no open, no os.kill, no walk of its own)."""

    HELPERS = ("main_checkout", "read_config", "repo_root", "process_alive", "read", "run", "git")
    OWN_BODY = re.compile(r"subprocess\.run\(|os\.kill\(|\bopen\(|\"worktree\", \"list\"|os\.path\.dirname\(probe")

    def test_every_helper_has_one_body_and_every_import_follows_the_path_line(self):
        import ast
        common = os.path.join(ROOT, "scripts", "reef_common.py")
        self.assertTrue(os.path.isfile(common), "scripts/reef_common.py is the helpers' one home")
        src = open(common, encoding="utf-8").read()
        for h in self.HELPERS:
            self.assertRegex(src, rf"(?m)^(def {h}\(|{h} = )", f"reef_common defines {h}")
        importers = 0
        for f in sorted(glob.glob(os.path.join(ROOT, "scripts", "reef*"))):   # the entry point `reef` too (the review)
            if f.endswith((".sh", ".json")) or os.path.basename(f) == "reef_common.py":
                continue
            text = open(f, encoding="utf-8").read()
            name = os.path.basename(f)
            if "from reef_common import" in text:
                importers += 1
                at = [text.index(line) for line in ("sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))",
                                                    "sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))") if line in text]   # realpath: a record writer
                self.assertTrue(at and min(at) < text.index("from reef_common import"),
                                f"{name}: the sys.path line precedes the import (a script loaded from elsewhere, or run under -I)")
                self.assertLess(text.index("sys.dont_write_bytecode = True"), text.index("from reef_common import"),
                                f"{name}: no bytecode is written beside a project's scripts (CI, PR 215)")
            for node in ast.parse(text).body:
                if isinstance(node, ast.FunctionDef) and node.name in self.HELPERS and len(node.args.args) - len(node.args.defaults) <= 2:
                    body = ast.get_source_segment(text, node)
                    self.assertIsNone(self.OWN_BODY.search(body), f"{name}: {node.name} carries its own body — import reef_common")
        self.assertGreaterEqual(importers, 25, "the scripts that carried a copy import the module now")
        # every enumeration that keys on `scripts/reef-` knows the module too (the review): the session-start check, the
        # project measure's twin in reef-structure, CI's code-class job, the critical-tier glob
        self.assertIn('("reef-", "reef_")', read("scripts", "reef-loop.py"), "scripts_behind_plugin compares the module")
        self.assertIn("scripts/reef[-_]", read("scripts", "reef-structure"))
        self.assertIn("scripts/reef-*|scripts/reef_*", read(".github", "workflows", "ci.yml"))
        # 2026-11-01, the owner: the suite ran three times per change (local, the PR, the push to main) — the PR is the one
        # run, and a superseded run is cancelled
        ci = read(".github", "workflows", "ci.yml")
        self.assertNotIn("push:", ci.split("jobs:")[0], "the PR is the one run: no second run on the push to main")
        self.assertIn("cancel-in-progress: true", ci)
        self.assertIn('"scripts/reef_*"', read("templates", "config.json"))
        self.assertEqual(open(common, encoding="utf-8").readline().strip(), "# CLASS: code", "a change to the shared module needs a test, like every script")


class OneDefinitionInTheBigFour(unittest.TestCase):
    """docs/design/consolidation.md step 3 (2026-10-30): the loop's hold (`.reef/run/orchestrator.json`) is read by one
    function, `reef_common.read_hold`, and dropped by one, `drop_hold` — the guard, the runner, the doctor and the loop
    call them; the plan check says "finished task" and "rollup" once each; a markdown table's cells are split by one
    `table_cells`, in reef-queue.py and in every other script that read a table on its own."""

    def test_the_hold_has_one_reader(self):
        common = read("scripts", "reef_common.py")
        for h in ("def read_hold(", "def drop_hold(", "HOLD_FILE = ", "HOLD_MINUTES = ", "def table_cells("):
            self.assertIn(h, common, f"reef_common defines {h.strip('( =')}")
        homes = sorted(os.path.basename(f) for f in scripts() if "orchestrator.json" in read_file(f))
        self.assertEqual(homes, ["reef_common.py"], "the hold file's name has one home")
        minutes = sorted(os.path.basename(f) for f in scripts() if re.search(r"(?m)^HOLD_MINUTES\s*=", read_file(f)))
        self.assertEqual(minutes, ["reef_common.py"], "the stale-holder rule has one number")
        for name in ("reef-guard.py", "reef-run.py", "reef-doctor.py", "reef-loop.py"):
            imp = re.search(r"(?m)^from reef_common import (.*)$", read("scripts", name))
            self.assertIsNotNone(imp, f"{name} imports reef_common")
            self.assertRegex(imp.group(1), r"read_hold|drop_hold", f"{name} reads or drops the hold through reef_common")
        self.assertIn("write_hold", re.search(r"(?m)^from reef_common import (.*)$", read("scripts", "reef-guard.py")).group(1),
                      "the guard writes the hold through reef_common too — the record's fields have one home")

    def test_the_plan_check_says_finished_and_rollup_once(self):
        src = read("scripts", "reef-plan-check.py")
        self.assertIn("def in_done(", src)
        self.assertIn("def is_finished(", src)
        self.assertIn("def is_rollup(", src)
        code = [l for l in src.splitlines() if not l.lstrip().startswith("#")]   # a comment may quote the old spelling
        done_tests = [l for l in code if "os.path.basename(os.path.dirname(" in l and '"done"' in l]
        self.assertLessEqual(len(done_tests), 1, f"the under-done/ test is written once: {done_tests}")
        self.assertLessEqual(len([l for l in code if re.search(r"R\\d\+", l)]), 1, "the rollup name is matched once")
        by_letter = [l for l in code if "os.path.basename(" in l and 'startswith("R")' in l]
        self.assertEqual(by_letter, [], "a rollup is `is_rollup`, not a file name's first letter")

    def test_a_table_row_is_split_once(self):
        homes = sorted(os.path.basename(f) for f in scripts() if 'strip("|").split("|")' in read_file(f))
        self.assertEqual(homes, ["reef_common.py"], "one body splits a table row into cells")


class ThreeOrphansGone(unittest.TestCase):
    """docs/design/consolidation.md step 2 (2026-10-30): `reef-watch` is gone (`reef-run.py status` and `.reef/status.html`
    replaced it), `reef-guard-profile.py` is gone (its one measurement is docs/perf/guard-profile-2026-10-16.md), `reef-eval`
    lives under tests/eval/ beside its corpus — a test tool, run by tests only. The current pages say so; history keeps its words."""

    def test_the_scripts_are_gone_and_the_pages_do_not_name_them(self):
        for name in ("reef-watch", "reef-guard-profile.py", "reef-eval"):
            self.assertFalse(os.path.exists(os.path.join(ROOT, "scripts", name)), f"scripts/{name} is an orphan of the plan")
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "tests", "eval", "reef-eval")), "reef-eval is a test tool now")
        self.assertFalse(os.path.exists(os.path.join(ROOT, "tests", "test_watch.py")))
        pages = [os.path.join(ROOT, *p) for p in (("README.md",), ("docs", "index.html"), ("docs", "manual", "ar", "index.html"), ("docs", "design", "site-information-architecture.md"), ("tests", "run.sh"))]
        for d in ("skills", "agents", "hooks", "commands", "templates", "scripts"):   # the plan's own definition of an orphan: nothing there names it
            pages += [f for f in glob.glob(os.path.join(ROOT, d, "**", "*"), recursive=True) if os.path.isfile(f)]
        for f in pages:
            text = open(f, encoding="utf-8", errors="replace").read()
            for name in ("scripts/reef-watch", "reef-guard-profile", "scripts/reef-eval", "test_watch"):
                self.assertNotIn(name, text, f"{os.path.relpath(f, ROOT)} still names {name}")
        self.assertIn("tests/eval/reef-eval", read("README.md"))
        self.assertIn("reef-run.py status", read("README.md"))


class TheScreenIsDocumented(unittest.TestCase):
    def test_the_readme_and_the_manual_say_reef_alone_opens_the_screen_with_the_inbox(self):
        readme = read("README.md")
        self.assertIn("the inbox", readme)
        self.assertIn("`reef approve <row>`", readme)
        self.assertIn("`reef answer <row> \"<text>\"`", readme)
        self.assertIn("reef screen --once", readme)
        self.assertIn("inbox", read("docs", "manual", "ar", "index.html").lower())


class PlanReviewRoundsAreCapped(unittest.TestCase):
    def test_the_template_and_the_skill_name_the_cap(self):
        import json as _json
        cfg = _json.loads(read("templates", "config.json"))
        self.assertEqual(cfg["review"]["plan_rounds"], 2)
        self.assertIn("review.plan_rounds", read("skills", "reef-plan-review", "SKILL.md"))
        self.assertLessEqual(len(read("skills", "reef-plan-review", "SKILL.md").splitlines()), 60)

class NoLineNumbersInCriteria(unittest.TestCase):
    def test_the_plan_skill_and_the_planner_say_lines_live_in_read_first(self):
        for p in (("skills", "reef-plan", "SKILL.md"), ("agents", "planner.md")):
            self.assertIn("no `file:line` in a criterion, a decision or the scope", read(*p), p)
        self.assertLessEqual(len(read("skills", "reef-plan", "SKILL.md").splitlines()), 60)


class AutopilotIsDelegationInEveryVoice(unittest.TestCase):
    """2026-10-30: the autopilot routes plan approvals and questions to Mahmoud by day — so his brief, the loop skill and the
    README must say the kinds are the contract's `Decides:` line, not a fixed pair (the review: the brief said WAIT to every plan)."""

    def test_the_brief_the_skill_and_the_readme_name_the_autopilot(self):
        self.assertIn("autopilot", read("agents", "mahmoud.md"))
        self.assertNotIn("every plan approval are `WAIT`", read("agents", "mahmoud.md"))
        self.assertIn("reef autopilot", read("skills", "reef-loop", "SKILL.md"))
        self.assertIn("`reef autopilot` runs", read("README.md"))
        self.assertIn("--autopilot", read("README.md"))


class OneFullRunPerRow(unittest.TestCase):
    """2026-11-01, the owner's project (MahmoudMoe/reef#270): a row ran the full suite about nine times — the implementer, the
    verifier, the fast path's last task, converge, the merged head — each on a tree the last stage had changed, so the cache
    by tree never hit (31 full runs, 30 trees). Tasks run the fast gate; the full suite runs once per row, in /reef-review, on
    the head that merges (the base's tip brought in first), and the local feature gate reads that same tree's result."""

    def test_tasks_run_the_fast_gate_and_the_review_runs_the_full_suite_once_on_the_head_that_merges(self):
        impl, verifier = read("agents", "implementer.md"), read("agents", "verifier.md")
        task, verify, review = read("skills", "reef-task", "SKILL.md"), read("skills", "reef-verify", "SKILL.md"), read("skills", "reef-review", "SKILL.md")
        for name, text in (("implementer", impl), ("verifier", verifier), ("reef-task", task), ("reef-verify", verify)):
            self.assertNotIn("reef-gate.sh full", text, f"{name}: a task stage never runs the full suite")
            self.assertIn("reef-gate.sh fast", text, name)
            self.assertIn("once per row", text, f"{name} says where the full suite runs")
        self.assertIn("GATE: fast exit", verifier)
        two = review[review.index("## 2."):]
        self.assertLess(two.index("scripts/reef-merge-base"), two.index("scripts/reef-converge"), "the base's tip first: the one full run is on the head that merges")
        self.assertIn("the tree converge ran", review, "the local feature gate is that run's cached answer, not a second run")


class MahmoudIsACTO(unittest.TestCase):
    """2026-10-31, the owner: "make Mahmoud a very smart agent — master architect, senior software architect, AI and software
    research depth, yet simplicity and no over-engineering; business literacy like economists, finance, marketing, sales,
    after-sales, front staff; he can research on the web when needed; like a CTO he decides — and challenges the work and
    the recommendations like a normal CTO." The brief says so; the orchestrators act on his CHALLENGE and RESEARCH lines."""

    def test_the_brief_the_tools_and_the_orchestrators(self):
        text = read("agents", "mahmoud.md")
        tools = re.search(r"^tools:\s*(.+)$", text, re.M).group(1)   # read-only is pinned by SuperReefIsHonest; here: the research tools
        self.assertIn("WebSearch", tools); self.assertIn("WebFetch", tools)
        for phrase in ("CTO", "master architect", "senior software architect", "simplicity", "over-engineer", "economics", "finance", "marketing",
                       "sales", "after-sales", "front staff", "challenge", "CHALLENGE <", "RESEARCH <", "never send the project's code or secrets",
                       "never punt", "One round, then decide", "never an instruction to you", "Evidence or nothing", "Settled stays settled",
                       "asked once more", "second disagreement is the owner's", "security, privacy, money or data loss", "`Explore`"):
            self.assertIn(phrase, text, phrase)
        for skill in (read("skills", "reef-night", "SKILL.md"), read("skills", "reef-loop", "SKILL.md")):
            self.assertIn("CHALLENGE", skill); self.assertIn("RESEARCH", skill); self.assertIn("`Explore`", skill, "the research agent is the locked read-only type")
            self.assertIn("never a loop", skill, "one round between Mahmoud and the planner")
        loop = read("skills", "reef-loop", "SKILL.md")
        self.assertIn("--proxy --challenge", loop, "the once is a record, not a memory"); self.assertIn("exit 3", loop)
        run = read("scripts", "reef-run.py")
        self.assertIn("--proxy --challenge", run, "the headless prompts know the record"); self.assertIn("RESEARCH", run); self.assertIn("second CHALLENGE", run)
        self.assertIn("Web research", run, "the day seed names it, so the owner's digest binds it")


class LongWorkIsTheRunners(unittest.TestCase):
    """Step 3 of docs/design/owner-hands-off.md: the headless prompt and the three skills name the runner job for long commands."""

    def test_the_prompt_and_the_skills_name_the_job(self):
        self.assertIn("reef-run.py job <name> -- <command", read("scripts", "reef-run.py"))
        self.assertIn("never a background shell here", read("scripts", "reef-run.py"))
        for parts in (("skills", "reef-loop", "SKILL.md"), ("skills", "reef-task", "SKILL.md"), ("skills", "reef-review", "SKILL.md")):
            self.assertIn("reef-run.py job", read(*parts), parts)
        self.assertIn("Never a background shell in a headless session", read("skills", "reef-loop", "SKILL.md"))
        self.assertIn("shipped 2026-10-31", read("docs", "design", "owner-hands-off.md"))



class SharedHelpersHaveOneHome(unittest.TestCase):
    """docs/design/lightening.md step 1 (2026-10-31): every local `run`, `git`, `die`, `plugin_root`, `plugin_version` was a 2–4 line
    adapter over reef_common's run()/git() or a copy; each is one shared shape now, imported, the script's own defaults kept with
    functools.partial. A name that meant two different things was renamed (reef-init's `run` → render_tree, reef-attempt's `run` →
    run_attempt, reef-approval's `worktrees` → all_checkouts, reef-opencode's `frontmatter` → split_frontmatter, reef-factory's `say` →
    note); reef-merge-close's `fail` IS die with a prefix."""

    def test_no_shared_helper_is_defined_twice(self):
        dup, _ = SizeBudget.duplicate_defs()
        for name in ("run", "git", "die", "plugin_root", "plugin_version", "worktrees", "frontmatter", "say", "fail"):
            self.assertNotIn(name, dup, f"{name} is defined in {dup.get(name)} — one home: scripts/reef_common.py")
        common = read("scripts", "reef_common.py")
        for name in ("run_rc", "run_rc3", "run_out", "run_all", "git_rc", "git_out", "git_checked", "git_text", "die", "plugin_root", "plugin_version"):
            self.assertRegex(common, rf"(?m)^def {name}\(", f"reef_common defines {name}")

    def test_the_shapes_say_what_the_adapters_said(self):
        import importlib.machinery, importlib.util, io, contextlib
        loader = importlib.machinery.SourceFileLoader("reef_common_for_shapes", os.path.join(ROOT, "scripts", "reef_common.py"))
        spec = importlib.util.spec_from_loader(loader.name, loader); c = importlib.util.module_from_spec(spec); loader.exec_module(c)
        py = sys.executable
        self.assertEqual(c.run_rc([py, "-c", "print('a')"], None), (0, "a\n"))
        self.assertEqual(c.run_rc3([py, "-c", "import sys; print('a'); print('b', file=sys.stderr)"], None), (0, "a\n", "b\n"))
        self.assertEqual(c.run_out([py, "-c", "print(' a ')"], None), "a"); self.assertEqual(c.run_out([py, "-c", "raise SystemExit(3)"], None), "")
        self.assertEqual(c.run_all([py, "-c", "import sys; print('a'); print('b', file=sys.stderr)"], None), (0, "a\nb\n"))
        self.assertEqual(c.run_all([py, "-c", "print(' a ')"], None, strip=True), (0, "a"))
        self.assertEqual(c.git_rc(ROOT, "rev-parse", "--is-inside-work-tree"), (0, "true"))
        self.assertEqual(c.git_out(ROOT, "rev-parse", "--is-inside-work-tree"), "true"); self.assertEqual(c.git_out(ROOT, "no-such-verb"), "")
        self.assertEqual(c.git_text(ROOT, "rev-parse", "--is-inside-work-tree", prefix="t").strip(), "true")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            c.git_checked(ROOT, "no-such-verb", prefix="reef-x", limit=40, where=True)
        self.assertEqual(cm.exception.code, 1); self.assertRegex(err.getvalue(), r"^reef-x: git no-such-verb failed in .*: .{1,40}\n$")
        self.assertEqual(c.git_checked(ROOT, "no-such-verb", prefix="reef-x", check=False).returncode, 1 if False else c.git(ROOT, "no-such-verb").returncode)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            c.die("no", 3, prefix="reef-y")
        self.assertEqual((cm.exception.code, err.getvalue()), (3, "reef-y: no\n"))
        self.assertEqual(c.plugin_root(ROOT), ROOT); self.assertIsNone(c.plugin_root(os.path.join(ROOT, "docs")) if not os.environ.get("CLAUDE_PLUGIN_ROOT") and not os.path.isfile(os.path.join(ROOT, ".claude-plugin", "plugin.json")) else None)
        self.assertEqual(c.plugin_version(ROOT), json.loads(read(".claude-plugin", "plugin.json"))["version"]); self.assertEqual(c.plugin_version("/nowhere"), "?")


class TheSameNameInTwoScripts(unittest.TestCase):
    """docs/design/lightening.md step 2 (2026-10-31): after step 1, thirty definitions still shared a name across scripts. A true
    duplicate merged into reef_common (`load_sibling` for the three `plan_check_module` loaders and reef-graph-run's `load_script`,
    `git_root` for the two `root_of`, `reef_dir`, `section`, `slug_error` with its SLUG_RE and GENERIC_SLUGS, `served_dirs`,
    `config_homes`); a false one — two things under one name — was renamed so a reader stops confusing them (reef-row's
    `queue_rows` → queue_status, reef-run's `release_hold` → drop_session_hold, reef-loop's `render` → render_status_page,
    reef-init's `render`/`detect` → render_template/detect_stack, reef-handoff's `render` → render_handoff, reef-recalibrate's
    `render_plan` → render_moves, reef-plan-check's `parse_args` → parse_check_args, reef-threat's `lint` → lint_threat,
    reef-factory's and reef-graph-run's `script` → own_script/project_script, reef-record's `gh` → gh_text, reef-repo's `gh` →
    gh_rc3). A script's own `cmd_<verb>` handlers are one per CLI by convention and the pin does not count them."""

    def test_no_name_is_defined_in_two_scripts(self):
        dup, count = SizeBudget.duplicate_defs()
        self.assertEqual(dup, {}, f"{count} definition(s) past the first: {dup}")
        common = read("scripts", "reef_common.py")
        for name in ("load_sibling", "git_root", "reef_dir", "section", "slug_error", "served_dirs", "config_homes"):
            self.assertRegex(common, rf"(?m)^def {name}\(", f"reef_common defines {name}")
        self.assertRegex(common, r"(?m)^SLUG_RE = "); self.assertRegex(common, r"(?m)^GENERIC_SLUGS = ")

    def test_the_merged_helpers_say_what_the_copies_said(self):
        import importlib.machinery, importlib.util, tempfile
        loader = importlib.machinery.SourceFileLoader("reef_common_for_step2", os.path.join(ROOT, "scripts", "reef_common.py"))
        spec = importlib.util.spec_from_loader(loader.name, loader); c = importlib.util.module_from_spec(spec); loader.exec_module(c)
        self.assertEqual(c.git_root(os.path.join(ROOT, "docs")), ROOT, "the repository's top level from inside it")
        with tempfile.TemporaryDirectory(prefix="reef-step2.") as tmp:
            self.assertEqual(c.git_root(tmp), os.path.abspath(tmp), "outside a repository: the directory itself")
            self.assertEqual(c.reef_dir(tmp), os.path.join(tmp, ".reef"))
            self.assertEqual(c.served_dirs(tmp), set())
            with open(os.path.join(tmp, "mkdocs.yml"), "w") as f:
                f.write("docs_dir: site\n")
            self.assertIn("site", c.served_dirs(tmp))
            with open(os.path.join(tmp, "conf.py"), "w") as f:
                f.write("project = 'x'\n")
            self.assertNotIn("", c.served_dirs(tmp), "a Sphinx conf.py at the root names no directory")
        self.assertTrue(c.reef_dir(ROOT).endswith("reef") and ".git" in c.reef_dir(ROOT), "inside: under the git common dir")
        self.assertEqual(c.section("# t\n\n## A\nalpha\n\n## B\nbeta\n", "A"), "\nalpha\n\n"); self.assertIsNone(c.section("## A\nx\n", "Z"))
        self.assertIsNone(c.slug_error("csv-export-for-orders"))
        self.assertIn("is not 2-5 kebab-case words", c.slug_error("Csv"))
        self.assertIn("is a number or a generic word", c.slug_error("misc-stuff"))
        self.assertEqual(c.config_homes({"paths": {"adr": "docs/adr/", "queue": "reef/queue.md", "other": "x"}}), ["docs/adr", "reef/queue.md"])
        m = c.load_sibling("reef-tier.py")
        self.assertTrue(hasattr(m, "main"), "a sibling script loaded as a module")


class OneFixtureModule(unittest.TestCase):
    """docs/design/lightening.md step 3 (2026-10-31): `write(root, rel, text)` was defined in fifteen test files, a `git(d, *a)` helper
    in fifteen (four shapes: the CompletedProcess, checked or not; its stdout; its stdout stripped), the temp-repo opening of every
    `project()` in ten. tests/_fixtures.py holds each once — and test_entry's script loader, the one that moved (the other ad-hoc
    SourceFileLoader bodies are a follow-up); a file imports the shape it used, under the name it used, so its tests read as before.
    A test file's own `project()` stays — it is that suite's world — and opens its repository through `git_repo()`."""

    NAMES = re.compile(r"^def (write|git|git_checked|git_out|git_text|git_repo|load_script|load_entry)\(", re.M)   # a fixture's name in a test file is the finding, whatever its parameters

    def test_the_fixtures_have_one_home(self):
        fx = os.path.join(ROOT, "tests", "_fixtures.py")
        self.assertTrue(os.path.isfile(fx), "tests/_fixtures.py is the fixtures' one home")
        src = open(fx, encoding="utf-8").read()
        for name in ("write", "git", "git_out", "git_text", "git_repo", "load_script"):
            self.assertRegex(src, rf"(?m)^def {name}\(", f"_fixtures defines {name}")
        copies, importers = {}, 0
        for f in sorted(glob.glob(os.path.join(ROOT, "tests", "test_*.py"))):
            text = open(f, encoding="utf-8").read()
            for m in self.NAMES.finditer(text):
                copies.setdefault(m.group(1), []).append(os.path.basename(f))
            if "from _fixtures import" in text:
                importers += 1
                self.assertLess(text.index("sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))"), text.index("from _fixtures import"),
                                f"{os.path.basename(f)}: the tests folder goes on sys.path before the import (python3 -m unittest tests.<suite> runs from the repository root)")
        self.assertEqual(copies, {}, f"a test file still carries its own copy of a fixture: {copies}")
        self.assertGreaterEqual(importers, 20, "the files that carried a copy import the module now")
        self.assertGreaterEqual(sum(open(f, encoding="utf-8").read().count("git_repo(prefix=") for f in glob.glob(os.path.join(ROOT, "tests", "test_*.py"))), 8, "the suites' project()s open their repository through repo()")

    def test_the_shapes_say_what_the_copies_said(self):
        import importlib.machinery, importlib.util, tempfile
        loader = importlib.machinery.SourceFileLoader("reef_fixtures_under_test", os.path.join(ROOT, "tests", "_fixtures.py"))
        spec = importlib.util.spec_from_loader(loader.name, loader); fx = importlib.util.module_from_spec(spec); loader.exec_module(fx)
        with tempfile.TemporaryDirectory(prefix="reef-fx.") as tmp:
            p = fx.write(tmp, "a/b/c.md", "x\n")
            self.assertEqual((p, open(p).read()), (os.path.join(tmp, "a/b/c.md"), "x\n"), "write makes the folders and returns the path")
            d = fx.git_repo(prefix="reef-fx-repo.", branch="develop", config={"gates": {"full": "true"}})
            self.assertEqual(fx.git_text(d, "symbolic-ref", "--short", "HEAD"), "develop")
            self.assertEqual(json.load(open(os.path.join(d, ".reef", "config.json"))), {"gates": {"full": "true"}})
            fx.write(d, "f.txt", "1\n"); fx.git(d, "add", "-A"); fx.git(d, "commit", "-qm", "one")
            self.assertEqual(fx.git_out(d, "log", "--format=%s"), "one\n", "git_out: stdout as git printed it")
            self.assertEqual(fx.git(d, "status", "--porcelain").returncode, 0, "git: the CompletedProcess")
            self.assertEqual(fx.git(d, "no-such-verb").returncode, 1, "not checked by default")
            with self.assertRaises(subprocess.CalledProcessError):
                fx.git(d, "no-such-verb", check=True)
            m = fx.load_script("reef-tier.py")
            self.assertTrue(hasattr(m, "main"))


class NoAliasLayer(unittest.TestCase):
    """docs/design/lightening.md step 4 (2026-10-31, the owner: "/reef-plan and /reef:plan — that is duplication too"; his call: delete).
    `commands/` held fifteen three-line files that each invoked a skill, so every verb showed twice in Claude Code's menu; every
    document, prompt and the runner name `/reef-<verb>`, which is the skill. The folder keeps the one real command — `reef.md`, the
    overview, which has no skill — and the OpenCode host writes its command stubs from the skills. `orphan_scripts` was already 0:
    nothing else to remove."""

    def test_the_aliases_are_gone_and_no_text_names_one(self):
        self.assertEqual(sorted(os.listdir(os.path.join(ROOT, "commands"))), ["reef.md"], "the overview alone")
        self.assertIn("Reef overview", read("commands", "reef.md"))
        pages = [os.path.join(ROOT, "README.md")] + [f for d in ("skills", "agents", "templates", "scripts", "hooks") for f in glob.glob(os.path.join(ROOT, d, "**", "*"), recursive=True) if os.path.isfile(f)]
        pages += [os.path.join(ROOT, "docs", "index.html"), os.path.join(ROOT, "docs", "manual", "ar", "index.html")]
        for f in pages:
            text = open(f, encoding="utf-8", errors="replace").read()
            self.assertNotRegex(text, r"(?<![\w/.])/reef:[a-z]", f"{os.path.relpath(f, ROOT)} names a /reef:<verb> alias — the skill is /reef-<verb>")   # a path like .opencode/agents/reef:x is not one
        self.assertIn("Invoke the {skill} skill", read("scripts", "reef-opencode.py"), "the OpenCode command stubs are written from the skills, one per SKILL.md")
        self.assertEqual(SizeBudget.orphan_scripts(), [], "nothing else to remove")


class The16HexFallbackLastsOneRelease(unittest.TestCase):
    """0.7.4: an approval or review record binds the plan's full digest; one written before carries only `digest16`
    and is read at 16 hex for that release only. Past 0.7.4 this goes red until the fallback in record_binds is gone."""

    def test_the_fallback_is_gone_after_0_7_4(self):
        version = tuple(int(x) for x in json.loads(read(".claude-plugin", "plugin.json"))["version"].split(".")[:3])
        if version <= (0, 7, 4):
            self.skipTest("0.7.4 still reads a record without `digest` at its 16 hex")
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _fixtures import load_script
        pc = load_script("reef-plan-check.py")
        self.assertFalse(pc.record_binds({"digest16": "a" * 16}, "a" * 64), "drop record_binds' 16-hex fallback (and this test)")

