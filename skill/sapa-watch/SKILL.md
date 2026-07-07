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

Before anything else, mark the stream's stage for the window switcher: run `sapa
status --stage watch` (best-effort — it no-ops outside a sapa stream). Teardown on
merge clears the status file, so no explicit clear is needed here.

## Find the PR

Use the PR for the current branch. `gh pr view` (or `gh pr list --head <branch>`)
to get its number and state.

## The watch loop

Do not reimplement the poll loop. `sapa watch` owns the mechanical half —
resolving the PR, polling with back-off, guarding empty or failed fetches, and
deduping — so the detection is written once and tested, not improvised each
session. Run it as a background process through Monitor and only wake to act when
it emits a line. Each line is one real change: the first tab-separated token is
the event type.

- `ci-failed	<checks>` — CI is failing. Read the failing job (`gh pr checks
  <N>`), fix the cause in the working tree, commit, and push.
- `new-review	<id> <author> <state> <self|other>` /
  `new-comment	<id> <author> <self|other>` — a review or comment landed. The
  trailing marker says who wrote it: `self` is you (the authenticated gh user,
  this stream's developer), `other` is anyone else. Read it
  (`gh pr view <N> --comments`) and route on the marker:
  - **`self`** — your own comment on your own PR. Do **not** reply on GitHub (not
    the PR, not the issue): a public reply to yourself is noise. Instead surface
    its content here and escalate through the notification hook so clicking it
    opens this window, then handle it in the chat. GitHub is not the reply
    surface for your own words; this session is.
  - **`other`** — a colleague. Decide:
    - Mechanical (rename, typo, obvious small fix): make the change, push, and
      reply on GitHub that it is done.
    - Subjective or a judgement call: do not guess. Escalate to the user through
      the notification hook so clicking it opens this window, and wait.

    Any reply you post to an `other` comment goes out under your gh account, so
    lead it with an attribution line so the colleague knows it is your agent, not
    you typing:

    ```
    🤖 _Sapa Workflow, on @<your-login>'s behalf:_

    <the reply>
    ```

    `<your-login>` is the authenticated gh user (`gh api user --jq .login`).
  - Either marker: if it changes the approach, refresh the plan comment on the
    issue by running `/sapa-plan` step 4's flow in full (find the `sapa:plan`
    comment, feed its body through `sapa section plan`, patch in place). `sapa
    section` refuses a damaged read on its own, so there is no guard to hand-roll
    here. If that comment is locked or edited, leave it. Never touch the issue
    body.
- `base-behind` — the base branch moved and branch protection needs the branch
  up to date: if the rebase is trivial (no conflicts), invoke `/sapa-gate` (it
  rebases onto `<remote>/<base>` and re-runs the checks), then push. If it is not
  trivial, escalate.
- `merged` / `closed` — terminal. `sapa watch` emits this and exits; on `merged`,
  tear the stream down (below).

After you push a fix, `sapa watch` keeps running and will emit the next real
change; you do not restart it. It dedupes against what it has already seen, so
acting on an event will not make it fire again.

If the PR was opened as a draft, the user may promote it to ready whenever they
choose; keep watching across that transition. (When it shipped ready there is
nothing to promote.) Your own comments and colleagues' comments split by the
`self`/`other` marker above: yours are handled here in the chat, theirs on
GitHub with Sapa Workflow attribution.

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
