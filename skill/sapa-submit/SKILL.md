---
name: sapa-submit
description: Push a green stream and open (or update) its PR — a managed body that links its issue, draft or ready per config — then reconcile the plan on the issue. Use once the gate is green, or when the user says "submit it", "ship it", "open the PR", "sapa submit", or "/sapa-submit".
---

# sapa-submit

Push the branch to the configured remote and open (or update) its PR, then
reconcile the plan comment on the issue. Assumes the branch is already green and
rebased onto the base — run `/sapa-gate` first, or let `/sapa-flow` do it. Does
not gate — that is `/sapa-gate`.

Rules (always): the configured remote (default `origin`) is the only remote;
GitHub goes through `gh`, Jira through `acli`; the PR always lives on GitHub. The
PR body is managed with `sapa section` and never clobbers human text; the issue
plan is recorded with `sapa issue plan-comment` (which is not edit-locked).

Before anything else, record the stream's stage: run `sapa status --stage submit`
(best-effort — it no-ops outside a sapa stream). It is how `/sapa-flow` resumes a
stream at the phase it left off in.

## Step 1 — Locate the config

Run `sapa config -p` and read these top-level keys (all optional):

- `base:` — the branch the PR targets (default `main`).
- `remote:` — the single remote to push to (default `origin`).
- `pr:` — `draft` or `ready`, the state to open the PR in (default `draft`).
- `tracker:` — `github` (default) or `jira`, the issue backend the link targets.
- `jira.site:` — the Jira site host, used only to build the issue link on the
  Jira path (e.g. `verygood-ventures.atlassian.net`).
- `writing_style:` — a skill that shapes the PR body's free prose as a final pass
  before it is written (default none). Absent, the body is written as composed.

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
   (the plan lives on the issue). Four sections, in this order:

   - `## Summary` — 1-3 sentences: what changed and why.
   - `## Changes` — a short bullet list of the notable changes. Omit the whole
     section for a trivial change the summary already covers.
   - `## Testing` — answer one question from the reviewer's chair: *if I were
     testing this change, what is the best way?* Write what earns them
     confidence, and let it scale to the change — force no ceremony. For a
     mechanical change (a rename, a pure refactor) that is simply "the tests pass
     and the lights are green"; say that rather than invent steps. For a
     human-perceived change (an animation, a layout or copy tweak) guide them to
     the thing — how to navigate to it and what to look for. When it is best
     exercised with capability the reviewer has on their machine (integration
     tests behind their own keys), point them at running those. This is not a
     recap of the gate sapa already ran — that record is `## Gates`.
   - `## Gates` — the automated record, the recap `## Testing` deliberately leaves
     out. You do not write this section: `sapa gate --report` prints it from the
     record the gate wrote, and Step 3 appends it verbatim. Do not compose it, do
     not summarize it, and do not reconcile it against the config if the two seem
     to disagree — the config says what the gate would run and the record says what
     it did, and where they differ the record is the one worth publishing. If it
     reports no record, or a head that has moved, leave that in and say so in the
     ship summary.

3. Build the PR body in a managed section so it is protected from the start.
   First, if `writing_style:` in the config names a skill, run it over the free
   prose as a final pass — the `## Summary`, `## Changes`, and `## Testing`
   sections — leaving the Conventional Commits title untouched, since it is a
   structured line rather than prose. Invoke the skill the normal way (for example
   `/humanizer`); if it cannot be model-invoked, read its `SKILL.md` and apply its
   guidance by hand. Absent the key, keep the composed prose as is.

   Write the resulting `## Summary` / `## Changes` / `## Testing` markdown to
   `$(sapa tmp)/pr.md` — this stream's own scratch directory, so parallel streams
   don't clobber each other, and the path is stable across the commands below — then
   append the gate record's own account of what ran and wrap the result:

   ```
   { printf '\n'; sapa gate --report; } >> "$(sapa tmp)/pr.md"
   printf '' | sapa section pr-description --content-file "$(sapa tmp)/pr.md" > "$(sapa tmp)/pr-body.md"
   ```

   The blank line is load-bearing: markdown needs one before a heading, and without
   it `## Gates` renders as the tail of your last `## Testing` sentence.

   `sapa gate --report` renders `## Gates` from the record `sapa gate` wrote while
   it walked: the steps that actually ran, their results, the commit it gated, and
   whether any step was given the recorded plan as its spec source. It always
   succeeds and always prints a section, so the append needs no guard. Run it after
   the `writing_style:` pass and never through it — the section is a mechanical
   record, and a rewrite would turn evidence back into an assertion, which is the
   whole reason it is not composed here.

   Append the issue link after the managed block — outside it on purpose, so it
   survives even after a human locks the body. `sapa issue key` prints the
   identity. On GitHub append `\n\nCloses #<N>` (it links and auto-closes on
   merge). On Jira append `\n\nJira: https://<site>/browse/<KEY>` using
   `jira.site` from the config — Jira has no PR-driven auto-close, and the key in
   the branch name already back-links the PR on the issue's dev panel.
4. Open it in the configured state, using the Conventional Commits title
   composed above. When `pr` is `draft` (the default):

   ```
   gh pr create --draft --base <base> --title "<title>" --body-file "$(sapa tmp)/pr-body.md"
   ```

   When `pr` is `ready`, run the same command without `--draft`. Either command
   prints the new PR URL to stdout — note it for the ship summary in Step 4
   (Summarize).

   If a PR already exists for this branch, update it instead. Read the current
   body untruncated, then run it through `sapa section`:

   ```
   gh pr view <N> --json body --jq .body > "$(sapa tmp)/pr-existing.md"
   sapa section pr-description --content-file "$(sapa tmp)/pr.md" --body-file "$(sapa tmp)/pr-existing.md" > "$(sapa tmp)/pr-body.md"
   ```

   `sapa section` exits non-zero (nothing on stdout) if that body is damaged — a
   truncated read missing its closing marker, which editing would duplicate. If
   it errors, stop and report; re-read the body in full rather than edit.
   Otherwise run `gh pr edit <N> --body-file "$(sapa tmp)/pr-body.md"` only if the
   status is `created`/`updated`. If `locked`/`locked-edited`, leave the body
   alone. Either way, note the URL for the summary with
   `gh pr view <N> --json url --jq .url`.

## Step 3 — Reconcile the plan

If what shipped diverged from the plan on the issue, refresh the plan comment by
re-running `/sapa-plan` step 4 — re-author the plan (markdown for GitHub, ADF for
Jira) and record it with `sapa issue plan-comment`, which overwrites sapa's own
comment in place. Never touch the issue body.

## Step 4 — Summarize

Print a short ship summary that leads with the PR URL on its own line so the
terminal makes it clickable, then one line of key facts:

```
<PR URL>
<title> · <draft|ready> · base <base> · <Closes #<N>  (GitHub)  |  Jira <KEY>>
```

Carry any plan divergence noted in Step 3 into this summary. Carry the gate record
too when it is not clean: if `sapa gate --report` found no record, or reported a
gated commit that is not the current head, say so here in one line. The PR already
says it, and the developer should not have to read their own PR body to find out
the branch went up on the strength of a gate that did not run on it. That
completes the submit phase, and `/sapa-watch` monitors the PR from here. Under
`/sapa-flow`, go straight on to it: an open PR is the hand-off to watch, not a
place to ask whether to keep going.
