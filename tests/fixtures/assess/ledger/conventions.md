# Conventions — ledger (as written, not as declared)

Written by `/reef-assess` on 2026-10-16 from the code and the tree, not from a template. Every line is **Observed** with its proving path or command, or **Inferred**. This is the input to the constitution and the glossary; where `AGENTS.md` "Conventions" says something the code does not do, this file says so and `AGENTS.md` is the one to fix.

## Lint and formatter
- Observed — **no lint or formatter configuration exists**: `pyproject.toml` has only `[tool.pytest.ini_options]` and `[tool.setuptools.packages.find]`; none of `setup.cfg`, `.flake8`, `ruff.toml`, `mypy.ini`, `.pre-commit-config.yaml` exists (`ls`); ruff and mypy are not declared as dev dependencies (`pyproject.toml:15-16`).
- Observed — `ruff check src tests` (ruff 0.16.8, default rules) → exit 0, "All checks passed!".
- Observed — `ruff format --check src tests` → exit 1, "5 files would be reformatted, 4 files already formatted" (`src/ledger/__init__.py`, `cli.py`, `report.py`, `tests/test_import.py`, `tests/test_report.py`). The diff is line-length wrapping only: the code uses lines up to 112 characters (24 lines over 88, 8 over 100; `awk` over `src tests`), ruff's default is 88.
- Observed — `.ruff_cache/` and `.mypy_cache/` exist untracked (`git ls-files | grep -c cache` → 0). A cache proves a tool was run once, not that it is configured or enforced.
- Observed — no lint step in CI or in the hooks: `.github/workflows/ci.yml:40` runs only `sh scripts/reef-ci-local.sh --ci --release`; `gates.fast` is `""`, `gates.full` is `pytest -q`, `gates.extra` is `{}` (`.reef/config.json`).
- Inferred — the style is black/ruff-format shaped with a longer line (about 110): double quotes, trailing commas in multi-line calls, imports grouped stdlib then first-party (`cli.py:3-12`, `store.py:30-33`). Adopting ruff format needs `line-length = 110` or a one-time reformat of 5 files.
- Observed — `AGENTS.md` Conventions claims "`ruff check` + `ruff format`; CI fails on either" and "`mypy --strict` or `pyright` in CI". Neither is true of this tree (above). The template's opinion, not the repository's.

## Type strictness
- Observed — every function in `src/` is fully annotated, parameters and return: 14 public names (`main`, `read_transactions`, `monthly_totals`, `format_table`, `load_rules`, `categorise`, `connect`, `insert_transactions`, classes `Transaction`, `BadRow`, `BadRules`) and every private helper (`cli.py:19-80`, `csvimport.py:28,38,51`, `report.py:9,19,25`, `rules.py:13,32`, `store.py:19,26`).
- Observed — `mypy --strict src` (mypy from `/root/.local/bin`, default config) → exit 0, "Success: no issues found in 6 source files".
- Observed — no `# type: ignore`, no `Any` (`grep -rn "type: ignore\|Any" src` → none); no `from __future__ import annotations` (modern `X | None`, `list[str]` syntax, 3.11+: `csvimport.py:51`, `cli.py:83`, `store.py:4`).
- Observed — tests are annotated too (`-> None`, `pytest.CaptureFixture[str]`, `pytest.MonkeyPatch`: `tests/test_import.py:25`), except `tests/test_smoke.py:4` `def test_version():`.
- Inferred — the code was written to pass a strict checker; nothing in the repository makes that a gate.

## Test framework and style
- Observed — pytest, `testpaths = ["tests"]`, `pythonpath = ["src"]` (`pyproject.toml:18-20`). `pytest -q` → exit 0, **28 passed in 0.20s** (14 functions, 2 parametrised; `grep -c "^def test_"`: test_import 6, test_report 7, test_smoke 1).
- Observed — names read as the rule they prove: `test_import_bad_row_stops_with_row_number` (`tests/test_import.py:54`), `test_report_rejects_bad_month` (`tests/test_report.py:82`); files are `test_<area>.py`.
- Observed — tests call `main([...])` in-process, never a subprocess or CliRunner (`tests/test_import.py:35`, `tests/test_report.py:71`); they assert the integer return code, exact stdout, stderr via `startswith`, and rows read back from SQLite (`test_import.py:35-41,68-71`; `test_report.py:73-78,117-121`). `SystemExit` is expected only for argparse's own rejection, code 2 (`test_report.py:86-90`).
- Observed — fixtures: `tmp_path`, `monkeypatch.setenv` for `LEDGER_DB` / `LEDGER_RULES`, `capsys`, `@pytest.mark.parametrize` (`test_import.py:19,25,44`; `test_report.py:81,94`). No `conftest.py`; the `db` fixture is duplicated in `test_import.py:18-22` and `test_report.py:13-17`.
- Observed — two tests pin repository files as fixtures: `.env.example`, `examples/transactions.csv`, `examples/rules.toml` through a `ROOT` path (`test_import.py:102-109`, `test_report.py:135-150`).
- Observed — every acceptance criterion of tasks 101 and 102 names its proving test (`reef/journal.md` rows 101 and 102; `reef/features/csv-import-monthly-report/tasks/done/*.md` AC tables).
- Observed — no test module has a docstring (`tests/*.py:1`).

## Error handling
- Observed — two domain exceptions, both `ValueError` subclasses: `BadRow(row_number, reason)` (`src/ledger/csvimport.py:21-25`) and `BadRules` (`src/ledger/rules.py:9-10`). Low-level errors are chained with `raise … from exc` (`csvimport.py:34,42`; `rules.py:18,20`).
- Observed — the CLI catches them at the boundary, prints `<cmd>: <msg>` to stderr and returns exit 1 (`cli.py:26-32,58-60`); `main` returns an int and never calls `sys.exit` (`cli.py:83-89`; `grep -rn "sys.exit\|except:" src` → none). Exit 2 is argparse's. Bad month → `argparse.ArgumentTypeError` (`cli.py:44-47`).
- Observed — `sqlite3` errors are not caught: a missing `LEDGER_DB` directory or a corrupt file tracebacks (`cli.py:34-38,61-65`; journal nit on task 101).
- Observed — no bare `except`, every handler names its types (`grep` above).

## Logging
- Observed — `logging` imported, `log = logging.getLogger(__name__)` (`cli.py:4,14`), one `log.debug` (`cli.py:39`), no handler configured anywhere in `src/`. Product output is `print` to stdout (`cli.py:40,67,69`) and stderr (`cli.py:27,31,59`); `report.py` builds strings and does not print.
- Inferred — logging is effectively unused; the `AGENTS.md` line "logging through `logging`, never `print`" does not describe a CLI whose product output is stdout.

## Naming
- Observed — modules are short lowercase nouns: `cli`, `csvimport`, `report`, `rules`, `store`. Functions and variables snake_case; private helpers `_import`, `_money`, `_parse_date`; constants UPPER_CASE `HEADER`, `UNCATEGORISED`, `SCHEMA`; private regexes `_MONTH`, `_ISO_DATE` (`cli.py:16`, `csvimport.py:10-11`, `rules.py:6`, `store.py:9`).
- Observed — one `@dataclass(frozen=True)`, `Transaction` (`csvimport.py:14-18`); no TypedDict or NamedTuple; rules are `list[tuple[str, str]]`, totals `list[tuple[str, int]]` (`rules.py:13`, `report.py:9`).
- Observed — money is integer cents end to end, `Decimal` only to parse (`csvimport.py:40-48`; ADR 0004; glossary "Transaction").
- Observed — glossary nouns match code identifiers: `transactions` table, `amount_cents`, `uncategorised`, `LEDGER_DB`, `LEDGER_RULES` (`reef/glossary.md:9-13` vs `store.py:11-14`, `rules.py:6`, `cli.py:20,51`). One glossary line is stale: "Task … in `tasks/NNN-slug.md`" (`glossary.md:6`) while tasks live in `reef/features/<slug>/tasks/`.

## Module layout
- Observed — `src/ledger/` package, `tests/` beside it, no mirror per module (3 test files for 5 modules); `__init__.py` is a docstring and `__version__` only, no exports and no logic (`src/ledger/__init__.py:1-2`).
- Observed — sizes: `__init__` 2, `cli` 89, `csvimport` 71, `report` 31, `rules` 37, `store` 34; tests 109 + 150 + 5; total 528 lines (`wc -l`).
- Observed — every `src` module has a one-line module docstring (line 1 of each); function docstrings on `read_transactions`, `monthly_totals`, `insert_transactions` only (`csvimport.py:52`, `report.py:10`, `store.py:27`). Inline comments mark non-obvious facts (`cli.py:89` "unreachable: argparse rejects unknown subcommands").
- Observed — `pyproject.toml` is the one config home; no `setup.py`, no `requirements.txt`, no lockfile (`git ls-files`).

## Hooks and gates (the mechanisms that enforce any of this)
- Observed — `.githooks/pre-commit` and `pre-merge-commit` are byte-identical (`diff` → same); each backs up the index, runs `sh scripts/reef-gate.sh fast` against the staged index and restores (`.githooks/pre-commit:2-6,44,89`); before the gate it rejects a staged `done/*.md` with `tier: design|critical` and no `adversarial-guard:` line (`pre-commit:26-35`).
- Observed — `reef-gate.sh fast` resolves `gates.fast > gates.test > gates.full` (`scripts/reef-gate.sh:7`); with `gates.fast` empty the commit gate is `pytest -q` (0.2 s).
- Observed — `sh scripts/reef-ci-local.sh` → exit 0, "1 passed, 0 failed, 0 skipped" (only `full`; `gates.extra` is empty).
- Observed — `python3 scripts/reef-structure --check` → exit 0, "ok: every process document lives in the layout".

## What the constitution and glossary should take from this
- The real baseline is: full type hints that pass `mypy --strict`, pytest with in-process CLI calls and exact-output assertions, integer cents, domain `ValueError` subclasses caught once at the CLI boundary, stdlib only.
- Not yet a gate, so not yet a rule: ruff check, ruff format (needs a line-length decision: 88 and reformat 5 files, or 110), mypy --strict in `gates.extra`. Admitting any of them is an Article VIII decision (`reef/constitution.md:30`).
- Fix `AGENTS.md` Conventions to match: no ORM, no migrations, no logging-over-print rule for a CLI, no "CI fails on ruff/mypy" until it does.

## How it was pushed
Mechanical read: `python3 scripts/reef-recalibrate history` (2026-10-16), cross-checked by an Explore agent over `git log`, `git reflog`, `git shortlog`.
- Observed — branches `develop` (HEAD) and `main`; no remote, no tags (`git remote -v` → empty; `git tag` → empty). `develop` is 9 commits ahead of `main` (`git log main..develop --oneline`); `main` has nothing `develop` lacks.
- Observed — 11 commits, all on 2026-10-16, one email under two author names (`git shortlog -sne --all`: 9 "Mahmoud Moawed", 2 "reef" for the close and handoff commits). Unsigned (`%G?` → N for all).
- Observed — commit subjects: 10 of 11 are `type(scope): subject` shaped; the `history` command counts only standard conventional types (`feat`, `chore`) and reports share **0.38** (3 of 8 authored); the other prefixes are Reef loop stages: `plan`, `plan-review`, `merge`, `close`, `handoff`. Inferred — the expectation to record is "`type(scope): subject`, Reef stage names allowed", not strict Conventional Commits.
- Observed — merge style **merge**, 3 true two-parent merges (`7a3495f`, `c6cafed` task merges; `8207922` feature → develop, "Merge made by the 'ort' strategy"); no squash, rebase or amend in the reflog; the feature → develop merge is non-fast-forward although it could have fast-forwarded (Inferred: `--no-ff` or equivalent).
- Observed — one rename commit (`5dbcd57`: four `draft-1-*.md` ADRs → `0001`–`0004`), no deletions (`git log --all --diff-filter=DR --name-status`).
- Observed — CI: `ci.yml` on `pull_request: branches: [main]` only; Dependabot pip + github-actions weekly, `target-branch: develop`. CI has never run (no remote, no PR).
- Observed — derived `branches.base` develop, `branches.release` main, `merge.by` loop, `ci.feature_gate` local **equal the values already in `.reef/config.json`**; nothing to change there.
