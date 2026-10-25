"""Reef runs on the Python a Mac already has (0.7.3, the first adoption, 2026-10-25): macOS's /usr/bin/python3 is 3.9.
`reef-merge-close` and `reef-handoff` were SyntaxErrors there — an f-string with a backslash, and one nesting its own
quotes, both legal only from 3.12 — so a task could not merge and the guard's checkpoint wrote no handoff. CI tested on
3.12+ only and never saw it. Two guards: every Python file of Reef compiles under the running interpreter (the macOS CI leg
runs /usr/bin/python3), and on 3.12+ no f-string expression uses what only 3.12 allows."""
import ast
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLOOR = (3, 9)


def python_files():
    for d in ("scripts", ".githooks", "hooks", "templates"):
        base = os.path.join(ROOT, d)
        for dirpath, _, names in os.walk(base):
            for n in sorted(names):
                p = os.path.join(dirpath, n)
                if n.endswith(".py"):
                    yield p
                elif "." not in n:
                    try:
                        with open(p, encoding="utf-8") as f:
                            first = f.readline()
                    except (OSError, UnicodeDecodeError):
                        continue
                    if first.startswith("#!") and "python" in first:
                        yield p


def newer_than_floor(src):
    """f-string expressions that are legal only from 3.12 (PEP 701): a backslash, or the enclosing quote."""
    tree = ast.parse(src)
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        whole = ast.get_source_segment(src, node) or ""
        body = whole.lstrip("rRbBfFuU")
        quote = body[:3] if body[:3] in ('"""', "'''") else body[:1]
        for part in node.values:
            if not isinstance(part, ast.FormattedValue):
                continue
            expr = ast.get_source_segment(src, part.value) or ""
            if "\\" in expr or (quote and quote in expr):
                bad.append(f"line {node.lineno}: {expr[:60]!r}")
    return bad


class PythonFloor(unittest.TestCase):
    def test_every_reef_python_file_compiles_here(self):
        files = list(python_files())
        self.assertGreater(len(files), 20, "the walk found Reef's scripts")
        broken = []
        for p in files:
            with open(p, encoding="utf-8") as f:
                src = f.read()
            try:
                compile(src, p, "exec")
            except SyntaxError as e:
                broken.append(f"{os.path.relpath(p, ROOT)}:{e.lineno}: {e.msg}")
        self.assertEqual(broken, [], f"SyntaxError under Python {sys.version.split()[0]} (Reef's floor is "
                                     f"{FLOOR[0]}.{FLOOR[1]}, macOS's /usr/bin/python3)")

    @unittest.skipIf(sys.version_info < (3, 12), "positions inside f-strings are exact from 3.12; below it compile() is the check")
    def test_no_f_string_needs_python_3_12(self):
        found = []
        for p in python_files():
            with open(p, encoding="utf-8") as f:
                src = f.read()
            found += [f"{os.path.relpath(p, ROOT)} {b}" for b in newer_than_floor(src)]
        self.assertEqual(found, [], "an f-string expression with a backslash or its own quote is a SyntaxError before 3.12; "
                                    "compute it into a variable first")

    def test_the_check_catches_both_shapes(self):
        self.assertTrue(newer_than_floor('x = f"{re.sub(r\'\\d\', \'\', s)}"\n') if sys.version_info >= (3, 12) else True)
        self.assertTrue(newer_than_floor("x = f'{p['a']}'\n") if sys.version_info >= (3, 12) else True)
        self.assertEqual(newer_than_floor("x = f\"{p['a']}\"\n"), [])


if __name__ == "__main__":
    unittest.main()
