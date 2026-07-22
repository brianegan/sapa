---
name: sapa-plan
description: Read a stream's issue (GitHub or Jira), agree a plan, and record it on the issue as a durable comment, then stop. Use at the start of a stream, or when the user says "plan this", "sapa plan", or "/sapa-plan". For the whole flow (plan, build, gate, submit, watch) use /sapa-flow.
---

# sapa-plan

Turn the stream's issue into an agreed plan, recorded on the issue as a dedicated
comment so it is durable and visible rather than trapped in this session.

Rules (always): the configured remote (default `origin`) is the only remote. The
issue lives on GitHub (through `gh`) or Jira (through `acli`); which one is set by
`tracker:` in the config and is baked into the branch name, so `sapa issue` derives
it — you never choose by hand. The plan lives in its own issue comment, never in the
issue body — leave the body byte-for-byte as the author wrote it. The comment is
recorded with `sapa issue plan-comment`, which finds sapa's own comment by a marker
and overwrites it; it is not edit-locked, so it always reflects the latest plan.

## Steps

First, mark the stream's stage for the window switcher: run `sapa status --stage
plan` (best-effort — it no-ops outside a sapa stream and never needs your input).

1. **Find the issue.** `sapa issue key` prints the identity for this branch — a
   GitHub number (`42`) or a Jira key (`GP-1`). Use the value the user gave if they
   named one, else this.
2. **Read it.** Read `tracker` from `sapa config -p` (default `github`):
   - GitHub: `gh issue view <N>`.
   - Jira: `acli jira workitem view <KEY>` (the plain view renders the description
     as readable text).
3. **Plan with the user.** Check the config for a planning skill: run
   `sapa config -p` and look for a `plan:` key. If it names a skill, invoke that
   skill to run the discussion (for example wingspan `/plan` or
   `/grill-with-docs`); if there is no config or no `plan:` key, discuss the
   approach here. Either way keep the plan about intent and decisions, not
   file-by-file code, and always continue to step 4 — recording it on the issue
   is sapa's durable value no matter who developed the plan.
4. **Record it as an issue comment.** Write the agreed plan to a file under
   `$(sapa tmp)` — this stream's own scratch directory, so parallel streams never
   clobber each other's drafts — then hand it to `sapa issue plan-comment`, which
   finds sapa's comment (by its marker), creates it if absent, and overwrites it if
   present. The content format depends on the backend, because GitHub renders
   markdown and Jira renders ADF:

   - **GitHub** — write the plan as markdown:

     ```
     printf '%s' "$PLAN_MARKDOWN" > "$(sapa tmp)/plan.md"
     sapa issue plan-comment --content-file "$(sapa tmp)/plan.md"
     ```

   - **Jira** — write the plan as an ADF document (JSON). acli renders ADF, not
     markdown, so a markdown body would show its literal `#`/`-`. Emit a valid
     `{"type":"doc","version":1,"content":[…]}` object using `heading`,
     `paragraph`, `bulletList`/`orderedList` (each `listItem` wrapping a
     `paragraph`), and `codeBlock` nodes, with `strong`/`em` marks for emphasis:

     ```
     cat > "$(sapa tmp)/plan.adf.json" <<'JSON'
     {"type":"doc","version":1,"content":[
       {"type":"heading","attrs":{"level":2},"content":[{"type":"text","text":"Goal"}]},
       {"type":"paragraph","content":[{"type":"text","text":"…"}]},
       {"type":"bulletList","content":[
         {"type":"listItem","content":[{"type":"paragraph","content":[{"type":"text","text":"…"}]}]}
       ]}
     ]}
     JSON
     sapa issue plan-comment --content-file "$(sapa tmp)/plan.adf.json"
     ```

   The helper prints `created` or `updated` on stderr and injects the identity
   marker itself, so you do not add one. It never touches the issue body. Report
   where the plan landed and stop.

Once the plan comment is recorded, this skill is done: the plan is captured and
durable. Building it is `/sapa-build`, and `/sapa-flow` runs the whole sequence
(plan, build, gate, submit, watch) when the developer wants it all in one.
