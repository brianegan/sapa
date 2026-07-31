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

First, record the stream's stage: run `sapa status --stage build` (best-effort —
it no-ops outside a sapa stream and never needs your input). It is how
`/sapa-flow` resumes a stream at the phase it left off in.

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
3. **Load the configured build skill.** Run `sapa config -p` and look for a
   `build:` key. If it names a skill, invoke it now — before task 1, so its
   guidance shapes every task that follows (for example `/tdd` to build
   test-first). Invoke it the normal way; if it cannot be model-invoked, read its
   `SKILL.md` and apply its guidance by hand. If there is no config or no `build:`
   key, implement the tasks as step 4 describes and nothing here applies.

   Invoke it once, here, and not again per task: a skill's instructions stay in
   the session once loaded, so a single invocation already covers the whole build.
   It loads after steps 1 and 2 because both of those stop the build outright, and
   there is no sense loading a build skill for a build that will not happen.

   A build skill shapes *how* each task reaches green; it never decides *whether*
   one does. It can tighten sapa's rule — `/tdd` demanding a failing test before
   any implementation is stronger than step 4's "write the test and reach green",
   and that is the point of configuring it — but it cannot loosen it. No skill's
   guidance excuses starting the next task with the current one unverified, and
   none re-scopes, merges, or reorders the recorded tasks, because the plan comment
   is the accepted plan.
4. **Implement one task at a time.** A recorded plan is an accepted plan, so build
   what the comment says — but work through the tasks in order, not all at once.
   For each task: implement what it calls for in this working tree, then verify it
   against its `Done when:` criterion before starting the next. Verifying means a
   passing test when the task is code — write the test and reach green — and the
   most direct check that the criterion holds when it is not (the file now says X,
   the command now behaves Y). A verified task is a durable checkpoint, so when
   something breaks after several tasks the failure localizes to the task just
   finished rather than the whole branch. This stays a single-session build: no
   subagents, no per-task dispatch — just the cadence of reaching green on each
   task before moving to the next.

   Crossing from one task to the next is automatic. The boundaries above say where
   a task ends, not that anything happens there: a verified task is followed
   immediately by the next one, without reporting back and waiting, and without
   asking the developer whether to carry on. Their answer is already in the plan
   comment, which is an accepted plan. Only an escalation stops a build partway —
   a task you cannot reach green, or work the plan does not cover — and that is a
   real block to raise, not a checkpoint to pause at. When every task is verified,
   stop; `/sapa-gate` runs the checks next.
