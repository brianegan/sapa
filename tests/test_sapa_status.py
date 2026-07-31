#!/usr/bin/env python3
"""Tests for sapa-status, the per-stream status writer for the window switcher.

Run: python3 tests/test_sapa_status.py

Assert on external, observable behavior: the JSON file that lands in the registry,
that --state and --stage merge rather than clobber each other, that the writer
self-guards outside a sapa stream (the load-bearing case — the run-state hooks
fire in every Claude session, not just sapa ones), and that --clear removes it.

The registry is redirected with SAPA_STATUS_DIR so nothing touches the real
~/.sapa. A fixture "stream" is just a temp `<root>/proj/.bare` plus a
`<root>/proj/<branch>/` worktree dir — enough for the `.bare` walk-up; the dirs
need not be real git repos (git resolution falls back to the basename).
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
STATUS = os.path.join(HERE, "..", "bin", "sapa-status")

pass_ = 0
fail = 0


def ok(msg):
    global pass_
    print("ok   " + msg)
    pass_ += 1


def bad(msg):
    global fail
    print("FAIL " + msg)
    fail += 1


def run(args, start, status_dir, stdin=None):
    env = dict(os.environ)
    env["SAPA_STATUS_DIR"] = status_dir
    # PWD is what sapa-status defaults --start to; set it too so the default path
    # is exercised, but pass --start explicitly for determinism.
    env["PWD"] = start
    return subprocess.run(
        [STATUS, *args, "--start", start],
        input=stdin,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
    )


def make_stream(root, branch="42-a-feature"):
    proj = os.path.join(root, "proj")
    os.makedirs(os.path.join(proj, ".bare"))
    wt = os.path.join(proj, branch)
    os.makedirs(wt)
    return proj, wt, branch


def read_entry(status_dir, branch):
    with open(os.path.join(status_dir, branch + ".json"), encoding="utf-8") as f:
        return json.load(f)


with tempfile.TemporaryDirectory() as d:
    status_dir = os.path.join(d, "registry")

    # --- --stage writes a keyed file with the expected fields ---
    proj, wt, branch = make_stream(os.path.join(d, "s1"))
    r = run(["--stage", "gate"], wt, status_dir)
    entry_path = os.path.join(status_dir, branch + ".json")
    if r.returncode == 0 and os.path.isfile(entry_path):
        ok("--stage writes a file keyed by the worktree basename")
    else:
        bad("--stage writes a file (rc=%d, %s)" % (r.returncode, r.stderr))
    e = read_entry(status_dir, branch)
    if e.get("stage") == "gate" and e.get("branch") == branch and "updated" in e:
        ok("--stage sets stage, branch, and updated")
    else:
        bad("--stage fields wrong: %r" % e)

    # --- --state merges without clobbering the existing stage ---
    r = run(["--state", "busy"], wt, status_dir)
    e = read_entry(status_dir, branch)
    if r.returncode == 0 and e.get("state") == "busy" and e.get("stage") == "gate":
        ok("--state merges in without clobbering stage")
    else:
        bad("--state merge wrong (rc=%d): %r" % (r.returncode, e))

    # --- and the reverse: a later --stage keeps the state ---
    r = run(["--stage", "watch"], wt, status_dir)
    e = read_entry(status_dir, branch)
    if e.get("stage") == "watch" and e.get("state") == "busy":
        ok("--stage keeps the existing state")
    else:
        bad("--stage clobbered state: %r" % e)

    # --- --report prints the recorded stage, bare, and writes nothing ---
    before = read_entry(status_dir, branch)
    r = run(["--report"], wt, status_dir)
    if r.returncode == 0 and r.stdout == "watch\n":
        ok("--report prints the recorded stage alone")
    else:
        bad("--report output wrong (rc=%d): %r" % (r.returncode, r.stdout))
    if read_entry(status_dir, branch) == before:
        ok("--report leaves the file untouched")
    else:
        bad("--report wrote to the file: %r" % read_entry(status_dir, branch))

    # --- a stream with a file but no stage yet reports nothing, not an error ---
    _, swt, sbranch = make_stream(os.path.join(d, "s2"), branch="7-state-only")
    run(["--state", "busy"], swt, status_dir)
    r = run(["--report"], swt, status_dir)
    if r.returncode == 0 and r.stdout == "":
        ok("--report prints nothing when no stage is recorded")
    else:
        bad("--report on a stageless file (rc=%d): %r" % (r.returncode, r.stdout))

    # --- and with no file at all: same answer, so a fresh stream starts at the top ---
    _, fwt, _ = make_stream(os.path.join(d, "s3"), branch="8-never-written")
    r = run(["--report"], fwt, status_dir)
    if r.returncode == 0 and r.stdout == "":
        ok("--report prints nothing when the stream has no file")
    else:
        bad("--report on a missing file (rc=%d): %r" % (r.returncode, r.stdout))

    # --- --clear removes the file ---
    r = run(["--clear"], wt, status_dir)
    if r.returncode == 0 and not os.path.exists(entry_path):
        ok("--clear removes the file")
    else:
        bad("--clear did not remove the file (rc=%d)" % r.returncode)

    # --- --clear on a missing file is a no-op success ---
    r = run(["--clear"], wt, status_dir)
    if r.returncode == 0:
        ok("--clear on a missing file exits 0")
    else:
        bad("--clear on missing file failed (rc=%d, %s)" % (r.returncode, r.stderr))

    # --- self-guard: outside any sapa stream, do nothing and exit 0 ---
    outside = os.path.join(d, "not-a-stream")
    os.makedirs(outside)
    before = set(os.listdir(status_dir)) if os.path.isdir(status_dir) else set()
    r = run(["--state", "busy"], outside, status_dir)
    after = set(os.listdir(status_dir)) if os.path.isdir(status_dir) else set()
    if r.returncode == 0 and before == after:
        ok("self-guards outside a sapa stream (exit 0, writes nothing)")
    else:
        bad("self-guard failed (rc=%d, new files: %r)" % (r.returncode, after - before))

    # --- the project root itself is not a stream ---
    r = run(["--state", "busy"], proj, status_dir)
    if r.returncode == 0 and not os.path.exists(os.path.join(status_dir, "proj.json")):
        ok("the project root is not treated as a stream")
    else:
        bad("project root wrongly treated as a stream (rc=%d)" % r.returncode)

    # --- nothing to do is a usage error ---
    r = run([], wt, status_dir)
    if r.returncode != 0:
        ok("no action flag is a usage error")
    else:
        bad("no action flag should error")

    # --- --notification: discriminate a real prompt from the idle nudge ---
    # A fresh stream keeps these run-state assertions isolated from the above.
    _, nwt, nbranch = make_stream(os.path.join(d, "notif"), branch="60-notify")

    idle_nudge = '{"message": "Claude is waiting for your input"}'
    permission = '{"message": "Claude needs your permission to use Bash"}'

    def seed(state):
        run(["--state", state], nwt, status_dir)

    # busy + no message → the agent paused mid-work: needs-you.
    seed("busy")
    r = run(["--notification"], nwt, status_dir, stdin="")
    e = read_entry(status_dir, nbranch)
    if r.returncode == 0 and e.get("state") == "needs-you":
        ok("--notification while busy writes needs-you")
    else:
        bad("--notification while busy wrong (rc=%d): %r" % (r.returncode, e))

    # idle + idle-nudge message → just the nudge: leave it idle.
    seed("idle")
    r = run(["--notification"], nwt, status_dir, stdin=idle_nudge)
    e = read_entry(status_dir, nbranch)
    if r.returncode == 0 and e.get("state") == "idle":
        ok("--notification while idle with the nudge message stays idle")
    else:
        bad("--notification idle nudge wrong (rc=%d): %r" % (r.returncode, e))

    # idle + permission message → the message rescues it: needs-you.
    seed("idle")
    r = run(["--notification"], nwt, status_dir, stdin=permission)
    e = read_entry(status_dir, nbranch)
    if r.returncode == 0 and e.get("state") == "needs-you":
        ok("--notification with a permission message writes needs-you even when idle")
    else:
        bad("--notification permission-while-idle wrong (rc=%d): %r" % (r.returncode, e))

    # busy + idle-nudge message → the message overrides a stale busy: stay put.
    seed("busy")
    r = run(["--notification"], nwt, status_dir, stdin=idle_nudge)
    e = read_entry(status_dir, nbranch)
    if r.returncode == 0 and e.get("state") == "busy":
        ok("--notification nudge message does not upgrade a stale busy")
    else:
        bad("--notification nudge-over-busy wrong (rc=%d): %r" % (r.returncode, e))

    # self-guard: --notification outside a sapa stream writes nothing, exits 0.
    before = set(os.listdir(status_dir)) if os.path.isdir(status_dir) else set()
    r = run(["--notification"], outside, status_dir, stdin=permission)
    after = set(os.listdir(status_dir)) if os.path.isdir(status_dir) else set()
    if r.returncode == 0 and before == after:
        ok("--notification self-guards outside a sapa stream")
    else:
        bad("--notification self-guard failed (rc=%d, new: %r)" % (r.returncode, after - before))

    # --- --active: clear a stale needs-you on resumed work, and only then ---
    # The PreToolUse hook fires on every tool call, so --active must downgrade a
    # stale needs-you and otherwise not write the file at all. The no-op cases
    # seed a distinct past `updated` directly and assert the entry is untouched,
    # which pins down "no write" rather than merely "no state change".
    _, awt, abranch = make_stream(os.path.join(d, "active"), branch="66-resume")
    apath = os.path.join(status_dir, abranch + ".json")

    def write_entry(data):
        os.makedirs(status_dir, exist_ok=True)
        with open(apath, "w", encoding="utf-8") as f:
            json.dump(data, f)

    # needs-you → busy: resuming work clears the stale attention.
    run(["--state", "needs-you"], awt, status_dir)
    r = run(["--active"], awt, status_dir)
    e = read_entry(status_dir, abranch)
    if r.returncode == 0 and e.get("state") == "busy":
        ok("--active downgrades a stale needs-you to busy")
    else:
        bad("--active needs-you->busy wrong (rc=%d): %r" % (r.returncode, e))

    # already busy → no write at all (the common per-tool-call case).
    stale_busy = {"branch": abranch, "state": "busy", "stage": "build",
                  "updated": "2020-01-01T00:00:00Z"}
    write_entry(dict(stale_busy))
    r = run(["--active"], awt, status_dir)
    e = read_entry(status_dir, abranch)
    if r.returncode == 0 and e == stale_busy:
        ok("--active while busy leaves the file untouched (no churn)")
    else:
        bad("--active while busy wrote the file (rc=%d): %r" % (r.returncode, e))

    # idle → no write either.
    stale_idle = {"branch": abranch, "state": "idle", "stage": "build",
                  "updated": "2020-01-01T00:00:00Z"}
    write_entry(dict(stale_idle))
    r = run(["--active"], awt, status_dir)
    e = read_entry(status_dir, abranch)
    if r.returncode == 0 and e == stale_idle:
        ok("--active while idle leaves the file untouched")
    else:
        bad("--active while idle wrote the file (rc=%d): %r" % (r.returncode, e))

    # no status file yet → nothing to clear, and none is created.
    os.remove(apath)
    r = run(["--active"], awt, status_dir)
    if r.returncode == 0 and not os.path.exists(apath):
        ok("--active with no status file creates nothing")
    else:
        bad("--active created a file with no prior state (rc=%d)" % r.returncode)

    # self-guard: --active outside a sapa stream writes nothing, exits 0.
    before = set(os.listdir(status_dir)) if os.path.isdir(status_dir) else set()
    r = run(["--active"], outside, status_dir)
    after = set(os.listdir(status_dir)) if os.path.isdir(status_dir) else set()
    if r.returncode == 0 and before == after:
        ok("--active self-guards outside a sapa stream")
    else:
        bad("--active self-guard failed (rc=%d, new: %r)" % (r.returncode, after - before))

print()
print("%d/%d passed" % (pass_, pass_ + fail))
sys.exit(1 if fail else 0)
