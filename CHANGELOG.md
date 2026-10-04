# Changelog

## 0.5.0 — the graph executor and the full project setup

- **Task graph executed, not just declared.** `scripts/reef-graph.py` computes the ready set from
  `blocked-by`, `resources:` and `graph.parallel`; `/reef-task` dispatches every ready task in
  parallel, each in its own worktree (`reef-graph worktree`); the guard refuses any implementer
  dispatch outside the ready set and marks the task `in-progress` on allow, under one graph-wide
  lock. `reef-graph lock <resource> -- cmd` serialises heavy commands (2 slots by default).
- **Guard rules from a measured merge wave:** `git stash` denied (one stack serves every worktree);
  a gate piped into another command without `pipefail` denied (the pipe hides the exit code).
- **`tier:`** (light / full / design) on tasks; plan-check refuses a tier that does not match the
  complexity (mech ⇔ light). `resources:` is plan content; `worktree:` and `in-progress` are
  execution state the stamp ignores.
- **The adversarial stage.** `agents/loophole-hunter.md` ("how can this be green while the defect happens?"),
  mandatory twice on `tier: design` — on the plan before code (the guard refuses the first dispatch
  without `adversarial-plan:` bound to the plan's content) and on the finished guard before close (the
  pre-commit refuses a design-tier task entering `done/` without `adversarial-guard:`); never on mech.
  `scripts/reef-adversarial` records only a PASS without BLOCKER lines.
- **Claims bound to the round.** `scripts/reef-claims.py check` rejects a claim at a line the round did
  not add; `claims-only` is the one commit allowed after GREEN. Verifier and hunter attack the last
  round's fix first; "cannot verify here" needs the probe pasted.
- **`/reef-init` is the full project setup.** `scripts/reef-init.py` renders `templates/project/`
  (AGENTS.md, constitution, queue, ADR convention, journal, handoff, day-zero checklist, release-only
  CI, Dependabot on the integration branch, the hooks and every Reef script) adapted to the detected
  stack — idempotent: absent → written, identical → skipped, different → never overwritten (the
  rendering lands in `.reef/proposed/` with a diff; `--accept` applies it). Config keys are merged,
  never changed. `scripts/reef-ci-local.sh` (every gate, every exit code, 2 = skipped ≠ success; CI
  runs the same script), `scripts/reef-tier.py` (a tier only gets heavier), `scripts/reef-queue.py`
  (status derived from task files, ready rows, consistency, ADR numbering at merge). plan-check reads
  AGENTS.md as the brief when CLAUDE.md is a pointer. `/reef-loop` drives the outer graph.
- Arabic user manual: `docs/manual/ar/index.html`.
- Model per role read at dispatch (`roles.*`, the guard refuses another model); `agents/mechanic.md`.
- Defaults: `graph.parallel` 10, `resources.heavy.slots` 2, `worktree.setup` per project.
- Version 0.5.0 (0.4.0 was `parallel-loop-compat`: merge setting, one cap per item, draft ADRs,
  per-feature stamp, fast/full gates, model per role, rule-first verifier).
