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
        self.assertEqual(versions, {"0.6.0"})


class ConfigTemplate(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads(read("templates", "config.json"))

    def test_defaults_preserve_human_merge_and_ci(self):
        self.assertEqual(self.cfg["merge"]["by"], "human")
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

    def test_one_rollup_one_cap(self):
        self.assertNotIn("--cap 5", self.text, "acceptance, diff and CI share ONE cap")
        self.assertNotRegex(self.text, r"cap 5\b")


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
                if n.startswith(pat):
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
