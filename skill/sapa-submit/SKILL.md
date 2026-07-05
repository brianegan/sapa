---
name: sapa-submit
description: Push a green stream and open (or update) its PR — a managed body with Closes #N, draft or ready per config — then reconcile the plan on the issue. Use once the gate is green, or when the user says "submit it", "ship it", "open the PR", "sapa submit", or "/sapa-submit".
---

# sapa-submit

Push the branch to the configured remote and open (or update) its PR, then
reconcile the plan comment on the issue. Assumes the branch is already green and
rebased onto the base — run `/sapa-gate` first, or let `/sapa-flow` do it. Does
not gate — that is `/sapa-gate`.

Rules (always): the configured remote (default `origin`) is the only remote — its
name is configurable but there is never a second one; GitHub goes through `gh`;
never clobber human text (the PR body and issue plan are written with
`sapa-section`).

## Step 1 — Locate the config

Run `sapa-config -p` and read these top-level keys (all optional):

- `base:` — the branch the PR targets (default `main`).
- `remote:` — the single remote to push to (default `origin`).
- `pr:` — `draft` or `ready`, the state to open the PR in (default `draft`).

## Step 2 — Ship

1. Push to the configured remote only: `git push -u <remote> HEAD` (add
   `--force-with-lease` if the gate's rebase rewrote already-pushed history).
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

   When `pr` is `ready`, run the same command without `--draft`. Either command
   prints the new PR URL to stdout — note it for the ship summary in Step 4.

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
   `locked`/`locked-edited`, leave the body alone. Either way, note the URL for
   the summary with `gh pr view <N> --json url --jq .url`.

## Step 3 — Reconcile the plan

If what shipped diverged from the plan on the issue, refresh the plan comment by
running `/sapa-plan` step 4's flow verbatim — find (or create) the `sapa:plan`
comment, build it through `sapa-section plan`, and post or patch it in place. If
that comment is `locked`/`locked-edited`, the user owns it — leave it and note
the divergence in the ship summary. Never touch the issue body.

## Step 4 — Summarize

Print a short ship summary that leads with the PR URL on its own line so the
terminal makes it clickable, then one line of key facts:

```
<PR URL>
<title> · <draft|ready> · base <base> · Closes #<N>
```

Carry any plan divergence noted in Step 3 into this summary, then stop.
`/sapa-watch` monitors the PR from here.
