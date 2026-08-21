# Sapa

Sapa (Filipino for "brook" or "stream") runs a piece of work from a fresh worktree to a
merged PR. It bootstraps a repo into a worktree layout, spins up a worktree per
stream, then gates the work, captures the plan on the issue, and ships it as a PR
(draft by default).

It is a set of Claude Code skills plus small helper scripts: no daemon, no
binary, no second remote; everything runs in the session that did the work and
pushes to a single remote (`origin` by default). See [PRD.md](PRD.md) for the
full design and rationale.

## Quick start

Needs `git`, `gh` (authenticated), and `python3` with PyYAML. Install sapa from
a clone, then set up your machine once:

```sh
bin/sapa install      # link sapa onto PATH, skills into your agents
sapa settings init    # write a commented ~/.sapa/settings.yaml
```

The settings file is yours alone: `opener:` opens each new worktree in your
editor, `closer:` closes its window when the stream merges. Both are opt-in; with
no settings file sapa manages worktrees and leaves your desktop alone.
Prerequisites and installer options are under [Install](#install).

### Project setup

Once per project:

1. `sapa bootstrap git@github.com:me/proj.git` clones the repo into the `.bare`
   worktree layout the rest of sapa expects.
2. `sapa config init` writes a starter `.sapa.yaml`, the project's checked-in
   process config: base branch, tracker, gate steps, draft vs ready PRs. See
   [Config](#config).
3. `sapa start 42` creates a worktree for issue 42 on a branch named for it, and
   opens it in your editor if `opener:` is set.
4. Open Claude Code or Codex in the worktree, if your editor has not already.

### The flow

Run `/sapa-flow` in the agent. It reads the issue and drives the stream through
every phase:

- `/sapa-plan` agrees an approach with you and records it on the issue as a
  comment, with a `Done when:` criterion per task.
- `/sapa-build` implements the recorded plan, one task at a time.
- `/sapa-gate` rebases onto the base and runs the `gate.steps:` from
  `.sapa.yaml`: shell commands (test, lint, format) or skills such as
  `/code-review`, optionally pinned to a model. `max_fix_attempts:` bounds
  how many fixes it tries before handing the stream back.
- `/sapa-submit` pushes and opens the PR, draft or ready per the `pr:` key.
- `/sapa-watch` follows the PR: it fixes CI failures, answers or escalates
  review comments, and keeps the branch rebased when the base moves.

On merge, watch tears the stream down: it removes the worktree and branch, and
runs your `closer:` to close the editor window.

## What's here

### CLI

The `sapa` command backs the skills so no logic is duplicated. One name on your
`PATH`, a subcommand per helper (`sapa help` lists them):

- `sapa bootstrap`: clone or `init` a repo into the `.bare` worktree layout.
- `sapa worktree`: spin up a per-branch worktree off `origin/main` and open it
  in your editor, if you have set one in your personal settings.
- `sapa start`: turn an issue into a worktree ready to plan (derives the branch
  name from the issue title and calls `sapa worktree`). Takes a GitHub number
  (`42`) or a Jira key (`gp-1`); the key is kept in the branch name.
- `sapa issue`: derive the issue identity from the branch (`sapa issue key`) and
  record or read the plan comment (`sapa issue plan-comment`), against GitHub
  (`gh`) or Jira (`acli`) per the `tracker` config. The gh-vs-acli split lives
  here so the phase skills stay backend-agnostic.
- `sapa config`: find the project's `.sapa.yaml` by walking up, the way
  `sapa worktree` finds `.bare`.
- `sapa settings`: print (or `init`) your personal `~/.sapa/settings.yaml`, the
  per-machine half of the configuration.
- `sapa close`: close a finished stream's editor window. `sapa close code`
  handles VS Code on macOS; point `closer:` at it, or at your own.
- `sapa tmp`: print (creating on first use) a scratch directory scoped to the
  current stream. Phase skills write intermediate files there so parallel
  streams never clobber each other.
- `sapa section`: maintain a machine-managed section of a PR body or issue
  without clobbering text a human has edited or locked.
- `sapa status`: record the stream's run-state and lifecycle stage to a
  per-stream JSON file, and read the stage back with `--report`. A window
  switcher badges each window from it (see [Window status](#window-status));
  `sapa-flow` reads it to resume a stream at the phase it left off in.
- `sapa gate`: walk the configured `gate.steps:` in order (`run:` steps get
  `SAPA_BASE` and `SAPA_CHANGED_FILES`; `skill:` steps get the plan comment).
  It stops at a `skill:` step (exit 4), since invoking a skill needs the agent;
  `sapa-gate` resumes with `sapa gate --after <name>` and reports the outcome
  with `--result`/`--summary`. `sapa gate --report` renders the walk's record as
  the PR's `## Gates` section (see [The gate record](#the-gate-record)).
- `sapa skills`: provision and verify the skills a `.sapa.yaml` references (see
  [Provisioning skills](#provisioning-skills)). `enumerate` lists them, `lock`
  pins each object-form skill to a commit SHA, `sync` vendors it into
  `.claude/skills/<name>/`, `check` verifies (offline) the config and the
  vendored folders agree, and `update` re-pins to the latest SHA and re-syncs.
- `sapa watch`: poll the current branch's PR and emit one structured line per
  real change (`ci-failed`, `new-review`, `new-comment`, `base-behind`,
  `merged`, `closed`). The `sapa-watch` skill runs it and reasons about each
  event.
- `sapa teardown`: remove a merged stream's worktree and local branch, refusing
  if there are uncommitted changes, then close its editor window.

### Skills

`/sapa-*` skills, one per phase, so each shows up on its own in the `/` menu
(type `sapa` to filter to just these) and can't wander into another phase, plus
`sapa-flow` to chain them for the common case:

- `skill/sapa-flow`: drive a stream end to end (plan, build, gate, submit,
  watch). The daily entry point; the rest run a single phase.
- `skill/sapa-plan`: agree a plan and record it on the issue, then stop.
- `skill/sapa-build`: read the recorded plan and implement the code and tests.
- `skill/sapa-gate`: rebase onto the base and run the quality gate, certifying
  the branch is green against what will merge.
- `skill/sapa-submit`: push and open the PR (draft by default), then reconcile
  the plan on the issue.
- `skill/sapa-watch`: monitor the PR (CI, comments, keeping it mergeable) and
  tear the stream down when it merges.

Plus `.sapa.yaml` (Sapa's own gate config; it gates itself) and `tests/`.

## Install

Needs `git`, `gh` (authenticated), `python3`, and PyYAML. PyYAML ships with
Apple's `/usr/bin/python3` and is `python3 -m pip install pyyaml` otherwise; only
`sapa gate` needs it, to read the `gate:` map. Jira projects also need `acli`.

Clone the repo, then run the installer from it:

```sh
bin/sapa install    # link sapa onto PATH, skills into your agents
sapa update         # git pull the installed clone, then reinstall
sapa uninstall      # remove those symlinks
```

It symlinks the `sapa` command into `~/.local/bin` and the `skill/` directories
into every coding agent it finds: Claude Code (`~/.claude/skills`) and Codex
(`~/.codex/skills`), which read the same `SKILL.md` format. The links point into
the clone, so editing the source updates the installed copy; develop sapa from
your `main` checkout. Re-running is safe.

When Claude Code is a target, install also wires three run-state hooks into
`~/.claude/settings.json` for the [window status](#window-status) feature: the
one config file sapa edits, touching only its own entries, and `sapa uninstall`
removes exactly them.

Two optional overrides: `SAPA_BIN_DIR` picks the `PATH` directory (default
`~/.local/bin`; the installer prints a hint if it isn't on your `PATH`), and
`SAPA_AGENTS` (e.g. `SAPA_AGENTS="claude codex"`) forces the agents to target
instead of auto-detecting.

To pull the latest sapa without walking over to the clone, run `sapa update`
from anywhere. It resolves the clone backing the `sapa` on your `PATH`, runs
`git pull --ff-only` there, and on success re-runs `sapa install` so new or
renamed skills get linked and the hooks get re-wired. The pull is fast-forward
only: a clone that has diverged stops with git's own error and is left
untouched, and the reinstall is skipped.

GitHub access uses `gh`. `npx skills add <repo>` is an alternative for the skills
half only; it can't put the `sapa` command on your `PATH`.

### Shell completion (optional)

For zsh Tab-completion of subcommands and their arguments, run this once (it
appends the enable line to your `~/.zshrc`):

```sh
echo 'eval "$(sapa completion zsh)"' >> ~/.zshrc
```

sapa never edits your shell config for you; the installer prints this same line
as a hint. It normally belongs after `compinit` (oh-my-zsh runs it for you);
placed earlier, the script initializes completion itself so Tab still works.

## Config

Sapa reads two files. `.sapa.yaml` is checked in and owns the process a team
shares: the base branch, the tracker, the quality gate. `~/.sapa/settings.yaml`
is yours alone and owns your workflow: which editor to open, whether to close the
window afterwards. Neither file can reach into the other's keys: your machine
cannot quietly weaken the gate everyone else runs, and a config someone commits
cannot start driving your editor.

Drop a `.sapa.yaml` at the root of any repo. Sapa walks up to find it, so in the
`.bare` layout it can sit beside `.bare` and cover every worktree at once. The
walk only locates the config: `sapa gate` runs its steps in the worktree you
invoked it from.

A few optional top-level keys tune the flow, each with a backward-compatible
default:

- `base:`: the branch PRs target (default `main`). `sapa-gate` rebases onto it
  before running the checks.
- `remote:`: the single remote to push to (default `origin`).
- `pr:`: `draft` or `ready`, the state new PRs open in (default `draft`). Solo
  repos often prefer `ready`; shared repos keep `draft`.
- `plan:`: a skill `/sapa-plan` invokes to run the planning discussion (for
  example wingspan `/plan` or `/grilling`). Omit it to use the built-in
  dialogue. Either way sapa still records the agreed plan to the issue.
- `build:`: a skill `/sapa-build` invokes once, before the first task, to shape
  the implementation (for example `/tdd` to build test-first). It can tighten
  sapa's rules, never loosen them, and never re-scopes, merges, or reorders the
  recorded tasks.
- `writing_style:`: a skill sapa runs as a final pass over the free prose it
  writes (plan comment, PR body, review replies; for example `/humanizer`). It
  shapes prose only: the task list, `Done when:` lines, PR title, and gate
  record stay as written.

  Each of `plan:`, `build:`, and `writing_style:` (and a gate step's `skill:`)
  may be a bare skill name, as above, or an object that `sapa skills` provisions
  at a pinned commit. See [Provisioning skills](#provisioning-skills).
- `tracker:`: the issue backend, `github` (default) or `jira`. On `github`, sapa
  reads issues and records the plan through `gh`, and PRs link the issue with
  `Closes #N`. On `jira` it uses the Atlassian CLI (`acli`); PRs still live on
  GitHub and link the issue by URL. The Jira key is kept in the branch
  (`gp-1-…`), so Jira's dev panel back-links the PR.
- `jira:`: Jira settings, used only when `tracker: jira`. `site:` is the Jira
  host, used to build the PR's issue link; `project:` is optional and lets a
  bare `sapa start 1` expand to that project's key (`GP-1`).

  ```yaml
  tracker: jira
  jira:
    site: verygood-ventures.atlassian.net
    project: GP
  ```
- `watch:`: settings for `sapa-watch`. `base_behind:` is `protection` (default)
  or `any`: `protection` reacts only when GitHub reports `mergeStateStatus:
  BEHIND`, which needs a "require branches up to date" rule, while `any` also
  reacts when the base has moved ahead without that rule, at the cost of a
  re-gate on every merge to the base. `max_ci_fix_attempts:` (default 3) bounds
  the CI autofix loop before `sapa-watch` stops and escalates; the count resets
  whenever CI goes green.

  ```yaml
  watch:
    base_behind: any
    max_ci_fix_attempts: 3
  ```

`gate:` is a map. Its `steps:` list is the gate itself, and `max_fix_attempts:`
(default 3) bounds `/sapa-gate`'s autofix loop: after that many fixes applied and
re-run for one failing gate, it stops and hands the stream back instead of
guessing again (repeated failures usually run deeper than the patch). `0` never
autofixes, and a green run ends the count. Unlike watch's `max_ci_fix_attempts`,
only sapa's own guesses spend from it: a fix you dictated after it stopped to ask
reruns on a fresh budget.

Each step under `gate.steps:` is a shell command (`run:`, which may carry a
version-manager prefix) or a skill (`skill:`). A step may also carry `model:` to
pin it to a model (`fable`, `opus`, `sonnet`, `haiku`). It is meaningful for
`skill:` steps only: they run in a sub-agent on that model, while unpinned steps
inherit the session model. The recommended posture: run sessions on Opus and pin
the review step to Fable, so the strongest model's judgment lands on the one step
that is bounded, token-light, and needs no mid-task conversation.

The pin is a preference, not a requirement. When the harness cannot reach the
pinned model — the running account has no access to it, or the harness has no such
model, as Codex has no Fable — the step falls back to the session model and the
gate still runs, so a stream stays gateable by anyone who clones it. The fallback
is recorded, not hidden: the gate report says the step ran on the session model
rather than asserting the pin ran.

```yaml
base: main
remote: origin
pr: draft
plan: grilling
build: tdd
writing_style: humanizer
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

The gate is the only thing that checks the work, and nothing downstream
re-verifies it, so make the `gate.steps:` count: include a real test, analyze,
and review step, not a token check.

### Provisioning skills

The flow and gate run skills the config names, so those skills have to be on the
machine. `sapa skills` provisions them, pinned, so a fresh checkout runs with
nothing installed by hand. A skill value is one of two shapes:

- a **bare name** (`plan: grilling`) means "resolve it however you already do",
  a global install. sapa leaves it alone.
- an **object** means "provision this one". sapa vendors it from its source at a
  pinned commit into `.claude/skills/<name>/`, the only place Claude Code
  resolves a project skill:

  ```yaml
  plan:
    source: mattpocock/skills           # owner/repo, a full git URL, or a local path
    path: skills/productivity/grilling  # the skill folder within that repo ('.' = root)
    sha: 0ab1b63a410a...                # the pinned commit, written by `lock`
  writing_style:
    source: blader/humanizer
    path: .
    name: humanizer                     # optional; defaults to the last path component
  ```

The name a gate `skill:` invokes, and the folder a skill vendors into, is the
object's `name:` or the last component of its `path:`. The five verbs:

- `sapa skills enumerate` prints every skill the config references.
- `sapa skills lock` resolves each object's source HEAD to a `sha:` and writes it
  back into `.sapa.yaml`, touching only that line.
- `sapa skills sync` vendors each pinned skill into `.claude/skills/<name>/`,
  carrying an upstream LICENSE for attribution (it refuses to vendor without one).
- `sapa skills check` verifies, offline, that the object-form skills and the
  vendored folders agree and each folder has a `SKILL.md`. Wire it into a setup
  task and the gate so config and provisioned skills cannot drift.
- `sapa skills update` re-pins every object to its latest source HEAD and
  re-syncs, leaving a reviewable diff.

Whether the vendored folders are committed (shared with the team) or gitignored
is the project's `.gitignore` choice.

### Personal settings

Your half lives at `~/.sapa/settings.yaml`, one file per machine. `sapa settings
init` writes a commented starter; `sapa settings` prints the path and
`sapa settings -p` its contents.

Both keys are opt-in, and the key being there is the opt-in. With no settings
file sapa opens no windows and closes none, so a teammate who clones your project
gets a tool that manages worktrees and leaves their desktop alone.

- `opener:`: a command `sapa worktree` (and so `sapa start`) runs on a new
  worktree, with the path as its last argument. It splits on spaces, so
  `opener: code -n` passes the flag through. Omit it and the path is printed
  instead.
- `closer:`: a command `sapa teardown` runs once it has removed a merged
  stream's worktree, with the worktree's basename as its argument, to close the
  window that was open on it. Omit it and your windows are left alone.

```yaml
opener: code -n
closer: sapa close code
```

`sapa close code` is the one closer that ships with sapa: VS Code on macOS,
best-effort. It presses the close button of the single window whose title
contains the worktree's basename, and closes nothing at all if zero or several
match, so it can never take the wrong window. Any command that takes a basename
and closes a window plugs in the same way: a different editor, a tmux session, a
Linux window manager.

A closer reports one word on stdout: `closed`, `no-editor`, `no-match`, or
`error:<n>`. The close is always best-effort: whatever it reports, the worktree
is already gone and the teardown has succeeded. Pressing another app's button
goes through System Events, which macOS gates behind Accessibility permission;
teardown prints a one-line hint naming it (grant it to your terminal app in
System Settings > Privacy & Security > Accessibility) rather than failing
silently.

### The gate record

The gate writes down what it did, and the PR publishes it. As `sapa gate` walks,
it appends to `$(sapa tmp)/gate-record.json`: per step the name, kind, command or
skill, model pin, whether the step fell back off an unreachable pinned model,
result, duration, and a tail of its output, and per run the head and base SHAs it
gated plus whether any step was given the recorded plan as its spec source. `sapa-submit` then puts a summary on the PR:

```text
## Gates

Gated `def5678` against `origin/main@abc1234`.

- **review**: skill `code-review` on `fable`, passed, agent-reported
- **test**: command, passed in 42.3s

Reviewed against the plan recorded on the issue.
```

A gate of one `format` step renders as one bullet and reads as thin, and a PR
where nothing was given the plan says so. A step whose pinned model was
unreachable renders as ``pinned `fable` unreachable, ran on the session model``
rather than asserting the pin, so the bullet never claims a model that did not review.
That is the design: disclosure, not enforcement. Sapa will not refuse to certify
a weak gate; it puts the truth where the reviewer is and lets them judge.

The section also distinguishes two kinds of evidence: a `run:` step's result is
an exit code sapa watched, while a `skill:` step's is what the agent reported and
says `agent-reported`. The spec-source line states what sapa observed, because
sapa cannot know whether a given step is a spec review. Names only, no commands:
the config is checked in and shows up in the diff.

The record lives in the stream's scratch directory and does not survive a reboot.
Submitting without a fresh gate is legitimate, so `sapa gate --report` says no
record was found rather than inventing one, and it flags a gate whose recorded
head is not the current commit. Run it yourself any time: `sapa gate --report`.

### Changed-package scoping in a monorepo

`sapa-gate` rebases onto the base before it runs, so it already holds the diff
against what will merge. It hands that to every `run:` step as two environment
variables:

- `SAPA_BASE`: the branch the PR targets (the config `base`).
- `SAPA_CHANGED_FILES`: the files this branch changed versus the merge-base,
  newline-separated.

That is the whole contract. Your script maps the changed files to packages and
decides what to gate: in a workspace with many packages, gate only the ones the
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

Sapa runs one editor window per stream, so with several streams going the
question is always "which window can I switch to right now?" `sapa status`
answers it for a window switcher: it writes a tiny JSON file per stream that a
switcher reads to badge each window as running, at rest, or waiting.

Two independent fields, each written by whoever knows it:

- `state`: the run-state, `busy` | `idle` | `needs-you`, written by the Claude
  Code hooks `sapa install` wires (`UserPromptSubmit → busy`, `Notification →
  needs-you`, `Stop → idle`).
- `stage`: the lifecycle phase, `plan` | `build` | `gate` | `submit` | `watch`,
  written by each phase skill as its first act.

`stage` is read back inside sapa too: `sapa status --report` prints it (writing
nothing), and that is how `sapa-flow` re-enters a stream at the phase it left off
in. A caller that changes the answer writes the stage it wants resumed, which is
why `sapa-flow` sets it back to `gate` after an interruption that edited the
working tree. An unrecorded stage prints nothing and exits 0: a fresh stream
starts at the first phase. `sapa status` resolves the stream from the `.bare`
project root, so the global hooks do nothing outside sapa sessions. On merge,
`sapa teardown` clears the file.

The registry is one file per stream under `${SAPA_STATUS_DIR:-~/.sapa/status}/`,
keyed by the worktree basename (which equals the branch, and is the token an
editor puts in its window title, the join a switcher matches windows on):

```json
{ "branch": "51-combine-jump-sapa", "stage": "gate", "state": "busy",
  "updated": "2026-07-07T22:48:00Z" }
```

Reading this registry and rendering the badge lives in the switcher.
[Jump](https://github.com/brianegan/jump) is the reference consumer; any tool
that can match a window to a stream by title and read the JSON can use it.

## Prior art

Sapa is not the first tool to gate AI-written code or to run agents in parallel
worktrees. It makes the opposite choices from the tools that do.

- [no-mistakes](https://github.com/kunchenguid/no-mistakes) is the closest in
  spirit and the exact inverse in architecture, the tool sapa was built in
  reaction to (see the [Problem Statement](PRD.md)). It runs the same rough
  pipeline (gate, ship, watch CI) but puts a git proxy in front of `origin`,
  gates in a disposable worktree as a background daemon, and overwrites the PR
  body on every push. Sapa keeps one remote, gates in the live tree in the
  foreground, and locks the PR body the moment you touch it.
- [Orca](https://github.com/stablyai/orca) and [Composio Agent
  Orchestrator](https://github.com/ComposioHQ/agent-orchestrator) are
  parallel-agent cockpits that run many agents in isolated worktrees and surface
  their PRs, but stop before the autonomous gate-ship-watch: CI fixes are manual,
  review comments are shown but not addressed, and nothing is written back to
  the issue. Sapa has no daemon and no dashboard; concurrency is one editor
  window per stream, and closing the window ends that stream's watch.

Three things sapa does that none of them do:

1. It owns the prose without clobbering yours. The PR body has a machine-managed
   section that locks the instant you edit it, and the agreed plan lives as a
   managed comment on the issue that reconciles when what shipped diverges from
   what was planned.
2. It triages comments by author (your own come back to you in the agent chat, a
   colleague's are answered on GitHub with a "Sapa Workflow, on your behalf"
   line) and by substance (mechanical comments are fixed and pushed, subjective
   ones escalated).
3. It runs inside the session that wrote the code: no proxy, no daemon, one
   remote, gate in your live tree, so there is no hidden state to reconcile and
   no supervisor to become a bottleneck.

One honest caveat: no-mistakes already fixes CI failures and rebases a moved
base on its own, so post-PR autopilot itself is not new. What is new is doing it
from inside your session with no second remote, plus the comment triage and the
issue-plan and PR-body ownership it lacks.

## Test

```sh
bash tests/run.sh
```

CI runs the same suite on every push and PR (`.github/workflows/ci.yml`).
