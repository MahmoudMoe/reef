# Hardening PR-9 — the glossary's banned words checked by code, its dead terms proposed for retirement

Today `templates/glossary.md` (rendered to `paths.glossary`, default `docs/glossary.md`) is a `Term | Definition` table. The only
reader is the acceptance agent, which is asked to spot "glossary nouns not in the glossary" by eye (`agents/acceptance.md:21`).
Nothing says which words a term replaces, nothing checks that a round does not bring them back, and the table only grows.
Idea from mattpocock/skills (domain-modeling, GLOSSARY-FORMAT): each term carries the words to avoid; project terms only, no
implementation details.

## 1. Format (backward compatible)

```
| Term | Definition | Avoid |
|---|---|---|
| Task | One vertical slice in `tasks/NNN-slug.md` … | ticket, story |
```

- The table whose header row has a `Term` cell is the glossary. A column headed `Avoid` (any case) lists the banned synonyms,
  comma-separated; an empty cell bans nothing. A two-column glossary (every project today) parses as before, with no avoids.
- The template gets the column and one sentence: an Avoid word is a synonym the project has stopped using; the check below
  enforces it. Project-specific terms only (the template already says "one canonical name per concept").

## 2. The check (code) — `scripts/reef-glossary.py`, new, `# CLASS: code`

`reef-glossary.py check [<rev>] [--repo DIR]` — the worktree (tracked changes and untracked files) against
`git merge-base <rev> HEAD` (default `HEAD`). `reef-claims.py round` calls the same function as a NEW part (d), with its own base.

- **The words**: the Avoid cells of the base's glossary UNION the worktree's. A round cannot drop an Avoid word to get past the
  check; a round may add one.
- **What is scanned**: the ADDED lines of every changed path, except the glossary file, its history file (§3) and, in the round,
  the task's folder (a task quoting the rename it asks for).
- **The match**: case-insensitive, whole words, an optional plural `s`/`es`. Identifiers are split first (`customerId`,
  `customer_id`, `customer-id` → `customer id`), so a banned word inside an identifier or a schema key is found; a multi-word
  Avoid (`work item`) matches across a space, `_`, `-` or a camelCase boundary.
- **Net new only**: per path and word, a match counts only when the added lines hold more of it than the removed lines. A round
  editing a legacy line that already says the old word is not made to rename the codebase (out of its scope, PR-1 (b)).
- **The verdict** (recommended split, flagged for the owner — decision 1):
  - **FAIL** — a non-comment line of a code or schema file (not `is_doc`, not a comment by `reef-claims`' own `is_comment`):
    the identifier, key or string a program reads. In the round: `round: REFUSED — glossary: src/a.py:12 uses "customer" —
    the glossary says Account (Avoid: customer)`. The refusal is a `round-other` class for PR-3's lessons (no new class).
  - **NIT** — a doc file (`is_doc`) or a comment line: printed `glossary: NIT — …`, never refused. The acceptance agent reports
    it as a NIT.
- No glossary file, or no Avoid word: `glossary: no Avoid words — not checked` (exit 0).
- Exit 0 no FAIL · 1 a FAIL · 2 bad usage or git error.

## 3. Pruning — retirement candidates, retired only on the owner's approval (PR-3's pattern)

- **Candidate** (code): a term whose word (whole word, case-insensitive, optional plural; a multi-word term across space/`_`/`-`)
  appears in no tracked file of the main checkout except the glossary and its history file (`git grep`).
- **Where it shows**: `reef doctor` prints one line per candidate:
  `WARN glossary: "Spec" appears nowhere outside docs/glossary.md — retire it? — python3 scripts/reef-approval.py --owner "Approve retiring glossary term Spec at <digest16>?"`.
  The `reef` screen's inbox already turns a doctor WARN whose fix is a command into an item, so the inbox and report code
  (another session's) are not touched.
- **The question**: `Approve retiring glossary term <Term> at <digest16>?`, digest16 = the first 16 hex of sha256 over
  `retire-term`, the term and its row as written. Answered `Approve` through the AskUserQuestion hook or
  `reef-approval.py --owner` (the guard already refuses an agent running `--owner`); no `--proxy` path takes it — the owner's
  only, like a lesson.
- **On the approval** (`reef-glossary.py`'s `approve`, called by `reef-approval.py`): refused, nothing written, when the digest
  is stale (the row changed), the term is gone, or the term is now used outside the glossary (a candidate is re-checked).
  Else the row is removed from the glossary, appended to `<glossary dir>/glossary-history.md`
  (`- 2026-11-17 retired: | Spec | … |`, created with a header, never deleted), and the record
  `.reef/approvals/glossary-<slug>.json` (`{action: retire-term, term, digest16, digest, approved_at, by: owner, paths}`) written.
- **The commit** (PR-3's decisions 5 and 6, followed — decision 3): the approval only writes; the next `reef-loop.py tick`
  commits exactly the glossary and history files under the pre-commit gate (reusing reef-lessons.py's `commit` helper, not
  changing it) and marks the record `committed_at`. A refused commit leaves the files; the doctor names it
  (`WARN glossary: retirement of Spec not committed — <why>`) until a tick commits it.

## 4. The acceptance agent

`agents/acceptance.md:21` — "glossary nouns not in the glossary" becomes: run `python3 scripts/reef-glossary.py check
<branches.base>` and report each `glossary: NIT` line as a NIT (a FAIL already refused the round); a NEW user-facing noun
without a glossary row is still a NIT by eye. Only that phrase of the line changes (another session adds a separate line).

## Wiring

- `reef-init.py` SCRIPTS gets `reef-glossary.py` (the round check loads it as a sibling in the project's `scripts/`).
- `reef-approval.py`: one regex and one branch beside the lesson one; the `--owner` usage line names the new question.
- `reef-doctor.py`: one section, `glossary`, loading the plugin's `reef-glossary.py`.
- `reef-loop.py tick`: one try-block beside the lessons' commit.
- `reef-claims.py round`: part (d) appended after (c); (a), (b), (c) unchanged.

## Tests (each red on the unchanged code first) — `tests/test_glossary.py`

- format: a three-column glossary yields its Avoid words; a two-column one parses with none; empty cells ban nothing.
- check: a banned word in a code line FAILs (exit 1); in a camelCase / snake_case identifier and a JSON key FAILs; in a `.md`
  and in a comment is a NIT (exit 0); a plural matches; a word containing it (`customers` yes, `customerservice` no) — whole
  words only; a legacy line edited with the word on both sides is not flagged; the glossary file itself is ignored; an Avoid
  word removed by the round from the glossary is still enforced (base ∪ worktree); a two-column glossary checks nothing.
- round: `reef-claims.py round` refuses with the `glossary:` line on a code FAIL and passes with a NIT printed (part (d)).
- candidates: an unused term is a candidate; a term used in code (or in plural, or as `work_item`) is not; the history file
  does not count as a use.
- approval: `--owner "Approve retiring glossary term X at <d16>?"` removes the row, appends the history line, writes the record;
  a stale digest, a term used since, an unknown term: nothing written; the `--proxy` path refuses it.
- commit: the tick commits the glossary and history files only, once; a second tick commits nothing.
- doctor: prints the candidate line with the approve command; the screen's inbox makes it an item (existing parser).
- contracts: `agents/acceptance.md` names `reef-glossary.py check`; the template has the Avoid column.

## Out of scope

- the guard protecting the glossary file from an agent's edit (the base ∪ worktree rule covers the dodge inside a round).
- checking that a new noun is in the glossary (stays the acceptance agent's NIT by eye), or a term's definition being true.
- any change to the report (`reef-run.py`) or inbox (`scripts/reef`) code, `APPROVE_Q`, or refactor of reef-claims' parts.

## Owner decisions (conservative defaults implemented; flagged to the orchestrator)

1. **Verdict split**: FAIL for a code identifier / schema key / code string (round refused), NIT for docs and comments.
   Conservative alternative: NIT everywhere. Recommended and implemented: the split.
2. **Net new only** (an edited legacy line is not flagged). Alternative: every added line.
3. **Commit on the tick** like PR-3 decisions 5/6. Alternative: no commit (the owner commits).
4. **Candidates in `reef doctor`** (and so the inbox), not the night report's sections.
