#!/usr/bin/env python3
"""0.7.2 -> 0.7.3: nothing to change in a project's files. reef-init adds what 0.7.3 ships (workflow v3: `loop.rows_in_flight`,
the setup proof's record under `.reef/ci-local/`, the factory's workflow), additive, never a value of yours; this step exists so
the migration chain has no gap and `.reef/version` reads 0.7.3. Idempotent; exit 0."""
import sys


def main(root, plugin):
    print("0.7.2-to-0.7.3: nothing to change; .reef/version becomes 0.7.3")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]) if len(sys.argv) >= 3 else 2)
