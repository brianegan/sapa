#!/bin/bash
# Tests for sapa-settings, the personal ~/.sapa/settings.yaml reader.
# Every case runs under a sandboxed HOME so a developer's real settings are
# never read, written, or overwritten.
# Run: bash tests/test_sapa_settings.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SETTINGS="$HERE/../bin/sapa-settings"

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
home="$root/home"
mkdir -p "$home"

# --- the path is fixed, and printed whether or not the file exists ---
out="$(HOME="$home" "$SETTINGS")"; rc=$?
check "bare prints the path" "$home/.sapa/settings.yaml" "$out"
check "bare exits 0 with no file" "0" "$rc"

# --- -p on a missing file exits 1 and says where it looked ---
err="$(HOME="$home" "$SETTINGS" -p 2>&1 >/dev/null)"; rc=$?
if [ $rc -eq 1 ] && grep -q "$home/.sapa/settings.yaml" <<<"$err"; then
  ok "-p on a missing file exits 1 with the path"
else
  bad "-p on a missing file exits 1 with the path (rc=$rc, $err)"
fi
if grep -q "settings init" <<<"$err"; then ok "-p hints at settings init"; else bad "-p hints at settings init ($err)"; fi

# --- -p prints the contents once a file exists ---
mkdir -p "$home/.sapa"
printf 'opener: my-editor\n' > "$home/.sapa/settings.yaml"
out="$(HOME="$home" "$SETTINGS" -p)"
check "-p prints the contents" "opener: my-editor" "$out"
out="$(HOME="$home" "$SETTINGS" --print)"
check "--print is a synonym for -p" "opener: my-editor" "$out"

# --- init writes the template into a fresh HOME, creating ~/.sapa ---
fresh="$root/fresh"
mkdir -p "$fresh"
out="$(HOME="$fresh" "$SETTINGS" init)"
check "init prints the written path" "$fresh/.sapa/settings.yaml" "$out"
check "init creates the file" "yes" \
  "$([ -f "$fresh/.sapa/settings.yaml" ] && echo yes || echo no)"

# The generated file parses as YAML and, being all comments, holds no keys.
if python3 -c "import sys,yaml; sys.exit(0 if yaml.safe_load(open(sys.argv[1])) is None else 1)" \
     "$fresh/.sapa/settings.yaml" 2>/dev/null; then
  ok "init output is valid YAML with everything commented out"
else
  bad "init output is valid YAML with everything commented out"
fi

# Both workflow keys appear as commented entries, so the file is its own menu.
for key in opener closer; do
  present=no
  grep -qE "^# ?${key}:" "$fresh/.sapa/settings.yaml" && present=yes
  check "init documents $key" "yes" "$present"
done

# The closer example names the closer that ships with sapa.
if grep -q "sapa close code" "$fresh/.sapa/settings.yaml"; then
  ok "init points closer at sapa close code"
else
  bad "init points closer at sapa close code"
fi

# --- init refuses to clobber existing settings without --force ---
printf 'opener: precious\n' > "$fresh/.sapa/settings.yaml"
if HOME="$fresh" "$SETTINGS" init </dev/null >/dev/null 2>&1; then
  check "init refuses to overwrite (no tty)" "refused" "created"
else
  check "init refuses to overwrite (no tty)" "refused" "refused"
fi
check "init leaves the existing file untouched on refuse" "opener: precious" \
  "$(cat "$fresh/.sapa/settings.yaml")"

# --force overwrites it.
HOME="$fresh" "$SETTINGS" init --force </dev/null >/dev/null 2>&1
overwritten=no
grep -qE "^# ?opener:" "$fresh/.sapa/settings.yaml" && overwritten=yes
check "init --force overwrites" "yes" "$overwritten"

# On a tty the guard prompts instead of refusing outright. Driven through a pty
# so [ -t 0 ] is true, the same way the config tests reach that branch.
run_prompt() {
  # $1 = answer fed to the prompt, $2 = HOME to run under. Prints exit code.
  python3 - "$SETTINGS" "$2" "$1" <<'PY'
import os, pty, sys
settings, home, answer = sys.argv[1], sys.argv[2], sys.argv[3]
pid, fd = pty.fork()
if pid == 0:
    os.environ["HOME"] = home
    os.execv("/bin/bash", ["/bin/bash", settings, "init"])
os.write(fd, (answer + "\n").encode())
try:
    while os.read(fd, 1024):
        pass
except OSError:
    pass
_, status = os.waitpid(pid, 0)
sys.exit(os.WEXITSTATUS(status) if os.WIFEXITED(status) else 1)
PY
}

prompted="$root/prompted"
mkdir -p "$prompted/.sapa"
printf 'opener: precious\n' > "$prompted/.sapa/settings.yaml"
if run_prompt n "$prompted"; then
  check "init prompt: no exits non-zero" "nonzero" "zero"
else
  check "init prompt: no exits non-zero" "nonzero" "nonzero"
fi
check "init prompt: no leaves the file untouched" "opener: precious" \
  "$(cat "$prompted/.sapa/settings.yaml")"

run_prompt y "$prompted"
overwritten=no
grep -qE "^# ?opener:" "$prompted/.sapa/settings.yaml" && overwritten=yes
check "init prompt: yes overwrites" "yes" "$overwritten"

# --- unknown arguments are a usage error ---
out="$(HOME="$home" "$SETTINGS" --bogus 2>&1)"; rc=$?
if [ $rc -eq 2 ] && grep -q "unknown argument" <<<"$out"; then
  ok "unknown argument exits 2"
else
  bad "unknown argument exits 2 (rc=$rc, $out)"
fi

# --- --help prints this command's own help ---
out="$(HOME="$home" "$SETTINGS" --help 2>&1)"; rc=$?
if [ $rc -eq 0 ] && grep -q "sapa settings" <<<"$out"; then
  ok "--help prints the help"
else
  bad "--help prints the help (rc=$rc)"
fi

echo
echo "$pass/$((pass + fail)) passed"
[ "$fail" -eq 0 ]
