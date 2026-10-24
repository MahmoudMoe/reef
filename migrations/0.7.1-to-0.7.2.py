#!/usr/bin/env python3
"""0.7.1 -> 0.7.2: nothing to change in a project's files. reef-init adds the keys 0.7.2 ships (`assess.exclude`, `assess.large_file`,
`structure.new_file_lines`, `review.security_per_item`), additive, never a value of yours; this step exists so the migration chain
has no gap and `.reef/version` reads 0.7.2. The new gates (boundaries, sizes, raw-sql, the semgrep release gate) are proposals the
owner adds to `.reef/config.json`. Idempotent; exit 0."""
import sys


def main(root, plugin):
    print("0.7.1-to-0.7.2: nothing to change; .reef/version becomes 0.7.2")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]) if len(sys.argv) >= 3 else 2)
