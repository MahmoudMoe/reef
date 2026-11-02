#!/usr/bin/env python3
"""The next version in every manifest: X.Y.Z -> X.Y.(Z+1)-dev.1, X.Y.Z-dev.N -> X.Y.Z-dev.(N+1). Usage: bump-version.py [repo-root]
Claude Code re-installs a plugin only on a new version (2026-11-02: sessions ran a cache 84 commits behind main), so every
shipped change carries one; the release drops the -dev suffix by hand, with its CHANGELOG title."""
import json
import os
import re
import sys

root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pj, mj = (os.path.join(root, ".claude-plugin", n) for n in ("plugin.json", "marketplace.json"))
plugin, market = (json.load(open(p, encoding="utf-8")) for p in (pj, mj))
m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-dev\.(\d+))?", plugin["version"])
if not m:
    sys.exit(f"bump-version: {plugin['version']!r} is not X.Y.Z or X.Y.Z-dev.N")
x, y, z, n = m.groups()
new = f"{x}.{y}.{z}-dev.{int(n) + 1}" if n else f"{x}.{y}.{int(z) + 1}-dev.1"
plugin["version"] = market["metadata"]["version"] = market["plugins"][0]["version"] = new
for p, d in ((pj, plugin), (mj, market)):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
        f.write("\n")
print(new)
