---
name: sapa-ship
description: Gate a stream in the working tree and ship it as a draft PR, then start watching it. Use when work is ready to go up, or the user says "ship it", "gate this", "sapa ship", or "/sapa-ship". Pass --gate-only to run the checks without pushing.
---

# sapa-ship

Run the quality gate in the working tree, then push to `origin` and open a draft
PR. On success, hand off to watching. Does not plan — that is `/sapa-plan`.

Rules (always): `origin` is the only remote; GitHub goes through `npx -y gh-axi`,
never `gh`; never clobber human text (the PR body is written with `sapa-section`).

## Step 1 — Locate the config

Run `sapa-config -p` to print the discovered `.sapa.yaml` (it walks up from the
current directory the way `worktree` finds `.bare`). If none is found, ask
whether to use a sensible default gate (test + format) or stop.

The config is an ordered list of gate steps. Each has a `name` and either:

- `run:` — a shell command, run verbatim in the working tree. It may carry a
  version-manager prefix such as `fvm flutter test`.
- `skill:` — a skill to invoke for that step (for example a review skill). Treat
  its findings as the step result.

## Step 2 — Run the gate (blocking)

Run each step in order, in the working tree. This blocks.

- All steps pass → continue.
- A step fails → **stop**. Report the failing step and its output as a finding.
  Apply a safe, mechanical fix and rerun from the top; if it is a judgement call,
  ask. Do not ship until green. The user may interrupt to change something and
  rerun `/sapa-ship`.

If invoked with `--gate-only`, stop here after reporting the result. Do not push.

## Step 3 — Ship

1. Commit any uncommitted work with a clear message if needed.
2. Push to `origin` only: `git push -u origin HEAD`.
3. Build the PR body in a managed section so it is protected from the start:

   ```
   printf '%s' "$PR_SUMMARY" > /tmp/sapa-pr.md
   printf '' | sapa-section pr-description --content-file /tmp/sapa-pr.md > /tmp/sapa-pr-body.md
   ```

   Append `\n\nCloses #<N>` so the PR links its issue. Do not repeat the plan;
   the plan lives on the issue.
4. Open it as a **draft**:

   ```
   npx -y gh-axi pr create --draft --base <base> --title "<title>" --body-file /tmp/sapa-pr-body.md
   ```

   If a PR already exists for this branch, update it instead: read the current
   body with `npx -y gh-axi pr view <N> --full`, pipe through
   `sapa-section pr-description`, and `pr edit --body-file` only if the status is
   `created`/`updated`. If `locked`/`locked-edited`, leave the body alone.
5. Report the PR URL.

## Step 4 — Reconcile the plan

If what shipped diverged from the plan on the issue, refresh the plan comment by
running `/sapa-plan` step 4's flow verbatim — find (or create) the `sapa:plan`
comment, build it through `sapa-section plan`, and post or patch it in place. If
that comment is `locked`/`locked-edited`, the user owns it — leave it and note
the divergence in the ship summary. Never touch the issue body.

## Step 5 — Hand off to watch

Unless the user asked to ship only, begin watching now by invoking the
**sapa-watch** skill for this PR. That is the fused default: shipping flows
straight into watching with no second command from the user.
