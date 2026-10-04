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
- Defaults: `graph.parallel` 10, `resources.heavy.slots` 2, `worktree.setup` per project.
- Version 0.5.0 (0.4.0 was `parallel-loop-compat`: merge setting, one cap per item, draft ADRs,
  per-feature stamp, fast/full gates, model per role, rule-first verifier).
