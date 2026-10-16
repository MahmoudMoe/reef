# Recalibration — 2026-10-16

The full plan of what `scripts/reef-recalibrate --apply` will create, convert, move and keep — one line each, with its reason. Nothing moves before the owner approves this list (edit a line's action to change it; `keep` lines move only when you change them). Undo is `git revert` of the apply commit.

## Create

- create `reef/constitution.md`
- create `reef/queue.md`
- create `reef/journal.md`
- create `reef/glossary.md`
- create `reef/architecture/`
- create `reef/features/README.md`
- create `reef/archive/2026-10-16/`
- create `reef/archive/README.md`

## Documents

| action | path | → | reason |
|---|---|---|---|
| keep | `AGENTS.md` | — | project file (README, LICENSE, CONTRIBUTING, SECURITY, CHANGELOG, CODEOWNERS) |
| keep | `CLAUDE.md` | — | project file (README, LICENSE, CONTRIBUTING, SECURITY, CHANGELOG, CODEOWNERS) |
| keep | `HANDOFF.md` | — | project file (README, LICENSE, CONTRIBUTING, SECURITY, CHANGELOG, CODEOWNERS) |
| keep | `README.md` | — | project file (README, LICENSE, CONTRIBUTING, SECURITY, CHANGELOG, CODEOWNERS) |
| keep | `reef/architecture/adr/0001-auth-boundary.md` | — | already in the layout |
| keep | `reef/architecture/adr/0002-data-store.md` | — | already in the layout |
| keep | `reef/architecture/adr/0003-hosting.md` | — | already in the layout |
| keep | `reef/architecture/adr/README.md` | — | project file (README, LICENSE, CONTRIBUTING, SECURITY, CHANGELOG, CODEOWNERS) |
| keep | `reef/architecture/architecture.md` | — | already in the layout |
| keep | `reef/constitution.md` | — | already in the layout |
| keep | `reef/day-zero.md` | — | already in the layout |
| keep | `reef/features/csv-import-monthly-report/SPEC.md` | — | already in the layout |
| keep | `reef/features/csv-import-monthly-report/adr/0004-categorise-at-report-time.md` | — | already in the layout |
| keep | `reef/features/csv-import-monthly-report/tasks/done/101-import-csv-into-sqlite.md` | — | already in the layout |
| keep | `reef/features/csv-import-monthly-report/tasks/done/102-monthly-report-by-category.md` | — | already in the layout |
| keep | `reef/glossary.md` | — | already in the layout |
| keep | `reef/journal.md` | — | already in the layout |
| keep | `reef/queue-archive.md` | — | already in the layout |
| keep | `reef/queue.md` | — | already in the layout |

## How it was pushed (derived)

- branches: develop, main → `branches.base` develop, `branches.release` main, `merge.by` loop
- commits sampled 11, conventional-commits share 0.38, merge style merge (3 merge commits)
- tags: none (semver: None)
- CI: ci.yml on pull_request: branches: [main]
