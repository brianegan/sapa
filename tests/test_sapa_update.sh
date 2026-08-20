#!/bin/bash
# Tests for sapa-update. sapa-update finds the clone to update from its own path,
# so it can't be pointed at a scratch repo with a flag — the test builds a real
# throwaway clone (a copy of bin/ and skill/) wired to a local origin, and runs
# that clone's own bin/sapa-update. HOME and SAPA_BIN_DIR are sandboxed to a temp
# dir so the reinstall lands there, never touching the real ~/.local/bin or
# ~/.claude.
# Run: bash tests/test_sapa_update.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
clone_src="$(cd "$HERE/.." && pwd)"

pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }

root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

# Commit with a fixed identity so the test never depends on the runner's git config.
gc() { git -C "$1" -c user.email=t@t -c user.name=t commit -q "${@:2}"; }

# --- build an origin seeded with a copy of the sapa layout ---
# The seed is a working clone we push from; origin is the bare repo the throwaway
# clones track. Only bin/ and skill/ are committed, so the repo stays small.
origin="$root/origin.git"
seed="$root/seed"
mkdir -p "$seed"
cp -R "$clone_src/bin" "$seed/bin"
cp -R "$clone_src/skill" "$seed/skill"
git -c init.defaultBranch=main init -q "$seed"
git -C "$seed" add -A
gc "$seed" -m "seed"
git init --bare -q "$origin"
git -C "$seed" remote add origin "$origin"
git -C "$seed" push -q origin main
git -C "$origin" symbolic-ref HEAD refs/heads/main   # so clones check out main

# advance <file>: add a new commit to origin (via the seed) touching <file>.
advance() { echo x > "$seed/$1"; git -C "$seed" add -A; gc "$seed" -m "$1"; git -C "$seed" push -q origin main; }

# --- clean fast-forward pulls and then reinstalls ---
clone1="$root/clone1"
git clone -q "$origin" "$clone1"
advance FF_MARKER   # origin now one commit ahead of clone1
home1="$root/home1"; mkdir -p "$home1/.claude"
# Run from an unrelated directory to prove update acts on its own clone, not cwd.
out="$(cd "$root" && HOME="$home1" SAPA_BIN_DIR="$home1/.local/bin" SAPA_AGENTS=claude bash "$clone1/bin/sapa-update" 2>&1)"; rc=$?
if [ $rc -eq 0 ]; then ok "update exits 0 on a clean fast-forward"; else bad "update exits 0 on a clean fast-forward (rc=$rc, $out)"; fi
if [ -f "$clone1/FF_MARKER" ]; then ok "fast-forwards the clone to origin"; else bad "fast-forwards the clone to origin"; fi
if [ "$(readlink "$home1/.local/bin/sapa")" = "$clone1/bin/sapa" ]; then ok "reinstall relinks sapa from the updated clone"; else bad "reinstall relinks sapa (got $(readlink "$home1/.local/bin/sapa" 2>&1))"; fi
if [ -L "$home1/.claude/skills/sapa-plan" ]; then ok "reinstall relinks skills"; else bad "reinstall relinks skills"; fi

# --- a diverged clone refuses: nothing changes, reinstall is skipped ---
clone2="$root/clone2"
git clone -q "$origin" "$clone2"
echo local > "$clone2/LOCAL"; git -C "$clone2" add -A; gc "$clone2" -m "local"  # local-only commit
advance REMOTE_MARKER   # origin moves too → histories diverge, ff-only impossible
home2="$root/home2"; mkdir -p "$home2/.claude"
out="$(HOME="$home2" SAPA_BIN_DIR="$home2/.local/bin" SAPA_AGENTS=claude bash "$clone2/bin/sapa-update" 2>&1)"; rc=$?
if [ $rc -ne 0 ]; then ok "update fails on a non-fast-forward"; else bad "update fails on a non-fast-forward (rc=$rc, $out)"; fi
if [ ! -e "$clone2/REMOTE_MARKER" ]; then ok "a refused pull leaves the clone unchanged"; else bad "a refused pull leaves the clone unchanged"; fi
if [ ! -e "$home2/.local/bin/sapa" ]; then ok "a refused pull skips the reinstall"; else bad "a refused pull skips the reinstall"; fi
if grep -q "skipped the reinstall" <<<"$out"; then ok "reports skipping the reinstall"; else bad "reports skipping the reinstall ($out)"; fi

# --- the dispatcher routes `update` to this helper (probe via --help so it never
#     pulls), mirroring how test_sapa_dispatch.sh probes gate/watch/uninstall ---
out="$(bash "$clone_src/bin/sapa" update --help 2>&1)"; rc=$?
if [ $rc -eq 0 ] && grep -q "sapa update" <<<"$out"; then ok "dispatcher routes update to the helper"; else bad "dispatcher routes update to the helper (rc=$rc, $out)"; fi

# --- --help works and does not pull ---
out="$(bash "$clone_src/bin/sapa-update" --help 2>&1)"; rc=$?
if [ $rc -eq 0 ] && grep -q "Usage:" <<<"$out"; then ok "--help prints usage"; else bad "--help prints usage (rc=$rc)"; fi

# --- an unknown argument is rejected before any pull ---
out="$(bash "$clone_src/bin/sapa-update" bogus 2>&1)"; rc=$?
if [ $rc -eq 2 ] && grep -q "unknown argument" <<<"$out"; then ok "rejects an unknown argument"; else bad "rejects an unknown argument (rc=$rc, $out)"; fi

echo
echo "$pass/$((pass+fail)) passed"
[ "$fail" -eq 0 ]
