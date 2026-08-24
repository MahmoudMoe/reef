---
name: reef-init
description: Bootstrap Reef in a project — detect the stack, write .reef/config.json, scaffold tasks/ and docs/adr/, install the deterministic commit gates. Run once per repo, or when the user says "/reef-init".
---

# Reef Init

Bootstrap the current repo for Reef. Refuse to overwrite existing files — report and skip instead.

0. Prerequisite: `command -v python3` — the gates and scripts need it. Missing → STOP and say so.
1. Verify this is a git repo (`git rev-parse`); if not, ask before `git init`.
2. PREFLIGHT the hook surface — never clobber someone else's hooks:
   `git config --get core.hooksPath` non-empty (and not `.githooks`), or `.git/hooks/` contains
   non-`.sample` hooks (husky, lfs, pre-commit.com)? → STOP, show what exists, and ask the human
   whether to chain (call the existing hook from `.githooks/pre-commit`) or abort.
3. Detect the stack (uv/pyproject, package.json, Cargo.toml, go.mod, Makefile) and write `.reef/config.json` from `${CLAUDE_PLUGIN_ROOT}/templates/config.json`, filling `gates.test`. If no test command can be detected, leave it "" — the gate FAILS LOUDLY until the human sets it; never write a no-op gate. (`plan.test_re` empty = the built-in multi-stack default; set it only for a convention the default misses.)
4. Scaffold: `tasks/`, `tasks/done/`, `docs/adr/`, `docs/glossary.md` (3 process rows: Task/Spec/Gate), `docs/runlog.md` (header only). No `CLAUDE.md`/`AGENTS.md` at root → write a minimal brief (project name, one-line purpose, stack, test command) — reef-plan-check requires one.
5. Install gates: copy `${CLAUDE_PLUGIN_ROOT}/templates/pre-commit` to `.githooks/pre-commit`, duplicate it as `pre-merge-commit` (same index semantics), `chmod +x` both, then `git config core.hooksPath .githooks` (the guard hook allow-lists exactly this value). NO pre-push hook by design: at push time the worktree has no relationship to the refs being pushed, so a worktree gate there only false-rejects; CI is the push wall. Makefile handling: exists → APPEND a `setup:` target if absent (never rewrite the file; verify with `make -n setup`); missing → create one. hooksPath is local config and does not survive a clone; `make setup` is documented step 0.
6. Copy `${CLAUDE_PLUGIN_ROOT}/scripts/reef-gate.sh`, `reef-attempt`, `reef-snapshot.sh` and `reef-plan-check.py` into `scripts/`, chmod +x.
7. Stage and commit everything this init created (one commit, `chore: reef init`) — the pre-commit gate must never trip over its own untracked config on the first real commit.
8. Offer (AskUserQuestion): add a minimal CI workflow running the test gate? CI is the only gate that survives cloning and `--no-verify` — the hooks are tripwires, CI is the wall.
9. Print what was created, skipped, and the one manual step remaining (if any).
