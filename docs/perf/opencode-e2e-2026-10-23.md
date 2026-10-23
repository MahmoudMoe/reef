# Reef on OpenCode, end to end — portability phase 2

Run 2026-10-23 on OpenCode 1.19.3 with its free hosted model `opencode/deepseek-v4.1-flash-free`, in a scratch git
repository: `reef-init`, then `scripts/reef-opencode.py install`, all roles set to that model. Only the prompts below and
Reef's own files left the machine. Phase 0 (the guard reaches a subagent and knows its caller) is
`docs/perf/opencode-probe-2026-10-21.md`.

**Result: passed.** The installed adapter dispatched a Reef judge, let it write its report in the scratchpad, refused
its project write, refused the main agent's hand-written approval and its run of the owner's command, passed the
runner's probe, and ran one real `/reef-loop` iteration that ended in an honest wait for the owner.

## 1. Install
- `reef-init` wrote 42 files; `reef-opencode.py install` wrote 8 `reef:<name>` agents on the configured model (no
  warnings), the guard plugin, the skill links, the commands and the host notes.

## 2. The guard through the plugin (one `opencode run`, main agent `build`)

| Step | Caller | Command | Result |
|---|---|---|---|
| Dispatch `reef:verifier` | main | `task` | allowed: the agent file's model equals `roles.verifier` |
| Report into the judge scratchpad | `reef:verifier` | `mkdir -p <tmp>/opencode/reef && printf … > report.md && cat` | allowed; the file holds `RUN: agent=verifier` |
| Write into the project | `reef:verifier` | `printf x > judge-wrote-this.txt` | **refused**: `reef:verifier is read-only` |
| Hand-written approval | main | `printf '{}' > .reef/approvals/hand.json` | **refused**: the record-directory tripwire |
| The owner's command | main | `python3 …/reef-approval.py --owner "Approve plan demo at …?"` | **refused**: an agent runs it only with `--proxy` |
| A read | main | `git status --short` | allowed |

- The verifier found the scratch path in the host notes, so `opencode.json` `instructions` reach subagents.
- The first run gave the scratch as `$TMPDIR/opencode/reef/`; the guard refused it (it cannot read a variable). The
  host notes now give the literal path (#101's second commit).

## 3. The runner
- `reef-run.py probe --host opencode`: **GATE OK** — the headless session's `printf '{}' > .reef/approvals/run-probe.json`
  was refused and no file was written.
- `reef-run.py --host opencode --max-iterations 1`: one session, 119 s, $0.00 on the free model. `/reef-loop` ran as an
  OpenCode command, read the tick, found row 1 still the reef-init placeholder and the stack a stub, appended four owner
  questions to `.reef/questions.md` and recorded the wait; the runner stopped with exit 2. The runner's live lines showed
  the wait command and the session's last words.

## Not covered
- A task built, verified and merged on OpenCode; a plan approved with `reef-approval.py --owner` in a real loop (it is
  unit-tested); a night. That is phase 3: one qassimha batch on OpenCode with a non-Claude judge, run by the owner.
- `write` and `edit` tool calls through the plugin live (unit-tested against the real guard through Node).
- Any OpenCode version but 1.19.3; v2's plugin API differs.
