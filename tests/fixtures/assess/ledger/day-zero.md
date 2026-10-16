# Day zero — ledger

Each line is a command or a gate. Tick it when the gate is green, not when it feels done. `/reef-init` wrote this file and the ones it names; it never overwrites a file you edited (a differing rendering lands in `.reef/proposed/` with a diff). `/reef-assess` (2026-10-16) ticked what it could prove and wrote the harnessability score below; each tick names its proof.

- [ ] Reef installed: `/plugin install reef@mahmoudmoe`; review-toolkit agents present (`~/.claude/agents/plan-review.md`, `code-excellence.md`, `code-security.md`) — a stand-in runs only with an owner footnote. *Open: `ls ~/.claude/agents/` → no such directory in this sandbox; the plugin itself is present and `.reef/version` is 0.6.0.*
- [x] `make setup` (hooks) · `pip install -e .` · `pytest -q` green — `git config --get core.hooksPath` → `.githooks`; `src/ledger.egg-info/` present; `pytest -q` → exit 0, 28 passed.
- [ ] `.reef/config.json`: `gates.fast` under a minute, `gates.full` the whole suite, `gates.extra` the other checks (build, docs consistency, secret scan, migrations replay); `roles.*` as the owner routes them. *Open: `gates.fast` is `""` (falls back to `pytest -q`, 0.2 s, acceptable); `gates.extra` is `{}` — ruff check, ruff format and `mypy --strict` all pass or nearly pass today but none is a gate; `"structure"` joins `gates.extra` at recalibrate apply.*
- [x] `reef/constitution.md` read and cut to this project (8–15 articles, each with what it prevents) — `grep -c '^## Article'` → 9.
- [ ] `AGENTS.md`: commands and layout true; "Owner decision points" filled. *Open: the Conventions block claims ruff and mypy in CI, migrations and logging-over-print; none describes this tree (`reef/architecture/conventions.md`, "Lint and formatter").*
- [x] `reef/queue.md`: the first batch's planned rows written before any code; row 1 is the walking skeleton — `git log --oneline`: `96c57a0 plan(row 1)` precedes `cbdccd9 feat(import)`; row 1 closed in `reef/queue-archive.md`.
- [x] Every port, host and database parameterised; tests have a local database; `.env.example` holds the shape, `.env` is ignored — `LEDGER_DB`, `LEDGER_RULES` (`src/ledger/cli.py:20,51`); tests use `tmp_path` databases; `.gitignore:10-11`.
- [x] CI: `.github/workflows/ci.yml` on PRs into `main` only; `sh scripts/reef-ci-local.sh` green locally; Dependabot targets `develop` — `ci.yml:9-10`; `reef-ci-local.sh` → exit 0, 1 passed; `dependabot.yml:5,14`. *CI has never run: no remote (`git remote -v` → empty).*
- [ ] `tiers.light.allow` in `.reef/config.json` names the safe paths (nothing touching privacy, money, auth, tenancy, data). *Open: it names `docs/**` and `README.md`; no `docs/` directory exists. Score below is moderate, so the list is not emptied; it still needs real paths (`reef/**` prose? decide at the first light row).*
- [x] First row: `/reef-plan` → `/reef-plan-review` → `/reef-task` → `/reef-review` — tasks 101 and 102 merged, row 1 closed (`reef/journal.md`; `8207922`). Merged by hand: no forge, so no PR and no release CI.

## Harnessability — moderate (3/5)

Scored by `/reef-assess` on 2026-10-16 from `reef/architecture/conventions.md`. A dimension counts when the signal exists and would catch a sub-agent's mistake; `high` 5/5, `moderate` 3–4, `low` ≤ 2.

| Dimension | Score | Observed |
|---|---|---|
| Type safety | 1 | Every function in `src/` fully annotated; `mypy --strict src` → exit 0, 6 files. Not enforced by any gate. |
| Module boundaries | 1 | `src/ledger/` package, six modules, acyclic import graph with `cli` on top and `csvimport`/`rules` as leaves (`conventions.md`, `architecture.md` "Module graph"); `__init__` holds no logic. |
| Framework opinionation | 0 | Stdlib only: argparse, sqlite3, tomllib; `dependencies = []` (`pyproject.toml:10`). No framework dictates layout, errors or wiring, so nothing but review catches a structural deviation. |
| Test signal | 1 | `pytest -q` → 28 passed in 0.20 s; every acceptance criterion of tasks 101–102 has a named test; tests assert exit codes, exact stdout and database rows in-process. |
| Lint baseline | 0 | No ruff, mypy or formatter config; `ruff check` passes by default rules, `ruff format --check` → 5 of 9 files would change; no lint in hooks or CI. None configured and weak → 0. |

**Consequence:** moderate, so `tiers.light.allow` is left as is (a `low` score would empty it). The two zero dimensions are the cheapest harness gains: a `[tool.ruff]` block with the line length decided, `ruff check`/`ruff format --check`/`mypy --strict` as `gates.extra`, then `AGENTS.md` Conventions rewritten to match. That is an Article VIII admission (three conditions) and a row of its own; `.reef/config.json` is critical tier.

## Still open after assess (feeds the queue)
- `reef/architecture/workspace.dsl` missing: `python3 scripts/reef-c4.py --diff` → exit 1 "no committed model"; `gates.release.c4` cannot pass. `/reef-c4`.
- No threat model (`reef/architecture/threat-model.md`); required before any critical task touching auth, pii or money (`scripts/reef-plan-check.py:571-577`). `/reef-threat` after `/reef-c4`.
- The HTTP layer, Compose and VPS deploy of footnotes ¹ ² ⁵ have no queue row; Batch 1 is empty.
- Lint and type gates (above) and the `AGENTS.md` Conventions correction.
- `reef/glossary.md:6` "Task … `tasks/NNN-slug.md`" is stale; tasks live in `reef/features/<slug>/tasks/`.
- Release: `develop` → `main` PR, security pass, CI first run — all wait on a forge (`HANDOFF.md`).
