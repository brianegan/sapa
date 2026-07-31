---
name: sapa-flow
description: Carry a stream forward from wherever it stands — plan, build, gate, submit, and watch — by invoking each phase skill in turn, resuming at the phase it left off in. Use at the start of a stream or to pick one back up, or when the user says "flow this", "sapa flow", "/sapa-flow", or "take this issue to a PR".
---

# sapa-flow

Drive one stream from its issue all the way to a merged PR by invoking the five
phase skills in order. This skill implements none of the phases itself — each
lives in its own skill and can be run alone. What it does own is the movement
between them: where a stream picks up, when to cross from one phase to the next,
and how a developer interruption resumes. So a single command carries a stream
from issue through plan, build, PR, and watch with no second command from the
developer.

## Steps

First, find where this stream picks up. `sapa status --report` prints the stage
recorded for it — `plan`, `build`, `gate`, `submit` or `watch`, matching steps 1
to 5 below — and enters the list there rather than at the top. It prints nothing
for a stream that has never recorded one, or whose file teardown has removed; that
is a fresh stream, so start at step 1.

This is what makes `/sapa-flow` resumable. Every phase records its stage as its
first act, so a stream carries its own position on disk, and re-invoking the flow
after a session ends picks the stream up where it stands instead of re-planning
work that is already built. The consequence is deliberate: `/sapa-flow` means
"carry this stream forward from wherever it is", not "run all five phases from the
top". A stream someone gated by hand resumes at the gate.

Invoke each phase in turn and honor its result. A phase returning is not the flow
ending: every phase skill finishes by handing control back, and the flow continues
straight to the next step without asking the developer for permission to. Only an
escalation stops the flow — a `locked`/`locked-edited` plan comment, a failing
gate, a rebase conflict — and there, stop rather than papering over it. Do not
re-implement any phase's work here; call the skill.

1. **Plan** — invoke `/sapa-plan`. It agrees the plan with the developer and
   records it on the issue, then returns. Continue to step 2.
2. **Build** — invoke `/sapa-build`. It reads the recorded plan and implements
   the code and tests in the working tree, then returns. Continue to step 3.
3. **Gate** — invoke `/sapa-gate`. It rebases onto the base and runs the quality
   gate. On a green gate, continue to step 4; if it does not go green, that is an
   escalation, so stop.
4. **Submit** — on a green gate, invoke `/sapa-submit`. It pushes and opens (or
   updates) the PR and reconciles the plan on the issue, then returns. Continue to
   step 5.
5. **Watch** — invoke `/sapa-watch`. It monitors the PR and tears the stream down
   when it merges. That teardown ends the flow.

## Interruptions

A flow survives the developer interrupting it. They will report a bug, ask for a
change, or take the session somewhere else mid-stream; that suspends the flow, it
does not end it. Once their requests are handled, re-enter the phase list and
carry on. Do not ask whether to resume — the flow is still running, and the only
things that end it are an escalation or the developer saying so.

An interruption can invalidate a phase that already passed, so before re-entering,
correct the recorded stage to say where the stream now picks up:

- **The working tree changed** — run `sapa status --stage gate`. Any edit made
  after a green gate is un-gated code, and re-entering at `submit` would push work
  no gate ran on.
- **The intended work changed** — run `sapa status --stage plan`. The recorded plan
  no longer describes the change, so it needs re-agreeing before more is built.
  This one is a judgement call; a bug fix inside the agreed scope is a tree change,
  not a new plan.
- **Neither** — leave the stage alone and re-enter where it stands.

Write the corrected stage rather than remembering an exception to it. The status
file is the one record of where this stream resumes, and the entry read at the top
of Steps reads it back every time. A rule that overrode it at read time would put
the answer in two places that can disagree.
