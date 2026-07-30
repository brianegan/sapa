#!/usr/bin/env python3
"""Tests for sapa-gate, the mechanical gate-step runner.

Run: python3 tests/test_sapa_gate.py

Each case builds a throwaway git repo with its own `.sapa.yaml`, stubs `gh` on
PATH (the way the rest of bin/ is tested), and asserts on the emitted lines, the
exit code, and the side effects a step left behind — external, observable
behaviour rather than internals.

The load-bearing cases are the two the gate's correctness rests on: a `run:` step
really does receive `SAPA_BASE` and `SAPA_CHANGED_FILES` computed against the
merge-base, and a failing step stops the walk instead of letting a later green
step imply the gate passed.
"""

import json
import os
import pty
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "..", "bin", "sapa-gate")

# A gh stub for the plan read. `SAPA_TEST_PLAN` holds the plan comment body; unset
# means no sapa comment exists, so the id lookup prints nothing and `sapa issue`
# exits 3 (the plan-absent path). Any other gh call is a no-op success.
GH_STUB = r'''#!/usr/bin/env python3
import os, sys
a = sys.argv[1:]
plan = os.environ.get("SAPA_TEST_PLAN")
if os.environ.get("SAPA_TEST_GH_FAILS"):
    # A `gh` that cannot answer: no auth, no network, not a repo. `sapa issue`
    # fails with something other than exit 3, which is how the gate tells
    # "could not check" apart from "no plan is recorded".
    sys.stderr.write("gh: could not reach GitHub\n")
    sys.exit(1)
if a[:1] == ["api"] and a[-2] == "--jq" and a[1].endswith("/comments"):
    if plan:
        print("100")
    sys.exit(0)
if a[:1] == ["api"] and a[-2:] == ["--jq", ".body"]:
    print(plan or "")
    sys.exit(0)
sys.exit(0)
'''


def git(cwd, *args):
    subprocess.run(["git", "-C", cwd, *args], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def write(path, text):
    with open(path, "w") as f:
        f.write(text)


class Repo:
    """A temp git repo with a base commit, an `origin/main` ref, and a branch.

    The branch is named `42-feature` so `sapa issue` can derive a GitHub issue
    from it; the `origin/main` ref is planted locally so the merge-base diff
    resolves with no network.
    """

    def __init__(self, tmp, config, branch="42-feature", changes=("a.txt", "pkg/b.txt")):
        self.dir = os.path.join(tmp, "repo")
        os.makedirs(self.dir)
        git(self.dir, "init", "-q", "-b", "main")
        git(self.dir, "config", "user.email", "t@example.com")
        git(self.dir, "config", "user.name", "Test")
        write(os.path.join(self.dir, "seed.txt"), "seed\n")
        git(self.dir, "add", ".")
        git(self.dir, "commit", "-qm", "base")
        git(self.dir, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(self.dir, "checkout", "-q", "-b", branch)
        for rel in changes:
            path = os.path.join(self.dir, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            write(path, "change\n")
        if changes:
            git(self.dir, "add", ".")
            git(self.dir, "commit", "-qm", "work")
        write(os.path.join(self.dir, ".sapa.yaml"), config)

        self.bindir = os.path.join(tmp, "bin")
        os.makedirs(self.bindir)
        gh = os.path.join(self.bindir, "gh")
        write(gh, GH_STUB)
        os.chmod(gh, 0o755)
        self.tmpdir = os.path.join(tmp, "scratch")

    def break_pyyaml(self):
        """Put a `yaml` module that refuses to import ahead of the real one.

        The helper's own `import yaml` then raises ImportError, which is the exact
        state a machine without PyYAML is in. Simulated rather than assumed: the
        suite runs where PyYAML is installed, so this is the only way to reach the
        one error path that exists because the dependency is new.
        """
        shim = os.path.join(self.dir, "..", "noyaml")
        os.makedirs(shim, exist_ok=True)
        write(os.path.join(shim, "yaml.py"), "raise ImportError('no pyyaml here')\n")
        return os.path.abspath(shim)

    def env(self, plan=None, gh_fails=False):
        env = dict(os.environ)
        env["PATH"] = self.bindir + os.pathsep + env["PATH"]
        env["SAPA_TMP_DIR"] = self.tmpdir
        env.pop("SAPA_TEST_PLAN", None)
        env.pop("SAPA_TEST_GH_FAILS", None)
        env.pop("SAPA_BASE", None)
        env.pop("SAPA_CHANGED_FILES", None)
        if plan is not None:
            env["SAPA_TEST_PLAN"] = plan
        if gh_fails:
            env["SAPA_TEST_GH_FAILS"] = "1"
        return env

    def run(self, *args, plan=None, start=None, pythonpath=None, gh_fails=False):
        env = self.env(plan, gh_fails)
        if pythonpath is not None:
            env["PYTHONPATH"] = pythonpath
        return subprocess.run(
            [sys.executable, GATE, "--start", start or self.dir, *args],
            capture_output=True, text=True, env=env,
        )

    def run_on_a_terminal(self, *args, plan=None):
        """Run the gate with its stdout and stderr on a pty, and return its output.

        The suite itself runs with pipes, so the interactive branch of `channel`
        only gets exercised if a test supplies the terminal. Both streams share one
        pty here because the test only needs the child to see a terminal, not to
        tell the two apart.
        """
        env = self.env(plan)
        ours, theirs = pty.openpty()
        proc = subprocess.Popen(
            [sys.executable, GATE, "--start", self.dir, *args],
            stdout=theirs, stderr=theirs, env=env,
        )
        os.close(theirs)
        chunks = []
        while True:
            try:
                chunk = os.read(ours, 4096)
            except OSError:  # EIO once the child drops the last slave fd
                break
            if not chunk:
                break
            chunks.append(chunk)
        os.close(ours)
        return proc.wait(), b"".join(chunks).decode("utf-8", "replace")

    def read(self, rel):
        with open(os.path.join(self.dir, rel)) as f:
            return f.read()

    def has(self, rel):
        return os.path.exists(os.path.join(self.dir, rel))

    def plan_path(self):
        return os.path.join(self.tmpdir, "repo", "plan.md")

    def record_path(self):
        return os.path.join(self.tmpdir, "repo", "gate-record.json")

    def record(self):
        """The parsed gate record, or None when the gate wrote none."""
        try:
            with open(self.record_path()) as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def runs(self):
        return (self.record() or {}).get("runs", [])

    def write_record(self, text):
        os.makedirs(os.path.dirname(self.record_path()), exist_ok=True)
        write(self.record_path(), text)

    def sha(self, ref="HEAD"):
        return subprocess.run(["git", "-C", self.dir, "rev-parse", ref],
                              capture_output=True, text=True).stdout.strip()


def lines(stdout):
    """The emitted structured lines, split on tabs, with the marker dropped."""
    out = []
    for line in stdout.splitlines():
        parts = line.split("\t")
        if parts and parts[0] == "sapa-gate":
            out.append(parts[1:])
    return out


def run_step(name, command):
    """A `run:` step as a value, so a case spells steps rather than YAML text."""
    return {"name": name, "run": command}


def skill_step(name, skill, model=None):
    """A `skill:` step as a value, so a case spells steps rather than YAML text."""
    return {"name": name, "skill": skill, "model": model}


def gate_of(*steps, attempts=None, base=None):
    """A config holding `steps`, rendered as the YAML sapa parses.

    `max_fix_attempts` and a top-level `base:` appear only when asked for. Run
    commands are single-quoted with `'` doubled, so a command like `true` stays
    a string and indicator characters stay inert.
    """
    out = f"base: {base}\n" if base is not None else ""
    out += "gate:\n"
    if attempts is not None:
        out += f"  max_fix_attempts: {attempts}\n"
    out += "  steps:\n"
    for step in steps:
        out += f"    - name: {step['name']}\n"
        if "run" in step:
            out += "      run: '" + step["run"].replace("'", "''") + "'\n"
        else:
            out += f"      skill: {step['skill']}\n"
            if step["model"] is not None:
                out += f"      model: {step['model']}\n"
    return out


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# --- step model and config errors --------------------------------------------

@case
def test_list_prints_each_step_with_kind_and_model():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(skill_step("review", "code-review", "fable"),
                                 run_step("test", "echo hi")))
        p = repo.run("--list")
        assert p.returncode == 0, p.stderr
        assert lines(p.stdout) == [
            ["list", "review", "skill", "code-review", "fable"],
            ["list", "test", "run", "echo hi", "-"],
        ], p.stdout


@case
def test_list_runs_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("touch", "echo ran > ran.txt")))
        repo.run("--list")
        assert not repo.has("ran.txt"), "--list executed a step"


@case
def test_malformed_configs_exit_2_with_a_reason():
    bad = {
        "no gate key": "base: main\n",
        "gate not a mapping": "gate: nope\n",
        "no steps key": "gate:\n  max_fix_attempts: 3\n",
        "empty steps": "gate:\n  steps: []\n",
        "step with neither": "gate:\n  steps:\n    - name: x\n",
        "step with both": "gate:\n  steps:\n    - name: x\n      run: 'true'\n      skill: y\n",
        "unnamed step": "gate:\n  steps:\n    - run: 'true'\n",
        "duplicate names": ("gate:\n  steps:\n    - name: x\n      run: 'true'\n"
                            "    - name: x\n      run: 'true'\n"),
        "step not a mapping": "gate:\n  steps:\n    - just a string\n",
    }
    for label, config in bad.items():
        with tempfile.TemporaryDirectory() as tmp:
            p = Repo(tmp, config).run("--list")
            assert p.returncode == 2, f"{label}: expected exit 2, got {p.returncode}"
            assert p.stderr.startswith("sapa gate: "), f"{label}: {p.stderr!r}"
            assert len(p.stderr.strip()) > len("sapa gate: "), f"{label}: empty reason"


@case
def test_the_old_list_shaped_gate_is_rejected_with_the_edit_that_fixes_it():
    """`gate:` used to be the step list. Rejected, not quietly accepted.

    A config written for the old shape is a config whose author has not seen the
    new one, so the error has to name `steps:`. Reporting only that the shape is
    wrong would leave them guessing at a key that is not in their file.
    """
    with tempfile.TemporaryDirectory() as tmp:
        p = Repo(tmp, "gate:\n  - name: test\n    run: 'true'\n").run("--list")
        assert p.returncode == 2, p.returncode
        assert "steps:" in p.stderr, p.stderr
        assert lines(p.stdout) == [], "a list-shaped gate ran anyway"


@case
def test_missing_pyyaml_exits_2_and_names_it():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("test", "true")))
        p = repo.run("--list", pythonpath=repo.break_pyyaml())
        assert p.returncode == 2, p.returncode
        assert "PyYAML" in p.stderr, p.stderr
        assert "pip install pyyaml" in p.stderr, p.stderr


@case
def test_no_config_exits_2():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("x", "true")))
        os.remove(os.path.join(repo.dir, ".sapa.yaml"))
        # Start from the temp dir's own root so the walk-up can't reach a real
        # .sapa.yaml on the machine running the suite.
        p = repo.run("--list", start=repo.dir)
        assert p.returncode == 2, p.returncode


# --- run steps: the env contract, ordering, fail-fast -------------------------

@case
def test_run_step_receives_base_and_changed_files():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("capture",
                                          "printf '%s\\n' \"$SAPA_BASE\" > base.txt;"
                                          " printf '%s\\n' \"$SAPA_CHANGED_FILES\" > changed.txt"),
                                 base="main"))
        p = repo.run()
        assert p.returncode == 0, p.stderr
        assert repo.read("base.txt") == "main\n", repo.read("base.txt")
        assert repo.read("changed.txt") == "a.txt\npkg/b.txt\n", repo.read("changed.txt")


@case
def test_changed_files_is_empty_when_the_branch_matches_the_base():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("capture",
                                          "printf '[%s]' \"$SAPA_CHANGED_FILES\" > changed.txt")),
                    changes=())
        p = repo.run()
        assert p.returncode == 0, p.stderr
        assert repo.read("changed.txt") == "[]", repo.read("changed.txt")


@case
def test_unresolvable_base_warns_and_still_runs():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("capture",
                                          "printf '[%s]' \"$SAPA_CHANGED_FILES\" > changed.txt"),
                                 base="nonexistent"))
        p = repo.run()
        assert p.returncode == 0, p.stderr
        assert repo.read("changed.txt") == "[]", repo.read("changed.txt")
        assert "origin/nonexistent" in p.stderr, p.stderr


@case
def test_steps_run_in_order_and_report_exit_and_duration():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("one", "echo one >> order.txt"),
                                 run_step("two", "echo two >> order.txt")))
        p = repo.run()
        assert p.returncode == 0, p.stderr
        assert repo.read("order.txt") == "one\ntwo\n", repo.read("order.txt")
        emitted = lines(p.stdout)
        assert [e[:4] for e in emitted[:2]] == [
            ["step", "one", "run", "0"], ["step", "two", "run", "0"]], emitted
        assert all(float(e[4]) >= 0 for e in emitted[:2]), emitted
        assert emitted[-1] == ["done", "green"], emitted


@case
def test_a_failing_step_stops_the_walk_and_exits_1():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("boom", "exit 7"),
                                 run_step("later", "echo later > later.txt")))
        p = repo.run()
        assert p.returncode == 1, p.returncode
        assert not repo.has("later.txt"), "a step after the failure ran"
        emitted = lines(p.stdout)
        assert emitted[0][:4] == ["step", "boom", "run", "7"], emitted
        assert ["done", "green"] not in emitted, emitted


@case
def test_steps_run_at_the_config_root_not_the_start_dir():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("where", "pwd > where.txt")))
        nested = os.path.join(repo.dir, "pkg", "deep")
        os.makedirs(nested)
        p = repo.run(start=nested)
        assert p.returncode == 0, p.stderr
        assert repo.read("where.txt").strip() == os.path.realpath(repo.dir), repo.read("where.txt")


# --- skill steps: halt and resume ---------------------------------------------

@case
def test_a_skill_step_halts_the_walk_with_exit_4():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("first", "echo first > first.txt"),
                                 skill_step("review", "code-review", "fable"),
                                 run_step("last", "echo last > last.txt")))
        p = repo.run(plan="a plan")
        assert p.returncode == 4, p.returncode
        assert repo.has("first.txt"), "the step before the skill did not run"
        assert not repo.has("last.txt"), "a step after the skill step ran"
        assert ["needs-skill", "review", "code-review", "fable"] in lines(p.stdout), p.stdout


@case
def test_after_resumes_with_the_following_step():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("first", "echo first > first.txt"),
                                 skill_step("review", "code-review"),
                                 run_step("last", "echo last > last.txt")))
        # Walk up to the skill step the way the skill does, so the resume has the
        # record it appends to. Clearing the marker makes a re-run of `first` visible.
        repo.run(plan="a plan")
        os.remove(os.path.join(repo.dir, "first.txt"))
        p = repo.run("--after", "review", plan="a plan")
        assert p.returncode == 0, p.stderr
        assert repo.has("last.txt"), "the trailing step did not run"
        assert not repo.has("first.txt"), "--after re-ran a step before the resume point"
        assert lines(p.stdout)[-1] == ["done", "green"], p.stdout


@case
def test_a_skill_step_with_no_model_reports_a_dash():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(skill_step("review", "code-review")))
        p = repo.run(plan="a plan")
        assert ["needs-skill", "review", "code-review", "-"] in lines(p.stdout), p.stdout


@case
def test_unknown_after_name_exits_2():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("test", "true")))
        p = repo.run("--after", "nope")
        assert p.returncode == 2, p.returncode
        assert "nope" in p.stderr, p.stderr


# --- skill-step results, reported on the resume --------------------------------

SKILL_GATE = gate_of(skill_step("review", "code-review", "fable"),
                     run_step("test", "true"))


@case
def test_a_resume_records_the_skill_step_the_agent_handled():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, SKILL_GATE)
        repo.run(plan="a plan")
        p = repo.run("--after", "review", "--result", "pass",
                     "--summary", "3 findings, none blocking", plan="a plan")
        assert p.returncode == 0, p.stderr
        step = repo.runs()[0]["steps"][0]
        assert step["name"] == "review", step
        assert step["kind"] == "skill", step
        assert step["target"] == "code-review", step
        assert step["model"] == "fable", step
        assert step["result"] == "pass", step
        assert step["summary"] == "3 findings, none blocking", step
        assert step["reported_by"] == "agent", step
        assert step["duration"] is None, "a duration nothing measured was invented"
        assert ["step", "review", "skill", "pass", "-"] in lines(p.stdout), p.stdout


@case
def test_a_resume_without_a_result_counts_as_a_reported_pass():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, SKILL_GATE)
        repo.run(plan="a plan")
        repo.run("--after", "review", plan="a plan")
        step = repo.runs()[0]["steps"][0]
        assert step["result"] == "pass", step
        assert step["summary"] is None, step
        assert step["reported_by"] == "agent", step


@case
def test_a_reported_failure_stops_the_walk_and_closes_the_run():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(skill_step("review", "code-review"),
                                 run_step("test", "echo ran > ran.txt")))
        repo.run(plan="a plan")
        p = repo.run("--after", "review", "--result", "fail",
                     "--summary", "a blocking finding", plan="a plan")
        assert p.returncode == 1, p.returncode
        assert not repo.has("ran.txt"), "a step after the failed skill step ran"
        run = repo.runs()[0]
        assert run["result"] == "failed", run
        assert run["steps"][0]["result"] == "fail", run["steps"][0]


@case
def test_result_without_after_exits_2():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, SKILL_GATE)
        for args in (("--result", "pass"), ("--summary", "x")):
            p = repo.run(*args)
            assert p.returncode == 2, f"{args}: {p.returncode}"
            assert "--after" in p.stderr, p.stderr


@case
def test_reporting_a_result_for_a_run_step_exits_2():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("test", "true"),
                                 run_step("later", "true")))
        repo.run()
        p = repo.run("--after", "test", "--result", "pass")
        assert p.returncode == 2, p.returncode
        assert "run:" in p.stderr, p.stderr


@case
def test_a_two_skill_gate_records_both_reported_steps():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(skill_step("review", "code-review"),
                                 run_step("test", "true"),
                                 skill_step("docs", "doc-check")))
        repo.run(plan="a plan")
        repo.run("--after", "review", "--result", "pass", plan="a plan")
        p = repo.run("--after", "docs", "--result", "pass", plan="a plan")
        assert p.returncode == 0, p.stderr
        runs = repo.runs()
        assert len(runs) == 1, runs
        assert [s["name"] for s in runs[0]["steps"]] == ["review", "test", "docs"], \
            runs[0]["steps"]
        assert runs[0]["result"] == "green", runs[0]


# --- a resume with no usable record --------------------------------------------

RESTART_GATE = gate_of(run_step("first", "echo first >> first.txt"),
                       skill_step("review", "code-review"),
                       run_step("last", "echo last > last.txt"))


def assert_restarted(repo, p):
    """The walk went back to the top: it stopped at the skill step again, and the
    fresh run holds every step from the first one rather than a partial list."""
    assert p.returncode == 4, f"expected to halt at the skill step again: {p.returncode}"
    assert ["needs-skill", "review", "code-review", "-"] in lines(p.stdout), p.stdout
    assert "walking from the first step" in p.stderr, p.stderr
    assert not repo.has("last.txt"), "the walk carried on past the skill step"
    run = repo.runs()[-1]
    assert [s["name"] for s in run["steps"]] == ["first"], run["steps"]
    assert run["result"] == "incomplete", run


@case
def test_a_resume_with_no_record_walks_from_the_top():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, RESTART_GATE)
        p = repo.run("--after", "review", plan="a plan")
        assert_restarted(repo, p)


@case
def test_a_resume_with_an_unparseable_record_walks_from_the_top():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, RESTART_GATE)
        repo.write_record("{not json at all")
        p = repo.run("--after", "review", plan="a plan")
        assert_restarted(repo, p)


@case
def test_a_resume_against_a_finished_run_walks_from_the_top():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, RESTART_GATE)
        repo.run(plan="a plan")                              # halts at the skill step
        repo.run("--after", "review", plan="a plan")         # finishes that run
        os.remove(os.path.join(repo.dir, "last.txt"))        # so a re-run of it shows
        p = repo.run("--after", "review", plan="a plan")     # nothing left to resume
        assert_restarted(repo, p)
        assert len(repo.runs()) == 2, "the restart did not append a fresh run"


@case
def test_a_resume_whose_run_does_not_cover_the_earlier_steps_walks_from_the_top():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, RESTART_GATE)
        # An incomplete run that never ran `first`: the shape a record from another
        # config leaves behind. Appending to it would understate what the gate covered.
        repo.write_record(json.dumps({"runs": [
            {"started": "2026-01-01T00:00:00Z", "scope": "full", "result": "incomplete",
             "base_ref": "origin/main", "base_sha": None, "head_sha": None,
             "spec_source": "not-looked-up", "steps": []},
        ]}))
        p = repo.run("--after", "review", plan="a plan")
        assert_restarted(repo, p)


@case
def test_the_restart_does_not_discard_earlier_runs():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, RESTART_GATE)
        repo.run(plan="a plan")
        repo.run("--after", "review", plan="a plan")
        first_started = repo.runs()[0]["started"]
        repo.run("--after", "review", plan="a plan")
        runs = repo.runs()
        assert len(runs) == 2, runs
        assert runs[0]["started"] == first_started, "the completed run was overwritten"
        assert runs[0]["result"] == "green", runs[0]


# --- the plan contract ---------------------------------------------------------

@case
def test_a_recorded_plan_is_materialized_and_marked_present():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(skill_step("review", "code-review")))
        p = repo.run(plan="## Tasks\n\n1. do the thing")
        plan_line = [e for e in lines(p.stdout) if e[0] == "plan"]
        assert plan_line == [["plan", repo.plan_path(), "present"]], p.stdout
        assert os.path.isabs(repo.plan_path()), repo.plan_path()
        with open(repo.plan_path()) as f:
            assert "do the thing" in f.read()


@case
def test_no_recorded_plan_is_marked_absent_and_writes_no_file():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(skill_step("review", "code-review")))
        p = repo.run()  # no SAPA_TEST_PLAN => sapa issue exits 3
        plan_line = [e for e in lines(p.stdout) if e[0] == "plan"]
        assert plan_line == [["plan", repo.plan_path(), "absent"]], p.stdout
        assert not os.path.exists(repo.plan_path()), "absent must not leave a file behind"


@case
def test_an_absent_plan_does_not_fail_the_gate():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("check", "echo ran > ran.txt"),
                                 skill_step("review", "code-review")))
        p = repo.run()
        assert p.returncode == 4, p.returncode  # stopped at the skill, not failed
        assert repo.has("ran.txt"), "the run step was skipped over an absent plan"


@case
def test_a_plan_that_cannot_be_read_is_recorded_as_unreadable_not_absent():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(skill_step("review", "code-review")))
        p = repo.run(plan="a plan", gh_fails=True)
        assert p.returncode == 4, p.returncode  # still halts at the skill, never fails
        assert repo.runs()[0]["spec_source"] == "unreadable", repo.runs()[0]
        # The emitted line still collapses to `absent`, which is all the skill needs,
        # while stderr and the record carry the difference.
        assert [e for e in lines(p.stdout) if e[0] == "plan"][0][2] == "absent", p.stdout
        assert "could not read the plan comment" in p.stderr, p.stderr
        out = repo.run("--report").stdout
        assert "The recorded plan could not be read" in out, out


@case
def test_a_run_only_gate_does_not_look_up_a_plan():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("test", "true")))
        p = repo.run(plan="a plan")
        assert [e for e in lines(p.stdout) if e[0] == "plan"] == [], p.stdout
        assert not os.path.exists(repo.plan_path()), "a run-only gate materialized a plan"


@case
def test_resuming_past_the_last_skill_step_skips_the_plan_lookup():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(skill_step("review", "code-review"),
                                 run_step("test", "true")))
        repo.run(plan="a plan")  # the walk that stops at the skill step looks it up
        p = repo.run("--after", "review", plan="a plan")
        assert [e for e in lines(p.stdout) if e[0] == "plan"] == [], p.stdout


# --- the output tail -----------------------------------------------------------

@case
def test_all_output_streams_through_while_only_the_tail_is_recorded():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("chatty",
                                          "for i in $(seq 1 500); do echo line-$i; done")))
        p = repo.run()
        assert p.returncode == 0, p.stderr
        assert p.stdout.count("line-") == 500, p.stdout.count("line-")
        tail = repo.runs()[0]["steps"][0]["tail"]
        assert tail.endswith("line-500"), tail[-80:]
        assert "line-1\n" not in tail, "the tail kept the whole output"
        assert len(tail.splitlines()) <= 40, len(tail.splitlines())


@case
def test_the_tail_is_capped_by_characters_too():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("wide",
                                          "head -c 20000 /dev/zero | tr '\\0' 'x'")))
        repo.run()
        tail = repo.runs()[0]["steps"][0]["tail"]
        assert len(tail) == 4000, len(tail)


@case
def test_stdout_and_stderr_stay_on_their_own_streams():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("talk",
                                          "echo to-stdout; echo to-stderr >&2")))
        p = repo.run()
        assert "to-stdout" in p.stdout, p.stdout
        assert "to-stderr" not in p.stdout, "stderr was merged into stdout"
        assert "to-stderr" in p.stderr, p.stderr


@case
def test_both_streams_reach_the_tail():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("talk",
                                          "echo to-stdout; echo to-stderr >&2")))
        repo.run()
        tail = repo.runs()[0]["steps"][0]["tail"]
        assert "to-stdout" in tail and "to-stderr" in tail, tail


@case
def test_a_piped_gate_gives_its_step_no_terminal():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("tty",
                                          "if [ -t 1 ]; then echo TTY; else echo NOTTY; fi")))
        repo.run()
        assert repo.runs()[0]["steps"][0]["tail"] == "NOTTY", repo.runs()[0]["steps"][0]


@case
def test_an_interactive_gate_gives_its_step_a_terminal():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("tty",
                                          "if [ -t 1 ]; then echo TTY; else echo NOTTY; fi")))
        code, out = repo.run_on_a_terminal()
        assert code == 0, out
        assert "TTY" in out and "NOTTY" not in out, out
        assert repo.runs()[0]["steps"][0]["tail"] == "TTY", repo.runs()[0]["steps"][0]


@case
def test_the_recorded_tail_carries_no_escape_sequences():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("colour",
                                          "printf '\\033[31mred\\033[0m\\n'")))
        code, out = repo.run_on_a_terminal()
        assert code == 0, out
        assert "\033[31m" in out, "the colour never reached the terminal"
        assert repo.runs()[0]["steps"][0]["tail"] == "red", \
            repr(repo.runs()[0]["steps"][0]["tail"])


@case
def test_the_recorded_tail_is_cleaned_the_same_way_with_or_without_a_terminal():
    """A pty changes what the step sees. It must not change what the record keeps.

    The step reports whether it got a terminal and then emits colour unconditionally,
    so the two runs differ only in the line that is supposed to differ, and the
    escape stripping is observably the same on both paths.
    """
    config = gate_of(run_step("both",
                              "if [ -t 1 ]; then echo TTY; else echo NOTTY; fi;"
                              " printf '\\033[31mred\\033[0m\\n'"))
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        on_a_pty = Repo(a, config)
        on_a_pty.run_on_a_terminal()
        through_a_pipe = Repo(b, config)
        through_a_pipe.run()
        pty_tail = on_a_pty.runs()[0]["steps"][0]["tail"]
        pipe_tail = through_a_pipe.runs()[0]["steps"][0]["tail"]
        assert pty_tail == "TTY\nred", repr(pty_tail)
        assert pipe_tail == "NOTTY\nred", repr(pipe_tail)
        assert "\033" not in pty_tail and "\033" not in pipe_tail, "an escape survived"


@case
def test_a_line_rewritten_in_place_collapses_to_what_the_terminal_shows():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("progress",
                                          "printf '10%%\\r50%%\\r100%%\\n'")))
        repo.run()
        assert repo.runs()[0]["steps"][0]["tail"] == "100%", \
            repr(repo.runs()[0]["steps"][0]["tail"])


# --- the record: runs, append semantics, per-run stamps -----------------------

@case
def test_a_bare_invocation_appends_a_run_rather_than_replacing_it():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("test", "true")))
        repo.run()
        repo.run()
        runs = repo.runs()
        assert len(runs) == 2, runs
        assert runs[0]["started"] != runs[1]["started"], runs
        assert all(r["result"] == "green" for r in runs), runs


@case
def test_a_resume_adds_its_steps_to_the_last_run():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("first", "true"),
                                 skill_step("review", "code-review"),
                                 run_step("last", "true")))
        repo.run(plan="a plan")                        # stops at the skill step
        repo.run("--after", "review", plan="a plan")   # finishes the walk
        runs = repo.runs()
        assert len(runs) == 1, f"the resume started a second run: {runs}"
        assert [s["name"] for s in runs[0]["steps"]] == ["first", "review", "last"], \
            runs[0]["steps"]
        assert runs[0]["result"] == "green", runs[0]


@case
def test_the_record_keeps_at_most_twenty_runs():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("test", "true")))
        seeded = [{"started": f"2026-01-01T00:00:{i:02d}Z", "scope": "full",
                   "result": "green", "base_ref": "origin/main", "base_sha": None,
                   "head_sha": None, "spec_source": "not-looked-up", "steps": [],
                   "seq": i} for i in range(20)]
        repo.write_record(json.dumps({"runs": seeded}))
        repo.run()
        runs = repo.runs()
        assert len(runs) == 20, len(runs)
        assert [r.get("seq") for r in runs[:19]] == list(range(1, 20)), \
            "the oldest run was not the one dropped"
        assert "seq" not in runs[-1], "the new run is not last"


@case
def test_a_run_records_the_shas_it_gated():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("test", "true")))
        repo.run()
        run = repo.runs()[0]
        assert run["head_sha"] == repo.sha("HEAD"), run
        assert run["base_sha"] == repo.sha("origin/main"), run
        assert run["base_ref"] == "origin/main", run
        assert run["scope"] == "full", run


@case
def test_an_unresolvable_base_records_a_null_sha_rather_than_guessing():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("test", "true"), base="nonexistent"))
        repo.run()
        run = repo.runs()[0]
        assert run["base_sha"] is None, run
        assert run["base_ref"] == "origin/nonexistent", run


@case
def test_a_failing_step_closes_the_run_as_failed():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("boom", "exit 7"),
                                 run_step("later", "true")))
        repo.run()
        run = repo.runs()[0]
        assert run["result"] == "failed", run
        assert [s["name"] for s in run["steps"]] == ["boom"], run["steps"]
        assert run["steps"][0]["exit"] == 7, run["steps"][0]
        assert run["steps"][0]["result"] == "fail", run["steps"][0]


@case
def test_a_run_halted_at_a_skill_step_stays_incomplete():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(skill_step("review", "code-review")))
        repo.run(plan="a plan")
        run = repo.runs()[0]
        assert run["result"] == "incomplete", run
        assert run["spec_source"] == "present", run


@case
def test_the_record_names_which_spec_source_state_applied():
    states = {
        "present": (gate_of(skill_step("review", "code-review")), "a plan"),
        "absent": (gate_of(skill_step("review", "code-review")), None),
        "not-looked-up": (gate_of(run_step("test", "true")), "a plan"),
    }
    for expected, (config, plan) in states.items():
        with tempfile.TemporaryDirectory() as tmp:
            repo = Repo(tmp, config)
            repo.run(plan=plan)
            got = repo.runs()[0]["spec_source"]
            assert got == expected, f"expected {expected}, got {got}"


@case
def test_a_step_entry_carries_its_command_and_model():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("test", "echo hi")))
        repo.run()
        step = repo.runs()[0]["steps"][0]
        assert step["target"] == "echo hi", step
        assert step["kind"] == "run", step
        assert step["model"] is None, step
        assert step["duration"] >= 0, step


# --- --report: the PR's Gates section -------------------------------------------

@case
def test_report_with_no_record_says_so_and_exits_0():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("test", "true")))
        p = repo.run("--report")
        assert p.returncode == 0, p.stderr
        assert p.stdout.startswith("## Gates\n"), p.stdout
        assert "No gate record was found" in p.stdout, p.stdout


@case
def test_report_lists_the_steps_that_ran_by_name():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(skill_step("review", "code-review", "fable"),
                                 run_step("test", "echo hi")))
        repo.run(plan="a plan")
        repo.run("--after", "review", "--result", "pass", plan="a plan")
        out = repo.run("--report").stdout
        assert "- **review**: skill `code-review` on `fable`, passed, agent-reported" in out, out
        assert "- **test**: command, passed in " in out, out
        assert "echo hi" not in out, "the report printed the command"
        assert "Reviewed against the plan recorded on the issue." in out, out
        assert f"Gated `{repo.sha()[:7]}` against `origin/main@{repo.sha('origin/main')[:7]}`." in out, out


@case
def test_report_marks_a_skill_step_as_agent_reported_and_a_run_step_as_timed():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(skill_step("review", "code-review"),
                                 run_step("test", "true")))
        repo.run(plan="a plan")
        repo.run("--after", "review", plan="a plan")
        out = repo.run("--report").stdout
        assert "- **review**: skill `code-review`, passed, agent-reported" in out, out
        assert "agent-reported" not in out.split("- **test**")[1], \
            "a run step was reported as an agent claim"


@case
def test_report_shows_a_failed_run_and_the_step_that_failed():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("boom", "exit 7")))
        repo.run()
        out = repo.run("--report").stdout
        assert "- **boom**: command, failed (exit 7) after " in out, out
        assert "This run did not go green." in out, out


@case
def test_report_says_when_a_run_never_finished():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(skill_step("review", "code-review")))
        repo.run(plan="a plan")  # halts at the skill step, never resumed
        out = repo.run("--report").stdout
        assert "This run never finished, so the list above is partial." in out, out


@case
def test_report_flags_a_head_that_moved_since_the_gate_ran():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("test", "true")))
        repo.run()
        gated = repo.sha()
        write(os.path.join(repo.dir, "more.txt"), "more\n")
        git(repo.dir, "add", ".")
        git(repo.dir, "commit", "-qm", "one more")
        out = repo.run("--report").stdout
        assert f"The gate ran on `{gated[:7]}`, which is not the current head " \
               f"`{repo.sha()[:7]}`." in out, out


@case
def test_report_says_nothing_about_a_moved_head_when_it_has_not_moved():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("test", "true")))
        repo.run()
        assert "not the current head" not in repo.run("--report").stdout


@case
def test_report_states_each_spec_source_case():
    expected = {
        "present": "Reviewed against the plan recorded on the issue.",
        "absent": "No plan is recorded on the issue, so no step was given one as a "
                  "spec source.",
        "unreadable": "The recorded plan could not be read, so no step was given one "
                      "as a spec source.",
        "not-looked-up": "No step was given the recorded plan as a spec source.",
    }
    for state, line in expected.items():
        with tempfile.TemporaryDirectory() as tmp:
            repo = Repo(tmp, gate_of(run_step("test", "true")))
            repo.run()
            record = repo.record()
            record["runs"][-1]["spec_source"] = state
            repo.write_record(json.dumps(record))
            out = repo.run("--report").stdout
            assert line in out, f"{state}: {out}"
        # The thin-gate case is the one worth reading at a glance.
        if state == "not-looked-up":
            assert "Reviewed against" not in out, out


@case
def test_report_names_an_unresolved_base_rather_than_inventing_one():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("test", "true"), base="nonexistent"))
        repo.run()
        out = repo.run("--report").stdout
        assert "against `origin/nonexistent` (unresolved)." in out, out


@case
def test_report_reads_the_most_recent_run():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("first", "exit 3")))
        repo.run()
        write(os.path.join(repo.dir, ".sapa.yaml"),
              gate_of(run_step("second", "true")))
        repo.run()
        out = repo.run("--report").stdout
        assert "- **second**: command, passed" in out, out
        assert "first" not in out, "the report described a superseded run"


@case
def test_report_runs_no_steps():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(run_step("touch", "echo ran > ran.txt")))
        repo.run("--report")
        assert not repo.has("ran.txt"), "--report executed a step"


# --- the autofix budget: attempts, the line, the refusal ------------------------

# One step that always fails, and the same step passing, so an episode of fixes can
# be walked end to end by swapping the config the way a real fix swaps the code.
BOOM = run_step("boom", "exit 1")
FINE = run_step("boom", "true")

FAILING_GATE = gate_of(BOOM)


def attempts_line(p):
    """The `attempts` line the run emitted, or None."""
    return next((l for l in lines(p.stdout) if l[0] == "attempts"), None)


@case
def test_a_bare_run_opens_an_episode_at_attempt_zero():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, FAILING_GATE)
        p = repo.run()
        assert p.returncode == 1, p.returncode
        assert repo.runs()[-1]["attempt"] == 0, repo.runs()[-1]
        assert attempts_line(p) == ["attempts", "0", "3"], p.stdout


@case
def test_fix_attempt_counts_up_across_separate_invocations():
    """Each re-run is its own process, so the count has to live in the record.

    Walked the way the skill walks it: fail, fix, re-run, fail. Nothing in this
    test carries state between the calls except the record on disk.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, FAILING_GATE)
        repo.run()
        for expected in (1, 2, 3):
            p = repo.run("--fix-attempt")
            assert p.returncode == 1, f"attempt {expected}: {p.returncode} {p.stderr}"
            assert repo.runs()[-1]["attempt"] == expected, repo.runs()[-1]
            assert attempts_line(p) == ["attempts", str(expected), "3"], p.stdout


@case
def test_a_green_run_ends_the_episode_so_the_count_starts_over():
    """A `--fix-attempt` straight after a green run is the first of a new episode.

    Green is what the attempts were spent reaching, so they go with it. Carried
    forward, a stream that went green on its second fix would be refused its first
    fix next time. The budget is 2 and the green lands on attempt 2, so the last
    call is refused outright if the count does not start over.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(BOOM, attempts=2))
        repo.run()
        repo.run("--fix-attempt")
        assert repo.runs()[-1]["attempt"] == 1, repo.runs()[-1]

        write(os.path.join(repo.dir, ".sapa.yaml"), gate_of(FINE, attempts=2))
        assert repo.run("--fix-attempt").returncode == 0, "the gate did not go green"
        assert repo.runs()[-1]["attempt"] == 2, repo.runs()[-1]

        write(os.path.join(repo.dir, ".sapa.yaml"), gate_of(BOOM, attempts=2))
        p = repo.run("--fix-attempt")
        assert p.returncode == 1, f"the spent budget carried past a green run: {p.stderr}"
        assert repo.runs()[-1]["attempt"] == 1, repo.runs()[-1]


@case
def test_a_fix_attempt_past_the_budget_is_refused_and_runs_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(BOOM, attempts=2))
        repo.run()
        repo.run("--fix-attempt")
        repo.run("--fix-attempt")
        before = len(repo.runs())

        p = repo.run("--fix-attempt")
        assert p.returncode == 5, f"expected the refusal, got {p.returncode}"
        assert attempts_line(p) == ["attempts", "2", "2"], p.stdout
        assert "not converging" in p.stderr, p.stderr
        assert len(repo.runs()) == before, "the refused run was recorded anyway"
        assert not any(l[0] == "step" for l in lines(p.stdout)), "a step ran anyway"


@case
def test_a_budget_of_zero_never_autofixes():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(BOOM, attempts=0))
        p = repo.run()
        assert p.returncode == 1, p.returncode
        assert attempts_line(p) == ["attempts", "0", "0"], p.stdout
        assert repo.run("--fix-attempt").returncode == 5, "a fix ran on a zero budget"


@case
def test_an_explicit_budget_is_what_the_attempts_line_reports():
    with tempfile.TemporaryDirectory() as tmp:
        p = Repo(tmp, gate_of(BOOM, attempts=7)).run()
        assert attempts_line(p) == ["attempts", "0", "7"], p.stdout


@case
def test_a_budget_that_is_not_a_count_exits_2():
    for value in ("-1", "three", "1.5", "yes"):
        with tempfile.TemporaryDirectory() as tmp:
            p = Repo(tmp, gate_of(BOOM, attempts=value)).run("--list")
            assert p.returncode == 2, f"{value}: expected exit 2, got {p.returncode}"
            assert "max_fix_attempts" in p.stderr, f"{value}: {p.stderr!r}"


@case
def test_a_failed_skill_step_reports_the_attempts_too():
    """A skill step the agent resumed with `--result fail` is a failed run like any
    other, so the skill needs the same budget reading before it fixes and re-runs."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(skill_step("review", "code-review")))
        repo.run(plan="a plan")
        p = repo.run("--after", "review", "--result", "fail",
                     "--summary", "found a real problem", plan="a plan")
        assert p.returncode == 1, p.returncode
        assert attempts_line(p) == ["attempts", "0", "3"], p.stdout


@case
def test_fix_attempt_with_after_is_a_usage_error():
    """A mid-walk resume is not a new attempt. Counting it would spend the budget on
    a gate that has a skill step in it, twice as fast as one that does not."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, gate_of(skill_step("review", "code-review")))
        repo.run(plan="a plan")
        p = repo.run("--after", "review", "--fix-attempt", plan="a plan")
        assert p.returncode == 2, p.returncode
        assert "--fix-attempt" in p.stderr, p.stderr


@case
def test_a_fix_attempt_with_no_record_runs_and_says_the_count_is_a_guess():
    """Scratch can be cleared between re-runs. Losing it should cost the accuracy of
    the count, not the ability to check the branch."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, FAILING_GATE)
        p = repo.run("--fix-attempt")
        assert p.returncode == 1, f"the gate refused to run without a record: {p.stderr}"
        assert "no gate record" in p.stderr, p.stderr
        assert repo.runs()[-1]["attempt"] == 1, repo.runs()[-1]


@case
def test_the_report_says_nothing_about_attempts():
    """The gate fixes locally before anything is pushed, and sapa's fixes are commits
    in the PR already, so narrating the count to a reviewer discloses nothing new."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, FAILING_GATE)
        repo.run()
        repo.run("--fix-attempt")
        out = repo.run("--report").stdout
        assert "attempt" not in out.lower(), out


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
