# Day zero — {{name}}

Each line is a command or a gate. Tick it when the gate is green, not when it feels done. `/reef-init` wrote this file and the ones it names; it never overwrites a file you edited (a differing rendering lands in `.reef/proposed/` with a diff).

- [ ] Reef installed: `/plugin install reef@mahmoudmoe`; review-toolkit agents present (`~/.claude/agents/plan-review.md`, `code-excellence.md`, `code-security.md`) — a stand-in runs only with an owner footnote
- [ ] `make setup` (hooks) · `{{install}}` · `{{test}}` green
- [ ] `.reef/config.json`: `gates.fast` under a minute, `gates.full` the whole suite, `gates.extra` the other checks (build, docs consistency, secret scan, migrations replay); `roles.*` as the owner routes them
- [ ] `.specify/constitution.md` read and cut to this project (8–15 articles, each with what it prevents)
- [ ] `AGENTS.md`: commands and layout true; "Owner decision points" filled
- [ ] `docs/queue.md`: the first batch's planned rows written before any code
- [ ] Every port, host and database parameterised; tests have a local database; `.env.example` holds the shape, `.env` is ignored
- [ ] CI: `.github/workflows/ci.yml` on PRs into `{{release}}` only; `sh scripts/reef-ci-local.sh` green locally; Dependabot targets `{{base}}`
- [ ] `tiers.light.allow` in `.reef/config.json` names the safe paths (nothing touching privacy, money, auth, tenancy, data)
- [ ] First row: `/reef-plan` → `/reef-plan-review` → `/reef-task` → `/reef-review`
