"""Sabotage suite for 0.6 Phase 6: feature-aware loaders (6.1: two features' tasks form ONE ready set with shared
resources: slots; a 0.5 flat project untouched passes every check with its old paths; `reef-migrate --layout`
moves everything, rewrites links, and a second run moves nothing) and versioned migrations (6.3: a 0.5 config gains
the keys once, a second run is a no-op, gates.test is untouched; the chain refuses a gap)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRAPH = os.path.join(ROOT, "scripts", "reef-graph.py")
QUEUE = os.path.join(ROOT, "scripts", "reef-queue.py")
CHECK = os.path.join(ROOT, "scripts", "reef-plan-check.py")
MIGRATE = os.path.join(ROOT, "scripts", "reef-migrate")
STRUCT = os.path.join(ROOT, "scripts", "reef-structure")
GUARD = os.path.join(ROOT, "scripts", "reef-guard.py")


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def git(d, *a):
    return subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True, capture_output=True, text=True).stdout


def task(tid, feature, status="pending", resources="[]", blocked="[]"):
    return (f"---\nid: {tid}\nfeature: {feature}\nstatus: {status}\ncomplexity: mech\neffort: medium\nblocked-by: {blocked}\n"
            f"resources: {resources}\ntier: light\nverify: gate-only\nattempts: 0\ndispatches: 0\nlast_failure_sig: \"\"\n---\n# {tid}\n\n## Scope\nx\n\n"
            f"## Acceptance Criteria\n- AC-1 (FR-1): the thing works.\n\n## Proof\n| AC | Proof |\n|---|---|\n| AC-1 | `test_t{tid}` |\n\n## Log\n")


SPEC = "# {slug} — SPEC\n\nRow: {row}\nSlug: {slug}\n\n## Intent\nx.\n\n## Grill\n- Q: a — A: b\n\n## Scope\nx\n\n## Non-goals\nnone\n\n## Already shipped\nnone\n\n## Requirements\n- FR-1 [backend]: it works.\n\n## Success criteria\n- SC-1: visible.\n\n## Owner decisions\n- none\n\n## Architecture impact\nnone, argued: a script.\n"


class OneGraph(unittest.TestCase):
    def test_two_features_form_one_ready_set_with_shared_resource_slots(self):
        d = tempfile.mkdtemp(prefix="reef-onegraph.")
        subprocess.run(["git", "init", "-q", d], check=True)
        write(d, ".reef/config.json", json.dumps({"gates": {"full": "true"}, "paths": {"features": "reef/features", "tasks": "tasks"}, "resources": {"db": {"slots": 1}}, "graph": {"parallel": 10}}))
        write(d, ".reef/version", "0.6.0\n")
        write(d, "reef/features/csv-export/SPEC.md", SPEC.format(slug="csv-export", row=1))
        write(d, "reef/features/csv-export/tasks/101-a.md", task(101, "csv-export", status="in-progress", resources="[db]"))
        write(d, "reef/features/csv-export/tasks/102-b.md", task(102, "csv-export", blocked="[101]"))
        write(d, "reef/features/user-login/SPEC.md", SPEC.format(slug="user-login", row=2))
        write(d, "reef/features/user-login/tasks/201-c.md", task(201, "user-login", resources="[db]"))
        write(d, "reef/features/user-login/tasks/202-d.md", task(202, "user-login"))
        r = subprocess.run([sys.executable, GRAPH, "ready", "--json", "--root", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        ready = {t["id"] for t in json.loads(r.stdout)}
        self.assertEqual(ready, {"101", "202"}, "201 waits: feature csv-export's 101 holds the one db slot; 102 waits on 101")
        r = subprocess.run([sys.executable, GRAPH, "check", os.path.join(d, "reef/features/user-login/tasks/201-c.md")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("resource 'db' held by task(s) 101", r.stderr)
        # the queue derives both rows' status from their folders
        write(d, "reef/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 1 | csv export | | planned | 1 | |\n| 2 | user login | | planned | 1 | |\n")
        write(d, ".reef/config.json", json.dumps({"gates": {"full": "true"}, "paths": {"features": "reef/features", "tasks": "tasks", "queue": "reef/queue.md"}, "resources": {"db": {"slots": 1}}}))
        out = subprocess.run([sys.executable, QUEUE, "status", "--repo", d], capture_output=True, text=True).stdout
        self.assertIn("csv-export\tbuilding", out.replace("1\tbuilding", "csv-export\tbuilding")) if "csv-export" in out else self.assertIn("1\tbuilding", out)

    def test_05_flat_project_untouched_passes_every_check_with_its_old_paths(self):
        d = tempfile.mkdtemp(prefix="reef-flat05.")
        subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
        write(d, ".reef/config.json", json.dumps({"gates": {"test": "true"}, "paths": {"tasks": "tasks", "adr": "docs/adr", "queue": "docs/queue.md", "runlog": "docs/journal.md"}}))
        write(d, "CLAUDE.md", "# brief\n")
        write(d, "docs/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 1 | first | | planned | 1 | |\n")
        write(d, "docs/adr/0001-x.md", "# ADR 0001\nStatus: Accepted\n## Context\nc\n## Decision\nd\n## Consequences\n+ e\n")
        write(d, "tasks/101-a.md", task(101, "1").replace("- AC-1 (FR-1): the thing works.\n\n## Proof\n| AC | Proof |\n|---|---|\n| AC-1 | `test_t101` |\n", "- test_t101 goes red first\n"))
        os.makedirs(os.path.join(d, "tasks", "done"))
        shutil.copy(CHECK, os.path.join(d, "scripts", "reef-plan-check.py") if os.makedirs(os.path.join(d, "scripts"), exist_ok=True) is None else "")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "0.5 project")
        for cmd in ([sys.executable, CHECK, d], [sys.executable, QUEUE, "check", "--repo", d], [sys.executable, GRAPH, "ready", "--root", d], [sys.executable, STRUCT, "--check", "--repo", d]):
            r = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{cmd[1:3]}: {r.stdout} {r.stderr}")
        self.assertIn("101\tpending", subprocess.run([sys.executable, GRAPH, "ready", "--root", d], capture_output=True, text=True).stdout)


class LayoutMove(unittest.TestCase):
    def fixture(self):
        d = tempfile.mkdtemp(prefix="reef-layout.")
        subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
        write(d, ".reef/config.json", json.dumps({"gates": {"test": "true"}, "paths": {"tasks": "tasks", "adr": "docs/adr", "queue": "docs/queue.md", "runlog": "docs/journal.md", "glossary": "docs/glossary.md"}}))
        write(d, "AGENTS.md", "# AGENTS\nSee [the queue](docs/queue.md) and [ADR 1](docs/adr/0001-x.md).\n")
        write(d, "docs/queue.md", "# Queue\nCurrent batch: 1\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 12 | csv export | | planned | 1 | |\n\nSee [journal](journal.md).\n")
        write(d, "docs/journal.md", "# Journal\n")
        write(d, "docs/glossary.md", "# Glossary\n")
        write(d, "docs/day-zero.md", "# Day zero\n")
        write(d, ".specify/constitution.md", "# Constitution\n")
        write(d, "docs/adr/0001-x.md", "# ADR 0001\nStatus: Accepted\n")
        write(d, "tasks/1201-a.md", task(1201, "csv-export"))
        write(d, "tasks/done/1200-z.md", task(1200, "csv-export", status="done"))
        git(d, "add", "-A")
        git(d, "commit", "-qm", "0.5 project")
        return d

    def test_layout_moves_everything_rewrites_links_and_a_second_run_moves_nothing(self):
        d = self.fixture()
        r = subprocess.run([sys.executable, MIGRATE, "--layout", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for p in ("reef/queue.md", "reef/journal.md", "reef/glossary.md", "reef/day-zero.md", "reef/constitution.md", "reef/architecture/adr/0001-x.md",
                  "reef/features/csv-export/tasks/1201-a.md", "reef/features/csv-export/tasks/done/1200-z.md", "reef/features/csv-export/SPEC.md"):
            self.assertTrue(os.path.isfile(os.path.join(d, p)), p)
        self.assertFalse(os.path.exists(os.path.join(d, "docs", "queue.md")))
        agents = open(os.path.join(d, "AGENTS.md")).read()
        self.assertIn("(reef/queue.md)", agents)
        self.assertIn("(reef/architecture/adr/0001-x.md)", agents)
        self.assertIn("[journal](journal.md)", open(os.path.join(d, "reef", "queue.md")).read(), "a link between two moved files stays relative and valid")
        cfg = json.loads(open(os.path.join(d, ".reef", "config.json")).read())
        self.assertEqual(cfg["paths"]["queue"], "reef/queue.md")
        self.assertEqual(cfg["paths"]["features"], "reef/features")
        self.assertEqual(git(d, "status", "--porcelain").strip(), "", "one commit")
        self.assertIn("reef layout", git(d, "log", "-1", "--format=%s"))
        r = subprocess.run([sys.executable, MIGRATE, "--layout", "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("nothing to move", r.stdout)
        # the moved project is a valid 0.6 project: one graph, structure, index
        write(d, ".reef/version", "0.6.0\n")
        r = subprocess.run([sys.executable, GRAPH, "ready", "--root", d], capture_output=True, text=True)
        self.assertIn("1201", r.stdout)
        self.assertEqual(subprocess.run([sys.executable, STRUCT, "--check", "--repo", d], capture_output=True, text=True).returncode, 0)


class Migrations(unittest.TestCase):
    def test_05_config_gains_keys_once_and_gates_test_is_untouched(self):
        d = tempfile.mkdtemp(prefix="reef-mig.")
        subprocess.run(["git", "init", "-q", d], check=True)
        write(d, ".reef/config.json", json.dumps({"gates": {"test": "pytest -q"}, "caps": {"attempts": 5}, "roles": {"author": "opus"}, "paths": {"tasks": "tasks"}}))
        r = subprocess.run([sys.executable, MIGRATE, "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        cfg = json.loads(open(os.path.join(d, ".reef", "config.json")).read())
        self.assertEqual(cfg["gates"], {"test": "pytest -q"}, "the alias stays exactly as it was")
        self.assertEqual(cfg["caps"]["attempts"], 5)
        self.assertEqual(cfg["caps"]["context_tokens"], 0)
        self.assertIn("critical", cfg["tiers"])
        self.assertEqual(cfg["tiers"]["light"]["roles"], {"plan_reviewer": "none"}, "no sonnet author shipped by default")
        self.assertEqual(cfg["writing"]["sentence_words"], 0, "0.7: budgets ship off; the key still arrives")
        self.assertEqual(cfg["loop"]["no_progress_ticks"], 3)
        self.assertEqual(cfg["paths"]["queue"], "docs/queue.md", "a 0.5 project keeps the 0.5 locations")
        self.assertNotIn("features", cfg["paths"], "the one tree is offered, not imposed")
        self.assertEqual(open(os.path.join(d, ".reef", "version")).read().strip(), "0.7.1", "the chain walks 0.5 -> 0.6 -> 0.7 -> 0.7.1")
        self.assertIn("--layout", r.stdout)
        snapshot = open(os.path.join(d, ".reef", "config.json")).read()
        r = subprocess.run([sys.executable, MIGRATE, "--repo", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("nothing to run", r.stdout)
        self.assertEqual(open(os.path.join(d, ".reef", "config.json")).read(), snapshot, "a second run is a no-op")

    def test_chain_refuses_a_gap(self):
        d = tempfile.mkdtemp(prefix="reef-mig-gap.")
        subprocess.run(["git", "init", "-q", d], check=True)
        write(d, ".reef/config.json", "{}")
        write(d, ".reef/version", "0.4.0\n")
        plugin = tempfile.mkdtemp(prefix="reef-plugin.")
        write(plugin, ".claude-plugin/plugin.json", json.dumps({"version": "0.6.0"}))
        shutil.copytree(os.path.join(ROOT, "migrations"), os.path.join(plugin, "migrations"))
        shutil.copytree(os.path.join(ROOT, "templates"), os.path.join(plugin, "templates"))
        r = subprocess.run([sys.executable, MIGRATE, "--repo", d, "--plugin", plugin], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("gaps between 0.4.0 and 0.5.0", r.stderr)


if __name__ == "__main__":
    unittest.main()
