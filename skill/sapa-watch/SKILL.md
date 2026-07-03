---
name: sapa-watch
description: Monitor a stream's PR — fix CI failures, address review comments, keep it mergeable, and tear the stream down when it merges. Use to attach to an existing PR, or when the user says "watch this", "sapa watch", or "/sapa-watch". sapa-ship hands off here automatically.
---

# sapa-watch

Watch this stream's PR and act on what happens, until it merges. Attaches to an
existing PR without gating, so it can also resume monitoring from a fresh
session.

Rules (always): `origin` is the only remote; GitHub goes through `npx -y gh-axi`,
never `gh`; never clobber human text (PR body and issue plan go through
`sapa-section`).

## Find the PR

Use the PR for the current branch. `npx -y gh-axi pr view --full` (or
`pr list --head <branch>`) to get its number and state.

## The watch loop

Poll cheaply. Run the status check as a background process on an interval with
back-off, and only wake to act when something actually changed, so the session
is not burning tokens while it waits. On each change:

- **CI is failing** (`npx -y gh-axi pr checks <N>`): read the failing job, fix the
  cause in the working tree, commit, and push. Re-check.
- **A new review comment** (`npx -y gh-axi pr view <N> --comments --reviews`):
  - Mechanical (rename, typo, obvious small fix): make the change, push, and
    reply that it is done.
  - Subjective or a judgement call: do not guess. Escalate to the user through
    the notification hook so clicking it opens this window, and wait.
  - If a comment changes the approach, refresh the plan on the issue with
    `sapa-section plan` (add a comment instead if that section is locked).
- **`main` has moved** and branch protection needs the branch up to date: if the
  rebase is trivial (no conflicts), rebase onto `origin/main`, re-run the gate
  (the `/sapa-ship --gate-only` steps), and push. If it is not trivial, escalate.

The user may promote the draft to ready whenever they choose; keep watching
across that transition. Their comments and colleagues' comments flow through the
same path.

## Teardown on merge

When the PR is merged (`state: merged`), the stream is done. Tear it down:

```
sapa-teardown
```

Run it from the project root or let the script relocate itself — it removes this
worktree and deletes the local branch, and refuses if there are uncommitted
changes. Report that the stream is merged and cleaned up; the window can be
closed. This is the watch loop's terminal action, so stop after it.
