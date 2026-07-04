# Sapa

Sapa (Filipino for "stream") closes out a piece of work. It picks up after
`barry` and `worktree` have put you in a worktree and the code is written, then
gates the work, captures the plan on the GitHub issue, and ships it as a PR
(draft by default).

It is a Claude Code skill plus two small helper scripts. There is no daemon, no
binary, and no second remote: everything runs in the Claude session that did the
work, and it pushes to a single remote (`origin` by default; the name is
configurable but there is never a second one).

See [PRD.md](PRD.md) for the full design and rationale.

## What's here

Three `/sapa-*` skills, one per phase, so each shows up on its own in the `/`
menu and can't wander into another phase:

- `skill/sapa-plan` — read the issue, agree a plan, record it on the issue.
- `skill/sapa-ship` — gate in the working tree, push to the configured remote,
  open the PR (draft by default), then hand off to watch.
- `skill/sapa-watch` — monitor the PR (CI, comments, keeping it mergeable) and
  tear the stream down when it merges.

Helper scripts, backing the skills so there's no duplicated logic:

- `bin/sapa-start` — turn an issue number into a worktree ready to plan (derives
  the branch name from the issue title and calls `worktree`).
- `bin/sapa-config` — find the project's `.sapa.yaml` by walking up, the way
  `worktree` finds `.bare`.
- `bin/sapa-section` — maintain a machine-managed section of a PR body or issue
  without clobbering text a human has edited or locked.
- `bin/sapa-teardown` — remove a merged stream's worktree and local branch,
  refusing if there are uncommitted changes.

Plus `.sapa.yaml` (Sapa's own gate config — it gates itself) and `tests/`.

## Install

Put the helpers on your `PATH` and the skills where Claude Code can find them:

```sh
for h in sapa-start sapa-config sapa-section sapa-teardown; do
  ln -sf "$PWD/bin/$h" ~/bin/$h
done
for s in sapa-plan sapa-ship sapa-watch; do
  ln -sfn "$PWD/skill/$s" ~/.claude/skills/$s
done
```

GitHub access uses `gh-axi`, invoked on demand as `npx -y gh-axi`.

## Flow

```sh
sapa-start 42     # issue 42 -> worktree, opens your editor
# open Claude in the new window, then:
/sapa-plan        # read issue 42, agree a plan, write it to the issue
# ...implement...
/sapa-ship        # gate, push, open a draft PR, start watching
# on merge, watch removes the worktree for you
```

## Config

Drop a `.sapa.yaml` at the root of any repo. A few optional top-level keys tune
the flow, each with a backward-compatible default:

- `base:` — the branch PRs target (default `main`).
- `remote:` — the single remote to push to (default `origin`). Names your one
  remote; it never adds a second.
- `pr:` — `draft` or `ready`, the state new PRs open in (default `draft`). Solo
  repos often prefer `ready`; shared repos keep `draft`.
- `plan:` — a skill `/sapa-plan` invokes to run the planning discussion (for
  example wingspan `/plan` or `/grill-me-with-docs`). Omit it to use the built-in
  dialogue. Either way sapa still records the agreed plan to the issue.

Each gate step under `gate:` is a shell command (`run:`, which may carry a
version-manager prefix) or a skill (`skill:`):

```yaml
base: main
remote: origin
pr: draft
plan: /grill-me-with-docs
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
