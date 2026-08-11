#!/bin/bash
# Tests for sapa-worktree, covering how it decides whether to open the new tree.
#
# Opening is opt-in through `editor:` in the personal settings, so HOME is
# sandboxed for the whole file: a developer running this with a real editor
# configured must not have a window opened on a temp worktree.
# Run: bash tests/test_sapa_worktree.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORKTREE="$HERE/../bin/sapa-worktree"
BOOTSTRAP="$HERE/../bin/sapa-bootstrap"
# Put bin on PATH so sapa-worktree can resolve sapa-settings for the editor key.
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
check "prints the worktree path when no editor is set" "$proj/plain" "$out"
check "\$EDITOR no longer opens anything" "" "$(cat "$opened")"

# --- with `editor:` set, the configured command runs on the new worktree ---
mkdir -p "$HOME/.sapa"
printf 'editor: %s\n' "$editor_stub" > "$HOME/.sapa/settings.yaml"
: > "$opened"
( cd "$proj/main" && bash "$WORKTREE" configured >/dev/null 2>&1 )
check "runs the configured editor on the worktree" "$proj/configured" "$(cat "$opened")"

# --- a multi-word `editor:` splits into a command and its flags ---
printf 'editor: %s -n --wait\n' "$editor_stub" > "$HOME/.sapa/settings.yaml"
: > "$opened"
( cd "$proj/main" && bash "$WORKTREE" flags >/dev/null 2>&1 )
check "passes the editor's own flags through" "-n --wait $proj/flags" "$(cat "$opened")"

# --- a quoted value works too, since YAML allows it and the read is a grep ---
printf 'editor: "%s"\n' "$editor_stub" > "$HOME/.sapa/settings.yaml"
: > "$opened"
( cd "$proj/main" && bash "$WORKTREE" quoted >/dev/null 2>&1 )
check "strips quotes around the editor value" "$proj/quoted" "$(cat "$opened")"

# --- the editor value splits on spaces but is not globbed ---
# Splitting is the whole contract; expanding `*` against whatever sits in the
# current directory is not, and would hand the editor a directory listing.
printf 'editor: %s -x *.txt\n' "$editor_stub" > "$HOME/.sapa/settings.yaml"
: > "$opened"
( cd "$proj/main" && bash "$WORKTREE" globby >/dev/null 2>&1 )
check "the editor value is split but not globbed" "-x *.txt $proj/globby" "$(cat "$opened")"

# --- a commented-out `editor:` is not a setting ---
# The template ships every key commented, so a fresh `sapa settings init` must
# leave opening switched off rather than trying to run `# editor: code -n`.
"$HERE/../bin/sapa-settings" init --force >/dev/null
: > "$opened"
out="$(cd "$proj/main" && bash "$WORKTREE" fromtemplate 2>/dev/null | tail -1)"
check "the starter template opens nothing" "$proj/fromtemplate" "$out"
check "the starter template runs no editor" "" "$(cat "$opened")"
rm -f "$HOME/.sapa/settings.yaml"

# --- the worktree is created either way ---
for name in plain configured flags quoted globby fromtemplate; do
  if [ -d "$proj/$name" ]; then
    ok "created the $name worktree"
  else
    bad "created the $name worktree"
  fi
done

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
