"""Sabotage suite for `reef-claims.py assess`: /reef-assess's output as data. The fixture under tests/fixtures/assess/
ledger/ is a REAL report (four Explore agents on the ledger dogfood project, 2026-10-16); it must pass as written, and
each way an assess can lie must be caught: a claim with no Observed/Inferred label, an Observed claim with no proving
path, a harnessability heading whose sum or level does not match its table, a missing dimension, a missing section."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAIMS = os.path.join(ROOT, "scripts", "reef-claims.py")
FIX = os.path.join(ROOT, "tests", "fixtures", "assess", "ledger")


def project():
    d = tempfile.mkdtemp(prefix="reef-assess.")
    os.makedirs(os.path.join(d, "reef", "architecture"))
    for name in ("architecture.md", "conventions.md"):
        shutil.copy(os.path.join(FIX, name), os.path.join(d, "reef", "architecture", name))
    shutil.copy(os.path.join(FIX, "day-zero.md"), os.path.join(d, "reef", "day-zero.md"))
    return d


def assess(d):
    return subprocess.run([sys.executable, CLAIMS, "assess", d], capture_output=True, text=True)


RECAL = os.path.join(ROOT, "scripts", "reef-recalibrate")


def write(d, rel, text):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


class Measure(unittest.TestCase):
    """0.7.2 (ai-coach, 2026-10-24, item 10): `reef-recalibrate measure` counts what /reef-assess used to judge by feel. On
    ai-coach the largest files were tests and an i18n dictionary (2613 lines of data), the `$executeRawUnsafe` hits were
    mostly comments, and the tagged `$queryRaw` calls were parameterised."""

    def fixture(self, cfg_extra=None):
        d = project()
        subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
        write(d, ".reef/config.json", json.dumps({"paths": {}, **(cfg_extra or {})}))
        write(d, "package.json", json.dumps({"name": "demo", "dependencies": {"@prisma/client": "6"}}))
        write(d, ".eslintrc.json", "{}\n")
        write(d, "src/lib/big.ts", "export const a = 1;\n" * 900)                         # product, over the cap
        write(d, "src/lib/interface/ar.ts", "export const t = {};\n" * 2613)             # data: excluded
        write(d, "src/types.d.ts", "declare const x: number;\n" * 50)                      # excluded
        write(d, "src/lib/db.ts", "import { prisma } from './client';\n"
                                  "// never use prisma.$executeRawUnsafe here — see the ADR\n"
                                  " * prisma.$queryRawUnsafe is forbidden too\n"
                                  "export const one = () => prisma.$queryRaw`select 1`;\n"
                                  "export const bad = (s: string) => prisma.$executeRawUnsafe(s);\n")
        write(d, "src/lib/big.test.ts", "import { a } from './big';\n" * 100)            # a test, 100 lines
        write(d, "tests/aimed-writes.test.ts", "/** Forbids writes outside the aimed tables. */\nimport { it } from 'vitest';\n")
        write(d, "tests/helpers.ts", "export const h = 1;\n")
        write(d, "prisma/migrations/0001_x/migration.sql", "CREATE FUNCTION f() RETURNS trigger AS $$ $$;\n"
                                                          "create or replace function g() returns void as $$ $$;\n"
                                                          "CREATE TRIGGER t BEFORE INSERT ON x EXECUTE FUNCTION f();\n")
        write(d, "node_modules/x/index.js", "x\n" * 5000)                                  # generated: excluded
        return d

    def test_exact_counts_and_the_three_outputs(self):
        d = self.fixture()
        r = subprocess.run([sys.executable, RECAL, "measure", "--json", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        m = json.loads(r.stdout)
        self.assertEqual(m["largest"][0], ["src/lib/big.ts", 900])
        self.assertNotIn("src/lib/interface/ar.ts", [x[0] for x in m["largest"]], "an i18n dictionary is data, not product")
        self.assertNotIn("src/types.d.ts", [x[0] for x in m["largest"]])
        self.assertEqual((m["product"]["files"], m["product"]["loc"]), (2, 905))
        self.assertEqual((m["tests"]["files"], m["tests"]["loc"]), (3, 103))
        self.assertEqual(m["raw_sql"], {"src/lib": {"tagged": 1, "unsafe": 1, "files": ["src/lib/db.ts"]}}, "the two comment lines never count")
        self.assertEqual(m["migrations"], {"prisma/migrations/0001_x/migration.sql": {"functions": 2, "triggers": 1}})
        self.assertEqual(m["linter"], ".eslintrc.json")
        self.assertEqual(m["guard_tests"], ["tests/aimed-writes.test.ts"])
        self.assertEqual(m["large_files"], [["src/lib/big.ts", 900]])
        dz = open(os.path.join(d, "reef", "day-zero.md")).read()
        self.assertIn("## Measured", dz)
        self.assertIn("| 900 | `src/lib/big.ts` |", dz)
        self.assertIn("| `src/lib` | 1 | 1 |", dz)
        self.assertEqual(assess(d).returncode, 0, "the harnessability checker still passes with the section appended")
        base = json.load(open(os.path.join(d, "reef", "size-baseline.json")))
        self.assertEqual(base["files"], {"src/lib/big.ts": 900, "src/lib/db.ts": 5}, "product files only, same excludes")
        rec = open(os.path.join(d, "reef", "recalibration.md")).read()
        self.assertIn("| `src/lib/big.ts` | 900 | `kind: refactor` · `splits: src/lib/big.ts under 800 lines` |", rec)
        r = subprocess.run([sys.executable, RECAL, "measure", "--json", "--repo", d], capture_output=True, text=True)
        self.assertEqual(open(os.path.join(d, "reef", "day-zero.md")).read().count("## Measured"), 1, "a second run replaces the section")

    def test_assess_exclude_and_large_file_are_the_owners(self):
        d = self.fixture({"assess": {"exclude": ["src/lib/big.ts"], "large_file": 3}})
        r = subprocess.run([sys.executable, RECAL, "measure", "--json", "--repo", d], capture_output=True, text=True)
        m = json.loads(r.stdout)
        self.assertEqual(m["largest"], [["src/lib/db.ts", 5]])
        self.assertEqual(m["large_files"], [["src/lib/db.ts", 5]])

    def test_without_prisma_raw_sql_is_not_measured(self):
        d = self.fixture()
        write(d, "package.json", json.dumps({"name": "demo"}))
        m = json.loads(subprocess.run([sys.executable, RECAL, "measure", "--json", "--repo", d], capture_output=True, text=True).stdout)
        self.assertIsNone(m["raw_sql"])
        self.assertIn("not measured", open(os.path.join(d, "reef", "day-zero.md")).read())


def edit(d, rel, old, new):
    p = os.path.join(d, rel)
    with open(p, encoding="utf-8") as f:
        t = f.read()
    assert old in t, old
    with open(p, "w", encoding="utf-8") as f:
        f.write(t.replace(old, new, 1))


class Assess(unittest.TestCase):
    def test_the_real_report_passes(self):
        r = assess(project())
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("harnessability moderate (3/5) consistent", r.stdout)

    def test_unlabelled_claim_and_proofless_observed_are_rejected(self):
        d = project()
        edit(d, "reef/architecture/architecture.md", "- Observed — `requires-python", "- Python 3.11 is required (`requires-python")
        r = assess(d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("a claim without Observed/Inferred", r.stdout)
        d = project()
        # an Observed claim with no path, line or command behind it, placed in an observed section
        edit(d, "reef/architecture/conventions.md", "## Naming", "- Observed — everything is tidy and well named\n\n## Naming")
        r = assess(d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("Observed without a proving path", r.stdout)

    def test_a_proposal_under_open_needs_no_label(self):
        # the real report's Open and "should take" sections carry unlabelled proposals and pass; the same bullet
        # moved into an observed section is caught
        d = project()
        edit(d, "reef/architecture/architecture.md", "## Open\n", "## Open\n- Reconsider the queue table format\n")
        self.assertEqual(assess(d).returncode, 0)

    def test_harnessability_sum_level_and_dimensions_are_checked(self):
        d = project()
        edit(d, "reef/day-zero.md", "## Harnessability — moderate (3/5)", "## Harnessability — high (5/5)")
        r = assess(d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("says 5/5 but the dimensions sum to 3", r.stdout)
        d = project()
        edit(d, "reef/day-zero.md", "## Harnessability — moderate (3/5)", "## Harnessability — low (3/5)")
        self.assertIn("3/5 is 'moderate', the heading says 'low'", assess(d).stdout)
        d = project()
        edit(d, "reef/day-zero.md", "| Lint baseline |", "| Style baseline |")
        self.assertIn("lacks 'lint baseline'", assess(d).stdout)

    def test_missing_section_or_file_is_rejected(self):
        d = project()
        edit(d, "reef/architecture/conventions.md", "## How it was pushed", "## Git history")
        self.assertIn("no section for 'how it was pushed'", assess(d).stdout)
        d = project()
        os.unlink(os.path.join(d, "reef", "day-zero.md"))
        r = assess(d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing reef/day-zero.md", r.stdout)


if __name__ == "__main__":
    unittest.main()


class RawSqlProposal(unittest.TestCase):
    """0.7.2 (ai-coach, 2026-10-24, item 12): the measure seeds `assess.raw_sql_allow` from today's Unsafe files (a baseline) and
    proposes the raw-SQL gate — or names the project's own guard test instead when it has one."""

    def test_the_proposal_seeds_the_allow_list_or_reuses_a_guard_test(self):
        d = Measure().fixture()
        m = json.loads(subprocess.run([sys.executable, RECAL, "measure", "--json", "--repo", d], capture_output=True, text=True).stdout)
        self.assertEqual(m["raw_sql_proposal"], {"allow": ["src/lib/db.ts"], "reuse": [], "gate": "python3 scripts/reef-structure --raw-sql"})
        rec = open(os.path.join(d, "reef", "recalibration.md")).read()
        self.assertIn('`assess.raw_sql_allow: ["src/lib/db.ts"]`', rec)
        self.assertIn('"raw-sql": "python3 scripts/reef-structure --raw-sql"', rec)
        write(d, "tests/raw-sql-guard.test.ts", "/** Forbids Unsafe raw queries outside lib/db. */\n")
        m = json.loads(subprocess.run([sys.executable, RECAL, "measure", "--json", "--repo", d], capture_output=True, text=True).stdout)
        self.assertEqual(m["raw_sql_proposal"]["reuse"], ["tests/raw-sql-guard.test.ts"])
        self.assertIn("reuse it (keep it in `gates.full`); no new gate is proposed", open(os.path.join(d, "reef", "recalibration.md")).read())
