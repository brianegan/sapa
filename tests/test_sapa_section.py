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


def run_raw(marker, content, body):
    """Invoke sapa-section without asserting success; return the CompletedProcess."""
    with tempfile.TemporaryDirectory() as d:
        cpath = os.path.join(d, "content")
        bpath = os.path.join(d, "body")
        with open(cpath, "w") as f:
            f.write(content)
        with open(bpath, "w") as f:
            f.write(body)
        cmd = [sys.executable, SECTION, marker, "--content-file", cpath,
               "--body-file", bpath]
        return subprocess.run(cmd, capture_output=True, text=True)


def run_check(marker, body):
    """Invoke sapa-section --check; return the CompletedProcess."""
    with tempfile.TemporaryDirectory() as d:
        bpath = os.path.join(d, "body")
        with open(bpath, "w") as f:
            f.write(body)
        cmd = [sys.executable, SECTION, marker, "--check", "--body-file", bpath]
        return subprocess.run(cmd, capture_output=True, text=True)


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


@case
def test_refuses_truncated_read_open_without_close():
    # A read cut off mid-section: the opening marker survives, the close is gone.
    full, _ = run("plan", "The plan.", "# Issue\n")
    truncated = full[: full.index("<!-- /sapa:plan -->")]
    p = run_raw("plan", "New plan.", truncated)
    assert p.returncode == 3, p.returncode
    assert p.stdout == "", p.stdout
    assert "damaged" in p.stderr and "sapa:plan" in p.stderr


@case
def test_refuses_stray_closing_marker():
    p = run_raw("plan", "New plan.", "# Issue\n\n<!-- /sapa:plan -->\n")
    assert p.returncode == 3, p.returncode
    assert p.stdout == ""


@case
def test_refuses_duplicate_sections():
    once, _ = run("plan", "First.", "# Issue\n")
    twice = once + "\n\n" + once
    p = run_raw("plan", "New plan.", twice)
    assert p.returncode == 3, p.returncode
    assert p.stdout == ""


@case
def test_inline_marker_mention_is_not_a_wrapper():
    # A plan that quotes the marker inline (in backticks) is prose, not a
    # wrapper line, so writing a fresh section into it must still succeed.
    body = "# Issue\n\nThe plan mentions `<!-- sapa:plan -->` in a sentence.\n"
    out, status = run("plan", "The plan.", body)
    assert status == "created", status
    assert out.count("<!-- /sapa:plan -->") == 1


@case
def test_check_passes_on_whole_body():
    full, _ = run("plan", "The plan.", "# Issue\n")
    p = run_check("plan", full)
    assert p.returncode == 0, p.stderr
    assert p.stdout == "", p.stdout


@case
def test_check_fails_on_truncated_body():
    full, _ = run("plan", "The plan.", "# Issue\n")
    truncated = full[: full.index("<!-- /sapa:plan -->")]
    p = run_check("plan", truncated)
    assert p.returncode == 3, p.returncode
    assert p.stdout == ""


@case
def test_check_passes_when_no_section_present():
    p = run_check("plan", "# Issue\n\nJust a description.\n")
    assert p.returncode == 0, p.stderr


@case
def test_sibling_marker_is_not_mistaken_for_this_one():
    # A body that holds only a `plan-extra` block is sound for marker `plan`:
    # the prefix must not be miscounted as a `plan` opening.
    extra, _ = run("plan-extra", "Other block.", "# Issue\n")
    p = run_check("plan", extra)
    assert p.returncode == 0, p.stderr
    # And writing a plan section into it still succeeds, leaving both intact.
    out, status = run("plan", "The plan.", extra)
    assert status == "created", status
    assert out.count("<!-- /sapa:plan-extra -->") == 1
    assert out.count("<!-- /sapa:plan -->") == 1


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
