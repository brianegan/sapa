---
name: sapa-plan
description: Read a stream's GitHub issue, agree a plan, and record it on the issue as a durable comment, then stop. Use at the start of a stream, or when the user says "plan this", "sapa plan", or "/sapa-plan". For the whole flow (plan, build, gate, submit, watch) use /sapa-flow.
---

# sapa-plan

Turn a GitHub issue into an agreed plan, recorded on the issue as a dedicated
comment so it is durable and visible rather than trapped in this session.

Rules (always): the configured remote (default `origin`) is the only remote;
GitHub goes through `gh`; the plan lives in its own issue comment, never in the
issue body —
leave the body byte-for-byte as the author wrote it. The comment is written with
`sapa section`, which refuses to overwrite a comment a human has edited or
locked.

## Steps

First, mark the stream's stage for the window switcher: run `sapa status --stage
plan` (best-effort — it no-ops outside a sapa stream and never needs your input).

1. **Find the issue.** Use the number the user gave, else derive it from the
   branch name (a leading number like `42-add-widget` → 42), else ask.
2. **Read it.** `gh issue view <N>`.
3. **Plan with the user.** Check the config for a planning skill: run
   `sapa config -p` and look for a `plan:` key. If it names a skill, invoke that
   skill to run the discussion (for example wingspan `/plan` or
   `/grill-with-docs`); if there is no config or no `plan:` key, discuss the
   approach here. Either way keep the plan about intent and decisions, not
   file-by-file code, and always continue to step 4 — recording it on the issue
   is sapa's durable value no matter who developed the plan.
4. **Record it as an issue comment.** The plan goes in its own comment carrying
   the `sapa:plan` markers, never in the issue body.

   Write the agreed plan, then find any existing sapa plan comment. Scratch files
   go under `$(sapa tmp)`, this stream's own directory, so parallel streams never
   clobber each other's drafts; the path is stable across commands, so you can
   reuse `$(sapa tmp)/…` in each. `gh api` returns the id directly and reads
   bodies in full:

   ```
   printf '%s' "$PLAN_MARKDOWN" > "$(sapa tmp)/plan.md"
   gh api /repos/{owner}/{repo}/issues/<N>/comments --paginate \
     --jq '.[] | select(.body | contains("<!-- sapa:plan")) | .id'
   ```

   That prints the `id` of the sapa plan comment, or nothing if there is none.

   - **No sapa plan comment yet** — build the comment body from an empty base and
     post it (stderr status is `created`):

     ```
     printf '' | sapa section plan --content-file "$(sapa tmp)/plan.md" > "$(sapa tmp)/comment.md"
     gh issue comment <N> --body-file "$(sapa tmp)/comment.md"
     ```

   - **A sapa plan comment exists** — fetch its current body untruncated, then
     feed it through `sapa section` so the hash protection applies:

     ```
     gh api /repos/{owner}/{repo}/issues/comments/<id> --jq .body > "$(sapa tmp)/existing.md"
     sapa section plan --content-file "$(sapa tmp)/plan.md" --body-file "$(sapa tmp)/existing.md" > "$(sapa tmp)/comment.md"
     ```

     `sapa section` exits non-zero (status 3, nothing on stdout) if that body is
     damaged — a truncated read that kept an opening marker but lost its close,
     which patching would turn into a duplicate section. If it errors, stop and
     report; re-read the body in full rather than patch. Otherwise:

     If `updated`, patch that same comment in place — do not post a new one.
     `-F body=@file` sends the body from the file, avoiding shell-escaping and
     argument-length pitfalls:

     ```
     gh api --method PATCH /repos/{owner}/{repo}/issues/comments/<id> \
       -F body=@"$(sapa tmp)/comment.md"
     ```

     If `locked` or `locked-edited`, the user has taken over the comment — leave
     it unchanged (do not patch) and say so. The plan is still recorded either
     way; report where it landed and stop.

   Never run `issue edit`; the issue body stays exactly as the author wrote it.

Once the plan comment is recorded, this skill is done: the plan is captured and
durable. Building it is `/sapa-build`, and `/sapa-flow` runs the whole sequence
(plan, build, gate, submit, watch) when the developer wants it all in one.
