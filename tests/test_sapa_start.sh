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

# --- Jira keys: kept in the branch, lower-cased prefix ---
check "jira key kept in branch" "gp-1-jira-support" \
  "$(bash "$START" gp-1 --title 'JIRA support' --print)"

check "upper-case key is lower-cased" "gp-1-jira-support" \
  "$(bash "$START" GP-1 --title 'JIRA support' --print)"

check "bare jira key when title empty" "gp-7" \
  "$(bash "$START" gp-7 --title '' --print)"

# --- bare number expands via config tracker+project ---
cfgdir="$(mktemp -d)"
trap 'rm -rf "$cfgdir"' EXIT
printf 'tracker: jira\njira:\n  project: GP\n' > "$cfgdir/.sapa.yaml"
check "bare number expands to project key under tracker: jira" "gp-5-do-a-thing" \
  "$(cd "$cfgdir" && bash "$START" 5 --title 'Do a thing' --print)"
check "explicit key still works under tracker: jira" "gp-9-other" \
  "$(cd "$cfgdir" && bash "$START" gp-9 --title 'Other' --print)"

# A checked-in Jira config in the primary worktree also applies when start is
# invoked from the bootstrapped repository's bare container.
bare_root="$cfgdir/bare-layout"
mkdir -p "$bare_root"
git init --bare -q "$bare_root/.bare"
printf 'gitdir: ./.bare\n' > "$bare_root/.git"
git --git-dir="$bare_root/.bare" symbolic-ref HEAD refs/heads/trunk
git --git-dir="$bare_root/.bare" worktree add --orphan -q -b trunk "$bare_root/trunk"
printf 'tracker: jira\njira:\n  project: GP\n' > "$bare_root/trunk/.sapa.yaml"
from_bare="$(cd "$bare_root" && bash "$START" 50 --title 'Ticket name' --print)"
from_worktree="$(cd "$bare_root/trunk" && bash "$START" 50 --title 'Ticket name' --print)"
check "bare root uses Jira config from primary worktree" \
  "gp-50-ticket-name" "$from_bare"
check "bare root and primary worktree derive the same branch" \
  "$from_worktree" "$from_bare"

# Without a jira tracker, a bare number stays a GitHub number (no expansion).
ghdir="$(mktemp -d)"
printf 'base: main\n' > "$ghdir/.sapa.yaml"
check "bare number stays github without tracker: jira" "5-do-a-thing" \
  "$(cd "$ghdir" && bash "$START" 5 --title 'Do a thing' --print)"
rm -rf "$ghdir"

echo
echo "$pass/$((pass+fail)) passed"
[ "$fail" -eq 0 ]
