"""The clean-code ratchet (2026-11-06, the owner: "clean code, a function never past a size, and so on — baked into Reef?").
`reef-structure --quality` runs the project's own linter with Reef's four limits (complexity, parameters, function length or
statements, nesting) on the files changed since HEAD, against reef/quality-baseline.json: a file never gains a violation, a
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
out = [{"filename": os.path.abspath(f), "code": "C901", "message": "too complex"} for f in files
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
        self.assertEqual(base["files"], {"src/old.py": 1})
        self.assertIn("lint.mccabe.max-complexity=7", open(self.args).read(), "the limit comes from structure.quality")
        write(self.d, "src/old.py", "def a():  # complex\n    return 1\n")
        self.assertEqual(self.q().returncode, 0, "the old violation is grandfathered")
        write(self.d, "src/old.py", "def a():  # complex\n    pass\ndef b():  # complex\n    pass\n")
        r = self.q()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("src/old.py: 2 violation(s), over its baseline of 1", r.stdout)
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
