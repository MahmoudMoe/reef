"""Sabotage suite for scripts/reef-guard.py.

Every DENY case here is a bypass that MUST be caught (the gate shown red), and
every ALLOW case is a legitimate command that MUST NOT be blocked (no false
positives — a guard that blocks reef-init's own install is a self-deadlock).
Zero external deps: python3 -m unittest discover tests
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, "scripts", "reef-guard.py")


def run_guard(payload):
    return subprocess.run([sys.executable, GUARD], input=json.dumps(payload),
                          capture_output=True, text=True)


def bash(cmd):
    return run_guard({"tool_name": "Bash", "tool_input": {"command": cmd}})


DENY_BASH = [
    # the colleague's original table — the exact spellings that shamed v0.2.0
    'git commit -m "x" --no-verify',
    'git commit -n -m "x"',
    'git -c core.hooksPath=/dev/null commit -m "x"',
    'git config core.hooksPath /dev/null',
    'git --no-pager commit --no-verify -m "x"',
    # bypass spellings the tokenizer must catch
    'git commit -anm "x"',                                  # bundled short flags
    'git -c core.hookspath=/dev/null commit -m x',          # case games
    'git config CORE.HOOKSPATH /tmp/nothing',
    'git config --global core.hooksPath /dev/null',
    'git config --unset core.hooksPath',
    'GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x',
    'cd /tmp && git commit -n -m x',                        # behind an operator
    'git merge --no-verify feature',
    'rm -rf .githooks',
    'mv .git/hooks/pre-commit /tmp/',
    'chmod -x .githooks/pre-commit',
    'chmod 000 .githooks',
    'git commit -m "x" --no-verify || true',
    # round-2 findings: shapes the first guard missed
    'git commit -m x\ngit commit -n -m y',                  # newline-separated second command
    'sh -c "git commit -n -m x"',                           # shell wrapper payload
    'bash -c "git commit --no-verify -m x"',
    'eval git commit -n -m x',
    'git --config-env core.hooksPath=EVIL commit -m x',     # space form of --config-env
    'git --config-env=core.hooksPath=EVIL commit -m x',     # glued form
    # round-3 findings: shapes the second guard missed
    'nohup git commit -n -m x',                             # prefix word hides the head
    'env GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x',
    'nice -n 5 git commit --no-verify -m x',
    'chmod ugo+r,ugo-x .githooks/pre-commit',               # '+' present but strips exec
    'chmod u=rw .githooks/pre-commit',                      # '=' can strip exec too
    'bash -lc "git commit -n -m x"',                        # bundled -c flag
    'git commit -m x \\\n--no-verify',                      # backslash continuation
    # round-4 findings
    'git commit -n # -m harmless-looking-comment',          # '#' must not truncate the scan
    'echo setup # a note\ngit commit --no-verify -m x',      # '#' comment must NOT swallow the next line's command
    'git commit -m "a\nb" -n',                              # newline INSIDE the message; -n is a live bypass
    '(git commit -n -m x)',                                 # subshell paren glued to git
    'true && (env X=1 git commit --no-verify -m x)',
    'chmod ugo+r,ugo-x .githooks/pre-commit',               # mixed add/remove mode
    'chmod 644 .githooks/pre-commit',                        # octal that strips exec
    # 0.5.0 — lessons measured on a 15-agent merge wave
    'git stash',                                             # one stash stack serves EVERY worktree
    'git stash push -m wip',
    'git stash pop',
    'git stash apply stash@{0}',
    'cd .reef/worktrees/3 && git stash',
    'npm test | tail -5',                                    # the pipe reports tail's exit code
    'npm test 2>&1 | tail -20',
    'sh scripts/reef-gate.sh | tail -1',
    'pytest -q | grep passed',
    'npm run ci:local | tail -1 && git commit -m x',
    'cargo test | head',
    'go test ./... |& tee log',
    'uv run pytest | tail',
    'python3 -m pytest -q | tail -3',
    'npx vitest run | tail',
    'nice -n 5 npm test | tail',
    # first contact (2026-10-16): newline-separated and heredoc-fed writes to a guarded file
    'echo x\ncp evil.py scripts/reef-guard.py',               # a bare newline separates commands — the cp is real
    "cat > scripts/reef-guard.py <<'EOF'\nx\nEOF",             # the redirect target is the guard
    "python3 - <<'EOF' > scripts/reef-guard.py\nprint(1)\nEOF",
    'python3 gen.py | tee scripts/reef-guard.py',
    'sed -i s/a/b/ scripts/reef-guard.py',
]

ALLOW_BASH = [
    'git commit -m "x"',
    'git commit -am "regular commit"',
    'git commit --amend --no-edit',                         # --amend has n but not as a short flag
    'git commit -m "docs: explain why --no-verify is forbidden"',   # value, not flag
    'git config core.hooksPath .githooks',                  # reef-init's own install
    'git config --get core.hooksPath',                      # read-only query
    'git config --list',
    'git log --oneline -n 5',                               # -n belongs to log, not commit
    'git checkout -b feat/x && git commit -m "y"',
    'echo hooksPath is documented in README.md',            # bare word in a value
    'ls -la',
    # round-2 findings: false positives the first guard would have produced
    'chmod +x .githooks/pre-commit .githooks/pre-merge-commit',   # reef-init's own install step
    'git merge -n topic',                                   # merge -n is --no-stat, not --no-verify
    'git push --no-verify',                                 # no pre-push hook exists to bypass
    'git config core.hooksPathological x',                  # not the hooksPath key
    'rm not.githooksish.txt',                               # substring, not a path component
    'git commit -m fix -- -n',                              # after -- it is a pathspec
    # round-4 findings: benign shapes the tighter rules must still allow
    'chmod +x .githooks/pre-commit run.sh',                 # pure add touching a bare filename too
    'chmod -R +x .githooks',                                # recursive pure add
    'git log # git commit -n in a comment',                 # comment after a benign git command
    '(cd sub && git status)',                               # subshell with benign git
    # round-5: a multi-line commit MESSAGE whose body merely mentions a guarded command
    # is one quoted -m value in real bash, not a command — must not false-deny
    'git commit -m "docs: never run\ngit commit --no-verify\nor rm -rf .githooks"',
    # 0.5.0 — the lesson rules must not false-deny
    'git stash list',                                        # read-only
    'git stash show -p',
    'set -o pipefail; npm test 2>&1 | tail -5',              # the exit code survives
    'npm test > out.txt 2>&1; tail -5 out.txt',              # redirect, then read
    'npm test',
    'go build ./... | tail',                                 # build is not the gate
    'echo test | grep t',
    'git log --oneline | head -5',
    'grep -rn pytest tests/ | head',                         # a gate WORD, not a gate — only the head counts
    'git log --grep pytest | head',
    # first contact (2026-10-16): the guard denied `cat > .reef/grill.json <<'EOF' … EOF` + `python3 …/reef-init.py`
    # on the next line as a write to reef-init.py — a heredoc body is data and a guarded path that is RUN is no target
    "mkdir -p .reef && cat > .reef/grill.json <<'EOF'\n{\"host\": \"Vercel\"}\nEOF\npython3 /x/reef/scripts/reef-init.py --root . --base develop",
    'python3 scripts/reef-init.py --root . > init.log',       # the redirect's target is the log, the script is run
    'python3 scripts/reef-loop.py tick; ls .reef/approvals 2>/dev/null; ls scripts',   # 2>/dev/null is no write (re-entry, 2026-10-16)
    "cat > notes.md <<'EOF'\nnever run git commit --no-verify\nEOF",   # a bypass mentioned INSIDE a heredoc body
    "cat <<-END\n\tgit commit -n -m x\n\tEND",                     # <<- form
    'echo npm test | cat',
    'rg vitest src | wc -l',
    'npm run lint | tail',                                   # not the test gate
    'go build ./... | tail',
]


class NativeWindows(unittest.TestCase):
    """0.7 (the owner, 2026-10-20): native Windows has no fcntl, SIGALRM or process groups; the guard died at its first
    import. Inside a Reef project it now stops with the one sentence that helps; anywhere else it steps aside."""

    def guard(self, cwd):
        env = dict(os.environ, REEF_TEST_NATIVE_WINDOWS="1")
        return subprocess.run([sys.executable, GUARD], input=json.dumps({"tool_name": "Bash", "cwd": cwd, "tool_input": {"command": "ls"}}),
                              capture_output=True, text=True, env=env)

    def test_stops_with_wsl2_inside_a_reef_project_and_steps_aside_elsewhere(self):
        proj = tempfile.mkdtemp(prefix="reef-win.")
        write_config(proj, {"gates": {"test": "true"}})
        sub = os.path.join(proj, "src", "deep")
        os.makedirs(sub)
        r = self.guard(sub)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("on Windows, run Claude Code inside WSL2", r.stderr)
        self.assertNotIn("Traceback", r.stderr, "no crash on the fcntl import")
        other = tempfile.mkdtemp(prefix="not-reef.")
        r = self.guard(other)
        self.assertEqual(r.returncode, 0, "a Windows user's other projects are not Reef's to block")


class GateOnAnyStack(unittest.TestCase):
    """0.7.3 (the owner's rule: Reef works on any stack, 2026-10-25): piping a gate hides its exit code. The guard knew npm,
    pytest, vitest, jest, cargo and go — and one adopted project's `npm run ci:local` by name. Now a gate is any command the
    project configured in `.reef/config.json` `gates.*` (lint and typecheck count when configured), a task runner's test,
    check, ci, verify or spec target, or a common test runner of another stack."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-gates.")
        subprocess.run(["git", "init", "-q", "-b", "main", self.d], check=True)
        write_config(self.d, {"gates": {"full": "bundle exec rspec", "fast": "pnpm lint && pnpm typecheck", "extra": {"docs": "make docs-index"}}})

    def run_in(self, cmd):
        return run_guard({"tool_name": "Bash", "cwd": self.d, "tool_input": {"command": cmd}})

    def test_the_projects_configured_gates_and_other_stacks_runners_are_gates(self):
        for cmd in ("bundle exec rspec | tail -3", "make docs-index 2>&1 | tail", "pnpm test | tail", "pnpm lint | head",
                    "pnpm typecheck | tail", "yarn test | tail", "bun run test | tail", "make test | tail", "just check | tail", "mvn test | tail", "./gradlew test | tail",
                    "dotnet test | tail", "mix test | tail", "rspec | tail", "tox -e py312 | tail", "deno test | tail",
                    "npm run check:docs | tail", "npm run ci:local | tail -1", "composer test | tail", "phpunit | tail"):
            with self.subTest(cmd=cmd):
                r = self.run_in(cmd)
                self.assertEqual(r.returncode, 2, f"NOT DENIED: {cmd!r}: {r.stderr}")
        for cmd in ("bundle exec rake routes | head", "npm run dev | tail", "make build-assets | tail", "git log | head", "yarn run lint | tail",
                    "grep rspec Gemfile | head"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.run_in(cmd).returncode, 0, f"denied a non-gate: {cmd!r}")

class PushBypass(unittest.TestCase):
    """0.7.2 (ai-coach, 2026-10-24): `git push --no-verify` skips `.githooks/pre-push` when the repository has one — ai-coach
    chained its push guard into that hook. Without the hook there is nothing to skip; `push -n` is --dry-run."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-push.")
        subprocess.run(["git", "init", "-q", "-b", "main", self.d], check=True)

    def push(self, cmd):
        return run_guard({"tool_name": "Bash", "cwd": self.d, "tool_input": {"command": cmd}})

    def test_the_long_bypass_is_refused_only_when_a_pre_push_hook_exists(self):
        self.assertEqual(self.push("git push --no-verify").returncode, 0, "no pre-push hook: nothing to skip")
        os.makedirs(os.path.join(self.d, ".githooks"))
        with open(os.path.join(self.d, ".githooks", "pre-push"), "w") as f:
            f.write("#!/bin/sh\nexit 1\n")
        r = self.push("git push --no-verify origin main")
        self.assertEqual(r.returncode, 2)
        self.assertIn(".githooks/pre-push", r.stderr)
        self.assertEqual(self.push("git push -n origin main").returncode, 0, "push -n is --dry-run, not a bypass")
        self.assertEqual(self.push("git push origin main").returncode, 0)


class BashGuard(unittest.TestCase):
    def test_denies_bypasses(self):
        for cmd in DENY_BASH:
            with self.subTest(cmd=cmd):
                r = bash(cmd)
                self.assertEqual(r.returncode, 2, f"NOT DENIED: {cmd!r}\nstderr: {r.stderr}")
                self.assertIn("reef-guard DENY", r.stderr)

    def test_allows_legitimate(self):
        for cmd in ALLOW_BASH:
            with self.subTest(cmd=cmd):
                r = bash(cmd)
                self.assertEqual(r.returncode, 0, f"FALSE POSITIVE: {cmd!r}\nstderr: {r.stderr}")

    def test_unparseable_bypass_denied_innocent_allowed(self):
        self.assertEqual(bash('git commit --no-verify -m "unbalanced').returncode, 2)
        self.assertEqual(bash('echo "unbalanced').returncode, 0)

    def test_recursion_bomb_denied_not_hung(self):
        # nested eval must terminate with a denial, never hang past the hook timeout
        payload = "eval " * 60 + "git commit -n -m x"
        r = subprocess.run([sys.executable, GUARD], input=json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": payload}}),
            capture_output=True, text=True, timeout=15)
        self.assertEqual(r.returncode, 2)

    def test_garbage_stdin_allows(self):
        r = subprocess.run([sys.executable, GUARD], input="not json", capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)


def make_task(dirpath, name="007-demo.md", status="pending", attempts=0, dispatches=0, extra=""):
    p = os.path.join(dirpath, "tasks", name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(f"---\nid: 7\nfeature: demo\nstatus: {status}\nattempts: {attempts}\n"
                f"dispatches: {dispatches}\n{extra}---\n# demo\n\n## Log\n")
    return p


def dispatch(cwd, prompt, subagent="reef:implementer", model=None):
    tool_input = {"subagent_type": subagent, "prompt": prompt}
    if model is not None:
        tool_input["model"] = model
    return run_guard({"tool_name": "Task", "cwd": cwd, "tool_input": tool_input})


def write_config(cwd, cfg):
    os.makedirs(os.path.join(cwd, ".reef"), exist_ok=True)
    with open(os.path.join(cwd, ".reef", "config.json"), "w") as f:
        json.dump(cfg, f)


class RoleModel(unittest.TestCase):
    """0.5.0: a dispatch runs on the configured model for its role — read at dispatch, not remembered."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="reef-guard-roles.")
        write_config(self.dir, {"gates": {"test": "true"}, "roles": {
            "author": "opus", "verifier": "opus", "plan_reviewer": "fable", "mechanic": "sonnet"}})
        make_task(self.dir)

    def test_implementer_on_wrong_model_denied(self):
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement", model="sonnet")
        self.assertEqual(r.returncode, 2)
        self.assertIn("roles.author", r.stderr)
        with open(os.path.join(self.dir, "tasks", "007-demo.md")) as f:
            self.assertIn("dispatches: 0", f.read())   # a denial costs nothing

    def test_implementer_without_model_denied_when_role_configured(self):
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2, "the agent file's default is not the configured model")
        self.assertIn("pass model='opus'", r.stderr)

    def test_the_security_auditor_runs_on_roles_security(self):
        write_config(self.dir, {"gates": {"test": "true"}, "roles": {"security": "opus"}})
        r = dispatch(self.dir, "Audit git diff main...develop", subagent="reef:security", model="sonnet")
        self.assertEqual(r.returncode, 2)
        self.assertIn("roles.security", r.stderr)
        self.assertEqual(dispatch(self.dir, "Audit git diff main...develop", subagent="reef:security", model="opus").returncode, 0,
                         "no REEF-TASK line is needed: the release audit is not a task's judge")

    def test_the_pentest_hunter_needs_no_task_line_but_runs_on_roles_adversary(self):
        write_config(self.dir, {"gates": {"test": "true"}, "roles": {"adversary": "opus"}})
        prompt = "pass=system\nreef/architecture/threat-model.md\nhttp://127.0.0.1:3000"
        self.assertEqual(dispatch(self.dir, prompt, subagent="reef:loophole-hunter", model="opus").returncode, 0)
        r = dispatch(self.dir, prompt, subagent="reef:loophole-hunter", model="sonnet")
        self.assertEqual(r.returncode, 2)
        self.assertIn("roles.adversary", r.stderr)

    def test_the_planner_runs_on_roles_planner(self):
        # 0.7 (2026-10-20): roles.planner was set in every config and enforced by nothing (the brief's known gap)
        write_config(self.dir, {"gates": {"test": "true"}, "roles": {"planner": "opus"}})
        r = dispatch(self.dir, "Draft the plan for row 3", subagent="reef:planner", model="sonnet")
        self.assertEqual(r.returncode, 2)
        self.assertIn("roles.planner", r.stderr)
        r = dispatch(self.dir, "Draft the plan for row 3", subagent="reef:planner")
        self.assertEqual(r.returncode, 2, "the agent file's default is not the configured model")
        self.assertIn("pass model='opus'", r.stderr)
        self.assertEqual(dispatch(self.dir, "Draft the plan for row 3", subagent="reef:planner", model="opus").returncode, 0)
        self.assertEqual(dispatch(self.dir, "Review it", subagent="reef:plan-reviewer", model="opus").returncode, 0,
                         "plan-reviewer is not matched by 'planner'")

    def test_implementer_on_configured_model_allowed(self):
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement", model="opus")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_verifier_plan_reviewer_mechanic_checked(self):
        for sub, want, wrong in (("reef:verifier", "opus", "fable"), ("reef:plan-reviewer", "fable", "opus"),
                                 ("reef:mechanic", "sonnet", "opus")):
            with self.subTest(sub=sub):
                self.assertEqual(dispatch(self.dir, "x", subagent=sub, model=wrong).returncode, 2)
                self.assertEqual(dispatch(self.dir, "x", subagent=sub, model=want).returncode, 0)

    def test_unset_role_is_not_enforced(self):
        write_config(self.dir, {"gates": {"test": "true"}, "roles": {"author": "opus"}})
        self.assertEqual(dispatch(self.dir, "x", subagent="reef:verifier", model="fable").returncode, 0)
        self.assertEqual(dispatch(self.dir, "x", subagent="reef:mechanic").returncode, 0)


class DispatchGuard(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="reef-guard-test.")

    def test_no_header_denied(self):
        r = dispatch(self.dir, "implement the thing please")
        self.assertEqual(r.returncode, 2)
        self.assertIn("REEF-TASK", r.stderr)

    def test_missing_file_denied(self):
        r = dispatch(self.dir, "REEF-TASK: tasks/999-ghost.md\nimplement")
        self.assertEqual(r.returncode, 2)

    def test_blocked_denied(self):
        make_task(self.dir, status="blocked")
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked", r.stderr)

    def test_at_cap_denied(self):
        make_task(self.dir, attempts=3)
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2)
        self.assertIn("retry cap", r.stderr)

    def test_odometer_backstop_denies_runaway(self):
        # the K4 scenario: a model that never records failures re-dispatches forever.
        # The guard itself advances dispatches:; at 2x cap it trips regardless.
        p = make_task(self.dir)
        for i in range(6):
            r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
            self.assertEqual(r.returncode, 0, f"dispatch {i+1} wrongly denied: {r.stderr}")
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2, "7th dispatch with zero recorded failures must trip the backstop")
        self.assertIn("runaway", r.stderr)
        with open(p) as f:
            self.assertIn("dispatches: 6", f.read())

    def test_odometer_written_to_frontmatter_only(self):
        p = make_task(self.dir)
        dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        text = open(p).read()
        fm = text.split("---\n")[1]
        self.assertIn("dispatches: 1", fm)

    def test_non_implementer_ignored(self):
        r = dispatch(self.dir, "anything", subagent="reef:verifier")
        self.assertEqual(r.returncode, 0)

    def test_denied_dispatch_never_bumps_odometer(self):
        p = make_task(self.dir, status="blocked", dispatches=2)
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2)
        with open(p) as f:
            self.assertIn("dispatches: 2", f.read())   # unchanged: a denial costs nothing

    def test_path_with_spaces(self):
        make_task(self.dir, name="008-two words.md")
        r = dispatch(self.dir, "REEF-TASK: tasks/008-two words.md\nimplement")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_crlf_prompt_accepted(self):
        # round-3: a CRLF prompt left '\r' glued to the path and false-denied
        make_task(self.dir)
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\r\nimplement")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_negative_dispatches_denied(self):
        # round-3: a negative odometer disabled the runaway backstop
        make_task(self.dir, dispatches=-999)
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2)
        self.assertIn("negative", r.stderr)

    def test_duplicate_status_key_first_wins(self):
        # round-3: guard read the LAST duplicate key while reef-attempt reads the FIRST
        p = make_task(self.dir, status="blocked", extra="status: pending\n")
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2, "first occurrence (blocked) must win in the guard too")

    def test_indented_key_ignored_matches_attempt(self):
        # round-4: guard accepted indented keys while reef-attempt requires column 0
        p = make_task(self.dir, status="blocked", extra=" status: pending\n")
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2, "an indented 'status: pending' must not override column-0 'blocked'")

    def test_absolute_path_accepted(self):
        # the dispatch runs from a different checkout than the task's; the cwd must be a real, writable
        # directory because 0.6 records the dispatch under <cwd>/.reef/inflight (a hardcoded /somewhere/else
        # passed only where the test ran as root and could create it)
        p = make_task(self.dir)
        elsewhere = tempfile.mkdtemp(prefix="reef-guard-elsewhere.")
        r = dispatch(elsewhere, f"REEF-TASK: {p}\nimplement")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_non_utf8_task_fails_closed(self):
        p = make_task(self.dir)
        with open(p, "ab") as f:
            f.write(b"\xff\xfe garbage")
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2, "an unreadable task file must DENY, never crash-allow")

    def _stamped_repo(self):
        """A real git repo with a full valid plan and a written stamp."""
        import shutil
        import subprocess as sp
        d = self.dir
        sp.run(["git", "init", "-q", "-b", "main", d], check=True)
        os.makedirs(os.path.join(d, "tasks", "done"), exist_ok=True)
        os.makedirs(os.path.join(d, "scripts"), exist_ok=True)
        os.makedirs(os.path.join(d, ".reef"), exist_ok=True)
        with open(os.path.join(d, ".reef", "config.json"), "w") as f:
            f.write('{"gates": {"test": "true"}}')
        with open(os.path.join(d, "CLAUDE.md"), "w") as f:
            f.write("# demo brief\n")
        with open(os.path.join(d, "tasks", "007-demo.md"), "w") as f:
            f.write("---\nid: 7\nfeature: demo\nstatus: pending\ncomplexity: mech\n"
                    "effort: medium\nblocked-by: []\nverify: gate-only\nattempts: 0\n"
                    "dispatches: 0\nlast_failure_sig: \"\"\n---\n# 7\n\n## Scope\nx\n\n"
                    "## Acceptance Criteria\n- test_demo_works goes red first\n\n## Log\n")
        shutil.copy(os.path.join(ROOT, "scripts", "reef-plan-check.py"),
                    os.path.join(d, "scripts", "reef-plan-check.py"))
        r = sp.run([sys.executable, os.path.join(d, "scripts", "reef-plan-check.py"), d],
                   capture_output=True, text=True)
        assert r.returncode == 0, f"fixture plan must pass plan-check:\n{r.stdout}"
        return d

    def test_stamp_match_allows_and_stale_denies(self):
        d = self._stamped_repo()
        r = dispatch(d, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 0, f"fresh stamp must allow: {r.stderr}")
        # the guard's own odometer bump must NOT stale the stamp
        r = dispatch(d, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 0, f"odometer bump staled the stamp: {r.stderr}")
        # a real plan edit must deny
        p = os.path.join(d, "tasks", "007-demo.md")
        with open(p) as f:
            t = f.read()
        with open(p, "w") as f:
            f.write(t.replace("## Scope\nx", "## Scope\nsneaky edit"))
        r = dispatch(d, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2)
        self.assertIn("stamp", r.stderr)

    def test_missing_stamp_denied(self):
        import shutil
        make_task(self.dir)
        os.makedirs(os.path.join(self.dir, "scripts"), exist_ok=True)
        import subprocess as sp
        sp.run(["git", "init", "-q", "-b", "main", self.dir], check=True)
        shutil.copy(os.path.join(ROOT, "scripts", "reef-plan-check.py"),
                    os.path.join(self.dir, "scripts", "reef-plan-check.py"))
        os.makedirs(os.path.join(self.dir, ".reef"), exist_ok=True)
        with open(os.path.join(self.dir, ".reef", "config.json"), "w") as f:
            f.write('{"gates": {"test": "true"}}')
        r = dispatch(self.dir, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 2)
        self.assertIn("stamp", r.stderr)

    # ---- 0.4.0: one rollup per feature (the cap is shared by acceptance, diff and CI) ----

    def test_second_rollup_for_same_feature_denied(self):
        # a fresh R02 for a feature that already has R01 would start a fresh counter and
        # launder the cap; the guard must refuse it even without reef-attempt
        make_task(self.dir, name="R01-fixups.md", extra="")
        os.makedirs(os.path.join(self.dir, "tasks", "done"), exist_ok=True)
        os.replace(os.path.join(self.dir, "tasks", "R01-fixups.md"),
                   os.path.join(self.dir, "tasks", "done", "R01-fixups.md"))
        make_task(self.dir, name="R02-more-fixups.md")
        r = dispatch(self.dir, "REEF-TASK: tasks/R02-more-fixups.md\nimplement")
        self.assertEqual(r.returncode, 2, "a second rollup file for one feature must be denied")
        self.assertIn("rollup", r.stderr)


# ---------------- 0.4.0: the stamp under parallel worktrees ----------------

def git(d, *args):
    return subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *args],
                          check=True, capture_output=True, text=True)


def plan_task(tid, feature, scope="x"):
    return ("---\nid: {id}\nfeature: {f}\nstatus: pending\ncomplexity: mech\neffort: medium\n"
            "blocked-by: []\nverify: gate-only\nattempts: 0\ndispatches: 0\nlast_failure_sig: \"\"\n"
            "---\n# {id}\n\n## Scope\n{s}\n\n## Acceptance Criteria\n- test_{f}_{id}_works goes red first\n\n"
            "## Log\n").format(id=tid, f=feature, s=scope)


def plan_repo(d, tasks=((7, "demo"),)):
    """A committed git repo with a valid plan, the plan-check script, and the stamp
    gitignored (it is per-worktree state)."""
    import shutil
    os.makedirs(os.path.join(d, "tasks", "done"), exist_ok=True)
    os.makedirs(os.path.join(d, "scripts"), exist_ok=True)
    os.makedirs(os.path.join(d, ".reef"), exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    with open(os.path.join(d, ".reef", "config.json"), "w") as f:
        f.write('{"gates": {"test": "true"}}')
    with open(os.path.join(d, "CLAUDE.md"), "w") as f:
        f.write("# demo brief\n")
    with open(os.path.join(d, ".gitignore"), "w") as f:
        f.write("tasks/.plan-review.json\n")
    for tid, feat in tasks:
        with open(os.path.join(d, "tasks", f"{tid:03d}-{feat}.md"), "w") as f:
            f.write(plan_task(tid, feat))
    shutil.copy(os.path.join(ROOT, "scripts", "reef-plan-check.py"),
                os.path.join(d, "scripts", "reef-plan-check.py"))
    git(d, "add", "-A")
    git(d, "commit", "-qm", "plan")
    return d


def plan_check(d):
    r = subprocess.run([sys.executable, os.path.join(d, "scripts", "reef-plan-check.py"), d],
                       capture_output=True, text=True)
    assert r.returncode == 0, f"fixture plan must pass plan-check:\n{r.stdout}"


class SetupIsGuarded(unittest.TestCase):
    """The security review of the setup proof (2026-10-28): `worktree.setup` is a command scripts/reef-setup.py runs under the
    main checkout, and the hook sees only `python3 scripts/reef-setup.py prove` — so the worktree keys are the owner's, like
    the gates, and a read-only judge never runs prove/apply (they make worktrees and write .reef/ci-local/)."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-setup-guard.")
        subprocess.run(["git", "init", "-q", "-b", "main", self.d], check=True)
        write_config(self.d, {"gates": {"full": "true"}, "worktree": {"setup": "npm ci", "dir": ".reef/worktrees"}, "writing": {"task_words": {}}})

    def edit(self, old, new, who="reef:implementer"):
        return run_guard({"tool_name": "Edit", "cwd": self.d, "agent_id": "a1", "agent_type": who,
                          "tool_input": {"file_path": os.path.join(self.d, ".reef", "config.json"), "old_string": old, "new_string": new}})

    def test_the_worktree_keys_are_the_owners(self):
        r = self.edit('"setup": "npm ci"', '"setup": "printf {} > ../../evidence/x.json; npm ci"')
        self.assertEqual(r.returncode, 2, "worktree.setup is a command the proof runs unseen: " + r.stderr)
        self.assertIn("worktree", r.stderr)
        r = self.edit('"dir": ".reef/worktrees"', '"dir": "/tmp/elsewhere"')
        self.assertEqual(r.returncode, 2)
        r = self.edit('"task_words": {}', '"task_words": {"light": 300}')
        self.assertEqual(r.returncode, 0, "a key that is not the guard's stays editable: " + r.stderr)

    def test_a_judge_never_proves_or_applies_the_setup(self):
        for cmd in ("python3 scripts/reef-setup.py prove", "python3 scripts/reef-setup.py apply .reef/worktrees/x --repo .", "cd /x && python3 /x/scripts/reef-setup.py prove"):
            with self.subTest(cmd=cmd):
                r = run_guard({"tool_name": "Bash", "agent_type": "reef:verifier", "cwd": self.d, "tool_input": {"command": cmd}})
                self.assertEqual(r.returncode, 2, "NOT DENIED: " + cmd)
                self.assertIn("read-only", r.stderr)
        for who, cmd in (("reef:verifier", "python3 scripts/reef-setup.py state"), ("reef:implementer", "python3 scripts/reef-setup.py prove")):
            with self.subTest(who=who, cmd=cmd):
                r = run_guard({"tool_name": "Bash", "agent_type": who, "cwd": self.d, "tool_input": {"command": cmd}})
                self.assertEqual(r.returncode, 0, f"FALSE POSITIVE for {who}: {cmd}\n{r.stderr}")


class JudgeScratch(unittest.TestCase):
    """Re-entry (2026-10-16): the loophole-hunter was refused `mkdir -p …/scratchpad/pk` to unpack a tarball it wanted
    to read, and `tar -xzO 2>/dev/null` as "writes a file". A judge never mutates the PROJECT; its scratch space and
    /dev/null are not the project."""

    def judge(self, cmd, who="reef:loophole-hunter"):
        return run_guard({"tool_name": "Bash", "agent_type": who, "cwd": tempfile.gettempdir(), "tool_input": {"command": cmd}})

    def test_scratch_and_devnull_allowed_project_writes_denied(self):
        for cmd in ("mkdir -p /private/tmp/claude-501/x/scratchpad/pk && cd /private/tmp/claude-501/x/scratchpad/pk && curl -sL u | tar -xz",
                    "curl -sL u | tar -xzO 2>/dev/null | grep -o x",
                    "npm test > /tmp/out.txt; tail /tmp/out.txt",
                    "ls .reef/approvals 2>/dev/null",
                    # first contact (2026-10-17): the plan-reviewer was refused `git worktree list`, a read
                    "git worktree list --porcelain", "git stash list", "git submodule status"):
            with self.subTest(cmd=cmd):
                r = self.judge(cmd)
                self.assertEqual(r.returncode, 0, f"FALSE POSITIVE: {cmd!r}\n{r.stderr}")
        # 2026-10-18: `S=<scratchpad>; mkdir -p $S` was refused — the value assigned in the same command stands in for $S
        for cmd in ("S=/private/tmp/claude-501/x/scratchpad/r2; mkdir -p $S && cd $S && cat > mod.ts <<'EOF'\nx\nEOF",
                    "D=/tmp/claude-1/x/scratchpad; mkdir -p ${D}/brand; printf 'x' > ${D}/brand/m2.ts"):
            with self.subTest(cmd=cmd):
                r = self.judge(cmd)
                self.assertEqual(r.returncode, 0, f"FALSE POSITIVE: {cmd!r}\n{r.stderr}")
        for cmd in ("S=src/new; mkdir -p $S", "S=/home/u/proj/src; printf x > $S/a.ts", "mkdir -p $UNKNOWN/x",
                    "cd /tmp/claude-1/x/scratchpad; cd /home/u/proj && printf x > a.ts", "cd /tmp/claude-1/x/scratchpad | cat > a.ts"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.judge(cmd).returncode, 2, f"a project path through a variable, or a variable the guard cannot read, is still a write: {cmd!r}")
        for cmd in ("echo x | tee src/x.ts", "npm test > out.txt", "cp /tmp/x src/y.ts", "mkdir -p src/new", "sed -i s/a/b/ README.md",
                    "git worktree add ../x", "git worktree remove ../x", "git worktree prune", "git stash", "git stash pop"):
            with self.subTest(cmd=cmd):
                r = self.judge(cmd, who="reef:verifier")
                self.assertEqual(r.returncode, 2, f"NOT DENIED: {cmd!r}")
                self.assertIn("read-only", r.stderr)
        # 0.7: the release's security auditor is a judge too
        for cmd in ("cp /tmp/x src/y.ts", "sed -i s/a/b/ src/auth.ts"):
            with self.subTest(who="reef:security", cmd=cmd):
                r = self.judge(cmd, who="reef:security")
                self.assertEqual(r.returncode, 2, f"NOT DENIED for reef:security: {cmd!r}")
        self.assertEqual(self.judge("git diff main...develop -- src", who="reef:security").returncode, 0)
        # /reef-pentest: the hunter attacks a running app over HTTP — a read; saving a response into the project is a write
        for cmd in ("curl -s http://127.0.0.1:3000/api/bills/1", "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.judge(cmd).returncode, 0, f"FALSE POSITIVE: {cmd!r}")
        for cmd in ("curl -s -o src/dump.json http://127.0.0.1:3000/api/x", "curl -s --output=src/d.json http://x", "wget -O src/d.json http://x"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.judge(cmd).returncode, 2, f"a download into the project is a write: {cmd!r}")
        self.assertEqual(self.judge("curl -s -o /private/tmp/claude-501/x/scratchpad/r.json http://x").returncode, 0, "into the scratchpad: fine")

    def test_the_jobs_scratchpad_is_scratch_and_the_rest_of_dot_claude_is_not(self):
        # 2026-10-21 (qassimha row 5): the session's scratchpad was ~/.claude/jobs/b60d6e32/tmp; the plan reviewer's
        # `mkdir -p … && cat > …/plan-review-<slug>.md` there was refused as a project write, twice, and the
        # orchestrator copied the report out of the reviewer's transcript instead.
        jobs = os.path.join(os.path.expanduser("~"), ".claude", "jobs", "b60d6e32", "tmp")
        for cmd in (f"mkdir -p {jobs} && cat > {jobs}/plan-review-demo.md <<'EOF'\nRUN: agent=plan-reviewer\nEOF",
                    f"printf x > ~/.claude/jobs/b60d6e32/tmp/r.md", f"S={jobs}; mkdir -p $S/r2 && printf x > $S/r2/report.md"):
            with self.subTest(cmd=cmd[:60]):
                r = self.judge(cmd, who="reef:plan-reviewer")
                self.assertEqual(r.returncode, 0, f"FALSE POSITIVE: {cmd!r}\n{r.stderr}")
        for cmd in (f"printf x > ~/.claude/jobs/b60d6e32/r.md", "printf x > ~/.claude/settings.json",
                    f"printf x > ~/.claude/jobs/b60d6e32/tmp/../escape.md", "printf x > ~/.claude/jobs/tmp/r.md"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.judge(cmd, who="reef:plan-reviewer").returncode, 2, f"NOT DENIED: {cmd!r}")


class WorktreeStamp(unittest.TestCase):
    """The compat read (2026-10-03) found both failure directions: the guard resolved the
    stamp against the DISPATCHING SESSION's folder, not the task's own worktree."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reef-guard-wt.")
        self.main = plan_repo(os.path.join(self.tmp, "main"))
        self.wt = os.path.join(self.tmp, "wt")
        git(self.main, "worktree", "add", "-q", "-b", "feat", self.wt)
        self.wt_task = os.path.join(self.wt, "tasks", "007-demo.md")

    def test_fresh_worktree_stamp_allows_dispatch_from_main_checkout(self):
        # direction 1: the worktree was reviewed; the main checkout never was. Dispatching
        # from the main session used to deny every dispatch ("stamp missing").
        plan_check(self.wt)
        r = dispatch(self.main, f"REEF-TASK: {self.wt_task}\nimplement")
        self.assertEqual(r.returncode, 0, f"fresh stamp in the task's worktree must allow: {r.stderr}")

    def test_edited_worktree_plan_denied_even_if_session_stamp_is_fresh(self):
        # direction 2: the main checkout's stamp is fresh, the worktree's plan was edited
        # after its review. Checking the session's folder used to let this through.
        plan_check(self.main)
        plan_check(self.wt)
        with open(self.wt_task) as f:
            t = f.read()
        with open(self.wt_task, "w") as f:
            f.write(t.replace("## Scope\nx", "## Scope\nsneaky post-approval edit"))
        r = dispatch(self.main, f"REEF-TASK: {self.wt_task}\nimplement")
        self.assertEqual(r.returncode, 2, "a stale plan in the task's own worktree must deny")
        self.assertIn("stamp", r.stderr)


class FeatureStamp(unittest.TestCase):
    def test_unrelated_feature_arriving_by_merge_does_not_deny_dispatch(self):
        # merging the integration branch brings another feature's task files; that is not
        # an edit of THIS feature's plan and must not force a re-review
        d = plan_repo(tempfile.mkdtemp(prefix="reef-guard-feat."))
        plan_check(d)
        with open(os.path.join(d, "tasks", "008-other.md"), "w") as f:
            f.write(plan_task(8, "other"))
        r = dispatch(d, "REEF-TASK: tasks/007-demo.md\nimplement")
        self.assertEqual(r.returncode, 0, f"another feature's task staled this feature's stamp: {r.stderr}")
        r = dispatch(d, "REEF-TASK: tasks/008-other.md\nimplement")
        self.assertEqual(r.returncode, 2, "the newly arrived feature itself was never reviewed here")



class HandoffIsRendered(unittest.TestCase):
    """v3 phase 5: HANDOFF.md is rendered whole by scripts/reef-handoff --write (the loop's wait and the guard's checkpoint
    run it); a hand-written one is a map drawn from memory — denied for the main session and every agent, in every tool."""

    def test_no_hand_written_handoff(self):
        for cmd in ("cat > HANDOFF.md <<'EOF'\n# Handoff\nEOF", "echo '# Handoff' > HANDOFF.md", "printf 'x' >> ./HANDOFF.md",
                    "cp /tmp/claude-1/x/scratchpad/h.md HANDOFF.md", "sed -i '' 's/a/b/' HANDOFF.md"):
            with self.subTest(cmd=cmd):
                self.assertEqual(bash(cmd).returncode, 2, cmd)
        # the review (2026-10-26): a copy INTO a directory lands the handoff; `$PWD` is the cwd
        for cmd in ("cp /tmp/claude-1/x/scratchpad/HANDOFF.md .", "cp /tmp/claude-1/x/scratchpad/HANDOFF.md ./", "echo x > $PWD/HANDOFF.md", "echo x > ${PWD}/HANDOFF.md"):
            with self.subTest(cmd=cmd):
                self.assertEqual(bash(cmd).returncode, 2, cmd)
        for cmd in ("python3 scripts/reef-handoff --write", "python3 scripts/reef-loop.py wait \"/clear requested\"", "cat HANDOFF.md",
                    "head -40 HANDOFF.md", "cp HANDOFF.md /tmp/claude-1/x/scratchpad/handoff-copy.md", "echo x > HANDOFF-notes.md",
                    "cd /tmp/claude-1/x/scratchpad && cat > HANDOFF.md <<'EOF'\nscratch\nEOF", "git add HANDOFF.md", "git mv HANDOFF.md docs/HANDOFF.md"):
            with self.subTest(cmd=cmd):
                self.assertEqual(bash(cmd).returncode, 0, cmd + ": " + bash(cmd).stderr)
        for tool in ("Write", "Edit"):
            r = run_guard({"tool_name": tool, "tool_input": {"file_path": "HANDOFF.md", "content": "# Handoff", "old_string": "a", "new_string": "b"}})
            self.assertEqual(r.returncode, 2, tool)
            self.assertIn("reef-handoff --write", r.stderr)
        r = run_guard({"tool_name": "Write", "tool_input": {"file_path": "templates/project/HANDOFF.md", "content": "# template"}})
        self.assertEqual(r.returncode, 0, "the plugin's own template is not a project's handoff")
        r = run_guard({"tool_name": "Write", "agent_id": "a0e1e40f", "agent_type": "reef:implementer", "tool_input": {"file_path": "HANDOFF.md", "content": "x"}})
        self.assertEqual(r.returncode, 2, "no agent writes it either")


class TaskFilesAreThePlan(unittest.TestCase):
    """2026-10-29 (row 9 on the current adoption): the implementer rewrote the line numbers in its task's `## Read first` and
    the next task's, every close carried the edit, and the plan's digest moved — a re-approval of a plan the owner had
    approved, three times. A task file is the owner's approved text: an implementer never edits one; the mechanic's close
    and the orchestrator's amendments are not implementers."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-task-guard.")
        subprocess.run(["git", "init", "-q", "-b", "main", self.d], check=True)
        write_config(self.d, {"gates": {"full": "true"}, "paths": {"features": "reef/features"}})

    def edit(self, rel, who, tool="Edit"):
        payload = {"tool_name": tool, "cwd": self.d, "tool_input": {"file_path": os.path.join(self.d, rel), "old_string": ":234", "new_string": ":225", "content": "x"}}
        if who:
            payload.update(agent_id="a1", agent_type=who)
        return run_guard(payload)

    def test_an_implementer_never_edits_a_task_file(self):
        for rel in ("reef/features/demo/tasks/902-agents.md", "reef/features/demo/tasks/done/901-loop.md", "tasks/R03-fix.md"):
            for tool in ("Edit", "Write", "MultiEdit"):
                r = self.edit(rel, "reef:implementer", tool)
                self.assertEqual(r.returncode, 2, f"{tool} {rel}: {r.stderr}")
                self.assertIn("task file", r.stderr)
                self.assertIn("hand-back", r.stderr)
        r = self.edit("reef/features/demo/tasks/902-agents.md", "reef:mechanic")
        self.assertEqual(r.returncode, 0, "the mechanic's close edits are its job: " + r.stderr)
        r = self.edit("reef/features/demo/tasks/902-agents.md", "")
        self.assertEqual(r.returncode, 0, "the orchestrator amends a plan (then the owner re-approves): " + r.stderr)
        r = self.edit("src/tasks/902-agents.md", "reef:implementer")
        self.assertEqual(r.returncode, 0, "a project's own tasks folder outside the features dir is not Reef's: " + r.stderr)
        r = self.edit("reef/features/demo/tasks/notes.md", "reef:implementer")
        self.assertEqual(r.returncode, 0, "not a task file: " + r.stderr)


class EvidenceIsTheGates(unittest.TestCase):
    """v3 phase 2: .reef/evidence/<snapshot>.json is the suite's one result per tree, written by scripts/reef-gate.sh full
    and read by every judge. A hand-written file there would be a suite run that never happened — denied like a record
    under .reef/review/; running the gate, or reading the evidence, is never a write to it."""

    def test_every_writer_but_the_gate_is_denied_and_readers_pass(self):
        for cmd in ("echo '{\"exit\": 0}' > .reef/evidence/0123456789abcdef.json",
                    "cp /tmp/claude-1/x/scratchpad/e.json .reef/evidence/0123456789abcdef.json",
                    "tee .reef/evidence/0123456789abcdef.json < /tmp/e.json",
                    "python3 - <<'EOF'\nopen('.reef/evidence/x.json', 'w').write('{}')\nEOF\nmv x.json .reef/evidence/y.json",
                    "rm -rf .reef/evidence",
                    "cd .reef/worktrees/1101 && printf '{}' >> ../../evidence/abc.json",
                    # the security review of this change (2026-10-25): a case-insensitive disk, dd's of=, a whole folder
                    # copied, synced or unpacked into .reef/, and the deletes that take the folder with them
                    "echo '{}' > .reef/Evidence/0123456789abcdef.json",
                    "dd if=/tmp/e.json of=.reef/evidence/0123456789abcdef.json",
                    "mkdir -p /tmp/x/evidence && cp -r /tmp/x/evidence .reef/",
                    "rsync -a /tmp/x/evidence .reef/",
                    "mv /tmp/x/review .reef",
                    "tar -C .reef -xf /tmp/x.tar",
                    "rm -rf .reef",
                    "find .reef/evidence -delete",
                    "find .reef -name '*.json' -delete",
                    "git clean -fdX .reef/evidence",
                    "git clean -fdx .reef"):
            with self.subTest(cmd=cmd):
                self.assertEqual(bash(cmd).returncode, 2, cmd)
        for cmd in ("rm -rf .reef/worktrees/1101", "find .reef/ci-local -name '*.log'", "git clean -fd .reef/worktrees",
                    "cp /tmp/claude-1/x/scratchpad/notes.md .reef/", "tar -czf /tmp/claude-1/x/scratchpad/wt.tgz .reef/worktrees/1101", "ls .reef"):
            with self.subTest(cmd=cmd):
                self.assertEqual(bash(cmd).returncode, 0, cmd + ": " + bash(cmd).stderr)
        for cmd in ("sh scripts/reef-gate.sh full > /tmp/claude-1/x/scratchpad/gate.log 2>&1",
                    "REEF_GATE_NO_CACHE=1 sh scripts/reef-gate.sh full > /tmp/gate.log 2>&1; echo $?",
                    "python3 scripts/reef-evidence.py HEAD", "python3 scripts/reef-evidence.py --format json > /tmp/e.json",
                    "cat .reef/evidence/0123456789abcdef.json", "ls .reef/evidence 2>/dev/null"):
            with self.subTest(cmd=cmd):
                self.assertEqual(bash(cmd).returncode, 0, cmd + ": " + bash(cmd).stderr)
        for tool in ("Write", "Edit"):
            r = run_guard({"tool_name": tool, "tool_input": {"file_path": ".reef/evidence/0123456789abcdef.json", "content": "{}", "old_string": "a", "new_string": "b"}})
            self.assertEqual(r.returncode, 2, tool + " writes the evidence by hand")
            self.assertIn("evidence", r.stderr)
        r = run_guard({"tool_name": "Write", "agent_id": "a0e1e40f", "agent_type": "reef:verifier",
                       "tool_input": {"file_path": ".reef/evidence/0123456789abcdef.json", "content": "{}"}})
        self.assertEqual(r.returncode, 2, "a judge is no exception: it reads the evidence, it never writes it")


class EvidenceIsTheAgents(unittest.TestCase):
    """0.7: a hand-back or a judge's report typed by the orchestrator is evidence nobody but the orchestrator wrote
    (2026-10-17: a hunter report "written from the hand-back", a 1101 hand-back written "so the next session can verify it")."""

    def test_main_session_cannot_author_evidence_but_may_copy_it(self):
        for cmd in ("cat > .reef/ci-local/handback-1101.md <<'EOF'\nRUN: x\nEOF", "echo 'VERDICT: PASS' > .reef/hunt/row2-plan-r4.md",
                    "printf 'x' >> .reef/ci-local/report-1101.md", "tee .reef/ci-local/plan-review-demo.md"):
            with self.subTest(cmd=cmd):
                r = bash(cmd)
                self.assertEqual(r.returncode, 2, cmd)
                self.assertIn("Resume that agent", r.stderr)
        for cmd in ("cp /tmp/claude-1/x/scratchpad/row2.md .reef/hunt/row2-plan-r4.md", "mv /tmp/claude-1/x/scratchpad/h.md .reef/ci-local/handback-1101.md",
                    "cat .reef/ci-local/handback-1101.md", "python3 scripts/reef-claims.py check --handback .reef/ci-local/handback-1101.md"):
            with self.subTest(cmd=cmd):
                self.assertEqual(bash(cmd).returncode, 0, cmd)
        r = run_guard({"tool_name": "Write", "tool_input": {"file_path": ".reef/ci-local/handback-1101.md", "content": "RUN: x"}})
        self.assertEqual(r.returncode, 2, "the Write tool is authoring too")
        r = run_guard({"tool_name": "Write", "agent_id": "a0e1e40f", "agent_type": "reef:implementer",
                       "tool_input": {"file_path": ".reef/ci-local/handback-1101.md", "content": "RUN: x"}})
        self.assertEqual(r.returncode, 0, "the implementer writes its own hand-back: " + r.stderr)
        r = run_guard({"tool_name": "Bash", "agent_id": "a0e1e40f", "agent_type": "reef:implementer",
                       "tool_input": {"command": "cat > .reef/ci-local/handback-1101.md <<'EOF'\nRUN: x\nEOF"}})
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()


class TheEntryPointAndTheRunnerAreTheOwners(unittest.TestCase):
    """The security review of PR 202 (2026-10-28): `scripts/reef` sat outside the guard's own-files rule (the dash was required),
    and the runner evicted a LIVE loop holder — an agent could run `reef-run.py --detach` and take the loop from the owner's
    session. The entry point is a guard file; a sub-agent never runs the runner's writing verbs or `reef-loop.py unlock`."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-entry-guard.")
        subprocess.run(["git", "init", "-q", "-b", "main", self.d], check=True)
        write_config(self.d, {"gates": {"full": "true"}})

    def test_the_entry_point_is_a_guard_file(self):
        r = run_guard({"tool_name": "Edit", "cwd": self.d, "agent_id": "a1", "agent_type": "reef:implementer",
                       "tool_input": {"file_path": os.path.join(self.d, "scripts", "reef"), "old_string": "x", "new_string": "y"}})
        self.assertEqual(r.returncode, 2, "scripts/reef is the owner's terminal: " + r.stderr)
        self.assertIn("guard's own files", r.stderr)
        r = run_guard({"tool_name": "Bash", "cwd": self.d, "tool_input": {"command": "printf 'x' > scripts/reef"}})
        self.assertEqual(r.returncode, 2)

    def test_a_sub_agent_never_takes_the_loop(self):
        for cmd in ("python3 scripts/reef-run.py --detach", "python3 scripts/reef-run.py --night --detach", "python3 scripts/reef-loop.py unlock",
                    "cd /x && python3 /x/scripts/reef-run.py --max-iterations 3"):
            with self.subTest(cmd=cmd):
                r = run_guard({"tool_name": "Bash", "cwd": self.d, "agent_id": "a1", "agent_type": "reef:implementer", "tool_input": {"command": cmd}})
                self.assertEqual(r.returncode, 2, "NOT DENIED: " + cmd)
                self.assertIn("owner", r.stderr)
        for cmd in ("python3 scripts/reef-run.py status", "python3 scripts/reef-run.py watch", "python3 scripts/reef-loop.py tick"):
            with self.subTest(cmd=cmd):
                r = run_guard({"tool_name": "Bash", "cwd": self.d, "agent_id": "a1", "agent_type": "reef:implementer", "tool_input": {"command": cmd}})
                self.assertEqual(r.returncode, 0, f"FALSE POSITIVE: {cmd}\n{r.stderr}")
        # the main session runs the runner (/reef-run) and nothing changes for it
        r = run_guard({"tool_name": "Bash", "cwd": self.d, "tool_input": {"command": "python3 scripts/reef-run.py --detach"}})
        self.assertEqual(r.returncode, 0, r.stderr)
