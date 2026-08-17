#!/bin/bash
# Tests for sapa-worktree, covering how it decides whether to open the new tree.
#
# Opening is opt-in through `opener:` in the personal settings, so HOME is
# sandboxed for the whole file: a developer running this with a real editor
# configured must not have a window opened on a temp worktree.
# Run: bash tests/test_sapa_worktree.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORKTREE="$HERE/../bin/sapa-worktree"
BOOTSTRAP="$HERE/../bin/sapa-bootstrap"
# Put bin on PATH so sapa-worktree can resolve sapa-settings for the opener key.
export PATH="$HERE/../bin:$PATH"

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
export HOME="$root/home"
mkdir -p "$HOME"

# A project in the bare layout with a real local origin to fetch from, built the
# way sapa itself builds one.
mkdir -p "$root/sources"
src="$root/sources/app"
git init -q -b main "$src"
# Two tracked .txt files, so every worktree checked out below contains something
# for a `*.txt` to match. The glob case at the bottom needs them present in the
# new worktree itself, which is the directory the editor command expands in.
printf 'decoy\n' > "$src/decoy-a.txt"
printf 'decoy\n' > "$src/decoy-b.txt"
git -C "$src" add decoy-a.txt decoy-b.txt
git -C "$src" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -q -m init
( cd "$root" && bash "$BOOTSTRAP" "$src" >/dev/null 2>&1 )
proj="$root/app"

# An editor stand-in that records the arguments it was handed instead of opening
# anything.
opened="$root/opened"
editor_stub="$root/editor-stub"
printf '#!/bin/bash\nprintf "%%s\\n" "$*" >> "%s"\n' "$opened" > "$editor_stub"
chmod +x "$editor_stub"
: > "$opened"

# --- with no settings, the path is printed and nothing is opened ---
# $EDITOR is deliberately set here: it used to drive this, and no longer does.
out="$(cd "$proj/main" && EDITOR="$editor_stub" VISUAL="$editor_stub" bash "$WORKTREE" plain 2>/dev/null | tail -1)"
check "prints the worktree path when no opener is set" "$proj/plain" "$out"
check "\$EDITOR no longer opens anything" "" "$(cat "$opened")"

# --- the former `editor:` key is ignored ---
mkdir -p "$HOME/.sapa"
printf 'editor: %s\n' "$editor_stub" > "$HOME/.sapa/settings.yaml"
: > "$opened"
out="$(cd "$proj/main" && bash "$WORKTREE" legacy 2>/dev/null | tail -1)"
check "prints the worktree path for the former editor key" "$proj/legacy" "$out"
check "the former editor key opens nothing" "" "$(cat "$opened")"

# --- with `opener:` set, the configured command runs on the new worktree ---
printf 'opener: %s\n' "$editor_stub" > "$HOME/.sapa/settings.yaml"
: > "$opened"
( cd "$proj/main" && bash "$WORKTREE" configured >/dev/null 2>&1 )
check "runs the configured opener on the worktree" "$proj/configured" "$(cat "$opened")"

# --- a multi-word `opener:` splits into a command and its flags ---
printf 'opener: %s -n --wait\n' "$editor_stub" > "$HOME/.sapa/settings.yaml"
: > "$opened"
( cd "$proj/main" && bash "$WORKTREE" flags >/dev/null 2>&1 )
check "passes the editor's own flags through" "-n --wait $proj/flags" "$(cat "$opened")"

# --- a quoted value works too, since YAML allows it and the read is a grep ---
printf 'opener: "%s"\n' "$editor_stub" > "$HOME/.sapa/settings.yaml"
: > "$opened"
( cd "$proj/main" && bash "$WORKTREE" quoted >/dev/null 2>&1 )
check "strips quotes around the editor value" "$proj/quoted" "$(cat "$opened")"

# --- the editor value splits on spaces but is not globbed ---
# Splitting is the whole contract; expanding `*` against whatever sits in the
# current directory is not, and would hand the editor a directory listing.
printf 'opener: %s -x *.txt\n' "$editor_stub" > "$HOME/.sapa/settings.yaml"
: > "$opened"
( cd "$proj/main" && bash "$WORKTREE" globby >/dev/null 2>&1 )
check "the editor value is split but not globbed" "-x *.txt $proj/globby" "$(cat "$opened")"

# --- a commented-out `opener:` is not a setting ---
# The template ships every key commented, so a fresh `sapa settings init` must
# leave opening switched off rather than trying to run `# opener: code -n`.
"$HERE/../bin/sapa-settings" init --force >/dev/null
: > "$opened"
out="$(cd "$proj/main" && bash "$WORKTREE" fromtemplate 2>/dev/null | tail -1)"
check "the starter template opens nothing" "$proj/fromtemplate" "$out"
check "the starter template runs no editor" "" "$(cat "$opened")"
rm -f "$HOME/.sapa/settings.yaml"

# --- the worktree is created either way ---
for name in plain legacy configured flags quoted globby fromtemplate; do
  if [ -d "$proj/$name" ]; then
    ok "created the $name worktree"
  else
    bad "created the $name worktree"
  fi
done

# --- the default path branches from the configured `base`, not a hardcoded main ---
# Give origin a second branch with a marker commit, so the test can tell which
# ref the new worktree actually started from.
git -C "$src" checkout -q -b develop
printf 'develop-marker\n' > "$src/develop-marker.txt"
git -C "$src" add develop-marker.txt
git -C "$src" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -q -m develop
git -C "$src" checkout -q main

printf 'base: develop\n' > "$proj/.sapa.yaml"
( cd "$proj/main" && bash "$WORKTREE" frombase >/dev/null 2>&1 )
check "default path branches from the configured base" \
  "$(git -C "$src" rev-parse develop)" \
  "$(git -C "$proj/frombase" rev-parse HEAD 2>/dev/null)"
rm -f "$proj/.sapa.yaml"

# --- the default path fetches and branches from the configured `remote`, not origin ---
# A second remote with its own main, distinct from origin's, so the test can
# tell which remote the worktree actually started from.
upstream_src="$root/sources/upstream"
git init -q -b main "$upstream_src"
printf 'upstream-marker\n' > "$upstream_src/upstream-marker.txt"
git -C "$upstream_src" add upstream-marker.txt
git -C "$upstream_src" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -q -m upstream
git -C "$proj/main" remote add upstream "$upstream_src"

printf 'remote: upstream\n' > "$proj/.sapa.yaml"
( cd "$proj/main" && bash "$WORKTREE" fromremote >/dev/null 2>&1 )
check "default path fetches and branches from the configured remote" \
  "$(git -C "$upstream_src" rev-parse main)" \
  "$(git -C "$proj/fromremote" rev-parse HEAD 2>/dev/null)"
rm -f "$proj/.sapa.yaml"

# --- the default path does not track the branch it started from ---
( cd "$proj/main" && bash "$WORKTREE" notrack >/dev/null 2>&1 )
if git -C "$proj/notrack" rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
  bad "default path worktree has no upstream"
else
  ok "default path worktree has no upstream"
fi

# --- an explicit start point still tracks it, same as before this fix ---
( cd "$proj/main" && bash "$WORKTREE" tracked origin/main >/dev/null 2>&1 )
check "explicit start point still tracks it" \
  "origin/main" \
  "$(git -C "$proj/tracked" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)"

# --- a remote-qualified branch name (no separate start-point arg) also still tracks it ---
git -C "$src" checkout -q -b topic
printf 'topic-marker\n' > "$src/topic-marker.txt"
git -C "$src" add topic-marker.txt
git -C "$src" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -q -m topic
git -C "$src" checkout -q main
( cd "$proj/main" && bash "$WORKTREE" origin/topic >/dev/null 2>&1 )
check "a remote-qualified branch name still tracks it" \
  "origin/topic" \
  "$(git -C "$proj/topic" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)"

# --- a missing branch name is a usage error ---
out="$(cd "$proj/main" && bash "$WORKTREE" 2>&1)"; rc=$?
if [ $rc -eq 2 ] && grep -q "expected a branch name" <<<"$out"; then
  ok "no branch name exits 2"
else
  bad "no branch name exits 2 (rc=$rc, $out)"
fi

echo
echo "$pass/$((pass + fail)) passed"
[ "$fail" -eq 0 ]
