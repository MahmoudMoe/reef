#!/bin/sh
# Sabotage suite for scripts/reef-ci-local.sh: every exit code read, a skip is not a pass,
# --require turns a skip into a failure, --ci never accepts a skip, an empty gate fails loudly.
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
TMP=$(mktemp -d "${TMPDIR:-/tmp}/reef-cilocal-test.XXXXXX")
trap 'rm -rf "$TMP"' EXIT
PASS=0; FAILED=0

t() { # t <name> <expected-rc> -> compares $? of the previous command
  rc=$?
  if [ "$rc" -eq "$2" ]; then PASS=$((PASS+1)); echo "ok   $1"
  else FAILED=$((FAILED+1)); echo "FAIL $1 (rc=$rc wanted $2)"; fi
}

mkrepo() { # mkrepo <dir> <config-json>
  rm -rf "$1"; mkdir -p "$1"; cd "$1"
  git init -q -b main
  mkdir -p scripts .reef
  cp "$ROOT/scripts/reef-ci-local.sh" scripts/
  printf '%s\n' "$2" > .reef/config.json
}

mkrepo "$TMP/c1" '{"gates": {"full": "true", "extra": {"build": "true", "docs": "true"}}}'
sh scripts/reef-ci-local.sh >/dev/null 2>&1
t "all gates green: exit 0" 0

mkrepo "$TMP/c2" '{"gates": {"full": "true", "extra": {"build": "exit 3"}}}'
OUT=$(sh scripts/reef-ci-local.sh 2>&1); RC=$?
[ "$RC" -eq 1 ]
t "one red gate: exit 1" 0
echo "$OUT" | grep -q 'FAIL     build (exit 3)'
t "  the failing gate and ITS exit code are named" 0

# the gate's exit code is read directly — a gate whose LAST command is green but whose first
# command is red is still red (the config says what it says; no pipe can hide it here)
mkrepo "$TMP/c3" '{"gates": {"full": "sh -c \"exit 4\""}}'
sh scripts/reef-ci-local.sh >/dev/null 2>&1
t "exit code of the gate command itself is the verdict" 1

mkrepo "$TMP/c4" '{"gates": {"full": "true", "extra": {"transactions": "exit 77"}}}'
sh scripts/reef-ci-local.sh >/dev/null 2>&1
t "a SKIPPED gate (77): exit 2, never 0" 2
sh scripts/reef-ci-local.sh --require transactions >/dev/null 2>&1
t "  --require makes the skip a failure: exit 1" 1
sh scripts/reef-ci-local.sh --require=other >/dev/null 2>&1
t "  --require of another gate: still exit 2" 2
sh scripts/reef-ci-local.sh --ci >/dev/null 2>&1
t "  --ci never accepts a skip: exit 1" 1

mkrepo "$TMP/c5" '{"gates": {"full": ""}}'
sh scripts/reef-ci-local.sh >/dev/null 2>&1
t "empty gates.full FAILS LOUDLY (a no-op gate is worse than none)" 1

mkrepo "$TMP/c6" '{"gates": {"test": "true"}}'
sh scripts/reef-ci-local.sh >/dev/null 2>&1
t "pre-0.4 gates.test still works as the full gate" 0

mkrepo "$TMP/c7" '{"gates": {"full": "echo hello > seen.txt"}}'
sh scripts/reef-ci-local.sh >/dev/null 2>&1 && [ -f seen.txt ] && [ -f .reef/ci-local/full.log ]
t "gate ran via sh -c in the repo root, log written" 0

cd "$TMP"; ( cd / && sh "$TMP/c1/scripts/reef-ci-local.sh" ) >/dev/null 2>&1
t "outside a git repo FAILS LOUDLY" 1

echo
echo "ci-local suite: $PASS passed, $FAILED failed"
[ "$FAILED" -eq 0 ]
