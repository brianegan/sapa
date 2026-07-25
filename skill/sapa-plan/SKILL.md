---
name: sapa-plan
description: Read a stream's issue (GitHub or Jira), agree a plan, and record it on the issue as a durable comment, then stop. Use at the start of a stream, or when the user says "plan this", "sapa plan", or "/sapa-plan". For the whole flow (plan, build, gate, submit, watch) use /sapa-flow.
---

# sapa-plan

Turn the stream's issue into an agreed plan — and the decisions and discussion
behind it — recorded on the issue as a dedicated comment so both are durable and
visible rather than trapped in this session.

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
   `/grilling`); if there is no config or no `plan:` key, discuss the
   approach here. Either way keep the plan about intent and decisions, not
   file-by-file code, and always continue to step 4 — recording it on the issue
   is sapa's durable value no matter who developed the plan.

   **Before writing the task list, surface the decisions the issue leaves open.**
   A refined issue settles most of the WHAT, but it rarely settles all of it — it
   often leaves a WHAT-level decision open that only surfaces when you work out the
   HOW. "Add rate limiting" without saying per-user or per-IP, sliding or fixed
   window, is a WHAT-gap wearing a HOW-detail costume. Identify those gaps and
   surface them to the developer as questions rather than quietly picking an answer
   and writing it into the plan as if the issue had asked for it — a silent wrong
   assumption flows through the tasks, their acceptance criteria, and the build,
   and per-task verification will not catch it because the plan itself rests on it.
   Distinguish a genuine WHAT-gap, which needs a decision, from a HOW-detail you can
   reasonably choose on your own; only the former gets surfaced, and a settled,
   unambiguous issue produces no questions at all — stay quiet when nothing is open.
   If a configured `plan:` skill is running the discussion, that skill owns this
   surfacing (grilling naturally does it); otherwise ask here. Carry each
   resolution and its rationale into the `## Decisions & Discussions` section in
   step 4.
4. **Record it as an issue comment.** Write the agreed plan to a file under
   `$(sapa tmp)` — this stream's own scratch directory, so parallel streams never
   clobber each other's drafts — then hand it to `sapa issue plan-comment`, which
   finds sapa's comment (by its marker), creates it if absent, and overwrites it if
   present.

   Record one comment with three parts, in order: the **plan intent** (a short
   prose statement of what the change accomplishes and why — the at-a-glance
   target, not file-by-file code), a **`## Tasks`** section (below), and a
   **`## Decisions & Discussions`** section that captures *why* the plan looks the
   way it does — the key choices and their rationale ("chose X over Y because Z")
   plus the notable questions planning surfaced and how they resolved, including
   the WHAT-level decisions step 3 surfaced and the answer each one got. If the
   planning skill ran a discussion (for example grilling), distil its
   questions and answers here. Distil, do not transcribe: the value is the
   reasoning a later reader needs to understand the feature, not a verbatim log.
   This section is what makes the recorded plan explain itself once the session is
   gone.

   The **`## Tasks`** section is a numbered list of independently-verifiable units
   of work, sitting between the intent and `Decisions & Discussions`. Each task is a
   bold title line saying what it touches and what it should do, followed by one
   `Done when:` line stating its acceptance criterion as a checkable observation —
   the task's red-green target and the requirement a spec review can cite against a
   named task rather than infer from prose. Keep the task the unit of verification:
   `sapa-build` implements and verifies one task before starting the next, so each
   task should be something you can reach green on its own. Always include the
   section, even when the work is a single task — a one-task plan is a one-item
   list, not a reason to drop the heading. Never pad the list to reach an imagined
   minimum: the work decides the count, one task upward.

   **Style the free prose before recording.** Run `sapa config -p` and look for a
   `writing_style:` key. If it names a skill, run that skill over the drafted free
   prose — the intent statement and the `Decisions & Discussions` bullets — as a
   final pass before you encode and record, so the plan reads in the repo's chosen
   voice. Leave the `## Tasks` section untouched: its titles are terse by design
   and its `Done when:` lines are the checkable targets `sapa-build` and spec
   review cite, so a rewrite must not soften them. If there is no `writing_style:`
   key, record the prose as drafted. Invoke the skill the normal way (for example
   `/humanizer`); if it cannot be model-invoked, read its `SKILL.md` and apply its
   guidance by hand.

   The content format depends on the backend, because GitHub renders markdown and
   Jira renders ADF:

   - **GitHub** — write the plan as markdown with the three parts in order: intent
     prose, `## Tasks`, then `## Decisions & Discussions`:

     ```
     One or two sentences on what this change accomplishes and why.

     ## Tasks

     1. **What this task touches and does** — a sentence of detail if it needs one.
        - *Done when:* the checkable observation that proves this task is complete.

     ## Decisions & Discussions

     - Chose X over Y because Z.
     ```

     Then hand it to the helper:

     ```
     printf '%s' "$PLAN_MARKDOWN" > "$(sapa tmp)/plan.md"
     sapa issue plan-comment --content-file "$(sapa tmp)/plan.md"
     ```

   - **Jira** — write the plan as an ADF document (JSON). acli renders ADF, not
     markdown, so a markdown body would show its literal `#`/`-`. Emit a valid
     `{"type":"doc","version":1,"content":[…]}` object using `heading`,
     `paragraph`, `bulletList`/`orderedList` (each `listItem` wrapping a
     `paragraph`), and `codeBlock` nodes, with `strong`/`em` marks for emphasis.
     Use the same three parts: an intent paragraph, a `Tasks` heading over an
     `orderedList` (each task's `Done when:` label carried as a `strong` mark), then
     a `Decisions & Discussions` heading and its bullets:

     ```
     cat > "$(sapa tmp)/plan.adf.json" <<'JSON'
     {"type":"doc","version":1,"content":[
       {"type":"heading","attrs":{"level":2},"content":[{"type":"text","text":"Goal"}]},
       {"type":"paragraph","content":[{"type":"text","text":"What this change accomplishes and why."}]},
       {"type":"heading","attrs":{"level":2},"content":[{"type":"text","text":"Tasks"}]},
       {"type":"orderedList","content":[
         {"type":"listItem","content":[
           {"type":"paragraph","content":[{"type":"text","text":"What this task touches and does."}]},
           {"type":"paragraph","content":[{"type":"text","text":"Done when: ","marks":[{"type":"strong"}]},{"type":"text","text":"the checkable observation that proves it complete."}]}
         ]}
       ]},
       {"type":"heading","attrs":{"level":2},"content":[{"type":"text","text":"Decisions & Discussions"}]},
       {"type":"bulletList","content":[
         {"type":"listItem","content":[{"type":"paragraph","content":[{"type":"text","text":"Chose … over … because …"}]}]}
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
