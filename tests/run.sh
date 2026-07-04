#!/bin/bash
# Run the whole sapa test suite. The single source of truth for "run the tests",
# used by CI and locally. Runs every test file even if an earlier one fails, so
# you see the full picture, then exits non-zero if any failed.
# Run: bash tests/run.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

fail=0
run() {
  echo "===== $1 ====="
  "${@:2}" || fail=1
  echo
}

run test_sapa_section.py   python3 "$HERE/test_sapa_section.py"
run test_sapa_config.sh    bash    "$HERE/test_sapa_config.sh"
run test_sapa_bootstrap.sh bash    "$HERE/test_sapa_bootstrap.sh"
run test_sapa_start.sh     bash    "$HERE/test_sapa_start.sh"
run test_sapa_teardown.sh  bash    "$HERE/test_sapa_teardown.sh"

if [ "$fail" -ne 0 ]; then
  echo "FAIL: one or more test files failed"
else
  echo "OK: all test files passed"
fi
exit "$fail"
