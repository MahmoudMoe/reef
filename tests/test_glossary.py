"""Hardening PR-9 (docs/design/hardening-pr9-plan.md): the glossary's Avoid words are checked by code, and a term nothing uses is
proposed for retirement, retired only on the owner's approval. The glossary keeps its two-column form; a third column, Avoid,
lists the synonyms the project stopped using. `reef-glossary.py check` (and `reef-claims.py round`, part (d)) finds an Avoid word
the round ADDED: a FAIL in a code or schema line, a NIT in docs and comments. `reef doctor` names each unused term with the
owner's question; on `Approve retiring glossary term <T> at <d16>?` the row moves to glossary-history.md, the next tick commits."""
import json
import os
import re
import subprocess
import sys
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import write, git, git_repo, load_script  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GLOSSARY = os.path.join(ROOT, "scripts", "reef-glossary.py")
CLAIMS = os.path.join(ROOT, "scripts", "reef-claims.py")
APPROVAL = os.path.join(ROOT, "scripts", "reef-approval.py")
DOCTOR = os.path.join(ROOT, "scripts", "reef-doctor.py")
LOOP = os.path.join(ROOT, "scripts", "reef-loop.py")
GLOSS = """# Glossary
One canonical name per concept.

| Term | Definition | Avoid |
|---|---|---|
| Account | A paying organisation. | customer, client |
| Work item | One unit of the queue. | ticket |
| Ledger | The books. | |
"""
TWO_COL = "# Glossary\n\n| Term | Definition |\n|---|---|\n| Account | A paying organisation. |\n"


def project(glossary=GLOSS):
    d = os.path.realpath(git_repo(prefix="reef-glossary.", identity=True))
    write(d, ".reef/config.json", json.dumps({"paths": {"glossary": "docs/glossary.md"}}))
    write(d, ".gitignore", ".reef/\n")
    write(d, "docs/glossary.md", glossary)
    write(d, "src/app.py", "def open_account(account):\n    return account  # the ledger and the work item\n")
    git(d, "add", "-A"); git(d, "commit", "-qm", "base")
    return d


def check(d, *args):
    return subprocess.run([sys.executable, GLOSSARY, "check", *args, "--repo", d], capture_output=True, text=True, cwd=d)


class Format(unittest.TestCase):
    def setUp(self):
        self.m = load_script("reef-glossary.py")

    def test_the_avoid_column_is_read_and_a_two_column_glossary_bans_nothing(self):
        terms = self.m.parse(GLOSS)
        self.assertEqual([t["term"] for t in terms], ["Account", "Work item", "Ledger"])
        self.assertEqual(terms[0]["avoid"], ["customer", "client"])
        self.assertEqual(terms[2]["avoid"], [], "an empty cell bans nothing")
        self.assertEqual(self.m.parse(TWO_COL), [{"term": "Account", "avoid": [], "row": "| Account | A paying organisation. |"}])

    def test_the_template_has_the_avoid_column(self):
        with open(os.path.join(ROOT, "templates", "glossary.md"), encoding="utf-8") as f:
            self.assertRegex(f.read(), r"(?m)^\| Term \| Definition \| Avoid \|$")


class Check(unittest.TestCase):
    def setUp(self):
        self.d = project()

    def test_an_avoid_word_in_a_code_line_fails(self):
        write(self.d, "src/app.py", "def open_account(account):\n    customer = account\n    return customer  # the ledger and the work item\n")
        r = check(self.d)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('glossary: FAIL — src/app.py:2 uses "customer" — the glossary says Account (Avoid: customer, client)', r.stdout)

    def test_inside_an_identifier_and_a_schema_key_it_fails(self):
        write(self.d, "src/b.py", "def load(clientId):\n    return clientId\n")
        write(self.d, "schemas/order.json", '{"properties": {"ticket_ref": {"type": "string"}}}\n')
        write(self.d, "src/c.ts", "export const workTicketCount = 1;\n")
        out = check(self.d).stdout
        self.assertIn('src/b.py:1 uses "client"', out)
        self.assertIn('schemas/order.json:1 uses "ticket"', out)
        self.assertIn('src/c.ts:1 uses "ticket"', out, "camelCase is split into words")

    def test_docs_and_comments_are_a_nit_not_a_fail(self):
        write(self.d, "README.md", "Each customer gets an invoice.\n")
        write(self.d, "src/app.py", "def open_account(account):\n    # a client calls this\n    return account  # the ledger and the work item\n")
        r = check(self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('glossary: NIT — README.md:1 uses "customer" — the glossary says Account', r.stdout)
        self.assertIn('glossary: NIT — src/app.py:2 uses "client"', r.stdout)

    def test_whole_words_and_a_plural(self):
        write(self.d, "src/b.py", "customers = []\nclientele = 1\ncustomerservice = 2\n")
        out = check(self.d).stdout
        self.assertIn('src/b.py:1 uses "customer"', out, "a plural is the word")
        self.assertNotIn("src/b.py:2", out)
        self.assertNotIn("src/b.py:3", out, "a longer word is another word")

    def test_a_multi_word_avoid_and_a_multi_word_line(self):
        g = GLOSS.replace("| ticket |", "| ticket, task card |")
        write(self.d, "docs/glossary.md", g); git(self.d, "commit", "-qam", "g")
        write(self.d, "src/b.py", "task_card = 1\ntaskCard = 2\ntask = 3\n")
        out = check(self.d).stdout
        self.assertIn('src/b.py:1 uses "task card"', out)
        self.assertIn('src/b.py:2 uses "task card"', out)
        self.assertNotIn("src/b.py:3", out)

    def test_an_edited_legacy_line_that_keeps_the_word_is_not_flagged(self):
        write(self.d, "src/legacy.py", "customer = 1\n")
        git(self.d, "add", "-A"); git(self.d, "commit", "-qm", "legacy")
        write(self.d, "src/legacy.py", "customer = 2\n")
        r = check(self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("legacy.py", r.stdout)
        write(self.d, "src/legacy.py", "customer = 2\ncustomer_name = 'x'\n")
        self.assertIn("src/legacy.py:2", check(self.d).stdout, "one more than the removed lines held is net new")

    def test_the_glossary_file_itself_is_not_scanned(self):
        write(self.d, "docs/glossary.md", GLOSS + "| Invoice | What a customer pays. | bill |\n")
        r = check(self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("docs/glossary.md", r.stdout)

    def test_dropping_an_avoid_word_from_the_glossary_does_not_get_past_it(self):
        write(self.d, "docs/glossary.md", GLOSS.replace("| customer, client |", "| |"))
        write(self.d, "src/b.py", "customer = 1\n")
        self.assertEqual(check(self.d).returncode, 1, "the base's Avoid words still count")

    def test_an_untracked_file_is_scanned(self):
        write(self.d, "src/new.py", "ticket = 1\n")
        self.assertIn('src/new.py:1 uses "ticket"', check(self.d).stdout)

    def test_a_two_column_glossary_checks_nothing(self):
        d = project(TWO_COL)
        write(d, "src/b.py", "customer = 1\n")
        r = check(d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("glossary: no Avoid words — not checked", r.stdout)

    def test_against_a_base_branch_the_committed_work_is_checked(self):
        git(self.d, "checkout", "-qb", "feat")
        write(self.d, "src/b.py", "client = 1\n")
        git(self.d, "add", "-A"); git(self.d, "commit", "-qm", "work")
        r = check(self.d, "main")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('src/b.py:1 uses "client"', r.stdout)


TASK = """---
id: 101
feature: demo
status: in-progress
attempts: 0
files: [src/, tasks/]
---
# 101 — open accounts

## Acceptance Criteria
- AC-1 (FR-1): opens

## Proof
| AC | Proof |
|---|---|
| AC-1 | `make proof` |

## Log
"""


class Round(unittest.TestCase):
    """reef-claims.py round, part (d): the round's code FAIL is a refusal; a NIT is printed, never refused."""

    def setUp(self):
        self.d = project()
        write(self.d, "tasks/101-open.md", TASK.replace("customer", ""))
        git(self.d, "add", "-A"); git(self.d, "commit", "-qm", "task")

    def round(self):
        return subprocess.run([sys.executable, CLAIMS, "round", "tasks/101-open.md", "--repo", self.d], capture_output=True, text=True, cwd=self.d)

    def test_a_code_fail_refuses_the_round(self):
        write(self.d, "src/b.py", "client = 1\n")
        r = self.round()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('round: REFUSED — glossary: src/b.py:1 uses "client" — the glossary says Account (Avoid: customer, client)', r.stdout)

    def test_a_nit_is_printed_and_the_round_holds(self):
        write(self.d, "src/b.py", "x = 1  # for the client\n")
        r = self.round()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('glossary: NIT — src/b.py:1 uses "client"', r.stdout)

    def test_the_task_folder_is_not_scanned(self):
        write(self.d, "tasks/101-open.md", TASK + "- rename every customer to account\n")
        r = self.round()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("tasks/101-open.md", r.stdout)


def owner(d, q):
    return subprocess.run([sys.executable, APPROVAL, "--owner", q], capture_output=True, text=True, cwd=d, env=dict(os.environ, REEF_NO_RESUME="1"))


def candidates(d):
    return subprocess.run([sys.executable, GLOSSARY, "candidates", "--repo", d], capture_output=True, text=True, cwd=d)


def question(d, term):
    m = re.search(rf"Approve retiring glossary term {re.escape(term)} at [0-9a-f]{{16}}\?", candidates(d).stdout)
    assert m, candidates(d).stdout
    return m.group(0)


class Prune(unittest.TestCase):
    def setUp(self):
        self.d = project(GLOSS + "| Spec | The raw description. | |\n")

    def test_an_unused_term_is_a_candidate_and_a_used_one_is_not(self):
        out = candidates(self.d).stdout
        self.assertIn('glossary: "Spec" appears nowhere outside docs/glossary.md', out)
        for used in ("Account", "Work item", "Ledger"):
            self.assertNotIn(f'"{used}"', out)

    def test_a_plural_and_a_snake_case_use_count(self):
        write(self.d, "src/b.py", "specs = []\nwork_item = 1\n")
        write(self.d, "src/app.py", "def open_account(accounts):\n    return accounts\n")
        git(self.d, "add", "-A"); git(self.d, "commit", "-qm", "uses")
        out = candidates(self.d).stdout
        self.assertNotIn('"Spec"', out)
        self.assertNotIn('"Work item"', out)
        self.assertNotIn('"Account"', out)

    def test_the_history_file_is_no_use(self):
        write(self.d, "docs/glossary-history.md", "- retired: | Spec | old |\n")
        git(self.d, "add", "-A"); git(self.d, "commit", "-qm", "h")
        self.assertIn('"Spec"', candidates(self.d).stdout)

    def test_the_owners_approval_moves_the_row_to_the_history(self):
        r = owner(self.d, question(self.d, "Spec"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("glossary term Spec retired", r.stdout)
        with open(os.path.join(self.d, "docs", "glossary.md"), encoding="utf-8") as f:
            self.assertNotIn("| Spec |", f.read())
        with open(os.path.join(self.d, "docs", "glossary-history.md"), encoding="utf-8") as f:
            self.assertRegex(f.read(), r"(?m)^- \d{4}-\d\d-\d\d retired: \| Spec \| The raw description\. \| \|$")
        with open(os.path.join(self.d, ".reef", "approvals", "glossary-spec.json"), encoding="utf-8") as f:
            rec = json.load(f)
        self.assertEqual((rec["action"], rec["term"], rec["by"]), ("retire-term", "Spec", "owner"))

    def test_the_hook_takes_the_owners_answer(self):
        payload = {"tool_name": "AskUserQuestion", "cwd": self.d, "tool_response": {"answers": {question(self.d, "Spec"): "Approve"}}}
        subprocess.run([sys.executable, APPROVAL], input=json.dumps(payload), capture_output=True, text=True, cwd=self.d)
        with open(os.path.join(self.d, "docs", "glossary.md"), encoding="utf-8") as f:
            self.assertNotIn("| Spec |", f.read())

    def test_a_stale_digest_a_term_used_since_and_an_unknown_term_write_nothing(self):
        q = question(self.d, "Spec")
        write(self.d, "docs/glossary.md", GLOSS + "| Spec | The raw description, sharpened. | |\n")
        self.assertIn("stale", owner(self.d, q).stdout)
        q = question(self.d, "Spec")
        write(self.d, "src/spec.py", "spec = 1\n")
        git(self.d, "add", "-A"); git(self.d, "commit", "-qm", "used")
        self.assertIn("is used outside", owner(self.d, q).stdout)
        self.assertIn("no such term", owner(self.d, "Approve retiring glossary term Nope at 0123456789abcdef?").stdout)
        with open(os.path.join(self.d, "docs", "glossary.md"), encoding="utf-8") as f:
            self.assertIn("| Spec |", f.read())
        self.assertFalse(os.path.exists(os.path.join(self.d, "docs", "glossary-history.md")))
        self.assertFalse(os.path.exists(os.path.join(self.d, ".reef", "approvals", "glossary-spec.json")))

    def test_another_answer_writes_nothing(self):
        payload = {"tool_name": "AskUserQuestion", "cwd": self.d, "tool_response": {"answers": {question(self.d, "Spec"): "Keep"}}}
        subprocess.run([sys.executable, APPROVAL], input=json.dumps(payload), capture_output=True, text=True, cwd=self.d)
        with open(os.path.join(self.d, "docs", "glossary.md"), encoding="utf-8") as f:
            self.assertIn("| Spec |", f.read())

    def test_the_tick_commits_the_glossary_and_the_history_once(self):
        owner(self.d, question(self.d, "Spec"))
        write(self.d, "src/other.py", "x = 1\n")   # another change stays out of the commit
        subprocess.run([sys.executable, LOOP, "tick", "--repo", self.d], capture_output=True, text=True, cwd=self.d,
                       env=dict(os.environ, REEF_NO_RESUME="1"))
        files = git(self.d, "show", "--name-only", "--format=%s", "HEAD").stdout.split()
        self.assertIn("docs/glossary.md", files)
        self.assertIn("docs/glossary-history.md", files)
        self.assertNotIn("src/other.py", files)
        n = git(self.d, "rev-list", "--count", "HEAD").stdout
        subprocess.run([sys.executable, LOOP, "tick", "--repo", self.d], capture_output=True, text=True, cwd=self.d,
                       env=dict(os.environ, REEF_NO_RESUME="1"))
        self.assertEqual(git(self.d, "rev-list", "--count", "HEAD").stdout, n, "a second tick commits nothing")

    def test_the_doctor_names_the_candidate_with_the_owners_command(self):
        r = subprocess.run([sys.executable, DOCTOR, "--repo", self.d], capture_output=True, text=True, cwd=self.d)
        line = next((l for l in r.stdout.splitlines() if '"Spec"' in l), "")
        self.assertTrue(line.startswith("WARN"), r.stdout)
        self.assertRegex(line, r' — python3 scripts/reef-approval\.py --owner "Approve retiring glossary term Spec at [0-9a-f]{16}\?"$')
        screen = load_script("reef")
        items = [i for i in screen.inbox(self.d, doctor=[line], runner=(0, 0, "")) if "Spec" in i["text"]]
        self.assertEqual(len(items), 1, "the inbox turns the doctor's line into one item")


class Contracts(unittest.TestCase):
    def test_the_acceptance_agent_runs_the_check(self):
        with open(os.path.join(ROOT, "agents", "acceptance.md"), encoding="utf-8") as f:
            self.assertIn("reef-glossary.py check", f.read())

    def test_init_copies_the_script(self):
        self.assertIn("reef-glossary.py", load_script("reef-init.py").SCRIPTS)


if __name__ == "__main__":
    unittest.main()
