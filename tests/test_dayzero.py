"""Sabotage suite for 0.6 Phase 3: reef-repo (3.2, a mocked gh records the exact calls, a second run issues
none), the Explore lock (3.3), reef-recalibrate + reef-structure (3.4: another ADR format, specs/, rfcs/ and
stray Markdown become Reef ADRs with Supersedes:, an archive tree with its index, the layout, zero broken
links; a file a docs build or code references stays; a second apply moves nothing; git revert restores the
fixture byte for byte; the structure check fails on a stray process document; derived branches match a
develop -> main history)."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.join(ROOT, "scripts", "reef-repo")
RECAL = os.path.join(ROOT, "scripts", "reef-recalibrate")
STRUCT = os.path.join(ROOT, "scripts", "reef-structure")
GUARD = os.path.join(ROOT, "scripts", "reef-guard.py")
INIT = os.path.join(ROOT, "scripts", "reef-init.py")
PROPOSED = os.path.join(".reef", "recalibration", "proposed")   # the plan's; .reef/proposed/ is reef-init's

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
log = os.environ["GH_LOG"]; state = json.load(open(os.environ["GH_STATE"]))
a = sys.argv[1:]
with open(log, "a") as f: f.write(" ".join(a) + "\n")
if a[:2] == ["repo", "view"]:
    print(json.dumps({"nameWithOwner": "o/r", "visibility": "PRIVATE", "owner": {"login": "o"}})); sys.exit(0)
if a[:1] == ["api"] and a[1].endswith("/protection") and "-X" not in a:
    sys.exit(0 if print(json.dumps(state["protection"])) is None and state["protection"] else 1)
if a[:1] == ["api"] and "--jq" in a and a[a.index("--jq") + 1] == ".private":
    print(state.get("private", "false")); sys.exit(0)
if a[:1] == ["api"] and "-X" in a and a[a.index("-X") + 1] == "PUT":
    if state.get("put_403"):
        print("HTTP 403: Upgrade to GitHub Pro or make this repository public to enable this feature.", file=sys.stderr); sys.exit(1)
    state["protection"] = {"required_pull_request_reviews": {}, "required_status_checks": {"checks": [{"context": "every gate, once"}]},
                           "allow_force_pushes": {"enabled": False}, "allow_deletions": {"enabled": False}}
    json.dump(state, open(os.environ["GH_STATE"], "w")); sys.exit(0)
if a[:1] == ["api"] and "--jq" in a and "secret_scanning" in a[a.index("--jq") + 1]:
    print(state["push_protection"]); sys.exit(0)
if a[:1] == ["api"] and "-X" in a and a[a.index("-X") + 1] == "PATCH":
    state["push_protection"] = "enabled"; json.dump(state, open(os.environ["GH_STATE"], "w")); sys.exit(0)
sys.exit(1)
'''


def git(d, *a):
    return subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True, capture_output=True, text=True).stdout


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


class RepoProtection(unittest.TestCase):
    def test_mock_gh_records_exact_calls_and_second_run_issues_none(self):
        tmp = tempfile.mkdtemp(prefix="reef-repo.")
        bin_ = os.path.join(tmp, "bin")
        os.makedirs(bin_)
        with open(os.path.join(bin_, "gh"), "w") as f:
            f.write(FAKE_GH)
        os.chmod(os.path.join(bin_, "gh"), 0o755)
        d = os.path.join(tmp, "proj")
        os.makedirs(d)
        subprocess.run(["git", "init", "-q", d], check=True)
        write(d, ".reef/config.json", json.dumps({"branches": {"base": "develop", "release": "main"}}))
        state = os.path.join(tmp, "state.json")
        log = os.path.join(tmp, "gh.log")
        with open(state, "w") as f:
            json.dump({"protection": {}, "push_protection": "disabled"}, f)
        env = dict(os.environ, PATH=bin_ + os.pathsep + os.environ["PATH"], GH_STATE=state, GH_LOG=log)
        r = subprocess.run([sys.executable, REPO, "--repo", d], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = open(log).read().splitlines()
        self.assertIn("repo view --json nameWithOwner,visibility,owner", calls[0])
        self.assertTrue(any(c.startswith("api -X PUT repos/o/r/branches/main/protection") for c in calls), calls)
        self.assertTrue(any("-X PATCH repos/o/r" in c and "secret_scanning_push_protection" in c for c in calls), calls)
        self.assertTrue(os.path.isfile(os.path.join(d, ".github", "CODEOWNERS")))
        self.assertIn("* @o", open(os.path.join(d, ".github", "CODEOWNERS")).read())
        writes_first = [c for c in calls if "-X PUT" in c or "-X PATCH" in c or c.startswith("repo create")]
        self.assertEqual(len(writes_first), 2)
        open(log, "w").close()
        r = subprocess.run([sys.executable, REPO, "--repo", d], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout)
        calls = open(log).read().splitlines()
        self.assertFalse([c for c in calls if "-X PUT" in c or "-X PATCH" in c or c.startswith("repo create")], f"a second run must issue no write: {calls}")
        self.assertIn("already protected", r.stdout)
        self.assertIn("already enabled", r.stdout)


    def repo_run(self, state):
        tmp = tempfile.mkdtemp(prefix="reef-repo403.")
        bin_ = os.path.join(tmp, "bin")
        os.makedirs(bin_)
        with open(os.path.join(bin_, "gh"), "w") as f:
            f.write(FAKE_GH)
        os.chmod(os.path.join(bin_, "gh"), 0o755)
        d = os.path.join(tmp, "proj")
        os.makedirs(d)
        subprocess.run(["git", "init", "-q", d], check=True)
        write(d, ".reef/config.json", json.dumps({"branches": {"base": "develop", "release": "main"}}))
        with open(os.path.join(tmp, "state.json"), "w") as f:
            json.dump(state, f)
        env = dict(os.environ, PATH=bin_ + os.pathsep + os.environ["PATH"], GH_STATE=os.path.join(tmp, "state.json"), GH_LOG=os.path.join(tmp, "gh.log"))
        return subprocess.run([sys.executable, REPO, "--repo", d], capture_output=True, text=True, env=env)

    def test_a_403_on_a_private_repository_names_the_plan_a_public_one_the_old_message(self):
        # 0.7.2 (ai-coach, 2026-10-24): the protection PUT failed with a bare 403 on a private repository; the cause is the
        # GitHub plan, not a permission — the screen must say so
        r = self.repo_run({"protection": {}, "push_protection": "enabled", "put_403": True, "private": "true"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("COULD NOT protect branch main — gh exited 1: HTTP 403", r.stdout)
        self.assertIn("COULD NOT branch protection on a private repository needs GitHub Pro/Team — until then CI and the local gate are the only wall", r.stdout)
        r = self.repo_run({"protection": {}, "push_protection": "enabled", "put_403": True, "private": "false"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("COULD NOT protect branch main — gh exited 1: HTTP 403", r.stdout)
        self.assertNotIn("GitHub Pro/Team", r.stdout)


class ExploreLock(unittest.TestCase):
    def test_explore_payload_with_a_write_is_denied(self):
        d = tempfile.mkdtemp(prefix="reef-explore.")
        for cmd in ("echo notes > findings.md", "git checkout -b scratch", "sed -i s/a/b/ src/app.py"):
            payload = {"tool_name": "Bash", "cwd": d, "agent_type": "Explore", "agent_id": "e1", "tool_input": {"command": cmd}}
            r = subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, cmd)
        payload = {"tool_name": "Bash", "cwd": d, "agent_type": "Explore", "agent_id": "e1", "tool_input": {"command": "git log --stat -5 && cat package.json"}}
        self.assertEqual(subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True).returncode, 0)


def fixture_repo():
    """An existing project: another ADR format, a specs/ directory, an rfcs/ directory, a runbook, a glossary,
    stray Markdown, a docs build (mkdocs) and a file referenced from code; develop and main branches."""
    d = tempfile.mkdtemp(prefix="reef-recal.")
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    write(d, "README.md", "# proj\nSee [the runbook](ops/runbook.md) and [ADR 1](decisions/0001-use-postgres.md).\n")
    write(d, "LICENSE", "MIT\n")
    write(d, "decisions/0001-use-postgres.md", "# 1. Use Postgres\n\nDate: 2025-01-01\n\n## Status\nAccepted\n\n## Context\nWe need a store.\n\n## Decision\nPostgres.\n\n## Consequences\nOperate a database.\n")
    write(d, "rfcs/0002-event-bus.md", "# RFC 2: event bus\n\n## Context\nServices need to talk.\n\n## Decision\nNATS.\n\n## Consequences\n+ decoupled\n- one more process\n")
    write(d, "specs/export/spec.md", "# CSV export\n\n- the operator exports a month\n- amounts keep two decimals\n\nSee [the ADR](../../decisions/0001-use-postgres.md) and the [design tokens](design-tokens.md).\n")
    write(d, "specs/export/design-tokens.md", "# Tokens\n--ink: #000;\n")          # a sibling the code reads: KEPT in place
    write(d, "src/theme.css", "/* generated from specs/export/design-tokens.md */\n")
    write(d, "specs/old-import/spec.md", "# Importer\nStatus: done\n\n- imports CSV\n")
    write(d, "ops/runbook.md", "# Runbook\nHow to restart the service.\n")
    write(d, "docs/glossary.md", "# Glossary\n| Term | Definition |\n|---|---|\n| Order | one sale |\n")
    write(d, "notes/ideas.md", "# Ideas\nTODO maybe later.\n")
    write(d, "mkdocs.yml", "site_name: proj\ndocs_dir: site\n")
    write(d, "site/index.md", "# Served docs\n## Decision\nthis is a served page, never moved\n")
    write(d, "src/app.py", "HELP = open('help/usage.md').read()\n")
    write(d, "help/usage.md", "# Usage\n## Runbook\nreferenced from code, never moved\n")
    write(d, ".reef/config.json", json.dumps({"gates": {"full": "true"}, "paths": {"queue": "reef/queue.md", "features": "reef/features", "adr": "reef/architecture/adr", "glossary": "reef/glossary.md"}}))
    write(d, ".reef/version", "0.6.0\n")
    write(d, "reef/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 1 | first | | planned | 1 | |\n")
    git(d, "add", "-A")
    git(d, "commit", "-qm", "feat: initial")
    git(d, "checkout", "-qb", "develop")
    write(d, "src/more.py", "x = 1\n")
    git(d, "add", "-A")
    git(d, "commit", "-qm", "fix: more")
    git(d, "checkout", "-q", "main")
    git(d, "merge", "-q", "--no-ff", "--no-edit", "develop")
    git(d, "tag", "v0.1.0")
    return d


def tree_hash(d):
    h = hashlib.sha256()
    for dp, dn, fn in os.walk(d):
        dn[:] = sorted(x for x in dn if x not in (".git", ".reef"))
        for f in sorted(fn):
            p = os.path.join(dp, f)
            h.update(os.path.relpath(p, d).encode() + b"\0" + open(p, "rb").read() + b"\0")
    return h.hexdigest()


class Recalibrate(unittest.TestCase):
    def run_(self, d, *args):
        return subprocess.run([sys.executable, RECAL, *args, "--repo", d], capture_output=True, text=True)

    def test_moved_spec_keeps_its_link_to_a_kept_sibling(self):
        # 0.7 dogfood (ai-coach, 839 Markdown files): a spec linked to `design-decisions.md` beside it, a file the plan
        # itself KEPT (referenced from code); the converted spec and its archive copy then carried a dead link and the
        # whole apply was refused. A moved document's links are relative to where it came from.
        d = fixture_repo()
        self.assertEqual(self.run_(d, "plan").returncode, 0)
        plan = json.loads(open(os.path.join(d, ".reef", "recalibration.json")).read())
        by = {e["path"]: e for e in plan["entries"]}
        self.assertEqual(by["specs/export/design-tokens.md"]["action"], "keep", "referenced from code")
        git(d, "add", "-A"); git(d, "commit", "-qm", "chore: plan")
        r = self.run_(d, "--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        date = plan["date"]
        archived = open(os.path.join(d, "reef", "archive", date, "specs", "export", "spec.md")).read()
        self.assertIn("(../../../../../specs/export/design-tokens.md)", archived)
        self.assertTrue(os.path.isfile(os.path.join(d, "specs", "export", "design-tokens.md")), "the kept sibling never moved")

    def test_slugs_drop_id_tokens_and_never_collide(self):
        # 0.7 dogfood (ai-coach): 96 feature slugs began with an id token (`014a-tenant-schema`), which the slug rule
        # refuses, and 13 specs shared a title with another, so the later SPEC.md overwrote the earlier one
        d = fixture_repo()
        write(d, "specs/014a-tenant-schema/spec.md", "# Tenant schema\n\n- one schema per tenant\n")
        write(d, "specs/311-review-round/spec.md", "# Review round\n\n- a round\n")
        write(d, "specs/412-review-round/spec.md", "# Review round\n\n- another round\n")
        git(d, "add", "-A"); git(d, "commit", "-qm", "chore: more specs")
        self.assertEqual(self.run_(d, "plan").returncode, 0)
        plan = json.loads(open(os.path.join(d, ".reef", "recalibration.json")).read())
        by = {e["path"]: e for e in plan["entries"]}
        self.assertEqual(by["specs/014a-tenant-schema/spec.md"]["feature"], "tenant-schema")
        feats = {by["specs/311-review-round/spec.md"]["feature"], by["specs/412-review-round/spec.md"]["feature"]}
        self.assertEqual(len(feats), 2, feats)
        self.assertIn("review-round", feats)
        git(d, "add", "-A"); git(d, "commit", "-qm", "chore: plan")
        r = self.run_(d, "--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(subprocess.run([sys.executable, STRUCT, "--check", "--repo", d], capture_output=True, text=True).returncode, 0)
        for f in feats:
            self.assertTrue(os.path.isfile(os.path.join(d, "reef", "features", f, "SPEC.md")))

    def test_a_link_broken_before_the_apply_does_not_block_it(self):
        # 0.7 dogfood (ai-coach): seven links were already dead before any move (screenshots never committed, source
        # files renamed); the apply must only refuse on links IT breaks, and say which were dead already
        d = fixture_repo()
        write(d, "ops/runbook.md", "# Runbook\nHow to restart the service. See [the old diagram](diagram.png).\n")
        git(d, "add", "-A"); git(d, "commit", "-qm", "chore: a dead link")
        self.assertEqual(self.run_(d, "plan").returncode, 0)
        git(d, "add", "-A"); git(d, "commit", "-qm", "chore: plan")
        r = self.run_(d, "--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("already broken before the apply", r.stdout)
        self.assertIn("diagram.png", r.stdout)

    def test_structure_check_is_not_fooled_by_the_plan_file_or_logs(self):
        # 0.7 dogfood: `.reef/recalibration.json` names every document and CI logs quote spec paths, so the
        # "referenced from code" exemption excused 800+ stray documents and the structure check printed ok
        d = fixture_repo()
        self.assertEqual(self.run_(d, "plan").returncode, 0)
        write(d, "evidence/run-1.log", "checking rfcs/0002-event-bus.md ... ok\n")
        git(d, "add", "-A"); git(d, "commit", "-qm", "chore: plan + a log")
        r = subprocess.run([sys.executable, STRUCT, "--check", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("rfcs/0002-event-bus.md", r.stdout)
        # and a second `plan` still classifies the RFC as a conversion, not as kept
        self.assertEqual(self.run_(d, "plan").returncode, 0)
        plan = json.loads(open(os.path.join(d, ".reef", "recalibration.json")).read())
        self.assertEqual({e["path"]: e for e in plan["entries"]}["rfcs/0002-event-bus.md"]["action"], "convert-adr")

    def test_plan_apply_revert(self):
        d = fixture_repo()
        before = tree_hash(d)
        r = self.run_(d, "history")
        self.assertEqual(r.returncode, 0, r.stderr)
        hist = json.loads(r.stdout)
        self.assertEqual(hist["derived"], {"branches.base": "develop", "branches.release": "main", "merge.by": "loop", "ci.feature_gate": "local"})
        self.assertEqual(hist["conventional_commits_share"], 1.0)
        self.assertTrue(hist["semver_tags"])
        r = self.run_(d, "plan")
        self.assertEqual(r.returncode, 0, r.stderr)
        plan = json.loads(open(os.path.join(d, ".reef", "recalibration.json")).read())
        by = {e["path"]: e for e in plan["entries"]}
        self.assertEqual(by["decisions/0001-use-postgres.md"]["action"], "convert-adr")
        self.assertEqual(by["rfcs/0002-event-bus.md"]["action"], "convert-adr")
        self.assertEqual(by["specs/export/spec.md"]["action"], "convert-feature")
        self.assertEqual(by["specs/old-import/spec.md"]["action"], "archive")
        self.assertEqual(by["ops/runbook.md"]["action"], "archive")
        self.assertEqual(by["docs/glossary.md"]["action"], "merge-glossary")
        self.assertEqual(by["notes/ideas.md"]["action"], "archive")
        self.assertEqual(by["README.md"]["action"], "keep")
        self.assertEqual(by["site/index.md"]["action"], "keep", "served by mkdocs")
        self.assertEqual(by["help/usage.md"]["action"], "keep", "referenced from code")
        self.assertIn("referenced by src/app.py", by["help/usage.md"]["reason"])
        md = open(os.path.join(d, "reef", "recalibration.md")).read()
        self.assertIn("| keep | `help/usage.md` | — | referenced by src/app.py |", md)
        # the plan is not an apply: nothing moved yet
        self.assertTrue(os.path.isfile(os.path.join(d, "decisions", "0001-use-postgres.md")))
        git(d, "add", "-A")
        git(d, "commit", "-qm", "chore: plan")
        r = self.run_(d, "--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        date = plan["date"]
        adr = os.path.join(d, "reef", "architecture", "adr", "0001-use-postgres.md")
        self.assertTrue(os.path.isfile(adr))
        text = open(adr).read()
        # 0.7.2 (ai-coach, item 21): a numbered ADR is the same record moved, its number kept — no Supersedes, no archive copy
        self.assertIn("# 1. Use Postgres", text)
        self.assertNotIn("Supersedes:", text)
        self.assertTrue(os.path.isfile(os.path.join(d, "reef", "architecture", "adr", "0002-event-bus.md")))
        self.assertFalse(os.path.isfile(os.path.join(d, "reef", "archive", date, "decisions", "0001-use-postgres.md")))
        self.assertTrue(os.path.isfile(os.path.join(d, "reef", "archive", date, "ops", "runbook.md")))
        self.assertTrue(os.path.isfile(os.path.join(d, "reef", "features", "export", "SPEC.md")) or any(
            os.path.isfile(os.path.join(d, "reef", "features", f, "SPEC.md")) for f in os.listdir(os.path.join(d, "reef", "features"))))
        spec_dir = [f for f in os.listdir(os.path.join(d, "reef", "features")) if os.path.isdir(os.path.join(d, "reef", "features", f))][0]
        spec = open(os.path.join(d, "reef", "features", spec_dir, "SPEC.md")).read()
        self.assertIn("FR-1 [backend]: the operator exports a month", spec)
        self.assertIn("Row: 2", spec)
        self.assertIn("| 2 |", open(os.path.join(d, "reef", "queue.md")).read())
        self.assertIn("| Order | one sale |", open(os.path.join(d, "reef", "glossary.md")).read())
        self.assertIn("| `ops/runbook.md` |", open(os.path.join(d, "reef", "archive", "README.md")).read())
        self.assertTrue(os.path.isfile(os.path.join(d, "site", "index.md")), "served docs never move")
        self.assertTrue(os.path.isfile(os.path.join(d, "help", "usage.md")), "referenced docs never move")
        readme = open(os.path.join(d, "README.md")).read()
        self.assertIn(f"(reef/archive/{date}/ops/runbook.md)", readme, "links rewritten to the new home")
        self.assertIn("(reef/architecture/adr/0001-use-postgres.md)", readme, "a converted decision's link points at the ADR")
        self.assertEqual(git(d, "status", "--porcelain").strip(), "", "the apply is ONE commit")
        self.assertIn("reef recalibration", git(d, "log", "-1", "--format=%s"))
        r = subprocess.run([sys.executable, STRUCT, "--check", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        r = self.run_(d, "--apply")
        self.assertEqual(r.returncode, 1)
        self.assertIn("nothing to do", r.stdout)
        # undo is one revert; the fixture comes back byte for byte (reef/ additions aside)
        git(d, "revert", "--no-edit", "HEAD")        # the apply
        git(d, "revert", "--no-edit", "HEAD~2")     # the plan commit (HEAD~1 is now the revert itself)
        self.assertEqual(tree_hash(d), before, "git revert of the apply (and the plan) restores the fixture byte for byte")

    def test_structure_check_fails_on_a_stray_process_document_and_knows_both_layouts(self):
        d = fixture_repo()
        r = subprocess.run([sys.executable, STRUCT, "--check", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("decisions/0001-use-postgres.md: a process document outside the layout", r.stdout)
        self.assertNotIn("site/index.md", r.stdout, "served docs are the product's")
        self.assertNotIn("help/usage.md", r.stdout, "referenced from code")
        # a 0.5 project: docs/adr and tasks/ are the layout
        d5 = tempfile.mkdtemp(prefix="reef-struct05.")
        subprocess.run(["git", "init", "-q", d5], check=True)
        write(d5, "docs/adr/0001-x.md", "# x\n## Decision\ny\n## Consequences\nz\n")
        write(d5, "docs/queue.md", "# Queue\n")
        write(d5, ".reef/config.json", "{}")
        git(d5, "add", "-A")
        git(d5, "commit", "-qm", "init")
        self.assertEqual(subprocess.run([sys.executable, STRUCT, "--check", "--repo", d5], capture_output=True, text=True).returncode, 0)

    def test_broken_link_refuses_the_apply_and_restores(self):
        d = fixture_repo()
        write(d, "notes/ideas.md", "# Ideas\nTODO see [missing](nowhere.md).\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "chore: broken link")
        self.run_(d, "plan")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "chore: plan")
        head = git(d, "rev-parse", "HEAD").strip()
        r = self.run_(d, "--apply")
        # 0.7: a link that was dead BEFORE the apply is not the apply's to fix — it travels as it was, the apply says
        # so, and still commits; the refusal is reserved for links the apply itself breaks (ai-coach had 7 dead links
        # and could never have been recalibrated under the old rule)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("already broken before the apply", r.stdout)
        self.assertIn("nowhere.md", r.stdout)
        self.assertNotEqual(git(d, "rev-parse", "HEAD").strip(), head, "the apply committed")
        self.assertEqual(git(d, "status", "--porcelain").strip(), "", "one commit, clean tree")
        date = json.loads(open(os.path.join(d, ".reef", "recalibration.json")).read())["date"]
        self.assertIn("(nowhere.md)", open(os.path.join(d, "reef", "archive", date, "notes", "ideas.md")).read(), "the dead link travelled unchanged")


if __name__ == "__main__":
    unittest.main()


class RawSqlCheck(unittest.TestCase):
    """0.7.2 (ai-coach, 2026-10-24, item 12): `reef-structure --raw-sql` fails on an Unsafe raw query in a file outside
    `assess.raw_sql_allow` (the measured baseline); an allowed file and a comment line are green."""

    def project(self, files):
        d = tempfile.mkdtemp(prefix="reef-rawsql.")
        subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
        write(d, ".reef/config.json", json.dumps({"assess": {"raw_sql_allow": ["src/legacy.ts"]}}))
        for rel, text in files.items():
            write(d, rel, text)
        return subprocess.run([sys.executable, STRUCT, "--raw-sql", "--repo", d], capture_output=True, text=True)

    def test_a_new_unsafe_call_is_red_an_allowed_file_and_a_comment_are_green(self):
        r = self.project({"src/legacy.ts": "prisma.$executeRawUnsafe(sql);\n",
                          "src/ok.ts": "// prisma.$queryRawUnsafe is forbidden\n * also $executeRawUnsafe\nconst r = prisma.$queryRaw`select 1`;\n"})
        self.assertEqual(r.returncode, 0, r.stdout)
        r = self.project({"src/legacy.ts": "prisma.$executeRawUnsafe(sql);\n", "src/new.ts": "const x = 1;\nconst r = prisma.$queryRawUnsafe(q);\n"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("src/new.ts:2: an Unsafe raw query outside assess.raw_sql_allow", r.stdout)
        self.assertNotIn("src/legacy.ts", r.stdout)


class SizeRatchet(unittest.TestCase):
    """0.7.2 (ai-coach, 2026-10-24, item 14): `reef-structure --sizes` — a baselined file may not grow, a new file may not be born
    over structure.new_file_lines, shrinking lowers the baseline in the same run; tests and i18n are ignored."""

    def project(self):
        d = tempfile.mkdtemp(prefix="reef-sizes.")
        subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
        write(d, ".reef/config.json", json.dumps({"structure": {"new_file_lines": 400}}))
        write(d, "src/a.ts", "a\n" * 10)
        write(d, "reef/size-baseline.json", json.dumps({"generated": "2026-10-24", "large_file": 800, "files": {"src/a.ts": 10}}))
        git(d, "add", "-A"); git(d, "commit", "-qm", "baseline")
        return d

    def sizes(self, d):
        return subprocess.run([sys.executable, STRUCT, "--sizes", "--repo", d], capture_output=True, text=True)

    def test_grow_is_red_new_big_file_is_red_shrink_lowers_the_baseline_tests_and_i18n_ignored(self):
        d = self.project()
        self.assertEqual(self.sizes(d).returncode, 0, "nothing changed: green")
        write(d, "src/a.ts", "a\n" * 12)
        r = self.sizes(d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("src/a.ts: 12 lines, over its baseline of 10", r.stdout)
        write(d, "src/a.ts", "a\n" * 10)
        write(d, "src/new.ts", "b\n" * 401)
        r = self.sizes(d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("src/new.ts: a new file of 401 lines, over structure.new_file_lines (400)", r.stdout)
        os.remove(os.path.join(d, "src", "new.ts"))
        write(d, "src/ok.ts", "b\n" * 400)
        write(d, "tests/huge.test.ts", "t\n" * 1000)
        write(d, "src/i18n/ar.ts", "x\n" * 3000)
        write(d, "src/a.ts", "a\n" * 8)
        r = self.sizes(d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("1 baseline(s) lowered", r.stdout)
        self.assertEqual(json.load(open(os.path.join(d, "reef", "size-baseline.json")))["files"], {"src/a.ts": 8})
        write(d, "src/a.ts", "a\n" * 9)
        self.assertEqual(self.sizes(d).returncode, 1, "the ratchet: 9 is over the lowered baseline of 8")


class RecalibrationSafety(unittest.TestCase):
    """0.7.2 (ai-coach, 2026-10-24, item 16): the plan keeps documents a tool reads by DIRECTORY, licences anywhere, documents edited
    on an unmerged branch; `plan --measure` applies the plan in a scratch worktree, runs the gates there and leaves the tree untouched.
    On ai-coach the full plan moved 735 documents and caused 603 check:docs errors, 4 red tests, an archived font licence and 4 conflicts."""

    def plan(self, d, *a):
        r = subprocess.run([sys.executable, RECAL, "plan", *a, "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return {e["path"]: e for e in json.loads(open(os.path.join(d, ".reef", "recalibration.json")).read())["entries"]}, r.stdout

    def test_a_directory_a_tool_reads_a_licence_anywhere_and_an_unmerged_edit_are_kept(self):
        d = fixture_repo()
        write(d, "package.json", json.dumps({"name": "x", "scripts": {"check:docs": "node scripts/check-docs.js docs/loop/"}}))
        write(d, "scripts/check-docs.js", "// walks the directory it is given\n")
        write(d, "docs/loop/queue.md", "# Loop queue\n\n## Decision\nold rows\n\n## Consequences\nx\n")
        write(d, "docs/loop/notes.md", "# Notes\nTODO later\n")
        write(d, "public/fonts/OFL.md", "# SIL Open Font License\n## Decision\nthe font's licence text\n## Consequences\nx\n")
        write(d, "public/fonts/Inter.ttf", "binary")
        write(d, "public/fonts/README-fonts.md", "# Fonts\n## Runbook\nhow the fonts were built\n")
        write(d, "docs/legal/LICENSE-images.md", "# Image licence\n## Status\nx\n## Decision\ny\n## Consequences\nz\n")
        git(d, "add", "-A"); git(d, "commit", "-qm", "a loop, fonts, licences")
        git(d, "checkout", "-qb", "wip")
        write(d, "ops/runbook.md", "# Runbook\nHow to restart the service — edited on wip.\n")
        git(d, "add", "-A"); git(d, "commit", "-qm", "wip edit")
        git(d, "checkout", "-q", "main")
        by, _ = self.plan(d)
        self.assertEqual((by["docs/loop/queue.md"]["action"], by["docs/loop/queue.md"]["reason"]), ("keep", "directory docs/loop/ read by package.json"))
        self.assertEqual(by["docs/loop/notes.md"]["action"], "keep", "every document under a read directory stays")
        self.assertEqual(by["public/fonts/OFL.md"]["reason"], "a licence (kept wherever it is, under any name)")
        self.assertEqual(by["docs/legal/LICENSE-images.md"]["action"], "keep")
        self.assertEqual(by["public/fonts/README-fonts.md"]["reason"], "beside an asset's licence (fonts, images, binaries)")
        self.assertEqual((by["ops/runbook.md"]["action"], by["ops/runbook.md"]["reason"]), ("keep", "edited on unmerged branch wip"))
        self.assertEqual(by["notes/ideas.md"]["action"], "archive", "a stray document still moves")

    def test_measure_reports_a_gate_that_reads_a_moved_file_and_leaves_the_tree_untouched(self):
        d = fixture_repo()
        cfg = json.loads(open(os.path.join(d, ".reef", "config.json")).read())
        cfg["gates"]["full"] = "cat ops/runbook.md"     # a gate that reads a document the plan archives (config is not grepped)
        write(d, ".reef/config.json", json.dumps(cfg))
        write(d, "package.json", json.dumps({"name": "x", "scripts": {"check:docs": "d=notes; test -f $d/ideas.md || { echo 'error: ideas missing'; exit 1; }"}}))
        git(d, "add", "-A"); git(d, "rm", "-q", "--cached", ".reef/config.json"); git(d, "commit", "-qm", "a gate on a document; the config untracked, as on a real project")
        head = git(d, "rev-parse", "HEAD")
        by, out = self.plan(d, "--measure")
        self.assertEqual((by["ops/runbook.md"]["action"], by["notes/ideas.md"]["action"]), ("archive", "archive"), "the plan itself still moves them (nothing grep can see names them)")
        self.assertIn("| gates.full | 1 |", out)
        self.assertRegex(out, r"\| check:docs \| 1 \| [1-9]\d* \| 0 \|", "exit 1 and at least the script's own error line (npm adds its own)")
        self.assertIn("this plan leaves a gate red", out)
        self.assertIn("## Measured cost of this plan", open(os.path.join(d, "reef", "recalibration.md")).read())
        self.assertTrue(os.path.isfile(os.path.join(d, "ops", "runbook.md")), "the tree here was not touched")
        self.assertEqual(git(d, "rev-parse", "HEAD"), head)
        self.assertEqual([l for l in git(d, "status", "--porcelain").splitlines() if not l.endswith(("recalibration.md", "recalibration.json", "instruction-layer.md", ".reef/config.json"))], [], "the plan files and the untracked config are the only change")
        self.assertEqual(len(git(d, "worktree", "list").splitlines()), 1, "the scratch worktree is gone")
        # ai-coach, 2026-10-25: when the scratch apply itself fails the gates must not run against an unchanged worktree
        write(d, "docs/loop/queue.md", "# Loop queue\n\n| id | item | status |\n|---|---|---|\n| 9 | wip (feat/wip) | open |\n")
        git(d, "add", "-A"); git(d, "commit", "-qm", "an old queue claiming a branch")
        git(d, "checkout", "-qb", "feat/wip"); write(d, "src/w.py", "x\n"); git(d, "add", "-A"); git(d, "commit", "-qm", "wip"); git(d, "checkout", "-q", "main")
        _, out = self.plan(d, "--measure")
        self.assertIn("| apply (scratch) | 1 |", out)
        self.assertIn("(the apply did not run: ", out)
        self.assertNotIn("| gates.full |", out, "no gate ran on an unchanged worktree")


class StructureBaselineIsThePlan(unittest.TestCase):
    """0.7.3 (ai-coach, 2026-10-25): `structure --check` found 507 documents the plan had KEPT for a reader (specs/ read by check:docs),
    so the gate could not be switched on. A document the plan kept for a reader is the baseline; a new stray document still fails."""

    def project(self):
        d = tempfile.mkdtemp(prefix="reef-struct-base.")
        subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
        write(d, ".reef/version", "0.7.2\n")
        write(d, ".reef/config.json", json.dumps({"paths": {"queue": "reef/queue.md"}}))
        write(d, "specs/export/spec.md", "# Export\n\n## Requirements\n- a month\n")
        write(d, "design_handoff/notes.md", "# Notes\n\n## Decision\nkeep\n\n## Consequences\nx\n")
        write(d, "reef/queue.md", "# Queue\n")
        git(d, "add", "-A"); git(d, "commit", "-qm", "init")
        return d

    def check(self, d):
        return subprocess.run([sys.executable, STRUCT, "--check", "--repo", d], capture_output=True, text=True)

    def test_a_document_the_plan_kept_for_a_reader_is_the_baseline_a_new_stray_still_fails(self):
        d = self.project()
        r = self.check(d)
        self.assertEqual(r.returncode, 1, "no plan: both documents are strays")
        write(d, ".reef/recalibration.json", json.dumps({"date": "2026-10-25", "entries": [
            {"path": "specs/export/spec.md", "action": "keep", "reason": "directory specs/ read by package.json"},
            {"path": "design_handoff/notes.md", "action": "keep", "reason": "waits: package.json reads design_handoff/ (a retire row is created)", "blocked_by": "package.json reads design_handoff/"}]}))
        r = self.check(d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("note: 2 document(s) kept by the recalibration plan for a reader are the baseline", r.stdout)
        write(d, "specs/new/spec.md", "# New\n\n## Requirements\n- new\n")
        git(d, "add", "-A")   # the check reads tracked files
        r = self.check(d)
        self.assertEqual(r.returncode, 1, "a document the plan never saw is a stray")
        self.assertIn("specs/new/spec.md: a process document outside the layout", r.stdout)
        self.assertNotIn("specs/export/spec.md", r.stdout)
        write(d, ".reef/recalibration.json", json.dumps({"date": "2026-10-25", "entries": [{"path": "specs/export/spec.md", "action": "keep", "reason": "a spec whose work is done"}]}))
        r = self.check(d)
        self.assertIn("specs/export/spec.md: a process document outside the layout", r.stdout, "a keep for another reason is not a reader baseline")


class StructureHonoursConfigPaths(unittest.TestCase):
    """0.7.2 (ai-coach, 2026-10-24, item 17): reef-structure accepts the places .reef/config.json paths.* names whatever the
    version — init adopted docs/adr as the ADR home and the check then flagged every ADR in it."""

    def project(self, adr_home):
        d = tempfile.mkdtemp(prefix="reef-struct-paths.")
        subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
        write(d, ".reef/version", "0.7.1\n")
        write(d, ".reef/config.json", json.dumps({"paths": {"adr": adr_home, "queue": "docs/queue.md", "runlog": "docs/journal.md"}}))
        write(d, "docs/adr/0001-x.md", "# ADR 0001 — x\n\n## Status\nAccepted\n\n## Context\nc\n\n## Decision\nd\n")
        write(d, "docs/queue.md", "# Queue\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n")
        git(d, "add", "-A"); git(d, "commit", "-qm", "init")
        return subprocess.run([sys.executable, STRUCT, "--check", "--repo", d], capture_output=True, text=True)

    def test_the_configured_adr_home_is_ok_and_another_one_is_flagged(self):
        r = self.project("docs/adr")
        self.assertEqual(r.returncode, 0, r.stdout)
        r = self.project("reef/architecture/adr")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("docs/adr/0001-x.md: a process document outside the layout", r.stdout)


class InstructionLayer(unittest.TestCase):
    """0.7.2 (ai-coach, 2026-10-24, item 19): CLAUDE.md, AGENTS.md and CLAUDE-CODE-PROMPT.md pointed every session at the old
    process. The plan lists each pointer and conflicting rule with file:line, proposes a rewrite that keeps product content and
    another tool's block byte for byte, merges a duplicate CLAUDE file, and counts those files as readers."""

    FOREIGN = "<!-- BEGIN:nextjs-agent-rules -->\n# Next.js rules\n- never edit .next/\n<!-- END:nextjs-agent-rules -->\n"

    def fixture(self):
        d = fixture_repo()
        write(d, "AGENTS.md", "# ai-coach — agents\n\nAn AI coach for runners: Next.js 16, Prisma, Vitest.\n\n## Non-negotiables\n"
                              "- there is deliberately no linter — adopting one is its own item with an argued ruleset\n\n## Process\n"
                              "Read HANDOFF-FRESH.md first, then docs/loop/queue.md.\nStart every session with /loop-start and close with `npm run loop:close`.\n"
                              "Number ADRs with loop:adr. Run up to 15 agents.\n\n" + self.FOREIGN)
        write(d, "CLAUDE.md", "# Claude notes\n\nThe product: coaching plans.\n\nSee docs/coaching-model.md for the domain model.\n")
        write(d, "CLAUDE-CODE-PROMPT.md", "# Prompt\n\nAlways read HANDOFF-FRESH.md first.\n")
        write(d, "HANDOFF-FRESH.md", "# Handoff (fresh)\n## Runbook\nnothing merges into develop until promotion 11\n")
        write(d, "docs/loop/queue.md", "# Loop queue\n\n| id | item | status |\n|---|---|---|\n| 1 | x | open |\n")
        write(d, "docs/coaching-model.md", "# Coaching model\n\n## Decision\nperiodisation\n\n## Consequences\nweekly plans\n")
        git(d, "add", "-A"); git(d, "commit", "-qm", "the old process in the instruction layer")
        return d

    def test_pointers_and_rules_are_listed_with_lines_and_a_doc_read_only_by_claude_md_is_kept(self):
        d = self.fixture()
        r = subprocess.run([sys.executable, RECAL, "plan", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        plan = json.loads(open(os.path.join(d, ".reef", "recalibration.json")).read())
        by = {e["path"]: e for e in plan["entries"]}
        agents = next(e for e in plan["instruction_layer"]["files"] if e["file"] == "AGENTS.md")
        self.assertIn([9, "HANDOFF-FRESH.md"], [p[:2] for p in agents["pointers"]])
        self.assertIn([9, "docs/loop/queue.md"], [p[:2] for p in agents["pointers"]])
        claude = next(e for e in plan["instruction_layer"]["files"] if e["file"] == "CLAUDE.md")
        self.assertEqual(claude["pointers"], [[5, "docs/coaching-model.md", False]], "a pointer to a KEPT document is listed and stays")
        self.assertFalse(os.path.exists(os.path.join(d, PROPOSED, "CLAUDE.md")), "nothing to rewrite in CLAUDE.md")
        kinds = {(n, k) for n, k, _ in agents["rules"]}
        self.assertIn((10, "start command"), kinds)
        self.assertIn((11, "ADR numbering"), kinds)
        self.assertEqual([n for n, _ in agents["outranks"]], [6], "the no-linter rule is surfaced, never overridden")
        self.assertEqual(plan["instruction_layer"]["duplicates"], ["CLAUDE-CODE-PROMPT.md"])
        self.assertEqual((by["docs/coaching-model.md"]["action"], by["docs/coaching-model.md"]["reason"]), ("keep", "referenced by CLAUDE.md"))
        layer = open(os.path.join(d, "reef", "instruction-layer.md")).read()
        self.assertIn("rule, start command: `Start every session with /loop-start and close with `npm run loop:close`.` (AGENTS.md:10)", layer)
        self.assertIn("pointer → `HANDOFF-FRESH.md` (AGENTS.md:9)", layer)
        self.assertIn("DUPLICATE of the primary CLAUDE file", layer)
        self.assertIn("read the diff first: `git diff --no-index AGENTS.md .reef/recalibration/proposed/AGENTS.md`", open(os.path.join(d, "reef", "recalibration.md")).read())
        proposed = open(os.path.join(d, PROPOSED, "AGENTS.md")).read()
        self.assertIn(self.FOREIGN, proposed, "another tool's block is byte-identical")
        self.assertIn("An AI coach for runners: Next.js 16, Prisma, Vitest.", proposed, "product content kept verbatim")
        self.assertIn("there is deliberately no linter", proposed, "the project's rule stays")
        self.assertNotIn("/loop-start", proposed)
        self.assertIn("Process: this project runs on Reef. Read `HANDOFF.md` first", proposed)
        git(d, "add", "-A"); git(d, "commit", "-qm", "plan")
        r = subprocess.run([sys.executable, RECAL, "--apply", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(open(os.path.join(d, "AGENTS.md")).read(), proposed, "applied in the one commit")
        self.assertFalse(os.path.exists(os.path.join(d, PROPOSED, "AGENTS.md")), "an applied rewrite is not left waiting")
        self.assertFalse(os.path.isfile(os.path.join(d, "CLAUDE-CODE-PROMPT.md")))
        claude_md = open(os.path.join(d, "CLAUDE.md")).read()
        self.assertIn("The product: coaching plans.", claude_md, "product content kept")
        self.assertIn("## Carried over from CLAUDE-CODE-PROMPT.md", claude_md)
        self.assertTrue(os.path.isfile(os.path.join(d, "docs", "coaching-model.md")), "a document only CLAUDE.md names stays in place")
        self.assertEqual(git(d, "status", "--porcelain").strip(), "", "one commit")

    def test_reefs_own_scripts_never_read_keep_or_block_a_document(self):
        """0.7.3 (ai-coach, 2026-10-25): after reef-init, Reef's own scripts/reef-* name `specs/`, `docs/`, HANDOFF-FRESH.md in
        comments and code; the plan counted them as the project's readers — specs/ and the glossary kept, the old queue retired
        behind four reef-* scripts, scripts/reef-recalibrate repointed by its own apply, which then refused on a "broken link"."""
        d = self.fixture()
        r = subprocess.run([sys.executable, INIT, "--root", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        git(d, "add", "-A"); git(d, "commit", "-qm", "init")
        r = subprocess.run([sys.executable, RECAL, "plan", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        plan = json.loads(open(os.path.join(d, ".reef", "recalibration.json")).read())
        reef_code = [rd for rd in plan["adoption"]["readers"] if rd["reader"].startswith(("scripts/reef-", ".githooks/"))]
        self.assertEqual(reef_code, [], "Reef's own code is not the project's reader")
        self.assertEqual([e["path"] for e in plan["entries"] if "scripts/reef-" in e["reason"] + str(e.get("blocked_by", ""))], [])
        before = open(os.path.join(d, "scripts", "reef-recalibrate"), "rb").read()
        git(d, "add", "-A"); git(d, "commit", "-qm", "plan")
        r = subprocess.run([sys.executable, RECAL, "--apply", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(open(os.path.join(d, "scripts", "reef-recalibrate"), "rb").read(), before, "the apply never edits Reef's own script")

    def test_the_plan_leaves_reef_inits_proposals_alone_and_the_apply_clears_its_own(self):
        """0.7.3 (ai-coach, 2026-10-25): the plan wrote its AGENTS.md rewrite to .reef/proposed/AGENTS.md, over reef-init's own
        proposal for the same file; the doctor then advised `reef-init --accept AGENTS.md`, which recorded the rewrite as Reef's
        rendering, and the next reef-update replaced AGENTS.md with the template: the product text and the project's rule gone."""
        d = self.fixture()
        write(d, ".gitignore", ".reef/proposed/\n.reef/recalibration/\n")
        init_proposal = write(d, ".reef/proposed/AGENTS.md", "# reef-init's rendering of AGENTS.md, waiting for --accept or --keep\n")
        git(d, "add", ".gitignore"); git(d, "commit", "-qm", "init")
        r = subprocess.run([sys.executable, RECAL, "plan", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(os.listdir(os.path.join(d, ".reef", "proposed"))), ["AGENTS.md"], "the plan adds nothing to reef-init's proposals")
        self.assertEqual(open(init_proposal).read(), "# reef-init's rendering of AGENTS.md, waiting for --accept or --keep\n")
        self.assertTrue(os.path.isfile(os.path.join(d, PROPOSED, "AGENTS.md")))
        git(d, "add", "-A"); git(d, "commit", "-qm", "plan")
        r = subprocess.run([sys.executable, RECAL, "--apply", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("An AI coach for runners", open(os.path.join(d, "AGENTS.md")).read())
        self.assertEqual(os.listdir(os.path.join(d, PROPOSED)), [], "what the apply applied is not left waiting")
        self.assertTrue(os.path.isfile(init_proposal), "reef-init's proposal is the owner's to accept or keep")
        self.assertEqual(git(d, "status", "--porcelain").strip(), "", "one commit")

class WholeAdoption(unittest.TestCase):
    """0.7.2 (ai-coach, 2026-10-24, item 18): the plan covers the whole adoption — the old queue's open rows become Reef rows, the
    second handoff is merged into HANDOFF.md, readers are repointed, holds are named, and the hand-off line says complete or
    partial; an old loop with work in flight refuses the migration and names the branch."""

    OLD_QUEUE = ("# Loop queue\n\n| id | item | status |\n|---|---|---|\n| 1 | M1 schema | done |\n| 2 | M2 api | open |\n"
                 "| 3 | M3 ui | in progress |\n")

    def fixture(self, in_flight=False):
        d = fixture_repo()
        write(d, "docs/loop/queue.md", self.OLD_QUEUE + ("| 4 | M4 billing | in progress (feat/m4-billing) |\n" if in_flight else ""))
        write(d, "HANDOFF-FRESH.md", "# Handoff (fresh)\n\n## Where things stand\nnothing merges into develop until promotion 11\n\n## Next\nM2 api\n")
        write(d, "package.json", json.dumps({"name": "x", "scripts": {"check:queue": "test -f docs/loop/queue.md", "loop:start": "node scripts/loop.js start"}}))
        write(d, "scripts/loop.js", "// the old loop\n")
        write(d, ".claude/commands/loop-start.md", "Start the loop: read HANDOFF-FRESH.md and docs/loop/queue.md, then /loop-start.\n")
        write(d, "AGENTS.md", "# proj\n\n## Process\nRead HANDOFF-FRESH.md first. Start with /loop-start.\n")
        git(d, "add", "-A"); git(d, "commit", "-qm", "an old loop")
        if in_flight:
            git(d, "checkout", "-qb", "feat/m4-billing"); write(d, "src/billing.py", "x = 1\n"); git(d, "add", "-A"); git(d, "commit", "-qm", "wip"); git(d, "checkout", "-q", "main")
        return d

    def recal(self, d, *a):
        return subprocess.run([sys.executable, RECAL, *a, "--repo", d], capture_output=True, text=True)

    def test_the_measured_plan_migrates_everything_and_the_hand_off_says_complete(self):
        d = self.fixture()
        r = self.recal(d, "plan", "--measure")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("ADOPTION REFUSED", r.stdout)
        plan = json.loads(open(os.path.join(d, ".reef", "recalibration.json")).read())
        by = {e["path"]: e for e in plan["entries"]}
        self.assertEqual(by["docs/loop/queue.md"]["action"], "convert-queue")
        self.assertEqual(by["HANDOFF-FRESH.md"]["action"], "merge-handoff")
        self.assertEqual(by[".claude/commands/loop-start.md"]["action"], "archive")
        a = plan["adoption"]
        self.assertEqual(a["old_queues"], {"docs/loop/queue.md": {"rows": 3, "open": 2}})
        self.assertEqual([h["file"] + ":" + str(h["line"]) for h in a["holds"]], ["HANDOFF-FRESH.md:4"])
        self.assertEqual(a["old_scripts"], {"loop:start": "node scripts/loop.js start"})
        self.assertIn({"reader": "package.json", "target": "docs/loop/queue.md", "action": "repoint", "new": "reef/queue.md"}, a["readers"])
        self.assertIn("| check:queue | 0 |", r.stdout, "the scratch apply repointed the reader: the gate is green after the move")
        git(d, "add", "-A"); git(d, "commit", "-qm", "plan")
        r = self.recal(d, "--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("hand-off: Reef's tree is complete", r.stdout)
        self.assertIn("hold: HANDOFF-FRESH.md:4 — nothing merges into develop until promotion 11", r.stdout)
        queue = open(os.path.join(d, "reef", "queue.md")).read()
        self.assertIn("M2 api (from docs/loop/queue.md row 2)", queue)
        self.assertIn("M3 ui (from docs/loop/queue.md row 3)", queue)
        self.assertNotIn("M1 schema", queue, "a closed row stays in the archived file")
        self.assertFalse(os.path.isfile(os.path.join(d, "docs", "loop", "queue.md")))
        self.assertIn("## Carried over from HANDOFF-FRESH.md", open(os.path.join(d, "HANDOFF.md")).read())
        self.assertFalse(os.path.isfile(os.path.join(d, "HANDOFF-FRESH.md")))
        self.assertIn('"check:queue": "test -f reef/queue.md"', open(os.path.join(d, "package.json")).read(), "the reader was repointed")
        self.assertFalse(os.path.isfile(os.path.join(d, ".claude", "commands", "loop-start.md")))
        self.assertNotIn("/loop-start", open(os.path.join(d, "AGENTS.md")).read())
        self.assertEqual(git(d, "status", "--porcelain").strip(), "", "one commit")

    def test_the_release_branch_an_archive_and_a_done_row_never_count_as_in_flight(self):
        # ai-coach, 2026-10-25: `main` was "in flight" because the word sat in docs/loop/queue-archive.md; a done row naming a branch too
        d = self.fixture()
        write(d, "docs/loop/queue-archive.md", "# Archive\n\n| id | item | status |\n|---|---|---|\n| 0 | released to main | done |\n")
        write(d, "docs/loop/queue.md", self.OLD_QUEUE + "| 4 | M4 old (feat/old-done) | done |\n")
        git(d, "add", "-A"); git(d, "commit", "-qm", "archive + a done row")
        git(d, "checkout", "-qb", "feat/old-done"); write(d, "src/old.py", "x\n"); git(d, "add", "-A"); git(d, "commit", "-qm", "old"); git(d, "checkout", "-q", "main")
        git(d, "checkout", "-qb", "release-only"); write(d, "src/rel.py", "x\n"); git(d, "add", "-A"); git(d, "commit", "-qm", "rel"); git(d, "checkout", "-q", "main")
        cfg = json.loads(open(os.path.join(d, ".reef", "config.json")).read()); cfg["branches"] = {"base": "main", "release": "release-only"}
        write(d, ".reef/config.json", json.dumps(cfg)); git(d, "add", "-A"); git(d, "commit", "-qm", "release branch named")
        r = self.recal(d, "plan")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("ADOPTION REFUSED", r.stdout, "the release branch, an archive mention and a done row claim nothing")

    def test_work_in_flight_under_the_old_loop_refuses_and_names_the_branch_until_parked(self):
        d = self.fixture(in_flight=True)
        r = self.recal(d, "plan")
        self.assertIn("ADOPTION REFUSED: branch feat/m4-billing is in flight under the old loop (claimed by docs/loop/queue.md)", r.stdout)
        git(d, "add", "-A"); git(d, "commit", "-qm", "plan")
        r = self.recal(d, "--apply")
        self.assertEqual(r.returncode, 1)
        self.assertIn("feat/m4-billing (claimed by docs/loop/queue.md)", r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(d, "docs", "loop", "queue.md")), "nothing moved")
        r = self.recal(d, "--apply", "--park-in-flight")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("parked: finish branch feat/m4-billing under Reef", open(os.path.join(d, "reef", "queue.md")).read())


class ExistingAdrNumbersAreKept(unittest.TestCase):
    """0.7.2 (ai-coach, 2026-10-24, item 21): 193 numbered ADRs cited 456 times would have been renumbered by the apply. A
    filename that carries a 4-digit number keeps it; only unnumbered decisions get the next number; a numbered record that
    would land on a number already in the ADR home refuses the apply and names both files.
    0.7.3 (ai-coach, 2026-10-25): the ADR home is `paths.adr`. The apply wrote converted ADRs to reef/architecture/adr/ and
    moved the configured docs/adr/ there too, while reef-structure counts the configured folders as the layout; after the
    owner moved docs/adr/ back (the project's check:docs reads it), the next apply would have split the ADRs across two homes.
    A document under any configured `paths.*` home is in the layout and stays."""

    def project(self, clash=False):
        d = tempfile.mkdtemp(prefix="reef-adrnum.")
        subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
        write(d, ".reef/config.json", json.dumps({"gates": {"full": "true"}, "paths": {"adr": "docs/adr", "queue": "reef/queue.md", "glossary": "docs/glossary.md"}}))
        write(d, ".reef/version", "0.7.1\n")
        write(d, "reef/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n")
        write(d, "docs/adr/0024-x.md", self.ADR)
        write(d, "docs/glossary.md", "# Glossary\n| Term | Definition |\n|---|---|\n| Order | one sale |\n")
        write(d, "decisions/foo.md", "# Foo\n\n## Status\nAccepted\n\n## Context\nc\n\n## Decision\nd\n\n## Consequences\ne\n")
        write(d, "src/a.py", "# see ADR 0024\n")
        if clash:
            write(d, "decisions/0024-other.md", "# ADR 0024 — other\n\n## Status\nAccepted\n\n## Context\nc\n\n## Decision\nd\n\n## Consequences\ne\n")
        git(d, "add", "-A"); git(d, "commit", "-qm", "init")
        run = lambda *a: subprocess.run([sys.executable, RECAL, *a, "--repo", d], capture_output=True, text=True)
        self.assertEqual(run("plan").returncode, 0)
        git(d, "add", "-A"); git(d, "commit", "-qm", "plan")
        return d, run("--apply")

    ADR = "# ADR 0024 — x\n\n## Status\nAccepted\n\n## Context\nc\n\n## Decision\nd\n\n## Consequences\ne\n"

    def test_the_adr_home_is_paths_adr_its_records_stay_and_an_unnumbered_one_gets_the_next_number_there(self):
        d, r = self.project()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(open(os.path.join(d, "docs", "adr", "0024-x.md")).read(), self.ADR, "in the ADR home: stays, byte for byte")
        self.assertFalse(os.path.exists(os.path.join(d, "reef", "architecture", "adr")), "no second ADR home")
        nxt = [f for f in os.listdir(os.path.join(d, "docs", "adr")) if f.startswith("0025-")]
        self.assertEqual(len(nxt), 1, os.listdir(os.path.join(d, "docs", "adr")))
        self.assertIn("Supersedes: reef/archive/", open(os.path.join(d, "docs", "adr", nxt[0])).read())
        self.assertIn("| Order | one sale |", open(os.path.join(d, "docs", "glossary.md")).read(), "the configured glossary stays where it is")
        self.assertFalse(os.path.exists(os.path.join(d, "reef", "glossary.md")))
        plan = {e["path"]: e for e in json.loads(open(os.path.join(d, ".reef", "recalibration.json")).read())["entries"]}
        self.assertEqual(plan["docs/adr/0024-x.md"]["action"], "keep")
        self.assertIn(f"docs/adr/0025-", open(os.path.join(d, "reef", "recalibration.md")).read().replace("NNNN", "0025"))
        r = subprocess.run([sys.executable, STRUCT, "--check", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_clash_with_the_adr_home_refuses_and_names_both(self):
        d, r = self.project(clash=True)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("ADR number 0024 clashes: decisions/0024-other.md and docs/adr/0024-x.md", r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(d, "decisions", "0024-other.md")), "nothing moved")
        self.assertEqual(git(d, "status", "--porcelain").strip(), "")
