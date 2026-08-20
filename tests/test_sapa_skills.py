#!/usr/bin/env python3
"""Tests for sapa-skills, which provisions and verifies the skills a .sapa.yaml
references.

Run: python3 tests/test_sapa_skills.py

Assert on external, observable behavior: what `enumerate` prints, what `check`
exits and names, what `lock` writes back into the config (comments preserved),
what `sync` materializes on disk, and that `update` bumps a moved SHA. The
network verbs run against a *local* git repo used as the skill source, so the
suite needs no network.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.join(HERE, "..", "bin", "sapa-skills")
SAPA = os.path.join(HERE, "..", "bin", "sapa")

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


def run(args, start=None):
    """Run sapa-skills. When start is given, pass it as --start and as PWD."""
    env = dict(os.environ)
    argv = [SKILLS, *args]
    if start is not None:
        env["PWD"] = start
        argv += ["--start", start]
    return subprocess.run(
        argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env
    )


def git(args, cwd):
    env = dict(os.environ)
    # Deterministic identity so committing works in a bare CI environment.
    env.setdefault("GIT_AUTHOR_NAME", "t")
    env.setdefault("GIT_AUTHOR_EMAIL", "t@t")
    env.setdefault("GIT_COMMITTER_NAME", "t")
    env.setdefault("GIT_COMMITTER_EMAIL", "t@t")
    return subprocess.run(
        ["git", *args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env, check=True,
    )


def make_worktree(root):
    """A project repo standing in for a worktree: a real git repo with a
    default branch, so `git rev-parse --show-toplevel` resolves to it."""
    wt = os.path.join(root, "project")
    os.makedirs(wt)
    git(["init", "-q", "-b", "main"], wt)
    # An initial commit so HEAD exists.
    open(os.path.join(wt, ".gitkeep"), "w").close()
    git(["add", "."], wt)
    git(["commit", "-q", "-m", "init"], wt)
    return wt


def write_config(wt, text):
    with open(os.path.join(wt, ".sapa.yaml"), "w") as f:
        f.write(text)


# --------------------------------------------------------------------------
# Task 1: dispatch, help, unknown verb
# --------------------------------------------------------------------------

def test_help():
    for flag in ("--help", "-h", "help"):
        r = run([flag])
        verbs = all(v in r.stdout for v in
                    ("enumerate", "lock", "sync", "check", "update"))
        if r.returncode == 0 and "sapa skills" in r.stdout and verbs:
            ok(f"help ({flag}) lists the five verbs, exits 0")
        else:
            bad(f"help ({flag}) lists the five verbs, exits 0 (rc={r.returncode})")

    r = run([])
    if r.returncode == 0 and "sapa skills" in r.stdout:
        ok("no verb prints usage, exits 0")
    else:
        bad(f"no verb prints usage, exits 0 (rc={r.returncode})")


def test_unknown_verb():
    r = run(["bogus"])
    if r.returncode == 2 and "unknown verb" in r.stderr:
        ok("unknown verb exits 2, names it")
    else:
        bad(f"unknown verb exits 2, names it (rc={r.returncode}, {r.stderr!r})")


def test_dispatch_routes():
    # `sapa skills <verb>` must reach this helper. A bogus verb routed through
    # the dispatcher returns the helper's own exit 2, proving the route.
    r = subprocess.run(
        [SAPA, "skills", "bogus"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    if r.returncode == 2 and "unknown verb" in r.stderr:
        ok("bin/sapa routes 'skills' to the helper")
    else:
        bad(f"bin/sapa routes 'skills' to the helper (rc={r.returncode}, {r.stderr!r})")


# --------------------------------------------------------------------------
# Task 2: enumerate
# --------------------------------------------------------------------------

ENUM_CONFIG = """\
base: main
plan: grilling
build: tdd
writing_style:
  source: blader/humanizer
  path: .
  name: humanizer
gate:
  steps:
    - name: review
      skill:
        source: mattpocock/skills
        path: skills/engineering/code-review
        sha: abc123
    - name: test
      run: bash tests/run.sh
"""


def test_enumerate():
    with tempfile.TemporaryDirectory() as root:
        wt = make_worktree(root)
        write_config(wt, ENUM_CONFIG)
        r = run(["enumerate"], start=wt)
        lines = r.stdout.splitlines()
        # plan(bare), build(bare), writing_style(object w/ name), gate skill
        # (object w/ path basename). The `test` step has no skill, so it is not
        # listed. Order is stable: config keys first, then gate steps.
        if r.returncode == 0 and lines == ["grilling", "tdd", "humanizer", "code-review"]:
            ok("enumerate prints exactly the referenced skills, in order")
        else:
            bad(f"enumerate prints exactly the referenced skills (rc={r.returncode}, {lines!r})")

    # A config that references nothing prints nothing.
    with tempfile.TemporaryDirectory() as root:
        wt = make_worktree(root)
        write_config(wt, "base: main\n")
        r = run(["enumerate"], start=wt)
        if r.returncode == 0 and r.stdout == "":
            ok("enumerate on a skill-free config prints nothing")
        else:
            bad(f"enumerate on a skill-free config prints nothing (rc={r.returncode}, {r.stdout!r})")


# --------------------------------------------------------------------------
# Task 3: check
# --------------------------------------------------------------------------

def make_folder(wt, name, with_skill_md=True):
    d = os.path.join(wt, ".claude", "skills", name)
    os.makedirs(d, exist_ok=True)
    if with_skill_md:
        with open(os.path.join(d, "SKILL.md"), "w") as f:
            f.write("# skill\n")
    return d


# One object-form skill (provisioned) plus one bare (bring-your-own).
CHECK_CONFIG = """\
base: main
plan: grilling
writing_style:
  source: blader/humanizer
  path: .
  name: humanizer
"""


def test_check_passes():
    with tempfile.TemporaryDirectory() as root:
        wt = make_worktree(root)
        write_config(wt, CHECK_CONFIG)
        make_folder(wt, "humanizer")            # the one provisioned skill
        r = run(["check"], start=wt)
        if r.returncode == 0:
            ok("check passes when the object set matches the folders")
        else:
            bad(f"check passes when the object set matches (rc={r.returncode}, {r.stderr!r})")


def test_check_ignores_bare():
    # `grilling` is referenced bare, so it needs no folder and its absence is
    # not an offense.
    with tempfile.TemporaryDirectory() as root:
        wt = make_worktree(root)
        write_config(wt, CHECK_CONFIG)
        make_folder(wt, "humanizer")
        r = run(["check"], start=wt)
        if r.returncode == 0 and "grilling" not in r.stderr:
            ok("check leaves a bare-string reference unflagged")
        else:
            bad(f"check leaves a bare-string reference unflagged (rc={r.returncode}, {r.stderr!r})")


def test_check_missing_folder():
    with tempfile.TemporaryDirectory() as root:
        wt = make_worktree(root)
        write_config(wt, CHECK_CONFIG)
        # humanizer folder absent
        r = run(["check"], start=wt)
        if r.returncode == 1 and "not vendored: humanizer" in r.stderr:
            ok("check names a referenced-but-missing skill")
        else:
            bad(f"check names a referenced-but-missing skill (rc={r.returncode}, {r.stderr!r})")


def test_check_orphan_folder():
    with tempfile.TemporaryDirectory() as root:
        wt = make_worktree(root)
        write_config(wt, CHECK_CONFIG)
        make_folder(wt, "humanizer")
        make_folder(wt, "leftover")             # not referenced anywhere
        r = run(["check"], start=wt)
        if r.returncode == 1 and "not referenced: leftover" in r.stderr:
            ok("check names an orphan folder")
        else:
            bad(f"check names an orphan folder (rc={r.returncode}, {r.stderr!r})")


def test_check_missing_skill_md():
    with tempfile.TemporaryDirectory() as root:
        wt = make_worktree(root)
        write_config(wt, CHECK_CONFIG)
        make_folder(wt, "humanizer", with_skill_md=False)
        r = run(["check"], start=wt)
        if r.returncode == 1 and "no SKILL.md: humanizer" in r.stderr:
            ok("check names a folder lacking SKILL.md")
        else:
            bad(f"check names a folder lacking SKILL.md (rc={r.returncode}, {r.stderr!r})")


# --------------------------------------------------------------------------
# Task 4: lock
# --------------------------------------------------------------------------

def make_source(root, name, subpath="."):
    """A local git repo standing in for an upstream skill source: a SKILL.md at
    `subpath` and a LICENSE at the root, one commit. Returns (path, head_sha)."""
    repo = os.path.join(root, "src-" + name)
    skdir = repo if subpath in (".", "") else os.path.join(repo, subpath)
    os.makedirs(skdir, exist_ok=True)
    with open(os.path.join(skdir, "SKILL.md"), "w") as f:
        f.write(f"# {name}\n")
    with open(os.path.join(repo, "LICENSE"), "w") as f:
        f.write("MIT License\n")
    git(["init", "-q", "-b", "main"], repo)
    git(["add", "."], repo)
    git(["commit", "-q", "-m", "init"], repo)
    sha = git(["rev-parse", "HEAD"], repo).stdout.strip()
    return repo, sha


def read_config(wt):
    with open(os.path.join(wt, ".sapa.yaml")) as f:
        return f.read()


def test_lock_inserts_sha_preserving_comments():
    with tempfile.TemporaryDirectory() as root:
        wt = make_worktree(root)
        src, head = make_source(root, "humanizer", ".")
        # A comment block AND another key follow the skill block, so the sha must
        # land adjacent to the block's last field, not below the trailing comments
        # (which pyyaml folds into the mapping's end_mark).
        cfg = (
            "base: main\n"
            "# a comment that must survive verbatim\n"
            "writing_style:\n"
            f"  source: {src}\n"
            "  path: .\n"
            "  name: humanizer\n"
            "# a trailing comment between the block and the next key\n"
            "pr: ready\n"
        )
        write_config(wt, cfg)
        r = run(["lock"], start=wt)
        after = read_config(wt)
        import yaml
        parsed = yaml.safe_load(after)
        sha_ok = parsed["writing_style"].get("sha") == head and len(head) == 40
        comment_ok = ("# a comment that must survive verbatim\n" in after
                      and "# a trailing comment between the block and the next key\n" in after)
        untouched = (parsed["writing_style"]["source"] == src
                     and parsed["writing_style"]["path"] == "."
                     and parsed["writing_style"]["name"] == "humanizer"
                     and parsed["pr"] == "ready")
        adjacent = f"  name: humanizer\n  sha: {head}\n" in after
        if r.returncode == 0 and sha_ok and comment_ok and untouched and adjacent:
            ok("lock inserts the sha adjacent to the last field, comments preserved")
        else:
            bad(f"lock inserts sha adjacent, comments preserved (rc={r.returncode}, "
                f"sha_ok={sha_ok}, comment_ok={comment_ok}, untouched={untouched}, "
                f"adjacent={adjacent})")


def test_lock_errors_on_bad_config():
    # lock's error contract matches check's: a non-mapping config is a loud
    # SkillsError, not a silent "nothing to lock" exit 0.
    with tempfile.TemporaryDirectory() as root:
        wt = make_worktree(root)
        write_config(wt, "- a\n- b\n")
        r = run(["lock"], start=wt)
        if r.returncode != 0 and "does not hold a mapping" in r.stderr:
            ok("lock errors on a non-mapping config instead of a silent no-op")
        else:
            bad(f"lock errors on a non-mapping config (rc={r.returncode}, {r.stderr!r})")


def test_lock_replaces_existing_sha():
    with tempfile.TemporaryDirectory() as root:
        wt = make_worktree(root)
        src, head = make_source(root, "grilling", "skills/productivity/grilling")
        cfg = (
            "base: main\n"
            "plan:\n"
            f"  source: {src}\n"
            "  path: skills/productivity/grilling\n"
            "  sha: 0000000000000000000000000000000000000000  # stale\n"
        )
        write_config(wt, cfg)
        r = run(["lock"], start=wt)
        after = read_config(wt)
        import yaml
        parsed = yaml.safe_load(after)
        if r.returncode == 0 and parsed["plan"]["sha"] == head and "# stale" in after:
            ok("lock replaces a stale sha in place, keeping the trailing comment")
        else:
            bad(f"lock replaces a stale sha in place (rc={r.returncode}, "
                f"sha={parsed['plan'].get('sha')!r}, {after!r})")


# --------------------------------------------------------------------------
# Task 5: sync
# --------------------------------------------------------------------------

def make_source_no_license(root, name, subpath="."):
    repo = os.path.join(root, "src-" + name)
    skdir = repo if subpath in (".", "") else os.path.join(repo, subpath)
    os.makedirs(skdir, exist_ok=True)
    with open(os.path.join(skdir, "SKILL.md"), "w") as f:
        f.write(f"# {name}\n")
    git(["init", "-q", "-b", "main"], repo)
    git(["add", "."], repo)
    git(["commit", "-q", "-m", "init"], repo)
    return repo, git(["rev-parse", "HEAD"], repo).stdout.strip()


def test_sync_vendors_folder_and_license():
    with tempfile.TemporaryDirectory() as root:
        wt = make_worktree(root)
        # A subfolder skill: SKILL.md nested, LICENSE only at the repo root.
        src, head = make_source(root, "grilling", "skills/productivity/grilling")
        cfg = (
            "base: main\n"
            "plan:\n"
            f"  source: {src}\n"
            "  path: skills/productivity/grilling\n"
            f"  sha: {head}\n"
        )
        write_config(wt, cfg)
        r = run(["sync"], start=wt)
        base = os.path.join(wt, ".claude", "skills", "grilling")
        has_skill = os.path.isfile(os.path.join(base, "SKILL.md"))
        has_license = os.path.isfile(os.path.join(base, "LICENSE"))
        no_git = not os.path.exists(os.path.join(base, ".git"))
        if r.returncode == 0 and has_skill and has_license and no_git:
            ok("sync vendors the skill folder with SKILL.md and a root LICENSE")
        else:
            bad(f"sync vendors folder+license (rc={r.returncode}, skill={has_skill}, "
                f"license={has_license}, no_git={no_git}, err={r.stderr!r})")


def test_sync_errors_without_sha():
    with tempfile.TemporaryDirectory() as root:
        wt = make_worktree(root)
        src, _head = make_source(root, "humanizer", ".")
        cfg = (
            "base: main\n"
            "writing_style:\n"
            f"  source: {src}\n"
            "  path: .\n"
            "  name: humanizer\n"      # no sha
        )
        write_config(wt, cfg)
        r = run(["sync"], start=wt)
        if r.returncode != 0 and "run `sapa skills lock`" in r.stderr:
            ok("sync errors when an entry has no sha, pointing at lock")
        else:
            bad(f"sync errors when an entry has no sha (rc={r.returncode}, {r.stderr!r})")


def test_sync_fails_without_license():
    with tempfile.TemporaryDirectory() as root:
        wt = make_worktree(root)
        src, head = make_source_no_license(root, "grilling", "skills/productivity/grilling")
        cfg = (
            "base: main\n"
            "plan:\n"
            f"  source: {src}\n"
            "  path: skills/productivity/grilling\n"
            f"  sha: {head}\n"
        )
        write_config(wt, cfg)
        r = run(["sync"], start=wt)
        vendored = os.path.exists(os.path.join(wt, ".claude", "skills", "grilling"))
        if r.returncode != 0 and "without attribution" in r.stderr and not vendored:
            ok("sync fails loudly and vendors nothing when no LICENSE exists upstream")
        else:
            bad(f"sync fails without a license (rc={r.returncode}, vendored={vendored}, {r.stderr!r})")


# --------------------------------------------------------------------------
# Task 6: update
# --------------------------------------------------------------------------

def advance_source(repo, subpath, content):
    skdir = repo if subpath in (".", "") else os.path.join(repo, subpath)
    with open(os.path.join(skdir, "SKILL.md"), "w") as f:
        f.write(content)
    git(["add", "."], repo)
    git(["commit", "-q", "-m", "advance"], repo)
    return git(["rev-parse", "HEAD"], repo).stdout.strip()


def test_update_bumps_and_refreshes_uncommitted():
    with tempfile.TemporaryDirectory() as root:
        wt = make_worktree(root)
        sub = "skills/productivity/grilling"
        src, sha1 = make_source(root, "grilling", sub)
        cfg = (
            "base: main\n"
            "plan:\n"
            f"  source: {src}\n"
            f"  path: {sub}\n"
            f"  sha: {sha1}\n"
        )
        write_config(wt, cfg)
        # Establish a committed baseline: config + vendored folder at sha1.
        run(["sync"], start=wt)
        git(["add", "-A"], wt)
        git(["commit", "-q", "-m", "baseline"], wt)

        # Upstream advances.
        sha2 = advance_source(src, sub, "# grilling v2\n")

        r = run(["update"], start=wt)
        import yaml
        parsed = yaml.safe_load(read_config(wt))
        skill_md = os.path.join(wt, ".claude", "skills", "grilling", "SKILL.md")
        content = open(skill_md).read() if os.path.isfile(skill_md) else ""
        status = git(["status", "--porcelain"], wt).stdout.strip()

        bumped = parsed["plan"]["sha"] == sha2 and sha2 != sha1
        refreshed = content == "# grilling v2\n"
        uncommitted = status != ""
        if r.returncode == 0 and bumped and refreshed and uncommitted:
            ok("update bumps the sha, refreshes the folder, leaves it uncommitted")
        else:
            bad(f"update bumps+refreshes uncommitted (rc={r.returncode}, bumped={bumped}, "
                f"refreshed={refreshed}, uncommitted={uncommitted})")


def test_check_non_mapping_config_errors():
    # A config that is not a mapping is an error, not an empty config coerced to
    # a falsely-passing check (matches sapa-gate's load_config).
    with tempfile.TemporaryDirectory() as root:
        wt = make_worktree(root)
        write_config(wt, "- a\n- b\n")
        r = run(["check"], start=wt)
        if r.returncode != 0 and "does not hold a mapping" in r.stderr:
            ok("check errors on a non-mapping config instead of passing empty")
        else:
            bad(f"check errors on a non-mapping config (rc={r.returncode}, {r.stderr!r})")


def main():
    test_help()
    test_unknown_verb()
    test_dispatch_routes()
    test_enumerate()
    test_check_passes()
    test_check_ignores_bare()
    test_check_missing_folder()
    test_check_orphan_folder()
    test_check_missing_skill_md()
    test_check_non_mapping_config_errors()
    test_lock_inserts_sha_preserving_comments()
    test_lock_errors_on_bad_config()
    test_lock_replaces_existing_sha()
    test_sync_vendors_folder_and_license()
    test_sync_errors_without_sha()
    test_sync_fails_without_license()
    test_update_bumps_and_refreshes_uncommitted()

    print()
    print(f"{pass_}/{pass_ + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
