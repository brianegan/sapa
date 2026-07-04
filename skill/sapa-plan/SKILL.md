---
name: sapa-plan
description: Read a stream's GitHub issue, agree a plan, and record it on the issue, then implement it and hand off to /sapa-submit. Use at the start of a stream, or when the user says "plan this", "sapa plan", or "/sapa-plan". Pass --plan-only to record the plan and stop without starting the work.
---

# sapa-plan

Turn a GitHub issue into an agreed plan, recorded on the issue as a dedicated
comment so it is durable and visible rather than trapped in this session.

Rules (always): the configured remote (default `origin`) is the only remote;
GitHub goes through `gh`; the plan lives in its own issue comment, never in the
issue body —
leave the body byte-for-byte as the author wrote it. The comment is written with
`sapa-section`, which refuses to overwrite a comment a human has edited or
locked.

## Steps

1. **Find the issue.** Use the number the user gave, else derive it from the
   branch name (a leading number like `42-add-widget` → 42), else ask.
2. **Read it.** `gh issue view <N>`.
3. **Plan with the user.** Check the config for a planning skill: run
   `sapa-config -p` and look for a `plan:` key. If it names a skill, invoke that
   skill to run the discussion (for example wingspan `/plan` or
   `/grill-with-docs`); if there is no config or no `plan:` key, discuss the
   approach here. Either way keep the plan about intent and decisions, not
   file-by-file code, and always continue to step 4 — recording it on the issue
   is sapa's durable value no matter who developed the plan.
4. **Record it as an issue comment.** The plan goes in its own comment carrying
   the `sapa:plan` markers, never in the issue body.

   Write the agreed plan, then find any existing sapa plan comment. `gh api`
   returns the id directly and reads bodies in full:

   ```
   printf '%s' "$PLAN_MARKDOWN" > /tmp/sapa-plan.md
   gh api /repos/{owner}/{repo}/issues/<N>/comments --paginate \
     --jq '.[] | select(.body | contains("<!-- sapa:plan")) | .id'
   ```

   That prints the `id` of the sapa plan comment, or nothing if there is none.

   - **No sapa plan comment yet** — build the comment body from an empty base and
     post it (stderr status is `created`):

     ```
     printf '' | sapa-section plan --content-file /tmp/sapa-plan.md > /tmp/sapa-comment.md
     gh issue comment <N> --body-file /tmp/sapa-comment.md
     ```

   - **A sapa plan comment exists** — fetch its current body untruncated, then
     feed it through `sapa-section` so the hash protection applies:

     ```
     gh api /repos/{owner}/{repo}/issues/comments/<id> --jq .body > /tmp/sapa-existing.md
     ```

     Guard before touching it: if `/tmp/sapa-existing.md` contains an opening
     `<!-- sapa:plan` marker but no closing `<!-- /sapa:plan -->`, the read came
     back damaged — stop, report it, and do not run `sapa-section` or patch;
     patching now would append a duplicate section. Otherwise continue:

     ```
     sapa-section plan --content-file /tmp/sapa-plan.md --body-file /tmp/sapa-existing.md > /tmp/sapa-comment.md
     ```

     If `updated`, patch that same comment in place — do not post a new one.
     `-F body=@file` sends the body from the file, avoiding shell-escaping and
     argument-length pitfalls:

     ```
     gh api --method PATCH /repos/{owner}/{repo}/issues/comments/<id> \
       -F body=@/tmp/sapa-comment.md
     ```

     If `locked` or `locked-edited`, the user has taken over the comment — leave
     it unchanged (do not patch) and say so. This is not a stop: the plan is
     still recorded, so carry that comment's current text into Step 5 as the
     accepted plan.

   Never run `issue edit`; the issue body stays exactly as the author wrote it.

## Step 5 — Start the work

Once the plan comment is recorded, begin the work in this working tree —
implement the agreed plan, writing the code and tests it calls for — then invoke
**`/sapa-submit`**, which rebases onto the base, gates, opens the draft PR, and
hands off to watch. This is the fused default: planning flows straight into
building and shipping with no second command from the developer, the same way
submitting flows straight into watching. A recorded plan is an accepted plan,
whether `sapa-section` reported `created`, `updated`, or a `locked`/`locked-edited`
comment the developer already owns. When it is `locked`/`locked-edited`, the
developer's version in the comment is authoritative — implement what the comment
says, not an earlier draft.

Skip this step — record the plan and stop — when either:

- the skill was invoked with `--plan-only`, or
- the config sets `plan_auto_start: false` (read it from the `sapa-config -p`
  output, the same output Step 3 reads for the `plan:` key).

`--plan-only` always wins for a single run regardless of config. When you skip,
say plainly that the plan is recorded and the work was not started, and that
`/sapa-submit` will pick it up when the developer is ready.
