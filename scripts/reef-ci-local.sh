#!/bin/sh
# Reef local CI: every gate CI runs, run here, every exit code read.
#   sh scripts/reef-ci-local.sh [--ci] [--require name,name]
# Gates come from .reef/config.json: gates.full first (as `full`), then every gates.extra.<name>
# in order. Each runs under `sh -c` with its output in .reef/ci-local/<name>.log and its exit code
# read DIRECTLY — never through a pipe (the pipe reports the last command's status; a red gate
# went unnoticed until CI once). A gate exits 77 to say "skipped" (no database here, no key).
# Exit 0 every gate passed · 1 something failed or a --require'd gate was skipped · 2 nothing failed
# but something was skipped — AND 2 IS NOT SUCCESS. CI calls this same script (--ci), so a check
# that exists only on the release branch cannot exist.
set -u
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "reef-ci-local: not a git repository" >&2; exit 1; }
cd "$ROOT"
command -v python3 >/dev/null 2>&1 || { echo "reef-ci-local: python3 is required to read .reef/config.json" >&2; exit 1; }
[ -f .reef/config.json ] || { echo "reef-ci-local: no .reef/config.json — run /reef-init" >&2; exit 1; }
REQUIRE=""
CI=0
while [ $# -gt 0 ]; do
  case "$1" in
    --require) REQUIRE=$2; shift 2 ;;
    --require=*) REQUIRE=${1#--require=}; shift ;;
    --ci) CI=1; shift ;;
    *) echo "reef-ci-local: unknown argument $1" >&2; exit 1 ;;
  esac
done
LOGDIR=.reef/ci-local
mkdir -p "$LOGDIR"
# one line per gate: name<TAB>command — order is the config's order; a name must not repeat
GATES=$(python3 - <<'PY'
import json, sys
cfg = json.load(open(".reef/config.json"))
g = cfg.get("gates", {})
full = g.get("full") or g.get("test") or ""
rows = [("full", full)]
extra = g.get("extra", {})
if isinstance(extra, dict):
    rows += [(str(k), str(v)) for k, v in extra.items()]
names = [r[0] for r in rows]
if len(names) != len(set(names)):
    print("reef-ci-local: a gate name repeats in gates.extra", file=sys.stderr); sys.exit(1)
for name, cmd in rows:
    if "\t" in name or "\n" in cmd:
        print("reef-ci-local: gate names and commands must be single-line", file=sys.stderr); sys.exit(1)
    print(name + "\t" + cmd)
PY
) || exit 1
[ -n "$GATES" ] || { echo "reef-ci-local: no gates configured" >&2; exit 1; }
FAILED=0; SKIPPED=0; PASSED=0; REQUIRED_SKIP=0
echo "reef-ci-local: gates from .reef/config.json (logs in $LOGDIR/)"
OLDIFS=$IFS
IFS='
'
for row in $GATES; do
  IFS=$OLDIFS
  name=${row%%	*}; cmd=${row#*	}
  if [ -z "$cmd" ]; then
    echo "  FAIL     $name — empty command (a no-op gate is worse than none)"
    FAILED=$((FAILED+1)); continue
  fi
  sh -c "$cmd" >"$LOGDIR/$name.log" 2>&1
  rc=$?
  if [ "$rc" -eq 0 ]; then
    PASSED=$((PASSED+1)); echo "  ok       $name (exit 0)"
  elif [ "$rc" -eq 77 ]; then
    SKIPPED=$((SKIPPED+1)); echo "  SKIPPED  $name (exit 77) — not a pass"
    case ",$REQUIRE," in *",$name,"*) REQUIRED_SKIP=$((REQUIRED_SKIP+1)); echo "           required by --require: counts as a failure" ;; esac
  else
    FAILED=$((FAILED+1)); echo "  FAIL     $name (exit $rc) — $LOGDIR/$name.log"
    tail -n 5 "$LOGDIR/$name.log" | sed 's/^/           | /'
  fi
done
IFS=$OLDIFS
echo "reef-ci-local: $PASSED passed, $FAILED failed, $SKIPPED skipped"
if [ "$FAILED" -gt 0 ] || [ "$REQUIRED_SKIP" -gt 0 ]; then exit 1; fi
if [ "$SKIPPED" -gt 0 ]; then
  echo "reef-ci-local: exit 2 — a skipped gate is not a passed gate; name it with --require to make a skip a failure"
  [ "$CI" -eq 1 ] && exit 1   # CI has no business skipping: a skip there is a failure
  exit 2
fi
exit 0
