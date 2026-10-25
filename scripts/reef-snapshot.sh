#!/bin/sh
# CLASS: code
# Reef tree snapshot: one CONTENT hash over HEAD + index + worktree (untracked included).
# `git status --porcelain` cannot see an edit that keeps a file's status letter the same;
# tree objects hash content, so ANY byte changed by a "read-only" agent changes this value.
# reef-task records it before and after the verifier runs; a difference = automatic FAIL.
# Nested worktrees (another agent's checkout under this repo) are EXCLUDED: `git add -A`
# records them as gitlinks, so another agent's commit there would read as our change.
set -e
ROOT=$(git rev-parse --show-toplevel) || { echo "reef-snapshot: not a git repository" >&2; exit 1; }
cd "$ROOT"
ROOTP=$(pwd -P)
GITDIR=$(git rev-parse --git-dir)
TMPIDX=$(mktemp "${TMPDIR:-/tmp}/reef-snap.XXXXXX")
trap 'rm -f "$TMPIDX"' EXIT
if [ -f "$GITDIR/index" ]; then cp "$GITDIR/index" "$TMPIDX"; else : >"$TMPIDX"; fi
# racy git: an entry whose file was rewritten in the same second as the index, at the same size, reads as unchanged by
# stat alone. Dating the scratch index to the epoch makes git re-hash every entry's CONTENT (2026-10-18, CI: a gate
# cache test edited a file within the second and the snapshot did not move)
touch -t 198001010000 "$TMPIDX"   # not the epoch: a zero index timestamp switches git's racy check OFF
set -- .
# v3 phase 2: the gate's own artifacts never move the hash they are keyed by — its logs and markers (.reef/ci-local/) and
# its evidence (.reef/evidence/<snapshot>.json) are left out whether or not the project ignores them
set -- "$@" ":(exclude).reef/ci-local" ":(exclude).reef/evidence" ":(exclude)scripts/__pycache__"   # and Reef's own byte-code
while IFS= read -r wt; do
  [ -n "$wt" ] || continue
  w=$(cd "$wt" 2>/dev/null && pwd -P) || continue   # macOS: /var -> /private/var
  case "$w" in
    "$ROOTP"/*) set -- "$@" ":(exclude,literal)${w#"$ROOTP"/}" ;;
  esac
done <<EOF_WT
$(git worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p')
EOF_WT
GIT_INDEX_FILE="$TMPIDX" git add -A -- "$@" 2>/dev/null || true
{
  git rev-parse -q --verify HEAD || echo no-head
  git write-tree                          # the real index (staged state), read-only
  GIT_INDEX_FILE="$TMPIDX" git write-tree # worktree incl. untracked, via a scratch index
} | git hash-object --stdin
