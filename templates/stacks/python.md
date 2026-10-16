# Python — stack opinions (read by reef-init, never copied)
- Layout: `src/<package>/` or a flat package, `tests/` mirroring the package; `__init__.py` holds exports, never logic.
- Environment: `uv` when `uv.lock` exists (`uv sync`, `uv run`), else `pip install -e .`; one lockfile; never `pip install` into the system interpreter.
- Tests: pytest, `test_<thing>` names that read as the rule they prove; a fixture per external system; `pytest -q` is the full gate.
- Types: type hints on every public function; `mypy --strict` or `pyright` in CI; `# type: ignore` carries a reason.
- Lint and format: `ruff check` + `ruff format`; CI fails on either; no `noqa` without a code and a reason.
- Config: `pyproject.toml` is the one home (tool sections, dependencies); no `setup.py` next to it.
- Errors: raise specific exceptions; never a bare `except:`; logging through `logging`, never `print`, in product code.
- Data: migrations with the ORM's tool (Alembic, Django) beside the model change; a schema change without its migration is not complete.
- Entry points: `[project.scripts]` or a `__main__.py`; no top-level side effects on import.
