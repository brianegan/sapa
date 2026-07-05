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
2. Compose the PR content. Keep it consistent — the title and body follow a
   fixed shape so every sapa PR reads the same way.

   **Title** — Conventional Commits: `<type>: <imperative summary>`, where `type`
   is one of `feat`, `fix`, `docs`, `refactor`, `test`, `chore`. No trailing
   period, no issue number (`Closes #<N>` links it), ~70 characters at most. This
   becomes the squash-merge commit title, so write it as the changelog line for
   the work.

   **Body** — an execution summary of what shipped, never a repeat of the plan
   (the plan lives on the issue). Three sections, in this order:

   - `## Summary` — 1-3 sentences: what changed and why.
   - `## Changes` — a short bullet list of the notable changes. Omit the whole
     section for a trivial change the summary already covers.
   - `## Testing` — how it was verified: name the gate steps that ran (from the
     config, e.g. review + tests) and any manual checks.

3. Build the PR body in a managed section so it is protected from the start.
   Write the composed `## Summary` / `## Changes` / `## Testing` markdown to
   `/tmp/sapa-pr.md`, then wrap it:

   ```
   printf '' | sapa-section pr-description --content-file /tmp/sapa-pr.md > /tmp/sapa-pr-body.md
   ```

   Append `\n\nCloses #<N>` so the PR links its issue. It sits outside the
   managed block on purpose, so it survives even after a human locks the body.
4. Open it in the configured state, using the Conventional Commits title
   composed above. When `pr` is `draft` (the default):

   ```
   gh pr create --draft --base <base> --title "<title>" --body-file /tmp/sapa-pr-body.md
   ```

   When `pr` is `ready`, run the same command without `--draft`. Either command
   prints the new PR URL to stdout — note it for the ship summary in Step 4
   (Summarize).

   If a PR already exists for this branch, update it instead. Read the current
   body untruncated, then run it through `sapa-section`:

   ```
   gh pr view <N> --json body --jq .body > /tmp/sapa-pr-existing.md
   ```

   Guard first: the read is damaged only if a wrapper opening line —
   `<!-- sapa:pr-description hash=… -->` or `<!-- sapa:pr-description locked -->`
   alone on its own line, as `sapa-section` emits it — appears without its matching
   `<!-- /sapa:pr-description -->` closing line. A marker quoted inline in prose (in
   backticks, whatever its shape) is not a wrapper line and does not count; a PR
   body may mention the marker, so match the emitted line, not the string. If
   damaged, stop and report; do not edit, or you would append a duplicate section.
   Otherwise pipe through
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
