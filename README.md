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
- `sapa start` — turn an issue into a worktree ready to plan (derives the branch
  name from the issue title and calls `sapa worktree`). Takes a GitHub number
  (`42`) or a Jira key (`gp-1`); the key is kept in the branch name.
- `sapa issue` — derive the issue identity from the branch (`sapa issue key`) and
  record or read the plan comment (`sapa issue plan-comment`), against GitHub
  (`gh`) or Jira (`acli`) per the `tracker` config. The gh-vs-acli branch lives
  here so the phase skills stay backend-agnostic.
- `sapa config` — find the project's `.sapa.yaml` by walking up, the way
  `sapa worktree` finds `.bare`.
- `sapa tmp` — print (creating on first use) a scratch directory scoped to the
  current stream, keyed by its branch the way `sapa status` keys its registry.
  The phase skills write their intermediate files there so two streams in the
  same phase never clobber each other's scratch.
- `sapa section` — maintain a machine-managed section of a PR body or issue
  without clobbering text a human has edited or locked.
- `sapa status` — record the current stream's run-state and lifecycle stage to a
  per-stream JSON file a window switcher can read (see [Window status](#window-status)).
- `sapa gate` — walk the configured `gate.steps:` in order, run each `run:` step
  with `SAPA_BASE` and `SAPA_CHANGED_FILES` set, materialize the plan comment for
  the `skill:` steps, and emit one structured line per result. It stops when it
  reaches a `skill:` step (exit 4), because invoking a skill needs the agent; the
  `sapa-gate` skill invokes it and resumes with `sapa gate --after <name>`,
  reporting that step's outcome with `--result`/`--summary`. The walk writes a
  record of itself, and `sapa gate --report` renders that record as the PR's
  `## Gates` section (see [The gate record](#the-gate-record)).
- `sapa watch` — poll the current branch's PR and emit one structured line per
  real change (`ci-failed`, `new-review`, `new-comment`, `base-behind`,
  `merged`, `closed`), guarding empty or failed fetches and deduping against the
  last poll. The `sapa-watch` skill runs it and reasons about each event.
- `sapa teardown` — remove a merged stream's worktree and local branch,
  refusing if there are uncommitted changes, then close its VS Code window.

Plus `.sapa.yaml` (Sapa's own gate config — it gates itself) and `tests/`.

## Install

Needs `git`, `gh` (authenticated), `python3`, and PyYAML. Everything but PyYAML
you already have if you use GitHub from a terminal on macOS; PyYAML ships with
Apple's `/usr/bin/python3` and is `python3 -m pip install pyyaml` otherwise. Only
`sapa gate` needs it, to read the `gate:` map. Jira projects also need
`acli`.

Clone the repo, then run the installer from it:

```sh
bin/sapa install    # link sapa onto PATH, skills into your agents
sapa uninstall      # remove those symlinks
```

It symlinks the `sapa` command into `~/.local/bin` and the `skill/` directories
into every coding agent it finds — Claude Code (`~/.claude/skills`) and Codex
(`~/.codex/skills`), which read the same `SKILL.md` format. The other helpers
stay in the clone and `sapa` resolves back to them, so only one name lands on
your `PATH`. The links point into the clone you run it from, so editing the
source updates the installed copy; develop sapa from your `main` checkout so the
links track merged code. Re-running is safe (and it clears any links left by the
older one-command-per-helper layout).

When Claude Code is a target, install also wires three run-state hooks into
`~/.claude/settings.json` for the [window status](#window-status) feature. This
is the one config file sapa edits (the `PATH` and completion hints stay hints); it
touches only its own entries, leaving any hooks you already have, and `sapa
uninstall` removes exactly them.

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
- `writing_style:` — a skill sapa runs as a final pass over the free prose it
  writes: the plan comment, the PR body, and its replies to review comments (for
  example `/humanizer`). Omit it (the default) to write plainly. It shapes prose
  only, never the structured parts — the plan's task list and `Done when:` lines,
  the PR title, and the gate record stay as written.
- `tracker:` — the issue backend, `github` (default) or `jira`. On `github`, sapa
  reads issues and records the plan through `gh`, and PRs link the issue with
  `Closes #N`. On `jira`, it reads issues and records the plan through the
  Atlassian CLI (`acli`); PRs still live on GitHub and link the issue by URL. The
  Jira key is kept in the branch (`gp-1-…`), so Jira's dev panel back-links the PR.
- `jira:` — Jira settings, used only when `tracker: jira`. `site:` is the Jira
  host, used to build the PR's issue link; `project:` is optional and lets a bare
  `sapa start 1` expand to that project's key (`GP-1`).

  ```yaml
  tracker: jira
  jira:
    site: verygood-ventures.atlassian.net
    project: GP
  ```
- `close_window:` — after teardown removes a merged stream's worktree, close the
  VS Code window that was open on it (default on; set `false` to keep it open).
  macOS + VS Code only and best-effort: it presses the close button of the one
  window matching the worktree's basename (closing nothing if zero or several
  match) and never fails the teardown.
- `watch:` — settings for `sapa-watch`. `base_behind:` is `protection` (default)
  or `any`. `protection` treats the branch as behind only when GitHub reports
  `mergeStateStatus: BEHIND`, which needs a "require branches up to date"
  protection rule. `any` also reacts when the base has genuinely moved ahead
  without that rule, keeping the branch rebased at the cost of a re-gate on every
  merge to the base. `max_ci_fix_attempts:` (default 3) bounds the CI autofix
  loop: after that many failed fixes for one failure streak, `sapa-watch` stops
  and escalates instead of pushing another guess. The count resets whenever CI
  goes green again.

  ```yaml
  watch:
    base_behind: any
    max_ci_fix_attempts: 3
  ```

`gate:` is a map. Its `steps:` list is the gate itself, and `max_fix_attempts:`
(default 3) bounds `/sapa-gate`'s autofix loop: after that many fixes applied and
re-run for one failing gate, it stops and hands the stream back instead of guessing
again, because repeated failed fixes usually mean the failure is deeper than the
patch. `0` never autofixes. A run that reaches green ends the count. Unlike watch's
`max_ci_fix_attempts`, only sapa's own guesses spend from it: a fix you dictated
after it stopped to ask reruns on a fresh budget.

Each step under `gate.steps:` is a shell command (`run:`, which may carry a
version-manager prefix) or a skill (`skill:`). A step may also carry `model:`,
which pins that step to a model (`fable`, `opus`, `sonnet`, `haiku`) — meaningful
for `skill:` steps, which then run in a sub-agent pinned to it; absent, the step
inherits the session model. The recommended posture: run sessions on Opus and
pin the review step to Fable, so the strongest model's judgment lands on the one
step that is bounded, token-light, and needs no mid-task conversation.

```yaml
base: main
remote: origin
pr: draft
plan: /grill-with-docs
writing_style: /humanizer
gate:
  max_fix_attempts: 3
  steps:
    - name: review
      skill: code-review
      model: fable
    - name: analyze
      run: fvm dart analyze
    - name: test
      run: fvm flutter test
```

The gate is the only thing that checks the work — nothing downstream re-verifies
it — so make the `gate.steps:` count: include a real test, analyze, and review
step, not a token check.

### The gate record

That last paragraph used to be the whole enforcement mechanism: advice in a README,
against a "the branch is green" that was a sentence in a chat log and gone with the
session. So the gate writes down what it did, and the PR publishes it.

As `sapa gate` walks, it appends to `$(sapa tmp)/gate-record.json` — per step the
name, kind, command or skill, model pin, result, duration, and a tail of its output,
and per run the head and base SHAs it gated plus whether any step was given the
recorded plan as its spec source. `sapa-submit` then puts a summary on the PR:

```
## Gates

Gated `def5678` against `origin/main@abc1234`.

- **review**: skill `code-review` on `fable`, passed, agent-reported
- **test**: command, passed in 42.3s

Reviewed against the plan recorded on the issue.
```

A gate of one `format` step renders as one bullet and reads as thin, and a PR where
nothing was given the plan says so. That is deliberate, and it is the whole design:
disclosure, not enforcement. Sapa will not refuse to certify a weak gate — that
would make adopting it on someone else's repo a fight, and it is not sapa's call —
so it puts the truth where the reviewer is and lets them judge. A good gate pays
nothing for this.

Two things the section is careful about. A `run:` step's result is an exit code sapa
watched, while a `skill:` step's is what the agent reported when it resumed the
walk, and skill bullets say `agent-reported` rather than letting the two read as the
same kind of evidence. And the spec-source line states what sapa observed rather
than reaching a verdict, because sapa cannot know whether a given step is a spec
review. Names only, no commands: the config is checked in and shows up in the diff.

The record lives in the stream's scratch directory and does not survive a reboot.
Submitting without a fresh gate is legitimate, so `sapa gate --report` says no
record was found rather than rebuilding a plausible list from the config. It also
compares the recorded head against the current one and flags a gate that ran on a
different commit. Run it yourself any time: `sapa gate --report`.

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
  steps:
    - name: format
      run: ./.sapa-verify.sh format
    - name: analyze
      run: ./.sapa-verify.sh analyze
    - name: test
      run: ./.sapa-verify.sh test
```

## Window status

Sapa runs one editor window per stream, so with three to five streams going the
question is always "which window can I switch to right now?" `sapa status` answers
it for a window switcher: it writes a tiny JSON file per stream that a switcher
reads to badge each window as running, at rest, or waiting.

Two orthogonal fields, each written by whoever knows it:

- `state` — the run-state, `busy` | `idle` | `needs-you`, written by the Claude
  Code hooks `sapa install` wires (`UserPromptSubmit → busy`, `Notification →
  needs-you`, `Stop → idle`). This is the "running vs at rest" signal.
- `stage` — the lifecycle phase, `plan` | `build` | `gate` | `submit` | `watch`,
  written by each phase skill as it runs.

They are written independently and merged, so the frequent run-state hook and the
once-per-phase stage write never clobber each other. `sapa status` self-guards: it
resolves the stream by walking up for the `.bare` project root, so the global hooks
do nothing in any non-sapa session. On merge, `sapa teardown` clears the file.

The registry is one file per stream — so each window only writes its own, and
teardown removes just that one — under `${SAPA_STATUS_DIR:-~/.sapa/status}/`, keyed
by the worktree basename (which equals the branch, and is the token an editor puts
in its window title — the join a switcher matches windows on):

```json
{ "branch": "51-combine-jump-sapa", "stage": "gate", "state": "busy",
  "updated": "2026-07-07T22:48:00Z" }
```

The consumer side — reading this registry and rendering a per-window badge — lives
in the switcher. [Jump](https://github.com/brianegan/jump) is the reference
consumer; any tool that can match a window to a stream by title and read the JSON
can use it.

## Prior art

Sapa is not the first tool to gate AI-written code or to run agents in parallel
worktrees. It is a deliberate set of opposite choices from the tools that do.

- [no-mistakes](https://github.com/kunchenguid/no-mistakes) is the closest in
  spirit and the exact inverse in architecture — the tool sapa was built in
  reaction to (see the [Problem Statement](PRD.md)). It runs the same rough
  pipeline (gate, ship, watch CI) but puts a git proxy in front of `origin`,
  gates in a disposable worktree, runs the gate as a background daemon, and
  overwrites the PR body on every push. Sapa keeps one remote, gates in the live
  tree in the foreground where you can cancel and rerun, and locks the PR body
  the moment you touch it.
- [Orca](https://github.com/stablyai/orca) and [Composio Agent
  Orchestrator](https://github.com/ComposioHQ/agent-orchestrator) are
  parallel-agent cockpits — a desktop IDE and a daemon-plus-dashboard supervisor
  — that run many agents in isolated worktrees and surface their PRs. They
  overlap sapa's worktree-per-stream half and stop before the autonomous
  gate-ship-watch: CI fixes are a manual button or a nudge to the agent, review
  comments are shown but not addressed, and nothing is written back to the issue.
  Sapa has no daemon and no dashboard; concurrency is one editor window per
  stream, and closing the window ends that stream's watch.

Three things sapa does that none of them do:

1. **It owns the prose without clobbering yours.** The PR body has a
   machine-managed section that locks the instant you edit it, and the agreed
   plan lives as a managed comment on the GitHub issue that reconciles when what
   shipped diverges from what was planned. The others either overwrite your
   description or never write one, and none record the plan on the issue.
2. **It triages comments on two axes.** By author — your own comments come back
   to you in the agent chat, a colleague's are answered on GitHub with a "Sapa
   Workflow, on your behalf" line — and by substance, so mechanical comments are
   fixed and pushed while subjective ones are escalated to you. The others
   classify bot-versus-human at most.
3. **It runs inside the session that wrote the code.** No proxy, no daemon, no
   supervisor, one remote, gate in your live tree. The OS owns process lifecycle,
   so there is no hidden state to reconcile and no single supervisor to become a
   bottleneck across streams.

One honest caveat: no-mistakes already fixes CI failures and rebases a moved base
on its own, so post-PR autopilot itself is not new. What is new is doing it from
inside your session with no second remote, plus the comment triage and the
issue-plan and PR-body ownership it lacks.

## Test

```sh
bash tests/run.sh
```

CI runs the same suite on every push and PR (`.github/workflows/ci.yml`).
