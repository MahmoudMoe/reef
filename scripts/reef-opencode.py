#!/usr/bin/env python3
# CLASS: code
"""Reef on OpenCode (0.7, portability phase 2): install the adapter into a project, so OpenCode runs Reef's skills, agents
and guard. Usage: reef-opencode.py install [--repo DIR] [--plugin DIR]
Writes, all regenerated on every run (machine-local: they carry absolute paths, so they are gitignored):
  .opencode/plugins/reef-guard.js   before every bash, write, edit and task call, the normalized input to reef-guard.py;
                                     the caller comes from `chat.params` (session -> agent); any non-zero exit or a timeout
                                     blocks; a tool not known to be read-only goes to the guard, which refuses what it
                                     cannot map
  .opencode/agents/reef:<name>.md   one per agents/*.md: the model is roles.<role> (a provider/model id); a judge gets
                                     `edit: deny`
  .opencode/skills/<skill>          a link to the plugin's skill
  .opencode/commands/reef-<x>.md    one per commands/*.md (/reef-loop, /reef-plan, ...)
  .opencode/reef-host.md            what the skills' Claude Code words mean here, read through opencode.json `instructions`
Not on OpenCode: graph mode (tasks run one dispatch each), the Stop and SessionStart hooks, the approval capture (the
owner approves in their own terminal with reef-approval.py --owner), the context ceiling (it fails open).
"""
import json
import os
import re
import sys

ROLE_OF = {"implementer": "author", "verifier": "verifier", "plan-reviewer": "plan_reviewer", "loophole-hunter": "adversary",
           "mechanic": "mechanic", "security": "security", "planner": "planner", "mahmoud": "proxy"}
JUDGES = ("verifier", "loophole-hunter", "plan-reviewer", "security", "mahmoud")
IGNORE = [".opencode/plugins/reef-guard.js", ".opencode/agents/reef:*", ".opencode/skills/reef-*", ".opencode/commands/reef*",
          ".opencode/reef-host.md"]

PLUGIN = r'''// Reef's guard for OpenCode, written by scripts/reef-opencode.py install. Regenerated on every install; do not edit.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
const GUARD = __GUARD__;
const TIMEOUT_MS = Number(process.env.REEF_GUARD_TIMEOUT_MS || 10000);
const TOOL = { bash: "shell", write: "write", edit: "edit", task: "dispatch" };
const READ_ONLY = new Set(["read", "glob", "grep", "list", "webfetch", "websearch", "codesearch", "todoread", "todowrite",
  "skill", "question", "invalid", "lsp"]);
const PRIMARY = new Set(["build", "plan"]);
function agentModel(dir, name) {
  try {
    const m = readFileSync(join(dir, ".opencode", "agents", `${name}.md`), "utf8").match(/^model:\s*(\S+)\s*$/m);
    return m ? m[1] : undefined;
  } catch { return undefined; }
}
export const ReefGuard = async ({ directory }) => {
  const agentOf = new Map();
  return {
    "chat.params": async (input) => { agentOf.set(input.sessionID, input.agent); },
    "tool.execute.before": async (input, output) => {
      if (READ_ONLY.has(input.tool)) return;
      const tool = TOOL[input.tool] || input.tool;
      const a = (output && output.args) || {};
      const agent = agentOf.get(input.sessionID);
      const payload = { reef_host: "opencode", tool, agent: agent === undefined ? undefined : (PRIMARY.has(agent) ? "main" : agent),
        agent_id: input.sessionID, cwd: a.workdir || directory, command: a.command, path: a.filePath, content: a.content,
        old: a.oldString, new: a.newString, subagent: a.subagent_type, prompt: a.prompt,
        model: tool === "dispatch" ? agentModel(directory, a.subagent_type) : undefined };
      const r = spawnSync("python3", [GUARD], { input: JSON.stringify(payload), encoding: "utf8", timeout: TIMEOUT_MS });
      if (r.status !== 0) {
        throw new Error("reef-guard: " + ((r.stderr || "").trim() || `denied (exit ${r.status}, ${r.signal || r.error || "no signal"})`));
      }
    },
  };
};
'''

HOST = '''# Reef on OpenCode

The skills are written in Claude Code's words. Here they mean:
- **The Agent / Task tool** is the `task` tool. Dispatch `reef:<role>` (`reef:verifier`, `reef:implementer`, …); its model is
  in its agent file (`.opencode/agents/`), so pass none. The guard checks that file against `roles.<role>`.
- **AskUserQuestion** does not exist. Ask in the chat. A plan or night approval is the owner's, in their own terminal:
  `python3 {plugin}/scripts/reef-approval.py --owner "Approve plan <slug> at <digest16>?"` (or `"Approve night <date> at
  <digest16>?"`). Never run it yourself: the guard refuses an agent running reef-approval.py.
- **Graph mode and the Workflow tool** do not exist: every task is its own dispatch (`/reef-task`); `graph.mode` stays `chat`.
- **`/clear`** means: end this session; the owner starts a fresh one, which reads the handoff head and one tick.
- **Monitor, ScheduleWakeup, SendMessage** do not exist: poll by re-running the command, and dispatch a fresh agent with the
  earlier one's file path instead of resuming it.
- **The scratchpad** for a judge's report is `$TMPDIR/opencode/reef/` (create it); the orchestrator copies the file with `cp`.
- The Stop hook and the session-start tick are not here: run `python3 scripts/reef-loop.py tick` at the start of a session.
'''


def die(msg):
    print(f"reef-opencode: {msg}", file=sys.stderr)
    sys.exit(2)


def frontmatter(text):
    m = re.match(r"\A---\n(.*?)\n---\n?(.*)\Z", text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        k, sep, v = line.partition(":")
        if sep and not line.startswith((" ", "#")):
            fm[k.strip()] = v.strip()
    return fm, m.group(2)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def install(repo, plugin):
    try:
        with open(os.path.join(repo, ".reef", "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        die(f"{repo} has no readable .reef/config.json — run reef-init first")
    roles = cfg.get("roles") if isinstance(cfg.get("roles"), dict) else {}
    oc = os.path.join(repo, ".opencode")
    write(os.path.join(oc, "plugins", "reef-guard.js"),
          PLUGIN.replace("__GUARD__", json.dumps(os.path.join(plugin, "scripts", "reef-guard.py"))))
    warnings = []
    for fn in sorted(os.listdir(os.path.join(plugin, "agents"))):
        if not fn.endswith(".md"):
            continue
        name = fn[:-3]
        fm, body = frontmatter(open(os.path.join(plugin, "agents", fn), encoding="utf-8").read())
        role = ROLE_OF.get(name)
        model = str(roles.get(role) or "").strip()
        lines = ["---", f"description: {fm.get('description', 'Reef ' + name)}", "mode: subagent"]
        if "/" in model:
            lines.append(f"model: {model}")
        else:
            warnings.append(f"roles.{role} = {model or 'unset'!r} is not a provider/model id; reef:{name} runs on the caller's "
                            f"model and the guard refuses its dispatch while roles.{role} is set — set it, e.g. 'openai/<model>'")
        for tier, t in (cfg.get("tiers") or {}).items():
            other = str(((t or {}).get("roles") or {}).get(role) or "").strip() if isinstance(t, dict) else ""
            if other and other != model and other.lower() != "none":
                warnings.append(f"tiers.{tier}.roles.{role} = {other!r} differs from roles.{role}: on OpenCode one agent file "
                                f"carries one model, so the guard refuses that tier's reef:{name} dispatches — make them equal")
        if name in JUDGES:
            lines += ["permission:", "  edit: deny"]
        write(os.path.join(oc, "agents", f"reef:{name}.md"), "\n".join(lines + ["---", ""]) + body)
    for skill in sorted(os.listdir(os.path.join(plugin, "skills"))):
        src, dst = os.path.join(plugin, "skills", skill), os.path.join(oc, "skills", skill)
        if not os.path.isfile(os.path.join(src, "SKILL.md")):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.islink(dst):
            os.remove(dst)
        if os.path.exists(dst):
            warnings.append(f"{os.path.relpath(dst, repo)} exists and is not Reef's link — left as it is")
            continue
        os.symlink(src, dst)
    for fn in sorted(os.listdir(os.path.join(plugin, "commands"))):
        if fn.endswith(".md"):
            name = fn if fn == "reef.md" else "reef-" + fn
            write(os.path.join(oc, "commands", name), open(os.path.join(plugin, "commands", fn), encoding="utf-8").read())
    write(os.path.join(oc, "reef-host.md"), HOST.replace("{plugin}", plugin))
    conf = os.path.join(repo, "opencode.json")
    if os.path.isfile(os.path.join(repo, "opencode.jsonc")):
        warnings.append('opencode.jsonc is yours: add ".opencode/reef-host.md" to its "instructions"')
    else:
        try:
            c = json.load(open(conf, encoding="utf-8")) if os.path.isfile(conf) else {"$schema": "https://opencode.ai/config.json"}
        except ValueError:
            die("opencode.json is not valid JSON — fix it, then install again")
        ins = c.get("instructions") if isinstance(c.get("instructions"), list) else []
        if ".opencode/reef-host.md" not in ins:
            c["instructions"] = ins + [".opencode/reef-host.md"]
            write(conf, json.dumps(c, indent=2) + "\n")
    gi = os.path.join(repo, ".gitignore")
    have = open(gi, encoding="utf-8").read().splitlines() if os.path.isfile(gi) else []
    missing = [l for l in IGNORE if l not in have]
    if missing:
        with open(gi, "a", encoding="utf-8") as f:
            f.write(("\n" if have and have[-1] else "") + "\n".join(missing) + "\n")
    for w in warnings:
        print(f"WARN {w}")
    print(f"reef-opencode: installed into {repo}/.opencode (plugin {plugin}); start OpenCode there and run /reef-loop")
    return 0


def main(argv):
    if not argv or argv[0] != "install" or "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0 if ("-h" in argv or "--help" in argv) else 2
    repo = os.path.abspath(argv[argv.index("--repo") + 1]) if "--repo" in argv else os.getcwd()
    plugin = os.path.abspath(argv[argv.index("--plugin") + 1]) if "--plugin" in argv else \
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return install(repo, plugin)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
