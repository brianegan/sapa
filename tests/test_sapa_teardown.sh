#!/bin/bash
# Tests for sapa-teardown against a real bare-layout repo in a temp dir.
# Run: bash tests/test_sapa_teardown.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TEARDOWN="$HERE/../bin/sapa-teardown"
# Put bin on PATH so teardown can resolve sapa-config for the close_window key.
export PATH="$HERE/../bin:$PATH"

pass=0; fail=0
ok()   { echo "ok   $1"; pass=$((pass+1)); }
bad()  { echo "FAIL $1"; fail=$((fail+1)); }

# Stub the window closer so no real osascript ever runs during tests (it would
# otherwise try to close live VS Code windows on a developer's mac). The stub
# records each basename it is handed.
closer="$(mktemp)"
recorded="$(mktemp)"
cat > "$closer" <<EOF
#!/bin/bash
printf '%s\n' "\$1" >> "$recorded"
EOF
chmod +x "$closer"
export SAPA_TEARDOWN_CLOSER="$closer"

# Build a bare-layout project: root/.bare + a main worktree + a feature worktree.
root="$(mktemp -d)"
trap 'rm -rf "$root" "$closer" "$recorded"' EXIT
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
# By default the window closer runs with the worktree's basename.
if grep -qx "feature" "$recorded"; then ok "closes window by default"; else bad "closes window by default (recorded: $(cat "$recorded"))"; fi

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

# --- close_window: false suppresses the window close ---
printf 'close_window: false\n' > "$proj/.sapa.yaml"
git -C "$proj/main" worktree add -q "$proj/noclose" -b noclose
: > "$recorded"
out="$(bash "$TEARDOWN" "$proj/noclose" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ ! -s "$recorded" ]; then ok "close_window: false suppresses close"; else bad "close_window: false suppresses close (rc=$rc, recorded: $(cat "$recorded"))"; fi

# --- opt-out is honoured even when sapa-config is not on PATH (sibling fallback) ---
git -C "$proj/main" worktree add -q "$proj/nopath" -b nopath
: > "$recorded"
out="$(PATH=/usr/bin:/bin bash "$TEARDOWN" "$proj/nopath" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ ! -s "$recorded" ]; then ok "opt-out honoured without sapa-config on PATH"; else bad "opt-out honoured without sapa-config on PATH (rc=$rc, recorded: $(cat "$recorded"))"; fi
rm -f "$proj/.sapa.yaml"

# --- a failing closer never fails the teardown ---
git -C "$proj/main" worktree add -q "$proj/badcloser" -b badcloser
out="$(SAPA_TEARDOWN_CLOSER=/bin/false bash "$TEARDOWN" "$proj/badcloser" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ ! -d "$proj/badcloser" ]; then ok "failing closer does not fail teardown"; else bad "failing closer does not fail teardown (rc=$rc, $out)"; fi

# --- a denied close (no Accessibility) surfaces a hint but still succeeds ---
git -C "$proj/main" worktree add -q "$proj/denied" -b denied
denier="$(mktemp)"
printf '#!/bin/bash\necho "error:-25211"\n' > "$denier"; chmod +x "$denier"
err="$(SAPA_TEARDOWN_CLOSER="$denier" bash "$TEARDOWN" "$proj/denied" 2>&1 >/dev/null)"; rc=$?
if [ $rc -eq 0 ] && [ ! -d "$proj/denied" ] && printf '%s' "$err" | grep -qi "Accessibility"; then
  ok "denied close prints Accessibility hint and still succeeds"
else
  bad "denied close hint (rc=$rc, err: $err)"
fi
rm -f "$denier"

# --- teardown clears the stream's window-switcher status file ---
status_dir="$(mktemp -d)"
git -C "$proj/main" worktree add -q "$proj/statusy" -b statusy
SAPA_STATUS_DIR="$status_dir" "$HERE/../bin/sapa-status" --stage watch --start "$proj/statusy"
out="$(SAPA_STATUS_DIR="$status_dir" bash "$TEARDOWN" "$proj/statusy" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ ! -e "$status_dir/statusy.json" ]; then
  ok "clears the status file on teardown"
else
  bad "clears the status file on teardown (rc=$rc, left: $(ls -A "$status_dir" 2>/dev/null))"
fi
rm -rf "$status_dir"

# --- refuses to remove the project root ---
out="$(bash "$TEARDOWN" "$proj/main" 2>&1)"; rc=$?
# main is a worktree, not the root; the root itself has no branch checkout.
out="$(bash "$TEARDOWN" "$proj" 2>&1)"; rc=$?
if [ $rc -ne 0 ] && [ -d "$proj" ]; then ok "refuses project root"; else bad "refuses project root (rc=$rc)"; fi

echo
echo "$pass/$((pass+fail)) passed"
[ "$fail" -eq 0 ]
