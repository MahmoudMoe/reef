"""--help is never data (0.7, the owner's go 2026-10-24): qassimha's loop ran `reef-queue.py footnote --help` and got a footnote
reading "--help", three times. Every script that writes from its arguments prints its usage on -h/--help and writes nothing."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import git_repo  # noqa: E402  (the suites' shared fixtures, once)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, "scripts")


def project():
    d = git_repo(prefix="reef-help.", branch="main")
    os.makedirs(os.path.join(d, ".reef"))
    os.makedirs(os.path.join(d, "reef"))
    with open(os.path.join(d, ".reef", "config.json"), "w") as f:
        json.dump({"paths": {"queue": "reef/queue.md"}}, f)
    with open(os.path.join(d, ".reef", "loop.json"), "w") as f:
        json.dump({"active": True, "wait": None, "stop": None, "parked": None, "hashes": []}, f)
    with open(os.path.join(d, "reef", "queue.md"), "w") as f:
        f.write("# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 1 | a | | planned | 1 | |\n")
    return d


def snapshot(d):
    out = {}
    for dp, dns, fns in os.walk(d):
        dns[:] = [n for n in dns if n != ".git"]
        for n in fns:
            p = os.path.join(dp, n)
            out[os.path.relpath(p, d)] = hashlib.sha1(open(p, "rb").read()).hexdigest()
    return out


class HelpIsNeverData(unittest.TestCase):
    def test_help_prints_usage_and_writes_nothing(self):
        d = project()
        before = snapshot(d)
        for script, args in (("reef-queue.py", ["footnote", "--help"]), ("reef-queue.py", ["note", "-h", "--row", "1"]),
                             ("reef-queue.py", ["add-row", "--item", "--help"]), ("reef-loop.py", ["wait", "--help"]),
                             ("reef-record", ["--help"]), ("reef-record", ["plan-review", "x", "--help"])):
            with self.subTest(script=script, args=args):
                r = subprocess.run([sys.executable, os.path.join(S, script), *args, "--repo", d], capture_output=True, text=True,
                                   cwd=d, env=dict(os.environ, PATH="/nonexistent-gh:" + os.environ["PATH"]))
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("reef-", r.stdout, "the usage is printed")
                self.assertEqual(snapshot(d), before, f"{script} {' '.join(args)} wrote something")


if __name__ == "__main__":
    unittest.main()
