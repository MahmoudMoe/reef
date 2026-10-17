---
name: reef-threat
description: Derive the threat model from the architecture — trust boundaries as a Mermaid data-flow diagram and a STRIDE table where every row names its mitigation and its proving test or an explicit acceptance; unmitigated rows become found queue rows. Use after /reef-c4, before a critical task that touches auth, pii or money, or when the user says "/reef-threat".
argument-hint: <empty | crossing to focus on>
---

# Reef Threat — security is a boundary artifact

Runs on the `critical` tier table. **Input:** `reef/architecture/architecture.md` and `reef/architecture/workspace.dsl` (regenerate with `/reef-c4` first if stale). **Output:** `reef/architecture/threat-model.md`, nothing else written.

1. Boundaries: every relationship in the DSL that crosses a trust boundary — a person to a container, a container to an external system, a container to a store — is a crossing `a -> b` (`scripts/reef-threat.py lint` lists the uncovered ones). Draw them as ONE Mermaid data-flow diagram with the boundaries as subgraphs.
2. The STRIDE table, one row per crossing and class that applies: `| crossing | STRIDE | threat | mitigation | proof |`. `mitigation` names the control in the code (file, middleware, policy); `proof` names the test or command that proves it (`test_x`, `it('…')`, a backticked command). A risk the owner carries reads `accepted: <reason>` in the mitigation cell — an acceptance is a decision, so it is also an owner footnote in the queue.
3. `python3 scripts/reef-threat.py lint` must pass: a crossing without a row, a row without a mitigation and a proof, an acceptance without a reason — each fails. Never pad a row to pass: a mitigation that does not exist yet is an UNMITIGATED row.
4. Unmitigated rows → `python3 scripts/reef-threat.py rows` prints them as `found` queue rows with `touches:` set (`auth` for S/E, `pii` for I); append them to the queue's next batch. Each becomes a `critical` task through the normal loop.
5. Freshness: `scripts/reef-plan-check.py` demands a re-run when a `critical` task carries `touches: auth|pii|money` and the threat model is older than the architecture document (`scripts/reef-threat.py fresh`). The loophole-hunter's `pass=system` (4.4) takes this file as its input and maps its findings to these rows.

End with the lint's last line and the count of unmitigated rows; `in flight: … / waiting on: … / next: <command>`.
