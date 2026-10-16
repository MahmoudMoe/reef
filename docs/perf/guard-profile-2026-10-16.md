# Guard profile — 2026-10-16

`python3 scripts/reef-guard-profile.py --runs 30` on linux, python 3.13.16; wall time of one `reef-guard.py` invocation per matcher over the recorded payloads. Rule: `timeout` ≥ 5 × p95, floor 10 s.

| matcher | p50 (ms) | p95 (ms) | max (ms) | timeout (s) |
|---|---|---|---|---|
| `Bash` | 66 | 126 | 134 | 10 |
| `Task|Agent` | 56 | 83 | 83 | 10 |
| `Edit|Write|MultiEdit` | 56 | 77 | 81 | 10 |
| `Stop` | 62 | 78 | 80 | 10 |
