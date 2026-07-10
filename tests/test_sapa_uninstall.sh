#!/bin/bash
# Tests for sapa-uninstall. Everything is sandboxed by pointing HOME at a temp dir
# so SAPA_BIN_DIR and the agent skills dirs land there — the real ~/.local/bin
# and ~/.claude are never touched. Uninstall is the inverse of install, so each
# case installs into the sandbox first, then uninstalls and checks the result.
# Run: bash tests/test_sapa_uninstall.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
INSTALL="$HERE/../bin/sapa-install"
UNINSTALL="$HERE/../bin/sapa-uninstall"
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

# --- uninstall removes sapa's links (incl. legacy) but leaves foreign files alone ---
HOME="$home" bash "$INSTALL" >/dev/null 2>&1                # create the real links
foreign="$bin_dir/other"
: > "$foreign"                                  # a regular file that isn't ours
ln -sfn /somewhere/else "$bin_dir/sapa-worktree"  # a link that isn't ours
ln -sfn "$clone/bin/sapa-start" "$bin_dir/sapa-start"  # a stale legacy link that IS ours
out="$(HOME="$home" bash "$UNINSTALL" 2>&1)"; rc=$?
if [ $rc -eq 0 ]; then ok "uninstall exits 0"; else bad "uninstall exits 0 (rc=$rc, $out)"; fi
if [ ! -e "$bin_dir/sapa" ]; then ok "uninstall removes the sapa link"; else bad "uninstall removes the sapa link"; fi
if [ ! -e "$bin_dir/sapa-start" ]; then ok "uninstall removes a legacy sapa link"; else bad "uninstall removes a legacy sapa link"; fi
if [ ! -e "$home/.claude/skills/sapa-plan" ]; then ok "uninstall removes a claude skill link"; else bad "uninstall removes a claude skill link"; fi
if [ ! -e "$home/.codex/skills/sapa-plan" ]; then ok "uninstall removes a codex skill link"; else bad "uninstall removes a codex skill link"; fi
if [ -f "$foreign" ]; then ok "uninstall leaves a foreign regular file"; else bad "uninstall leaves a foreign regular file"; fi
if [ -L "$bin_dir/sapa-worktree" ]; then ok "uninstall leaves a foreign symlink"; else bad "uninstall leaves a foreign symlink"; fi
if printf '%s' "$out" | grep -q 'sapa completion zsh'; then bad "uninstall does not print the completion hint"; else ok "uninstall does not print the completion hint"; fi

# --- SAPA_AGENTS scopes which agents uninstall touches ---
home2="$root/home2"
mkdir -p "$home2/.claude" "$home2/.codex"
HOME="$home2" bash "$INSTALL" >/dev/null 2>&1              # link into both agents
HOME="$home2" SAPA_AGENTS=claude bash "$UNINSTALL" >/dev/null 2>&1
if [ ! -e "$home2/.claude/skills/sapa-plan" ] && [ -L "$home2/.codex/skills/sapa-plan" ]; then
  ok "SAPA_AGENTS scopes uninstall to the named agent"
else
  bad "SAPA_AGENTS scopes uninstall to the named agent"
fi

# --- uninstall on a clean home is a no-op that still exits 0 ---
home3="$root/home3"
mkdir -p "$home3/.claude"
out="$(HOME="$home3" bash "$UNINSTALL" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q "removed 0 links"; then ok "uninstall on a clean home removes nothing, exits 0"; else bad "uninstall on a clean home (rc=$rc, $out)"; fi

# --- uninstall removes the run-state status hooks it added, leaving others ---
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

home4="$root/home4"; mkdir -p "$home4/.claude"
cat > "$home4/.claude/settings.json" <<'JSON'
{ "hooks": { "Stop": [ { "hooks": [ { "type": "command", "command": "keep-me.sh" } ] } ] } }
JSON
sf="$home4/.claude/settings.json"
HOME="$home4" SAPA_AGENTS=claude bash "$INSTALL" >/dev/null 2>&1     # wires our hooks
HOME="$home4" SAPA_AGENTS=claude bash "$UNINSTALL" >/dev/null 2>&1   # should unwire them
if [ "$(count_hook "$sf" Stop 'status --state idle')" = "0" ] \
   && [ "$(count_hook "$sf" UserPromptSubmit 'status --state busy')" = "0" ] \
   && [ "$(count_hook "$sf" Notification 'status --notification')" = "0" ] \
   && [ "$(count_hook "$sf" PreToolUse 'status --active')" = "0" ]; then
  ok "uninstall removes our status hooks"
else
  bad "uninstall removes our status hooks"
fi
if [ "$(count_hook "$sf" Stop 'keep-me.sh')" = "1" ]; then ok "uninstall preserves an existing hook"; else bad "uninstall preserves an existing hook"; fi

# --- uninstall with no settings.json present never creates one ---
home5="$root/home5"; mkdir -p "$home5/.claude"
HOME="$home5" SAPA_AGENTS=claude bash "$UNINSTALL" >/dev/null 2>&1
if [ ! -e "$home5/.claude/settings.json" ]; then ok "uninstall does not create a settings.json"; else bad "uninstall does not create a settings.json"; fi

# --- unknown argument errors ---
out="$(bash "$UNINSTALL" bogus 2>&1)"; rc=$?
if [ $rc -eq 2 ] && printf '%s' "$out" | grep -q "unknown argument"; then ok "unknown argument exits 2"; else bad "unknown argument exits 2 (rc=$rc, $out)"; fi

# --- --help works ---
out="$(bash "$UNINSTALL" --help 2>&1)"; rc=$?
if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q "Usage:"; then ok "--help prints usage"; else bad "--help prints usage (rc=$rc)"; fi

echo
echo "$pass/$((pass+fail)) passed"
[ "$fail" -eq 0 ]
