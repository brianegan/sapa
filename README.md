# Sapa

Sapa (Filipino for "stream") runs a piece of work from a fresh worktree to a
merged PR. It bootstraps a repo into a worktree layout and spins up a worktree
per stream, then once the code is written it gates the work, captures the plan
on the GitHub issue, and ships it as a PR (draft by default).

It is a set of Claude Code skills plus small helper scripts. There is no daemon,
no binary, and no second remote: everything runs in the Claude session that did
the work, and it pushes to a single remote (`origin` by default; the name is
configurable but there is never a second one).

See [PRD.md](PRD.md) for the full design and rationale.

## What's here

Three `/sapa-*` skills, one per phase, so each shows up on its own in the `/`
menu and can't wander into another phase:

- `skill/sapa-plan` — read the issue, agree a plan, record it on the issue.
- `skill/sapa-submit` — rebase onto the base, gate in the working tree, push to
  the configured remote, open the PR (draft by default), then hand off to watch.
- `skill/sapa-watch` — monitor the PR (CI, comments, keeping it mergeable) and
  tear the stream down when it merges.

Helper scripts, backing the skills so there's no duplicated logic:

- `bin/sapa-bootstrap` — clone or `init` a repo into the `.bare` worktree layout
  the rest of sapa expects.
- `bin/sapa-worktree` — spin up a per-branch worktree off `origin/main` and open
  it in your editor (`$EDITOR`).
- `bin/sapa-start` — turn an issue number into a worktree ready to plan (derives
  the branch name from the issue title and calls `sapa-worktree`).
- `bin/sapa-config` — find the project's `.sapa.yaml` by walking up, the way
  `sapa-worktree` finds `.bare`.
- `bin/sapa-section` — maintain a machine-managed section of a PR body or issue
  without clobbering text a human has edited or locked.
- `bin/sapa-teardown` — remove a merged stream's worktree and local branch,
  refusing if there are uncommitted changes, then close its VS Code window.

Plus `.sapa.yaml` (Sapa's own gate config — it gates itself) and `tests/`.

## Install

Put the helpers on your `PATH` and the skills where Claude Code can find them:

```sh
for h in sapa-bootstrap sapa-worktree sapa-start sapa-config sapa-section sapa-teardown; do
  ln -sf "$PWD/bin/$h" ~/bin/$h
done
for s in sapa-plan sapa-submit sapa-watch; do
  ln -sfn "$PWD/skill/$s" ~/.claude/skills/$s
done
```

GitHub access uses `gh-axi`, invoked on demand as `npx -y gh-axi`.

## Flow

```sh
sapa-bootstrap git@github.com:me/proj.git   # once per repo: set up the worktree layout
sapa-start 42     # issue 42 -> worktree, opens your editor
# open Claude in the new window, then:
/sapa-plan        # read issue 42, agree a plan, write it to the issue
# ...implement...
/sapa-submit      # rebase onto base, gate, push, open a draft PR, start watching
# on merge, watch removes the worktree for you
```

## Config

Drop a `.sapa.yaml` at the root of any repo. A few optional top-level keys tune
the flow, each with a backward-compatible default:

- `base:` — the branch PRs target (default `main`). Submit rebases onto it before
  gating.
- `remote:` — the single remote to push to (default `origin`). Names your one
  remote; it never adds a second.
- `pr:` — `draft` or `ready`, the state new PRs open in (default `draft`). Solo
  repos often prefer `ready`; shared repos keep `draft`.
- `plan:` — a skill `/sapa-plan` invokes to run the planning discussion (for
  example wingspan `/plan` or `/grill-with-docs`). Omit it to use the built-in
  dialogue. Either way sapa still records the agreed plan to the issue.
- `gate_only_rebase:` — rebase onto the base even for `--gate-only` (default
  `false`). A full submit always rebases before gating regardless.
- `close_window:` — after teardown removes a merged stream's worktree, close the
  VS Code window that was open on it (default on; set `false` to keep it open).
  macOS + VS Code only and best-effort: it matches the window by the worktree's
  basename and never fails the teardown.

Each gate step under `gate:` is a shell command (`run:`, which may carry a
version-manager prefix) or a skill (`skill:`):

```yaml
base: main
remote: origin
pr: draft
plan: /grill-with-docs
gate_only_rebase: false
gate:
  - name: review
    skill: code-review
  - name: analyze
    run: fvm dart analyze
  - name: test
    run: fvm flutter test
```

## Test

```sh
python3 tests/test_sapa_section.py
bash tests/test_sapa_config.sh
```
