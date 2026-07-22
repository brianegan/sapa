---
name: sapa-build
description: Implement a stream's recorded plan — read the plan comment from the issue and write the code and tests it calls for in the working tree. Use once the plan is recorded and it's time to code, or when the user says "build this", "implement the plan", "sapa build", or "/sapa-build".
---

# sapa-build

Turn the plan recorded on the issue into working code. The plan comment is the
source of truth, so this can pick up a stream from a fresh session: read the plan,
implement it, stop. It does not push or open a PR — that is `/sapa-gate` then
`/sapa-submit`.

Rules (always): the configured remote (default `origin`) is the only remote; the
issue lives on GitHub (via `gh`) or Jira (via `acli`), resolved by `sapa issue`
from the branch; read the plan from its issue comment, never re-derive it from the
issue body.

## Steps

First, mark the stream's stage for the window switcher: run `sapa status --stage
build` (best-effort — it no-ops outside a sapa stream and never needs your input).

1. **Read the recorded plan.** `sapa issue plan-comment --read` finds sapa's plan
   comment on this stream's issue (GitHub or Jira) and prints its body:

   ```
   sapa issue plan-comment --read > "$(sapa tmp)/plan.md"
   ```

   `$(sapa tmp)` is this stream's own scratch directory, so a parallel stream's
   plan can't land in the file you read back. The command exits non-zero (nothing
   printed) when no plan comment has been recorded yet — if so, stop and say the
   plan has not been recorded (run `/sapa-plan` first).
2. **Require a task list.** The recorded plan carries a `## Tasks` section — a
   numbered list of independently-verifiable units, each with a `Done when:`
   acceptance criterion (recorded by `/sapa-plan`). If the plan you read has no
   `## Tasks` section, stop and say so: the plan predates the task format or came
   from elsewhere, and it needs re-recording with `/sapa-plan` before build. Do not
   fall back to a single-pass build — the task list is the build contract.
3. **Implement one task at a time.** A recorded plan is an accepted plan, so build
   what the comment says — but work through the tasks in order, not all at once.
   For each task: implement what it calls for in this working tree, then verify it
   against its `Done when:` criterion before starting the next. Verifying means a
   passing test when the task is code — write the test and reach green — and the
   most direct check that the criterion holds when it is not (the file now says X,
   the command now behaves Y). A verified task is a durable checkpoint, so when
   something breaks after several tasks the failure localizes to the task just
   finished rather than the whole branch. This stays a single-session build: no
   subagents, no per-task dispatch — just the cadence of reaching green on each
   task before moving to the next. When every task is verified, stop; `/sapa-gate`
   runs the checks next.
