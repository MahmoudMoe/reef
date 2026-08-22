---
name: reef-init
description: Bootstrap Reef in a project — detect the stack, write .reef/config.json, scaffold tasks/ and docs/adr/, install the deterministic commit gates. Run once per repo, or when the user says "/reef-init".
---

# Reef Init

Bootstrap the current repo for Reef. Refuse to overwrite existing files — report and skip instead.

1. Verify this is a git repo (`git rev-parse`); if not, ask before `git init`.
2. Detect the stack (uv/pyproject, package.json, Cargo.toml, go.mod, Makefile) and write `.reef/config.json` from `${CLAUDE_PLUGIN_ROOT}/templates/config.json`, filling `gates.test` (and `gates.lint` if obvious). If no test command can be detected, leave it "" — the gate FAILS LOUDLY until the human sets it; never write a no-op gate.
3. Scaffold: `tasks/`, `tasks/done/`, `docs/adr/`, `docs/glossary.md` (3 process rows: Task/Spec/Gate), `docs/runlog.md` (header only).
4. Install gates: copy `${CLAUDE_PLUGIN_ROOT}/templates/pre-commit` to `.githooks/pre-commit`, duplicate as `pre-merge-commit` and `pre-push`, `chmod +x`, then `git config core.hooksPath .githooks` AND write a `Makefile` target `setup:` doing the same — hooksPath is local git config and does not survive a clone; `make setup` is documented step 0.
5. Copy `${CLAUDE_PLUGIN_ROOT}/scripts/reef-gate.sh`, `reef-attempt` and `reef-plan-check.py` into `scripts/`, chmod +x.
6. Offer (AskUserQuestion): add a minimal CI workflow running the test gate? CI is the only gate that survives cloning and `--no-verify`.
7. Print what was created, skipped, and the one manual step remaining (if any).
