"""Hardening PR-7 (docs/design/hardening-pr7-plan.md): the PR-4 walls (docs/design/hardening-pr4-guard-audit.md section 4)
as Claude Code config. reef-init writes them into the project's .claude/settings.json, merged and never clobbered; the
deny patterns block their DENY forms and none of the guard's ALLOW table; the doctor names a project without them. The
guard keeps every check (defense in depth): nothing here touches it."""
import ast
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import write  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INIT = os.path.join(ROOT, "scripts", "reef-init.py")
DOCTOR = os.path.join(ROOT, "scripts", "reef-doctor.py")
SETTINGS = ".claude/settings.json"

# PR-4 section 7, as this PR ships it (section 3 of the PR-7 plan: two patterns narrowed so the guard's ALLOW table passes)
EDIT_WALLS = ["Edit(~/.claude/plugins/**)",                                   # W1: the guard's trust root
              "Edit(/.claude/settings.json)",                                 # W2: the walls' own file
              "Edit(/.git/hooks/**)",                                         # W3
              "Edit(/.githooks/**)",                                          # W4 (D2 = yes)
              "Edit(/.reef/approvals/**)", "Edit(/.reef/review/**)", "Edit(/.reef/night/**)", "Edit(/.reef/evidence/**)",
              "Edit(/.reef/run/jobs/**)", "Edit(/.reef/graph/gate.json)", "Edit(/HANDOFF.md)"]   # W5
DENY_WRITE = ["~/.claude/plugins", "./.claude/settings.json", "./.git/hooks"]   # W1-W3, sandbox prefixes (`./` = project root)


def init(root, *args):
    return subprocess.run([sys.executable, INIT, "--root", root, "--verbose", *args], capture_output=True, text=True)


def project(pkg=None, pyproject=False):
    d = tempfile.mkdtemp(prefix="reef-walls.")
    if pyproject:
        write(d, "pyproject.toml", "[project]\nname = 'demo'\n")
    else:
        write(d, "package.json", json.dumps(pkg or {"name": "demo", "scripts": {"test": "echo t"}}))
    subprocess.run(["git", "init", "-q", "-b", "develop", d], check=True)
    return d


def raw(d, mode="r"):
    with open(os.path.join(d, SETTINGS), mode) as f:
        return f.read()


def settings(d):
    with open(os.path.join(d, SETTINGS), encoding="utf-8") as f:
        return json.load(f)


class InitWritesTheWalls(unittest.TestCase):
    def test_a_fresh_project_gets_every_wall_and_the_fail_closed_sandbox(self):
        d = project()
        r = init(d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(d, SETTINGS)), "init writes .claude/settings.json:\n" + r.stdout)
        s = settings(d)
        deny = s["permissions"]["deny"]
        for rule in EDIT_WALLS:
            self.assertIn(rule, deny)
        for rule in ("Bash(git commit --no-verify *)", "Bash(git commit * --no-verify)", "Bash(git commit -n *)",
                     "Bash(git merge --no-verify *)", "Bash(git push --no-verify *)", "Bash(git -c core.hooksPath*)",
                     "Bash(git config --unset core.hooksPath*)", "Bash(git stash)", "Bash(git stash pop*)",
                     "Bash(gh pr merge * --repo *)", "Bash(*reef-run.py _job-run*)", "Bash(*reef-approval.py --owner*)"):
            self.assertIn(rule, deny)
        sb = s["sandbox"]
        self.assertIs(sb["enabled"], True)
        self.assertIs(sb["failIfUnavailable"], True, "the owner's fail-closed key")
        self.assertIs(sb["allowUnsandboxedCommands"], False, "the default is true: false is what stops the unsandboxed retry")
        self.assertEqual(sorted(sb["filesystem"]["denyWrite"]), sorted(DENY_WRITE))
        hosts = sb["network"]["allowedDomains"]
        for h in ("github.com", "api.github.com", "registry.npmjs.org"):
            self.assertIn(h, hosts)
        self.assertNotIn("pypi.org", hosts, "a node project gets npm's registry, not PyPI's")
        self.assertIn(f"written  {SETTINGS}", r.stdout)

    def test_the_hosts_follow_the_stack_and_each_one_is_documented(self):
        d = project(pyproject=True)
        self.assertEqual(init(d).returncode, 0)
        hosts = settings(d)["sandbox"]["network"]["allowedDomains"]
        for h in ("github.com", "api.github.com", "pypi.org", "files.pythonhosted.org"):
            self.assertIn(h, hosts)
        self.assertNotIn("registry.npmjs.org", hosts)
        prisma = project({"name": "p", "scripts": {"test": "echo t"}, "dependencies": {"@prisma/client": "6"}})
        self.assertEqual(init(prisma).returncode, 0)
        self.assertIn("binaries.prisma.sh", settings(prisma)["sandbox"]["network"]["allowedDomains"], "prisma generate fetches its engines")
        with open(os.path.join(ROOT, "templates", "claude-settings.json"), encoding="utf-8") as f:
            tpl = json.load(f)
        for host, h in tpl["hosts"].items():
            self.assertTrue(str(h.get("why") or "").strip(), f"{host}: every allowed host says why (D1)")
            self.assertNotIn("*", host, f"{host}: an exact host, never a wildcard")

    def test_a_second_init_writes_nothing(self):
        d = project()
        init(d)
        before = raw(d, "rb")
        r = init(d)
        self.assertIn(f"skipped  {SETTINGS}", r.stdout)
        self.assertEqual(raw(d, "rb"), before)

    def test_an_existing_settings_file_keeps_every_key_and_value_and_gains_only_what_it_lacked(self):
        d = project()
        own = {"permissions": {"allow": ["Bash(npm test *)"], "deny": ["Read(./.env)", "Bash(git stash)"]},
               "sandbox": {"enabled": False, "network": {"allowedDomains": ["internal.example.com"]}},
               "model": "opus", "env": {"FOO": "1"}}
        write(d, SETTINGS, json.dumps(own, indent=2) + "\n")
        r = init(d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        s = settings(d)
        self.assertEqual(s["model"], "opus")
        self.assertEqual(s["env"], {"FOO": "1"})
        self.assertEqual(s["permissions"]["allow"], ["Bash(npm test *)"], "the project's allow list is untouched")
        self.assertEqual(s["permissions"]["deny"][:2], ["Read(./.env)", "Bash(git stash)"], "the project's rules first, in its order")
        self.assertEqual(s["permissions"]["deny"].count("Bash(git stash)"), 1, "a rule it already had is not added twice")
        for rule in EDIT_WALLS:
            self.assertIn(rule, s["permissions"]["deny"])
        self.assertIs(s["sandbox"]["enabled"], False, "a key the project already has is never changed (the doctor names it)")
        self.assertIs(s["sandbox"]["failIfUnavailable"], True, "a key it lacked is added")
        self.assertEqual(s["sandbox"]["network"]["allowedDomains"][0], "internal.example.com")
        self.assertIn("github.com", s["sandbox"]["network"]["allowedDomains"])
        self.assertIn(f"written  {SETTINGS} (walls merged", r.stdout)

    def test_an_unparseable_settings_file_is_left_byte_identical_and_named(self):
        d = project()
        write(d, SETTINGS, "{ not json\n")
        r = init(d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(raw(d), "{ not json\n")
        self.assertIn(f"PROPOSED {SETTINGS}", r.stdout)
        self.assertIn("does not parse", r.stdout)

    def test_a_dry_run_writes_no_settings(self):
        d = project()
        r = init(d, "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(d, SETTINGS)))

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root writes through a read-only mode; CI runs as a user")
    def test_a_settings_file_init_cannot_write_becomes_a_proposal_with_the_merge(self):
        # the sandbox protects .claude settings files from sandboxed commands: a re-init run as a Bash call gets EPERM
        d = project()
        write(d, SETTINGS, json.dumps({"model": "opus"}) + "\n")
        os.chmod(os.path.join(d, SETTINGS), stat.S_IRUSR)
        try:
            r = init(d)
        finally:
            os.chmod(os.path.join(d, SETTINGS), stat.S_IRUSR | stat.S_IWUSR)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(settings(d), {"model": "opus"})
        self.assertIn(f"PROPOSED {SETTINGS}", r.stdout)
        a = init(d, "--accept", SETTINGS)
        self.assertEqual(a.returncode, 0, a.stdout + a.stderr)
        s = settings(d)
        self.assertEqual(s["model"], "opus", "the accepted proposal is the merge: the project's keys ride along")
        self.assertIs(s["sandbox"]["failIfUnavailable"], True)


# ---------------------------------------------------------------- T2: the patterns, against the guard's own tables

def guard_tables():
    """DENY_BASH and ALLOW_BASH from tests/test_guard.py, read as data (no import: the suite has fixtures of its own)."""
    with open(os.path.join(ROOT, "tests", "test_guard.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ("DENY_BASH", "ALLOW_BASH"):
            out[node.targets[0].id] = ast.literal_eval(node.value)
    return out["DENY_BASH"], out["ALLOW_BASH"]


def subcommands(cmd):
    """The command split where Claude Code splits it (permissions docs: `&&`, `||`, `;`, `|`, `|&`, `&` and newlines),
    outside quotes, each stripped of a subshell's parentheses. A heredoc's body is data, not commands (a shell parse, as the
    docs' "aware of shell operators" implies; the model's one assumption the real harness is not asked about here)."""
    head = re.compile(r"<<(-?)\s*(['\"]?)(\w+)\2[^\n]*\n")
    m = head.search(cmd)
    while m:
        end = re.compile(r"(?m)^" + (r"\t*" if m.group(1) else "") + re.escape(m.group(3)) + r"$").search(cmd, m.end())
        cmd = cmd[:m.end()] + (cmd[end.end():] if end else "")
        m = head.search(cmd, m.end())
    out, cur, q, i = [], "", None, 0
    while i < len(cmd):
        c = cmd[i]
        if q:
            cur += c
            if c == q:
                q = None
            elif c == "\\" and q == '"' and i + 1 < len(cmd):
                cur += cmd[i + 1]; i += 1
        elif c in "'\"":
            q, cur = c, cur + c
        elif c == "\\" and i + 1 < len(cmd):
            cur += " " if cmd[i + 1] == "\n" else c + cmd[i + 1]; i += 1
        elif cmd.startswith(("&&", "||", "|&"), i):
            out.append(cur); cur = ""; i += 1
        elif c in ";|&\n":
            out.append(cur); cur = ""
        else:
            cur += c
        i += 1
    out.append(cur)
    return [re.sub(r"\s+", " ", s.strip().strip("()").strip()) for s in out if s.strip().strip("()").strip()]


def rule_regex(pattern):
    """A Bash rule as the docs define it: `*` stands for any text, spaces included; everything before the first `*` is
    matched as written; a trailing ` *` also matches the bare command."""
    tail = pattern.endswith(" *")
    body = pattern[:-2] if tail else pattern
    rx = ".*".join(re.escape(p) for p in body.split("*"))
    return re.compile(rx + ("( .*)?" if tail else ""), re.S)


def denied_by(cmd, rules):
    """The rules that block `cmd`: any subcommand matching, as written or past its leading assignments (a deny rule
    "matches past any leading assignment"). Both readings of a quoted word are tried, the text as written and the words a
    shell parse yields: the docs do not say which the harness matches, so the stricter union is the model."""
    hits = []
    for s in subcommands(cmd) + [s.replace('"', "").replace("'", "") for s in subcommands(cmd)]:   # as written, and as the parsed words
        bare = re.sub(r"^(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)+", "", s)
        hits += [r for r in rules if rule_regex(r).fullmatch(s) or rule_regex(r).fullmatch(bare)]
    return hits


def bash_rules():
    with open(os.path.join(ROOT, "templates", "claude-settings.json"), encoding="utf-8") as f:
        deny = json.load(f)["settings"]["permissions"]["deny"]
    return [r[len("Bash("):-1] for r in deny if r.startswith("Bash(")]


class ThePatternsMatchTheDocs(unittest.TestCase):
    # the DENY forms the config claims (PR-4 W7/W8); every other DENY form is the guard's alone, and stays there
    CLAIMED = ['git commit -m "x" --no-verify', 'git commit -n -m "x"', 'git -c core.hooksPath=/dev/null commit -m "x"',
               'git config core.hooksPath /dev/null', 'git -c core.hookspath=/dev/null commit -m x',
               'git config --global core.hooksPath /dev/null', 'git config --unset core.hooksPath',
               'cd /tmp && git commit -n -m x', 'git merge --no-verify feature', 'git commit -m "x" --no-verify || true',
               'git commit -m x\ngit commit -n -m y', 'git --config-env core.hooksPath=EVIL commit -m x',
               'git --config-env=core.hooksPath=EVIL commit -m x', '(git commit -n -m x)', 'git commit -m x \\\n--no-verify',
               'git stash', 'git stash push -m wip', 'git stash pop', 'git stash apply stash@{0}', 'cd .reef/worktrees/3 && git stash']
    # stated costs, never surprises: D3 (a message that ENDS in --no-verify) and PR-4 B5 (push's long form is always denied)
    ACCEPTED = {'git commit -m "x --no-verify"', 'git push --no-verify'}

    def test_every_claimed_deny_form_is_blocked(self):
        rules = bash_rules()
        deny, _ = guard_tables()
        for cmd in self.CLAIMED:
            self.assertIn(cmd, deny, f"a claimed form is one of the guard's own DENY cases: {cmd!r}")
            self.assertTrue(denied_by(cmd, rules), f"the config claims {cmd!r} and no rule blocks it")
        for cmd in ('gh pr merge 7 --repo o/r --squash', 'python3 scripts/reef-run.py _job-run x', 'python3 scripts/reef-approval.py --owner 3',
                    'git commit -a --no-verify -m x', 'git commit -a -n -m x'):
            self.assertTrue(denied_by(cmd, rules), f"W7/W8 claims {cmd!r}")

    def test_no_allow_case_is_blocked_except_the_accepted_ones(self):
        rules = bash_rules()
        _, allow = guard_tables()
        for cmd in allow:
            if cmd in self.ACCEPTED:
                continue
            self.assertEqual(sorted(set(denied_by(cmd, rules))), [], f"the config would block the guard's ALLOW case {cmd!r}")
        for cmd in self.ACCEPTED:
            self.assertTrue(denied_by(cmd, rules), f"an accepted false positive is pinned, so its cost stays stated: {cmd!r}")


# ---------------------------------------------------------------- the doctor

def reef_project():
    d = tempfile.mkdtemp(prefix="reef-walls-doctor.")
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    write(d, ".reef/config.json", json.dumps({"branches": {"base": "main"}, "paths": {"queue": "reef/queue.md"}}))
    return d


def doctor(d):
    env = dict(os.environ, PATH="/nonexistent-gh:" + os.environ["PATH"])
    return subprocess.run([sys.executable, DOCTOR, "--repo", d, "--plugin", ROOT], capture_output=True, text=True, env=env)


class TheDoctorNamesMissingWalls(unittest.TestCase):
    def test_no_settings_file_is_named_with_the_fix(self):
        r = doctor(reef_project())
        line = [l for l in r.stdout.splitlines() if " walls:" in l]
        self.assertTrue(line, r.stdout)
        self.assertRegex(line[0], r"^WARN walls: no \.claude/settings\.json")
        self.assertIn("reef-init.py --root", line[0])

    def test_the_walls_reef_init_writes_are_ok(self):
        d = reef_project()
        r0 = init(d)
        self.assertEqual(r0.returncode, 0, r0.stdout + r0.stderr)
        self.assertRegex(doctor(d).stdout, r"(?m)^OK   walls: \d+ deny rules, the sandbox on and fail-closed")

    def test_a_missing_rule_and_an_overridden_sandbox_key_are_named(self):
        d = reef_project()
        init(d)
        s = settings(d)
        s["permissions"]["deny"].remove("Edit(/.githooks/**)")
        s["sandbox"]["enabled"] = False
        write(d, SETTINGS, json.dumps(s))
        out = doctor(d).stdout
        self.assertRegex(out, r"(?m)^WARN walls: .*Edit\(/\.githooks/\*\*\)", out)
        self.assertRegex(out, r"(?m)^WARN walls: .*sandbox\.enabled", out)


if __name__ == "__main__":
    unittest.main()
