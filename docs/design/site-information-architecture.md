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
| **Evaluator** (saw the repo in a list, a feed, a link) | 90 seconds | What is this, and what does it do to my project? | The hero: one sentence in the reader's terms, the install command, three facts (two decisions are yours, nothing you wrote is overwritten, it resumes from disk) |
| **Adopter** (has a project and wants to try it) | 10 minutes | Where do I start for *my* situation? | The situation chooser: five situations, one command each, what happens next |
| **Operator** (runs it daily, needs to understand a stop or a denial) | as needed | Why did Reef refuse that, and who decides? | The pipeline explorer, the roles, and the **in practice** section: what it needs, what it never does, and a table of every stop with what it means and what to do |
| **Owner** (tunes the numbers, sets the models) | as needed | Which key, what default, what effect? | The tiers table and the searchable settings reference |
| **Skeptic / contributor** | 30 minutes | Which rules are really code, and where are the numbers? | Not on the site: the docs index links the README's honesty ledger and the `docs/` folder. The page is for people who run Reef, not for people who maintain it |

The first two readers get everything above the fold or one scroll below it. The operator and the owner get sections that
are **interactive on purpose**: a stage is read by clicking it, a settings table by searching it.

**The test for every sentence on the page: does a person running Reef on their own project need it?** Script names,
agent file paths, test counts, eval scores, dogfood runs and the code/tripwire/prose accounting are the maintainer's
concern and live in the README and under `docs/`. The page says what Reef does, what it needs, what it never does,
what each stop means, and what the user can change. The one exception is a script a user will actually type, such as
`scripts/reef-watch` or `scripts/reef-init.py --accept`.

## 2. The surface map: who owns what

| Surface | Owns | Links to (never copies) |
|---|---|---|
| `README.md` (the GitHub page) | The claim, the quick start, the **honesty ledger**, the tiers, the settings table, the measured summary, the layout, the status | the site, the manual, `docs/perf`, `docs/design` |
| `docs/index.html` (the site) | The *presentation* for a user: the situation chooser, the pipeline explorer, the roles, the in-practice section, the expandable layout tree | **the settings table and the version are fetched from the README at page load and parsed**; the honesty ledger, the design notes and the measurements are linked, never shown |
| `docs/manual/ar/index.html` | The Arabic user manual (learning path, daily use, troubleshooting) | the README for reference facts |
| `docs/design/*.md` | Design decisions and their reasoning (the graph executor, the planning cost cut, this document) | — |
| `docs/perf/*.md` | Every measured number: the dogfood run, the baseline, the eval, the payloads, the guard profile | — |
| `CHANGELOG.md` | What changed in each version, with the first contact that caused it | — |
| `skills/`, `agents/`, `commands/` | The behaviour itself | — |

Two consequences:

- **The settings table and the version have one home.** The site parses the README's "Settings" table and its
  version badge at runtime (`docs/assets/site.js`, `loadReadmeTables`). It tries the README served beside the site
  first, then the one in the repository root (a local preview), then the raw file on GitHub. If all fail or the
  heading moves, the section degrades to a link to the README section and the version chip keeps the value written
  in the HTML.
- **The site does not advertise figures.** No cost, token or eval number is restated on the page; the docs index links
  `docs/` for contributors, and the hero's three chips are facts, not counts.

## 3. The site, section by section

Reading order is the reader order of section 1. Each section says what it answers, the form chosen, and why that
form and not another.

| # | Section | Answers | Form | Why this form |
|---|---|---|---|---|
| 0 | Header | Where am I, where can I go | Sticky bar, section links with scroll-spy, theme toggle, GitHub link | The page is long; the reader needs to know their position and jump without scrolling back |
| 1 | Hero | What is Reef, what does it do to my project, how do I install it | One claim sentence, a lead written as what happens to the reader's row, three fact chips, the two-line install with a copy button, four buttons into the page | An evaluator decides in one screen; the chips are the three facts an owner most wants settled before installing anything |
| 2 | Start here | Which command for my situation | Five tabs (new project, existing project, a feature, a queue, keeping it running: the doctor, a delegated night, the headless runner, the pentest, graph mode, the updater, a fresh clone), each a command and "what happens" | The README's quick-start table is right but a five-row table of long cells is read by nobody; tabs show one situation at a time, and the reader has exactly one |
| 3 | How it works | What happens between a queue row and a merge | A seven-stage pipeline; clicking a stage reveals what it writes, what lets it through, and what the user's part is | The pipeline is the mental model everything else hangs on; a static ASCII diagram (the README's) is accurate but dense, and detail-on-demand lets the eye hold the shape while the text explains one stage. The "enforced by" column of script names was cut: a user meets the gate, not the script |
| 4 | Who does what | Which agent runs, read-only or not, on which model | Nine role cards (the planner, the security pass and the owner's proxy included) with a read-only or writes badge and the model it runs on | Operators debug denials by role ("the verifier may not run that"); cards group the facts a denial message refers to |
| 5 | Tiers | Which model and judge my task gets | A four-row table with a short gloss per tier | Four rows fit a table; the gloss turns the tier names into the question an owner asks ("would two people build it differently?") |
| 6 | In practice | What does it need, what will it never do, what does this stop mean | Three cards (needs, never does, what you accept) and a three-column table: you see, it means, you do | An operator meets Reef through its stops and denials; a lookup table keyed on the message they see answers them faster than any narrative, and the three cards are the facts an adopter decides on before installing |
| 7 | Settings | Which key, what default, what effect | The README's settings table, parsed and searchable | Owners look a key up by name; search is the right interaction for a reference table |
| 8 | Layout | Where a file lives after `/reef-init` | An expandable tree with a one-line purpose per node | A tree is the shape of the thing; expanding it on demand keeps the first view to the top level |
| 9 | Documents | Where to read more | Cards: the README, the Arabic manual, the changelog, the README's honesty ledger, and one card for contributors into `docs/` | The last reader wants the sources; the maintainer's material gets one door, not a shelf |
| 10 | Footer | License, where the page's source lives | One line | Required, not prominent |

## 4. Display rules

- **Every count links to its source.** The page restates no measurement; a count it does show (the proof chips) links to the evidence.
- **One colour means one thing.** Teal is the action colour; a dark dot and a dark badge mark the two places the
  user decides; the role badges are neutral. No colour carries a meaning the page does not explain in words beside it.
- **The palette is the banner's.** Cream surface, coral, teal, navy, amber, slate (`assets/banner-light.svg`), with
  the dark steps chosen for the dark surface, not flipped. The fonts are the manual's (IBM Plex Sans and Mono), so the
  manual and the site read as one system.
- **Commands are blocks with a copy button; prose names at most one file per sentence.**
- **Progressive disclosure, never hidden content.** Tabs, the stage detail and the tree hide nothing from search
  engines or from a reader without JavaScript: every panel is in the HTML and JavaScript only chooses which one is
  open. Without JavaScript all panels show and the settings section shows its README link.
- **No raster images.** The repository is the plugin (`plugin.json` source `./`), so the site ships inside every
  install. SVG and text only; the three site files total about 85 KB uncompressed.
- **Relative links only.** The site is served under `/reef/`, so a leading slash would break every link.
- **Phone first.** The pipeline turns vertical under 760px; tables scroll inside their own box; the header collapses
  to the essentials.

## 5. Maintenance: what to touch when

| Event | Touch |
|---|---|
| A release | the version in `README.md` badges, `.claude-plugin/plugin.json`, and the hero chip in `docs/index.html` (`data-version`) |
| A new report in `docs/perf` | a card in the docs section of `docs/index.html` |
| A new stop message or guard denial | a row in the "When it stops" table of `docs/index.html`, the README and the Arabic manual (the three carry the same rows, keyed on the exact text the tick prints) |
| A change in the pipeline's order (where the owner's gate sits, what runs in parallel) | the stage panels in `docs/index.html`, the README's steps and Mermaid diagram, the manual's section 3 and its figure caption |
| A settings row | nothing: the site reads the README |
| A ledger row | nothing: the site links the ledger and does not show it |
| A new command or skill | the situation chooser and the pipeline detail in `docs/index.html` |
| A README heading rename ("Settings") | the matching heading text in `site.js` (`TABLE_HEADINGS`) |
| The Arabic manual | kept at the same workflow as the README and the site (0.6 tree, the 0.7 gate-last flow, graph mode, the doctor, the updater); it names 0.7.1 as the release |

## 6. Deployment

`.github/workflows/pages.yml` uploads `docs/` as the Pages artifact on every push to `main` and deploys it. It
enables Pages on first run (`actions/configure-pages` with `enablement: true`); if the first run fails on that step,
set Settings → Pages → Source to "GitHub Actions" once by hand. `docs/.nojekyll` keeps GitHub from running Jekyll
over the folder, so the HTML is served exactly as committed and the markdown beside it is served raw (the site links
the GitHub-rendered copies instead).

## 7. Decided against

- **A documentation generator** (MkDocs, Docusaurus, Jekyll themes). It would add a build, a dependency set, and a
  second place for every fact to live. The site is three hand-written files.
- **Showing the honesty ledger on the site.** It was there first, parsed from the README with a class filter. It is
  the maintainer's accounting of which rule is code and which is prose, in script and test names; a user meets the
  rules as gates and stops, which the in-practice table covers. The docs section links the ledger for the curious.
- **Copying any README table into the site.** Forty-two rows copied once are forty-two rows wrong within a release.
- **Rendering `docs/perf` on the site.** Those reports are tables of measurements and GitHub renders them well;
  the site links to them.
- **Shortening the README into a landing page.** The README is the reference that the site presents; it got a
  "start here" block and a table of contents, and lost nothing.
