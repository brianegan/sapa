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

# Finds a non-dotfile sapa.yaml when it is the only config in an ancestor dir.
mkdir -p "$root/plain/feature/deep"
printf 'base: main\n' > "$root/plain/sapa.yaml"
found="$("$CONFIG" --start "$root/plain/feature/deep")"
check "finds sapa.yaml (no dot)" "$root/plain/sapa.yaml" "$found"

# Prefers .sapa.yaml over sapa.yaml in the same dir.
mkdir -p "$root/both/feature"
printf 'base: dotted\n' > "$root/both/.sapa.yaml"
printf 'base: plain\n' > "$root/both/sapa.yaml"
found="$("$CONFIG" --start "$root/both/feature")"
check "prefers .sapa.yaml in same dir" "$root/both/.sapa.yaml" "$found"

# A closer sapa.yaml beats a farther .sapa.yaml (proximity over dot).
mkdir -p "$root/near/child/deep"
printf 'base: far\n' > "$root/near/.sapa.yaml"
printf 'base: near\n' > "$root/near/child/sapa.yaml"
found="$("$CONFIG" --start "$root/near/child/deep")"
check "closer sapa.yaml beats farther .sapa.yaml" "$root/near/child/sapa.yaml" "$found"

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
