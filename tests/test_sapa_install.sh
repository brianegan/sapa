#!/bin/bash
# Tests for sapa-install. Everything is sandboxed by pointing HOME at a temp dir
# so SAPA_BIN_DIR and the agent skills dirs land there — the real ~/.local/bin
# and ~/.claude are never touched.
# Run: bash tests/test_sapa_install.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
INSTALL="$HERE/../bin/sapa-install"
clone="$(cd "$HERE/.." && pwd)"

pass=0; fail=0
ok()   { echo "ok   $1"; pass=$((pass+1)); }
bad()  { echo "FAIL $1"; fail=$((fail+1)); }

root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

# A sandbox HOME with both agent homes present so auto-detect targets each.
home="$root/home"
mkdir -p "$home/.claude" "$home/.codex"
bin_dir="$home/.local/bin"

# --- install links only the sapa command, plus skills ---
out="$(HOME="$home" bash "$INSTALL" 2>&1)"; rc=$?
if [ $rc -eq 0 ]; then ok "install exits 0"; else bad "install exits 0 (rc=$rc, $out)"; fi
if [ -L "$bin_dir/sapa" ]; then ok "links sapa into ~/.local/bin"; else bad "links sapa into ~/.local/bin"; fi
if [ ! -e "$bin_dir/sapa-config" ]; then ok "does not link per-command helpers"; else bad "does not link per-command helpers"; fi
if [ -L "$home/.claude/skills/sapa-plan" ]; then ok "links a skill into claude"; else bad "links a skill into claude"; fi
if [ -L "$home/.codex/skills/sapa-plan" ]; then ok "links a skill into codex"; else bad "links a skill into codex"; fi

# Targets point back into this clone, not somewhere arbitrary.
if [ "$(readlink "$bin_dir/sapa")" = "$clone/bin/sapa" ]; then ok "sapa target points into the clone"; else bad "sapa target points into the clone ($(readlink "$bin_dir/sapa"))"; fi
if readlink "$home/.claude/skills/sapa-plan" | grep -q '/skill/sapa-plan$'; then ok "skill target points into the clone"; else bad "skill target points into the clone"; fi

# --- install prints a copy-paste-and-run completion hint (shell config untouched) ---
if printf '%s' "$out" | grep -qF "echo 'eval \"\$(sapa completion zsh)\"' >> ~/.zshrc"; then ok "install hints at completion"; else bad "install hints at completion ($out)"; fi

# --- re-running is idempotent ---
out="$(HOME="$home" bash "$INSTALL" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ -L "$bin_dir/sapa" ]; then ok "re-install is idempotent"; else bad "re-install is idempotent (rc=$rc, $out)"; fi

# --- re-running the LINKED copy on PATH installs from the original clone ---
# Regression: invoking $bin_dir/sapa (a symlink into the clone) must resolve back
# to the clone, not treat $bin_dir/.. as the source and link sapa to itself. The
# dispatcher execs sapa-install from the clone, so assert the exact clone path.
out="$(HOME="$home" bash "$bin_dir/sapa" install 2>&1)"; rc=$?
if [ $rc -eq 0 ]; then ok "re-install via linked copy exits 0"; else bad "re-install via linked copy exits 0 (rc=$rc, $out)"; fi
if [ "$(readlink "$bin_dir/sapa")" = "$clone/bin/sapa" ]; then ok "linked-copy re-install keeps sapa target in the clone"; else bad "linked-copy re-install keeps sapa target in the clone ($(readlink "$bin_dir/sapa"))"; fi

# --- install sweeps links left by the old one-per-command layout ---
# A stale legacy link pointing into a sapa clone should be removed on install;
# a foreign link and a regular file must survive.
ln -sfn "$clone/bin/sapa-config" "$bin_dir/sapa-config"   # a stale sapa link
ln -sfn /somewhere/else "$bin_dir/sapa-teardown"          # a link that isn't ours
: > "$bin_dir/sapa-start"                                 # a regular file, not ours
out="$(HOME="$home" bash "$INSTALL" 2>&1)"; rc=$?
if [ ! -e "$bin_dir/sapa-config" ]; then ok "install sweeps a stale legacy sapa link"; else bad "install sweeps a stale legacy sapa link"; fi
if [ -L "$bin_dir/sapa-teardown" ]; then ok "install leaves a foreign symlink"; else bad "install leaves a foreign symlink"; fi
if [ -f "$bin_dir/sapa-start" ]; then ok "install leaves a foreign regular file"; else bad "install leaves a foreign regular file"; fi
rm -f "$bin_dir/sapa-teardown" "$bin_dir/sapa-start"

# --- SAPA_AGENTS overrides detection: only claude linked ---
home2="$root/home2"
mkdir -p "$home2/.claude" "$home2/.codex"
out="$(HOME="$home2" SAPA_AGENTS=claude bash "$INSTALL" 2>&1)"; rc=$?
if [ -L "$home2/.claude/skills/sapa-plan" ] && [ ! -e "$home2/.codex/skills/sapa-plan" ]; then
  ok "SAPA_AGENTS targets only the named agent"
else
  bad "SAPA_AGENTS targets only the named agent (rc=$rc, $out)"
fi

# --- uninstall removes sapa's links (incl. legacy) but leaves foreign files alone ---
foreign="$bin_dir/other"
: > "$foreign"                                  # a regular file that isn't ours
ln -sfn /somewhere/else "$bin_dir/sapa-worktree"  # a link that isn't ours
ln -sfn "$clone/bin/sapa-start" "$bin_dir/sapa-start"  # a stale legacy link that IS ours
out="$(HOME="$home" bash "$INSTALL" uninstall 2>&1)"; rc=$?
if [ $rc -eq 0 ]; then ok "uninstall exits 0"; else bad "uninstall exits 0 (rc=$rc, $out)"; fi
if [ ! -e "$bin_dir/sapa" ]; then ok "uninstall removes the sapa link"; else bad "uninstall removes the sapa link"; fi
if [ ! -e "$bin_dir/sapa-start" ]; then ok "uninstall removes a legacy sapa link"; else bad "uninstall removes a legacy sapa link"; fi
if [ ! -e "$home/.claude/skills/sapa-plan" ]; then ok "uninstall removes a sapa skill link"; else bad "uninstall removes a sapa skill link"; fi
if [ -f "$foreign" ]; then ok "uninstall leaves a foreign regular file"; else bad "uninstall leaves a foreign regular file"; fi
if [ -L "$bin_dir/sapa-worktree" ]; then ok "uninstall leaves a foreign symlink"; else bad "uninstall leaves a foreign symlink"; fi
if printf '%s' "$out" | grep -q 'sapa completion zsh'; then bad "uninstall does not print the completion hint"; else ok "uninstall does not print the completion hint"; fi

# --- --help works ---
out="$(bash "$INSTALL" --help 2>&1)"; rc=$?
if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q "Usage:"; then ok "--help prints usage"; else bad "--help prints usage (rc=$rc)"; fi

echo
echo "$pass/$((pass+fail)) passed"
[ "$fail" -eq 0 ]
