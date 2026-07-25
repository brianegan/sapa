#!/bin/bash
# Tests for `sapa completion`: it prints a zsh completion script covering every
# subcommand, rejects a missing or unsupported shell, routes through the
# dispatcher (and its install symlink), and emits a script zsh actually parses —
# including descriptions that contain apostrophes.
# Run: bash tests/test_sapa_completion.sh
#
# Assertions read a captured string with a herestring, never `printf … | grep`.
# Under pipefail a reader that exits on its first match (grep -q, awk with exit)
# leaves the writer to take EPIPE, and printf's non-zero status becomes the
# pipeline's — so a found pattern reports as not found. It fires only when the
# output is long enough to need a second write, which made it a flake that grew
# with the completion script.

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
if grep -q "_sapa()" <<<"$out"; then ok "defines the _sapa function"; else bad "defines the _sapa function"; fi
if grep -q "compdef _sapa sapa" <<<"$out"; then ok "wires compdef to sapa"; else bad "wires compdef to sapa"; fi

# --- every subcommand shows up as a completion candidate ---
missing=""
for c in $cmds; do
  grep -q "'$c:" <<<"$out" || missing="$missing $c"
done
if [ -z "$missing" ]; then ok "covers every subcommand"; else bad "covers every subcommand (missing:$missing)"; fi

# --- descriptions are scraped, not empty (a distinctive phrase from the help) ---
if grep -q "worktree layout" <<<"$out"; then ok "includes scraped descriptions"; else bad "includes scraped descriptions"; fi

# --- argument completion: teardown and config --start complete directories ---
# (regression for the reported bug: `sapa teardown <TAB>` offered `--force`
# instead of directories. The branch now completes directories on a blank word
# and only offers the options when the current word is dash-prefixed.)
teardown_branch="$(awk '/^    teardown\)/{f=1} f{print} f&&/;;/{exit}' <<<"$out")"
if grep -q '_files -/' <<<"$teardown_branch"; then ok "teardown completes directories"; else bad "teardown completes directories"; fi
if grep -q 'words\[CURRENT\]} == -\*' <<<"$teardown_branch"; then ok "teardown gates options behind a dash prefix"; else bad "teardown gates options behind a dash prefix"; fi
config_branch="$(awk '/^    config\)/{f=1} f{print} f&&/;;/{exit}' <<<"$out")"
if grep -q -- '--start\[.*_files -/' <<<"$config_branch"; then ok "config --start completes directories"; else bad "config --start completes directories"; fi
if grep -q 'init\\:' <<<"$config_branch"; then ok "config offers the init subcommand"; else bad "config offers the init subcommand"; fi
gate_branch="$(awk '/^    gate\)/{f=1} f{print} f&&/;;/{exit}' <<<"$out")"
gate_missing=""
for flag in --after --result --summary --list --report --start; do
  grep -q -- "$flag\[" <<<"$gate_branch" || gate_missing="$gate_missing $flag"
done
if [ -z "$gate_missing" ]; then ok "gate offers every flag"; else bad "gate offers every flag (missing:$gate_missing)"; fi
# The wiring self-heals when the enable line lands before compinit.
if grep -q 'functions\[compdef\]' <<<"$out"; then ok "guards compdef wiring behind compinit"; else bad "guards compdef wiring behind compinit"; fi

# --- a missing or unsupported shell is a usage error (exit 2) ---
out="$("$SAPA" completion 2>&1)"; rc=$?
if [ $rc -eq 2 ] && grep -q "usage: sapa completion zsh" <<<"$out"; then ok "no shell exits 2 with usage"; else bad "no shell exits 2 with usage (rc=$rc, $out)"; fi
out="$("$SAPA" completion bash 2>&1)"; rc=$?
if [ $rc -eq 2 ] && grep -q "unsupported shell" <<<"$out"; then ok "unsupported shell exits 2"; else bad "unsupported shell exits 2 (rc=$rc, $out)"; fi

# --- routes through an install-style symlink (only `sapa` goes on PATH) ---
linkdir="$root/bin"; mkdir -p "$linkdir"
ln -sfn "$(cd "$HERE/.." && pwd)/bin/sapa" "$linkdir/sapa"
out="$("$linkdir/sapa" completion zsh 2>&1)"; rc=$?
if [ $rc -eq 0 ] && grep -q "compdef _sapa sapa" <<<"$out"; then ok "resolves the helper through a symlink"; else bad "resolves the helper through a symlink (rc=$rc)"; fi

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
  if grep -q "branch's" <<<"$watchel"; then ok "apostrophes in descriptions survive"; else bad "apostrophes in descriptions survive ($watchel)"; fi

  # --- every argument-taking subcommand dispatches to a real branch ---
  # Stub the completion helpers as recorders, drive _sapa for each command at the
  # argument position, and confirm each one actually calls a helper (never falls
  # through the case to silence — the root cause of "Tab doesn't always work").
  # install and uninstall take no positional arguments (they read env vars), so
  # they complete nothing by design and are excluded here.
  "$SAPA" completion zsh > "$root/_sapa.zsh"
  cat > "$root/probe.zsh" <<'PROBE'
CALLS=()
_describe(){ CALLS+=("$*") }; _values(){ CALLS+=("$*") }
_arguments(){ CALLS+=("$*") }; _alternative(){ CALLS+=("$*") }
_files(){ CALLS+=("$*") }
compdef(){ : }; autoload(){ : }; compinit(){ : }
source "$SRC"
for c in bootstrap worktree start issue config section watch teardown completion; do
  words=(sapa "$c" ""); CURRENT=3; CALLS=()
  _sapa
  (( ${#CALLS} )) && print -r -- "$c ok" || print -r -- "$c MISSING"
done
PROBE
  probeout="$(SRC="$root/_sapa.zsh" zsh "$root/probe.zsh")"
  if ! grep -q MISSING <<<"$probeout"; then ok "every subcommand has an argument-completion branch"; else bad "every subcommand has an argument-completion branch ($(grep MISSING <<<"$probeout"))"; fi

  # --- teardown's blank word reaches directory completion directly ---
  # The reported bug: `sapa teardown <TAB>` completed nothing. The cause was
  # routing directory completion through `_arguments '::worktree:_files -/'` —
  # `_arguments` treats words[1] (sapa) as the command and parses positionals
  # from words[2] (teardown), so the subcommand word swallowed the lone spec and
  # the current word got nothing. The earlier grep-only check missed it because
  # the branch text still contained `_files -/`. Drive _sapa and record which
  # helper each path actually calls: a blank word must call `_files -/`
  # directly, and a dash word must reach the options instead of files.
  cat > "$root/teardown_probe.zsh" <<'PROBE'
FILES=""; ARGS=""
_files(){ FILES="$*" }
_arguments(){ ARGS="$*" }
_describe(){ : }; _values(){ : }; _alternative(){ : }
compdef(){ : }; autoload(){ : }; compinit(){ : }
source "$SRC"
words=(sapa teardown ""); CURRENT=3; FILES=""; ARGS=""
_sapa
print -r -- "blank files=[$FILES] args=[$ARGS]"
words=(sapa teardown "-"); CURRENT=3; FILES=""; ARGS=""
_sapa
print -r -- "dash files=[$FILES] args=[$ARGS]"
PROBE
  tdout="$(SRC="$root/_sapa.zsh" zsh "$root/teardown_probe.zsh")"
  blankline="$(printf '%s\n' "$tdout" | grep '^blank ')"
  dashline="$(printf '%s\n' "$tdout" | grep '^dash ')"
  if grep -q 'files=\[-/\]' <<<"$blankline"; then ok "teardown blank word calls _files -/ directly"; else bad "teardown blank word calls _files -/ directly ($blankline)"; fi
  if grep -q 'args=\[.*--force' <<<"$dashline"; then ok "teardown dash word reaches --force options"; else bad "teardown dash word reaches --force options ($dashline)"; fi
else
  echo "skip zsh -n / parse checks (zsh not installed)"
fi

echo
echo "$pass/$((pass+fail)) passed"
[ "$fail" -eq 0 ]
