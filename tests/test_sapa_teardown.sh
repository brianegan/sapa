#!/bin/bash
# Tests for sapa-teardown against a real bare-layout repo in a temp dir.
# Run: bash tests/test_sapa_teardown.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TEARDOWN="$HERE/../bin/sapa-teardown"

pass=0; fail=0
ok()   { echo "ok   $1"; pass=$((pass+1)); }
bad()  { echo "FAIL $1"; fail=$((fail+1)); }

# Build a bare-layout project: root/.bare + a main worktree + a feature worktree.
root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT
proj="$root/proj"
mkdir -p "$proj"
git init --bare "$proj/.bare" -q
printf 'gitdir: ./.bare\n' > "$proj/.git"
git -C "$proj" -c init.defaultBranch=main worktree add -q "$proj/main" -b main 2>/dev/null \
  || git -C "$proj/.bare" worktree add -q "$proj/main" -b main
( cd "$proj/main" && git -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -q --allow-empty -m init )
git -C "$proj/main" worktree add -q "$proj/feature" -b feature

# --- clean worktree is removed, along with its branch ---
out="$(bash "$TEARDOWN" "$proj/feature" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ ! -d "$proj/feature" ]; then ok "removes clean worktree"; else bad "removes clean worktree ($out)"; fi
if ! git -C "$proj/main" branch --list feature | grep -q feature; then ok "deletes local branch"; else bad "deletes local branch"; fi

# --- dirty worktree is refused ---
git -C "$proj/main" worktree add -q "$proj/dirty" -b dirty
printf 'wip\n' > "$proj/dirty/scratch.txt"
out="$(bash "$TEARDOWN" "$proj/dirty" 2>&1)"; rc=$?
if [ $rc -eq 3 ] && [ -d "$proj/dirty" ]; then ok "refuses dirty worktree"; else bad "refuses dirty worktree (rc=$rc, $out)"; fi

# --- --force removes a dirty worktree ---
out="$(bash "$TEARDOWN" --force "$proj/dirty" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ ! -d "$proj/dirty" ]; then ok "force removes dirty worktree"; else bad "force removes dirty worktree ($out)"; fi

# --- works when invoked from inside the target worktree ---
git -C "$proj/main" worktree add -q "$proj/inside" -b inside
out="$(cd "$proj/inside" && bash "$TEARDOWN" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ ! -d "$proj/inside" ]; then ok "removes cwd worktree from within"; else bad "removes cwd worktree from within (rc=$rc, $out)"; fi

# --- refuses to remove the project root ---
out="$(bash "$TEARDOWN" "$proj/main" 2>&1)"; rc=$?
# main is a worktree, not the root; the root itself has no branch checkout.
out="$(bash "$TEARDOWN" "$proj" 2>&1)"; rc=$?
if [ $rc -ne 0 ] && [ -d "$proj" ]; then ok "refuses project root"; else bad "refuses project root (rc=$rc)"; fi

echo
echo "$pass/$((pass+fail)) passed"
[ "$fail" -eq 0 ]
