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
- `reef doctor` reports a Reef project whose `.claude/settings.json` lacks a wall: one `FAIL` line naming the missing deny
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

Exactly PR-4 section 7's block, with the network list built per stack. Template: `templates/claude-settings.json` (the
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

Filled from the current docs before the code commit; every key the block writes is listed with its quote and whether it
changed since #375 (PR-4 section 6, fetched 2026-11-15). See section 5a below.

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

1. `tests/test_init.py` **Walls**: init on a fresh node project writes `.claude/settings.json` with every PR-4 deny rule, the
   sandbox block (`enabled`, `failIfUnavailable`, `allowUnsandboxedCommands: false`, `denyWrite`) and the node allowlist; a
   python project gets the PyPI hosts and not npm's; a second init writes nothing; an existing settings file keeps its keys
   and values (its own `allow`, its own `sandbox.enabled: false`, its own deny rules, its own hosts) and gains only what it
   lacked; an unparseable file is left byte-identical and named; an unwritable file becomes a proposal.
2. `tests/test_init.py` **WallPatterns**: every Bash deny rule, run through a matcher that follows the docs, blocks its DENY
   case in `tests/test_guard.py` (the forms the rules claim) and blocks **no** ALLOW case, except the one D3 accepts.
3. `tests/test_doctor.py` **Walls**: a Reef project without `.claude/settings.json` → `FAIL walls: …`; with the block →
   `OK walls`; with `sandbox.enabled: false` → `FAIL` naming the key.

## 8. Questions for the owner (conservative default taken, flagged)

- Q1: add `.claude/settings.json` to `GUARD_FILES` (guard + seal) in a follow-up? Default here: **no** (section 6).
- Q2: should `reef update` commit the merged `.claude/settings.json`? Default here: **no**, the owner commits it.
