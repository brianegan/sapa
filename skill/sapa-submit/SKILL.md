---
name: sapa-submit
description: Rebase onto the base, gate a stream in the working tree, and ship it as a PR (draft by default), then start watching it. Use when work is ready to go up, or the user says "submit it", "sapa submit", or "/sapa-submit". Pass --gate-only to run the checks without pushing.
---

# sapa-submit

Rebase onto the latest base, run the quality gate in the working tree, then push
to the configured remote and open the PR. On success, hand off to watching. Does
not plan — that is `/sapa-plan`.

Rebasing before the gate means a green gate reflects what will actually merge: no
false green against a stale base, and no branch-protection "must be up to date"
surprise at merge time.

Rules (always): the configured remote (default `origin`) is the only remote —
its name is configurable but there is never a second one; GitHub goes through
`gh`; never clobber human text (the PR body is written with `sapa-section`).

## Step 1 — Locate the config

Run `sapa-config -p` to print the discovered `.sapa.yaml` (it walks up from the
current directory the way `sapa-worktree` finds `.bare`). If none is found, ask
whether to use a sensible default gate (test + format) or stop.

Read these top-level keys (all optional):

- `base:` — the branch the PR targets (default `main`).
- `remote:` — the single remote to push to (default `origin`).
- `pr:` — `draft` or `ready`, the state to open the PR in (default `draft`).
- `gate_only_rebase:` — whether `--gate-only` also rebases onto the base (default
  `false`; see Step 2). A full submit always rebases regardless.
- `gate:` — the ordered list of gate steps below.

Each gate step has a `name` and either:

- `run:` — a shell command, run verbatim in the working tree. It may carry a
  version-manager prefix such as `fvm flutter test`.
- `skill:` — a skill to invoke for that step (for example a review skill). Treat
  its findings as the step result.

## Step 2 — Rebase onto the base

Bring the branch up to date with the base so the gate runs against what will
merge.

- On a full submit: always do this.
- With `--gate-only`: only if `gate_only_rebase: true` in the config; otherwise
  skip straight to Step 3 so a quick WIP check never moves the branch.

Steps:

1. Commit any uncommitted work with a clear message first, so the tree is clean
   for the rebase.
2. `git fetch <remote>`, then `git rebase <remote>/<base>` using `remote` and
   `base` from the config.
3. Already up to date → no-op, continue.
4. **Conflict → stop.** Run `git rebase --abort`, report the conflict as a
   finding, and let the user resolve it before rerunning `/sapa-submit`. Never
   auto-resolve a rebase conflict — it is a judgement call.

## Step 3 — Run the gate (blocking)

Run each gate step in order, in the working tree. This blocks.

- All steps pass → continue.
- A step fails → **stop**. Report the failing step and its output as a finding.
  Apply a safe, mechanical fix and rerun from the top; if it is a judgement call,
  ask. Do not ship until green. The user may interrupt to change something and
  rerun `/sapa-submit`.

If invoked with `--gate-only`, stop here after reporting the result. Do not push.

## Step 4 — Ship

1. Push to the configured remote only: `git push -u <remote> HEAD` (add
   `--force-with-lease` if the rebase rewrote already-pushed history).
2. Build the PR body in a managed section so it is protected from the start:

   ```
   printf '%s' "$PR_SUMMARY" > /tmp/sapa-pr.md
   printf '' | sapa-section pr-description --content-file /tmp/sapa-pr.md > /tmp/sapa-pr-body.md
   ```

   Append `\n\nCloses #<N>` so the PR links its issue. Do not repeat the plan;
   the plan lives on the issue.
3. Open it in the configured state. When `pr` is `draft` (the default):

   ```
   gh pr create --draft --base <base> --title "<title>" --body-file /tmp/sapa-pr-body.md
   ```

   When `pr` is `ready`, run the same command without `--draft`.

   If a PR already exists for this branch, update it instead. Read the current
   body untruncated, then run it through `sapa-section`:

   ```
   gh pr view <N> --json body --jq .body > /tmp/sapa-pr-existing.md
   ```

   Guard first: if `/tmp/sapa-pr-existing.md` has an opening
   `<!-- sapa:pr-description` marker but no closing `<!-- /sapa:pr-description -->`,
   the read is damaged — stop and report; do not edit, or you would append a
   duplicate section. Otherwise pipe through
   `sapa-section pr-description --body-file /tmp/sapa-pr-existing.md` and
   `gh pr edit <N> --body-file` only if the status is `created`/`updated`. If
   `locked`/`locked-edited`, leave the body alone.
4. Report the PR URL.

## Step 5 — Reconcile the plan

If what shipped diverged from the plan on the issue, refresh the plan comment by
running `/sapa-plan` step 4's flow verbatim — find (or create) the `sapa:plan`
comment, build it through `sapa-section plan`, and post or patch it in place. If
that comment is `locked`/`locked-edited`, the user owns it — leave it and note
the divergence in the ship summary. Never touch the issue body.

## Step 6 — Hand off to watch

Unless the user asked to gate only, begin watching now by invoking the
**sapa-watch** skill for this PR. That is the fused default: submitting flows
straight into watching with no second command from the user.
