#!/bin/bash
# Tests for sapa-bootstrap. The `init` path and the clone path against a local
# source repo are both offline and exercised here; cloning a real remote is not.
# Run: bash tests/test_sapa_bootstrap.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BOOTSTRAP="$HERE/../bin/sapa-bootstrap"

pass=0; fail=0
ok()   { echo "ok   $1"; pass=$((pass+1)); }
bad()  { echo "FAIL $1"; fail=$((fail+1)); }

root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

# --- init builds the bare + main worktree layout ---
out="$(cd "$root" && bash "$BOOTSTRAP" init proj 2>&1)"; rc=$?
proj="$root/proj"
if [ $rc -eq 0 ]; then ok "init exits 0"; else bad "init exits 0 (rc=$rc, $out)"; fi
if [ -d "$proj/.bare" ]; then ok "creates .bare"; else bad "creates .bare"; fi
if [ -d "$proj/main" ]; then ok "creates main worktree"; else bad "creates main worktree"; fi
if grep -qx 'gitdir: ./.bare' "$proj/.git" 2>/dev/null; then ok "writes .git pointer"; else bad "writes .git pointer"; fi

# --- the main worktree is a real checkout on branch main (unborn until first commit) ---
branch="$(git -C "$proj/main" symbolic-ref --short HEAD 2>/dev/null)"
if [ "$branch" = "main" ]; then ok "main worktree on branch main"; else bad "main worktree on branch main (got '$branch')"; fi

# --- init with no name is a usage error ---
out="$(cd "$root" && bash "$BOOTSTRAP" init 2>&1)"; rc=$?
if [ $rc -eq 2 ]; then ok "init without a name errors (exit 2)"; else bad "init without a name errors (rc=$rc)"; fi

# --- clone from a local source repo lands the worktree on the source's branch ---
# Source lives in its own dir so its basename ('app') doesn't collide with the
# clone destination ($root/app). Its default branch is 'master' to exercise the
# fallback path.
mkdir -p "$root/sources"
src="$root/sources/app"
git init -q -b master "$src"
git -C "$src" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -q --allow-empty -m init
out="$(cd "$root" && bash "$BOOTSTRAP" "$src" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ -d "$root/app/master" ]; then ok "clone checks out the master worktree"; else bad "clone checks out the master worktree (rc=$rc, $out)"; fi
# The success message must name the branch it actually created, not always 'main'.
if printf '%s' "$out" | grep -q "app/master"; then ok "reports the branch it created"; else bad "reports the branch it created ($out)"; fi

# --- clone a main-default source: the common path picks main, not the fallback ---
src2="$root/sources/web"
git init -q -b main "$src2"
git -C "$src2" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -q --allow-empty -m init
out="$(cd "$root" && bash "$BOOTSTRAP" "$src2" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ -d "$root/web/main" ]; then ok "clone checks out the main worktree"; else bad "clone checks out the main worktree (rc=$rc, $out)"; fi

# --- no argument is a usage error ---
out="$(cd "$root" && bash "$BOOTSTRAP" 2>&1)"; rc=$?
if [ $rc -eq 2 ]; then ok "no argument errors (exit 2)"; else bad "no argument errors (rc=$rc)"; fi

echo
echo "$pass/$((pass+fail)) passed"
[ "$fail" -eq 0 ]
