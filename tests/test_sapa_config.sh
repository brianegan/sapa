#!/bin/bash
# Tests for sapa-config, the walk-up config locator.
# Run: bash tests/test_sapa_config.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$HERE/../bin/sapa-config"

pass=0
fail=0
check() {
  local name="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    echo "ok   $name"
    pass=$((pass + 1))
  else
    echo "FAIL $name: expected [$expected] got [$actual]"
    fail=$((fail + 1))
  fi
}

root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

# Layout: root/.sapa.yaml and a nested worktree with no config of its own.
mkdir -p "$root/proj/feature/deep"
printf 'base: main\n' > "$root/proj/.sapa.yaml"

# Found by walking up several levels.
found="$("$CONFIG" --start "$root/proj/feature/deep")"
check "walks up to find config" "$root/proj/.sapa.yaml" "$found"

# Found when sitting directly in the config's directory.
found="$("$CONFIG" --start "$root/proj")"
check "finds config in current dir" "$root/proj/.sapa.yaml" "$found"

# Prints contents with -p.
contents="$("$CONFIG" -p --start "$root/proj/feature")"
check "prints contents with -p" "base: main" "$contents"

# Exits non-zero when no config exists anywhere up the tree.
mkdir -p "$root/orphan"
if "$CONFIG" --start "$root/orphan" >/dev/null 2>&1; then
  # It may still find a real ~/.sapa.yaml on a dev machine; guard on tmp only.
  echo "FAIL missing config exits non-zero: unexpected success"
  fail=$((fail + 1))
else
  echo "ok   missing config exits non-zero"
  pass=$((pass + 1))
fi

echo
echo "$pass/$((pass + fail)) passed"
[ "$fail" -eq 0 ]
