#!/bin/sh
# Reef tree snapshot: one CONTENT hash over HEAD + index + worktree (untracked included).
# `git status --porcelain` cannot see an edit that keeps a file's status letter the same;
# tree objects hash content, so ANY byte changed by a "read-only" agent changes this value.
# reef-task records it before and after the verifier runs; a difference = automatic FAIL.
set -e
ROOT=$(git rev-parse --show-toplevel) || { echo "reef-snapshot: not a git repository" >&2; exit 1; }
cd "$ROOT"
GITDIR=$(git rev-parse --git-dir)
TMPIDX=$(mktemp "${TMPDIR:-/tmp}/reef-snap.XXXXXX")
trap 'rm -f "$TMPIDX"' EXIT
if [ -f "$GITDIR/index" ]; then cp "$GITDIR/index" "$TMPIDX"; else : >"$TMPIDX"; fi
GIT_INDEX_FILE="$TMPIDX" git add -A 2>/dev/null || true
{
  git rev-parse -q --verify HEAD || echo no-head
  git write-tree                          # the real index (staged state), read-only
  GIT_INDEX_FILE="$TMPIDX" git write-tree # worktree incl. untracked, via a scratch index
} | git hash-object --stdin
