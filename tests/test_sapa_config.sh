#!/bin/bash
# Tests for sapa-config, the walk-up config locator.
# Run: bash tests/test_sapa_config.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$HERE/../bin/sapa-config"

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

root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

# Layout: root/.sapa.yaml and a nested worktree with no config of its own.
mkdir -p "$root/proj/feature/deep"
printf 'base: main\n' > "$root/proj/.sapa.yaml"

# Found by walking up several levels.
found="$("$CONFIG" --start "$root/proj/feature/deep")"
check "walks up to find config" "$root/proj/.sapa.yaml" "$found"

# Found when sitting directly in the config's directory.
found="$("$CONFIG" --start "$root/proj")"
check "finds config in current dir" "$root/proj/.sapa.yaml" "$found"

# Prints contents with -p.
contents="$("$CONFIG" -p --start "$root/proj/feature")"
check "prints contents with -p" "base: main" "$contents"

# Finds a non-dotfile sapa.yaml when it is the only config in an ancestor dir.
mkdir -p "$root/plain/feature/deep"
printf 'base: main\n' > "$root/plain/sapa.yaml"
found="$("$CONFIG" --start "$root/plain/feature/deep")"
check "finds sapa.yaml (no dot)" "$root/plain/sapa.yaml" "$found"

# Prefers .sapa.yaml over sapa.yaml in the same dir.
mkdir -p "$root/both/feature"
printf 'base: dotted\n' > "$root/both/.sapa.yaml"
printf 'base: plain\n' > "$root/both/sapa.yaml"
found="$("$CONFIG" --start "$root/both/feature")"
check "prefers .sapa.yaml in same dir" "$root/both/.sapa.yaml" "$found"

# A closer sapa.yaml beats a farther .sapa.yaml (proximity over dot).
mkdir -p "$root/near/child/deep"
printf 'base: far\n' > "$root/near/.sapa.yaml"
printf 'base: near\n' > "$root/near/child/sapa.yaml"
found="$("$CONFIG" --start "$root/near/child/deep")"
check "closer sapa.yaml beats farther .sapa.yaml" "$root/near/child/sapa.yaml" "$found"

# Exits non-zero when no config exists anywhere up the tree.
mkdir -p "$root/orphan"
if "$CONFIG" --start "$root/orphan" >/dev/null 2>&1; then
  # It may still find a real ~/.sapa.yaml on a dev machine; guard on tmp only.
  echo "FAIL missing config exits non-zero: unexpected success"
  fail=$((fail + 1))
else
  echo "ok   missing config exits non-zero"
  pass=$((pass + 1))
fi

# --- sapa config init ---

# Task 1: writes .sapa.yaml into the target dir and prints the path.
fresh="$root/fresh"
mkdir -p "$fresh"
out="$("$CONFIG" init --start "$fresh")"
check "init prints the written path" "$fresh/.sapa.yaml" "$out"
check "init creates the file" "yes" "$([ -f "$fresh/.sapa.yaml" ] && echo yes || echo no)"

# Task 1: the read path is untouched — bare config and -p still work.
found="$("$CONFIG" --start "$root/proj/feature")"
check "read path still walks up after init added" "$root/proj/.sapa.yaml" "$found"

# Task 2: the generated file parses as valid YAML.
if python3 -c "import sys,yaml; yaml.safe_load(open(sys.argv[1]))" "$fresh/.sapa.yaml" 2>/dev/null; then
  check "init output is valid YAML" "ok" "ok"
else
  check "init output is valid YAML" "ok" "invalid"
fi

# Task 2: every documented option appears as a commented entry.
for key in base pr tracker plan build writing_style watch gate; do
  present=no
  grep -qE "^# ?${key}:" "$fresh/.sapa.yaml" && present=yes
  check "init documents $key" "yes" "$present"
done

# Task 2: the gate example shows two steps, nested under `gate.steps:`.
steps=$(grep -cE "^#     - name:" "$fresh/.sapa.yaml")
check "init gate example has two steps" "2" "$steps"
nested=no
grep -qE "^#   steps:" "$fresh/.sapa.yaml" && nested=yes
check "init gate example nests them under steps:" "yes" "$nested"
budget=no
grep -qE "^#   max_fix_attempts:" "$fresh/.sapa.yaml" && budget=yes
check "init documents max_fix_attempts" "yes" "$budget"

# Task 3: a non-interactive run refuses when a config exists (proj/ has one).
guarded="$root/proj/feature/init-here"
mkdir -p "$guarded"
if "$CONFIG" init --start "$guarded" </dev/null >/dev/null 2>&1; then
  check "init refuses when config exists (no tty)" "refused" "created"
else
  check "init refuses when config exists (no tty)" "refused" "refused"
fi
check "init writes nothing on refuse" "no" \
  "$([ -f "$guarded/.sapa.yaml" ] && echo yes || echo no)"

# Task 3: --force bypasses the guard and writes anyway.
"$CONFIG" init --force --start "$guarded" </dev/null >/dev/null 2>&1
check "init --force writes despite an ancestor config" "yes" \
  "$([ -f "$guarded/.sapa.yaml" ] && echo yes || echo no)"

# Task 3: --force overwrites a config in the target dir itself.
own="$root/own"
mkdir -p "$own"
printf 'base: mine\n' > "$own/.sapa.yaml"
"$CONFIG" init --force --start "$own" </dev/null >/dev/null 2>&1
overwritten=no
grep -qE "^# base:" "$own/.sapa.yaml" && overwritten=yes
check "init --force overwrites a config in place" "yes" "$overwritten"

# Task 3: on an interactive run the prompt fires; answering yes creates it,
# answering no leaves nothing behind. Driven through a pty so [ -t 0 ] is true.
run_prompt() {
  # $1 = answer fed to the prompt, $2 = target dir. Prints exit code.
  python3 - "$CONFIG" "$2" "$1" <<'PY'
import os, pty, sys
config, target, answer = sys.argv[1], sys.argv[2], sys.argv[3]
pid, fd = pty.fork()
if pid == 0:
    os.execv("/bin/bash", ["/bin/bash", config, "init", "--start", target])
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

paccept="$root/proj/feature/prompt-accept"
mkdir -p "$paccept"
run_prompt y "$paccept"
check "init prompt: yes creates the file" "yes" \
  "$([ -f "$paccept/.sapa.yaml" ] && echo yes || echo no)"

pdecline="$root/proj/feature/prompt-decline"
mkdir -p "$pdecline"
if run_prompt n "$pdecline"; then
  check "init prompt: no exits non-zero" "nonzero" "zero"
else
  check "init prompt: no exits non-zero" "nonzero" "nonzero"
fi
check "init prompt: no writes nothing" "no" \
  "$([ -f "$pdecline/.sapa.yaml" ] && echo yes || echo no)"

echo
echo "$pass/$((pass + fail)) passed"
[ "$fail" -eq 0 ]
