# Guard profile — 2026-10-16

`python3 scripts/reef-guard-profile.py --runs 30` on linux, python 3.13.16; wall time of one `reef-guard.py` invocation per matcher over the recorded payloads. Rule: `timeout` ≥ 5 × p95, floor 10 s.

| matcher | p50 (ms) | p95 (ms) | max (ms) | timeout (s) |
|---|---|---|---|---|
| `Bash` | 60 | 127 | 160 | 10 |
| `Task|Agent` | 54 | 65 | 72 | 10 |
| `Edit|Write|MultiEdit` | 59 | 78 | 81 | 10 |
| `Stop` | 53 | 59 | 72 | 10 |
