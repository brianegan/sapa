#!/usr/bin/env python3
"""Tests for sapa-section, the ownership-lock section editor.

Run: python3 tests/test_sapa_section.py
These assert on external behavior (the resulting body and the status word),
not on internal implementation.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SECTION = os.path.join(HERE, "..", "bin", "sapa-section")


def run(marker, content, body, lock=False):
    """Invoke sapa-section, returning (stdout, status)."""
    with tempfile.TemporaryDirectory() as d:
        cpath = os.path.join(d, "content")
        bpath = os.path.join(d, "body")
        with open(cpath, "w") as f:
            f.write(content)
        with open(bpath, "w") as f:
            f.write(body)
        cmd = [sys.executable, SECTION, marker, "--content-file", cpath,
               "--body-file", bpath]
        if lock:
            cmd.append("--lock")
        p = subprocess.run(cmd, capture_output=True, text=True)
        assert p.returncode == 0, p.stderr
        return p.stdout, p.stderr.strip()


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def test_creates_section_when_absent():
    out, status = run("plan", "The plan.", "# Issue\n\nSome description.\n")
    assert status == "created", status
    assert "<!-- sapa:plan hash=" in out
    assert "The plan." in out
    assert "<!-- /sapa:plan -->" in out
    # The original body is preserved above the new section.
    assert out.startswith("# Issue\n\nSome description.")


@case
def test_creates_into_empty_body():
    out, status = run("pr", "Body.", "")
    assert status == "created", status
    assert out.startswith("<!-- sapa:pr hash=")
    assert "Body." in out


@case
def test_updates_section_sapa_still_owns():
    first, _ = run("plan", "Original plan.", "# Issue\n")
    second, status = run("plan", "Revised plan.", first)
    assert status == "updated", status
    assert "Revised plan." in second
    assert "Original plan." not in second
    # Still exactly one managed block.
    assert second.count("<!-- sapa:plan ") == 1


@case
def test_does_not_clobber_human_edit():
    first, _ = run("plan", "Original plan.", "# Issue\n")
    # Human edits the content inside the markers, leaving the hash stale.
    tampered = first.replace("Original plan.", "Human rewrote this by hand.")
    out, status = run("plan", "Sapa's new plan.", tampered)
    assert status == "locked-edited", status
    assert "Human rewrote this by hand." in out
    assert "Sapa's new plan." not in out


@case
def test_respects_explicit_lock():
    locked, status = run("plan", "Locked content.", "# Issue\n", lock=True)
    assert status == "locked-now", status
    assert "<!-- sapa:plan locked -->" in locked
    # A subsequent update must not touch a locked section.
    out, status2 = run("plan", "Trying to change it.", locked)
    assert status2 == "locked", status2
    assert "Locked content." in out
    assert "Trying to change it." not in out


@case
def test_idempotent_update_is_stable():
    first, _ = run("pr", "Same body.", "# PR\n")
    second, status = run("pr", "Same body.", first)
    assert status == "updated", status
    # Re-writing identical content leaves the managed block identical.
    assert first == second


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
