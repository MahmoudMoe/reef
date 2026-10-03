#!/bin/sh
# Reef portable test gate. Usage: reef-gate.sh [fast|full]   (no mode = full)
#   fast — the pre-commit gate:  gates.fast > gates.test > gates.full
#   full — review / verify / CI: gates.full > gates.test
# gates.test is the pre-0.4 single gate, kept as an alias, so a config that only sets it runs
# exactly what it ran before in both modes.
# Resolution: .reef/config.json -> autodetect (only when no config exists) -> LOUD FAIL.
# Never silently passes, never silently substitutes a different command: a no-op gate is
# worse than none, and a guessed gate is a no-op gate wearing a costume.
set -e
MODE=${1:-full}
case "$MODE" in
  fast|full) ;;
  *) echo "reef-gate: unknown mode '$MODE' (fast|full)" >&2; exit 1 ;;
esac
ROOT=$(git rev-parse --show-toplevel) || { echo "reef-gate: not a git repository" >&2; exit 1; }
cd "$ROOT"
CMD=''    # never inherit a caller's environment as the gate
if [ -f .reef/config.json ]; then
  command -v python3 >/dev/null 2>&1 || { echo "reef-gate: USER ACTION REQUIRED — python3 is required to read .reef/config.json" >&2; exit 1; }
  CMD=$(python3 -c "
import json, sys
g = json.load(open('.reef/config.json')).get('gates', {})
pick = lambda k: (g.get(k) or '').strip() if isinstance(g.get(k, ''), str) else ''
order = ('fast', 'test', 'full') if sys.argv[1] == 'fast' else ('full', 'test')
print(next((pick(k) for k in order if pick(k)), ''))" "$MODE") \
    || { echo "reef-gate: USER ACTION REQUIRED — .reef/config.json is unparseable" >&2; exit 1; }
  [ -n "$CMD" ] || { echo "reef-gate: USER ACTION REQUIRED — .reef/config.json exists but no $MODE gate is set (gates.full, or legacy gates.test); set it" >&2; exit 1; }
else
  if [ -f uv.lock ] || { [ -f pyproject.toml ] && command -v uv >/dev/null; }; then CMD="uv run pytest -q"
  elif [ -f pyproject.toml ]; then CMD="pytest -q"
  elif [ -f package.json ] && command -v python3 >/dev/null 2>&1 \
       && python3 -c "import json,sys;sys.exit(0 if 'test' in json.load(open('package.json')).get('scripts',{}) else 1)" 2>/dev/null; then CMD="npm test --silent"
  elif [ -f Cargo.toml ]; then CMD="cargo test -q"
  elif [ -f go.mod ]; then CMD="go test ./..."
  fi
  [ -n "$CMD" ] || { echo "reef-gate: USER ACTION REQUIRED — no test command found; run /reef-init or set gates.full in .reef/config.json" >&2; exit 1; }
fi
echo "reef-gate ($MODE): $CMD" >&2
# the gate is a shell command line, not an argv list — parse it as the human wrote it
# (unquoted `exec $CMD` would word-split and glob, mangling quoted args and operators).
exec sh -c "$CMD"
