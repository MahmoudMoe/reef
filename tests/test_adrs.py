"""Hardening PR-8 (docs/design/hardening-pr8-plan.md): an agent reads only the ADRs that touch its task's files. An ADR declares
the paths it governs (`Paths:`, the round check's matcher: `dir/` a prefix, else a glob); scripts/reef-adrs.py selects the
Accepted ADRs that meet a task's `files:` — and every ADR that declares none (conservative: an undeclared decision is never
dropped). The implementer gets the list by code (reef-attempt's `adrs:` block), the planner per feature, the verifier per diff."""
import os
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import write, load_script  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADRS = os.path.join(ROOT, "scripts", "reef-adrs.py")
ARCH = "reef/architecture/adr"


def adr(root, rel, status="Accepted", paths=None):
    write(root, rel, f"# ADR — {os.path.basename(rel)}\n\nStatus: {status}\n" + (f"Paths: {paths}\n" if paths is not None else "")
          + "\n## Context\nx\n\n## Decision\ny\n")


def task(root, rel, files="[src/auth/, tests/test_auth.py]"):
    write(root, rel, "---\nid: 101\nfeature: demo\nstatus: pending\n" + (f"files: {files}\n" if files is not None else "")
          + "---\n# demo\n\n## Log\n")
    return os.path.join(root, rel)


def project():
    """5 Accepted ADRs: 3 scoped elsewhere, 1 on the task's files, 1 undeclared — plus a Superseded and a Proposed one."""
    d = tempfile.mkdtemp(prefix="reef-adrs.")
    os.makedirs(os.path.join(d, ".reef"))
    adr(d, f"{ARCH}/0001-billing.md", paths="src/billing/")
    adr(d, f"{ARCH}/0002-ui.md", paths="web/*.tsx, web/static/")
    adr(d, f"{ARCH}/0003-auth.md", paths="src/auth/")
    adr(d, f"{ARCH}/0004-legacy.md")
    adr(d, f"{ARCH}/0005-old.md", status="Superseded by 0003", paths="src/auth/")
    adr(d, "reef/features/demo/adr/draft-demo-store.md", paths="src/store.py")
    adr(d, "reef/features/demo/adr/draft-demo-x.md", status="Proposed", paths="src/auth/")
    return d


def run(*args):
    return subprocess.run([sys.executable, ADRS, *args], capture_output=True, text=True)


def listed(out):
    return [l.strip().split(" ", 1)[0] for l in out.splitlines() if l.startswith("  ")]


class Meet(unittest.TestCase):
    """Two `files:` patterns meet when a path can match both — sound (never a miss), it may over-include."""

    def setUp(self):
        self.m = load_script("reef-adrs.py", "reef_adrs")

    def test_the_round_checks_matcher_on_a_concrete_path(self):
        self.assertTrue(self.m.meet("src/auth/login.py", "src/auth/"))
        self.assertTrue(self.m.meet("tests/test_auth.py", "tests/test_*.py"))
        self.assertFalse(self.m.meet("src/authx.py", "src/auth/"))
        self.assertFalse(self.m.meet("src/a.py", "src/b.py"))

    def test_two_patterns(self):
        self.assertTrue(self.m.meet("src/", "src/auth/"), "a dir and a dir under it")
        self.assertTrue(self.m.meet("src/*.py", "src/auth/"), "fnmatch's * crosses /, as the round check's does")
        self.assertTrue(self.m.meet("*", "anything/at/all.py"))
        self.assertFalse(self.m.meet("tests/test_a*.py", "tests/test_b*.py"))
        self.assertFalse(self.m.meet("web/", "src/auth/"))


class Task(unittest.TestCase):
    def test_a_task_loads_the_adrs_on_its_files_and_the_undeclared_only(self):
        d = project()
        p = task(d, "reef/features/demo/tasks/101-a.md")
        r = run("task", p)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(listed(r.stdout), [f"{ARCH}/0003-auth.md", f"{ARCH}/0004-legacy.md"], r.stdout)
        lines = r.stdout.splitlines()
        self.assertTrue(lines[0].startswith("adrs: 2 of 5 Accepted ADRs touch this task's files:"), lines[0])
        self.assertEqual(lines[-1], "adrs: end")
        self.assertIn(f"  {ARCH}/0004-legacy.md (Paths: not declared — loaded for every task)", lines)
        # the measure (plan, "Measure"): every Accepted ADR before, the scoped list after
        print(f"\n[PR-8 measure] ADR files loaded for task 101: before 5, after {len(listed(r.stdout))}", file=sys.stderr)

    def test_the_features_own_adr_is_scoped_too(self):
        d = project()
        p = task(d, "reef/features/demo/tasks/101-a.md", files="[src/store.py]")
        self.assertEqual(listed(run("task", p).stdout),
                         [f"{ARCH}/0004-legacy.md", "reef/features/demo/adr/draft-demo-store.md"])

    def test_a_task_without_files_loads_every_accepted_adr_and_says_why(self):
        d = project()
        p = task(d, "reef/features/demo/tasks/101-a.md", files=None)
        r = run("task", p)
        self.assertEqual(len(listed(r.stdout)), 5, r.stdout)
        self.assertIn("no files:", r.stdout.splitlines()[0])

    def test_superseded_and_proposed_are_never_listed(self):
        d = project()
        out = run("task", task(d, "reef/features/demo/tasks/101-a.md")).stdout
        self.assertNotIn("0005-old.md", out)
        self.assertNotIn("draft-demo-x.md", out)

    def test_none_matching_is_the_header_and_end(self):
        d = project()
        r = run("task", task(d, "reef/features/demo/tasks/101-a.md", files="[docs/]"))
        self.assertEqual(listed(r.stdout), [f"{ARCH}/0004-legacy.md"])
        d2 = tempfile.mkdtemp(prefix="reef-adrs.")
        os.makedirs(os.path.join(d2, ".reef"))
        adr(d2, f"{ARCH}/0001-billing.md", paths="src/billing/")
        r = run("task", task(d2, "tasks/101-a.md"))
        self.assertEqual(r.stdout.splitlines(), ["adrs: 0 of 1 Accepted ADRs touch this task's files: — read none", "adrs: end"])

    def test_no_adr_in_the_project_prints_nothing(self):
        d = tempfile.mkdtemp(prefix="reef-adrs.")
        os.makedirs(os.path.join(d, ".reef"))
        r = run("task", task(d, "tasks/101-a.md"))
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_the_legacy_adr_path_is_read(self):
        d = tempfile.mkdtemp(prefix="reef-adrs.")
        write(d, ".reef/config.json", '{"paths": {"adr": "docs/adr"}}')
        adr(d, "docs/adr/0001-auth.md", paths="src/auth/")
        self.assertEqual(listed(run("task", task(d, "tasks/101-a.md")).stdout), ["docs/adr/0001-auth.md"])

    def test_the_placeholder_and_an_empty_line_are_undeclared(self):
        d = tempfile.mkdtemp(prefix="reef-adrs.")
        os.makedirs(os.path.join(d, ".reef"))
        adr(d, f"{ARCH}/0001-a.md", paths="<dir/ or glob, …>")
        adr(d, f"{ARCH}/0002-b.md", paths="")
        self.assertEqual(len(listed(run("task", task(d, "tasks/101-a.md", files="[x/]")).stdout)), 2)


class FeatureAndPaths(unittest.TestCase):
    def test_the_planner_gets_its_features_adrs_and_the_project_adrs_on_its_files(self):
        d = project()
        task(d, "reef/features/demo/tasks/101-a.md", files="[src/auth/]")
        task(d, "reef/features/demo/tasks/102-b.md", files="[web/app.tsx]")
        r = run("feature", "demo", "--repo", d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(listed(r.stdout), [f"{ARCH}/0002-ui.md", f"{ARCH}/0003-auth.md", f"{ARCH}/0004-legacy.md",
                                            "reef/features/demo/adr/draft-demo-store.md"])

    def test_a_fresh_plan_gets_every_project_adr(self):
        d = project()
        self.assertEqual(len(listed(run("feature", "demo", "--repo", d).stdout)), 5)

    def test_the_verifier_gets_the_adrs_on_the_diffs_names(self):
        d = project()
        r = run("paths", "web/app.tsx", "README.md", "--repo", d)
        self.assertEqual(listed(r.stdout), [f"{ARCH}/0002-ui.md", f"{ARCH}/0004-legacy.md"])


class Cli(unittest.TestCase):
    def test_bad_input_is_exit_2(self):
        self.assertEqual(run().returncode, 2)
        self.assertEqual(run("task", "/nonexistent/101-a.md").returncode, 2)


if __name__ == "__main__":
    unittest.main()
