#!/usr/bin/env python3
"""Tests for sapa-watch, the mechanical PR poll/emitter.

Run: python3 tests/test_sapa_watch.py

These stub `gh` on PATH (the way the rest of bin/ is tested) and assert on the
emitted event lines and the persisted state — external, observable behavior, not
internals. The load-bearing case is the empty-poll guard: an empty-but-successful
`gh` response must never be mistaken for a state change (the #42 bug).
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WATCH = os.path.join(HERE, "..", "bin", "sapa-watch")

# A gh stub: for `pr view` it prints the fixture file (empty file => an
# empty-but-successful response) and exits 0; if the fixture is missing it exits
# non-zero (a failed fetch). Any other gh call is a no-op success.
GH_STUB = """#!/bin/bash
if [ "$1" = "pr" ] && [ "$2" = "view" ]; then
  if [ -n "${GH_FIXTURE:-}" ] && [ -f "$GH_FIXTURE" ]; then
    cat "$GH_FIXTURE"
    exit 0
  fi
  exit 1
fi
exit 0
"""


def pr(state="OPEN", merge="CLEAN", checks=None, reviews=None, comments=None):
    return {
        "number": 1,
        "state": state,
        "mergeStateStatus": merge,
        "statusCheckRollup": checks or [],
        "reviews": reviews or [],
        "comments": comments or [],
        "baseRefName": "main",
        "url": "https://example/pr/1",
    }


def run_once(fixture, prior_state=None, gh_fails=False):
    """Run `sapa-watch --once` against a stubbed gh.

    fixture: a PR dict to serialize, the string "empty" for an empty-but-
    successful response, or None. gh_fails: stub exits non-zero (failed fetch).
    Returns (stdout, stderr, state_after_dict_or_None).
    """
    with tempfile.TemporaryDirectory() as d:
        bindir = os.path.join(d, "bin")
        os.mkdir(bindir)
        gh = os.path.join(bindir, "gh")
        with open(gh, "w") as f:
            f.write(GH_STUB)
        os.chmod(gh, 0o755)

        fixture_path = os.path.join(d, "fixture.json")
        env = dict(os.environ)
        env["PATH"] = bindir + os.pathsep + env["PATH"]
        if not gh_fails:
            with open(fixture_path, "w") as f:
                f.write("" if fixture == "empty" else json.dumps(fixture))
            env["GH_FIXTURE"] = fixture_path
        # else: leave GH_FIXTURE unset so the stub exits non-zero.

        state_file = os.path.join(d, "state.json")
        if prior_state is not None:
            with open(state_file, "w") as f:
                json.dump(prior_state, f)

        p = subprocess.run(
            [sys.executable, WATCH, "--once", "--state-file", state_file, "--start", d],
            capture_output=True, text=True, env=env,
        )
        assert p.returncode == 0, p.stderr
        after = None
        if os.path.exists(state_file):
            with open(state_file) as f:
                after = json.load(f)
        return p.stdout, p.stderr, after


def events(stdout):
    return [line.split("\t") for line in stdout.splitlines() if line]


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def test_first_poll_surfaces_current_reviews_and_comments():
    fixture = pr(
        reviews=[{"id": "R1", "author": {"login": "alice"}, "state": "CHANGES_REQUESTED"}],
        comments=[{"id": "C1", "author": {"login": "bob"}}],
    )
    out, _, after = run_once(fixture)
    evs = events(out)
    assert ["new-review", "R1", "alice", "CHANGES_REQUESTED"] in evs, evs
    assert ["new-comment", "C1", "bob"] in evs, evs
    # Baseline is persisted.
    assert after["reviews"] == ["R1"] and after["comments"] == ["C1"], after


@case
def test_dedup_emits_nothing_when_nothing_changed():
    prior = {"reviews": ["R1"], "comments": ["C1"], "ci_failing": False, "behind": False}
    fixture = pr(
        reviews=[{"id": "R1", "author": {"login": "alice"}, "state": "APPROVED"}],
        comments=[{"id": "C1", "author": {"login": "bob"}}],
    )
    out, _, _ = run_once(fixture, prior_state=prior)
    assert events(out) == [], out


@case
def test_new_comment_delta_only():
    prior = {"reviews": [], "comments": ["C1"], "ci_failing": False, "behind": False}
    fixture = pr(comments=[
        {"id": "C1", "author": {"login": "bob"}},
        {"id": "C2", "author": {"login": "carol"}},
    ])
    out, _, after = run_once(fixture, prior_state=prior)
    evs = events(out)
    assert evs == [["new-comment", "C2", "carol"]], evs
    assert set(after["comments"]) == {"C1", "C2"}, after


@case
def test_empty_but_successful_fetch_is_guarded():
    # The #42 bug: an empty-but-successful poll must not count as a change and
    # must not clobber the baseline.
    prior = {"reviews": [], "comments": ["C1"], "ci_failing": False, "behind": False}
    out, err, after = run_once("empty", prior_state=prior)
    assert events(out) == [], out
    assert "skipped" in err.lower(), err
    # State preserved untouched...
    assert after == prior, after
    # ...so a following real poll with the same comment still emits nothing.
    fixture = pr(comments=[{"id": "C1", "author": {"login": "bob"}}])
    out2, _, _ = run_once(fixture, prior_state=after)
    assert events(out2) == [], out2


@case
def test_empty_object_response_is_guarded():
    # A parseable but stateless response ({}) is not a usable PR view; it must
    # be skipped, not treated as a change that clobbers the baseline.
    prior = {"reviews": [], "comments": ["C1"], "ci_failing": False, "behind": False}
    out, err, after = run_once({}, prior_state=prior)
    assert events(out) == [], out
    assert "skipped" in err.lower(), err
    assert after == prior, after


@case
def test_failed_fetch_is_guarded():
    prior = {"reviews": [], "comments": ["C1"], "ci_failing": False, "behind": False}
    out, err, after = run_once(None, prior_state=prior, gh_fails=True)
    assert events(out) == [], out
    assert "skipped" in err.lower(), err
    assert after == prior, after


@case
def test_ci_failed_is_edge_triggered():
    prior = {"reviews": [], "comments": [], "ci_failing": False, "behind": False}
    fixture = pr(checks=[
        {"name": "unit", "conclusion": "FAILURE"},
        {"name": "lint", "conclusion": "SUCCESS"},
    ])
    out, _, after = run_once(fixture, prior_state=prior)
    assert events(out) == [["ci-failed", "unit"]], out
    assert after["ci_failing"] is True, after
    # Held-failing on the next poll does not re-emit.
    out2, _, _ = run_once(fixture, prior_state=after)
    assert events(out2) == [], out2


@case
def test_ci_failed_detects_legacy_status_context():
    prior = {"reviews": [], "comments": [], "ci_failing": False, "behind": False}
    fixture = pr(checks=[{"context": "ci/legacy", "state": "FAILURE"}])
    out, _, _ = run_once(fixture, prior_state=prior)
    assert events(out) == [["ci-failed", "ci/legacy"]], out


@case
def test_base_behind_is_edge_triggered():
    prior = {"reviews": [], "comments": [], "ci_failing": False, "behind": False}
    fixture = pr(merge="BEHIND")
    out, _, after = run_once(fixture, prior_state=prior)
    assert events(out) == [["base-behind"]], out
    assert after["behind"] is True, after
    out2, _, _ = run_once(fixture, prior_state=after)
    assert events(out2) == [], out2


@case
def test_merged_is_terminal():
    prior = {"reviews": [], "comments": [], "ci_failing": False, "behind": False}
    out, _, _ = run_once(pr(state="MERGED"), prior_state=prior)
    assert events(out) == [["merged"]], out


@case
def test_closed_is_terminal():
    prior = {"reviews": [], "comments": [], "ci_failing": False, "behind": False}
    out, _, _ = run_once(pr(state="CLOSED"), prior_state=prior)
    assert events(out) == [["closed"]], out


@case
def test_loop_mode_exits_on_terminal_state():
    # The helper owns the loop and must exit on a terminal state rather than
    # spin. Interval 0 so it never sleeps; a merged fixture ends it on poll one.
    with tempfile.TemporaryDirectory() as d:
        bindir = os.path.join(d, "bin")
        os.mkdir(bindir)
        gh = os.path.join(bindir, "gh")
        with open(gh, "w") as f:
            f.write(GH_STUB)
        os.chmod(gh, 0o755)
        fixture_path = os.path.join(d, "fixture.json")
        with open(fixture_path, "w") as f:
            f.write(json.dumps(pr(state="MERGED")))
        env = dict(os.environ)
        env["PATH"] = bindir + os.pathsep + env["PATH"]
        env["GH_FIXTURE"] = fixture_path
        env["SAPA_WATCH_INTERVAL"] = "0"
        state_file = os.path.join(d, "state.json")
        p = subprocess.run(
            [sys.executable, WATCH, "--state-file", state_file, "--start", d],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert p.returncode == 0, p.stderr
        assert events(p.stdout) == [["merged"]], p.stdout


def main():
    failed = 0
    for fn in CASES:
        try:
            fn()
            print(f"ok   {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {fn.__name__}: {e!r}")
    print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
