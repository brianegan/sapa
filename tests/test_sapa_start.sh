#!/bin/bash
# Tests for sapa-start's branch-name derivation (the deterministic part).
# The gh lookup and worktree hand-off are integration and not exercised here;
# --title and --print keep these offline.
# Run: bash tests/test_sapa_start.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
START="$HERE/../bin/sapa-start"

pass=0; fail=0
check() {
  if [ "$2" = "$3" ]; then echo "ok   $1"; pass=$((pass+1))
  else echo "FAIL $1: expected [$2] got [$3]"; fail=$((fail+1)); fi
}
check_fails() {
  if "$@" >/dev/null 2>&1; then echo "FAIL expected non-zero: $*"; fail=$((fail+1))
  else echo "ok   rejects: $*"; pass=$((pass+1)); fi
}

check "slugifies a title" "42-add-the-widget" \
  "$(bash "$START" 42 --title 'Add the Widget!' --print)"

check "strips leading hash" "7-fix-bug" \
  "$(bash "$START" '#7' --title 'Fix bug' --print)"

check "collapses punctuation and spaces" "3-a-b-c" \
  "$(bash "$START" 3 --title '  a...b   c  ' --print)"

check "bare number when title empty" "9" \
  "$(bash "$START" 9 --title '' --print)"

check "bare number when title is all punctuation" "5" \
  "$(bash "$START" 5 --title '!!!' --print)"

check_fails bash "$START" not-a-number --print
check_fails bash "$START" --print   # missing issue number

echo
echo "$pass/$((pass+fail)) passed"
[ "$fail" -eq 0 ]
