# The docs for two hosts — README, site and Arabic manual

Written 2026-10-21, at the owner's request: "update the README and the English and Arabic site with instructions for
both Claude Code and OpenCode; make a plan for reorganizing the content." It follows the site's own rule from
`site-information-architecture.md`, **one home per fact**, and the port's phases in `portability-plan.md`.

## 1. The constraint that shapes everything

OpenCode support does not exist yet. Phase 0 (the probe) has not run and phase 2 (the adapter) is not built. So the
docs cannot carry OpenCode **instructions** today: an install line that does not work is worse than none. The plan
builds the slots now and fills them when each phase passes:

| When | What the docs say about OpenCode |
|---|---|
| Now, with phase 1 | One row: "OpenCode: planned", linking `docs/design/portability-plan.md` |
| Phase 2 adapter passes the probe | The install, the run command, the models map, and what is not available there |
| Phase 3 batch measured | Whether OpenCode matches Claude Code, with the numbers in `docs/perf/` |

## 2. What we have [V]

- **README and site share one order:** install, how it works, roles and tiers, before you run it, when it stops,
  settings, layout. The site is the README without the maintainers part.
- **The Arabic manual is a 10-chapter course** with its own order, glossary and troubleshooting; one self-contained
  file, no JavaScript.
- **Claude Code wording gathers in five places:** the install, graph mode as a background workflow, `/clear` and the
  context ceiling, the model cells (opus, sonnet, fable), and the README's plugin anatomy and honesty ledger. The
  concepts (queue, plan gate, tiers, roles, judges, records, layout, ADRs, journal) are already host-neutral.
- **Three tables are copied by hand into all three files:** the stops, the tiers, and the commands for each
  situation. Adding a host column to each would triple the drift.

## 3. The shape: one hosts table, a neutral body

1. **One new home: `## Hosts` in the README.** One table, a row per difference, a column per host: how you install,
   how you start a command, where each role's model is set, the night runner's command, the fresh-session step at the
   context ceiling, and what one host lacks (on OpenCode: graph mode, the Stop hook, the approval capture). Every
   other surface links to it or fetches it, never copies it.
2. **The site fetches it,** the way it already fetches the Settings table and the version (`site.js`,
   `loadReadmeTables`): a host switch on the install line and the situation chooser, filled from that table. With
   JavaScript off, or the fetch failing, the section shows Claude Code and links the README.
3. **The neutral body says the step, not the tool.** "Start a fresh session (`/clear` in Claude Code)" instead of
   "/clear"; "the graph runs as one background workflow where the host has one, task by task otherwise"; "the model
   from `roles.verifier`" instead of a model name in prose. The tier table keeps its model column, headed "default
   on Claude Code".
4. **The honesty ledger says, per row, which host enforces it.** A rule enforced by Claude Code's Stop hook is not
   enforced on OpenCode until the runner takes it over. A ledger that claims it everywhere would be the one dishonest
   page in the repo. One short column, "Hosts", filled `both` or `Claude Code`.
5. **The Arabic manual gets one new section in chapter 3, «اختيار المضيف»** (choosing the host): the install for
   each host in Arabic, and a link to the README's hosts table for the rest. Chapter 10's command list keeps its
   commands and adds one line on how each host starts them. Same RTL rules as today (`code` and `pre` left to right).

## 4. Couplings the change must keep [V]

- `site.js` parses the README's `## Settings` heading and table, and the version badge. Neither moves.
- `tests/test_contracts.py` parses the version badge, the honesty ledger's rows, and asserts the README's exact
  sentence `**macOS or Linux. On Windows, run Claude Code inside WSL2.**`. A new ledger column means editing that
  parser in the same PR; the WSL2 sentence stays as it is under the Claude Code row.

## 5. The steps

| Step | When | Files | Size |
|---|---|---|---|
| A. Neutral wording, the hosts table with Claude Code filled and OpenCode "planned", the ledger's Hosts column, the site fetch | Now, after this plan's go | README, `docs/index.html`, `site.js`, the Arabic manual, one contract test | About 300 words added, most of them the table |
| B. Fill OpenCode's column, the Arabic install section, the site switch's second tab | After phase 2 passes the probe | Same files | One table column, one Arabic section |
| C. The measured verdict and its numbers | After phase 3 | README status, `docs/perf/` | A few lines |

Docs words are not in the size budget (`prose_words` counts skills and agents only), but the owner's rule against
growth still applies: step A adds one table and removes the Claude tool names it replaces.

## 6. Not decided here

- Whether Codex gets a column. The portability plan defers Codex; the hosts table can take a third column later
  without another reorganization.
- The site's visual design for the host switch: it reuses the existing tab component, so no new component is
  planned.
