"""The queue on the project's GitHub issues (0.7.1, the owner's go 2026-10-24): `queue.home: issues`. A row is an
issue labelled `reef-row` whose title starts with Reef's row id (`[12] …`); a batch is a milestone `Batch N`, the
current batch the lowest open one; a closed issue is archived. Footnotes, notes and questions stay files. A fake
`gh` on PATH keeps the issues and milestones in one JSON file and logs every call."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(ROOT, "scripts", "reef-queue.py")

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
p = os.environ["GH_STATE"]
s = json.load(open(p))
a = sys.argv[1:]
s["calls"].append(a)
def save():
    json.dump(s, open(p, "w"), indent=1)
if os.environ.get("GH_MODE") == "slow":
    import time; time.sleep(6)
if os.environ.get("GH_MODE") == "fail":
    save(); print("HTTP 502", file=sys.stderr); sys.exit(1)
def opt(name, many=False):
    vals = [a[i + 1] for i, x in enumerate(a) if x == name and i + 1 < len(a)]
    return vals if many else (vals[-1] if vals else None)
def issue(n):
    return next(i for i in s["issues"] if i["number"] == int(n))
def view(i):
    ms = i.get("milestone")
    return {"number": i["number"], "title": i["title"], "body": i["body"], "state": i["state"], "stateReason": i.get("stateReason", ""),
            "labels": [{"name": l} for l in i["labels"]], "milestone": {"title": ms} if ms else None}
if a[:2] == ["issue", "list"]:
    lab = opt("--label")
    print(json.dumps([view(i) for i in s["issues"] if lab in i["labels"]]))
elif a[:2] == ["issue", "view"]:
    print(json.dumps(view(issue(a[2]))))
elif a[:2] == ["issue", "create"]:
    s["next"] += 1
    s["issues"].append({"number": s["next"], "title": opt("--title"), "body": opt("--body") or "", "state": "OPEN",
                        "labels": opt("--label", True), "milestone": opt("--milestone"), "comments": []})
    print(f"https://github.com/o/r/issues/{s['next']}")
elif a[:2] == ["issue", "edit"]:
    i = issue(a[2])
    if opt("--title") is not None: i["title"] = opt("--title")
    if opt("--body") is not None: i["body"] = opt("--body")
    if opt("--milestone") is not None: i["milestone"] = opt("--milestone")
    i["labels"] += [l for l in opt("--add-label", True) if l not in i["labels"]]
    for l in opt("--remove-label", True):
        if l not in s["labels"] and l not in i["labels"]:
            print(f"could not remove label {l}: not found", file=sys.stderr); save(); sys.exit(1)
        i["labels"] = [x for x in i["labels"] if x != l]
elif a[:2] == ["issue", "close"]:
    i = issue(a[2]); i["state"] = "CLOSED"; i["stateReason"] = "NOT_PLANNED" if opt("--reason") == "not planned" else "COMPLETED"
    if opt("--comment"): i["comments"].append(opt("--comment"))
elif a[:2] == ["issue", "comment"]:
    issue(a[2])["comments"].append(opt("--body"))
elif a[:2] == ["label", "create"]:
    if a[2] not in s["labels"]: s["labels"].append(a[2])
elif a[:1] == ["api"]:
    path = next(x for x in a[1:] if x.startswith("repos/"))
    if "-X" in a and opt("-X") == "PATCH":
        m = next(m for m in s["milestones"] if m["number"] == int(path.rsplit("/", 1)[1])); m["state"] = "closed"
        print(json.dumps(m))
    elif "-f" in a:
        t = opt("-f").split("=", 1)[1]
        m = {"number": len(s["milestones"]) + 1, "title": t, "state": "open"}; s["milestones"].append(m)
        print(json.dumps(m))
    else:
        print(json.dumps(s["milestones"]))
else:
    save(); print("fake gh: unknown " + " ".join(a), file=sys.stderr); sys.exit(1)
save()
'''

QUEUE_MD = """# Queue — demo

One row per unit of work.

Current batch: 2

## Rules of the loop
1. Take the top row of the current batch.

## Columns
`Id` · `Item` · `Depends` · `Source` · `Batch` · `Admitted`

## Batch 1

| Id | Item | Depends | Source | Batch | Admitted |
|---|---|---|---|---|---|
| 2 | first slice still open | | planned | 1 | |

## Batch 2

| Id | Item | Depends | Source | Batch | Admitted |
|---|---|---|---|---|---|
| 3 | exact totals¹ | 1 | planned | 2 | |
| 4 | photo resize | 3 | found | 2 | |

## Footnotes
¹ owner: "two decimals" (2026-10-20)
"""

ARCHIVE_MD = "# Queue archive\n\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n| 1 | skeleton | | planned | 1 | |\n"


def body(depends="", admitted=""):
    return f"Depends: {depends}\nAdmitted: {admitted}\n"


class Base(unittest.TestCase):
    home = "issues"

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reef-qi.")
        self.d = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.d, ".reef"))
        os.makedirs(os.path.join(self.d, "reef"))
        subprocess.run(["git", "init", "-q", "-b", "main", self.d], check=True)
        self.cfg = {"paths": {"queue": "reef/queue.md"}, "queue": {"home": self.home}}
        with open(os.path.join(self.d, ".reef", "config.json"), "w") as f:
            f.write(json.dumps(self.cfg, indent=2) + "\n")
        q = QUEUE_MD if self.home == "file" else "# Queue — demo\n\n## Footnotes\n¹ owner: \"two decimals\" (2026-10-20)\n"
        with open(os.path.join(self.d, "reef", "queue.md"), "w") as f:
            f.write(q)
        with open(os.path.join(self.d, "reef", "queue-archive.md"), "w") as f:
            f.write(ARCHIVE_MD)
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        with open(os.path.join(self.bin, "gh"), "w") as f:
            f.write(FAKE_GH)
        os.chmod(os.path.join(self.bin, "gh"), 0o755)
        self.state = os.path.join(self.tmp, "gh.json")
        self.put(self.forge())

    def forge(self):
        return {"next": 20, "labels": [], "calls": [], "milestones": [
            {"number": 1, "title": "Batch 1", "state": "closed"}, {"number": 2, "title": "Batch 2", "state": "open"},
            {"number": 3, "title": "Batch 3", "state": "open"}], "issues": [
            {"number": 11, "title": "[2] first slice", "body": body(), "state": "CLOSED", "stateReason": "COMPLETED",
             "labels": ["reef-row", "planned"], "milestone": "Batch 1", "comments": []},
            {"number": 12, "title": "[3] exact totals", "body": body("2"), "state": "OPEN", "labels": ["reef-row", "planned"],
             "milestone": "Batch 2", "comments": []},
            {"number": 13, "title": "[4] photo resize", "body": body("3"), "state": "OPEN", "labels": ["reef-row", "found"],
             "milestone": "Batch 2", "comments": []},
            {"number": 14, "title": "[5] cache lifetime", "body": body(), "state": "OPEN", "labels": ["reef-row", "found"],
             "milestone": "Batch 3", "comments": []},
            {"number": 15, "title": "an idea, not admitted", "body": "", "state": "OPEN", "labels": [], "milestone": None, "comments": []}]}

    def put(self, s):
        with open(self.state, "w") as f:
            json.dump(s, f)

    def gh(self):
        with open(self.state) as f:
            return json.load(f)

    def q(self, *args, mode="ok"):
        env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""), GH_STATE=self.state, GH_MODE=mode,
                   REEF_GH_READ_TIMEOUT="3")
        return subprocess.run([sys.executable, QUEUE, *args, "--repo", self.d], capture_output=True, text=True, env=env)

    def issue(self, rid):
        return next(i for i in self.gh()["issues"] if i["title"].startswith(f"[{rid}]"))


class ReadsFromIssues(Base):
    def test_status_and_ready_read_the_labelled_issues(self):
        r = self.q("status")
        self.assertEqual(r.returncode, 0, r.stderr)
        ids = [l.split("\t")[0] for l in r.stdout.splitlines()]
        self.assertEqual(ids, ["3", "4", "5"], "open labelled issues only; a closed one is archived, an unlabelled one is no row")
        self.assertIn("batch=2", r.stdout)
        r = self.q("ready", "--with-found")
        self.assertEqual([l.split("\t")[0] for l in r.stdout.splitlines()], ["3"], "row 4 waits on 3; row 5 is batch 3")
        self.assertTrue(os.path.isfile(os.path.join(self.d, ".reef", "queue.json")), "the snapshot is written")

    def test_a_failing_gh_reads_the_last_snapshot_and_writes_refuse(self):
        self.q("status")
        r = self.q("status", mode="fail")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("last snapshot", r.stderr)
        self.assertIn("exact totals", r.stdout)
        r = self.q("add-row", "--item", "x", mode="fail")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(self.gh()["issues"]), 5, "nothing written")
        r = self.q("status", mode="slow")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("last snapshot", r.stderr, "a slow gh read gives up after REEF_GH_READ_TIMEOUT")
        os.unlink(os.path.join(self.d, ".reef", "queue.json"))
        self.assertEqual(self.q("status", mode="fail").returncode, 1, "no snapshot, no gh: no queue")

    def test_check_warns_of_a_labelled_issue_without_an_id(self):
        s = self.gh()
        s["issues"][4]["labels"] = ["reef-row"]
        self.put(s)
        r = self.q("check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("warning: #15 is labelled reef-row but its title has no [id] — the owner admits it: reef-queue.py admit 15", r.stdout)


class WritesToIssues(Base):
    def test_add_row_takes_the_next_id_across_issues_and_the_archive_file(self):
        r = self.q("add-row", "--item", "receipt orientation", "--depends", "3", "--source", "found")
        self.assertEqual(r.stdout.strip(), "6")
        i = self.issue(6)
        self.assertEqual(i["title"], "[6] receipt orientation")
        self.assertEqual(i["milestone"], "Batch 3", "found work enters the next batch")
        self.assertEqual(sorted(i["labels"]), ["found", "reef-row"])
        self.assertIn("Depends: 3", i["body"])
        self.assertEqual(sorted(self.gh()["labels"]), ["found", "reef-row"], "missing labels are created")

    def test_set_depends_set_batch_footnote_drop_and_close(self):
        self.q("set-depends", "5", "3, 4")
        self.assertIn("Depends: 3, 4", self.issue(5)["body"])
        self.q("set-batch", "5", "4")
        self.assertEqual(self.issue(5)["milestone"], "Batch 4")
        self.assertIn("Batch 4", [m["title"] for m in self.gh()["milestones"]], "a missing milestone is created")
        r = self.q("footnote", "owner: keep it small", "--row", "4")
        self.assertEqual(r.stdout.strip(), "²")
        self.assertIn("² owner: keep it small", self.issue(4)["comments"][0])
        self.assertIn("² owner: keep it small", open(os.path.join(self.d, "reef", "queue.md")).read(), "footnotes stay a file")
        self.q("set-depends", "4", "3, 5")
        r = self.q("drop-row", "5", "--reason", "no longer matters")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.issue(5)["state"], self.issue(5)["stateReason"]), ("CLOSED", "NOT_PLANNED"))
        r = self.q("check")
        self.assertEqual(r.returncode, 1, "a dropped row is not done: its dependent dangles, as in the file queue")
        self.assertIn("row 4 depends on unknown row 5", r.stdout)
        self.q("set-depends", "4", "3")
        self.assertEqual(self.q("add-row", "--item", "next").stdout.strip(), "6", "a dropped id is never reused")
        r = self.q("close", "3", "--pr", "40")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.issue(3)["state"], self.issue(3)["stateReason"]), ("CLOSED", "COMPLETED"))
        self.assertIn("merged in #40", self.issue(3)["comments"][-1])
        self.assertEqual([l.split("\t")[0] for l in self.q("ready", "--with-found").stdout.splitlines()], ["6", "4"], "planned first")

    def test_admit_makes_a_plain_issue_a_row(self):
        r = self.q("admit", "15", "--source", "found")
        self.assertEqual(r.stdout.strip(), "6")
        i = next(x for x in self.gh()["issues"] if x["number"] == 15)
        self.assertEqual(i["title"], "[6] an idea, not admitted")
        self.assertEqual(sorted(i["labels"]), ["found", "reef-row"])
        self.assertEqual(i["milestone"], "Batch 3")


class Priority(Base):
    """`p1`/`p2`/`p3` labels order the ready rows (the owner's go, 2026-10-24): priority first (none counts as p2), then
    planned before found, then id; a found row labelled p1 counts as planned — the owner promoted it."""

    def forge(self):
        s = super().forge()
        s["issues"] += [
            {"number": 16, "title": "[6] polish copy", "body": body(), "state": "OPEN", "labels": ["reef-row", "planned", "p3"],
             "milestone": "Batch 2", "comments": []},
            {"number": 17, "title": "[7] session fixation", "body": body(), "state": "OPEN", "labels": ["reef-row", "found", "p1"],
             "milestone": "Batch 2", "comments": []},
            {"number": 18, "title": "[8] slow query", "body": body(), "state": "OPEN", "labels": ["reef-row", "found"],
             "milestone": "Batch 2", "comments": []}]
        return s

    def ids(self, *args):
        return [l.split("\t")[0] for l in self.q("ready", *args).stdout.splitlines()]

    def test_priority_orders_the_ready_rows_and_p1_promotes_a_found_row(self):
        self.assertEqual(self.ids(), ["7", "3", "6"], "p1 found (promoted), then p2 planned, then p3 planned; row 8 waits")
        self.assertEqual(self.ids("--with-found"), ["7", "3", "8", "6"], "priority before planned-before-found")

    def test_set_priority_and_admit_with_one(self):
        r = self.q("set-priority", "8", "p1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("p1", self.issue(8)["labels"])
        self.assertEqual(self.ids()[:2], ["7", "8"])
        self.q("set-priority", "8", "p3")
        self.assertEqual(sorted(l for l in self.issue(8)["labels"] if l.startswith("p")), ["p3"], "one priority at a time")
        self.q("set-priority", "8", "none")
        self.assertFalse([l for l in self.issue(8)["labels"] if l in ("p1", "p2", "p3")])
        self.assertEqual(self.q("set-priority", "8", "urgent").returncode, 2)
        r = self.q("admit", "15", "--source", "found", "--priority", "p1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("p1", next(i for i in self.gh()["issues"] if i["number"] == 15)["labels"])


class ReadersUseTheSnapshot(Base):
    """The night runner's open-rows check and the watch view read `.reef/queue.json`, never the network: after a
    migration the queue file has no table, and an empty set would refuse every night contract."""

    def load(self, name):
        import importlib.machinery, importlib.util
        loader = importlib.machinery.SourceFileLoader(name.replace("-", "_").replace(".py", ""), os.path.join(ROOT, "scripts", name))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        return mod

    def test_the_runner_and_the_watch_read_the_snapshot(self):
        run, watch = self.load("reef-run.py"), self.load("reef-watch")
        self.assertIsNone(run.queue_open_rows(self.d), "no snapshot yet: unreadable, never an empty queue")
        self.q("status")
        self.assertEqual(run.queue_open_rows(self.d), {"3", "4", "5"})
        self.assertEqual(watch.section_queue(self.d, self.cfg), ["queue: 3 open row(s) on issues, 2 found: photo resize; cache lifetime"])


class Migrate(Base):
    home = "file"

    def test_dry_run_writes_nothing_and_apply_moves_the_open_rows(self):
        s = self.forge()
        s.update(issues=[], milestones=[], next=0)
        self.put(s)
        r = self.q("migrate-to-issues")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("would create 3 issue(s)", r.stdout)
        self.assertEqual(self.gh()["issues"], [])
        r = self.q("migrate-to-issues", "--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        g = self.gh()
        self.assertEqual([i["title"] for i in g["issues"]], ["[2] first slice still open", "[3] exact totals", "[4] photo resize"])
        self.assertIn("Item: exact totals¹", g["issues"][1]["body"], "the footnote mark stays, in the body")
        self.assertEqual([(m["title"], m["state"]) for m in g["milestones"]], [("Batch 1", "closed"), ("Batch 2", "open")])
        self.assertEqual(g["issues"][2]["milestone"], "Batch 2")
        self.assertIn("Depends: 3", g["issues"][2]["body"])
        self.assertEqual(sorted(g["labels"]), ["found", "p1", "p2", "p3", "planned", "reef-row"])
        cfg = json.load(open(os.path.join(self.d, ".reef", "config.json")))
        self.assertEqual(cfg["queue"]["home"], "issues")
        q = open(os.path.join(self.d, "reef", "queue.md")).read()
        self.assertNotIn("| 3 | exact totals", q)
        self.assertIn("¹ owner: \"two decimals\"", q, "the footnotes stay")
        self.assertIn("## Rules of the loop", q, "the rules stay")
        r = self.q("ready")
        self.assertEqual([l.split("\t")[0] for l in r.stdout.splitlines()], ["3"], "batch 2 current: row 2 is batch 1")
        r = self.q("migrate-to-issues", "--apply")
        self.assertEqual(r.returncode, 1)
        self.assertIn("already on issues", r.stderr)


    def test_the_templates_placeholder_row_is_not_migrated(self):
        # 2026-10-24: a fresh /reef-init queue holds `<the first planned row, one line>`; the migration made it issue [1]
        p = os.path.join(self.d, "reef", "queue.md")
        q = open(p).read().replace("| 4 | photo resize | 3 | found | 2 | |\n",
                                   "| 4 | photo resize | 3 | found | 2 | |\n| 5 | <the first planned row, one line> | | planned | 2 | |\n")
        with open(p, "w") as f:
            f.write(q)
        s = self.forge()
        s.update(issues=[], milestones=[], next=0)
        self.put(s)
        r = self.q("migrate-to-issues", "--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("skipped row 5: the template's placeholder", r.stdout)
        self.assertEqual([i["title"][:3] for i in self.gh()["issues"]], ["[2]", "[3]", "[4]"])

if __name__ == "__main__":
    unittest.main()
