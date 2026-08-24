#!/bin/sh
# Reef's own gate: python sabotage suites + shell sabotage suites.
# Every gate in this plugin has a test here that shows it going RED on the
# defect it exists to catch — a gate never observed failing is decoration.
set -e
cd "$(dirname "$0")/.."
echo "== python suites (guard / attempt / plan-check) =="
python3 -m unittest discover -s tests -q
echo "== shell suite (pre-commit / gate / snapshot) =="
sh tests/test_hooks.sh
echo "ALL REEF TESTS PASSED"
