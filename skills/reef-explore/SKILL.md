---
name: reef-explore
description: Read a large tree by fanning out read-only Explore agents on N questions in ONE message and merging their answers into one report where every claim is labelled Observed (with the file:line or command that proves it) or Inferred. Use for day zero, for /reef-assess, or when the user says "/reef-explore".
argument-hint: <question | question; question; …>
---

# Reef Explore — many read-only eyes, one report

**Input:** N questions (`$ARGUMENTS`, `;`-separated; empty → ask for them and stop). **Output:** one report, nothing written to the repository.

1. Resolve the model: the dispatching tier's `mechanic` role (`tiers.<tier>.roles.mechanic`, then `roles.mechanic`, default sonnet). Every question gets its own `Explore` agent (`subagent_type: Explore`, that model), **all dispatched in one message**, each with a per-agent budget in the prompt: at most `context.explore_files` files read (default 40), cheapest sources first — configs, CI, lockfiles, `git log --stat` — code samples per directory second, never a whole tree.
2. The agents are READ-ONLY by mechanism: the guard denies them every mutating git command, every Bash write and every CI wait (1.3, `agent_type: Explore`); the snapshot hash is the backstop.
3. Each agent answers in one shape: `OBSERVED: <claim> — <file:line | command and its output>` or `INFERRED: <claim> — <why>`; nothing else. A claim without a proving path is Inferred by definition.
4. Merge: one report, questions in order, duplicates collapsed, every Observed line keeping its proving path, Inferred lines grouped under `## Inferred (check before relying on it)`. Under 400 lines; longer → the questions were too broad, split them.
5. The report is handed to the caller (`/reef-assess`, the owner); nothing is written unless the caller says where.
