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
            "createdAt": i.get("createdAt", "2026-10-24T00:00:00Z"),
            "labels": [{"name": l} for l in i["labels"]], "milestone": {"title": ms} if ms else None}
if a[:2] == ["auth", "status"]:
    print("Logged in to github.com")
elif a[:2] == ["issue", "list"]:
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

    def q(self, *args, mode="ok", **extra):
        env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""), GH_STATE=self.state, GH_MODE=mode, **extra)
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
        self.assertEqual(self.q("status").returncode, 0)
        r = self.q("status", mode="fail")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("last snapshot", r.stderr)
        self.assertIn("exact totals", r.stdout)
        r = self.q("add-row", "--item", "x", mode="fail")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(self.gh()["issues"]), 5, "nothing written")
        r = self.q("status", mode="slow", REEF_GH_READ_TIMEOUT="2")
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


class Triage(Base):
    """Every found row without a priority label is untriaged (the owner's go, 2026-10-24): the tick warns once one has
    waited more than 7 days; `triage` lists them all by module with four outcomes; `demote` makes one a note."""

    def aged(self, days):
        import datetime
        s = self.gh()
        when = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for i in s["issues"]:
            i["createdAt"] = when
        self.put(s)

    def test_the_weekly_line_and_the_full_list(self):
        self.aged(2)
        r = self.q("triage", "--count")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("untriaged found: 2", r.stdout)
        self.aged(9)
        r = self.q("triage", "--count")
        self.assertEqual(r.returncode, 1, "a finding untriaged for more than 7 days is the tick's line")
        self.assertIn("untriaged found: 2 (oldest 9 day(s))", r.stdout)
        r = self.q("triage")
        self.assertEqual(r.returncode, 1)
        for line in ("set-priority 4 p1|p2|p3", "drop-row 5 --reason", "demote 5", "absorbs row 4"):
            self.assertIn(line, r.stdout)
        self.q("set-priority", "4", "p2")
        self.q("set-priority", "5", "p3")
        r = self.q("triage", "--count")
        self.assertEqual((r.returncode, "untriaged found: 0" in r.stdout), (0, True), "a priority label is the triage decision")

    def test_demote_makes_a_finding_a_note_and_a_security_one_stays(self):
        r = self.q("demote", "5")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "n1")
        self.assertEqual((self.issue(5)["state"], self.issue(5)["stateReason"]), ("CLOSED", "NOT_PLANNED"))
        self.assertIn("demoted to note n1", self.issue(5)["comments"][-1])
        notes = open(os.path.join(self.d, "reef", "noted-risks.md")).read()
        self.assertIn("n1 · row 5 · ", notes)
        self.assertIn("cache lifetime (was row 5)", notes)
        s = self.gh()
        s["issues"][2]["title"] = "[4] session cookie leaks on resize"
        self.put(s)
        r = self.q("demote", "4")
        self.assertEqual(r.returncode, 1)
        self.assertIn("always a queue row", r.stderr)
        self.assertEqual(self.issue(4)["state"], "OPEN")

    def test_check_warns_when_the_current_batch_is_over_batch_max(self):
        self.cfg["queue"]["batch_max"] = 1
        with open(os.path.join(self.d, ".reef", "config.json"), "w") as f:
            f.write(json.dumps(self.cfg, indent=2) + "\n")
        r = self.q("check")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("warning: batch 2 holds 2 open row(s), over queue.batch_max 1", r.stdout)


class InitChoosesTheQueue(Base):
    """A new project's queue is the repository's GitHub issues unless the owner chose a file (the owner's go, 2026-10-24:
    no on-device queue unless clearly told); with no GitHub remote it stays a file and says how to move; an existing
    project changes only on --queue issues."""
    home = "file"

    def init(self, d, *args):
        env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""), GH_STATE=self.state)
        return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-init.py"), "--root", d, *args],
                              capture_output=True, text=True, env=env)

    def fresh(self, remote=None):
        d = tempfile.mkdtemp(prefix="reef-qinit.", dir=self.tmp)
        subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
        if remote:
            subprocess.run(["git", "-C", d, "remote", "add", "origin", remote], check=True)
        return d

    def home_of(self, d):
        return json.load(open(os.path.join(d, ".reef", "config.json")))["queue"]["home"]

    def test_a_new_project_on_github_starts_on_issues_and_one_without_stays_a_file(self):
        s = self.forge()
        s.update(issues=[], milestones=[], next=0)
        self.put(s)
        d = self.fresh("https://github.com/o/r.git")
        r = self.init(d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.home_of(d), "issues")
        self.assertIn("queue: the repository's GitHub issues", r.stdout)
        self.assertIn("reef-row", self.gh()["labels"])
        d = self.fresh()
        r = self.init(d)
        self.assertEqual(self.home_of(d), "file")
        self.assertIn("queue: a local file (no GitHub remote)", r.stdout)
        d = self.fresh("https://github.com/o/r2.git")
        self.init(d, "--queue", "file")
        self.assertEqual(self.home_of(d), "file", "the owner chose a file")
        inner = os.path.join(self.fresh("https://github.com/o/r3.git"), "sub")
        os.makedirs(inner)
        self.init(inner)
        self.assertEqual(self.home_of(inner), "file", "a folder inside another checkout never takes its remote")

    def test_an_existing_repository_new_to_reef_keeps_a_file_queue_until_assess(self):
        # 2026-10-24 (AI coach): a repository with history, first set up by Reef, moved to issues at init; /reef-assess then
        # appended its converted specs' rows to the file, which issues mode no longer reads
        d = self.fresh("https://github.com/o/coach.git")
        with open(os.path.join(d, "app.py"), "w") as f:
            f.write("x = 1\n")
        subprocess.run(["git", "-C", d, "add", "app.py"], check=True)
        r = self.init(d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.home_of(d), "file", "an existing repository keeps a file queue at init")
        self.assertIn("run /reef-assess first, then", r.stdout)

    def test_an_existing_project_moves_only_when_asked(self):
        d = self.fresh("https://github.com/o/r.git")
        self.init(d, "--queue", "file")
        self.init(d)
        self.assertEqual(self.home_of(d), "file", "a refresh never moves an existing queue")
        r = self.init(d, "--queue", "issues")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.home_of(d), "issues")
        r = self.init(d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.home_of(d), "issues", "a refresh (reef-update) keeps a project on issues")
        self.assertNotIn("PROPOSED reef/queue.md", r.stdout)
        self.assertNotIn("PROPOSED .reef/config.json", r.stdout)


class RowsInTheFile(Base):
    """On issues, rows another tool wrote into the queue file (reef-recalibrate converting an existing project's specs)
    are named by `check` and moved by `import-rows`, their ids kept; `next-id` is the next id in either mode."""

    def file_rows(self, *rows):
        with open(os.path.join(self.d, "reef", "queue.md"), "a") as f:
            f.write("\n| Id | Item | Depends | Source | Batch | Admitted |\n|---|---|---|---|---|---|\n" + "".join(rows))

    def test_next_id_check_and_import_rows(self):
        self.assertEqual(self.q("next-id").stdout.strip(), "6")
        self.file_rows("| 6 | export (recalibrated from specs/export/spec.md) | | planned | 1 | |\n",
                       "| 7 | importer (recalibrated from specs/import/spec.md) | 6 | planned | 1 | |\n")
        r = self.q("check")
        self.assertIn("2 row(s) in reef/queue.md while the queue is on issues", r.stdout)
        r = self.q("import-rows")
        self.assertIn("would create 2 issue(s)", r.stdout)
        self.assertEqual(len(self.gh()["issues"]), 5, "a dry run writes nothing")
        r = self.q("import-rows", "--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.issue(6)["title"], "[6] export (recalibrated from specs/export/spec.md)")
        self.assertIn("Depends: 6", self.issue(7)["body"])
        q = open(os.path.join(self.d, "reef", "queue.md")).read()
        self.assertNotIn("| 6 | export", q)
        self.assertIn("¹ owner", q, "the footnotes stay")
        self.assertNotIn("row(s) in reef/queue.md", self.q("check").stdout)

    def test_an_id_that_is_already_an_issue_is_refused(self):
        self.file_rows("| 3 | clash | | planned | 1 | |\n")
        r = self.q("import-rows", "--apply")
        self.assertEqual(r.returncode, 1)
        self.assertIn("row 3 is already issue #12", r.stderr)


class RecalibrateOnIssues(Base):
    """/reef-assess on a project whose queue is on issues: the converted spec's row takes the next id across the issues,
    and after the move's own commit it becomes an issue; the move stays one revertable commit."""

    def test_a_converted_spec_becomes_an_issue_with_the_next_id(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("dayzero", os.path.join(ROOT, "tests", "test_dayzero.py"))
        dz = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dz)
        d = dz.fixture_repo()
        cfg = json.load(open(os.path.join(d, ".reef", "config.json")))
        cfg["queue"] = {"home": "issues"}
        with open(os.path.join(d, ".reef", "config.json"), "w") as f:
            json.dump(cfg, f)
        with open(os.path.join(d, "reef", "queue.md"), "w") as f:
            f.write("# Queue\n\n## Footnotes\n")
        subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "queue on issues"], check=True)
        env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""), GH_STATE=self.state)
        recal = lambda *a: subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-recalibrate"), *a, "--repo", d],
                                          capture_output=True, text=True, env=env)
        self.assertEqual(recal("plan").returncode, 0)
        subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], check=True)
        subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "plan"], check=True)
        r = recal("--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        made = [i for i in self.gh()["issues"] if "recalibrated from specs/export/spec.md" in i["title"]]
        self.assertEqual([i["title"][:3] for i in made], ["[6]"], "the next id after every issue, never 1")
        feat = [f for f in os.listdir(os.path.join(d, "reef", "features")) if os.path.isdir(os.path.join(d, "reef", "features", f))][0]
        self.assertIn("Row: 6", open(os.path.join(d, "reef", "features", feat, "SPEC.md")).read())
        self.assertNotIn("| 6 |", open(os.path.join(d, "reef", "queue.md")).read(), "the row left the file")
        log = subprocess.run(["git", "-C", d, "log", "--format=%s", "-2"], capture_output=True, text=True).stdout
        self.assertIn("reef recalibration", log)
        self.assertIn("queue: recalibrated rows moved to issues", log)


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
