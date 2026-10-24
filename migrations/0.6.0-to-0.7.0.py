#!/usr/bin/env python3
"""0.6.0 -> 0.7.0: nothing to change in a project's files. reef-init adds the keys 0.7 ships (additive, never a value of
yours); this step exists so the migration chain has no gap and `.reef/version` reads 0.7.0. Idempotent; exit 0."""
import sys


def main(root, plugin):
    print("0.6.0-to-0.7.0: nothing to change; .reef/version becomes 0.7.0")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]) if len(sys.argv) >= 3 else 2)
