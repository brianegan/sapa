---
name: sapa-plan
description: Read a stream's GitHub issue and agree a plan, then record it on the issue. Use at the start of a stream, or when the user says "plan this", "sapa plan", or "/sapa-plan". Does not gate, push, or open a PR.
---

# sapa-plan

Turn a GitHub issue into an agreed plan, recorded on the issue as a dedicated
comment so it is durable and visible rather than trapped in this session.

Rules (always): the configured remote (default `origin`) is the only remote;
GitHub goes through `npx -y gh-axi`, never `gh`; the plan lives in its own issue
comment, never in the issue body —
leave the body byte-for-byte as the author wrote it. The comment is written with
`sapa-section`, which refuses to overwrite a comment a human has edited or
locked.

## Steps

1. **Find the issue.** Use the number the user gave, else derive it from the
   branch name (a leading number like `42-add-widget` → 42), else ask.
2. **Read it.** `npx -y gh-axi issue view <N> --full`.
3. **Plan with the user.** Check the config for a planning skill: run
   `sapa-config -p` and look for a `plan:` key. If it names a skill, invoke that
   skill to run the discussion (for example wingspan `/plan` or
   `/grill-me-with-docs`); if there is no config or no `plan:` key, discuss the
   approach here. Either way keep the plan about intent and decisions, not
   file-by-file code, and always continue to step 4 — recording it on the issue
   is sapa's durable value no matter who developed the plan.
4. **Record it as an issue comment.** The plan goes in its own comment carrying
   the `sapa:plan` markers, never in the issue body.

   Write the agreed plan, then find any existing sapa plan comment:

   ```
   printf '%s' "$PLAN_MARKDOWN" > /tmp/sapa-plan.md
   npx -y gh-axi api /repos/{owner}/{repo}/issues/<N>/comments --paginate
   ```

   Read the output and find the comment whose body contains `<!-- sapa:plan`;
   note its `id`.

   - **No sapa plan comment yet** — build the comment body from an empty base and
     post it (stderr status is `created`):

     ```
     printf '' | sapa-section plan --content-file /tmp/sapa-plan.md > /tmp/sapa-comment.md
     npx -y gh-axi issue comment <N> --body-file /tmp/sapa-comment.md
     ```

   - **A sapa plan comment exists** — fetch that comment and save its current
     body (the API escapes it onto one line, so decode it), then feed it through
     `sapa-section` so the hash protection applies:

     ```
     npx -y gh-axi api /repos/{owner}/{repo}/issues/comments/<id> \
       | python3 -c "import sys,json; ln=[l for l in sys.stdin if l.startswith('body: ')][0]; open('/tmp/sapa-existing.md','w').write(json.loads(ln[6:]))"
     sapa-section plan --content-file /tmp/sapa-plan.md --body-file /tmp/sapa-existing.md > /tmp/sapa-comment.md
     ```

     If `updated`, patch that same comment in place — do not post a new one:

     ```
     npx -y gh-axi api PATCH /repos/{owner}/{repo}/issues/comments/<id> \
       --field body="$(cat /tmp/sapa-comment.md)"
     ```

     If `locked` or `locked-edited`, the user has taken over the comment — leave
     it and say so.

   Never run `issue edit`; the issue body stays exactly as the author wrote it.

Stop here. Gating and shipping are `/sapa-ship`.
