#!/bin/sh
# CLASS: code
# Reef portable test gate. Usage: reef-gate.sh [fast|full] [--failures]   (no mode = full)
#   --failures (0.6, 5.6): the whole output goes to .reef/ci-local/gate-<mode>.log; stdout gets the exit code and
#   the FAILING BLOCK only (at most context.failure_lines lines, default 60, from the first failure marker to the
#   end) — never the raw log. Truncation happens here, so the exit code is the gate's, not a pipe's.
#   fast — the pre-commit gate:  gates.fast > gates.test > gates.full
#   full — review / verify / CI: gates.full > gates.test
# gates.test is the pre-0.4 single gate, kept as an alias, so a config that only sets it runs
# exactly what it ran before in both modes.
# Resolution: .reef/config.json -> autodetect (only when no config exists) -> LOUD FAIL.
# Never silently passes, never silently substitutes a different command: a no-op gate is
# worse than none, and a guessed gate is a no-op gate wearing a costume.
set -e
MODE=full; FAILURES=0
for a in "$@"; do
  case "$a" in
    fast|full) MODE=$a ;;
    --failures) FAILURES=1 ;;
    *) echo "reef-gate: unknown argument '$a' (fast|full|--failures)" >&2; exit 1 ;;
  esac
done
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
# 0.7: a hung gate ends — gates.timeout_s (default 1200, 0 = none) kills the gate's whole process group and exits 124
# with a line that says so (2026-10-18, qassimha 1103: a test waiting on a port it had leaked held vitest for 21 minutes
# and the graph-mode workflow for three hours; chat mode's Bash would have stopped at ten). Without python3 the gate
# runs unguarded, as before.
TIMEOUT=1200
if [ -f .reef/config.json ]; then
  TIMEOUT=$(python3 -c "import json;g=json.load(open('.reef/config.json')).get('gates',{});print(int(g.get('timeout_s',1200) or 0))" 2>/dev/null || echo 1200)
fi
# 0.7.2: gates.resources (default none) — the gate holds each named resource for its whole run, in the main checkout and
# every worktree (reef-graph.py lock, keyed on the main checkout), so two runs never share a test database (2026-10-24,
# the trial: a gate went red while a verifier's run used the same database). Waiting for the resource counts toward
# the timeout too, so the limit doubles while one is held.
RES=''
if [ -f .reef/config.json ] && [ -f scripts/reef-graph.py ]; then
  RES=$(python3 -c "import json,re;r=json.load(open('.reef/config.json')).get('gates',{}).get('resources') or [];print(' '.join(x for x in r if isinstance(x,str) and re.fullmatch(r'[A-Za-z0-9._-]+',x)))" 2>/dev/null || true)
fi
if [ -n "$RES" ]; then
  REEF_GATE_CMD=$CMD; export REEF_GATE_CMD
  WAIT=$(( TIMEOUT > 0 ? TIMEOUT : 21600 ))
  CMD='sh -c "$REEF_GATE_CMD"'
  for r in $RES; do CMD="python3 scripts/reef-graph.py lock $r --timeout $WAIT -- $CMD"; done
  [ "$TIMEOUT" -gt 0 ] && TIMEOUT=$(( TIMEOUT * 2 ))
  echo "reef-gate ($MODE): holds $RES while it runs (gates.resources)" >&2
fi
run_gate() {   # run_gate <command line> [tee log]: the exit code of the gate, or 124 on a hang past gates.timeout_s
  if [ "$TIMEOUT" -le 0 ] || ! command -v python3 >/dev/null 2>&1; then sh -c "$1"; return $?; fi
  python3 - "$1" "$TIMEOUT" "${2:-}" <<'PY'
import os, signal, subprocess, sys, threading
cmd, limit, tee = sys.argv[1], int(sys.argv[2]), sys.argv[3]
p = subprocess.Popen(["sh", "-c", cmd], start_new_session=True,
                     stdout=subprocess.PIPE if tee else None, stderr=subprocess.STDOUT if tee else None)
def pump():   # 0.7.1: the output streams as before and is kept, so a cached run can show what the green run said
    with open(tee, "wb") as f:
        for chunk in iter(lambda: os.read(p.stdout.fileno(), 65536), b""):
            sys.stdout.buffer.write(chunk); sys.stdout.buffer.flush(); f.write(chunk)
t = threading.Thread(target=pump, daemon=True) if tee else None
if t:
    t.start()
try:
    rc = p.wait(timeout=limit)
    if t:
        t.join(10)
    sys.exit(rc)
except subprocess.TimeoutExpired:
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except OSError:
        pass
    p.wait()
    print(f"reef-gate: TIMEOUT after {limit}s — the gate hung (a test waiting on a port, a server left running); its process group was killed. gates.timeout_s sets the limit, 0 = none", file=sys.stderr)
    sys.exit(124)
PY
}
# 0.7: the gate is deterministic on a tree, so one green run per snapshot is enough (2026-10-18: the same tree ran the
# full gate five times in one task — implementer, orchestrator, verifier, pre-commit twice). The marker is written only
# by a green run here and read only when REEF_GATE_NO_CACHE is unset; the pre-commit sets it and always runs the gate.
SNAP=''
if [ -z "${REEF_GATE_NO_CACHE:-}" ] && [ -x scripts/reef-snapshot.sh ] || { [ -z "${REEF_GATE_NO_CACHE:-}" ] && [ -f scripts/reef-snapshot.sh ]; }; then
  SNAP=$(sh scripts/reef-snapshot.sh 2>/dev/null) || SNAP=''
fi
if [ -n "$SNAP" ] && [ -f ".reef/ci-local/gate-$MODE-$SNAP.ok" ]; then
  echo "reef-gate ($MODE): cached — exit 0 on this snapshot ($(printf %s "$SNAP" | cut -c1-12)); the tree is unchanged since that run (REEF_GATE_NO_CACHE=1 forces a run)"
  # 0.7.1: the evidence comes with it (2026-10-24: judges re-ran the gate about four times a verdict to see a count)
  [ -s ".reef/ci-local/gate-$MODE-$SNAP.ok" ] && { echo "reef-gate ($MODE): that green run ended:"; sed 's/^/  /' ".reef/ci-local/gate-$MODE-$SNAP.ok"; }
  [ -f ".reef/ci-local/gate-$MODE-$SNAP.green.log" ] && echo "reef-gate ($MODE): its full log: .reef/ci-local/gate-$MODE-$SNAP.green.log"
  exit 0
fi
# v3 phase 1 (2026-10-25, the first adoption: the full suite ran three times on one commit and nothing counted it — this
# log is overwritten by the next run, the green marker removed by the next green): every REAL run appends one line to
# the MAIN checkout's .reef/ci-local/runs.jsonl — at, mode, snapshot, head, branch, exit, seconds. A cached answer is
# not a run. The main checkout's, because a task worktree is gone at the merge; reef-cost.py rows counts from it.
MAINROOT=$(git worktree list --porcelain 2>/dev/null | sed -n '1s/^worktree //p'); [ -n "$MAINROOT" ] || MAINROOT=$ROOT
T0=$(date +%s)
log_run() {   # log_run <exit>
  mkdir -p "$MAINROOT/.reef/ci-local" 2>/dev/null || return 0
  printf '{"at": "%s", "mode": "%s", "snapshot": "%s", "head": "%s", "branch": "%s", "exit": %s, "seconds": %s}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$MODE" "$SNAP" "$(git rev-parse -q --verify HEAD 2>/dev/null || echo none)" \
    "$(git branch --show-current 2>/dev/null | tr -d '"\\')" "$1" "$(( $(date +%s) - T0 ))" >> "$MAINROOT/.reef/ci-local/runs.jsonl" 2>/dev/null || true
}
mark_green() {   # the marker keeps the green run's last lines, its log is kept beside it (0.7.1)
  [ -n "$SNAP" ] || return 0; mkdir -p .reef/ci-local; rm -f .reef/ci-local/gate-"$MODE"-*.ok .reef/ci-local/gate-"$MODE"-*.green.log
  L=".reef/ci-local/gate-$MODE.log"
  if [ -f "$L" ]; then cp "$L" ".reef/ci-local/gate-$MODE-$SNAP.green.log"; grep -v '^[[:space:]]*$' "$L" | tail -n 3 > ".reef/ci-local/gate-$MODE-$SNAP.ok"
  else : > ".reef/ci-local/gate-$MODE-$SNAP.ok"; fi
}
if [ "$FAILURES" -eq 1 ]; then
  mkdir -p .reef/ci-local
  LOG=.reef/ci-local/gate-$MODE.log
  MAXL=$(python3 -c "import json;print(int(json.load(open('.reef/config.json')).get('context',{}).get('failure_lines',60) or 60))" 2>/dev/null || echo 60)
  RC=0
  run_gate "$CMD" >"$LOG" 2>&1 || RC=$?    # set -e must not end the script before the block is printed
  log_run "$RC"
  [ "$RC" -eq 0 ] && mark_green
  echo "reef-gate ($MODE): exit $RC — full log: $LOG ($(wc -l <"$LOG" | tr -d ' ') lines)"
  # the verdict stands outside the block: a hung suite's log has hundreds of lines after its first FAIL marker, and
  # the TIMEOUT line python prints last would be cut by context.failure_lines
  [ "$RC" -eq 124 ] && echo "reef-gate ($MODE): TIMEOUT after ${TIMEOUT}s — the gate hung and its process group was killed (gates.timeout_s; a server a test spawned detached may still hold its port)"
  if [ "$RC" -ne 0 ]; then
    # the failing block: from the first failure marker to the end, capped — the exit code above is the verdict
    START=$(grep -n -m1 -E 'FAIL|Error|error\[|FAILED|panicked|not ok|AssertionError|Traceback|TIMEOUT' "$LOG" | cut -d: -f1)
    TOTAL_LINES=$(wc -l <"$LOG" | tr -d ' ')
    [ -n "$START" ] || START=$(( TOTAL_LINES - MAXL + 1 ))
    [ "$START" -lt 1 ] && START=1
    BLOCK=$(( TOTAL_LINES - START + 1 ))
    tail -n +"$START" "$LOG" | head -n "$MAXL"
    [ "$BLOCK" -gt "$MAXL" ] && echo "[... $((BLOCK - MAXL)) more lines in $LOG]"
  fi
  exit $RC
fi
# the gate is a shell command line, not an argv list — parse it as the human wrote it
# (unquoted `exec $CMD` would word-split and glob, mangling quoted args and operators).
RC=0
mkdir -p .reef/ci-local
run_gate "$CMD" ".reef/ci-local/gate-$MODE.log" || RC=$?
log_run "$RC"
[ "$RC" -eq 0 ] && mark_green
[ "$RC" -eq 124 ] && echo "reef-gate ($MODE): TIMEOUT after ${TIMEOUT}s — the gate hung and its process group was killed (gates.timeout_s; a server a test spawned detached may still hold its port)"
exit $RC
