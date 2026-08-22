#!/bin/sh
# Reef portable test gate. Resolution: .reef/config.json -> autodetect -> LOUD FAIL.
# Never silently passes: a no-op gate is worse than none.
set -e
cd "$(git rev-parse --show-toplevel)"
if [ -f .reef/config.json ]; then
  CMD=$(python3 -c "import json;print(json.load(open('.reef/config.json')).get('gates',{}).get('test',''))" 2>/dev/null || true)
fi
if [ -z "$CMD" ]; then
  if [ -f uv.lock ] || { [ -f pyproject.toml ] && command -v uv >/dev/null; }; then CMD="uv run pytest -q"
  elif [ -f pyproject.toml ]; then CMD="pytest -q"
  elif [ -f package.json ] && python3 -c "import json,sys;sys.exit(0 if 'test' in json.load(open('package.json')).get('scripts',{}) else 1)" 2>/dev/null; then CMD="npm test --silent"
  elif [ -f Cargo.toml ]; then CMD="cargo test -q"
  elif [ -f go.mod ]; then CMD="go test ./..."
  fi
fi
[ -z "$CMD" ] && { echo "reef-gate: USER ACTION REQUIRED — no test command found; set .gates.test in .reef/config.json" >&2; exit 1; }
echo "reef-gate: $CMD" >&2
exec $CMD
