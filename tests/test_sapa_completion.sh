#!/bin/bash
# Tests for `sapa completion`: it prints a zsh completion script covering every
# subcommand, rejects a missing or unsupported shell, routes through the
# dispatcher (and its install symlink), and emits a script zsh actually parses —
# including descriptions that contain apostrophes.
# Run: bash tests/test_sapa_completion.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SAPA="$HERE/../bin/sapa"

pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }

root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

# The subcommands the dispatcher exposes — the completion must cover every one,
# derived from `sapa help` so this test can't drift from the real command list.
cmds="$("$SAPA" help | awk '/^Commands:/{f=1;next} f&&/^$/{f=0} f&&/^  /{print $1}')"

# --- `sapa completion zsh` emits a usable zsh function ---
out="$("$SAPA" completion zsh 2>&1)"; rc=$?
if [ $rc -eq 0 ]; then ok "completion zsh exits 0"; else bad "completion zsh exits 0 (rc=$rc, $out)"; fi
if printf '%s' "$out" | grep -q "_sapa()"; then ok "defines the _sapa function"; else bad "defines the _sapa function"; fi
if printf '%s' "$out" | grep -q "compdef _sapa sapa"; then ok "wires compdef to sapa"; else bad "wires compdef to sapa"; fi

# --- every subcommand shows up as a completion candidate ---
missing=""
for c in $cmds; do
  printf '%s' "$out" | grep -q "'$c:" || missing="$missing $c"
done
if [ -z "$missing" ]; then ok "covers every subcommand"; else bad "covers every subcommand (missing:$missing)"; fi

# --- descriptions are scraped, not empty (a distinctive phrase from the help) ---
if printf '%s' "$out" | grep -q "worktree layout"; then ok "includes scraped descriptions"; else bad "includes scraped descriptions"; fi

# --- a missing or unsupported shell is a usage error (exit 2) ---
out="$("$SAPA" completion 2>&1)"; rc=$?
if [ $rc -eq 2 ] && printf '%s' "$out" | grep -q "usage: sapa completion zsh"; then ok "no shell exits 2 with usage"; else bad "no shell exits 2 with usage (rc=$rc, $out)"; fi
out="$("$SAPA" completion bash 2>&1)"; rc=$?
if [ $rc -eq 2 ] && printf '%s' "$out" | grep -q "unsupported shell"; then ok "unsupported shell exits 2"; else bad "unsupported shell exits 2 (rc=$rc, $out)"; fi

# --- routes through an install-style symlink (only `sapa` goes on PATH) ---
linkdir="$root/bin"; mkdir -p "$linkdir"
ln -sfn "$(cd "$HERE/.." && pwd)/bin/sapa" "$linkdir/sapa"
out="$("$linkdir/sapa" completion zsh 2>&1)"; rc=$?
if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q "compdef _sapa sapa"; then ok "resolves the helper through a symlink"; else bad "resolves the helper through a symlink (rc=$rc)"; fi

# --- the emitted script is valid zsh, and apostrophes survive parsing ---
if command -v zsh >/dev/null 2>&1; then
  "$SAPA" completion zsh > "$root/comp.zsh"
  if zsh -n "$root/comp.zsh"; then ok "emitted script passes zsh -n"; else bad "emitted script passes zsh -n"; fi

  # Parse just the _sapa_cmds array in a throwaway zsh script (no compinit needed)
  # and confirm it survives quoting: one element per emitted line, apostrophes
  # intact. This is the regression guard for descriptions like "branch's".
  nlines="$(grep -c "^    '" "$root/comp.zsh")"
  {
    echo 'typeset -a c'
    echo 'c=('
    awk '/_sapa_cmds=\(/{f=1;next} f&&/^  \)/{f=0} f' "$root/comp.zsh"
    echo ')'
    echo 'print ${#c}'
    echo 'print -r -- "${c[(r)watch:*]}"'
  } > "$root/check.zsh"
  parsed="$(zsh "$root/check.zsh")"
  count="$(printf '%s\n' "$parsed" | sed -n 1p)"
  watchel="$(printf '%s\n' "$parsed" | sed -n 2p)"
  if [ "$count" = "$nlines" ] && [ "$count" -gt 0 ]; then ok "array parses to one element per command ($count)"; else bad "array parses to one element per command (count=$count, lines=$nlines)"; fi
  if printf '%s' "$watchel" | grep -q "branch's"; then ok "apostrophes in descriptions survive"; else bad "apostrophes in descriptions survive ($watchel)"; fi
else
  echo "skip zsh -n / parse checks (zsh not installed)"
fi

echo
echo "$pass/$((pass+fail)) passed"
[ "$fail" -eq 0 ]
