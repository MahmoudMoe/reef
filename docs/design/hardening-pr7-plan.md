# Hardening PR-7: the PR-4 walls as Claude Code config, written by `/reef-init`

Status: **plan** (this file is the PR's first commit). Base: `main` at `e5d2197` (PR-1..6 merged, #372–#377). Source plan:
[`hardening-pr4-guard-audit.md`](hardening-pr4-guard-audit.md) (#375), sections 4, 5, 7, 9.

## 1. What this PR does

- `reef-init` writes the PR-4 walls (W1–W8) into the project's `.claude/settings.json`: a `permissions.deny` list and a
  `sandbox` block with `failIfUnavailable: true` and a per-stack network allowlist.
- An existing `.claude/settings.json` is **merged, never clobbered**: every key the project already has keeps its value; a
  deny rule the project lacks is appended; a list the project already has only gains entries. A file that does not parse is
  left alone and named. A file init cannot write (the sandbox protects `.claude` settings files from sandboxed commands, so a
  re-init run as a Bash call inside a sandboxed session gets `EPERM`) goes to the proposals dir with its diff and the
  `--accept` line, the existing PROPOSED flow; the owner accepts it from their own terminal.
- `reef doctor` reports a Reef project whose `.claude/settings.json` lacks a wall: one `WARN` line (section 5b) naming the missing deny
  rules / sandbox keys, with the fix (`reef-init`). A project whose own value overrides a wall (say `sandbox.enabled: false`)
  is reported the same way: init never changes it, the doctor says so.
- **Defense in depth: no guard check is removed or weakened.** `scripts/reef-guard.py` is not touched.

## 2. Owner decisions (final, relayed by the orchestrator)

- **D1 = (a)**: a per-stack network allowlist written by `reef-init`, plus `github.com` and `api.github.com`. Each host is
  documented in the template (section 4). No `excludedCommands`: `git`/`gh` stay inside the sandbox (W3 keeps its strength).
- **D2 = yes**: `Edit(/.githooks/**)` is denied (W4). A critical task that changes a hook does it by Bash under the guard's
  exemption, or the owner edits it.
- **D3 = accept**: `Bash(git commit * --no-verify)` stays, with its residual false positive (a commit message that *ends* in
  `--no-verify`). A test pins the known false positive so it is a stated cost, not a surprise.
- `sandbox.failIfUnavailable: true`, as the owner asked, re-verified against the current docs (section 5).

## 3. The block

PR-4 section 7's block, with the network list built per stack and two patterns narrowed (section 5a). Template: `templates/claude-settings.json` (the
walls, plus a `hosts` table: host → stack → why). `reef-init` renders `settings` + `sandbox.network.allowedDomains` =
common hosts + the detected stack's hosts, and merges it.

## 4. The network allowlist (D1), host by host

| stack | host | why |
|---|---|---|
| all | `github.com` | `git fetch/push` over https to the forge; `cargo audit` fetches RustSec's advisory db from it |
| all | `api.github.com` | `gh` (the loop's PRs, checks, merges, issues queue) |
| node | `registry.npmjs.org` | `npm ci` / `npx` / `npm audit` (the setup and the release audit gate) |
| node + Prisma | `binaries.prisma.sh` | `npx prisma generate` downloads the engines (only when the rendered `worktree.setup` runs it) |
| python | `pypi.org`, `files.pythonhosted.org` | `pip install -e .` / `uv sync` (index and the files), `pip-audit` (PyPI's advisory API) |
| rust | `index.crates.io`, `static.crates.io` | `cargo fetch` (sparse index, crate downloads) |
| go | `proxy.golang.org`, `sum.golang.org`, `vuln.go.dev` | `go mod download` (module proxy, checksum db), `govulncheck` |
| node, python, rust, go | `semgrep.dev` | the injection release gate's rule packs (`p/owasp-top-ten`, the stack pack) |

An unknown stack gets the two GitHub hosts only. A project's own `allowedDomains` entries are kept; Reef's are added.

## 5. Doc re-verification (fetched 2026-11-17)

Sources: <https://code.claude.com/docs/en/settings-reference>, <https://code.claude.com/docs/en/settings>,
<https://code.claude.com/docs/en/permissions>, <https://code.claude.com/docs/en/sandboxing>,
<https://code.claude.com/docs/en/plugins/manifest-reference>, <https://code.claude.com/docs/en/plugins/components>. Fetched with
WebFetch, which returns a model's extraction: the quotes are near-verbatim, not byte-compared. **[S]** = a summary.

| key / rule | what the docs say now | vs #375 |
|---|---|---|
| `sandbox.failIfUnavailable` | "Refuse to start when the sandbox can't, instead of running unsandboxed, except in an Anthropic-hosted environment". Default false. **Scope "Any file"** | **settled**: #375 could not tell whether project settings may set it. They can. Under an admin-required sandbox a repository's value is ignored only when it would loosen it **[S]** |
| `sandbox.enabled` | "set `sandbox.enabled` to true in a settings file". Default false. Scope "Any file, with limits on project and local settings" **[S]** | unchanged |
| `sandbox.allowUnsandboxedCommands` | default **true**. "With the retry disabled, Claude Code ignores the `dangerouslyDisableSandbox` parameter." "A false in your user settings, --settings, or managed settings holds even when a project's settings set true. Before v2.1.285, a project's true overrode a false in your user settings." | the project-override note is new. The project's `false` is the restrictive direction, so it holds |
| `sandbox.filesystem.denyWrite` | prefixes: `/` = filesystem root, `~/` = home, `./` or none = the project root (project settings). "On Linux and WSL2, an entry for a path that doesn't exist yet has no effect, so create the path first." | the missing-path note is new: `~/.claude/plugins` and `.git/hooks` exist wherever Reef runs, and init writes `.claude/settings.json` first |
| `sandbox.network.allowedDomains` | exact name. "Your allowed domains start empty." Wildcards are allowed (`*.npmjs.org`). "An allowedDomains entry with no port allows every port on that host." | wildcards were not checked in #375. Reef lists exact hosts only (narrower) |
| default protected paths | `.claude` settings files, `.claude/{skills,agents,commands,hooks,workflows}`, `.mcp.json` (cwd and above), hooks and config inside `.git` (cwd only), most of `~/.claude` **[S]**. `~/.claude/plugins`: not named | unchanged. W1 lists the plugin tree explicitly |
| `Edit(…)` paths | `//path` absolute, `~/path` home, `/path` "relative to the settings source", `path`/`./path` the cwd. Gitignore syntax. "Write, NotebookEdit, or legacy MultiEdit: use Edit(docs/\*\*) in place of Write(docs/\*\*)". A `Write(path)` rule "doesn't match a read, search, or edit against it" | **stronger**: `Write(…)` does not work at all. The block uses `Edit(…)` only |
| Bash rules | "The * stands in for whatever text is in its place." "Claude Code matches everything before the first * as written." **"A * at the end, with a space before it, also matches the bare command."** Separators: `&&`, `\|\|`, `;`, `\|`, `\|&`, `&`, newlines; deny applies to every subcommand. "A deny or ask rule matches past any leading assignment." "…isn't a security boundary around the program." | the bare-command clause makes two PR-4 patterns block ALLOW cases (section 5a) |
| precedence | "An allow rule can't carve an exception out of a deny rule." Lists merge across files. Project `allow` waits for workspace trust; "deny and ask rules aren't affected, since they only restrict." | unchanged |
| plugins | the manifest and components pages list no `settings.json`, `permissions` or `sandbox` | unchanged: a plugin cannot ship the walls |
| `.claude` settings by the Edit tool | "In bypassPermissions mode, Claude Code skips permission prompts, including for writes to protected paths such as .git and .claude." | so the protection depends on the mode, and W2's explicit `Edit(/.claude/settings.json)` deny is load-bearing (deny "block[s] in every mode") |

### 5a. Two PR-4 patterns narrowed (found by T2, decided conservatively)

- `Bash(git commit * --no-verify *)` blocks `git commit -m "docs: explain why --no-verify is forbidden"`, a case in the
  guard's ALLOW table (`tests/test_guard.py`). It is now `Bash(git commit * --no-verify -*)`: the flag followed by another
  flag. `git merge` gets the same shape.
- `Bash(git commit * -n *)`, with the bare-command clause, blocks `git commit -m fix -- -n` (ALLOW: a pathspec). It is now
  `Bash(git commit * -n -*)`.
- What the config gives up: `git commit -a --no-verify file.txt`-style forms, which nothing in Reef produces. The guard
  still holds them (B3). D3's accepted false positive is unchanged (`Bash(git commit * --no-verify)`), and T2 pins it under
  the parsed-words reading. PR-4 B5's stricter push rule is pinned too (`git push --no-verify` is always denied).
- The matcher in T2 is a model of the documented syntax. It tries both readings (text as written, and words without
  quotes), and treats a heredoc body as data. It is not the harness: T5 (opt-in, `claude -p`) stays the place to ask the real one.

## 5b. Choices made while building

- **The doctor says WARN, not FAIL.** A FAIL changes the doctor's exit code for every Reef project that has not re-run init
  since this release. The guard still holds every rule, so a project without walls is less walled, not broken.
- **The host list is exact hosts.** Prisma's `binaries.prisma.sh` is added only when `package.json` depends on Prisma.
- **The file is re-serialised on a merge** (`json.dumps`, indent 2). Keys, values and list order are kept. Whitespace and
  formatting are not.

## 6. What is NOT in this PR (and why)

- **`GUARD_FILES` gains `.claude/settings.json`** (PR-4 W2's guard half): deferred. It is the guard's and `reef_common.py`'s
  regex (not files this PR owns), and it also feeds the runner's `guard_seal`, so a session that runs `reef-init` would
  change the seal. The wall itself holds without it: `Edit(/.claude/settings.json)` is denied, and the sandbox write-protects
  `.claude` settings files by default. Flagged for the owner (section 8).
- **`reef update` commits `.claude/settings.json`**: not changed. `reef update` runs `reef-init`, so the walls are merged on
  every update; the file is left for the owner's commit (as `.reef/config.json` value changes are). `reef-update.py` is not
  this PR's file.
- T3/T4/T6 (the sandbox's own enforcement, with bubblewrap) and T5 (headless `claude -p`): need the sandbox runtime or an API
  key, so they are not in `sh tests/run.sh`. This PR adds T1 (the block is written and merged), T2 (every deny pattern against
  the guard's DENY/ALLOW tables, with a matcher that follows the documented rule syntax), the doctor check, and T7's cheap
  half (the block parses, every host is documented, the sandbox paths use the sandbox prefixes).
- Managed settings, removing any guard check: out of scope (the brief).

## 7. Tests first (the red)

All three are in one new suite, `tests/test_walls.py` (so it does not conflict with the parallel PRs' edits to `test_init.py`).

1. **Init**: init on a fresh node project writes `.claude/settings.json` with every PR-4 deny rule, the
   sandbox block (`enabled`, `failIfUnavailable`, `allowUnsandboxedCommands: false`, `denyWrite`) and the node allowlist; a
   python project gets the PyPI hosts and not npm's; a second init writes nothing; an existing settings file keeps its keys
   and values (its own `allow`, its own `sandbox.enabled: false`, its own deny rules, its own hosts) and gains only what it
   lacked; an unparseable file is left byte-identical and named; an unwritable file becomes a proposal.
2. **Patterns**: every Bash deny rule, run through a matcher that follows the docs, blocks its DENY
   case in `tests/test_guard.py` (the forms the rules claim) and blocks **no** ALLOW case, except the one D3 accepts.
3. **Doctor**: a Reef project without `.claude/settings.json` → `WARN walls: …`; with the block →
   `OK walls`; with `sandbox.enabled: false` → `WARN` naming the key.

## 8. Questions for the owner (conservative default taken, flagged)

- Q1: add `.claude/settings.json` to `GUARD_FILES` (guard + seal) in a follow-up? Default here: **no** (section 6).
- Q2: should `reef update` commit the merged `.claude/settings.json`? Default here: **no**, the owner commits it.
