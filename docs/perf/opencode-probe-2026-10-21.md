# OpenCode probe — phase 0 of the portability plan

Run 2026-10-21, by hand, in a scratch git repository (not a real project). Question: can Reef's guard, wired into
OpenCode, refuse a judge's forbidden command **and know the judge made it**? Without the caller, the reviewer lock
never fires (`docs/design/portability-plan.md`, section 3).

**Result: passed.** The guard refused the verifier's `git commit` with the reviewer-lock reason and allowed the main
agent's `git status`; no commit was made.

## Setup
- OpenCode 1.19.3 (`npm install -g opencode-ai@1.19.3`), plugin API `@opencode-ai/plugin` 1.19.3.
- Model: `opencode/deepseek-v4.1-flash-free` (OpenCode's free hosted tier, no credentials). Only the probe prompt
  below left the machine.
- Guard: `scripts/reef-guard.py` from main at 535cd85 (phase 1: the normalized input, the caller required).
- Project config: `opencode.json` allows bash and edit, so OpenCode's own permissions decide nothing and the guard
  is the only gate.
- One subagent, `.opencode/agents/verifier.md` (`mode: subagent`, no model: it runs on the caller's).

## How the plugin knows the caller
- `tool.execute.before` receives `tool`, `sessionID`, `callID` and the tool's `args`; **no agent name**.
- `chat.params` runs before every model request with `sessionID` and `agent`. The plugin keeps a session → agent
  map from it. A subagent runs in its own child session, so its tool calls map to its own name.
- Primary agents (`build`, `plan`) are sent as `agent: "main"`; any other name as itself. A session with no recorded
  agent sends no `agent`, and the guard refuses it.
- The plugin sends the normalized input (`reef_host`, `tool`, `agent`, `cwd`, the tool's fields), and **throws on any
  non-zero exit or timeout**, which OpenCode reports to the model as the tool's error.
- Tool argument names seen: `bash` → `command`; `task` → `description`, `prompt`, `subagent_type`. `write` and
  `edit` (`filePath`, `content`, `oldString`, `newString`) were not exercised.

## The prompt
> Do exactly two things, in order. 1) Use the task tool to start the subagent named verifier, with this exact prompt:
> "Run: git commit --allow-empty -m probe-judge". 2) After it returns, run `git status --short` yourself with the bash
> tool. Then report what each step printed, including any error, verbatim.

## The guard's log
| Tool | Session | Caller sent | Command | Guard exit |
|---|---|---|---|---|
| task | main (`ses_ea0dd4…`) | `main` | dispatch `verifier` | 0 |
| bash | child (`ses_ea0dd2…`) | `verifier` | `git commit --allow-empty -m probe-judge` | **2**: `verifier is read-only: git commit mutates the tree or the refs the orchestrator hash-checks` |
| bash | main (`ses_ea0dd4…`) | `main` | `git status --short` | 0 |

`git log` after the run: the initial commit only.

## What the run stream shows (`opencode run --format json`)
- Event types: `step_start`, `text`, `tool_use`, `step_finish`; each carries `sessionID` and `part`.
- `step_finish.part.tokens` has `input`, `output`, `reasoning`, `cache.read`, `cache.write`, plus `cost`: the
  runner's usage source.
- The subagent's own tool calls are **not** in the parent's stream; the `task` tool's output carries its result.
  The runner's "agent out and back" line comes from the `task` `tool_use` event.

## Not covered
- `write` and `edit` through the plugin; a dispatch with a per-call model (the `task` call here carried no model argument).
- A guard crash or timeout reaching the plugin (the code throws on both; not provoked).
- Parallel subagents, and any OpenCode version other than 1.19.3 (v2's plugin API differs).
