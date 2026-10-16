"""Contract suite: the settings and rules that live in PROSE (skill text, agent text,
templates) cannot drift away silently. These tests do not prove an orchestrator obeys the
prose — the README's enforcement map says which rules are prose — they prove the prose
and the shipped defaults still say what the code and the config expect."""
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
        self.assertEqual(versions, {"0.5.0"})


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
                            ("plan_reviewer", "plan-reviewer"), ("mechanic", "mechanic")):
            front = re.search(r"^model:\s*(\S+)", read("agents", f"{agent}.md"), re.M).group(1)
            self.assertEqual(roles[role], front, f"roles.{role} default must equal the agent's frontmatter")


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
                    self.assertEqual(h.get("onFailure"), "block", key)


class Templates(unittest.TestCase):
    def test_runlog_has_no_subagent_tokens_column(self):
        self.assertNotIn("Subagent tokens", read("templates", "runlog.md"))

    def test_precommit_runs_the_fast_gate(self):
        self.assertIn("reef-gate.sh fast", read("templates", "pre-commit"))

    def test_init_gitignores_the_stamp(self):
        self.assertIn(".plan-review.json", read("skills", "reef-init", "SKILL.md"))


if __name__ == "__main__":
    unittest.main()
