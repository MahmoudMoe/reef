"""Reef on OpenCode (0.7, portability phase 2, the owner's go 2026-10-23): `reef-opencode.py install` writes the plugin, the
agents, the skill links, the commands and the host notes; the plugin feeds the guard's normalized input with the caller and
blocks on any non-zero exit; the owner approves from their own terminal; an agent never runs reef-approval.py."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import test_night as N  # noqa: E402  (a project with a plan and a night contract)

OC = os.path.join(ROOT, "scripts", "reef-opencode.py")
GUARD = os.path.join(ROOT, "scripts", "reef-guard.py")
APPROVAL = os.path.join(ROOT, "scripts", "reef-approval.py")
RUN = os.path.join(ROOT, "scripts", "reef-run.py")


def project(roles, tiers=None):
    d = tempfile.mkdtemp(prefix="reef-oc.")
    subprocess.run(["git", "init", "-q", d], check=True)
    os.makedirs(os.path.join(d, ".reef"))
    with open(os.path.join(d, ".reef", "config.json"), "w") as f:
        json.dump({"roles": roles, "tiers": tiers or {}}, f)
    return d


def install(d):
    return subprocess.run([sys.executable, OC, "install", "--repo", d, "--plugin", ROOT], capture_output=True, text=True)


def read(d, *p):
    with open(os.path.join(d, *p), encoding="utf-8") as f:
        return f.read()


class Install(unittest.TestCase):
    def test_the_plugin_agents_skills_commands_and_host_notes_and_a_second_run_changes_nothing(self):
        d = project({"verifier": "openai/gpt-x", "author": "anthropic/claude-y", "adversary": "opus"},
                    {"critical": {"roles": {"verifier": "openai/other"}}})
        r = install(d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(json.dumps(GUARD), read(d, ".opencode", "plugins", "reef-guard.js"))
        v = read(d, ".opencode", "agents", "reef:verifier.md")
        self.assertIn("model: openai/gpt-x", v)
        self.assertIn("permission:\n  edit: deny", v, "a judge never edits")
        self.assertIn("RULE AC", v, "the agent's own prompt rides along")
        impl = read(d, ".opencode", "agents", "reef:implementer.md")
        self.assertIn("model: anthropic/claude-y", impl)
        self.assertNotIn("edit: deny", impl)
        self.assertNotRegex(read(d, ".opencode", "agents", "reef:loophole-hunter.md"), r"(?m)^model:", "'opus' is no provider/model id")
        self.assertIn("WARN roles.adversary = 'opus' is not a provider/model id", r.stdout)
        self.assertIn("WARN tiers.critical.roles.verifier = 'openai/other' differs from roles.verifier", r.stdout)
        self.assertEqual(os.path.realpath(os.path.join(d, ".opencode", "skills", "reef-loop")), os.path.realpath(os.path.join(ROOT, "skills", "reef-loop")))
        self.assertIn("reef-loop skill", read(d, ".opencode", "commands", "reef-loop.md"))
        self.assertTrue(os.path.isfile(os.path.join(d, ".opencode", "commands", "reef.md")))
        host = read(d, ".opencode", "reef-host.md")
        self.assertIn(f"python3 {ROOT}/scripts/reef-approval.py --owner", host)
        self.assertEqual(json.loads(read(d, "opencode.json"))["instructions"], [".opencode/reef-host.md"])
        gi = read(d, ".gitignore")
        r = install(d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(read(d, ".gitignore"), gi, "the ignore lines are added once")
        self.assertEqual(json.loads(read(d, "opencode.json"))["instructions"], [".opencode/reef-host.md"])

    def test_no_config_refuses_and_help_writes_nothing(self):
        d = tempfile.mkdtemp(prefix="reef-oc.")
        r = install(d)
        self.assertEqual(r.returncode, 2)
        self.assertIn("run reef-init first", r.stderr)
        r = subprocess.run([sys.executable, OC, "install", "--help"], capture_output=True, text=True, cwd=d)
        self.assertEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(d, ".opencode")), "--help is never data")


DRIVER = r'''
import { pathToFileURL } from "node:url";
const { ReefGuard } = await import(pathToFileURL(process.argv[2]).href);
const h = await ReefGuard({ directory: process.argv[3] });
await h["chat.params"]({ sessionID: "s1", agent: "reef:verifier" });
await h["chat.params"]({ sessionID: "s0", agent: "build" });
const call = async (sess, tool, args) => {
  try { await h["tool.execute.before"]({ tool, sessionID: sess, callID: "c" }, { args }); return "ok"; }
  catch (e) { return "blocked: " + e.message; }
};
const out = [];
out.push(await call("s1", "bash", { command: "git commit -m x" }));
out.push(await call("s0", "bash", { command: "git status" }));
out.push(await call("s9", "bash", { command: "git status" }));
out.push(await call("s0", "read", { filePath: "x" }));
out.push(await call("s0", "patch", { patchText: "x" }));
out.push(await call("s0", "task", { subagent_type: "reef:verifier", prompt: "p", description: "d" }));
console.log(JSON.stringify(out));
'''

FAKE = r'''import json, os, sys
p = json.load(sys.stdin)
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps(p) + "\n")
if "commit" in (p.get("command") or ""):
    print("reef-guard DENY: fake", file=sys.stderr); sys.exit(2)
sys.exit(1 if p.get("tool") == "patch" else 0)
'''


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class Plugin(unittest.TestCase):
    def setUp(self):
        self.d = project({"verifier": "openai/gpt-x"})
        self.assertEqual(install(self.d).returncode, 0)
        self.plugin = os.path.join(self.d, ".opencode", "plugins", "reef-guard.js")
        self.driver = os.path.join(self.d, "driver.mjs")
        with open(self.driver, "w") as f:
            f.write(DRIVER)

    def drive(self, env=None):
        r = subprocess.run(["node", self.driver, self.plugin, self.d], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_the_caller_reaches_the_guard_and_any_nonzero_exit_blocks(self):
        fake, log = os.path.join(self.d, "fake-guard.py"), os.path.join(self.d, "fake.log")
        with open(fake, "w") as f:
            f.write(FAKE)
        with open(self.plugin) as f:
            js = f.read()
        with open(self.plugin, "w") as f:
            f.write(js.replace(json.dumps(GUARD), json.dumps(fake)))
        out = self.drive(dict(os.environ, FAKE_LOG=log))
        sent = [json.loads(l) for l in open(log)]
        self.assertTrue(out[0].startswith("blocked: reef-guard: reef-guard DENY"), out[0])
        self.assertEqual(sent[0]["agent"], "reef:verifier", "the subagent's session maps to its name")
        self.assertEqual(out[1], "ok")
        self.assertEqual(sent[1]["agent"], "main", "a primary agent is the main session")
        self.assertNotIn("agent", sent[2], "an unknown session sends no caller; the real guard refuses it")
        self.assertEqual(out[3], "ok")
        self.assertEqual([p["tool"] for p in sent], ["shell", "shell", "shell", "patch", "dispatch"], "a read is never sent")
        self.assertTrue(out[4].startswith("blocked"), "exit 1 blocks too: a crash is never an allow")
        self.assertEqual((sent[4]["subagent"], sent[4]["model"]), ("reef:verifier", "openai/gpt-x"), "the dispatch carries the agent file's model")

    def test_with_the_real_guard_a_judge_commit_and_an_unknown_caller_are_refused(self):
        out = self.drive()
        self.assertIn("read-only", out[0])
        self.assertEqual(out[1], "ok")
        self.assertIn("without `agent`", out[2])
        self.assertIn("patch", out[4], "a tool the guard cannot map is refused")
        self.assertEqual(out[5], "ok", "the agent file's model equals roles.verifier")


class OwnerApproval(unittest.TestCase):
    def test_the_owner_approves_a_plan_from_their_own_terminal(self):
        d = N.project()
        dg = N.digest(d, "share-links")
        owner = lambda q: subprocess.run([sys.executable, APPROVAL, "--owner", q], capture_output=True, text=True, cwd=d)
        r = owner(f"Approve plan share-links at {dg}?")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(read(d, ".reef", "approvals", "share-links.json"))["digest16"], dg)
        r = owner("Approve plan share-links at " + "0" * 16 + "?")
        self.assertEqual(r.returncode, 1, "a stale digest writes nothing")
        self.assertIn("stale", r.stdout)
        self.assertEqual(owner("approve it").returncode, 2)

    def test_the_owner_approves_tonights_contract(self):
        d = N.project()
        r = subprocess.run([sys.executable, RUN, "contract", "--repo", d], capture_output=True, text=True)
        q = [l for l in r.stdout.splitlines() if l.startswith("question: ")][0][len("question: "):]
        r = subprocess.run([sys.executable, APPROVAL, "--owner", q], capture_output=True, text=True, cwd=d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(read(d, ".reef", "approvals", "night.json"))["rows"], ["12"])


class AnAgentNeverApproves(unittest.TestCase):
    """2026-10-23: piping a made-up answered question into reef-approval.py approved a plan; the guard let any agent run it."""

    def guard(self, cmd):
        payload = {"tool_name": "Bash", "cwd": tempfile.gettempdir(), "tool_input": {"command": cmd}}
        return subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True)

    def test_only_the_proxy_runs_it_and_reading_it_is_fine(self):
        for cmd in ('python3 scripts/reef-approval.py --owner "Approve plan x at 0123456789abcdef?"',
                    "echo '{}' | python3 scripts/reef-approval.py", "scripts/reef-approval.py --root .",
                    "env A=1 python3 -u scripts/reef-approval.py"):
            with self.subTest(cmd=cmd):
                r = self.guard(cmd)
                self.assertEqual(r.returncode, 2, cmd)
                self.assertIn("the OWNER's approval", r.stderr)
        for cmd in ("python3 scripts/reef-approval.py --proxy --feature x --report y", "cat scripts/reef-approval.py",
                    "grep -n owner scripts/reef-approval.py"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.guard(cmd).returncode, 0, cmd)


if __name__ == "__main__":
    unittest.main()
