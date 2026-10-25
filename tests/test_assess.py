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
        # ai-coach, 2026-10-25: 220 of 517 tests matched "never" somewhere in their first lines; only a name or a docblock counts
        write(d, "tests/plans.test.ts", "import { it } from 'vitest';\n\n\nit('a plan is never longer than 12 weeks', () => {});\n")
        write(d, "tests/no-direct-db.test.ts", "import { it } from 'vitest';\n")
        m = json.loads(subprocess.run([sys.executable, RECAL, "measure", "--json", "--repo", d], capture_output=True, text=True).stdout)
        self.assertEqual(m["guard_tests"], ["tests/aimed-writes.test.ts", "tests/no-direct-db.test.ts"], "a test body's 'never' is not a guard; a guard-shaped name is")

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


class Boundaries(unittest.TestCase):
    """0.7.2 (ai-coach, 2026-10-24, item 13): the measure proposes a dependency-cruiser config from the observed layout, with
    today's violations as the known-violations baseline — day one green, only a NEW violation fails."""

    def fixture(self):
        d = project()
        subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
        write(d, ".reef/config.json", json.dumps({"paths": {}}))
        write(d, "package.json", json.dumps({"name": "demo", "dependencies": {"@prisma/client": "6"}}))
        write(d, "tsconfig.json", json.dumps({"compilerOptions": {"paths": {"@/*": ["./src/*"]}}}))
        write(d, "src/lib/prisma.ts", "import { PrismaClient } from '@prisma/client';\nexport const prisma = new PrismaClient();\n")
        write(d, "src/lib/orders.ts", "import { prisma } from './prisma';\nexport const orders = () => prisma.order.findMany();\n")
        write(d, "src/components/Button.tsx", "import { prisma } from '@/lib/prisma';\nexport const B = () => prisma;\n")
        write(d, "src/app/api/x/route.ts", "import { prisma } from '../../../lib/prisma';\nexport const GET = () => prisma;\n")
        write(d, "src/app/api/y/route.ts", "import { orders } from '@/lib/orders';\nexport const GET = () => orders();\n")
        return d

    def measure(self, d):
        r = subprocess.run([sys.executable, RECAL, "measure", "--json", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["boundaries"]

    def test_todays_violations_are_the_baseline_and_a_new_one_is_listed_as_new(self):
        d = self.fixture()
        b = self.measure(d)
        self.assertEqual(b["db_files"], ["src/lib/prisma.ts"])
        self.assertEqual([(k["from"], k["to"], k["rule"]["name"]) for k in b["known"]],
                         [("src/app/api/x/route.ts", "src/lib/prisma.ts", "api-db-through-lib"),
                          ("src/components/Button.tsx", "src/lib/prisma.ts", "components-no-db")], "lib/orders.ts and the y route are fine")
        self.assertEqual(b["new"], [])
        cfg = open(os.path.join(d, ".reef", "recalibration", "proposed", ".dependency-cruiser.cjs")).read()
        self.assertIn("name: 'components-no-db'", cfg)
        self.assertIn("src/lib/prisma\\.ts", cfg)
        self.assertEqual(len(json.load(open(os.path.join(d, ".reef", "recalibration", "proposed", ".dependency-cruiser-known-violations.json")))), 2)
        rec = open(os.path.join(d, "reef", "recalibration.md")).read()
        self.assertIn("## Proposed gate — boundaries (node)", rec)
        self.assertIn("Today's 2 violation(s) are the baseline", rec)
        self.assertIn('"boundaries": "npx depcruise --config .dependency-cruiser.cjs --ignore-known src"', rec)
        # the owner adopts the baseline, then a NEW component reaches the client: listed as new, never folded into the baseline
        shutil.copy(os.path.join(d, ".reef", "recalibration", "proposed", ".dependency-cruiser-known-violations.json"), os.path.join(d, ".dependency-cruiser-known-violations.json"))
        write(d, "src/components/Table.tsx", "import { PrismaClient } from '@prisma/client';\nexport const T = new PrismaClient();\n")
        b = self.measure(d)
        self.assertEqual([(k["from"], k["rule"]["name"]) for k in b["new"]], [("src/components/Table.tsx", "components-no-db")])
        self.assertIn("1 NEW violation(s) since the committed baseline", open(os.path.join(d, "reef", "recalibration.md")).read())

    def test_python_gets_an_adr_draft_only(self):
        d = project()
        subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
        write(d, ".reef/config.json", "{}")
        write(d, "pyproject.toml", "[project]\nname = 'x'\n")
        write(d, "src/x/a.py", "import os\n")
        b = self.measure(d)
        self.assertEqual(b["stack"], "python")
        self.assertTrue(os.path.isfile(os.path.join(d, b["adr_draft"])))
        self.assertIn("An ADR draft only", open(os.path.join(d, "reef", "recalibration.md")).read())


class SensitiveCode(unittest.TestCase):
    """0.7.2 (ai-coach, 2026-10-24, item 22): tiers.design.paths matched none of the 21 files holding access control, tenant isolation
    and money. The measure lists sensitive files by content with file:line and the plan proposes the globs, each with its match count."""

    DEFAULTS = ["**/auth/**", "**/crypto/**", "**/secrets/**", "migrations/**", "prisma/migrations/**", "alembic/**"]

    def test_sensitive_files_are_listed_and_the_proposed_globs_cover_them_while_the_defaults_do_not(self):
        d = Measure().fixture({"tiers": {"design": {"paths": self.DEFAULTS}}})
        write(d, "src/lib/visibility.ts", "export async function scope(tx, tenant) {\n  await tx.$executeRaw`select set_config('app.tenant', ${tenant}, true)`;\n}\n")
        write(d, "src/lib/metering.ts", "// metering\nexport const meterUsage = (userId: string) => quota.check(userId);\n")
        write(d, "src/app/api/sign-in/route.ts", "import { signIn } from 'next-auth/react';\nexport const POST = () => signIn();\n")
        write(d, "src/lib/format.ts", "export const fmt = (n: number) => n.toFixed(2);\n")
        write(d, "reef/architecture/threat-model.md", "# Threat model\n| T1 | tenant data leak | src/lib/visibility.ts scopes every query |\n")
        m = json.loads(subprocess.run([sys.executable, RECAL, "measure", "--json", "--repo", d], capture_output=True, text=True).stdout)
        by = {s["file"]: s for s in m["sensitive"]}
        self.assertEqual(sorted(by), ["src/app/api/sign-in/route.ts", "src/lib/metering.ts", "src/lib/visibility.ts"], "format.ts and big.ts are not sensitive")
        self.assertIn({"kind": "RLS or tenant scoping", "line": 2}, by["src/lib/visibility.ts"]["kinds"])
        self.assertIn({"kind": "named by the threat model", "line": 2}, by["src/lib/visibility.ts"]["kinds"])
        self.assertIn({"kind": "payment, usage, metering or cap", "line": 2}, by["src/lib/metering.ts"]["kinds"], "the comment line never counts")
        self.assertIn({"kind": "sensitive path", "line": 0}, by["src/app/api/sign-in/route.ts"]["kinds"])
        dp = m["design_paths"]
        self.assertEqual(dp["covered_by_current"], [], "the default globs alone match none of them")
        import fnmatch
        for f in by:
            self.assertTrue(any(fnmatch.fnmatch(f, g) or (g.endswith("/**") and f.startswith(g[:-3] + "/")) for g in dp["proposed"]), (f, dp["proposed"]))
        self.assertEqual(dp["counts"]["src/app/api/sign-in/route.ts"], 1)
        self.assertEqual(dp["counts"]["**/auth/**"], 0)
        rec = open(os.path.join(d, "reef", "recalibration.md")).read()
        self.assertIn("## Proposed tiers.design.paths", rec)
        self.assertIn("| `src/app/api/sign-in/route.ts` | 1 | **add** |", rec)
        self.assertIn("RLS or tenant scoping (src/lib/visibility.ts:2)", rec)
        self.assertIn("### Sensitive code, by content", open(os.path.join(d, "reef", "day-zero.md")).read())
