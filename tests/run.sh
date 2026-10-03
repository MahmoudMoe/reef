#!/bin/sh
# Reef's own gate: python sabotage suites + shell sabotage suites.
# Every gate in this plugin has a test here that shows it going RED on the
# defect it exists to catch — a gate never observed failing is decoration.
set -e
cd "$(dirname "$0")/.."
# Python suites (unittest discover picks up every tests/test_*.py):
#   test_guard.py       the PreToolUse guard: bypass spellings, dispatch caps, odometer, stamp
#   test_attempt.py     reef-attempt: the cap as data, failure signatures
#   test_plan_check.py  reef-plan-check: schema, graph, stamp, tier
#   test_graph.py       reef-graph: ready set, resources, parallel cap, the race, worktrees, locks
#   test_adversarial.py reef-adversarial + the guard's plan-pass check; reef-claims (check, claims-only)
#   test_contracts.py   the prose and the shipped defaults still say what the code expects
#   test_init.py        reef-init: idempotent, never overwrites, one home per fact, release-only CI
#   test_tier_queue.py  reef-tier (a tier only gets heavier); reef-queue (derived status, ready rows, check, ADR numbering)
# Shell suites: tests/test_hooks.sh (pre-commit, gate, snapshot), tests/test_ci_local.sh (reef-ci-local)
# One suite: python3 -m unittest tests.test_graph -v
echo "== python suites (guard / attempt / plan-check / graph) =="
python3 -m unittest discover -s tests -q
echo "== shell suite (pre-commit / gate / snapshot) =="
sh tests/test_hooks.sh
echo "== shell suite (reef-ci-local) =="
sh tests/test_ci_local.sh
echo "ALL REEF TESTS PASSED"
