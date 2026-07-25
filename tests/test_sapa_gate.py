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

import os
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

    def run(self, *args, plan=None, start=None, pythonpath=None):
        env = dict(os.environ)
        env["PATH"] = self.bindir + os.pathsep + env["PATH"]
        env["SAPA_TMP_DIR"] = self.tmpdir
        env.pop("SAPA_TEST_PLAN", None)
        env.pop("SAPA_BASE", None)
        env.pop("SAPA_CHANGED_FILES", None)
        if plan is not None:
            env["SAPA_TEST_PLAN"] = plan
        if pythonpath is not None:
            env["PYTHONPATH"] = pythonpath
        return subprocess.run(
            [sys.executable, GATE, "--start", start or self.dir, *args],
            capture_output=True, text=True, env=env,
        )

    def read(self, rel):
        with open(os.path.join(self.dir, rel)) as f:
            return f.read()

    def has(self, rel):
        return os.path.exists(os.path.join(self.dir, rel))

    def plan_path(self):
        return os.path.join(self.tmpdir, "repo", "plan.md")


def lines(stdout):
    """The emitted structured lines, split on tabs, with the marker dropped."""
    out = []
    for line in stdout.splitlines():
        parts = line.split("\t")
        if parts and parts[0] == "sapa-gate":
            out.append(parts[1:])
    return out


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# --- step model and config errors --------------------------------------------

@case
def test_list_prints_each_step_with_kind_and_model():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "gate:\n"
                         "  - name: review\n"
                         "    skill: code-review\n"
                         "    model: fable\n"
                         "  - name: test\n"
                         "    run: echo hi\n")
        p = repo.run("--list")
        assert p.returncode == 0, p.stderr
        assert lines(p.stdout) == [
            ["list", "review", "skill", "code-review", "fable"],
            ["list", "test", "run", "echo hi", "-"],
        ], p.stdout


@case
def test_list_runs_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "gate:\n  - name: touch\n    run: echo ran > ran.txt\n")
        repo.run("--list")
        assert not repo.has("ran.txt"), "--list executed a step"


@case
def test_malformed_configs_exit_2_with_a_reason():
    bad = {
        "no gate key": "base: main\n",
        "empty gate": "gate: []\n",
        "step with neither": "gate:\n  - name: x\n",
        "step with both": "gate:\n  - name: x\n    run: 'true'\n    skill: y\n",
        "unnamed step": "gate:\n  - run: 'true'\n",
        "duplicate names": "gate:\n  - name: x\n    run: 'true'\n  - name: x\n    run: 'true'\n",
        "step not a mapping": "gate:\n  - just a string\n",
    }
    for label, config in bad.items():
        with tempfile.TemporaryDirectory() as tmp:
            p = Repo(tmp, config).run("--list")
            assert p.returncode == 2, f"{label}: expected exit 2, got {p.returncode}"
            assert p.stderr.startswith("sapa gate: "), f"{label}: {p.stderr!r}"
            assert len(p.stderr.strip()) > len("sapa gate: "), f"{label}: empty reason"


@case
def test_missing_pyyaml_exits_2_and_names_it():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "gate:\n  - name: test\n    run: 'true'\n")
        p = repo.run("--list", pythonpath=repo.break_pyyaml())
        assert p.returncode == 2, p.returncode
        assert "PyYAML" in p.stderr, p.stderr
        assert "pip install pyyaml" in p.stderr, p.stderr


@case
def test_no_config_exits_2():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "gate:\n  - name: x\n    run: 'true'\n")
        os.remove(os.path.join(repo.dir, ".sapa.yaml"))
        # Start from the temp dir's own root so the walk-up can't reach a real
        # .sapa.yaml on the machine running the suite.
        p = repo.run("--list", start=repo.dir)
        assert p.returncode == 2, p.returncode


# --- run steps: the env contract, ordering, fail-fast -------------------------

@case
def test_run_step_receives_base_and_changed_files():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "base: main\n"
                         "gate:\n"
                         "  - name: capture\n"
                         "    run: printf '%s\\n' \"$SAPA_BASE\" > base.txt;"
                         " printf '%s\\n' \"$SAPA_CHANGED_FILES\" > changed.txt\n")
        p = repo.run()
        assert p.returncode == 0, p.stderr
        assert repo.read("base.txt") == "main\n", repo.read("base.txt")
        assert repo.read("changed.txt") == "a.txt\npkg/b.txt\n", repo.read("changed.txt")


@case
def test_changed_files_is_empty_when_the_branch_matches_the_base():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "gate:\n  - name: capture\n"
                         "    run: printf '[%s]' \"$SAPA_CHANGED_FILES\" > changed.txt\n",
                    changes=())
        p = repo.run()
        assert p.returncode == 0, p.stderr
        assert repo.read("changed.txt") == "[]", repo.read("changed.txt")


@case
def test_unresolvable_base_warns_and_still_runs():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "base: nonexistent\n"
                         "gate:\n  - name: capture\n"
                         "    run: printf '[%s]' \"$SAPA_CHANGED_FILES\" > changed.txt\n")
        p = repo.run()
        assert p.returncode == 0, p.stderr
        assert repo.read("changed.txt") == "[]", repo.read("changed.txt")
        assert "origin/nonexistent" in p.stderr, p.stderr


@case
def test_steps_run_in_order_and_report_exit_and_duration():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "gate:\n"
                         "  - name: one\n    run: echo one >> order.txt\n"
                         "  - name: two\n    run: echo two >> order.txt\n")
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
        repo = Repo(tmp, "gate:\n"
                         "  - name: boom\n    run: exit 7\n"
                         "  - name: later\n    run: echo later > later.txt\n")
        p = repo.run()
        assert p.returncode == 1, p.returncode
        assert not repo.has("later.txt"), "a step after the failure ran"
        emitted = lines(p.stdout)
        assert emitted[0][:4] == ["step", "boom", "run", "7"], emitted
        assert ["done", "green"] not in emitted, emitted


@case
def test_step_output_streams_through():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "gate:\n  - name: talk\n    run: echo to-stdout; echo to-stderr >&2\n")
        p = repo.run()
        assert "to-stdout" in p.stdout, p.stdout
        assert "to-stderr" in p.stderr, p.stderr


@case
def test_steps_run_at_the_config_root_not_the_start_dir():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "gate:\n  - name: where\n    run: pwd > where.txt\n")
        nested = os.path.join(repo.dir, "pkg", "deep")
        os.makedirs(nested)
        p = repo.run(start=nested)
        assert p.returncode == 0, p.stderr
        assert repo.read("where.txt").strip() == os.path.realpath(repo.dir), repo.read("where.txt")


# --- skill steps: halt and resume ---------------------------------------------

@case
def test_a_skill_step_halts_the_walk_with_exit_4():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "gate:\n"
                         "  - name: first\n    run: echo first > first.txt\n"
                         "  - name: review\n    skill: code-review\n    model: fable\n"
                         "  - name: last\n    run: echo last > last.txt\n")
        p = repo.run(plan="a plan")
        assert p.returncode == 4, p.returncode
        assert repo.has("first.txt"), "the step before the skill did not run"
        assert not repo.has("last.txt"), "a step after the skill step ran"
        assert ["needs-skill", "review", "code-review", "fable"] in lines(p.stdout), p.stdout


@case
def test_after_resumes_with_the_following_step():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "gate:\n"
                         "  - name: first\n    run: echo first > first.txt\n"
                         "  - name: review\n    skill: code-review\n"
                         "  - name: last\n    run: echo last > last.txt\n")
        p = repo.run("--after", "review", plan="a plan")
        assert p.returncode == 0, p.stderr
        assert repo.has("last.txt"), "the trailing step did not run"
        assert not repo.has("first.txt"), "--after re-ran a step before the resume point"
        assert lines(p.stdout)[-1] == ["done", "green"], p.stdout


@case
def test_a_skill_step_with_no_model_reports_a_dash():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "gate:\n  - name: review\n    skill: code-review\n")
        p = repo.run(plan="a plan")
        assert ["needs-skill", "review", "code-review", "-"] in lines(p.stdout), p.stdout


@case
def test_unknown_after_name_exits_2():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "gate:\n  - name: test\n    run: 'true'\n")
        p = repo.run("--after", "nope")
        assert p.returncode == 2, p.returncode
        assert "nope" in p.stderr, p.stderr


# --- the plan contract ---------------------------------------------------------

@case
def test_a_recorded_plan_is_materialized_and_marked_present():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "gate:\n  - name: review\n    skill: code-review\n")
        p = repo.run(plan="## Tasks\n\n1. do the thing")
        plan_line = [e for e in lines(p.stdout) if e[0] == "plan"]
        assert plan_line == [["plan", repo.plan_path(), "present"]], p.stdout
        assert os.path.isabs(repo.plan_path()), repo.plan_path()
        with open(repo.plan_path()) as f:
            assert "do the thing" in f.read()


@case
def test_no_recorded_plan_is_marked_absent_and_writes_no_file():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "gate:\n"
                         "  - name: review\n    skill: code-review\n")
        p = repo.run()  # no SAPA_TEST_PLAN => sapa issue exits 3
        plan_line = [e for e in lines(p.stdout) if e[0] == "plan"]
        assert plan_line == [["plan", repo.plan_path(), "absent"]], p.stdout
        assert not os.path.exists(repo.plan_path()), "absent must not leave a file behind"


@case
def test_an_absent_plan_does_not_fail_the_gate():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "gate:\n"
                         "  - name: check\n    run: echo ran > ran.txt\n"
                         "  - name: review\n    skill: code-review\n")
        p = repo.run()
        assert p.returncode == 4, p.returncode  # stopped at the skill, not failed
        assert repo.has("ran.txt"), "the run step was skipped over an absent plan"


@case
def test_a_run_only_gate_does_not_look_up_a_plan():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "gate:\n  - name: test\n    run: 'true'\n")
        p = repo.run(plan="a plan")
        assert [e for e in lines(p.stdout) if e[0] == "plan"] == [], p.stdout
        assert not os.path.exists(repo.plan_path()), "a run-only gate materialized a plan"


@case
def test_resuming_past_the_last_skill_step_skips_the_plan_lookup():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(tmp, "gate:\n"
                         "  - name: review\n    skill: code-review\n"
                         "  - name: test\n    run: 'true'\n")
        p = repo.run("--after", "review", plan="a plan")
        assert [e for e in lines(p.stdout) if e[0] == "plan"] == [], p.stdout


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
