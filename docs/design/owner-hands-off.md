# The owner's hands off — Reef works for the owner, not the other way around

Written 2026-10-30, after the owner's first two rounds alone on the current adoption. In one day he typed two approvals,
answered four questions by hand, restarted the runner three times, was handed a `nohup` line for an 85-minute migration
and a log to tail, and read "a session ended with work in flight — stopped" with no way out. His words: "I work for Reef,
not the other way around."

## 1. The rule

**The owner makes decisions; Reef does everything else.** A decision is: approve a plan, answer a question, say stop,
set a limit. Everything that is not a decision — start, restart, resume, verify, run, clear, retry, update — is Reef's,
and a message that hands the owner such a step is a bug of the same class as a placeholder in a command.

## 2. The measurement

**Touches per row**: the times the owner typed something that was not a decision, from the row's grill to its close.
2026-10-30, rows 4 and 7 together: about seven. The target is zero; every touch that remains is a decision, made with one
key on the `reef` screen, or made by the proxy under the contract below.

## 3. The steps, one PR each, red first, in this order

0. **Autopilot — the proxy by day decides inside a standing contract.** `reef/proxy.md` names what Mahmoud (the owner's
   proxy, `reef:mahmoud`) decides on the owner's behalf by day — plan approvals, the owner's questions, hunter holes,
   found-row triage — and the hard limits (cost per row, rows per day, a touch of auth/pii/money, a release). Approved once,
   from the screen; shown there as `autopilot: on`, `a` toggles it (the approval question, or the record's removal). Inside
   the contract a decision goes to Mahmoud, who records it as the night does (`reef-approval.py --proxy --day`, a footnote
   with the day label), and the loop continues without a wait. The inbox holds only what the contract excludes or a limit
   stopped. A daily report, like the morning one, lists his decisions, each reversible by deleting its record.
1. **A decision continues the loop.** Enter on the screen, `reef approve`, `reef answer`, a proxy decision: once recorded,
   the runner starts again if it had stopped on that wait. Nobody types `--detach`.
2. **The runner never stops dead.** "Work in flight": it checks whether the work still runs (the marker's pid, its age);
   if not, it releases the marker itself, says so, and the task retries. "No progress": the cause becomes a question in
   the inbox, not an exit. Every exit that remains is a decision, shown as an item.
3. **Long work is Reef's** (shipped 2026-10-31 for the orchestrator's commands: `reef-run.py job`, the runner waits before every session, the headless prompt and the loop, task and review skills say so; the implementer's own brief: not yet). A task's command runs in the session's foreground and the session waits for it. One that
   outlives a session is started detached by Reef (`reef-run.py job <task> -- <command>`), recorded on the task, and picked
   up by the next session, which closes the task when the job's exit and its evidence say so. The implementer's brief and
   the headless prompt forbid a background job of the session's own and forbid handing the owner a command.
4. **The queue is lag-proof.** `add-row` prints the issue number beside the id; `row-issue` answers from Reef's own record
   of what it just created while GitHub's list catches up; `row-issue --closed` knows an archived row. No project script
   needs a retry loop around Reef.
5. **One screen, nothing else to watch.** The `reef` screen (second design) is where every decision is made; `watch` ends
   with the runner's last word; the desk is told when a decision is needed. The owner opens one thing.
6. **The update is Reef's too.** After a merge in Reef, the project's screen shows one item — `u` applies it, re-proves the
   setup and reloads; no reminder from anyone to run `reef update`.

## 4. What the owner does after this lands

Opens `python3 scripts/reef`, reads the inbox, presses Enter on each decision the contract left him, closes the laptop. The
runner runs rows to merge, asks on the screen when the contract says it must, tells the desk, and reports what Mahmoud
decided. Scored by §2 after step 6: touches per row, measured on the next two rows the owner runs alone.
