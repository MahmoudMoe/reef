# Session handoff — Reef 0.6.0 shipped (2026-10-16)

Read this and `docs/perf/report-0.6-2026-10-16.md`; nothing else is needed to resume.

## Where things stand
- Branch `claude/new-session-4u0edl`, head `d4e08c8`, pushed; 8 commits on top of `main`'s `5f39db7` (one per phase 0–6 + Finishing). No PR opened (none requested).
- `sh tests/run.sh` green: 300 Python + 70 hooks + 17 ci-local = 387.
- Version 0.6.0 everywhere (`plugin.json`, `marketplace.json`, README badge, `test_one_version_everywhere`).
- Working tree clean after this file.

## What is NOT done / decisions the owner still owes
1. **Merge or review the branch.** Phases are commits, not per-phase PRs (session was bound to one branch).
2. **Size ceiling (decision 10):** ≈3,850 net new script lines vs 3,200. Cut candidates, each one file: `scripts/reef-repo` (≈125), Mermaid export in `reef-c4.py` (≈35), `--diff` in `reef-c4.py` (≈45), stack opinions in `reef-init.py` (≈20), `cmd_apply` in `reef-recalibrate` (≈140). All cuts together still leave ≈3,480. Owner decides: cut, or reset the budget.
3. **5.7 per-row growth** unmeasured (no project row ran). Command: `python3 scripts/reef-cost.py <transcript> --repo .`; target < 60k/row; then set `caps.context_warn` / `caps.context_tokens`.
4. **`tiers.light.roles.author`** left unset (opus). Needs an author eval before sonnet.
5. **Hunter false-FAIL 0.33 → 0.67** after 4.4 (one PASS entry, out-of-scope `#` shlex hole). Recorded; scope discipline is 0.7 row 2.
6. AskUserQuestion fixture is schema-derived, not live-captured (headless excludes the tool).

## Open 0.7 rows
See `docs/perf/report-0.6-2026-10-16.md` §"Open rows for 0.7" (7 rows).

## How to re-verify quickly
```
sh tests/run.sh                                  # ~2 min, must print ALL REEF TESTS PASSED
python3 scripts/reef-guard-profile.py --runs 30 --check hooks/hooks.json
python3 scripts/reef-eval run verifier --k 3 --out .reef/eval-after   # live, ~$5, never in CI
```

## Gotchas learned this session
- `pytest` is not installed; use `python3 -m unittest tests.test_x -q`.
- `claude -p` inherits `CLAUDE_CODE_SESSION_ID`; `reef-eval` clears it.
- Guard patches: anchor on exact text; two patches aborted on stale anchors and had to be re-applied.
- `git add -A -- <moved paths>` fails after renames; use `git add -A`.
- Layout is sticky via `paths.queue` prefix; a second `reef-init` must not flip 0.6 → 0.5.
- Test count: quote what `tests/run.sh` runs (300), not `grep -c "def test_"` (304; 4 are helpers/skips).

This file can be deleted once the branch is merged.
