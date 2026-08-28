#!/bin/bash
# Tests for sapa-teardown against a real bare-layout repo in a temp dir.
# Run: bash tests/test_sapa_teardown.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TEARDOWN="$HERE/../bin/sapa-teardown"
# Put bin on PATH so teardown can resolve sapa-settings for the closer key.
export PATH="$HERE/../bin:$PATH"

pass=0; fail=0
ok()   { echo "ok   $1"; pass=$((pass+1)); }
bad()  { echo "FAIL $1"; fail=$((fail+1)); }

check_failed_project_hook() {
  local name="$1" force_arg="$2" make_dirty="$3" label="$4"
  local hook_status_dir out rc

  hook_status_dir="$(mktemp -d)"
  git -C "$proj/main" worktree add -q "$proj/$name" -b "$name"
  if $make_dirty; then
    printf 'wip\n' > "$proj/$name/scratch.txt"
  fi
  printf 'teardown: /bin/false\n' > "$proj/.sapa.yaml"
  SAPA_STATUS_DIR="$hook_status_dir" "$HERE/../bin/sapa-status" --stage watch --start "$proj/$name"
  : > "$recorded"
  if [ -n "$force_arg" ]; then
    out="$(SAPA_STATUS_DIR="$hook_status_dir" bash "$TEARDOWN" "$force_arg" "$proj/$name" 2>&1)"; rc=$?
  else
    out="$(SAPA_STATUS_DIR="$hook_status_dir" bash "$TEARDOWN" "$proj/$name" 2>&1)"; rc=$?
  fi
  if [ $rc -ne 0 ] && [ -d "$proj/$name" ] \
    && git -C "$proj/main" branch --list "$name" | grep -q "$name" \
    && [ -e "$hook_status_dir/$name.json" ] && [ ! -s "$recorded" ]; then
    ok "$label"
  else
    bad "$label (rc=$rc, out=$out)"
  fi
  rm -f "$proj/.sapa.yaml"
  if $make_dirty; then
    bash "$TEARDOWN" --force "$proj/$name" >/dev/null 2>&1
  else
    bash "$TEARDOWN" "$proj/$name" >/dev/null 2>&1
  fi
  rm -rf "$hook_status_dir"
}

# Build a bare-layout project: root/.bare + a main worktree + a feature worktree.
root="$(mktemp -d)"

# Sandbox HOME for the whole file. Teardown reads `closer:` from
# ~/.sapa/settings.yaml, so a developer running this with a real closer
# configured would otherwise have it fire against their own live editor.
export HOME="$root/home"
mkdir -p "$HOME"

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

trap 'rm -rf "$root" "$closer" "$recorded" "$argrec"' EXIT
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
# The configured closer runs with the worktree's basename.
if grep -qx "feature" "$recorded"; then ok "runs the configured closer"; else bad "runs the configured closer (recorded: $(cat "$recorded"))"; fi

# --- a project teardown command runs before the worktree is removed ---
hook_record="$(mktemp)"
git -C "$proj/main" worktree add -q "$proj/hooked" -b hooked
printf 'teardown: |\n  test -d "$PWD" && pwd > "%s"\n' "$hook_record" > "$proj/.sapa.yaml"
out="$(bash "$TEARDOWN" "$proj/hooked" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ ! -d "$proj/hooked" ] && grep -qx "$proj/hooked" "$hook_record"; then
  ok "runs a block-scalar project command before removal"
else
  bad "runs a block-scalar project command before removal (rc=$rc, out=$out, recorded: $(cat "$hook_record"))"
fi

# YAML quoting and escapes are decoded before the command reaches the shell.
yaml_escape_record="$(mktemp)"
git -C "$proj/main" worktree add -q "$proj/yaml-escaped" -b yaml-escaped
printf 'teardown: "touch\\u0020%s"\n' "$yaml_escape_record" > "$proj/.sapa.yaml"
out="$(bash "$TEARDOWN" "$proj/yaml-escaped" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ ! -d "$proj/yaml-escaped" ] && [ -e "$yaml_escape_record" ]; then
  ok "decodes a quoted YAML command before running it"
else
  bad "decodes a quoted YAML command before running it (rc=$rc, out=$out)"
fi
rm -f "$yaml_escape_record"

# Shell operators in the config value work, and the personal closer still runs
# after the project hook and worktree removal.
order_record="$(mktemp)"
ordering_closer="$(mktemp)"
cat > "$ordering_closer" <<EOF
#!/bin/bash
if [ ! -d "$proj/ordered" ]; then
  printf '%s\n' 'closer-after-removal' >> "$order_record"
fi
EOF
chmod +x "$ordering_closer"
git -C "$proj/main" worktree add -q "$proj/ordered" -b ordered
printf 'teardown: test "$PWD" = "%s" && printf "%%s\\n" hook-before-removal >> "%s"\n' \
  "$proj/ordered" "$order_record" > "$proj/.sapa.yaml"
out="$(SAPA_TEARDOWN_CLOSER="$ordering_closer" bash "$TEARDOWN" "$proj/ordered" 2>&1)"; rc=$?
expected_order="$(printf 'hook-before-removal\ncloser-after-removal')"
if [ $rc -eq 0 ] && [ "$(cat "$order_record")" = "$expected_order" ]; then
  ok "runs shell commands in the worktree before the personal closer"
else
  bad "runs shell commands in the worktree before the personal closer (rc=$rc, out=$out, order: $(cat "$order_record"))"
fi
rm -f "$order_record" "$ordering_closer"

# --force bypasses the dirty guard but still runs project cleanup.
force_record="$(mktemp)"
git -C "$proj/main" worktree add -q "$proj/hook-forced" -b hook-forced
printf 'wip\n' > "$proj/hook-forced/scratch.txt"
printf 'teardown: pwd > "%s"\n' "$force_record" > "$proj/.sapa.yaml"
out="$(bash "$TEARDOWN" --force "$proj/hook-forced" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ ! -d "$proj/hook-forced" ] && grep -qx "$proj/hook-forced" "$force_record"; then
  ok "force teardown still runs the project command"
else
  bad "force teardown still runs the project command (rc=$rc, out=$out, recorded: $(cat "$force_record"))"
fi
rm -f "$force_record"

check_failed_project_hook \
  hook-force-failed --force true \
  "force does not override a failed project command"
check_failed_project_hook \
  hook-failed "" false \
  "a failed project teardown command preserves the whole stream"
rm -f "$hook_record"

# An existing project config without the opt-in key remains a no-op even when
# PyYAML is unavailable, because there is no YAML command to decode.
noyaml_dir="$(mktemp -d)"
printf 'raise ImportError("no pyyaml here")\n' > "$noyaml_dir/yaml.py"
git -C "$proj/main" worktree add -q "$proj/no-project-hook" -b no-project-hook
printf 'base: main\n' > "$proj/.sapa.yaml"
out="$(PYTHONPATH="$noyaml_dir" bash "$TEARDOWN" "$proj/no-project-hook" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ ! -d "$proj/no-project-hook" ]; then
  ok "a config without teardown changes nothing"
else
  bad "a config without teardown changes nothing (rc=$rc, out=$out)"
fi
rm -f "$proj/.sapa.yaml"
rm -rf "$noyaml_dir"

# YAML key spelling is decoded by the same parser as the command value.
quoted_key_record="$(mktemp)"
git -C "$proj/main" worktree add -q "$proj/quoted-hook-key" -b quoted-hook-key
printf '"teardown": touch "%s"\n' "$quoted_key_record" > "$proj/.sapa.yaml"
out="$(bash "$TEARDOWN" "$proj/quoted-hook-key" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ ! -d "$proj/quoted-hook-key" ] && [ -e "$quoted_key_record" ]; then
  ok "decodes a quoted YAML teardown key"
else
  bad "decodes a quoted YAML teardown key (rc=$rc, out=$out)"
fi
rm -f "$proj/.sapa.yaml" "$quoted_key_record"

# --- dirty worktree is refused ---
git -C "$proj/main" worktree add -q "$proj/dirty" -b dirty
printf 'wip\n' > "$proj/dirty/scratch.txt"
dirty_hook_record="$(mktemp)"
printf 'teardown: touch "%s"\n' "$dirty_hook_record" > "$proj/.sapa.yaml"
rm -f "$dirty_hook_record"
out="$(bash "$TEARDOWN" "$proj/dirty" 2>&1)"; rc=$?
if [ $rc -eq 3 ] && [ -d "$proj/dirty" ] && [ ! -e "$dirty_hook_record" ]; then
  ok "refuses dirty worktree before running the project command"
else
  bad "refuses dirty worktree before running the project command (rc=$rc, $out)"
fi
# The refusal names both spellings of the escape hatch.
if grep -q -- "-f/--force" <<<"$out"; then ok "refusal hint names -f and --force"; else bad "refusal hint names -f and --force ($out)"; fi
rm -f "$proj/.sapa.yaml" "$dirty_hook_record"

# --- --force removes a dirty worktree ---
out="$(bash "$TEARDOWN" --force "$proj/dirty" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ ! -d "$proj/dirty" ]; then ok "force removes dirty worktree"; else bad "force removes dirty worktree ($out)"; fi

# --- -f is a shorthand for --force ---
git -C "$proj/main" worktree add -q "$proj/dirty-short" -b dirty-short
printf 'wip\n' > "$proj/dirty-short/scratch.txt"
out="$(bash "$TEARDOWN" -f "$proj/dirty-short" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ ! -d "$proj/dirty-short" ]; then ok "-f removes dirty worktree"; else bad "-f removes dirty worktree (rc=$rc, $out)"; fi

# --- works when invoked from inside the target worktree ---
git -C "$proj/main" worktree add -q "$proj/inside" -b inside
out="$(cd "$proj/inside" && bash "$TEARDOWN" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ ! -d "$proj/inside" ]; then ok "removes cwd worktree from within"; else bad "removes cwd worktree from within (rc=$rc, $out)"; fi

# --- with no closer configured at all, nothing is closed ---
# Closing is opt-in: no settings file and no override means teardown removes the
# worktree and leaves every window alone.
#
# Watching only the stub above would not prove that. It stays silent whether
# teardown ran nothing or reached for some *other* closer, and a teardown that
# quietly fell back to a built-in default would drive a developer's real editor
# while the test still passed. So shadow the shipped closer on PATH with a
# recorder and require that it, too, was never called.
shadow_bin="$root/shadow-bin"
shadowed="$root/shadowed"
mkdir -p "$shadow_bin"
for name in sapa sapa-close; do
  printf '#!/bin/bash\nprintf "%%s\\n" "$*" >> "%s"\n' "$shadowed" > "$shadow_bin/$name"
  chmod +x "$shadow_bin/$name"
done
: > "$shadowed"

git -C "$proj/main" worktree add -q "$proj/noclose" -b noclose
: > "$recorded"
out="$(PATH="$shadow_bin:$PATH" env -u SAPA_TEARDOWN_CLOSER bash "$TEARDOWN" "$proj/noclose" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ ! -d "$proj/noclose" ] && [ ! -s "$recorded" ] && [ ! -s "$shadowed" ]; then
  ok "no closer configured closes nothing"
else
  bad "no closer configured closes nothing (rc=$rc, recorded: $(cat "$recorded"), shadowed: $(cat "$shadowed"))"
fi

# --- a `closer:` in the personal settings is read and run ---
mkdir -p "$HOME/.sapa"
printf 'closer: %s\n' "$closer" > "$HOME/.sapa/settings.yaml"
git -C "$proj/main" worktree add -q "$proj/fromsettings" -b fromsettings
: > "$recorded"
out="$(env -u SAPA_TEARDOWN_CLOSER bash "$TEARDOWN" "$proj/fromsettings" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && grep -qx "fromsettings" "$recorded"; then
  ok "runs the closer from settings"
else
  bad "runs the closer from settings (rc=$rc, recorded: $(cat "$recorded"))"
fi

# A quoted value works too, since YAML allows it and the read is a grep.
git -C "$proj/main" worktree add -q "$proj/quoted" -b quoted
printf 'closer: "%s"\n' "$closer" > "$HOME/.sapa/settings.yaml"
: > "$recorded"
out="$(env -u SAPA_TEARDOWN_CLOSER bash "$TEARDOWN" "$proj/quoted" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && grep -qx "quoted" "$recorded"; then
  ok "strips quotes around the closer value"
else
  bad "strips quotes around the closer value (rc=$rc, recorded: $(cat "$recorded"))"
fi

# --- a multi-word closer keeps its arguments (this is how `sapa close code` runs) ---
# Records every argument it was handed, so these cases can assert on the whole
# argument list rather than just the basename.
argrec="$(mktemp)"
printf '#!/bin/bash\nprintf "%%s\\n" "$*" >> "%s"\n' "$recorded" > "$argrec"
chmod +x "$argrec"
git -C "$proj/main" worktree add -q "$proj/multiword" -b multiword
printf 'closer: %s code\n' "$argrec" > "$HOME/.sapa/settings.yaml"
: > "$recorded"
out="$(env -u SAPA_TEARDOWN_CLOSER bash "$TEARDOWN" "$proj/multiword" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && grep -qx "code multiword" "$recorded"; then
  ok "a multi-word closer keeps its own arguments"
else
  bad "a multi-word closer keeps its own arguments (rc=$rc, recorded: $(cat "$recorded"))"
fi

# --- the closer value splits on spaces but is not globbed ---
git -C "$proj/main" worktree add -q "$proj/globby" -b globby
printf 'closer: %s -x *.txt\n' "$argrec" > "$HOME/.sapa/settings.yaml"
: > "$recorded"
out="$(cd "$proj/main" && touch decoy-a.txt decoy-b.txt \
       && env -u SAPA_TEARDOWN_CLOSER bash "$TEARDOWN" "$proj/globby" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && grep -Fqx -- "-x *.txt globby" "$recorded"; then
  ok "the closer value is split but not globbed"
else
  bad "the closer value is split but not globbed (rc=$rc, recorded: $(cat "$recorded"))"
fi
rm -f "$proj/main/decoy-a.txt" "$proj/main/decoy-b.txt"

# --- settings are read even when sapa-settings is not on PATH (sibling fallback) ---
git -C "$proj/main" worktree add -q "$proj/nopath" -b nopath
printf 'closer: %s\n' "$closer" > "$HOME/.sapa/settings.yaml"
: > "$recorded"
out="$(PATH=/usr/bin:/bin env -u SAPA_TEARDOWN_CLOSER bash "$TEARDOWN" "$proj/nopath" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && grep -qx "nopath" "$recorded"; then
  ok "reads the closer without sapa-settings on PATH"
else
  bad "reads the closer without sapa-settings on PATH (rc=$rc, recorded: $(cat "$recorded"))"
fi

# --- the env override beats a configured closer ---
override="$(mktemp)"
overrode="$(mktemp)"
printf '#!/bin/bash\nprintf "%%s\\n" "$1" >> "%s"\n' "$overrode" > "$override"
chmod +x "$override"
git -C "$proj/main" worktree add -q "$proj/override" -b override
: > "$recorded"
out="$(SAPA_TEARDOWN_CLOSER="$override" bash "$TEARDOWN" "$proj/override" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && grep -qx "override" "$overrode" && [ ! -s "$recorded" ]; then
  ok "SAPA_TEARDOWN_CLOSER beats the settings closer"
else
  bad "SAPA_TEARDOWN_CLOSER beats the settings closer (rc=$rc, recorded: $(cat "$recorded"))"
fi
rm -f "$override" "$overrode"
rm -f "$HOME/.sapa/settings.yaml"

# --- a failing closer never fails the teardown ---
git -C "$proj/main" worktree add -q "$proj/badcloser" -b badcloser
out="$(SAPA_TEARDOWN_CLOSER=/bin/false bash "$TEARDOWN" "$proj/badcloser" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ ! -d "$proj/badcloser" ]; then ok "failing closer does not fail teardown"; else bad "failing closer does not fail teardown (rc=$rc, $out)"; fi

# --- a denied close (no Accessibility) surfaces a hint but still succeeds ---
git -C "$proj/main" worktree add -q "$proj/denied" -b denied
denier="$(mktemp)"
printf '#!/bin/bash\necho "error:-25211"\n' > "$denier"; chmod +x "$denier"
err="$(SAPA_TEARDOWN_CLOSER="$denier" bash "$TEARDOWN" "$proj/denied" 2>&1 >/dev/null)"; rc=$?
if [ $rc -eq 0 ] && [ ! -d "$proj/denied" ] && grep -qi "Accessibility" <<<"$err"; then
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
