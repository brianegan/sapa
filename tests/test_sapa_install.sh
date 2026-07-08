#!/bin/bash
# Tests for sapa-install. Everything is sandboxed by pointing HOME at a temp dir
# so SAPA_BIN_DIR and the agent skills dirs land there — the real ~/.local/bin
# and ~/.claude are never touched.
# Run: bash tests/test_sapa_install.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
INSTALL="$HERE/../bin/sapa-install"
clone="$(cd "$HERE/.." && pwd)"

pass=0; fail=0
ok()   { echo "ok   $1"; pass=$((pass+1)); }
bad()  { echo "FAIL $1"; fail=$((fail+1)); }

root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

# A sandbox HOME with both agent homes present so auto-detect targets each.
home="$root/home"
mkdir -p "$home/.claude" "$home/.codex"
bin_dir="$home/.local/bin"

# --- install links only the sapa command, plus skills ---
out="$(HOME="$home" bash "$INSTALL" 2>&1)"; rc=$?
if [ $rc -eq 0 ]; then ok "install exits 0"; else bad "install exits 0 (rc=$rc, $out)"; fi
if [ -L "$bin_dir/sapa" ]; then ok "links sapa into ~/.local/bin"; else bad "links sapa into ~/.local/bin"; fi
if [ ! -e "$bin_dir/sapa-config" ]; then ok "does not link per-command helpers"; else bad "does not link per-command helpers"; fi
if [ -L "$home/.claude/skills/sapa-plan" ]; then ok "links a skill into claude"; else bad "links a skill into claude"; fi
if [ -L "$home/.codex/skills/sapa-plan" ]; then ok "links a skill into codex"; else bad "links a skill into codex"; fi

# Targets point back into this clone, not somewhere arbitrary.
if [ "$(readlink "$bin_dir/sapa")" = "$clone/bin/sapa" ]; then ok "sapa target points into the clone"; else bad "sapa target points into the clone ($(readlink "$bin_dir/sapa"))"; fi
if readlink "$home/.claude/skills/sapa-plan" | grep -q '/skill/sapa-plan$'; then ok "skill target points into the clone"; else bad "skill target points into the clone"; fi

# --- install prints a copy-paste-and-run completion hint (shell config untouched) ---
if printf '%s' "$out" | grep -qF "echo 'eval \"\$(sapa completion zsh)\"' >> ~/.zshrc"; then ok "install hints at completion"; else bad "install hints at completion ($out)"; fi

# --- re-running is idempotent ---
out="$(HOME="$home" bash "$INSTALL" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ -L "$bin_dir/sapa" ]; then ok "re-install is idempotent"; else bad "re-install is idempotent (rc=$rc, $out)"; fi

# --- re-running the LINKED copy on PATH installs from the original clone ---
# Regression: invoking $bin_dir/sapa (a symlink into the clone) must resolve back
# to the clone, not treat $bin_dir/.. as the source and link sapa to itself. The
# dispatcher execs sapa-install from the clone, so assert the exact clone path.
out="$(HOME="$home" bash "$bin_dir/sapa" install 2>&1)"; rc=$?
if [ $rc -eq 0 ]; then ok "re-install via linked copy exits 0"; else bad "re-install via linked copy exits 0 (rc=$rc, $out)"; fi
if [ "$(readlink "$bin_dir/sapa")" = "$clone/bin/sapa" ]; then ok "linked-copy re-install keeps sapa target in the clone"; else bad "linked-copy re-install keeps sapa target in the clone ($(readlink "$bin_dir/sapa"))"; fi

# --- install sweeps links left by the old one-per-command layout ---
# A stale legacy link pointing into a sapa clone should be removed on install;
# a foreign link and a regular file must survive.
ln -sfn "$clone/bin/sapa-config" "$bin_dir/sapa-config"   # a stale sapa link
ln -sfn /somewhere/else "$bin_dir/sapa-teardown"          # a link that isn't ours
: > "$bin_dir/sapa-start"                                 # a regular file, not ours
out="$(HOME="$home" bash "$INSTALL" 2>&1)"; rc=$?
if [ ! -e "$bin_dir/sapa-config" ]; then ok "install sweeps a stale legacy sapa link"; else bad "install sweeps a stale legacy sapa link"; fi
if [ -L "$bin_dir/sapa-teardown" ]; then ok "install leaves a foreign symlink"; else bad "install leaves a foreign symlink"; fi
if [ -f "$bin_dir/sapa-start" ]; then ok "install leaves a foreign regular file"; else bad "install leaves a foreign regular file"; fi
rm -f "$bin_dir/sapa-teardown" "$bin_dir/sapa-start"

# --- SAPA_AGENTS overrides detection: only claude linked ---
home2="$root/home2"
mkdir -p "$home2/.claude" "$home2/.codex"
out="$(HOME="$home2" SAPA_AGENTS=claude bash "$INSTALL" 2>&1)"; rc=$?
if [ -L "$home2/.claude/skills/sapa-plan" ] && [ ! -e "$home2/.codex/skills/sapa-plan" ]; then
  ok "SAPA_AGENTS targets only the named agent"
else
  bad "SAPA_AGENTS targets only the named agent (rc=$rc, $out)"
fi

# --- install no longer handles uninstall; it points at the new command ---
out="$(HOME="$home" bash "$INSTALL" uninstall 2>&1)"; rc=$?
if [ $rc -eq 2 ] && printf '%s' "$out" | grep -q "sapa uninstall"; then ok "install rejects uninstall, points at 'sapa uninstall'"; else bad "install rejects uninstall (rc=$rc, $out)"; fi

# --- run-state status hooks: wired on install, idempotent, and never touching
#     hooks the user already has (removal is covered in test_sapa_uninstall.sh) ---
# count_hook <settings> <event> <needle>: how many hook commands under <event>
# contain <needle>. The heredoc lives in the function body (parsed at definition
# time), so calling it inside $() does not hit the bash 3.2 heredoc-in-$() bug.
count_hook() {
  python3 - "$1" "$2" "$3" <<'PY'
import json, sys
f, ev, needle = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    d = json.load(open(f))
except (OSError, ValueError):
    print(0); sys.exit(0)
n = 0
for g in d.get("hooks", {}).get(ev, []):
    for h in g.get("hooks", []):
        if needle in (h.get("command") or ""):
            n += 1
print(n)
PY
}

home3="$root/home3"
mkdir -p "$home3/.claude"
# Seed a settings.json that already has a hook and a non-hook key, to prove we
# only add our own entries and disturb nothing else.
cat > "$home3/.claude/settings.json" <<'JSON'
{
  "model": "opus",
  "hooks": {
    "Stop": [ { "hooks": [ { "type": "command", "command": "keep-me.sh" } ] } ]
  }
}
JSON
sf="$home3/.claude/settings.json"

out="$(HOME="$home3" SAPA_AGENTS=claude bash "$INSTALL" 2>&1)"; rc=$?
if [ "$(count_hook "$sf" UserPromptSubmit 'status --state busy')" = "1" ] \
   && [ "$(count_hook "$sf" Notification 'status --notification')" = "1" ] \
   && [ "$(count_hook "$sf" Stop 'status --state idle')" = "1" ]; then
  ok "install wires the three run-state status hooks"
else
  bad "install wires the three run-state status hooks (rc=$rc, $out)"
fi
if printf '%s' "$out" | grep -q "wired run-state status hooks"; then ok "install reports wiring the hooks"; else bad "install reports wiring the hooks ($out)"; fi
if [ "$(count_hook "$sf" Stop 'keep-me.sh')" = "1" ]; then ok "install preserves an existing hook"; else bad "install preserves an existing hook"; fi
if [ "$(count_hook "$sf" Stop "$clone/bin/sapa status --state idle")" = "1" ]; then ok "hook command uses the absolute clone path"; else bad "hook command uses the absolute clone path"; fi
# Model key (and anything else) survives the JSON round-trip.
if grep -q '"model"' "$sf"; then ok "install leaves unrelated settings keys intact"; else bad "install leaves unrelated settings keys intact"; fi

# --- re-install does not duplicate ---
HOME="$home3" SAPA_AGENTS=claude bash "$INSTALL" >/dev/null 2>&1
if [ "$(count_hook "$sf" Stop 'status --state idle')" = "1" ] \
   && [ "$(count_hook "$sf" Stop 'keep-me.sh')" = "1" ]; then
  ok "re-install does not duplicate the status hook"
else
  bad "re-install does not duplicate the status hook (idle=$(count_hook "$sf" Stop 'status --state idle'))"
fi

# --- upgrade path: a stale old-form Notification hook is migrated, not doubled ---
# Before #60 the Notification hook ran `sapa status --state needs-you`. Re-running
# install must replace that with `status --notification`, leaving no old copy.
home4="$root/home4"
mkdir -p "$home4/.claude"
cat > "$home4/.claude/settings.json" <<JSON
{
  "hooks": {
    "Notification": [ { "hooks": [ { "type": "command", "command": "$clone/bin/sapa status --state needs-you" } ] } ]
  }
}
JSON
sf4="$home4/.claude/settings.json"
HOME="$home4" SAPA_AGENTS=claude bash "$INSTALL" >/dev/null 2>&1
if [ "$(count_hook "$sf4" Notification 'status --notification')" = "1" ] \
   && [ "$(count_hook "$sf4" Notification 'status --state needs-you')" = "0" ]; then
  ok "re-install migrates a stale old-form Notification hook to --notification"
else
  bad "stale Notification hook not migrated (new=$(count_hook "$sf4" Notification 'status --notification'), old=$(count_hook "$sf4" Notification 'status --state needs-you'))"
fi

# --- an unreadable settings.json never aborts the install (best-effort hooks) ---
# A settings.json that is somehow a directory can't be read as JSON; wiring the
# hooks must be skipped, not abort an install whose symlinks already landed.
home5="$root/home5"; mkdir -p "$home5/.claude/settings.json"
out="$(HOME="$home5" SAPA_AGENTS=claude bash "$INSTALL" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && [ -L "$home5/.claude/skills/sapa-plan" ]; then
  ok "a broken settings.json does not abort the install"
else
  bad "a broken settings.json does not abort the install (rc=$rc, $out)"
fi

# --- --help works ---
out="$(bash "$INSTALL" --help 2>&1)"; rc=$?
if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q "Usage:"; then ok "--help prints usage"; else bad "--help prints usage (rc=$rc)"; fi

echo
echo "$pass/$((pass+fail)) passed"
[ "$fail" -eq 0 ]
