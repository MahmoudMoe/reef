#!/bin/sh
# Sabotage suite for templates/pre-commit, scripts/reef-gate.sh
# and scripts/reef-snapshot.sh. Every scenario that used to brick a commit, eat a
# stash, or silently pass must be shown green here — and every gate must be shown
# RED on the defect it exists to catch.
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
TMP=$(mktemp -d "${TMPDIR:-/tmp}/reef-hooks-test.XXXXXX")
trap 'rm -rf "$TMP"' EXIT
PASS=0; FAILED=0

t() { # t <name> <expected-rc> -> compares $? of the previous command group
  rc=$?
  if [ "$rc" -eq "$2" ]; then PASS=$((PASS+1)); echo "ok   $1"
  else FAILED=$((FAILED+1)); echo "FAIL $1 (rc=$rc wanted $2)"; fi
}

mkrepo() { # mkrepo <dir> <gate-cmd>
  rm -rf "$1"; mkdir -p "$1"; cd "$1"
  git init -q -b main
  git config user.email t@t; git config user.name t
  mkdir -p scripts .reef .githooks
  cp "$ROOT/scripts/reef-gate.sh" scripts/
  printf '{"gates": {"test": "%s"}}\n' "$2" > .reef/config.json
  cp -p "$ROOT/templates/pre-commit" .githooks/pre-commit
  chmod +x scripts/reef-gate.sh
  git config core.hooksPath .githooks
}

# the template itself must ship executable: a mode-preserving copy (cp -p, rsync -a)
# of a 644 template yields a hook git silently never runs
[ -x "$ROOT/templates/pre-commit" ]
t "templates/pre-commit ships with the executable bit" 0

# ---------- pre-commit ----------

mkrepo "$TMP/r1" "true"
( echo v1 > f.txt && git add . && git commit -qm c1 ) >/dev/null 2>&1
t "first-ever commits work (r1 bootstrap)" 0

cd "$TMP/r1"
echo v2 > f.txt; git add f.txt; echo v3-dirty > f.txt
git commit -qm c2 >/dev/null 2>&1
t "staged+unstaged SAME file: commit accepted" 0
[ "$(git show HEAD:f.txt)" = "v2" ]
t "  committed content is the INDEX (v2)" 0
[ "$(cat f.txt)" = "v3-dirty" ]
t "  worktree content restored (v3-dirty)" 0
git stash list | grep -q . ; [ $? -ne 0 ]
t "  no stash left behind" 0
git status --short | grep -q '^UU'; [ $? -ne 0 ]
t "  no conflict markers / unmerged state" 0

# foreign stash must survive untouched
git stash push -qm someone-elses >/dev/null 2>&1 || true
echo v4 > f.txt; git add f.txt; echo v5-dirty > f.txt
git commit -qm c3 >/dev/null 2>&1
t "commit with a FOREIGN stash on the stack: accepted" 0
git stash list | grep -q someone-elses
t "  foreign stash still exists (never popped)" 0
git stash drop -q >/dev/null 2>&1 || true

# clean tree: amend must work (the old EXIT-trap bug rejected it)
git checkout -q -- .
git commit -q --amend --no-edit >/dev/null 2>&1
t "clean tree: --amend accepted (EXIT trap preserves status)" 0

# red gate must reject and restore
mkrepo "$TMP/r2" "false"
( echo v1 > f.txt && git add . && GIT_DIR=.git git commit -qm c1 ) >/dev/null 2>&1
t "RED gate rejects the commit" 1
cd "$TMP/r2"
printf '{"gates": {"test": "true"}}\n' > .reef/config.json
git add .reef/config.json f.txt; git commit -qm c1 >/dev/null 2>&1
printf '{"gates": {"test": "false"}}\n' > .reef/config.json
git add .reef/config.json                 # the RED config must be IN THE INDEX (that is what the gate tests)
echo v2 > f.txt; git add f.txt; echo v3 > f.txt
git commit -qm c2 >/dev/null 2>&1
t "RED gate rejects with dirty worktree" 1
[ "$(cat f.txt)" = "v3" ]
t "  worktree restored after rejection" 0

# gate must test the INDEX: broken worktree, good index
mkrepo "$TMP/r3" "sh check.sh"
printf 'grep -q GOOD f.txt\n' > check.sh
echo GOOD > f.txt; git add . ; git commit -qm c1 >/dev/null 2>&1
echo GOOD-v2 > f.txt; git add f.txt
echo BROKEN > f.txt                      # worktree is broken; index is good
git commit -qm c2 >/dev/null 2>&1
t "gate saw the INDEX, not the broken worktree" 0
[ "$(cat f.txt)" = "BROKEN" ]
t "  broken worktree restored (still the user's problem, not ours)" 0

# merge state must survive
mkrepo "$TMP/r4" "true"
echo base > f.txt; git add .; git commit -qm base >/dev/null 2>&1
git checkout -qb side; echo side > f.txt; git commit -qam side >/dev/null 2>&1
git checkout -q main; echo main > f.txt; git commit -qam main >/dev/null 2>&1
git merge side >/dev/null 2>&1           # conflict
echo resolved > f.txt; git add f.txt
git commit -qm merge >/dev/null 2>&1
t "resolved merge commits cleanly" 0
[ "$(git rev-list --parents -1 HEAD | wc -w | tr -d ' ')" = "3" ]
t "  merge kept BOTH parents (MERGE_HEAD survived)" 0

# ---------- round-2 data-loss scenarios ----------

# intent-to-add: the index blob is EMPTY; the dance must be skipped, never truncate
mkrepo "$TMP/r5" "true"
echo v1 > f.txt; git add .; git commit -qm c1 >/dev/null 2>&1
echo v2 > f.txt; git add f.txt
printf 'line1\nBRAND NEW WORK\n' > new.txt
git add -N new.txt
git commit -qm c2 >/dev/null 2>&1
t "intent-to-add (git add -N): commit path completes" 0
grep -q 'BRAND NEW WORK' new.txt
t "  ita file content PRESERVED (was truncated to 0 bytes before)" 0

# diff.noprefix=true: the user's diff config must not be able to break the restore
mkrepo "$TMP/r6" "true"
git config diff.noprefix true
echo v1 > f.txt; git add .; git commit -qm c1 >/dev/null 2>&1
echo v2 > f.txt; git add f.txt; echo PRECIOUS-UNSTAGED > f.txt
git commit -qm c2 >/dev/null 2>&1
t "diff.noprefix=true: commit accepted" 0
[ "$(cat f.txt)" = "PRECIOUS-UNSTAGED" ]
t "  unstaged work restored despite noprefix (plumbing diff-files)" 0
[ "$(git show HEAD:f.txt)" = "v2" ]
t "  committed content is still the index" 0

# round-3: rename-paired ita (mv old new; git add -N new) — rename detection made the
# A-filter blind and the dance truncated the file
mkrepo "$TMP/r8" "true"
seq 1 100 > old.py; echo v1 > other.txt; git add .; git commit -qm c1 >/dev/null 2>&1
mv old.py new.py; git add -N new.py                 # deletion left unstaged -> git pairs as R
echo v2 > other.txt; git add other.txt; echo PRECIOUS > other.txt
git commit -qm c2 >/dev/null 2>&1
t "rename-paired ita: commit completes" 0
[ "$(wc -c < new.py | tr -d ' ')" != "0" ]
t "  ita'd rename target NOT truncated (plumbing sees A, not R)" 0
[ "$(cat other.txt)" = "PRECIOUS" ]
t "  other unstaged work restored" 0

# round-3: an unrelated `git add -N` decoy must NOT downgrade the INDEX gate
mkrepo "$TMP/r9" "grep -q good f.txt"
echo good > f.txt; git add .; git commit -qm c1 >/dev/null 2>&1
echo BROKEN > f.txt; git add f.txt; echo good > f.txt   # index BROKEN, worktree good
touch decoy.txt; git add -N decoy.txt
git commit -qm c2 >/dev/null 2>&1
t "ita decoy: broken INDEX still rejected (gate not downgraded to worktree)" 1
[ "$(cat f.txt)" = "good" ]
t "  worktree restored after the rejection" 0

# round-4: a gate that STAGES changes must not corrupt the index or commit untested
# unstaged work (the --3way fallback implied --index and merged worktree into the commit)
mkrepo "$TMP/r11" 'x'
printf 'sed -i.bak "s/^l4\$/FORMATTED/" f.txt; rm -f f.txt.bak; git add -u; exit 0\n' > scripts/gate.sh
printf '{"gates": {"test": "sh scripts/gate.sh"}}\n' > .reef/config.json
printf 'l1\nl2\nl3\nl4\nl5\n' > f.txt; git add .; git commit -qm c1 >/dev/null 2>&1
printf 'l1\nSTAGED\nl3\nl4\nl5\n' > f.txt; git add f.txt        # index: line2 = STAGED
printf 'l1\nSTAGED\nl3\nl4\nMY-UNSTAGED\n' > f.txt              # worktree: + line5 edit
git commit -qm c2 >/dev/null 2>&1
t "staging gate: commit path completes" 0
git show HEAD:f.txt > /dev/null 2>&1 && ! git show HEAD:f.txt | grep -q 'MY-UNSTAGED'
t "  UNSTAGED work NOT smuggled into the commit (index-backup, no --3way)" 0
git show HEAD:f.txt | grep -q 'STAGED'
t "  committed content is exactly what was staged" 0
git ls-files -u | grep -q .; [ $? -ne 0 ]
t "  index has no unmerged/conflict entries" 0
grep -q '<<<<<<<' f.txt; [ $? -ne 0 ]
t "  no conflict markers written into the file" 0
[ "$(tail -1 f.txt)" = "MY-UNSTAGED" ]
t "  the user's unstaged edit is back in the worktree" 0

# round-3: clean/smudge-filtered path skips the dance LOUDLY instead of corrupting
mkrepo "$TMP/r10" "true"
printf '*.dat filter=scrub\n' > .gitattributes
git config filter.scrub.clean 'tr a-z A-Z'
printf 'v1\n' > d.dat; git add .; git commit -qm c1 >/dev/null 2>&1
printf 'v2\n' > d.dat; git add d.dat; printf 'precious lower\n' > d.dat
OUT=$(git commit -m c2 2>&1); RC=$?
[ "$RC" = "0" ]
t "filtered path: commit accepted via loud in-place fallback" 0
echo "$OUT" | grep -q 'WORKTREE'
t "  fallback announced itself on stderr (never silent)" 0
[ "$(cat d.dat)" = "precious lower" ]
t "  unstaged filtered content untouched (no clean-filter corruption)" 0

# ---------- reef-gate.sh ----------
cd "$TMP"; mkdir -p g1; cd g1; git init -q -b main; git config user.email t@t; git config user.name t
mkdir -p .reef scripts; cp "$ROOT/scripts/reef-gate.sh" scripts/
printf '{"gates": {"test": ""}}\n' > .reef/config.json
sh scripts/reef-gate.sh >/dev/null 2>&1
t "gate: empty gates.test FAILS LOUDLY (no autodetect substitution)" 1
printf 'not json' > .reef/config.json
sh scripts/reef-gate.sh >/dev/null 2>&1
t "gate: unparseable config FAILS LOUDLY" 1
printf '{"gates": {"test": "echo \\"two  spaced   args\\" > got.txt"}}\n' > .reef/config.json
sh scripts/reef-gate.sh >/dev/null 2>&1 && grep -q 'two  spaced   args' got.txt
t "gate: quoted args survive (sh -c, no word-splitting)" 0
printf '{"gates": {"test": "false"}}\n' > .reef/config.json
CMD=true sh scripts/reef-gate.sh >/dev/null 2>&1
t "gate: inherited CMD env var cannot override the config" 1
cd "$TMP"
( cd / && sh "$TMP/g1/scripts/reef-gate.sh" ) >/dev/null 2>&1
t "gate: outside a git repo FAILS LOUDLY" 1

# ---------- reef-snapshot.sh ----------
mkrepo "$TMP/r7" "true"
cp "$ROOT/scripts/reef-snapshot.sh" scripts/; chmod +x scripts/reef-snapshot.sh
echo v1 > f.txt; git add .; git commit -qm c1 >/dev/null 2>&1
S1=$(sh scripts/reef-snapshot.sh); S2=$(sh scripts/reef-snapshot.sh)
[ "$S1" = "$S2" ]
t "snapshot: deterministic on an unchanged tree" 0
printf 'x' >> f.txt                       # same size class, content-only edit
S3=$(sh scripts/reef-snapshot.sh)
[ "$S1" != "$S3" ]
t "snapshot: sees a tracked content edit" 0
git checkout -q -- .
echo sneaky > untracked.txt
S4=$(sh scripts/reef-snapshot.sh)
[ "$S1" != "$S4" ]
t "snapshot: sees a NEW untracked file" 0
echo sneakier > untracked.txt
S5=$(sh scripts/reef-snapshot.sh)
[ "$S4" != "$S5" ]
t "snapshot: sees an EDIT to an untracked file (porcelain was blind to this)" 0

echo
echo "hooks suite: $PASS passed, $FAILED failed"
[ "$FAILED" -eq 0 ]
