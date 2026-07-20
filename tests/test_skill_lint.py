#!/usr/bin/env python3
"""A deterministic linter for sapa's own SKILL.md files, plus its self-tests.

Run: python3 tests/test_skill_lint.py

sapa's skills are preference skills — durable, opinionated workflow, the kind a
talk on skill evals argues you should protect. A model-graded eval would mean
running a model in CI, which costs money or grades on a proxy model that isn't
the Claude the skills actually run on. So this stays deterministic: it asserts
the mechanical rules that need no model, and runs free in the same CI as the
rest. Model-graded triggering evals remain a maybe-later local script, out of CI
(see PRD Testing Decisions).

Checks per skill:
  - frontmatter is present and well-formed, with a non-empty name and description
  - name matches the skill's directory
  - SKILL.md is under 500 lines (the talk's threshold)
  - the description stays under a char budget (it is paid on every model call)
Across skills:
  - no two skills claim the same quoted trigger phrase

Scope: the collision check compares sapa's own skills against each other only.
Collisions with other installed skills (e.g. wingspan's /plan) are invisible from
here.

This is an internal test-suite util, not a `sapa` subcommand — it is never wired
into the dispatcher and never exposed to end users.
"""

import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.join(HERE, "..", "skill")

MAX_LINES = 500       # the talk's "keep a skill below 500 lines" rule
MAX_DESC_CHARS = 500  # the description is context cost on every call; catch bloat

# YAML block-scalar indicators. parse_frontmatter reads only single-line values,
# which fits sapa's skills; a description written as a block scalar would parse to
# just the indicator and slip past the char cap and phrase checks. Flag it rather
# than measure it wrong.
BLOCK_SCALARS = {"|", ">", "|-", ">-", "|+", ">+"}

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


def parse_frontmatter(text):
    """Return the top-level key/value frontmatter dict, or None if absent/unterminated.

    Minimal on purpose: sapa's frontmatter is flat `key: value` lines with a
    single-line value, so this avoids a YAML dependency. Deeper structure would
    need a real parser, but sapa's skills never use it.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    fm = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fm
        if line and not line[0].isspace() and ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return None  # opened with --- but never closed


def quoted_phrases(text):
    """The distinct non-empty double-quoted substrings of a description."""
    return {p.strip().lower() for p in re.findall(r'"([^"]*)"', text) if p.strip()}


def lint(skill_dir):
    """Lint every `<name>/SKILL.md` under skill_dir. Return a list of violations.

    An empty list means clean. Each violation is a human-readable string.
    """
    violations = []
    phrase_owners = {}  # trigger phrase -> list of skills that claim it

    for name in sorted(os.listdir(skill_dir)):
        path = os.path.join(skill_dir, name, "SKILL.md")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()

        fm = parse_frontmatter(text)
        if fm is None:
            violations.append("%s: missing or malformed frontmatter" % name)
            continue

        fm_name = fm.get("name", "")
        desc = fm.get("description", "")

        if not fm_name:
            violations.append("%s: frontmatter has no name" % name)
        elif fm_name != name:
            violations.append(
                "%s: name %r does not match its directory" % (name, fm_name))

        if not desc:
            violations.append("%s: frontmatter has no description" % name)
        elif desc in BLOCK_SCALARS:
            violations.append(
                "%s: description uses a multi-line YAML scalar the linter can't measure" % name)
        elif len(desc) > MAX_DESC_CHARS:
            violations.append(
                "%s: description is %d chars (max %d)" % (name, len(desc), MAX_DESC_CHARS))

        n_lines = len(text.splitlines())
        if n_lines > MAX_LINES:
            violations.append(
                "%s: SKILL.md is %d lines (max %d)" % (name, n_lines, MAX_LINES))

        for phrase in quoted_phrases(desc):
            phrase_owners.setdefault(phrase, []).append(name)

    for phrase, owners in sorted(phrase_owners.items()):
        if len(owners) > 1:
            violations.append(
                "trigger phrase %r is claimed by more than one skill: %s"
                % (phrase, ", ".join(sorted(owners))))

    return violations


# --- Real skills: the whole point. They must lint clean. ---

real = lint(SKILL_DIR)
if real == []:
    ok("sapa's own skills lint clean")
else:
    bad("sapa's own skills have violations:\n    " + "\n    ".join(real))


# --- Self-tests: prove each rule has teeth against a crafted skill tree. ---

def write_skill(root, dir_name, name=None, description="A fine skill.",
                extra_body_lines=0, frontmatter=True):
    """Create <root>/<dir_name>/SKILL.md. name defaults to dir_name."""
    if name is None:
        name = dir_name
    d = os.path.join(root, dir_name)
    os.makedirs(d)
    body = "\n# " + dir_name + "\n\nBody.\n" + ("filler\n" * extra_body_lines)
    if frontmatter:
        text = "---\nname: %s\ndescription: %s\n---\n%s" % (name, description, body)
    else:
        text = "# " + dir_name + "\n\nNo frontmatter here.\n"
    with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(text)


def write_raw(root, dir_name, text):
    """Create <root>/<dir_name>/SKILL.md with exactly `text`, for odd frontmatter."""
    d = os.path.join(root, dir_name)
    os.makedirs(d)
    with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(text)


def has(violations, substr):
    return any(substr in v for v in violations)


with tempfile.TemporaryDirectory() as root:
    write_skill(root, "good", description='Use when the user says "good".')
    v = lint(root)
    if v == []:
        ok("a well-formed skill lints clean")
    else:
        bad("a well-formed skill wrongly flagged: %r" % v)

with tempfile.TemporaryDirectory() as root:
    write_skill(root, "nofm", frontmatter=False)
    if has(lint(root), "frontmatter"):
        ok("missing frontmatter is flagged")
    else:
        bad("missing frontmatter not flagged: %r" % lint(root))

with tempfile.TemporaryDirectory() as root:
    write_raw(root, "unterminated", "---\nname: unterminated\ndescription: x\nno closing marker\n")
    if has(lint(root), "frontmatter"):
        ok("unterminated frontmatter is flagged")
    else:
        bad("unterminated frontmatter not flagged: %r" % lint(root))

with tempfile.TemporaryDirectory() as root:
    write_raw(root, "blockdesc",
              "---\nname: blockdesc\ndescription: |\n  A multi-line\n  description.\n---\n# body\n")
    if has(lint(root), "multi-line YAML scalar"):
        ok("a block-scalar description is flagged rather than mismeasured")
    else:
        bad("block-scalar description not flagged: %r" % lint(root))

with tempfile.TemporaryDirectory() as root:
    write_skill(root, "mismatch", name="something-else")
    if has(lint(root), "does not match its directory"):
        ok("a name that does not match its directory is flagged")
    else:
        bad("name/dir mismatch not flagged: %r" % lint(root))

with tempfile.TemporaryDirectory() as root:
    write_skill(root, "nodesc", description="")
    if has(lint(root), "no description"):
        ok("an empty description is flagged")
    else:
        bad("empty description not flagged: %r" % lint(root))

with tempfile.TemporaryDirectory() as root:
    write_skill(root, "toolong", extra_body_lines=MAX_LINES + 5)
    if has(lint(root), "lines (max"):
        ok("a SKILL.md over the line limit is flagged")
    else:
        bad("over-long SKILL.md not flagged: %r" % lint(root))

with tempfile.TemporaryDirectory() as root:
    write_skill(root, "bloated", description="x" * (MAX_DESC_CHARS + 1))
    if has(lint(root), "description is"):
        ok("a description over the char budget is flagged")
    else:
        bad("bloated description not flagged: %r" % lint(root))

with tempfile.TemporaryDirectory() as root:
    write_skill(root, "alpha", description='Use when the user says "do it".')
    write_skill(root, "beta", description='Also use when the user says "do it".')
    if has(lint(root), "claimed by more than one skill"):
        ok("a trigger phrase shared by two skills is flagged")
    else:
        bad("shared trigger phrase not flagged: %r" % lint(root))

print()
print("%d/%d passed" % (pass_, pass_ + fail))
sys.exit(1 if fail else 0)
