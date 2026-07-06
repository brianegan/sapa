#!/bin/bash
# Tests for the sapa dispatcher: help, unknown commands, routing to the helpers,
# per-command subhelp, and resolving its helpers through the install symlink.
# Run: bash tests/test_sapa_dispatch.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SAPA="$HERE/../bin/sapa"

pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }

root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

# --- top-level help lists the subcommands and exits 0 ---
for flag in help -h --help; do
  out="$("$SAPA" $flag 2>&1)"; rc=$?
  if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q "bootstrap" && printf '%s' "$out" | grep -q "teardown"; then
    ok "help ($flag) lists subcommands, exits 0"
  else
    bad "help ($flag) lists subcommands, exits 0 (rc=$rc)"
  fi
done

# --- no subcommand prints usage and exits 2 ---
out="$("$SAPA" 2>&1)"; rc=$?
if [ $rc -eq 2 ] && printf '%s' "$out" | grep -q "bootstrap"; then ok "no subcommand exits 2 with usage"; else bad "no subcommand exits 2 with usage (rc=$rc)"; fi

# --- unknown subcommand errors and exits 2 ---
out="$("$SAPA" bogus 2>&1)"; rc=$?
if [ $rc -eq 2 ] && printf '%s' "$out" | grep -q "unknown command"; then ok "unknown subcommand exits 2"; else bad "unknown subcommand exits 2 (rc=$rc, $out)"; fi

# --- routing: config walks up and prints the path ---
mkdir -p "$root/proj/feature"
printf 'base: main\n' > "$root/proj/.sapa.yaml"
out="$("$SAPA" config --start "$root/proj/feature")"; rc=$?
if [ $rc -eq 0 ] && [ "$out" = "$root/proj/.sapa.yaml" ]; then ok "routes to config"; else bad "routes to config (rc=$rc, $out)"; fi

# --- routing: start derives a branch name with no network (--title, --print) ---
out="$("$SAPA" start 42 --title "Add a Widget!" --print)"; rc=$?
if [ $rc -eq 0 ] && [ "$out" = "42-add-a-widget" ]; then ok "routes to start"; else bad "routes to start (rc=$rc, $out)"; fi

# --- routing: section reaches the Python helper and wraps content ---
printf 'hello\n' > "$root/content.md"
out="$(printf '' | "$SAPA" section mymark --content-file "$root/content.md" 2>/dev/null)"; rc=$?
if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q "<!-- sapa:mymark" && printf '%s' "$out" | grep -q "hello"; then
  ok "routes to section (Python helper)"
else
  bad "routes to section (Python helper) (rc=$rc, $out)"
fi

# --- subhelp: `sapa <cmd> --help` shows that command's own help ---
out="$("$SAPA" config --help 2>&1)"; rc=$?
if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q "sapa-config"; then ok "config --help shows subcommand help"; else bad "config --help shows subcommand help (rc=$rc)"; fi
out="$("$SAPA" section --help 2>&1)"; rc=$?
if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q "usage:"; then ok "section --help shows subcommand help"; else bad "section --help shows subcommand help (rc=$rc)"; fi

# --- resolves helpers through an install-style symlink ---
# sapa-install links only `sapa` onto PATH; invoked through that link the
# dispatcher must resolve back to the clone's bin/ to find its siblings.
linkdir="$root/bin"
mkdir -p "$linkdir"
ln -sfn "$(cd "$HERE/.." && pwd)/bin/sapa" "$linkdir/sapa"
out="$("$linkdir/sapa" config --start "$root/proj/feature")"; rc=$?
if [ $rc -eq 0 ] && [ "$out" = "$root/proj/.sapa.yaml" ]; then ok "resolves helpers through a symlink"; else bad "resolves helpers through a symlink (rc=$rc, $out)"; fi

echo
echo "$pass/$((pass+fail)) passed"
[ "$fail" -eq 0 ]
