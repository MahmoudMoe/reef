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
        self.assertIn(f"Supersedes: reef/archive/{date}/decisions/0001-use-postgres.md", text)
        self.assertIn("In the context of", text)
        self.assertTrue(os.path.isfile(os.path.join(d, "reef", "architecture", "adr", "0002-event-bus.md")))
        self.assertTrue(os.path.isfile(os.path.join(d, "reef", "archive", date, "decisions", "0001-use-postgres.md")))
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
