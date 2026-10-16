# Architecture — {{name}}

Written by `/reef-init`'s architecture grill from the owner's answers (verbatim below); regenerated model and
drift check by `scripts/reef-c4.py` (`reef/architecture/workspace.dsl`); decisions under `reef/architecture/adr/`.

## Intent
{{arch_intent}}

## The owner's answers
| Question | Answer |
|---|---|
| Host | {{arch_host}} |
| Shape | {{arch_shape}} |
| Scale (one year) | {{arch_scale}} |
| Data store | {{arch_store}} |
| Auth boundary | {{arch_auth}} |
| One-year non-goals | {{arch_non_goals}} |

## C4 level 1 — system context
```mermaid
{{arch_c4_l1}}
```

## C4 level 2 — containers
```mermaid
{{arch_c4_l2}}
```

## Walking skeleton (queue row 1)
One page end to end through every container above, built by the stack's own generator, deployed to {{arch_host}}, with the commit gate, the local gate and CI green. Everything after it is a vertical slice through this skeleton.
