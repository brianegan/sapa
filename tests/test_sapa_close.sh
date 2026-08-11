#!/bin/bash
# Tests for sapa-close, the VS Code closer that ships with sapa.
#
# No test here may drive a real editor: running this on a developer's mac must
# never close their live windows, and CI has no editor at all. So every case
# that reaches the AppleScript path stands in for `osascript` through
# SAPA_OSASCRIPT and asserts on what sapa-close hands it and reports back.
# Run: bash tests/test_sapa_close.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CLOSE="$HERE/../bin/sapa-close"
TEARDOWN="$HERE/../bin/sapa-teardown"

pass=0; fail=0
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
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }

root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

# A stand-in for osascript: records the arguments and the script it was fed,
# then prints whatever status the test asked for.
stub="$root/osascript-stub"
args_file="$root/args"
script_file="$root/script"
make_stub() {
  cat > "$stub" <<EOF
#!/bin/bash
printf '%s\n' "\$@" > "$args_file"
cat > "$script_file"
printf '%s\n' "$1"
EOF
  chmod +x "$stub"
}

# --- each status word the closer contract defines is relayed verbatim ---
for status in closed no-editor no-match "error:-25211"; do
  make_stub "$status"
  out="$(SAPA_OSASCRIPT="$stub" "$CLOSE" code my-stream)"; rc=$?
  check "relays $status" "$status" "$out"
  check "exits 0 for $status" "0" "$rc"
done

# --- the worktree basename reaches the script as its argument ---
make_stub closed
SAPA_OSASCRIPT="$stub" "$CLOSE" code my-stream >/dev/null
if grep -qx "my-stream" "$args_file"; then
  ok "passes the basename to the script"
else
  bad "passes the basename to the script (args: $(cat "$args_file"))"
fi

# --- the AppleScript is fed on stdin, and it is the VS Code one ---
if grep -q 'process "Code"' "$script_file"; then
  ok "feeds the VS Code AppleScript on stdin"
else
  bad "feeds the VS Code AppleScript on stdin"
fi
if grep -q "AXCloseButton" "$script_file"; then
  ok "the script presses the window's own close button"
else
  bad "the script presses the window's own close button"
fi

# --- an empty report means the close killed the closer mid-success ---
printf '#!/bin/bash\ncat >/dev/null\n' > "$stub"; chmod +x "$stub"
out="$(SAPA_OSASCRIPT="$stub" "$CLOSE" code my-stream)"; rc=$?
check "empty output reports closed" "closed" "$out"
check "empty output exits 0" "0" "$rc"

# --- a failing osascript still reports rather than erroring out ---
printf '#!/bin/bash\ncat >/dev/null\nexit 1\n' > "$stub"; chmod +x "$stub"
out="$(SAPA_OSASCRIPT="$stub" "$CLOSE" code my-stream)"; rc=$?
check "a failing osascript exits 0" "0" "$rc"

# --- no osascript to drive is the same news as no editor ---
out="$(SAPA_OSASCRIPT="$root/not-a-real-binary" "$CLOSE" code my-stream)"; rc=$?
check "a missing osascript reports no-editor" "no-editor" "$out"
check "a missing osascript exits 0" "0" "$rc"

# --- the stand-in is honoured off macOS, which is where CI runs ---
# Regression guard: this file is meaningless on a runner if a platform check
# short-circuits before SAPA_OSASCRIPT is consulted. Every case above would then
# pass locally and fail on Linux, so shadow `uname` and prove the seam still
# works when the platform says otherwise.
fake_bin="$root/fake-bin"
mkdir -p "$fake_bin"
printf '#!/bin/bash\necho Linux\n' > "$fake_bin/uname"
chmod +x "$fake_bin/uname"

make_stub closed
out="$(PATH="$fake_bin:$PATH" SAPA_OSASCRIPT="$stub" "$CLOSE" code my-stream)"
check "the stand-in is used even off macOS" "closed" "$out"

# Without the stand-in, though, a non-mac has nothing to drive.
out="$(PATH="$fake_bin:$PATH" env -u SAPA_OSASCRIPT "$CLOSE" code my-stream)"; rc=$?
check "off macOS with no stand-in reports no-editor" "no-editor" "$out"
check "off macOS with no stand-in exits 0" "0" "$rc"

# --- usage errors ---
out="$("$CLOSE" 2>&1)"; rc=$?
if [ $rc -eq 2 ] && grep -q "usage: sapa close" <<<"$out"; then
  ok "no arguments exits 2 with usage"
else
  bad "no arguments exits 2 with usage (rc=$rc, $out)"
fi
out="$("$CLOSE" code 2>&1)"; rc=$?
if [ $rc -eq 2 ]; then ok "a target with no basename exits 2"; else bad "a target with no basename exits 2 (rc=$rc)"; fi
out="$("$CLOSE" emacs my-stream 2>&1)"; rc=$?
if [ $rc -eq 2 ] && grep -q "unknown target" <<<"$out"; then
  ok "an unknown target exits 2"
else
  bad "an unknown target exits 2 (rc=$rc, $out)"
fi
out="$("$CLOSE" --help 2>&1)"; rc=$?
if [ $rc -eq 0 ] && grep -q "sapa close" <<<"$out"; then ok "--help prints the help"; else bad "--help prints the help (rc=$rc)"; fi
# Help past the target explains itself rather than hunting for a window called
# `--help`.
: > "$args_file"
out="$("$CLOSE" code --help 2>&1)"; rc=$?
if [ $rc -eq 0 ] && grep -q "sapa close" <<<"$out"; then
  ok "help after the target prints the help"
else
  bad "help after the target prints the help (rc=$rc, $out)"
fi

# --- teardown no longer knows about editors ---
# The AppleScript lives in exactly one place. Teardown runs whatever closer it
# is given and has no opinion about which editor that is.
if grep -qi "applescript\|osascript\|AXCloseButton" "$TEARDOWN"; then
  bad "teardown holds no AppleScript"
else
  ok "teardown holds no AppleScript"
fi
if grep -qi "vs code\|visual studio code\|process \"Code\"" "$TEARDOWN"; then
  bad "teardown does not name VS Code as its editor"
else
  ok "teardown does not name VS Code as its editor"
fi

echo
echo "$pass/$((pass + fail)) passed"
[ "$fail" -eq 0 ]
