# Contributing to Reef

Thanks for helping. Reef is a Claude Code plugin written in Python 3 (standard library only) and POSIX shell. You need no
build step and no dependencies to work on it.

## Ways to help

- **Try it on a real project and report what broke.** Run `/reef-init` on a repo, then `reef` or `/reef-loop`, and open an
  issue with what you ran, what you expected and what happened. Run `reef doctor` and paste its output too.
- **Try to break the guard.** If an agent can skip a gate, write an approval, merge on red or edit a guard file
  (`scripts/reef*`, `hooks/hooks.json`), open an issue with the exact command or tool call.
- **Fix a bug or a rough edge.** Read [`CHANGELOG.md`](CHANGELOG.md): every entry names the run that found it, which is the
  standard a fix should meet.
- **Support another stack.** `/reef-init` adapts to your stack (it already handles Python, Node and Next.js). Adding a stack
  means changing `scripts/reef-init.py` and `templates/`, with a test in `tests/test_init.py`.
- **Support another host.** OpenCode support is early ([`docs/design/portability-plan.md`](docs/design/portability-plan.md)).
  Building and merging a real feature on it, and reporting back, helps.
- **Improve the docs**: the [README](README.md), the [website and manual](https://mahmoudmoe.github.io/reef/) (`docs/`) and
  the Arabic manual.

## Set up

```bash
git clone https://github.com/MahmoudMoe/reef.git
cd reef
sh tests/run.sh
```

The run ends with `ALL REEF TESTS PASSED`. It needs `python3` 3.9 or newer (the floor is the Python a Mac ships), `git` and
`sh`. To test your clone inside Claude Code, add it as a local marketplace:

```
/plugin marketplace add /path/to/your/reef
/plugin install reef@mahmoudmoe
```

## Where things live

| Folder | What is in it |
|---|---|
| `scripts/` | the mechanisms: the guard (`reef-guard.py`), the loop, the runner, init, the `reef` screen |
| `hooks/` | `hooks.json`, which calls the guard before every tool call |
| `skills/`, `commands/`, `agents/` | the slash commands and the agent roles (prose the model reads) |
| `templates/` | the files `/reef-init` writes into a project |
| `schemas/`, `migrations/` | the config schema and upgrades between versions |
| `tests/` | the selftests (`run.sh`) and the stress suites (`stress_*.py`) |
| `docs/` | design notes, measurements, the website |

## Make a change

1. Fork the repo and create a branch from `main`.
2. Make the change, and add or update a test in `tests/` that **fails without your change**. Every mechanism in Reef has a
   test that shows it going red on the defect it catches.
3. Run the tests:
   ```bash
   sh tests/run.sh
   ```
   One suite at a time: `python3 -m unittest tests.test_guard -v`. The stress suites:
   `REEF_NO_RESUME=1 python3 -m unittest discover -s tests -p 'stress_*.py' -q`.
4. If you changed anything under `agents/`, `skills/`, `hooks/`, `scripts/`, `templates/`, `commands/`, `schemas/` or
   `migrations/`, bump the version (Claude Code reinstalls a plugin only when the version changes):
   ```bash
   python3 .github/bump-version.py
   ```
5. Add a line to `CHANGELOG.md` under the unreleased version. Say what changed and what made it necessary.
6. Open a pull request against `main`.

## What CI checks on your PR

- `sh tests/run.sh` and the stress suites, on Ubuntu (dash, the strict POSIX shell) and macOS (Python 3.9).
- **Shipped files changed means a new version.** This fails if step 4 was skipped.
- **A code script changed means `tests/` changed.** A `scripts/reef-*` file whose header says `# CLASS: code` cannot change
  without a test change.

## Style

- Python: standard library only, and it must run on 3.9.
- Shell: POSIX `sh`, no bash-only syntax (CI runs it under dash).
- A new `scripts/reef-*` script carries `# CLASS: code` or `# CLASS: tripwire` in its first 3 lines
  (`tests/test_contracts.py` checks it). The README's "honesty ledger" explains the classes.
- Keep messages and docs plain: short sentences, the exact command, no placeholders the reader must guess.

## Questions

Open an issue on [GitHub](https://github.com/MahmoudMoe/reef/issues). By contributing, you agree your work is released
under the [MIT License](LICENSE).
