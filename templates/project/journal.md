# Journal — {{name}}

Append-only. One entry per merge, written on `{{base}}` by the single writer at the merge, never on the item's branch. Newest at the bottom. When this file passes the word ceiling in `.reef/config.json` `writing.journal_words`, its oldest entries move whole and unedited to `journal-archive.md` beside this file.

An entry records what was attempted, what was verified **and how**, and what remains untrue. It is where "I could not check this" gets said out loud, with the probe that was run.

| Task | Implementer | Verifier | Attempts | Result | ACs | Escaped defects | Orchestrator |
|---|---|---|---|---|---|---|---|

`ACs` records every criterion's status — `AC-1 achieved; AC-2 partially-verified (Missing: … Next: …)` — from `not-verified | partially-verified | achieved | contradicted` (default `not-verified`); a status other than `achieved` carries `Missing:` and `Next:`.

`Orchestrator` is the main session's context growth the task cost, from `python3 scripts/reef-cost.py growth <id>` (summed over sessions; the Stop hook records it). Over `caps.task_growth`, the row says why.
