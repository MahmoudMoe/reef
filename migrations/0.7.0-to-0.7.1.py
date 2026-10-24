#!/usr/bin/env python3
"""0.7.0 -> 0.7.1: nothing to change in a project's files. reef-init adds the keys 0.7.1 ships (queue.home stays `file`
for a project that has a file queue; queue.batch_max), additive, never a value of yours; this step exists so the
migration chain has no gap and `.reef/version` reads 0.7.1. Moving the queue to issues is the owner's
`reef-queue.py migrate-to-issues`. Idempotent; exit 0."""
import sys


def main(root, plugin):
    print("0.7.0-to-0.7.1: nothing to change; .reef/version becomes 0.7.1")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]) if len(sys.argv) >= 3 else 2)
