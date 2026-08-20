# PRD: Sapa

Sapa (Filipino for "stream") gates, ships, and watches a piece of work.
Generated via `/to-prd` from the design conversation.

## Status of this document

This PRD is a living record of the current status: the decisions made so far and
the use cases we set out to support. It is a reference, not a contract, and it is
never a blocker. A decision written here reflects what we knew at the time, not a
commitment we owe the past. When a new request contradicts something recorded
here, raise the earlier decision so we weigh them together. The new request does
not always win; if there is a good reason it does not fit with earlier decisions,
we discuss it. Once we decide, update this document to match. The point of the
software is to be used and adapted as we learn from using it, so this document
follows the code rather than fencing it in.

## Problem Statement

I get into a piece of work cleanly with sapa's own tooling (`sapa bootstrap` to
clone or init a bare repo, `sapa worktree` to spin up a worktree per stream), but
nothing gets me out of one. After the code is written, everything is manual: I run quality
checks by hand, hand-fix PR descriptions, feed CI failures back to the agent one
at a time, and integrate a moved `main` myself. I do this across three to five
streams at once, so the manual coordination compounds.

I tried `no-mistakes`, which introduces the workflow I want (a quality gate
before every PR, plus post-PR monitoring), but its architecture fights mine. It
puts a git proxy in front of `origin`, so I juggle a second remote and lose time
thinking I am synced when I am not. It gates in a disposable worktree separate
from mine, so state is opaque. It handles one stream at a time. It rewrites my
hand-edited PR descriptions on every push. And it runs the gate as a background
process, which blocks me in the wrong place and gives me no clean
cancel-edit-rerun loop.

## Solution

A Claude Code skill, plus a few small `git`/`gh` helper scripts, that runs
inside the per-stream Claude session that already did the work. All GitHub
operations go through `gh`. It runs as one fused flow by default — `sapa-flow`
invokes each phase skill in turn — while every phase stays a distinct skill I can
run on its own:

- **Plan** agrees the approach and records it on the issue as a durable comment.
- **Build** reads that recorded plan and implements the code and tests in my
  working tree.
- **Gate** is foreground and blocking. It rebases my branch onto the latest base
  first, so the gate runs against what will actually merge, then runs the checks
  in my working tree. I can cancel it to make a change and rerun; it certifies
  green without pushing.
- **Submit** pushes the green branch and opens (or updates) the PR with a written
  description, then reconciles the plan on the issue.
- **Watch** is the same session monitoring its own PR through a cheap background
  poller. The mechanical half — resolving the PR, polling with back-off, guarding
  empty/failed fetches, and deduping — is the committed, tested `sapa watch`
  helper, which emits one structured line per real change; the skill reasons about
  each event. It fixes CI failures, addresses mechanical review comments, escalates
  subjective ones to me, and auto-rebases a trivially-moved `main` before
  re-running the gate. When the PR merges, it tears the stream down: remove the
  worktree and delete the local branch, so I do not clean up by hand.

`sapa-flow` chains these so I never manually step from one phase to the next, and
it stops wherever a phase stops. Watch starts in a draft posture and continues
through promotion to ready. Each phase is still callable on its own for the edge
cases: gate to check without pushing, submit to open a PR I already gated, watch
to attach to an existing PR without re-gating, build to resume a recorded plan.

There is no second remote, no separate daemon, and no supervisor. Concurrency
comes from running one window per stream, which I already do. Escalations reach
me through my existing notification hook, which opens the right window on click.

## User Stories

1. As a developer, I want to run a single gate command when a stream is ready, so that every PR goes through the same quality bar without me remembering the steps.
2. As a developer, I want the gate to run in my own working tree, so that I never have to keep a second worktree in sync.
3. As a developer, I want the gate to push only to `origin`, so that I never manage a second remote or wonder which remote is authoritative.
4. As a developer, I want the gate to block my session while it runs, so that I have a clear, single place where the work is being checked.
5. As a developer, I want to cancel a running gate, make a change, and rerun it, so that I keep full control when I spot something mid-check.
6. As a developer, I want the gate to run the project's configured review, test, docs, lint, and format steps, so that checks match what CI and my team expect.
7. As a developer, I want the gate to open the PR as a draft, so that I can review and shape it before colleagues are pulled in.
8. As a developer, I want the tool to write a useful PR description, so that I do not hand-write one every time.
9. As a developer, I want the tool to stop editing the PR description the moment I edit it or tell it to leave it alone, so that my prose is never clobbered on the next push.
10. As a developer, I want the tool to upgrade the PR description only on material change until I claim ownership, so that it stays current without fighting me.
11. As a developer, I want the same session to watch its own PR after it is pushed, so that the watcher already has the full context of the work.
12. As a developer, I want the watcher to run as a cheap background poller, so that it is not burning tokens while it waits for something to happen.
13. As a developer, I want to be woken only when something actually happens on the PR, so that I am not distracted by idle polling.
14. As a developer, I want CI failures fixed automatically and pushed, so that I do not have to come back and re-describe the failure to the agent.
15. As a developer, I want mechanical review comments addressed automatically, so that small fixes do not require my attention.
16. As a developer, I want subjective review comments escalated to me rather than guessed at, so that judgment calls stay mine.
17. As a developer, I want a trivially-moved `main` rebased automatically, so that branch-protection "must be up to date" rules do not block me by hand.
18. As a developer, I want the gate re-run after an automatic rebase, so that a clean merge that breaks the build is caught before it is called green.
19. As a developer, I want to promote a draft PR to ready when I decide it is ready, so that I control when colleagues are invited to review.
20. As a developer, I want my own comments on my own PR brought back to me in the coding-agent chat rather than answered on GitHub, so that I am not publicly replying to myself and the conversation with my agent stays where I am working.
20a. As a developer, I want my colleagues' comments answered on GitHub with a note that the reply came from the Sapa Workflow, so that GitHub stays the review surface for colleagues and they can tell my agent apart from me since it can only post under my account.
21. As a developer, I want to run three to five streams at once, each in its own window, so that I can context-switch without being blocked.
22. As a developer, I want each stream to watch its own PR independently, so that no single supervisor process can become a bottleneck or a single point of failure.
23. As a developer, I want to close a window and know that stream's watch is gone, so that the OS owns process lifecycle and there is no hidden state.
24. As a developer, I want escalations delivered through my existing notification hook, so that clicking a notification drops me into the exact window that needs me.
25. As a developer, I want to keep my machine awake myself with caffeinate, so that the tool stays simple and local rather than hosted.
26. As a developer, I want the gate to run with Claude only in v1, so that I am not blocked by an external reviewer that still needs command permissions.
27. As a developer, I want a cross-model reviewer (Codex reviews, Claude implements) to be designable later, so that I can add independent review without re-architecting.
28. As a developer, I want no cross-stream dashboard in v1, so that the tool ships smaller and I rely on my windows and switcher.
29. As a developer, I want all GitHub operations to go through `gh`, so that reads and writes are faithful — an agent-oriented wrapper that truncates long field values corrupts any flow that reads a body back to re-apply a managed section.
30. As a developer, I want the tool to find its config by walking up from the current directory, so that it works from any worktree without per-invocation setup.
31. As a developer, I want a gate step to be able to run a skill rather than a shell command, so that Flutter projects can use the wingspan review skill for the review step.
32. As a developer, I want check commands to run through a version manager like `fvm`, so that analyze, test, and lint use the project's pinned toolchain instead of a global `flutter`/`dart` on PATH.
33. As a developer, I want the same gate skill to adapt per project via config, so that repos with different toolchains all run the right commands.
34. As a developer, I want the agreed plan written to the GitHub issue rather than left in my local session, so that the plan is durable and visible even if I never finish.
35. As a developer, I want the plan on the issue rather than in the code repo, so that it does not become a stale file I have to maintain in source.
36. As a developer, I want the plan to live in a machine-managed comment on the issue that locks when I edit it, so that the tool keeps it current without clobbering my words or touching the issue body.
37. As a developer, I want the issue's plan reconciled when I submit, so that when what I built diverged from the plan, the issue reflects what actually shipped.
38. As a developer, I want the issue's plan updated when review feedback changes the approach, so that the issue never misrepresents the decision we landed on.
39. As a developer, I want the PR description to link the issue with `Closes #N` rather than repeat the plan, so that intent and execution summary each live in one place.
40. As a developer, I want `sapa-flow` to move from each phase to the next automatically and to stop wherever a phase stops, so that a clean run needs no nudging while a blocked one never silently barrels ahead.
41. As a developer, I want to run the gate on its own without pushing, so that I can check work in progress without opening a PR.
42. As a developer, I want to attach watch to an existing PR without re-gating, so that I can resume monitoring from a fresh session.
43. As a developer, I want the worktree removed and the local branch deleted when the PR merges, so that I do not manually tear down finished streams.
44. As a developer, I want teardown skipped and flagged when the worktree has uncommitted changes, so that auto-cleanup never destroys unsaved work.
45. As a developer, I want the gate to rebase my branch onto the latest base before running, so that a green gate reflects what will actually merge and branch-protection "must be up to date" never blocks me at merge time.
46. As a developer, I want the gate to resolve unambiguous rebase conflicts and escalate only the ones where the resolution is a judgement call or could change behaviour, so that trivial overlaps do not interrupt me while behavioural decisions stay mine.
47. As a developer, I want to resume a stream at any phase — build a recorded plan in a fresh session, or submit a branch I already gated — so that stepping in partway never forces me to rerun the earlier phases.
48. As a developer, I want submit's ship summary to lead with the clickable PR URL, so that I can open the PR in my browser for a quick review before watch takes over.
49. As a developer, I want a single `sapa-flow` command that carries a stream from its issue through plan, build, gate, PR, and watch, so that I do not manually kick off each phase, while every phase skill stays runnable on its own when I want just that step.
50. As a developer, I want the gate to integrate my branch's own remote head before rebasing onto the base, so that a teammate's commits pushed to the same branch are not lost when submit later force-pushes.
51. As a developer running three to five streams at once, I want to see at a glance which windows are running, at rest, or waiting on me, so that I know which one I can safely switch to without opening each.
52. As a developer, I want that status to also carry which lifecycle stage each stream is in, so that "watching, idle, waiting on CI" reads differently from "done".
53. As a developer, I want sapa to only *emit* the status and leave rendering to my own window switcher, so that sapa stays a local producer with no hosted UI or supervisor process.
54. As a developer, I want the status hooks to be inert in my non-sapa sessions and removable, so that opting into this never pollutes unrelated work or my global config permanently.
55. As a developer whose team tracks work in Jira, I want to point a repo at Jira with one config key, so that sapa reads the issue from and records the plan to Jira while my PRs stay on GitHub, without changing how any GitHub repo works.
56. As a developer, I want `sapa start gp-1` to accept a Jira key and keep it in the branch name, so that the branch is self-describing and Jira's dev panel links the branch and PR to the issue for free.
57. As a developer, I want the plan comment recorded on a Jira issue to render as formatted text, so that it reads as a plan rather than raw markup — accepting that this rides on sapa overwriting its own comment rather than locking it.
58. As a developer, I want sapa to stop edit-locking the plan comment, so that it always reflects the latest plan; I never hand-edit it, and dropping the lock is what makes the Jira rich-text path simple. My PR description stays edit-locked, since I do edit those.
59. As a developer, I want the gate to write down what it actually ran, so that "the branch is green" is something I can check against a record rather than a claim that disappears with the session.
60. As a reviewer, I want the PR to show which gate steps ran and whether any of them was given the plan to review against, so that I can see a thin gate for what it is without digging through someone else's config.

## Implementation Decisions

- **Form factor.** A Claude Code skill plus small `git`/`gh` helper scripts.
  Not a binary, not a long-lived daemon, not a proxy remote.
- **Install and update (#135).** `sapa install` links the `sapa` command onto
  `PATH` and the skills into each agent, pointing every link back into the clone,
  so the installed copy tracks the source and a sapa developer works from their
  `main` checkout. `sapa update` closes the loop on that model: it resolves the
  clone the running `sapa` points at, runs `git pull --ff-only` there, and on
  success re-runs `sapa install` so a pull that added or renamed a skill, or
  changed the hook wiring, takes effect in one command rather than leaving the
  install quietly stale. The pull is fast-forward only on purpose: the clone
  backs the whole toolchain, so a diverged clone stops with git's own error and
  is left untouched, and the reinstall is gated on the pull succeeding. Install
  through a package manager such as mise is not handled yet; a `git pull` inside
  a manager-owned directory would fight the manager, so a non-git install just
  fails the pull naturally and the manager's own update path is left for when one
  ships.
- **Issue backend (#77).** The issue tracker is selectable per repo with a
  `tracker:` config key: `github` (default) or `jira`. GitHub stays the zero-config
  default and is unchanged. On `jira`, sapa reads the issue from and records the
  plan to Jira through the Atlassian CLI (`acli`) — chosen for the same reason `gh`
  is: shell out to the tool the developer has already authed, rather than owning
  auth. PRs always live on GitHub regardless of tracker; the difference is only the
  issue link (`Closes #N` on GitHub, a `Jira: <browse-url>` line built from
  `jira.site` on Jira, since a GitHub PR cannot auto-close a Jira issue) and where
  the plan lands. The backend is never chosen by hand mid-flow: `sapa start` bakes
  the identity into the branch (a leading number for GitHub, a `gp-1` key for Jira),
  and a new `sapa issue` helper derives it back and owns the gh-vs-acli branch for
  reading and recording the plan, so the phase skills stay backend-agnostic and the
  branch is written and tested once. Two acli quirks shaped the helper, both found
  against a live instance: `comment update` stores its body as plain text and drops
  ADF (only `comment create` renders rich), so the plan comment is refreshed by
  create-new-then-delete-old rather than update-in-place; and `comment list --json`
  flattens away list items, so the plan is read back through `workitem view --fields
  comment --json` (full ADF) and re-flattened faithfully. Jira issue transitions and
  smart-commit closing are out of scope for v1.
- **GitHub interface.** All GitHub operations go through `gh`. An earlier version
  used `gh-axi` (`npx -y gh-axi`) for its token-efficient TOON output, but that
  output truncates long field values at ~2000 chars in every mode, which corrupts
  any reconcile that reads a comment or PR body back to re-apply a `sapa section`
  managed section. Faithful reads matter more here than token thrift, and `gh`
  covers every command sapa uses.
- **Config discovery.** The tool finds its config by walking up from the current
  directory until it finds a config file, the same pattern `sapa worktree` uses
  to locate `.bare`. The walk locates the config; it never relocates execution
  (#117). `sapa gate` resolves the caller's git worktree first and hangs
  everything off that one anchor — the config walk-up, the scratch directory, the
  stream's issue, the diff against the base, and each `run:` step's cwd — because
  in the `.bare` layout the config sits beside `.bare`, above every worktree, and
  a gate anchored on the config's directory ran its steps against a directory
  holding no project and read the bare repo's HEAD as the branch, which cost the
  `skill:` steps their spec source without saying so. One anchor rather than two:
  seeding discovery from the caller's cwd instead would let a `.sapa.yaml` in a
  subdirectory supply the step list while the steps ran at the worktree root. A
  caller outside a work tree is refused rather than fallen back on, since the
  fallback is precisely the broken state. This is what lets one config beside
  `.bare` cover every worktree, which is what the walk-up existed for.
- **Config expressiveness.** A gate step can be either a shell command or a
  skill invocation (for example, the wingspan review skill as the review step),
  and commands can carry a version-manager prefix (for example `fvm dart
  analyze`, `fvm flutter test`) so they use the project's pinned toolchain rather
  than a global binary on PATH. This extends the `no-mistakes` repo-config idea.
  `gate:` is a map holding that list under `steps:`, plus the gate's own settings:
  `max_fix_attempts:` (default 3) bounds `/sapa-gate`'s autofix loop, the way
  `watch.max_ci_fix_attempts` bounds the CI one. It was the flat step list until
  the gate had a setting to carry, and the flat form is now rejected with the edit
  that fixes it rather than accepted alongside, because two accepted shapes is two
  shapes to keep working.
  Alongside the gate map, optional top-level keys tune the flow with
  backward-compatible defaults: `remote:` names the single remote (default
  `origin`), `pr:` selects the state new PRs open in (`draft` or `ready`, default
  `draft`), `plan:` names a skill `/sapa-plan` delegates the planning
  discussion to, `build:` names a skill `/sapa-build` invokes once before its
  first task to shape the implementation (for example `/tdd`),
  `writing_style:` names a skill sapa runs as a final pass over
  the free prose it writes (the plan comment, PR body, and review replies),
  shaping prose only and leaving the structured parts — task lists and their
  `Done when:` lines, the PR title, the gate record — as written, and `tracker:`
  (`github` default, or `jira`) with an optional
  `jira:` map (`site:` for the PR's issue link, `project:` to expand a bare
  `sapa start 1` to `GP-1`) selects the issue backend. A configured `build:` skill
  shapes how each task reaches green and never whether it does: it may tighten
  sapa's rule but not loosen it, and never re-scopes the recorded tasks, the same
  division of labour that lets `plan:` own the planning discussion while the
  record-to-issue step always runs. Config is mostly
  agent-interpreted — `sapa config` walks up and prints the file, and the skills
  read the keys they need the way they already read `base`. A few helpers read it
  themselves: `sapa start` greps the printed config for `tracker`/`project` to
  expand a bare number, `sapa worktree` greps it for `base`/`remote` to pick its
  default start point, and `sapa gate` parses it with PyYAML. The gate is the
  exception on purpose. Walking an ordered list of step maps is past what a grep
  reads honestly, and unlike the other phases the gate's step execution is what
  everything downstream trusts, so it earns a real parser and the tests that come
  with it. That makes PyYAML a dependency of `sapa gate` alone; every other
  command still runs on git and gh.
- **Changed-file contract for `run:` steps.** The gate rebases onto
  `<remote>/<base>` before it runs, so it already holds the diff against what will
  merge. It hands that to every `run:` step as `SAPA_BASE` and
  `SAPA_CHANGED_FILES` (newline-separated paths versus the merge-base). This is
  the one thing sapa knows and a shell script would reinvent — every script that
  recomputed the base did so slightly wrong. It lets a monorepo verify script gate
  only the changed packages and fall back to all on a cross-cutting change, while
  sapa stays out of package discovery and version-manager handling, which vary too
  much per repo and are already covered by the `run:` prefix. `sapa gate` computes
  the diff and sets both variables on each step's environment, so the contract is
  executed by one tested helper rather than reproduced from prose per session.
  Structured per-package step results are a later refinement, built once
  changed-package scoping proves out.
- **The gate record, and disclosure over enforcement.** A green gate was an
  assertion the model made in chat, and it died with the session, so two things
  were invisible: a step that did not really pass, and a gate that never had a bar.
  `sapa gate` now writes a record as it walks — per step the name, kind, command or
  skill, model, whether the step fell back off an unreachable pinned model, result,
  duration, and an output tail, and per run the head and base SHAs and which of four
  states the plan lookup landed in — and `sapa gate --report` renders it as the PR's
  `## Gates` section. A step that fell back keeps the pin in the record as what was
  asked for and renders as ran on the session model, so the section never asserts a
  model that did not review (#138). A PR gated by `format` alone reads as
  visibly thin and a PR where no step saw the plan says so, but sapa never refuses
  to certify a weak gate and never scores one: enforcing a minimum would make
  adoption on someone else's repo a fight and is not sapa's call, while putting the
  truth on the PR moves the pressure to the reviewer and costs a good gate nothing.
  Three things follow from that being evidence rather than prose. The helper renders
  the section, not the model, since a paraphrase of the record is the same assertion
  the record replaced. A `skill:` step's result is carried back by the agent on the
  resume call and printed as `agent-reported`, because the helper cannot observe a
  skill step the way it observes an exit code and collapsing the two would relaunder
  the claim. And the spec-source line states what sapa observed rather than
  concluding the spec went unchecked, since sapa cannot know whether a given step is
  a spec review. The record is `{"runs": [...]}` and appends rather than overwrites,
  aging out the oldest runs past a cap: a bare invocation appends a run, `--after`
  extends the last one, and a resume with no usable record walks from the top rather
  than write a partial account. That shape
  is deliberately #99's — it gates only the `run:` steps before pushing a CI fix and
  needs the full-gate run still present beside it — as are the per-run SHAs, the
  `scope` field, and the split between record-level and run-level rendering.
- **One fused flow, separable phase skills.** `sapa-flow` is the fused default: a
  single invocation carries a stream from its issue through plan, build, gate,
  PR, and watch by invoking each phase skill in turn, with no second command. It
  implements none of the phases itself, and stops wherever a phase escalates. What it
  does own is the crossing between phases, and that crossing is automatic: a phase
  returning is not the flow ending, so the flow continues to the next phase without
  asking the developer for permission, and only an escalation stops it. The same
  rule holds one level down, inside `sapa-build` between tasks. It also survives
  the developer interrupting mid-stream: their requests suspend the flow rather
  than ending it, and once handled the flow re-enters on its own. Finally, the flow
  is resumable, because it enters at the stage recorded for the stream rather than
  at the top (below). So `sapa-flow` means "carry this stream forward from wherever
  it is", not "run all five phases from the beginning". Each phase is its
  own skill with its own context and lifetime, and stays callable alone for the
  edge cases: `sapa-plan` to capture a plan, `sapa-build` to resume a recorded
  one, `sapa-gate` for checks without pushing, `sapa-submit` to open a PR that is
  already green, and `sapa-watch` to attach to an existing PR without re-gating.
  The gate phase is foreground, blocking, and cancelable; the watch phase is a
  background poller owned by the same session.
- **Single remote.** The tool touches exactly one remote, `origin` by default.
  Its name is configurable via `remote:` for developers who name their remotes
  deliberately, but there is never a second remote, proxy, or secondary push
  target.
- **In-tree gate.** The gate operates on the developer's active working tree, not
  a disposable copy. Cancel is interrupting the session; rerun is invoking the
  gate again.
- **Rebase before gating.** `sapa-gate` first integrates the branch's own remote
  head (`<remote>/<branch>`, when it exists) so a teammate's pushed commits are
  not lost to a later force-push, then rebases the branch onto `<remote>/<base>`,
  so a green gate reflects the state that will actually merge, not a stale base. On
  a conflict at either rebase, the gate resolves what is unambiguous and escalates
  only conflicts whose resolution is a judgement call or could change behaviour,
  rather than guessing blindly or handing back every overlap. This is distinct from
  watch's trivial-merge rebase, which reacts to the base moving after the PR is
  open.
- **Configured checks.** The gate runs the project's configured review, test,
  docs, lint, and format steps from the discovered config as the source of truth
  rather than pure auto-detection.
- **Draft-first PR.** On a green gate the tool pushes to the configured remote
  and opens the PR as a draft by default; promotion to ready is then a manual
  developer action. Repos where draft is pure overhead (typically solo) can set
  `pr: ready` to open ready-for-review directly.
- **PR description ownership.** The tool writes and upgrades the description on
  material change by default. A human edit, or an explicit "leave it" signal,
  locks the description and the tool never modifies it again.
- **PR format.** The title and body follow a fixed shape so every sapa PR reads
  the same way. The title is Conventional Commits — `<type>: <imperative
  summary>` (`feat|fix|docs|refactor|test|chore`), no issue number, since it
  becomes the squash-merge commit title. The body is an execution summary of what
  shipped, not a repeat of the plan, in four sections: `## Summary` (what
  changed and why), `## Changes` (notable changes, omitted for trivial ones),
  `## Testing` (how a reviewer can best test the change themselves, scaled to the
  change — green lights for a mechanical one, navigation steps for a
  human-perceived one), and `## Gates` (the automated record — kept out of
  `## Testing` so the reviewer-facing steps stay uncluttered). `## Gates` is not
  composed by the model: `sapa gate --report` renders it from the gate record and
  `sapa-submit` appends it verbatim, after the `writing_style:` pass and never
  through it. `Closes #N` sits outside the managed section so it survives after a
  human locks the body.
- **Watcher wake model.** The background poller checks CI and comments on an
  interval with back-off and only wakes the session when state changes. The
  polling itself is the committed `sapa watch` helper: it resolves the PR for the
  current branch, guards empty or failed fetches so a bad cycle never counts as a
  change, dedupes against last-seen state, and emits one structured line per real
  change (`ci-failed`, `new-review`, `new-comment`, `base-behind`, `merged`,
  `closed`), exiting on the terminal states. A review still in `PENDING` state is
  the author's own unsubmitted draft and is skipped entirely — not emitted and
  not recorded as seen — so the review reads as new when it is submitted rather
  than being deduped away and stranded as pending. The skill runs it via Monitor and
  decides what each event warrants. This extracts the detection half — mechanical
  and identical every session — into tested code, leaving only the response half
  (which the agent must reason about) in the skill, mirroring how `sapa section`
  owns the comment-ownership logic. (The helper does not read `remote`/`base` from
  config, unlike the push/rebase subcommands: it resolves the PR by current branch
  and detects a moved base from `gh`'s `mergeStateStatus`. The one config knob that
  reaches the helper is `watch.base_behind`, which the skill reads and threads as
  `--base-behind`; the `sapa-watch` skill still reads `remote`/`base` for the fixes
  it pushes and the rebase-and-gate it triggers.)
- **Comment classification.** Two axes. First, by author: the `sapa watch`
  helper tags every new review/comment `self` (the authenticated gh user) or
  `other` (anyone else), resolving the viewer login once via `gh api user` and
  failing safe to `self` when it can't — a wrong `self` keeps the response
  private in the chat, a wrong `other` would post the public reply-to-yourself
  we are avoiding. A `self` comment is answered in the coding-agent chat and
  never on GitHub; an `other` comment is answered on GitHub, and any such reply
  leads with a "Sapa Workflow, on @<login>'s behalf" attribution line because it
  posts under the developer's account. Second, for `other` comments only, by
  substance: the watcher distinguishes mechanical comments (it fixes and pushes)
  from subjective comments (it escalates). The exact mechanical/subjective
  boundary is an open decision.
- **Behind detection.** `watch.base_behind` (default `protection`) chooses how a
  behind branch is spotted. `protection` fires `base-behind` only on
  `mergeStateStatus: BEHIND`, which GitHub reports only when a "require branches up
  to date" protection rule is active. `any` also fires it when the base has
  genuinely moved ahead without that rule — the status stays `CLEAN`/`UNSTABLE`, so
  the helper consults GitHub's compare API (`behind_by > 0`) instead. It skips the
  extra call when the status already answers it (`BEHIND` is behind, `DIRTY`
  escalates to `base-conflicted` and must not also fire `base-behind`), and a
  failed compare is read as no signal so it never fires a false `base-behind`.
  `any` keeps branches aggressively current at the cost of a rebase and re-gate on
  every merge to the base, so the default stays `protection`. A future `off` state
  (never rebase, for teams that merge rather than rebase) is left as headroom in
  the enum.
- **Trivial-merge policy.** A moved `main` is auto-rebased only when the merge is
  trivial, and the gate is always re-run afterward before the PR is considered
  green. The precise definition of "trivial" is an open decision.
- **Merge teardown.** When the watcher sees the PR merged, that is the terminal
  state of the stream. It removes the worktree and deletes the local branch so
  there is no manual cleanup. Two guards: it only tears down a clean worktree,
  and if there are uncommitted changes it skips teardown and flags them instead.
  Because the watch session runs inside the very worktree it is removing, the
  teardown runs from the project root (not from inside the worktree) as the
  watcher's final action, after which the window is detached and can be closed.
  Deleting the remote branch is left to GitHub's auto-delete-on-merge setting.
- **Escalation transport.** Human-in-the-loop escalations use the existing
  notification hook (`claude-notify.sh`), which opens the originating window on
  click.
- **Concurrency by windows.** Three to five concurrent streams are handled by one
  window per stream, not by a supervisor. The OS and the developer's window
  switcher provide the coordination.
- **v1 reviewer.** The gate runs with Claude only in v1. Cross-model review
  (Codex reviews, Claude implements) is designed for via configuration and
  deferred.
- **Model posture (#65).** The ClaudeDevs delegation patterns — a strong model
  coordinating while cheaper sub-agents build, or a cheap session consulting a
  strong advisor — were evaluated and delegating authorship was declined on
  quality grounds. The thread's own SWE-bench Pro numbers: Sonnet 5 solo ~0.755,
  Sonnet 5 with a Fable advisor ~0.84, Fable 5 solo ~0.91 — every delegation
  pattern gives up accuracy against the strongest model working alone.
  Authorship sets the quality ceiling and review only defends it, and a builder
  sub-agent cannot talk to the developer, so plan ambiguity becomes escalation
  round trips. Adopted instead: sessions stay model-agnostic with Opus as the
  recommended executor, and the gate's review step is pinned to Fable via a
  per-step `model:` key on gate steps — review is the one judgment-dense moment
  that is bounded, token-light, and needs no mid-task developer interaction, and
  a fresh-context reviewer avoids author-reviews-own-work bias regardless of
  model. `sapa gate` reads the key and reports it on the step's `needs-skill`
  line, but honouring it stays with the skill: pinning a model means spawning a
  sub-agent, which needs the harness. The pin is a preference, not a requirement
  (#138): when the harness cannot reach the pinned model — the account has no
  access to it, or the harness has no such model, as Codex has no Fable — the
  step falls back to the session model rather than failing the gate, so a stream
  stays gateable by anyone who clones it. The skill catches the unreachable-model
  error and re-spawns without the override, and the fallback is recorded through a
  `--fell-back` flag so the PR reports the session model ran rather than asserting
  the pin did (see the gate record below). Reserve
  positions: if cost tightens further, the advisor posture — Sonnet sessions
  with Fable pinned at plan and review — is the designed fallback at roughly 92%
  of solo quality for 63% of the price; if quality headroom is wanted later, the
  cross-model reviewer (user story 27) remains the direction.
- **Plan capture on the issue.** The agreed plan is written to the issue (GitHub
  or Jira, per `tracker`), not kept in the local session and not committed to the
  code repo. It lives in a dedicated, machine-managed "Plan" comment — never in the
  issue body, which stays byte-for-byte as the author wrote it. That one comment
  carries both the plan and a "Decisions & Discussions" section (#78) distilling
  why the plan looks the way it does — the choices, their rationale, and the
  questions planning surfaced (e.g. a grilling discussion) — so a later
  reader understands why a feature was built the way it was, not only what it
  does. The plan is
  reconciled at submit (if the build diverged) and when review feedback materially
  changes the approach, so the issue stays truthful across the life of the work.
  The PR does not repeat the plan; it links the issue (`Closes #N` on GitHub, a
  `Jira: <browse-url>` line on Jira). How the plan is *developed* is pluggable:
  `plan:` can point `/sapa-plan` at another skill (wingspan `/plan`,
  `/grilling`) to run the discussion, but the record-to-issue-comment step
  always runs, since that durable capture — not the dialogue style — is sapa's
  contribution.
- **Plan comment is not edit-locked (#77).** Revised from the original design,
  which locked the plan comment on a human edit under the same ownership rule as
  the PR description. In practice the plan comment is never hand-edited, so sapa
  now finds its own comment by an identity marker (an invisible `<!-- sapa:plan -->`
  on GitHub, a visible sentinel line on Jira) and overwrites it — no content hash,
  no lock. This is not only a simplification: the hash lock was the one thing that
  forced a byte-exact round-trip, and dropping it is what lets the Jira comment be
  authored as rich ADF (which acli stores but reads back only in a flattened form).
  The `sapa issue plan-comment` helper owns find-create-overwrite and marker
  injection for both backends. The **PR-description** lock is unaffected and stays
  in `sapa section`: PR bodies are edited by hand often, plan comments are not.
- **Window-switcher status (#51).** Sapa emits each stream's status so an external
  window switcher (reference consumer: Jump) can badge every window as running, at
  rest, or waiting — the cross-stream visibility the "concurrency by windows" model
  otherwise leaves to the eye. `sapa status` writes one JSON file per stream to a
  global registry (`${SAPA_STATUS_DIR:-~/.sapa/status}/<basename>.json`), keyed by
  the worktree basename — which equals the branch and is the token an editor puts in
  its window title, the join a switcher matches on. One file per stream so each
  window only writes its own (no cross-window contention) and teardown removes just
  that file. The file carries two orthogonal fields written by whoever knows each:
  `state` (`busy`/`idle`/`needs-you`, the run-state) and `stage`
  (`plan`/`build`/`gate`/`submit`/`watch`, the lifecycle phase). They are merged
  with an atomic read-modify-write (tmp + `os.replace`, as `sapa watch`) so the two
  writers never clobber each other. The producer/consumer split is deliberate: sapa
  owns writing the status; rendering stays in the switcher, keeping sapa a local
  producer with no hosted UI. Run-state comes from Claude Code hooks
  (`UserPromptSubmit → busy`, `Notification → needs-you`, `PreToolUse → busy`,
  `Stop → idle`) because hooks fire deterministically regardless of what the agent
  is doing; stage comes from the phase skills, each recording its own as its first
  act. `stage` has since gained a second consumer inside sapa, which fixes its
  meaning: `sapa status --report` prints it and writes nothing, and `sapa-flow`
  reads it to enter a stream at the phase it left off in. So `stage` means "where
  this stream picks up", not "the last phase that happened to run", and a caller
  that changes the answer writes the stage it wants resumed rather than leaving a
  stale one to be second-guessed at read time. That is why `sapa-flow` rewrites it
  to `gate` after an interruption that changed the working tree, or to `plan` when
  the interruption changed what the work should be: re-entry stays encoded in one
  place, and a stream interrupted after a green gate cannot resume at submit and
  push un-gated work. The read prints a bare value rather than JSON,
  as `sapa issue key` and `sapa tmp` do, so no skill parses JSON in shell; an
  unrecorded stage prints nothing and still exits 0, which the caller reads as
  "begin at the first phase". `PreToolUse` clears a stale
  `needs-you` when the agent resumes work after you resolve a prompt without typing
  a fresh one (approving a permission or answering a tool-based question never
  fires `UserPromptSubmit`); it only downgrades `needs-you`, so firing on every
  tool call does not churn the file. `sapa install` wires those hooks into
  `~/.claude/settings.json` — the one config file sapa edits rather than hinting at,
  justified because reliable run-state is only available through hooks. It is made
  safe the way the symlink installer is: idempotent, reversible (`sapa uninstall`
  removes exactly its own entries), and it touches only entries it
  recognizes as its own, never the user's other hooks. `sapa status` self-guards by
  walking up for the `.bare` root, so the global hooks are inert in non-sapa
  sessions. Only the sapa (producer) side is in this change; the Jump (consumer)
  side — matching a window to a stream by title and rendering the badge — is a
  separate change in that repo, built against this contract.

## Testing Decisions

- **What makes a good test here.** Assert on external, observable behavior of the
  command surface: git state after a run, that only `origin` was pushed, that a
  draft PR was requested, the resulting PR-description body, and cancel/rerun
  outcomes. Do not assert on the agent's internal reasoning, which is
  non-deterministic and verified by observation.
- **Primary seam (aim for one).** An end-to-end test that drives `gate` and
  `watch` against a disposable fixture git repo with `gh` stubbed to return
  canned CI states, canned review comments, and a canned moved-`main`. This one
  seam exercises the full flow. The fixture config can also point a step at a
  no-op stub skill and a stub version-manager prefix to prove config wiring
  without a real Flutter toolchain.
- **Secondary seam.** An isolated test of the PR-description ownership lock:
  given a description marked human-owned, a subsequent run must not modify it.
  This rule is the most likely to regress silently, so it earns its own test.
- **Modules tested.** The deterministic helper scripts behind the `sapa`
  subcommands: `sapa config` (walk-up discovery), `sapa section` (the
  ownership-lock logic for the PR body), `sapa issue` (branch-to-identity
  derivation for both backends, and the plan-comment find/create/overwrite plus
  ADF flatten and marker injection, with `gh` and `acli` both stubbed on PATH),
  `sapa gate` (the step walk: the `SAPA_BASE`/`SAPA_CHANGED_FILES` contract against
  a fixture repo's real merge-base diff, fail-fast on a failing step, the halt at a
  `skill:` step and the `--after` resume, the plan present/absent signal, and the
  config errors), `sapa watch` (the poll
  emitter: the empty/failed-fetch guard, dedup against last-seen state, each event
  type, and terminal-state exit, with `gh` stubbed on PATH), `sapa start`
  (issue-to-branch-name derivation, including Jira keys and bare-number expansion),
  `sapa status` (keyed write to the registry,
  state/stage merge without clobber, the self-guard outside a sapa stream, and
  `--clear`), `sapa teardown` (clean-guarded worktree removal), and `sapa
  bootstrap` (the `init` path builds the `.bare` + `main` layout offline), plus the
  `sapa` dispatcher itself (routing, help, unknown commands). `sapa install`'s hook
  merge is covered too: it wires the three run-state hooks idempotently and
  `uninstall` removes only its own, tested against a seeded `settings.json` under a
  sandboxed `HOME`. The remaining agent-driven parts (opening the PR, fixing CI,
  classifying comments) are verified by observation, not unit tests, as is
  `sapa worktree` (it fetches `origin` and opens an editor).
- **Prior art.** `no-mistakes` is the model: its `workflow_*_test.go` and recorded
  end-to-end fixtures drive the pipeline against fixture repos with recorded
  agent interactions. Imitate that fixture-driven, command-surface approach.
- **Skill linter, not evals.** sapa's skills are preference skills — durable,
  opinionated workflow — the kind worth protecting. A model-graded eval, though,
  means running a model in CI: a paid API bill, or a free tier (GitHub Models)
  that grades on a proxy model rather than the Claude the skills actually run on,
  which is weak signal. At this prototype stage that cost is not worth it, so
  model-graded triggering evals stay a maybe-later local script (run under an
  existing Claude subscription), out of CI. What CI runs instead is a
  deterministic linter of the `SKILL.md` files (`tests/test_skill_lint.py`,
  wired into `tests/run.sh` and the gate): valid frontmatter with a name matching
  its directory, a SKILL.md under 500 lines, a bounded description, and no two
  skills claiming the same quoted trigger phrase. It is an internal test-suite
  util, never a `sapa` subcommand. This adds a deterministic slice on top of the
  observation-based verification above, not a replacement for it.

## Out of Scope

- A git proxy remote or any second remote. `origin` only, always.
- A cross-stream mission-control view or supervisor UI. Status still lives per
  window — but as of #51 sapa *emits* a per-stream status (`sapa status`) that an
  external window switcher reads to badge each window (see "Window-switcher
  status" below). That is the v2 the "possible v2" note anticipated: a producer
  sapa owns, not a dashboard sapa hosts. A hosted mission-control view remains out
  of scope.
- A Codex (or any cross-model) reviewer in v1. Designed for, deferred.
- Any always-on hosted process. The tool is local; the developer keeps the
  machine awake with caffeinate when work should continue during a break.
- A supervisor process coordinating multiple streams.

## Further Notes

- The design deliberately splits `no-mistakes`' single background pipeline into a
  foreground gate and a background watch, because putting the gate in the
  background was the root of the "separation" and lost-sync pain.
- The tool bundles the `sapa bootstrap` and `sapa worktree` commands that get you
  into a stream, so a fresh clone carries the whole workflow — from setting up a
  worktree to a merged PR — rather than depending on tooling that lives only on
  one machine.
- Open questions to resolve before build: the config file
  format and name (how a step declares "run this skill" vs "run this command,"
  and how it carries a version-manager prefix), poll interval and back-off, the
  precise "trivial merge" definition and its re-gate cost across three to five
  streams, and the mechanical-vs-subjective comment boundary.
- `gh` is assumed installed and authenticated (`gh auth status`); sapa shells out
  to it for every GitHub operation.
