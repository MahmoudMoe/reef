"""Contract suite: the settings and rules that live in PROSE (skill text, agent text,
templates) cannot drift away silently. These tests do not prove an orchestrator obeys the
prose — the README's enforcement map says which rules are prose — they prove the prose
and the shipped defaults still say what the code and the config expect."""
import glob
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class Version(unittest.TestCase):
    def test_one_version_everywhere(self):
        plugin = json.loads(read(".claude-plugin", "plugin.json"))["version"]
        market = json.loads(read(".claude-plugin", "marketplace.json"))
        badge = re.search(r"badge/version-([0-9.]+)-", read("README.md")).group(1)
        versions = {plugin, market["metadata"]["version"], market["plugins"][0]["version"], badge}
        # pinned on purpose: a version bump edits this line too, in the same commit
        self.assertEqual(versions, {"0.7.2"})


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
        self.assertEqual(open(os.path.join(d, ".reef", "version")).read().strip(), "0.7.2", "0.6.0 -> 0.7.0 -> 0.7.1 -> 0.7.2, no gap")


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
        self.assertIn("reef-pentest", read("commands", "pentest.md"))
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
        for p in (("skills", "reef-loop", "SKILL.md"), ("templates", "project", "AGENTS.md"), ("README.md",), ("commands", "review.md"), ("docs", "manual", "ar", "index.html")):
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
    edits that file in the same diff, with its reason in the CHANGELOG — the raise is a reviewed line, never silent."""

    @staticmethod
    def measure():
        def n(d):
            return sum(n(v) if isinstance(v, dict) and v else 1 for v in d.values())
        keys = n(json.loads(read("templates", "config.json")))
        words = sum(len(open(f, encoding="utf-8").read().split()) for f in glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md")) + glob.glob(os.path.join(ROOT, "agents", "*.md")))
        lines = sum(len(open(f, encoding="utf-8", errors="ignore").read().splitlines()) for f in glob.glob(os.path.join(ROOT, "scripts", "reef-*")))
        return {"config_keys": keys, "prose_words": words, "script_lines": lines}

    def test_reef_does_not_grow_without_a_reviewed_raise(self):
        budget = json.loads(read("tests", "size-budget.json"))
        now = self.measure()
        print(f"\nsize: config_keys {now['config_keys']}/{budget['config_keys']} · prose_words {now['prose_words']}/{budget['prose_words']} · "
              f"script_lines {now['script_lines']}/{budget['script_lines']}")
        over = {k: (now[k], budget[k]) for k in budget if now[k] > budget[k]}
        self.assertEqual(over, {}, "Reef grew past tests/size-budget.json — cut something, or raise the number in that file in this "
                                   "PR with the reason in the CHANGELOG")


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
        self.assertIn("reef-night", read("commands", "night.md"))


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
        self.assertIn("sh scripts/reef-gate.sh full", text)
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
            self.assertRegex(text, r"(?i)none.{0,40}run `sh scripts/reef-gate.sh full` once", "/".join(path))
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
        self.assertTrue(profiles, "docs/perf/guard-profile-<date>.md is missing — run scripts/reef-guard-profile.py")
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
        row = read("scripts", "reef-row.py")
        self.assertIn('reef-approval.py --owner', row)
        self.assertIn("the rollup: tasks/R<NN>-", row)
        self.assertIn('"reef"', read("scripts", "reef-init.py"), "the entry point is copied to projects")
        for v in ("status", "doctor", "run", "night", "watch", "stop", "setup", "update", "factory", "cost"):
            self.assertIn(f'("{v}",', read("scripts", "reef"))
        self.assertIn("`reef --all`", read("README.md"))
        self.assertIn("<code>reef --all</code>", read("docs", "manual", "ar", "index.html"))
        self.assertIn("`reef run`", read("skills", "reef-run", "SKILL.md"))

