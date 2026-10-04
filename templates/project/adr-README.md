# Architecture decision records

One short file per decision that closes off an alternative (a vendor, a data shape, a process rule): what was decided, why, which options were rejected and why, what it costs. Written before the PR that depends on it merges.

- **Draft on the item's branch** as `draft-<row>-<slug>.md`, cited as `draft-<row>`, with `Status: Accepted (number at merge)` and **no number**. A number chosen on a branch is read from a snapshot of `{{base}}` and consumed hours later, so parallel branches that each checked first take the same one.
- **Numbered on `{{base}}` at merge** by the single writer: `python3 scripts/reef-queue.py adr-number` renames every `draft-*.md` to the next `NNNN-<slug>.md` and rewrites citations.
- Shape (`templates/adr.md` in the Reef plugin): Status · Context (3 lines) · Decision (stated as fact) · Consequences (+ and −; "none" is a lie).
- `AGENTS.md`, the queue rules and the constitution change **in the same PR** as the code and its ADR, never as a side edit from another item.
