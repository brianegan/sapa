#!/usr/bin/env python3
"""Tests for sapa-issue: issue-identity derivation and plan-comment plumbing.

Run: python3 tests/test_sapa_issue.py

Two layers, matching the PRD testing philosophy:
  * pure functions (branch->identity, ADF flattening, marker injection) are unit
    tested by importing the helper directly;
  * the plan-comment command surface is tested against stubbed `gh` and `acli` on
    PATH — the same way the rest of bin/ is tested — with a JSON file standing in
    for each backend's comment store, asserting on what got created/read/deleted.
"""

import atexit
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
ISSUE = os.path.join(HERE, "..", "bin", "sapa-issue")
# Load the extensionless helper as a module (exec_module, not the deprecated
# load_module) so we can unit-test its pure functions directly.
_spec = importlib.util.spec_from_loader("sapa_issue", SourceFileLoader("sapa_issue", ISSUE))
si = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(si)

_TMP = []  # temp dirs to sweep at exit so the suite leaves nothing behind
atexit.register(lambda: [shutil.rmtree(p, ignore_errors=True) for p in _TMP])


def write(path, text):
    with open(path, "w") as f:
        f.write(text)

pass_ = 0
fail = 0


def check(name, expected, got):
    global pass_, fail
    if expected == got:
        print(f"ok   {name}")
        pass_ += 1
    else:
        print(f"FAIL {name}: expected {expected!r} got {got!r}")
        fail += 1


def check_true(name, cond):
    check(name, True, bool(cond))


# --- unit: branch -> identity ------------------------------------------------

check("github number from branch", ("github", "77"),
      si.derive_identity("77-jira-support"))
check("bare github number", ("github", "42"), si.derive_identity("42"))
check("jira key upper-cased", ("jira", "GP-1"),
      si.derive_identity("gp-1-jira-support"))
check("jira key already upper", ("jira", "GP-12"),
      si.derive_identity("GP-12"))
try:
    si.derive_identity("not-an-issue")
    check("junk branch rejected", "raise", "no-raise")
except SystemExit:
    check_true("junk branch rejected", True)


# --- unit: ADF flattening keeps list items (acli's own flatten drops them) ----

doc = {"type": "doc", "version": 1, "content": [
    {"type": "heading", "attrs": {"level": 2},
     "content": [{"type": "text", "text": "Goal"}]},
    {"type": "paragraph", "content": [{"type": "text", "text": "Ship it."}]},
    {"type": "bulletList", "content": [
        {"type": "listItem", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "one"}]}]},
        {"type": "listItem", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "two"}]}]},
    ]},
]}
flat = si.adf_text(doc)
check("adf flatten keeps heading", True, "Goal" in flat)
check("adf flatten keeps both bullets", True,
      "- one" in flat and "- two" in flat)


# --- unit: marker injection --------------------------------------------------

injected = json.loads(si.jira_inject_marker(json.dumps(doc)))
check("marker prepended as first node", "paragraph",
      injected["content"][0]["type"])
check_true("marker carries the token",
           si.PLAN_TOKEN in injected["content"][0]["content"][0]["text"])
check_true("original content preserved after marker",
           len(injected["content"]) == len(doc["content"]) + 1)
try:
    si.jira_inject_marker('{"not":"a doc"}')
    check("non-doc ADF rejected", "raise", "no-raise")
except SystemExit:
    check_true("non-doc ADF rejected", True)


# --- command surface: stubbed backends --------------------------------------

GH_STUB = r'''#!/usr/bin/env python3
import json, os, re, sys
store = os.environ["SAPA_TEST_STORE"]
def load():
    with open(store) as f: return json.load(f)
def save(d):
    with open(store, "w") as f: json.dump(d, f)
a = sys.argv[1:]
d = load()
MARK = "<!-- sapa:plan"  # prefix: matches both new and legacy hash= markers
# gh api .../comments --paginate --jq '... contains(...) ... .id'
if a[:1] == ["api"] and a[-2] == "--jq" and a[1].endswith("/comments"):
    for c in d["gh"]:
        if MARK in c["body"]:
            print(c["id"])
    sys.exit(0)
# gh api .../comments/<id> --jq .body
if a[:1] == ["api"] and a[-2:] == ["--jq", ".body"]:
    cid = a[1].rstrip("/").split("/")[-1]
    for c in d["gh"]:
        if str(c["id"]) == cid: print(c["body"]); sys.exit(0)
    sys.exit(1)
# gh api --method PATCH .../comments/<id> -F body=@FILE
if a[:3] == ["api", "--method", "PATCH"]:
    cid = a[3].rstrip("/").split("/")[-1]
    path = a[a.index("-F") + 1].split("body=@", 1)[1]
    body = open(path).read()
    for c in d["gh"]:
        if str(c["id"]) == cid: c["body"] = body
    save(d); sys.exit(0)
# gh issue comment <N> --body-file FILE
if a[:2] == ["issue", "comment"]:
    path = a[a.index("--body-file") + 1]
    d["gh"].append({"id": d["next"], "body": open(path).read()})
    d["next"] += 1
    save(d); sys.exit(0)
sys.exit(0)
'''

ACLI_STUB = r'''#!/usr/bin/env python3
import json, os, sys
store = os.environ["SAPA_TEST_STORE"]
def load():
    with open(store) as f: return json.load(f)
def save(d):
    with open(store, "w") as f: json.dump(d, f)
a = sys.argv[1:]
d = load()
# acli jira workitem view KEY --json --fields comment
if a[:3] == ["jira", "workitem", "view"] and "comment" in a:
    print(json.dumps({"fields": {"comment": {"comments": d["jira"]}}}))
    sys.exit(0)
# acli jira workitem comment create --key K --body-file F
if a[:4] == ["jira", "workitem", "comment", "create"]:
    path = a[a.index("--body-file") + 1]
    raw = open(path).read()
    try: body = json.loads(raw)   # acli create renders ADF; plain text stays text
    except json.JSONDecodeError: body = raw
    d["jira"].append({"id": d["next"], "body": body})
    d["next"] += 1
    save(d); sys.exit(0)
# acli jira workitem comment delete --key K --id ID
if a[:4] == ["jira", "workitem", "comment", "delete"]:
    cid = a[a.index("--id") + 1]
    d["jira"] = [c for c in d["jira"] if str(c["id"]) != cid]
    save(d); sys.exit(0)
sys.exit(0)
'''


def with_stubs():
    """Return (dir, env) with gh+acli stubs on PATH and a fresh store."""
    d = tempfile.mkdtemp()
    _TMP.append(d)
    bindir = os.path.join(d, "bin")
    os.mkdir(bindir)
    for name, body in (("gh", GH_STUB), ("acli", ACLI_STUB)):
        p = os.path.join(bindir, name)
        with open(p, "w") as f:
            f.write(body)
        os.chmod(p, 0o755)
    store = os.path.join(d, "store.json")
    with open(store, "w") as f:
        json.dump({"gh": [], "jira": [], "next": 100}, f)
    env = dict(os.environ)
    env["PATH"] = bindir + os.pathsep + env["PATH"]
    env["SAPA_TEST_STORE"] = store
    return d, env, store


def issue(env, *args):
    return subprocess.run([sys.executable, ISSUE, *args],
                          capture_output=True, text=True, env=env)


def load_store(store):
    with open(store) as f:
        return json.load(f)


# GitHub path: create -> read -> update (patch in place, no duplicate).
d, env, store = with_stubs()
md = os.path.join(d, "plan.md")
write(md, "## Plan\n\n- do the thing\n")
issue(env, "plan-comment", "--content-file", md, "--branch", "77-feature")
gh = load_store(store)["gh"]
check("github: one comment created", 1, len(gh))
check_true("github: marker wraps the body",
           gh[0]["body"].startswith(si.GH_OPEN) and si.GH_CLOSE in gh[0]["body"])
check_true("github: content present", "do the thing" in gh[0]["body"])
r = issue(env, "plan-comment", "--read", "--branch", "77-feature")
check_true("github: read returns the body", "do the thing" in r.stdout)
write(md, "## Plan v2\n\n- revised\n")
issue(env, "plan-comment", "--content-file", md, "--branch", "77-feature")
gh = load_store(store)["gh"]
check("github: still one comment after update", 1, len(gh))
check_true("github: body was overwritten", "revised" in gh[0]["body"])

# transition: a legacy comment with a hash= marker is found and overwritten,
# not duplicated (the prefix match, not exact GH_OPEN).
d, env, store = with_stubs()
with open(store, "w") as f:
    json.dump({"gh": [{"id": 7, "body": "<!-- sapa:plan hash=deadbeef -->\nold\n<!-- /sapa:plan -->"}],
               "jira": [], "next": 100}, f)
write(md, "## New plan\n")
issue(env, "plan-comment", "--content-file", md, "--branch", "77-feature")
gh = load_store(store)["gh"]
check("github: legacy hash marker overwritten in place", 1, len(gh))
check_true("github: legacy comment now carries new content", "New plan" in gh[0]["body"])

# read with no comment recorded -> exit 3
d2, env2, store2 = with_stubs()
r = issue(env2, "plan-comment", "--read", "--branch", "88-empty")
check("github: read with no plan exits 3", 3, r.returncode)

# Jira path: create -> read (bullets survive) -> update (create+delete, no dupe).
d, env, store = with_stubs()
adf = os.path.join(d, "plan.adf")
write(adf, json.dumps(doc))
issue(env, "plan-comment", "--content-file", adf, "--branch", "gp-1-feature")
jira = load_store(store)["jira"]
check("jira: one comment created", 1, len(jira))
check_true("jira: stored as real ADF (dict body)", isinstance(jira[0]["body"], dict))
check_true("jira: sentinel node injected",
           si.PLAN_TOKEN in jira[0]["body"]["content"][0]["content"][0]["text"])
r = issue(env, "plan-comment", "--read", "--branch", "gp-1-feature")
check_true("jira: read keeps both bullets", "- one" in r.stdout and "- two" in r.stdout)
check_true("jira: read strips the sentinel", si.PLAN_TOKEN not in r.stdout)
# Update with different content: exactly one comment survives, carrying the new text.
doc2 = json.loads(json.dumps(doc))
doc2["content"][1]["content"][0]["text"] = "Ship it, revised."
write(adf, json.dumps(doc2))
issue(env, "plan-comment", "--content-file", adf, "--branch", "gp-1-feature")
jira = load_store(store)["jira"]
check("jira: still one comment after update (old deleted)", 1, len(jira))
check_true("jira: surviving comment carries the new content",
           "revised" in si.adf_text(jira[0]["body"]))

# key subcommand end to end
r = issue(env, "key", "--branch", "gp-1-feature")
check("key: prints jira key", "GP-1", r.stdout.strip())
r = issue(env, "key", "--branch", "77-feature")
check("key: prints github number", "77", r.stdout.strip())

print()
print(f"{pass_}/{pass_ + fail} passed")
sys.exit(1 if fail else 0)
