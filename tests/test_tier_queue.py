"""Sabotage suite for scripts/reef-tier.py (a tier can only get heavier) and
scripts/reef-queue.py (the outer graph: status derived from task files, ready rows, consistency,
ADR numbering at merge)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIER = os.path.join(ROOT, "scripts", "reef-tier.py")
QUEUE = os.path.join(ROOT, "scripts", "reef-queue.py")


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def git(root, *a):
    return subprocess.run(["git", "-C", root, *a], capture_output=True, text=True)


def repo(cfg=None):
    d = tempfile.mkdtemp(prefix="reef-tq.")
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    write(d, ".reef/config.json", json.dumps(cfg or {}))
    write(d, "src/app.py", "print(1)\n")
    write(d, "docs/notes.md", "n\n")
    git(d, "add", "-A")
    git(d, "commit", "-qm", "base")
    git(d, "checkout", "-qb", "feat")
    return d


def task(d, tier):
    return write(d, "tasks/001-t.md", f"---\nid: 1\nfeature: 1\nstatus: pending\ntier: {tier}\n---\n# 1\n")


def commit(d):
    git(d, "add", "-A")
    git(d, "commit", "-qm", "work")


def tier(task_path, *args):
    return subprocess.run([sys.executable, TIER, task_path, "--repo", os.path.dirname(os.path.dirname(task_path)), *args],
                          capture_output=True, text=True)


CFG = {"tiers": {"light": {"allow": ["docs/**", "src/safe/**"], "max_lines": 5, "migrations": ["migrations/**"]}}}


class Tier(unittest.TestCase):
    def test_light_diff_passes_light_declaration(self):
        d = repo(CFG)
        t = task(d, "light")
        write(d, "docs/notes.md", "n\nmore\n")
        write(d, "src/safe/x.py", "a = 1\n")
        commit(d)
        r = tier(t)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_declared_light_computed_full_refused_and_write_raises(self):
        d = repo(CFG)
        t = task(d, "light")
        write(d, "src/app.py", "print(2)\n")        # not allowlisted
        commit(d)
        r = tier(t)
        self.assertEqual(r.returncode, 1, "a diff outside the allowlist cannot be light")
        self.assertIn("not in tiers.light.allow", r.stdout)
        r = tier(t, "--write")
        self.assertEqual(r.returncode, 1)
        with open(t) as f:
            self.assertIn("tier: full", f.read())

    def test_migration_and_line_ceiling_make_it_full(self):
        d = repo(CFG)
        t = task(d, "light")
        write(d, "migrations/001.sql", "x\n")
        commit(d)
        self.assertIn("a migration", tier(t).stdout)
        d = repo(CFG)
        t = task(d, "light")
        write(d, "src/safe/big.py", "\n".join(f"l{i} = {i}" for i in range(10)) + "\n")
        commit(d)
        r = tier(t)
        self.assertEqual(r.returncode, 1)
        self.assertIn("product lines added", r.stdout)

    def test_tests_do_not_count_as_product_lines(self):
        d = repo(CFG)
        t = task(d, "light")
        write(d, "tests/test_big.py", "\n".join(f"def test_{i}(): pass" for i in range(40)) + "\n")
        write(d, "src/safe/x.py", "a = 1\n")
        commit(d)
        self.assertEqual(tier(t).returncode, 1, "tests/ is not in the allowlist — still full")
        cfg = {"tiers": {"light": {"allow": ["src/safe/**", "tests/**"], "max_lines": 5}}}
        d = repo(cfg)
        t = task(d, "light")
        write(d, "tests/test_big.py", "\n".join(f"def test_{i}(): pass" for i in range(40)) + "\n")
        write(d, "src/safe/x.py", "a = 1\n")
        commit(d)
        self.assertEqual(tier(t).returncode, 0, "test lines must not count toward the product-line ceiling")

    def test_heavier_declaration_always_ok_and_empty_diff_refused(self):
        d = repo(CFG)
        t = task(d, "design")
        write(d, "docs/notes.md", "n\nx\n")
        commit(d)
        self.assertEqual(tier(t).returncode, 0)
        d = repo(CFG)
        t = task(d, "light")
        commit(d)
        r = tier(t)
        self.assertEqual(r.returncode, 1)
        self.assertIn("empty diff", r.stderr)


QUEUE_MD = """# Queue
Current batch: 1

| Id | Item | Depends | Source | Batch | Admitted |
|---|---|---|---|---|---|
| 1 | first | | planned | 1 | |
| 2 | second | 1 | planned | 1 | |
| 3 | found thing | | found | 1 | |
| 4 | later | | planned | 2 | |
"""


def queue(root, *args):
    return subprocess.run([sys.executable, QUEUE, *args, "--repo", root], capture_output=True, text=True)


def qrepo():
    d = tempfile.mkdtemp(prefix="reef-q.")
    git(d, "init", "-q", "-b", "main")
    write(d, ".reef/config.json", json.dumps({"writing": {"queue_words": 200}}))
    write(d, "docs/queue.md", QUEUE_MD)
    return d


class Queue(unittest.TestCase):
    def test_status_derived_from_task_files(self):
        d = qrepo()
        write(d, "tasks/101-a.md", "---\nid: 101\nfeature: 1\nstatus: done\n---\n")
        write(d, "tasks/201-b.md", "---\nid: 201\nfeature: 2\nstatus: in-progress\n---\n")
        out = queue(d, "status").stdout
        self.assertIn("1\tdone", out)
        self.assertIn("2\tbuilding", out)
        self.assertIn("3\tqueued", out)

    def test_ready_respects_depends_batch_and_planned_first(self):
        d = qrepo()
        out = queue(d, "ready").stdout
        self.assertIn("1\tqueued", out)
        self.assertNotIn("2\t", out, "2 depends on 1, which is not done")
        self.assertNotIn("3\t", out, "a found row waits while a planned row is ready")
        self.assertNotIn("4\t", out, "batch 2 is not the current batch")
        write(d, "tasks/101-a.md", "---\nid: 101\nfeature: 1\nstatus: done\n---\n")
        out = queue(d, "ready").stdout
        self.assertIn("2\tqueued", out)
        self.assertNotIn("1\t", out)

    def test_archived_dependency_counts_as_done(self):
        d = qrepo()
        write(d, "docs/queue-archive.md", "| Id | Item | Depends |\n|---|---|---|\n| 0 | old | |\n")
        write(d, "docs/queue.md", QUEUE_MD.replace("| 1 | first | |", "| 1 | first | 0 |"))
        self.assertIn("1\tqueued", queue(d, "ready").stdout)

    def test_check_catches_orphans_duplicates_unknown_depends_and_word_cap(self):
        d = qrepo()
        self.assertEqual(queue(d, "check").returncode, 0)
        write(d, "tasks/901-x.md", "---\nid: 901\nfeature: 9\nstatus: pending\n---\n")
        r = queue(d, "check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("feature: 9 have no queue row", r.stdout)
        write(d, "docs/queue.md", QUEUE_MD + "| 2 | again | 7 | planned | 1 | |\n")
        r = queue(d, "check")
        self.assertIn("row id 2 repeats", r.stdout)
        self.assertIn("unknown row 7", r.stdout)
        write(d, "docs/queue.md", QUEUE_MD + " ".join(["word"] * 300))
        self.assertIn("over writing.queue_words", queue(d, "check").stdout)

    def test_adr_number_renames_and_rewrites_citations(self):
        d = qrepo()
        write(d, "docs/adr/0003-old.md", "# ADR 0003\nStatus: Accepted\n")
        write(d, "docs/adr/draft-12-cache.md", "# cache\nStatus: Accepted (number at merge)\n")
        write(d, "tasks/1201-t.md", "---\nid: 1201\nfeature: 12\nstatus: done\n---\nsee draft-12-cache\n")
        r = queue(d, "adr-number")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(d, "docs", "adr", "0004-cache.md")))
        self.assertFalse(os.path.exists(os.path.join(d, "docs", "adr", "draft-12-cache.md")))
        with open(os.path.join(d, "docs", "adr", "0004-cache.md")) as f:
            self.assertIn("Status: Accepted\n", f.read())
        with open(os.path.join(d, "tasks", "1201-t.md")) as f:
            self.assertIn("see ADR 0004", f.read())
        self.assertEqual(queue(d, "adr-number").returncode, 1, "nothing left to number")


if __name__ == "__main__":
    unittest.main()
