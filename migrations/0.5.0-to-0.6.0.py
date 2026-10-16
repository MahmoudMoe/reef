#!/usr/bin/env python3
"""0.5.0 -> 0.6.0: ADDITIVE keys only. Idempotent. Exit 0 = applied or nothing to do, 1 = refused, 2 = usage.
Adds, when absent: the tier table (tiers.<tier>.{roles,effort,paths}), paths.features (only when the project uses
the 0.6 tree), writing.* caps, caps.{feature_tokens,batch_tokens,context_tokens,context_warn}, loop.*, context.*,
converge.*; keeps gates.test as the alias it is; writes .reef/version; offers --layout. Never changes a value."""
import json
import os
import sys


def main(root, plugin):
    cfg_path = os.path.join(root, ".reef", "config.json")
    if not os.path.isfile(cfg_path):
        print("0.5.0-to-0.6.0: no .reef/config.json — nothing to migrate (run /reef-init)")
        return 0
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    with open(os.path.join(plugin, "templates", "config.json"), encoding="utf-8") as f:
        tpl = json.load(f)
    before = json.dumps(cfg, sort_keys=True)

    def add(dst, src):
        for k, v in src.items():
            if k not in dst:
                dst[k] = v
            elif isinstance(dst[k], dict) and isinstance(v, dict):
                add(dst[k], v)
    for section in ("tiers", "writing", "loop", "context", "converge"):
        cfg.setdefault(section, {})
        add(cfg[section], tpl.get(section, {}))
    cfg.setdefault("caps", {})
    for k in ("feature_tokens", "batch_tokens", "context_tokens", "context_warn"):
        cfg["caps"].setdefault(k, 0)
    cfg.setdefault("paths", {})
    for k, v in tpl.get("paths", {}).items():
        cfg["paths"].setdefault(k, v)   # the 0.5 locations are the template's defaults for these keys
    changed = json.dumps(cfg, sort_keys=True) != before
    if changed:
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
    vpath = os.path.join(root, ".reef", "version")
    wrote_v = False
    if not os.path.isfile(vpath):
        with open(vpath, "w", encoding="utf-8") as f:
            f.write("0.6.0\n")
        wrote_v = True
    if changed or wrote_v:
        print(f"0.5.0-to-0.6.0: {'keys added' if changed else 'config unchanged'}{', .reef/version written' if wrote_v else ''}; "
              "gates.test kept as the alias of gates.full. The flat layout (docs/, tasks/) keeps working; "
              "`python3 scripts/reef-migrate --layout` moves it to the one tree in one reviewed commit when you want it.")
    else:
        print("0.5.0-to-0.6.0: nothing to do")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ".", sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
