"""The test suites' shared fixtures, once (docs/design/lightening.md step 3, 2026-10-31): a file imports the shape it used, under
the name it used — `from _fixtures import git_out as git` reads as the file always read. A suite's own `project()` stays its own:
that is the world its tests run in, built on `git_repo()`."""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDENTITY = ["-c", "user.email=t@t", "-c", "user.name=t"]   # a commit needs an author; the CI runner has none


def write(root, rel, text):
    """`rel` under `root`, its folders made, written whole; the path."""
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def stamped(root):
    """`root` as a reef-init'd layout whose plan stamp is fresh now, for a suite whose subject is not the stamp: the plan check's
    copy (it only marks the layout, and a Reef project without it denies every dispatch since the review after #261), a brief,
    and the stamp the plugin's own check writes — called right before the dispatch the test is about. A plan the check fails
    (a cycle, a duplicate id) gets no stamp; the guard then names the check's failure."""
    import shutil
    import sys
    for n in ("reef-plan-check.py", "reef_common.py"):
        if not os.path.isfile(os.path.join(root, "scripts", n)):
            os.makedirs(os.path.join(root, "scripts"), exist_ok=True)
            shutil.copy(os.path.join(ROOT, "scripts", n), os.path.join(root, "scripts", n))
    if not any(os.path.isfile(os.path.join(root, b)) for b in ("CLAUDE.md", "AGENTS.md")):
        write(root, "CLAUDE.md", "# brief\n")
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reef-plan-check.py"), root], capture_output=True, text=True)


def git(d, *a, check=False):
    """`git -C d …` with the test identity: the CompletedProcess (text, captured); `check` raises on a non-zero exit."""
    return subprocess.run(["git", "-C", d, *IDENTITY, *a], check=check, capture_output=True, text=True)


def git_checked(d, *a):
    """The CompletedProcess; a failure raises (the suites that never expect git to fail)."""
    return git(d, *a, check=True)


def git_out(d, *a):
    """git's stdout, as printed (a failure raises)."""
    return git(d, *a, check=True).stdout


def git_text(d, *a):
    """git's stdout, stripped (a failure raises)."""
    return git_out(d, *a).strip()


def git_repo(prefix="reef-test.", branch="main", config=None, identity=False):
    """A temporary git repository, `branch` checked out; with `config`, .reef/config.json written; with `identity`, the author set
    in its config (a merge commit made by a script reads it there)."""
    d = tempfile.mkdtemp(prefix=prefix)
    subprocess.run(["git", "init", "-q", "-b", branch, d], check=True)
    if identity:
        subprocess.run(["git", "-C", d, "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", d, "config", "user.name", "t"], check=True)
    if config is not None:
        write(d, os.path.join(".reef", "config.json"), json.dumps(config) if not isinstance(config, str) else config)
    return d


def load_script(name, modname=None):
    """A script under scripts/ as a module, fresh each call (its globals can be replaced by a test)."""
    loader = importlib.machinery.SourceFileLoader(modname or "reef_" + name.replace("-", "_").replace(".py", "") + "_under_test", os.path.join(ROOT, "scripts", name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod
