---
id: NNNnn
feature: <feature-slug>
status: pending
complexity: mech|design
effort: low|medium|high
blocked-by: []
resources: []
tier: light|full|design|critical
touches: []
verify: judge|gate-only
attempts: 0
dispatches: 0
last_failure_sig: ""
---
# NNNnn — <title>

## Scope
<one paragraph: what changes, through every layer it needs. Sentences under 25 words.>

## Decision
<!-- design/critical tasks: the HUMAN writes this in their own words before implementation. A migration task adds a `Rollback: <how>` line. The implementer refuses a design task with an empty Decision. -->

## Acceptance Criteria
- AC-1 (FR-1): <one declarative sentence, under 50 words, no test name, no command — the proof is in the table below>
- AC-2 (FR-2, SC-1): <…>

## Proof
| AC | Proof |
|---|---|
| AC-1 | `test_<name>` |
| AC-2 | `<command that exits 0 iff the criterion holds>` |

## Out of scope

## Log
