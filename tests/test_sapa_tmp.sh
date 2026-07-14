#!/bin/bash
# Tests for sapa-tmp, the per-stream scratch-directory printer.
# Run: bash tests/test_sapa_tmp.sh
#
# The whole point of sapa-tmp is that two streams never share a scratch path, so
# the assertions center on: a stream gets a directory keyed by its branch, that
# path is stable across calls (skills recompute it in separate command blocks),
# distinct streams get distinct directories, the SAPA_TMP_DIR/TMPDIR base is
# honored, and a run outside a sapa worktree still yields a usable directory.
#
# A fixture "stream" is just <root>/proj/.bare plus a <root>/proj/<branch>/
# worktree dir — enough for the `.bare` walk-up; the dirs need not be real git
# repos (the branch is read straight off the worktree basename).

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="$HERE/../bin/sapa-tmp"

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
ok() { echo "ok   $1"; pass=$((pass + 1)); }
bad() { echo "FAIL $1"; fail=$((fail + 1)); }

root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

# A base for scratch dirs, redirected so nothing touches a real $TMPDIR/sapa.
base="$root/scratch"

make_stream() {  # make_stream <name> <branch> ; echoes the worktree path
  local proj="$root/$1"
  mkdir -p "$proj/.bare" "$proj/$2"
  echo "$proj/$2"
}

# --- in a stream: keyed by the branch, directory created ---
wt="$(make_stream s1 42-a-feature)"
got="$(SAPA_TMP_DIR="$base" "$TMP" --start "$wt")"
check "in-stream path is base/<branch>" "$base/42-a-feature" "$got"
[ -d "$got" ] && ok "in-stream directory is created" || bad "in-stream directory missing"

# --- stable across calls: the skills recompute it each command block ---
again="$(SAPA_TMP_DIR="$base" "$TMP" --start "$wt")"
check "stable across calls" "$got" "$again"

# --- resolves from a nested subdir of the worktree, still to the branch ---
mkdir -p "$wt/src/deep"
nested="$(SAPA_TMP_DIR="$base" "$TMP" --start "$wt/src/deep")"
check "resolves from a nested subdir" "$base/42-a-feature" "$nested"

# --- distinct streams get distinct directories ---
wt2="$(make_stream s2 99-other-thing)"
got2="$(SAPA_TMP_DIR="$base" "$TMP" --start "$wt2")"
if [ "$got2" != "$got" ]; then
  ok "distinct streams get distinct dirs"
else
  bad "distinct streams collided: both [$got]"
fi

# --- SAPA_TMP_DIR wins over TMPDIR ---
got3="$(SAPA_TMP_DIR="$base" TMPDIR="$root/ignored" "$TMP" --start "$wt")"
check "SAPA_TMP_DIR overrides TMPDIR" "$base/42-a-feature" "$got3"

# --- falls back to TMPDIR/sapa when SAPA_TMP_DIR is unset ---
got4="$(env -u SAPA_TMP_DIR TMPDIR="$root/td" "$TMP" --start "$wt")"
check "defaults to TMPDIR/sapa" "$root/td/sapa/42-a-feature" "$got4"

# --- a trailing slash on the base (macOS $TMPDIR has one) does not double up ---
got5="$(env -u SAPA_TMP_DIR TMPDIR="$root/td/" "$TMP" --start "$wt")"
check "tolerates a trailing slash in the base" "$root/td/sapa/42-a-feature" "$got5"

# --- a nonexistent --start is a hard error, not a silent wrong dir ---
# (regression: an unresolvable start once fell through to the cwd's stream, the
# exact collision the tool exists to prevent.)
if SAPA_TMP_DIR="$base" "$TMP" --start "$root/does-not-exist" >/dev/null 2>&1; then
  bad "nonexistent --start should exit non-zero"
else
  ok "nonexistent --start is a hard error"
fi

# --- --start with no directory is a clear error, not a silent set -e death ---
if SAPA_TMP_DIR="$base" "$TMP" --start >/dev/null 2>&1; then
  bad "--start with no value should exit non-zero"
else
  ok "--start with no value errors out"
fi

# --- outside a stream: still exits 0 and yields a real directory ---
lonely="$root/lonely"      # no .bare anywhere above it
mkdir -p "$lonely"
if out="$(SAPA_TMP_DIR="$base" "$TMP" --start "$lonely" 2>/dev/null)"; then
  if [ -n "$out" ] && [ -d "$out" ]; then
    ok "out-of-stream yields a usable directory"
  else
    bad "out-of-stream gave no usable dir: [$out]"
  fi
else
  bad "out-of-stream exited non-zero"
fi

echo
echo "$pass/$((pass + fail)) passed"
[ "$fail" -eq 0 ]
