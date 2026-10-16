---
name: reef-c4
description: The project's one architecture model (Structurizr DSL) generated from code with a proving path per element, its Mermaid views, and the element-level drift check that runs once per release. Use at day zero, after a change to containers or external systems, or when the user says "/reef-c4".
argument-hint: <generate | diff>
---

# Reef C4 — architecture diagrams are evidence

The model is **generated**, never drawn from memory: `scripts/reef-c4.py` reads manifests, infrastructure files, dependencies and routes into persons, containers, stores and external systems (cap 9 — the most similar pair is collapsed and reported), each with `# proof: <file>`; what the code cannot prove is tagged `Inferred`.

1. `python3 scripts/reef-c4.py generate --write` → `reef/architecture/workspace.dsl` (one model, L1 and L2 views) and the exported `reef/architecture/context.md` / `container.md` (marked generated). `python3 scripts/reef-c4.py lint` checks the DSL's structure without any dependency.
2. Read the result against `reef/architecture/architecture.md` (the grill's intent): an element the code shows and the intent does not name is a finding for the owner, never a silent edit of the model. Fix the CODE or the intent, then regenerate; never hand-edit an element.
3. Drift: `python3 scripts/reef-c4.py --diff` — `missing` (in the code, not in the model), `contradicts` (in the model, no longer in the code; a hand-edited Mermaid export too), `inferred` (no proving path). It is a release gate: `gates.release.c4` = `python3 scripts/reef-c4.py --diff`, run by `scripts/reef-ci-local.sh --release` on PRs into the release branch only (4.2); a feature PR never pays for it.
4. The threat model (`/reef-threat`) is derived from this model; a change here makes it stale (`scripts/reef-threat.py fresh`).

Output: the elements written or the drift lines; nothing else. Hand the `missing`/`contradicts` lines to the owner as queue rows when they are not this feature's.
