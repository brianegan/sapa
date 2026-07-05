---
name: sapa-flow
description: Run a stream end to end from its GitHub issue — plan, build, gate, submit, and watch — by invoking each phase skill in turn. Use at the start of a stream, or when the user says "flow this", "sapa flow", "/sapa-flow", or "take this issue to a PR".
---

# sapa-flow

Drive one stream from its issue all the way to a merged PR by invoking the five
phase skills in order. This skill holds no logic of its own — each phase lives in
its own skill and can be run alone. `sapa-flow` is just the fused default that
chains them, so a single command carries a stream from issue through plan, build,
PR, and watch with no second command from the developer.

## Steps

Invoke each phase in turn and honor its result. If a phase stops or escalates — a
`locked`/`locked-edited` plan comment, a failing gate, a rebase conflict — stop
there rather than papering over it. Do not re-implement any phase's work here;
call the skill.

1. **Plan** — invoke `/sapa-plan`. It agrees the plan with the developer and
   records it on the issue, then stops.
2. **Build** — invoke `/sapa-build`. It reads the recorded plan and implements
   the code and tests in the working tree.
3. **Gate** — invoke `/sapa-gate`. It rebases onto the base and runs the quality
   gate. If the gate does not go green, stop.
4. **Submit** — on a green gate, invoke `/sapa-submit`. It pushes and opens (or
   updates) the PR and reconciles the plan on the issue.
5. **Watch** — invoke `/sapa-watch`. It monitors the PR and tears the stream down
   when it merges.
