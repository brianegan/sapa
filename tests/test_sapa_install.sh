#!/bin/bash
# Tests for sapa-install. Everything is sandboxed by pointing HOME at a temp dir
# so SAPA_BIN_DIR and the agent skills dirs land there — the real ~/.local/bin
# and ~/.claude are never touched.
# Run: bash tests/test_sapa_install.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
INSTALL="$HERE/../bin/sapa-install"

pass=0; fail=0
ok()   { echo "ok   $1"; pass=$((pass+1)); }
bad()  { echo "FAIL $1"; fail=$((fail+1)); }

root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

# A sandbox HOME with both agent homes present so auto-detect targets each.
home="$root/home"
mkdir -p "$home/.claude" "$home/.codex"
bin_dir="$home/.local/bin"

# --- install links helpers and skills into the sandbox ---
out="$(HOME="$home" bash "$INSTALL" 2>&1)"; rc=$?
if [ $rc -eq 0 ]; then ok "install exits 0"; else bad "install exits 0 (rc=$rc, $out)"; fi
if [ -L "$bin_dir/sapa-config" ]; then ok "links a helper into ~/.local/bin"; else bad "links a helper into ~/.local/bin"; fi
if [ -L "$bin_dir/sapa-install" ]; then ok "links itself so uninstall stays on PATH"; else bad "links itself"; fi
if [ -L "$home/.claude/skills/sapa-plan" ]; then ok "links a skill into claude"; else bad "links a skill into claude"; fi
if [ -L "$home/.codex/skills/sapa-plan" ]; then ok "links a skill into codex"; else bad "links a skill into codex"; fi

# Targets point back into this clone, not somewhere arbitrary.
if readlink "$bin_dir/sapa-config" | grep -q '/bin/sapa-config$'; then ok "helper target points into the clone"; else bad "helper target points into the clone"; fi
if readlink "$home/.claude/skills/sapa-plan" | grep -q '/skill/sapa-plan$'; then ok "skill target points into the clone"; else bad "skill target points into the clone"; fi

# --- re-running is idempotent ---
out="$(HOME="$home" bash "$INSTALL" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ -L "$bin_dir/sapa-config" ]; then ok "re-install is idempotent"; else bad "re-install is idempotent (rc=$rc, $out)"; fi

# --- re-running the LINKED copy on PATH installs from the original clone ---
# Regression: invoking $bin_dir/sapa-install (a symlink into the clone) must
# resolve back to the clone, not treat $bin_dir/.. as the source and link the
# helpers to themselves. The self-referential target ($bin_dir/<h>) also ends in
# /bin/<h>, so assert the exact clone path — not just the suffix.
clone="$(cd "$HERE/.." && pwd)"
out="$(HOME="$home" bash "$bin_dir/sapa-install" 2>&1)"; rc=$?
if [ $rc -eq 0 ]; then ok "re-install via linked copy exits 0"; else bad "re-install via linked copy exits 0 (rc=$rc, $out)"; fi
if [ "$(readlink "$bin_dir/sapa-config")" = "$clone/bin/sapa-config" ]; then ok "linked-copy re-install keeps helper target in the clone"; else bad "linked-copy re-install keeps helper target in the clone ($(readlink "$bin_dir/sapa-config"))"; fi
if [ "$(readlink "$bin_dir/sapa-install")" = "$clone/bin/sapa-install" ]; then ok "linked-copy re-install does not self-reference"; else bad "linked-copy re-install does not self-reference ($(readlink "$bin_dir/sapa-install"))"; fi

# --- SAPA_AGENTS overrides detection: only claude linked ---
home2="$root/home2"
mkdir -p "$home2/.claude" "$home2/.codex"
out="$(HOME="$home2" SAPA_AGENTS=claude bash "$INSTALL" 2>&1)"; rc=$?
if [ -L "$home2/.claude/skills/sapa-plan" ] && [ ! -e "$home2/.codex/skills/sapa-plan" ]; then
  ok "SAPA_AGENTS targets only the named agent"
else
  bad "SAPA_AGENTS targets only the named agent (rc=$rc, $out)"
fi

# --- uninstall removes sapa's links but leaves foreign files alone ---
foreign="$bin_dir/other"
: > "$foreign"                      # a regular file that isn't ours
ln -sfn /somewhere/else "$bin_dir/sapa-start"  # a link that isn't ours
out="$(HOME="$home" bash "$INSTALL" uninstall 2>&1)"; rc=$?
if [ $rc -eq 0 ]; then ok "uninstall exits 0"; else bad "uninstall exits 0 (rc=$rc, $out)"; fi
if [ ! -e "$bin_dir/sapa-config" ]; then ok "uninstall removes a sapa helper link"; else bad "uninstall removes a sapa helper link"; fi
if [ ! -e "$home/.claude/skills/sapa-plan" ]; then ok "uninstall removes a sapa skill link"; else bad "uninstall removes a sapa skill link"; fi
if [ -f "$foreign" ]; then ok "uninstall leaves a foreign regular file"; else bad "uninstall leaves a foreign regular file"; fi
if [ -L "$bin_dir/sapa-start" ]; then ok "uninstall leaves a foreign symlink"; else bad "uninstall leaves a foreign symlink"; fi

# --- --help works ---
out="$(bash "$INSTALL" --help 2>&1)"; rc=$?
if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q "Usage:"; then ok "--help prints usage"; else bad "--help prints usage (rc=$rc)"; fi

echo
echo "$pass/$((pass+fail)) passed"
[ "$fail" -eq 0 ]
