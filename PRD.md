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
  poller. It fixes CI failures, addresses mechanical review comments, escalates
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
20. As a developer, I want my own review comments and my colleagues' comments to flow through the same pipe, so that GitHub is the single review surface regardless of who is commenting.
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

## Implementation Decisions

- **Form factor.** A Claude Code skill plus small `git`/`gh` helper scripts.
  Not a binary, not a long-lived daemon, not a proxy remote.
- **GitHub interface.** All GitHub operations go through `gh`. An earlier version
  used `gh-axi` (`npx -y gh-axi`) for its token-efficient TOON output, but that
  output truncates long field values at ~2000 chars in every mode, which corrupts
  any reconcile that reads a comment or PR body back to re-apply a `sapa section`
  managed section. Faithful reads matter more here than token thrift, and `gh`
  covers every command sapa uses.
- **Config discovery.** The tool finds its config by walking up from the current
  directory until it finds a config file, the same pattern `sapa worktree` uses
  to locate `.bare`.
- **Config expressiveness.** A gate step can be either a shell command or a
  skill invocation (for example, the wingspan review skill as the review step),
  and commands can carry a version-manager prefix (for example `fvm dart
  analyze`, `fvm flutter test`) so they use the project's pinned toolchain rather
  than a global binary on PATH. This extends the `no-mistakes` repo-config idea.
  Alongside the gate list, optional top-level keys tune the flow with
  backward-compatible defaults: `remote:` names the single remote (default
  `origin`), `pr:` selects the state new PRs open in (`draft` or `ready`, default
  `draft`), and `plan:` names a skill `/sapa-plan` delegates the planning
  discussion to. Config stays agent-interpreted — `sapa config` still just walks
  up and prints the file; the skills read the keys the way they already read
  `base`, so no parser is introduced.
- **Changed-file contract for `run:` steps.** The gate rebases onto
  `<remote>/<base>` before it runs, so it already holds the diff against what will
  merge. It hands that to every `run:` step as `SAPA_BASE` and
  `SAPA_CHANGED_FILES` (newline-separated paths versus the merge-base). This is
  the one thing sapa knows and a shell script would reinvent — every script that
  recomputed the base did so slightly wrong. It lets a monorepo verify script gate
  only the changed packages and fall back to all on a cross-cutting change, while
  sapa stays out of package discovery and version-manager handling, which vary too
  much per repo and are already covered by the `run:` prefix. It stays
  agent-interpreted: the gate skill exports what it already computed during the
  rebase, so no new command or parser is introduced. Structured per-package step
  results are a later refinement, built once changed-package scoping proves out.
- **One fused flow, separable phase skills.** `sapa-flow` is the fused default: a
  single invocation carries a stream from its issue through plan, build, gate,
  PR, and watch by invoking each phase skill in turn, with no second command. It
  holds no logic of its own and stops wherever a phase stops. Each phase is its
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
  shipped, not a repeat of the plan, in three sections: `## Summary` (what
  changed and why), `## Changes` (notable changes, omitted for trivial ones), and
  `## Testing` (how it was verified). `Closes #N` sits outside the managed section
  so it survives after a human locks the body.
- **Watcher wake model.** The background poller checks CI and comments on an
  interval with back-off and only wakes the session when state changes.
- **Comment classification.** The watcher distinguishes mechanical comments (it
  fixes and pushes) from subjective comments (it escalates). The exact boundary
  is an open decision.
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
- **Plan capture on the issue.** The agreed plan is written to the GitHub issue,
  not kept in the local session and not committed to the code repo. It lives in a
  dedicated, machine-managed "Plan" comment on the issue — never in the issue
  body, which stays byte-for-byte as the author wrote it — under the same
  ownership rule as the PR description: the tool maintains that comment until the
  developer edits it, then it locks. The plan is reconciled at submit (if the
  build diverged) and when review feedback materially changes the approach, so
  the issue stays truthful across the life of the work. The PR description links
  the issue with `Closes #N` and does not repeat the plan. How the plan is
  *developed* is pluggable: `plan:` can point `/sapa-plan` at another skill
  (wingspan `/plan`, `/grill-with-docs`) to run the discussion, but the
  record-to-issue-comment step always runs, since that durable capture — not the
  dialogue style — is sapa's contribution.

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
  ownership-lock logic for both PR body and issue plan), `sapa start`
  (issue-to-branch-name derivation), `sapa teardown` (clean-guarded worktree
  removal), and `sapa bootstrap` (the `init` path builds the `.bare` + `main`
  layout offline), plus the `sapa` dispatcher itself (routing, help, unknown
  commands). The `gh`-driven and agent-driven parts (opening the PR, fixing CI,
  classifying comments) are verified by observation, not unit tests, as is
  `sapa worktree` (it fetches `origin` and opens an editor).
- **Prior art.** `no-mistakes` is the model: its `workflow_*_test.go` and recorded
  end-to-end fixtures drive the pipeline against fixture repos with recorded
  agent interactions. Imitate that fixture-driven, command-surface approach.

## Out of Scope

- A git proxy remote or any second remote. `origin` only, always.
- A cross-stream dashboard or mission-control view. Status lives per window in
  v1; a dashboard is a possible v2.
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
