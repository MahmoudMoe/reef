# Glossary
One canonical name per concept — used in code identifiers, schemas, and docs. A commit introducing a new user-facing noun or type amends this table in the same commit. Project terms only, no implementation details.

**Avoid** lists the synonyms the project stopped using, comma-separated. They are checked by code (`scripts/reef-glossary.py check`; the round check refuses one added in a code or schema line, a doc or comment is a NIT). A term nothing uses any more is proposed for retirement by `reef doctor` and removed only on the owner's approval (kept in `glossary-history.md`).

| Term | Definition | Avoid |
|---|---|---|
| Task | One vertical slice in `tasks/NNN-slug.md`: scope, acceptance criteria, blocked-by, log. | |
| Spec | The human's raw feature description, sharpened by grilling before task-splitting. | |
| Gate | A deterministic check (hook/CI) that cannot be argued with. | |
