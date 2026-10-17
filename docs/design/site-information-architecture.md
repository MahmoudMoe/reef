# The Reef page: what is shown, where, and why

This document is the plan behind the project's public face: the GitHub repository page (the README), the
GitHub Pages site (`docs/index.html`, served at `https://mahmoudmoe.github.io/reef/`), and the documents both of
them point to. It follows Reef's own rule, **one home per fact**: every surface either owns a fact or links to the
surface that owns it. A fact that is copied is a fact that drifts.

## 1. Who reads, in what order, asking what

Readers arrive in a predictable order and each one is in a hurry for a different reason. The site is built in
that order, top to bottom, so every reader stops at the first section that answers them.

| Reader | Time | The one question | Answered by |
|---|---|---|---|
| **Evaluator** (saw the repo in a list, a feed, a link) | 90 seconds | What is this, and is it real? | The hero: one sentence, the install command, three proofs (selftests, the dogfood run, the honesty ledger) |
| **Adopter** (has a project and wants to try it) | 10 minutes | Where do I start for *my* situation? | The situation chooser: five situations, one command each, what happens next |
| **Operator** (runs it daily, needs to understand a stop or a denial) | as needed | Why did Reef refuse that, and who decides? | The pipeline explorer, the roles, the enforcement ledger with search |
| **Owner** (tunes the numbers, sets the models) | as needed | Which key, what default, what effect? | The tiers table and the searchable settings reference |
| **Skeptic / contributor** | 30 minutes | Where are the numbers, and where is the code? | The measured section with a source link per number; the layout tree; the docs index |

The first two readers get everything above the fold or one scroll below it. The last three get sections that are
**interactive on purpose**: a 42-row ledger is read by filtering it, not by scrolling it.

## 2. The surface map: who owns what

| Surface | Owns | Links to (never copies) |
|---|---|---|
| `README.md` (the GitHub page) | The claim, the quick start, the **honesty ledger**, the tiers, the settings table, the measured summary, the layout, the status, the acknowledgments | the site, the manual, `docs/perf`, `docs/design` |
| `docs/index.html` (the site) | The *presentation*: the situation chooser, the pipeline explorer, the roles, the growth chart, the expandable layout tree | **the ledger and the settings table are fetched from the README at page load and parsed**; every number links to its `docs/perf` report |
| `docs/manual/ar/index.html` | The Arabic user manual (learning path, daily use, troubleshooting) | the README for reference facts |
| `docs/design/*.md` | Design decisions and their reasoning (the graph executor, the planning cost cut, this document) | — |
| `docs/perf/*.md` | Every measured number: the dogfood run, the baseline, the eval, the payloads, the guard profile | — |
| `CHANGELOG.md` | What changed in each version, with the first contact that caused it | — |
| `skills/`, `agents/`, `commands/` | The behaviour itself | — |

Two consequences:

- **The ledger has one home.** The site parses the README's "What is enforced, and how" table and the "Settings"
  table at runtime (`docs/assets/site.js`, `loadReadmeTables`). It tries the README served beside the site first,
  then the raw file on GitHub. If both fail or the heading moves, the section degrades to a link to the README
  section. Nothing in the site's HTML restates a ledger row.
- **The site's own numbers are few and sourced.** The stat tiles and the growth chart carry about a dozen numbers,
  each hand-copied from `docs/perf/dogfood-2026-10-16.md` or the eval report, and each tile links to its source
  line. They change only at a release, together with the version string, and the maintenance list below names them.

## 3. The site, section by section

Reading order is the reader order of section 1. Each section says what it answers, the form chosen, and why that
form and not another.

| # | Section | Answers | Form | Why this form |
|---|---|---|---|---|
| 0 | Header | Where am I, where can I go | Sticky bar, section links with scroll-spy, theme toggle, GitHub link | The page is long; the reader needs to know their position and jump without scrolling back |
| 1 | Hero | What is Reef, is it real, how do I install it | One claim sentence, three proof chips, the two-line install with a copy button, three buttons into the page | An evaluator decides in one screen; proofs are chips because each is a link to evidence, not a slogan |
| 2 | Start here | Which command for my situation | Five tabs (new project, existing project, a feature, a queue, a fresh clone), each a command and "what happens" | The README's quick-start table is right but a five-row table of long cells is read by nobody; tabs show one situation at a time, and the reader has exactly one |
| 3 | How it works | What happens between a queue row and a merge | A seven-stage pipeline; clicking a stage reveals what it writes, what gate it passes, who enforces it, and whether a human is involved | The pipeline is the mental model everything else hangs on; a static ASCII diagram (the README's) is accurate but dense, and detail-on-demand lets the eye hold the shape while the text explains one stage |
| 4 | Who does what | Which agent runs, with which tools, read-only or not | Six role cards with a read-only or writes badge and the dispatch rule | Operators debug denials by role ("the verifier may not run that"); cards group the facts a denial message refers to |
| 5 | What is enforced | Is this rule code, a tripwire, or prose | The README's ledger, parsed, with a class filter and a search box and a live count | Honesty is the project's differentiator; a filter makes the "prose" rows findable in one click, which is the point of the ledger |
| 6 | Tiers | Which model and judge my task gets | A four-row table with a short gloss per tier | Four rows fit a table; the gloss turns the tier names into the question an owner asks ("would two people build it differently?") |
| 7 | Measured | What does a row cost, what did the eval show | Stat tiles (hero number: the cost of one row) and a single-series bar chart of orchestrator context growth per stage, hover for the max context | A number per claim is the README's promise; tiles isolate the headline numbers and the chart shows the one shape the text argues about (planning is the expensive stage) |
| 8 | Settings | Which key, what default, what effect | The README's settings table, parsed and searchable | Owners look a key up by name; search is the right interaction for a reference table |
| 9 | Layout | Where a file lives after `/reef-init` | An expandable tree with a one-line purpose per node | A tree is the shape of the thing; expanding it on demand keeps the first view to the top level |
| 10 | Documents | Where to read more | Cards: design docs, perf reports, the Arabic manual, the changelog, the acknowledgments | The last reader wants the sources, grouped by kind |
| 11 | Footer | License, the two projects whose ideas Reef stands on | One line each | Required and honest, not prominent |

## 4. Display rules

- **Every number links to its source.** A stat tile without a link to a `docs/perf` line is not allowed.
- **Three enforcement classes, three colours, used nowhere else.** code = teal, tripwire = amber, prose = coral.
  The same three colours mean the same three things in the ledger, the pipeline detail, and the role cards.
- **The palette is the banner's.** Cream surface, coral, teal, navy, amber, slate (`assets/banner-light.svg`), with
  the dark steps chosen for the dark surface, not flipped. The fonts are the manual's (IBM Plex Sans and Mono), so the
  manual and the site read as one system.
- **Commands are blocks with a copy button; prose names at most one file per sentence.**
- **Progressive disclosure, never hidden content.** Tabs, the stage detail and the tree hide nothing from search
  engines or from a reader without JavaScript: every panel is in the HTML and JavaScript only chooses which one is
  open. Without JavaScript all panels show and the ledger section shows its README link.
- **No raster images.** The repository is the plugin (`plugin.json` source `./`), so the site ships inside every
  install. SVG and text only; the three site files total about 85 KB uncompressed.
- **Relative links only.** The site is served under `/reef/`, so a leading slash would break every link.
- **Phone first.** The pipeline turns vertical under 760px; tables scroll inside their own box; the header collapses
  to the essentials.

## 5. Maintenance: what to touch when

| Event | Touch |
|---|---|
| A release | the version in `README.md` badges, `.claude-plugin/plugin.json`, and the hero chip in `docs/index.html` (`data-version`) |
| A new measurement in `docs/perf` | the stat tiles and chart data in `docs/index.html` (`data-source` attributes name the file) |
| A ledger or settings row | nothing: the site reads the README |
| A new command or skill | the situation chooser and the pipeline detail in `docs/index.html` |
| A README heading rename ("What is enforced, and how", "Settings") | the matching heading text in `site.js` (`TABLE_HEADINGS`) |

## 6. Deployment

`.github/workflows/pages.yml` uploads `docs/` as the Pages artifact on every push to `main` and deploys it. It
enables Pages on first run (`actions/configure-pages` with `enablement: true`); if the first run fails on that step,
set Settings → Pages → Source to "GitHub Actions" once by hand. `docs/.nojekyll` keeps GitHub from running Jekyll
over the folder, so the HTML is served exactly as committed and the markdown beside it is served raw (the site links
the GitHub-rendered copies instead).

## 7. Decided against

- **A documentation generator** (MkDocs, Docusaurus, Jekyll themes). It would add a build, a dependency set, and a
  second place for every fact to live. The site is three hand-written files.
- **Copying the ledger into the site.** Forty-two rows copied once are forty-two rows wrong within a release.
- **Rendering `docs/perf` on the site.** Those reports are tables of measurements and GitHub renders them well;
  the site links to them.
- **Shortening the README into a landing page.** The README is the reference that the site presents; it got a
  "start here" block and a table of contents, and lost nothing.
