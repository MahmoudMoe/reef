"""The clean-code ratchet (2026-11-06, the owner: "clean code, a function never past a size, and so on — baked into Reef?").
`reef-structure --quality` runs the project's own linter with Reef's four limits (complexity, parameters, function length or
statements, nesting) on the files the branch changed since its base, against reef/quality-baseline.json: a file never gains a violation, a
new file has none, the old code is grandfathered by `--quality --baseline`. No linter is a skip (exit 77), never a pass."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import write, git_checked, ROOT  # noqa: E402

STRUCT = os.path.join(ROOT, "scripts", "reef-structure")
# a fake ruff: one C901 per line holding `# complex`, reported as ruff's JSON does; it records the args it was given
FAKE_RUFF = r"""#!/usr/bin/env python3
import json, os, sys
open(os.environ["FAKE_ARGS"], "a").write(json.dumps(sys.argv[1:]) + "\n")
files = [a for a in sys.argv[1:] if a.endswith(".py")]
out = [{"filename": os.path.abspath(f), "code": "C901",
        "message": "`%s` is too complex (12 > 7)" % (line.split("# complex")[1].strip() or "f")} for f in files
       for line in open(f) if "# complex" in line]
print(json.dumps(out)); sys.exit(1 if out else 0)
"""


class QualityRatchet(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-quality.")
        git_checked(self.d, "init", "-q", "-b", "main")
        write(self.d, "pyproject.toml", "[project]\nname='x'\n")
        write(self.d, ".reef/config.json", json.dumps({"structure": {"quality": {"complexity": 7}}}))
        write(self.d, "src/old.py", "def a():  # complex\n    pass\n")
        git_checked(self.d, "add", "-A"); git_checked(self.d, "commit", "-qm", "start")
        self.bin = tempfile.mkdtemp(prefix="reef-quality-bin.")
        write(self.bin, "ruff", FAKE_RUFF); os.chmod(os.path.join(self.bin, "ruff"), 0o755)
        self.args = os.path.join(self.bin, "args.jsonl")

    def q(self, *a, path=None):
        env = dict(os.environ, PATH=(path if path is not None else self.bin + os.pathsep + os.environ["PATH"]), FAKE_ARGS=self.args)
        return subprocess.run([sys.executable, STRUCT, "--quality", *a, "--repo", self.d], capture_output=True, text=True, env=env)

    def test_old_code_is_grandfathered_and_never_gains_a_violation_and_new_code_has_none(self):
        r = self.q("--baseline")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        base = json.load(open(os.path.join(self.d, "reef", "quality-baseline.json")))
        self.assertEqual(base["files"], {"src/old.py": {"C901 `f` is too complex (N > N)": 1}}, "each violation by rule and name")
        self.assertIn("lint.mccabe.max-complexity=7", open(self.args).read(), "the limit comes from structure.quality")
        write(self.d, "src/old.py", "def a():  # complex\n    return 1\n")
        self.assertEqual(self.q().returncode, 0, "the old violation is grandfathered")
        write(self.d, "src/old.py", "def a():  # complex\n    pass\ndef b():  # complex\n    pass\n")
        r = self.q()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("src/old.py: 1 violation(s) the baseline does not hold", r.stdout)
        write(self.d, "src/old.py", "def a():\n    pass\n")
        write(self.d, "src/new.py", "def n():  # complex\n    pass\n")
        r = self.q()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("src/new.py: 1 violation(s) in a new file", r.stdout)
        self.assertIn("C901", r.stdout, "the rule is named")
        write(self.d, "src/new.py", "def n():\n    pass\n")
        r = self.q()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(json.load(open(os.path.join(self.d, "reef", "quality-baseline.json")))["files"].get("src/old.py", 0), 0,
                         "a file that got cleaner lowers its baseline (the ratchet)")

    def test_no_linter_is_a_skip_never_a_pass(self):
        write(self.d, "src/new.py", "def n():  # complex\n    pass\n")
        r = self.q(path="/usr/bin:/bin")
        self.assertEqual(r.returncode, 77, r.stdout + r.stderr)
        self.assertIn("skipped", r.stdout)


class ACommittedHeadIsChecked(unittest.TestCase):
    """2026-11-06 (an adopted project, row 239): the hunter found `--quality` and `--sizes` read only the files changed since
    HEAD — on a committed, pushed head that is nothing, so the gate passed on every row. Both now read the branch against its
    merge-base with the base branch (origin/<base>, else <base>), and refuse when the base cannot be found."""
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-committed.")
        git_checked(self.d, "init", "-q", "-b", "main")
        write(self.d, "pyproject.toml", "[project]\nname='x'\n")
        write(self.d, ".reef/config.json", json.dumps({"branches": {"base": "main"}, "structure": {"new_file_lines": 5}}))
        write(self.d, "reef/size-baseline.json", json.dumps({"files": {"src/old.py": 2}}))
        write(self.d, "reef/quality-baseline.json", json.dumps({"files": {}}))
        write(self.d, "src/old.py", "def a():\n    pass\n")
        git_checked(self.d, "add", "-A"); git_checked(self.d, "commit", "-qm", "start")
        git_checked(self.d, "checkout", "-q", "-b", "feat/x")
        self.bin = tempfile.mkdtemp(prefix="reef-committed-bin.")
        write(self.bin, "ruff", FAKE_RUFF); os.chmod(os.path.join(self.bin, "ruff"), 0o755)
        self.env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"], FAKE_ARGS=os.path.join(self.bin, "args.jsonl"))

    def run_struct(self, flag):
        return subprocess.run([sys.executable, STRUCT, flag, "--repo", self.d], capture_output=True, text=True, env=self.env)

    def commit(self):
        git_checked(self.d, "add", "-A"); git_checked(self.d, "commit", "-qm", "row")

    def test_a_committed_complex_function_fails_quality(self):
        write(self.d, "src/new.py", "def n():  # complex\n    pass\n")
        self.commit()
        r = self.run_struct("--quality")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("src/new.py: 1 violation(s) in a new file", r.stdout)

    def test_a_committed_growth_fails_sizes(self):
        write(self.d, "src/old.py", "def a():\n    pass\n\n\ndef b():\n    pass\n")
        self.commit()
        r = self.run_struct("--sizes")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("src/old.py: 6 lines, over its baseline of 2", r.stdout)

    def test_the_base_counts_from_origin_when_there_is_one(self):
        # the local base ran ahead of origin/<base> (the row was merged into it locally): the row's files are still read
        bare = tempfile.mkdtemp(prefix="reef-committed-origin.")
        git_checked(bare, "init", "-q", "--bare")
        git_checked(self.d, "remote", "add", "origin", bare)
        git_checked(self.d, "push", "-q", "origin", "main")
        git_checked(self.d, "fetch", "-q", "origin")
        write(self.d, "src/new.py", "def n():  # complex\n    pass\n")
        self.commit()
        git_checked(self.d, "branch", "-f", "main", "HEAD")
        self.assertEqual(self.run_struct("--quality").returncode, 1)

    def test_no_base_branch_fails_closed(self):
        write(self.d, ".reef/config.json", json.dumps({"branches": {"base": "develop"}}))
        write(self.d, "src/new.py", "def n():\n    pass\n")
        self.commit()
        for flag in ("--quality", "--sizes"):
            r = self.run_struct(flag)
            self.assertEqual(r.returncode, 1, flag + r.stdout + r.stderr)
            self.assertIn("no base branch develop", r.stdout, flag)


class TheBaselineNamesEachViolation(unittest.TestCase):
    """2026-11-06 (an adopted project, row 239's hunter): the baseline was one count per file, so fixing one grandfathered
    function and adding a new over-limit one in the same file kept the count and passed. Each violation is now held by its
    rule and the linter's own words for it (numbers dropped: the function's name stays). An old count baseline still works
    as before until `--baseline` rewrites it. And one linter that fails to answer while another runs is no pass: the files
    it was given were never measured (exit 77)."""
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="reef-quality-names.")
        git_checked(self.d, "init", "-q", "-b", "main")
        write(self.d, "pyproject.toml", "[project]\nname='x'\n")
        write(self.d, "src/old.py", "def a():  # complex a\n    pass\n")
        git_checked(self.d, "add", "-A"); git_checked(self.d, "commit", "-qm", "start")
        self.bin = tempfile.mkdtemp(prefix="reef-quality-names-bin.")
        write(self.bin, "ruff", FAKE_RUFF); os.chmod(os.path.join(self.bin, "ruff"), 0o755)
        self.env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"], FAKE_ARGS=os.path.join(self.bin, "args.jsonl"))

    def q(self, *a):
        return subprocess.run([sys.executable, STRUCT, "--quality", *a, "--repo", self.d], capture_output=True, text=True, env=self.env)

    def test_fixing_one_function_does_not_pay_for_a_new_one(self):
        self.assertEqual(self.q("--baseline").returncode, 0)
        write(self.d, "src/old.py", "def a():\n    pass\ndef b():  # complex b\n    pass\n")
        r = self.q()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("src/old.py: 1 violation(s) the baseline does not hold", r.stdout)
        self.assertIn("`b` is too complex", r.stdout, "the new one is named")
        write(self.d, "src/old.py", "def a():\n    pass\n")
        self.assertEqual(self.q().returncode, 0)
        self.assertNotIn("src/old.py", json.load(open(os.path.join(self.d, "reef", "quality-baseline.json")))["files"],
                         "the fixed one leaves the baseline (the ratchet)")

    def test_an_old_count_baseline_still_counts(self):
        write(self.d, "reef/quality-baseline.json", json.dumps({"files": {"src/old.py": 1}}))
        write(self.d, "src/old.py", "def a():  # complex a\n    pass\ndef b():  # complex b\n    pass\n")
        r = self.q()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("src/old.py: 2 violation(s), over its baseline of 1", r.stdout)
        self.assertIn("--baseline", r.stdout, "the line says how to move to the named baseline")

    def test_a_linter_that_fails_while_another_runs_is_a_skip(self):
        write(self.bin, "npx", "#!/bin/sh\necho 'npm ERR! could not determine executable to run'\nexit 1\n")
        os.chmod(os.path.join(self.bin, "npx"), 0o755)
        write(self.d, "src/new.ts", "export const n = 1\n")
        write(self.d, "src/new.py", "def n():\n    pass\n")
        r = self.q()
        self.assertEqual(r.returncode, 77, r.stdout + r.stderr)
        self.assertIn("eslint", r.stdout, "the line names the linter that did not answer")


class AnInlineDisableIsNoWayOut(unittest.TestCase):
    """2026-11-06 (an adopted project, row 239's hunter, B1): the quality command ran the project's linter with Reef's rules
    but honoured the file's own directives — `// eslint-disable-next-line complexity`, `/* eslint complexity: [...] */`,
    `# noqa: C901` — so one comment switched the gate off for that function. Both commands now ignore inline directives;
    only Reef's rules are kept from the result, so the project's other directives change nothing here."""

    def test_both_commands_ignore_inline_directives(self):
        stacks = json.load(open(os.path.join(ROOT, "scripts", "reef-stacks.json")))
        cmds = {k: v["quality"]["cmd"] for k, v in stacks.items() if isinstance(v, dict) and v.get("quality")}
        self.assertIn("--no-inline-config", cmds["node"])
        self.assertIn("--ignore-noqa", cmds["python"])

    @unittest.skipUnless(__import__("shutil").which("ruff"), "the real ruff is not on PATH")
    def test_a_noqa_comment_does_not_hide_a_complex_function_from_the_real_ruff(self):
        d = tempfile.mkdtemp(prefix="reef-quality-noqa.")
        git_checked(d, "init", "-q", "-b", "main")
        write(d, "pyproject.toml", "[project]\nname='x'\n")
        write(d, "src/ok.py", "def ok():\n    return 1\n")
        git_checked(d, "add", "-A"); git_checked(d, "commit", "-qm", "start")
        r = subprocess.run([sys.executable, STRUCT, "--quality", "--baseline", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        body = "".join(f"    if a == {i}:\n        return {i}\n" for i in range(12))
        write(d, "src/big.py", "def big(a):  # noqa: C901\n" + body + "    return 0\n")
        r = subprocess.run([sys.executable, STRUCT, "--quality", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("`big` is too complex", r.stdout)
