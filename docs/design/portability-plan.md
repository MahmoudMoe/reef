# Portability — Reef beyond Claude Code

Written 2026-10-21, at the owner's request: "make Reef compatible with OpenCode and Codex, not bound by Claude and its
models." This is a decision document, not a build spec: one recommendation, the gate that decides it, and what gets
cut. Evidence marks: **[V]** verified in this repo · **[D]** official docs only · **[C]** community source only ·
**[?]** not checked.

## 1. The recommendation

"Not bound by Claude" is two questions: the **host** (the agent CLI that runs Reef) and the **models** (who judges and
builds). One host answers both:

- **OpenCode first.** 75+ providers, Anthropic by API key among them, so Claude stays possible and stops being required
  [D]. It has a pre-tool hook that can block [D], subagents with their own model [D], and a read-only permission it
  enforces (`edit: deny`) [D]. Closest fit to Reef's shape.
- **Codex only if a later need names it.** It has no Anthropic provider [D], so it trades one lock-in for another. It
  cannot enforce a read-only subagent [D], and its hooks run only after an interactive trust step [D]. Three blockers.
- **One adapter, not three.** Each host churns (OpenCode's v1 and v2 hook APIs already differ [D]). Every adapter is a
  standing cost against the size ratchet.

## 2. What is already portable [V]

About 80% of `scripts/` (11,243 lines) touches no Claude contract. The queue, task, ADR and journal files, AGENTS.md,
the git pre-commit gate, git and gh carry over as they are. Both OpenCode and Codex read AGENTS.md and SKILL.md
skills [D]. What is bound to Claude Code, hardest first:

| Coupling | What Reef needs from the host | Load |
|---|---|---|
| Guard hook (`reef-guard.py`, `hooks/hooks.json`) | A hook before every shell, edit and dispatch call that can deny it, **and that says which subagent is calling** | Safety |
| Subagent dispatch | A named agent type, a model per call, a read-only tool set for judges | Core flow |
| Headless runner (`reef-run.py`) | `claude -p` stream-json events: agent out and back, verdict, cost, session end | Night mode |
| Graph mode (`reef-graph-run.py`) | Claude Code's Workflow tool | Optional (`graph.mode: chat` exists) |
| Approval hook (`reef-approval.py`) | PostToolUse on `AskUserQuestion` | Core flow (a command path exists) |
| Telemetry (`reef-cost.py`, context ceiling) | Claude's transcript JSONL with token usage | Convenience (fails open) |
| Packaging | `.claude-plugin`, `${CLAUDE_PLUGIN_ROOT}` | Mechanical |
| Skill prose | Claude tool names: `/clear`, `Monitor`, `SendMessage`, `Workflow`, `Explore` | Docs rewrite |

## 3. The hard constraint: the guard must know the caller

Without `agent_id`/`agent_type` in the hook payload the guard treats every call as the main session, and the
reviewer lock (judges may not write) **silently never fires** (`reef-guard.py:1113`, `:326`) [V]. That is a safety
loss with no error.

- Claude Code sends both fields [V]. Codex lists them as hook fields [D]. OpenCode's `tool.execute.before` input has only a
  session id; a plugin maps it to the agent from `chat.params` **[V]** (phase 0).
- So "the guard knows the caller" is a precondition per host, checked before anything else is built.
- So the guard **fails closed** where another host's input enters: no caller, no call (phase 1). On Claude Code's own
  path a main-session call has no caller by design, so the rule cannot live there.

## 4. The phases

### Phase 0 — the gate (no Reef change)
Run Reef's existing probe on OpenCode by hand: a headless session dispatches a judge subagent, the judge attempts a
forbidden write, the guard (wired through a throwaway OpenCode plugin) denies it **and knows it was the judge**.
Pin one OpenCode version. **If the probe fails, the port stops here.** Cost: one session, about a day.

**Passed 2026-10-21** on OpenCode 1.19.3 (`docs/perf/opencode-probe-2026-10-21.md`): the plugin learns the caller
from `chat.params` (session → agent), and the guard refused the verifier's `git commit` and allowed the main agent's
`git status`. Section 3's open question is answered for v1.

### Phase 1 — neutral core, inside Claude Code (one PR, any host decision)
Behaviour on Claude stays the same; each item has a test.
1. The guard takes one normalized input (`reef_host`, `tool`, `agent`, `cwd`, the tool's fields) and translates it to
   the payload its checks already read; `hooks.json` keeps feeding it Claude's payload as before. The tokenizer and
   git/gh checks already need only a command string [V].
2. That input must name its caller (`agent`: `main` or the agent's name), or the guard refuses it (section 3). An
   unmapped tool is refused too. A Claude Code main session sends no caller by design, so the rule lives at this
   boundary, not on Claude's own path.

### Phase 2 — the OpenCode adapter (only after phase 0 passes)
- **Guard:** an OpenCode plugin that calls `reef-guard.py` with the normalized input and blocks on deny. Move what a
  glob can say into OpenCode's declarative permissions per agent; keep the script for what it cannot.
  The plugin blocks on **any** non-zero exit or a timeout, not only exit 2, as `hooks.json` does with
  `onFailure: block`: a crash in the guard (a dispatch check exits 1) must never read as an allow.
- **Agents:** generate `.opencode/agents/*.md` from `agents/*.md` (one source), judges with `edit: deny`.
- **Runner:** `reef-run.py --host opencode` runs `opencode run --format json`; one parser maps its events to the
  runner's lines. The event format is from source and community notes only **[C]**; record real payloads first, as
  `tests/fixtures/payloads/` does for Claude.
- **Models:** role aliases. Config says `roles.verifier: judge`, a `models` map says what `judge` means, and the
  agent-file generator writes the real model. Cut from phase 1: on Claude Code the alias needed resolving in the
  guard, `reef-attempt`, the plan check and five skills' prose for no gain. The graph runner's allow-list lacking
  `fable` [V] stays a note until then.
- **Skills:** stay SKILL.md. A short "host verbs" table per host replaces Claude tool names in the prose.

### Phase 3 — the measure
One qassimha batch on OpenCode with a non-Claude judge model, against the Claude baseline: merges, cost per row, and
verdict quality (verifier FAILs that were real, holes the hunter found). **Without this comparison the port cannot
claim parity.**

## 5. Cut, not ported

| Piece | Why it is cut on OpenCode | What replaces it |
|---|---|---|
| Graph mode | No Workflow tool [D] | `graph.mode: chat` (exists) |
| Stop hook | OpenCode has none; `session.idle` only notifies [D] | The runner's tick between sessions |
| Approval hook | No `AskUserQuestion` PostToolUse | `reef-approval.py`'s command path (exists) |
| Precise cost and context ceiling | No transcript a hook can read mid-session **[?]** | Usage from the run's `step_finish` events [V] (phase 0); the ceiling stays fail-open |

## 6. Flags for the owner

- **Claude through OpenCode means API pricing.** Anthropic does not allow Pro/Max subscriptions in third-party tools
  [D]. A night that costs $22 on Claude Code may cost more there with Claude models.
- **Codex headless needs a hook-trust override flag** to run hooks without the interactive trust step [D]. Expect this
  session's auto-mode classifier to refuse writing it into scripts or skills, as it refused the merge-rule text today.
- **Judge quality is the real unknown.** Reef's verdicts were tuned on Opus. A different judge model may pass what Opus
  failed. Phase 3 is where that shows.
- **Maintenance.** Two hosts double the probe, fixture and doc surface. Phase 1 is worth doing alone; phase 2 only if
  phase 0 passes and you want to run nights off Claude Code.

## 7. Not verified

The OpenCode and Codex JSON event formats, how an OpenCode hook learns its caller, Codex's subagent tool names and
session layout, and whether `codex exec` waits for background subagents. Codex's execpolicy rules files were not
researched. Sources: OpenCode docs (opencode.ai/docs: rules, skills, agents, permissions, plugins, cli, providers) and
Codex docs (learn.chatgpt.com/docs: hooks, subagents, non-interactive-mode, config-advanced), read 2026-10-21 at
OpenCode v1.19.3 and Codex CLI 0.163.0.
