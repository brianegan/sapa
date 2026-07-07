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

`/sapa-*` skills, one per phase, so each shows up on its own in the `/` menu
(type `sapa` to filter to just these) and can't wander into another phase, plus
`sapa-flow` to chain them for the common case:

- `skill/sapa-flow` — drive a stream end to end: plan, build, gate, submit,
  watch. The daily entry point; the rest are for running a single phase.
- `skill/sapa-plan` — agree a plan and record it on the issue, then stop.
- `skill/sapa-build` — read the recorded plan and implement the code and tests.
- `skill/sapa-gate` — rebase onto the base and run the quality gate, certifying
  the branch is green against what will merge.
- `skill/sapa-submit` — push and open the PR (draft by default), then reconcile
  the plan on the issue.
- `skill/sapa-watch` — monitor the PR (CI, comments, keeping it mergeable) and
  tear the stream down when it merges.

The `sapa` command, backing the skills so there's no duplicated logic. One name
on your `PATH` with a subcommand per helper (`sapa help` lists them):

- `sapa bootstrap` — clone or `init` a repo into the `.bare` worktree layout
  the rest of sapa expects.
- `sapa worktree` — spin up a per-branch worktree off `origin/main` and open
  it in your editor (`$EDITOR`).
- `sapa start` — turn an issue number into a worktree ready to plan (derives
  the branch name from the issue title and calls `sapa worktree`).
- `sapa config` — find the project's `.sapa.yaml` by walking up, the way
  `sapa worktree` finds `.bare`.
- `sapa section` — maintain a machine-managed section of a PR body or issue
  without clobbering text a human has edited or locked.
- `sapa watch` — poll the current branch's PR and emit one structured line per
  real change (`ci-failed`, `new-review`, `new-comment`, `base-behind`,
  `merged`, `closed`), guarding empty or failed fetches and deduping against the
  last poll. The `sapa-watch` skill runs it and reasons about each event.
- `sapa teardown` — remove a merged stream's worktree and local branch,
  refusing if there are uncommitted changes, then close its VS Code window.

Plus `.sapa.yaml` (Sapa's own gate config — it gates itself) and `tests/`.

## Install

Clone the repo, then run the installer from it:

```sh
bin/sapa install            # link sapa onto PATH, skills into your agents
bin/sapa install uninstall  # remove those symlinks
```

It symlinks the `sapa` command into `~/.local/bin` and the `skill/` directories
into every coding agent it finds — Claude Code (`~/.claude/skills`) and Codex
(`~/.codex/skills`), which read the same `SKILL.md` format. The other helpers
stay in the clone and `sapa` resolves back to them, so only one name lands on
your `PATH`. The links point into the clone you run it from, so editing the
source updates the installed copy; develop sapa from your `main` checkout so the
links track merged code. Re-running is safe (and it clears any links left by the
older one-command-per-helper layout).

Two optional overrides: `SAPA_BIN_DIR` picks the `PATH` directory (default
`~/.local/bin`; the installer prints a hint if it isn't on your `PATH`), and
`SAPA_AGENTS` (e.g. `SAPA_AGENTS="claude codex"`) forces the agents to target
instead of auto-detecting.

GitHub access uses `gh`. `npx skills add <repo>` is an alternative for the skills
half only — it can't put the `sapa` command on your `PATH`.

### Shell completion (optional)

For zsh Tab-completion of subcommands, run this once — it appends the enable line
to your `~/.zshrc`:

```sh
echo 'eval "$(sapa completion zsh)"' >> ~/.zshrc
```

sapa never edits your shell config for you — the installer just prints this same
line for you to copy, paste, and run, the way it hints about `PATH`.

Completion covers each subcommand's arguments too — for example `sapa teardown`
completes worktree directories and `sapa config --start` completes directories.
The enable line normally belongs after `compinit` in your `~/.zshrc` (oh-my-zsh
runs `compinit` for you); if it lands before, the script initialises completion
itself so Tab still works.

## Flow

```sh
sapa bootstrap git@github.com:me/proj.git   # once per repo: set up the worktree layout
sapa start 42     # issue 42 -> worktree, opens your editor
# open Claude in the new window, then:
/sapa-flow        # issue 42 -> plan, build, gate, PR, watch, all in one
# or run a single phase: /sapa-plan, /sapa-build, /sapa-gate, /sapa-submit, /sapa-watch
# on merge, watch removes the worktree for you
```

## Config

Drop a `.sapa.yaml` at the root of any repo. A few optional top-level keys tune
the flow, each with a backward-compatible default:

- `base:` — the branch PRs target (default `main`). `sapa-gate` rebases onto it
  before running the checks.
- `remote:` — the single remote to push to (default `origin`). Names your one
  remote; it never adds a second.
- `pr:` — `draft` or `ready`, the state new PRs open in (default `draft`). Solo
  repos often prefer `ready`; shared repos keep `draft`.
- `plan:` — a skill `/sapa-plan` invokes to run the planning discussion (for
  example wingspan `/plan` or `/grill-with-docs`). Omit it to use the built-in
  dialogue. Either way sapa still records the agreed plan to the issue.
- `close_window:` — after teardown removes a merged stream's worktree, close the
  VS Code window that was open on it (default on; set `false` to keep it open).
  macOS + VS Code only and best-effort: it presses the close button of the one
  window matching the worktree's basename (closing nothing if zero or several
  match) and never fails the teardown.

Each gate step under `gate:` is a shell command (`run:`, which may carry a
version-manager prefix) or a skill (`skill:`):

```yaml
base: main
remote: origin
pr: draft
plan: /grill-with-docs
gate:
  - name: review
    skill: code-review
  - name: analyze
    run: fvm dart analyze
  - name: test
    run: fvm flutter test
```

The gate is the only thing that checks the work — nothing downstream re-verifies
it — so make the `gate:` steps count: include a real test, analyze, and review
step, not a token check.

### Changed-package scoping in a monorepo

`sapa-gate` rebases onto the base before it runs, so it already holds the diff
against what will merge. It hands that to every `run:` step as two environment
variables:

- `SAPA_BASE` — the branch the PR targets (the config `base`).
- `SAPA_CHANGED_FILES` — the files this branch changed versus the merge-base,
  newline-separated.

That is the whole contract. Sapa does not discover packages or own your version
manager — those vary too much per repo, and the `run:` prefix (`fvm dart …`)
already covers the toolchain. Your script maps the changed files to packages and
decides what to gate. In a workspace with many packages, gate only the ones the
branch touched, and fall back to gating everything when the change is
cross-cutting (root `pubspec.yaml`, CI config, shared tooling):

```sh
#!/usr/bin/env bash
# .sapa-verify.sh <format|analyze|test> — gate only changed packages.
set -euo pipefail
cmd="${1:?usage: .sapa-verify.sh <format|analyze|test>}"

# All workspace package dirs (one awk line; adjust to your layout). Strip only
# the leading list marker, and use a portable space class so BSD awk matches.
all_pkgs() { awk '/^[[:space:]]*-/{sub(/^[[:space:]]*-[[:space:]]*/,"");print}' pubspec.yaml; }

# A cross-cutting change means gate everything.
cross_cutting() {
  grep -qE '^(pubspec\.(yaml|lock)|\.github/)' <<<"$SAPA_CHANGED_FILES"
}

if [ -z "${SAPA_CHANGED_FILES:-}" ] || cross_cutting; then
  pkgs=$(all_pkgs)
else
  # Keep each package that owns at least one changed file.
  pkgs=$(all_pkgs | while IFS= read -r p; do
           if grep -qE "^${p}/" <<<"$SAPA_CHANGED_FILES"; then echo "$p"; fi
         done)
fi

while IFS= read -r p; do
  [ -n "$p" ] || continue
  echo ">> $cmd $p"
  (cd "$p" && fvm dart "$cmd" .)
done <<<"$pkgs"
```

```yaml
gate:
  - name: format
    run: ./.sapa-verify.sh format
  - name: analyze
    run: ./.sapa-verify.sh analyze
  - name: test
    run: ./.sapa-verify.sh test
```

## Test

```sh
bash tests/run.sh
```

CI runs the same suite on every push and PR (`.github/workflows/ci.yml`).
