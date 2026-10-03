#!/bin/sh
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
set -- .
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
