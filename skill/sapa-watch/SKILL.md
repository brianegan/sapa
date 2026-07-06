---
name: sapa-watch
description: Monitor a stream's PR — fix CI failures, address review comments, keep it mergeable, and tear the stream down when it merges. Use to attach to an existing PR, or when the user says "watch this", "sapa watch", or "/sapa-watch". sapa-flow hands off here after submit; it also attaches to an existing PR on its own.
---

# sapa-watch

Watch this stream's PR and act on what happens, until it merges. Attaches to an
existing PR without gating, so it can also resume monitoring from a fresh
session.

Rules (always): the configured remote (default `origin`) is the only remote —
read it, the base branch, and the PR state from `sapa config -p`; GitHub goes
through `gh`; never clobber human text (PR body and issue plan go through
`sapa section`).

## Find the PR

Use the PR for the current branch. `gh pr view` (or `gh pr list --head <branch>`)
to get its number and state.

## The watch loop

Poll cheaply. Run the status check as a background process on an interval with
back-off, and only wake to act when something actually changed, so the session
is not burning tokens while it waits. On each change:

- **CI is failing** (`gh pr checks <N>`): read the failing job, fix the
  cause in the working tree, commit, and push. Re-check.
- **A new review comment** (`gh pr view <N> --comments`):
  - Mechanical (rename, typo, obvious small fix): make the change, push, and
    reply that it is done.
  - Subjective or a judgement call: do not guess. Escalate to the user through
    the notification hook so clicking it opens this window, and wait.
  - If a comment changes the approach, refresh the plan comment on the issue by
    running `/sapa-plan` step 4's flow in full: find the `sapa:plan` comment,
    read its body untruncated with `gh api .../issues/comments/<id> --jq .body`,
    apply the same truncation guard (a `<!-- sapa:plan hash=… -->` or
    `<!-- sapa:plan locked -->` wrapper line with no matching `<!-- /sapa:plan -->`
    close → stop, do not patch; a marker quoted inline in prose does not count),
    then run it through `sapa section plan`
    and patch it in place. If that comment is locked or edited, leave it. Never
    touch the issue body.
- **The base branch has moved** and branch protection needs the branch up to
  date: if the rebase is trivial (no conflicts), invoke `/sapa-gate` (it rebases
  onto `<remote>/<base>` and re-runs the checks), then push. If it is not
  trivial, escalate.

If the PR was opened as a draft, the user may promote it to ready whenever they
choose; keep watching across that transition. (When it shipped ready there is
nothing to promote.) Their comments and colleagues' comments flow through the
same path.

## Teardown on merge

When the PR is merged (`state: merged`), the stream is done. Tear it down:

```
sapa teardown
```

Run it from the project root or let the script relocate itself — it removes this
worktree and deletes the local branch, and refuses if there are uncommitted
changes. It then closes the VS Code window that was open on the worktree, so
there is no manual window management (macOS + VS Code, best-effort; disable with
`close_window: false` in `.sapa.yaml`). Report that the stream is merged and
cleaned up. This is the watch loop's terminal action, so stop after it.
