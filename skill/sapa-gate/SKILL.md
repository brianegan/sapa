---
name: sapa-gate
description: Rebase a stream onto its base and run the quality gate in the working tree, certifying the branch is green against what will actually merge. Use to check work before it goes up, or when the user says "gate this", "sapa gate", "/sapa-gate", or "is it green".
---

# sapa-gate

Rebase the branch onto the latest base, then run the quality gate in the working
tree. Rebasing before the gate means a green gate reflects what will actually
merge: no false green against a stale base, and no branch-protection "must be up
to date" surprise at merge time. Does not push or open a PR — that is
`/sapa-submit`.

Rules (always): the configured remote (default `origin`) is the only remote;
GitHub goes through `gh`.

Before anything else, record the stream's stage: run `sapa status --stage gate`
(best-effort — it no-ops outside a sapa stream). It is how `/sapa-flow` resumes a
stream at the phase it left off in.

## Step 1 — Locate the config

Run `sapa gate --list` to print the resolved gate steps. `sapa gate` finds the
`.sapa.yaml` itself (walking up the way `sapa worktree` finds `.bare`) and reads
the keys it needs — `base:` (default `main`), `remote:` (default `origin`), and
the `gate:` map, which holds the ordered `steps:` list and the autofix budget
`max_fix_attempts:` (default 3, covered in Step 3). `sapa config -p` shows the
whole file if you want the other keys too.

Each line is `sapa-gate  list  <name>  run|skill  <command-or-skill>  <model>  <when>`:

- a `run:` step is a shell command the helper runs verbatim. It may carry a
  version-manager prefix such as `fvm flutter test`.
- a `skill:` step is a skill you invoke for that step. Treat its findings as the
  step result.
- `model:` (`-` when absent) names a model, the way the Agent tool's model
  override accepts (`fable`, `opus`, `sonnet`, `haiku`). It is meaningful for
  `skill:` steps; Step 3 says how to honour it. Absent, the step runs on the
  session model.
- `when:` is `always` (the default) or `pre-push`. Every `always` step must come
  before the first `pre-push` step. Pre-push is a point in this gate walk, not a
  Git hook.

Exit 2 means nothing ran, and the message says which of two causes it was.

**Not in a worktree.** `sapa gate` resolves the tree it is gating before it looks
for a config, so a caller outside a work tree is refused rather than gated
somewhere arbitrary. In a `.bare` layout that means the container directory, the
one holding `.bare` and the worktree directories. Move to the worktree you meant
and run again. Do not offer a config here — the config is not the problem.

**Nothing to run.** No config, no `gate:` map, no `gate.steps:`, a malformed
step, or a `max_fix_attempts:` that is not a count. On a missing config, ask
whether to use a sensible default gate (test + format) or stop; on a malformed
one, report it and stop rather than guessing what was meant. A config whose
`gate:` is still the old flat list of steps gets an exit 2 naming the edit that
fixes it: put the list under a `steps:` key. That is a config change for the
developer to make, not one to make for them silently.

## Step 2 — Rebase the branch up to date

Bring the branch up to date so the gate runs against what will merge: first
integrate any work a teammate pushed to this same branch, then rebase onto the
base.

1. Commit any uncommitted work with a clear message first, so the tree is clean
   for the rebase.
2. `git fetch <remote>` using `remote` from the config.
3. **Integrate the branch's own remote head.** A teammate may have pushed to this
   branch while you worked; a later `/sapa-submit` force-push would discard those
   commits. Take the current branch name with `git branch --show-current`. If it
   is empty (detached HEAD) stop and report rather than guessing a branch. If
   `<remote>/<branch>` exists (`git rev-parse --verify --quiet <remote>/<branch>`
   succeeds), rebase onto it — `git rebase <remote>/<branch>` — so the teammate's
   commits land underneath your local work rather than being lost. If the remote
   branch does not exist yet (never pushed), skip this rebase.
4. **Rebase onto the base.** `git rebase <remote>/<base>` using `base` from the
   config.

At each rebase: already up to date → no-op, continue. **On a conflict, resolve
what is unambiguous and escalate the rest.** Inspect the conflict. When the
correct resolution is clear and does not change how anything works — for example
each side added a separate entry, or the two edits overlap textually but are
independent — resolve it, `git add` the files, and `git rebase --continue`. When
the resolution is a judgement call or could change behaviour, do not guess: leave
the rebase stopped at that conflict, report the conflicting hunk as a finding, and
escalate to the user. Resolve it their way, then `git rebase --continue`; do not
certify green until the rebase completes cleanly.

Once the rebase settles, the branch holds the diff the gate runs against. `sapa
gate` computes it and hands it to each `run:` step, so a script can scope to it.

## Step 3 — Run the gate (blocking)

Run `sapa gate`. It walks the configured steps in order in the working tree,
runs each `run:` step with `SAPA_BASE` and `SAPA_CHANGED_FILES` set from the diff
the rebase just settled, and stops the moment something needs you. Always-run
steps come first on every attempt. Once they pass, the helper continues through
the pre-push steps on the same head without rerunning the earlier group. This
blocks.

It emits one tab-separated line per result, each led by `sapa-gate` so a step's
own output can't be mistaken for one:

```
sapa-gate	plan	<absolute-path>	present|absent
sapa-gate	step	<name>	run	<exit>	<seconds>
sapa-gate	step	<name>	skill	pass|fail	-
sapa-gate	needs-skill	<name>	<skill>	<model-or->
sapa-gate	attempts	<spent>	<max>
sapa-gate	done	green
```

As it walks, `sapa gate` writes a record of what ran to the stream's scratch
directory — per step the name, kind, command or skill, model, schedule, result,
duration, and a tail of its output, plus the SHAs the run gated and whether any
step was given the plan as a spec source. `/sapa-submit` publishes a summary of
it to the PR through `sapa gate --report`, so what you report in chat and what a
reviewer sees come from the same place. Nothing here has to maintain the record
by hand; the one thing it needs from you is the outcome of each `skill:` step,
below.

Act on the exit code:

- **0 — `done green`.** Every step passed. Report the branch is green; the gate is
  done and `/sapa-submit` ships it next. A green gate is a result to hand back, not
  a decision to put to the developer, so under `/sapa-flow` submit follows on its
  own.
- **4 — `needs-skill`.** The walk has reached a `skill:` step, which needs this
  harness. Invoke it (below), and when it passes continue the walk with `sapa gate
  --after <name> --result pass --summary "<one line on what it found>"`. Repeat
  until the gate ends on 0 or 1. A skill step whose findings are a genuine failure
  is treated like a failed step: resume with `--result fail` and a summary saying
  why, which records the failure and stops the walk, then report it and fix it the
  same way any finding is fixed, by the class and not the named instance (see
  **Fixing a finding**).

  Report the result honestly. The helper cannot watch a skill step the way it
  watches an exit code, so what you pass here is the only account of that step
  there will ever be, and it goes on the PR labelled as your word rather than as
  something sapa observed. Omitting `--result` counts as a pass, so resuming after
  a step you have not actually judged silently certifies it.

  **Getting `needs-skill` for a step you already handled is not a loop.** It means
  the record was lost (a cleared `TMPDIR`, a resume run by hand) and the helper
  restarted the walk from the top rather than write a record understating what ran.
  Its stderr says so. Run the step again and resume as normal.
- **1 — the last `step` line names the failing step.** Its output is directly
  above that line. Report it as a finding. If it is a judgement call, ask, and do
  not spend an attempt on it. Otherwise fix it the way **Fixing a finding** below
  describes, the class and not just the named instance, and rerun with `sapa gate
  --fix-attempt`, within the budget below. Do not certify green until every step
  passes. The user may interrupt to change something and rerun `/sapa-gate`.
- **2 — nothing ran.** Back to Step 1: either you are outside a worktree, or the
  config is missing or malformed. The message says which, and the two take
  different recoveries.
- **5 — the autofix budget is spent, so nothing ran.** You reached for another fix
  after the budget said stop. Do not try again: report where it stands and hand
  the stream back, as below.

### Fixing a finding

A finding is one instance of something, and rarely the whole of it. Before you
call it fixed and pay for another gate, work out its root cause and the class of
thing that cause produces, then eliminate every instance of that class across the
changed surface in one pass, not only the instance the gate named. A stale name a
review flags in one file is usually the same edit missed in ten others; a bug one
test catches is often the same mistake in its siblings. So fix the class, then
spot-check that you did: re-run the step, grep the tree for the pattern, look at
what else the same cause would have touched. This is the instinct a finding should
trigger, and it is what stops the gate from surfacing the next instance of a class
you already met a round later.

This governs how thoroughly you fix, not whether you guess. The judgement-call
carve-out holds either way: a finding whose fix is a real decision still gets
raised rather than swept, as the exit-1 handling above says. What the class-first
pass changes is that once you are fixing, you fix the cause and its whole class,
not the single instance in front of you.

### The autofix budget

"Fix it and run the gate again" with no stop is a loop that grinds. Repeated
failed fixes usually mean the failure is deeper than the patch, and the gate is
the worst place to keep guessing because it is foreground and blocking. Every
attempt pays for the always-run steps; pre-push steps run only after those pass.
A fix to a pre-push finding changes the head, so the next attempt starts from the
first always-run step before checking pre-push again. The loop is bounded, the
way `sapa-watch`'s CI loop is.

Every failed run ends with `sapa-gate	attempts	<spent>	<max>`. `<max>` is
`gate.max_fix_attempts` (default 3). **When `<spent>` has reached `<max>`, stop
there.** Do not diagnose, do not edit, do not rerun. Say plainly that repeated
fixes are not converging on this gate, which usually means the failure is deeper
than the patch and possibly architectural, and hand the stream back to the
developer. Say it in chat and stop; the gate is blocking and they are already
waiting on it, so there is no notification hook to fire.

Below the budget, rerun the whole gate with `sapa gate --fix-attempt`. The flag is
you saying the rerun checks a fix **you** decided on, and it is what the count
counts. Passing it when the budget is already spent is refused with exit 5 having
run nothing, which is the backstop for ignoring the line, not a second chance.

A fix the developer dictated is not one of your guesses, so it reruns **bare**,
with no `--fix-attempt`. That covers a judgement call they answered and a rebase
conflict they resolved. A bare rerun starts the count over, which is correct: they
are in the loop, and a loop blocked on their answer cannot run away. Do not reach
for a bare rerun to refill your own budget after they said nothing.

A run that reaches green ends the episode. Nothing carries forward.

### Invoking a `skill:` step

The `plan` line is the spec source for every `skill:` step: `sapa gate`
materializes the accepted plan once and prints its absolute path. Whichever
invocation path the step takes, its prompt must name that path as the accepted
spec for this change and say to review against it rather than discovering a
surface itself, and pass the path as the skill's argument too for skills that
read args. That keeps the contract skill-agnostic: any review skill that accepts
a spec path reviews against the plan, not against a guessed surface such as the
untouched issue body.

The prompt must also ask the review to be exhaustive per class: for each finding,
report every instance of its class present in the changed surface, not one
representative instance. A review left free to name only the first stale name or
the first missed case hands the gate the rest one at a time, a round each; asking
it to enumerate the whole class up front is what lets a single round clear it and
is the review-side half of **Fixing a finding** above. State this in the prompt
itself so it holds for whatever review skill is configured, rather than assuming a
skill enumerates on its own.

`absent` means there is no plan to review against: either none is recorded —
legitimate when `/sapa-gate` runs standalone before planning, an anomaly inside
the flow — or the read itself failed, which the helper says on stderr. Check
stderr and report which, because "no plan exists" and "could not check" call for
different follow-up. Either way, say so in the step prompt so the skill reports
its spec axis honestly rather than degrading to "no spec available" silently, and
warn visibly in the gate report that spec-compliance did not run. A green gate
must never imply the spec was checked when it was not. It is never a reason to
fail the step.

That warning also outlives the session now: the helper records which of the two
cases applied, and `sapa gate --report` puts it on the PR. Say it in chat anyway —
the developer is deciding what to do next and should not have to open the PR to
find out the spec axis had nothing to check.

When the `needs-skill` line carries a model (anything but `-`), run that step
inside a single sub-agent pinned to that model via the Agent tool's model
override. The sub-agent's prompt: invoke that skill against the diff
`<remote>/<base>...HEAD`, using the materialized plan file as the spec source,
enumerating every instance of each finding's class in that diff, and return its
findings verbatim. Treat the sub-agent's findings as the step result, exactly as
an in-session invocation would be. Sub-agents the skill itself spawns inherit the
pinned model, so a review skill's parallel reviewers run on it too. With `-`,
invoke the skill in-session with the same spec path.

A pinned model is a preference, not a requirement: it names the model to review
on when the harness can reach it, and the gate still runs when it cannot. So when
that pinned spawn comes back an error because the harness cannot reach the model
— the account has no access to it, or the harness has no such model at all — do
not fail the step, and do not drop to the in-session `-` path. Re-spawn the same
step as a sub-agent with no model override, so it runs on the session model, and
treat its findings as the step result exactly as the pinned spawn would have. The
fallback drops the override, not the isolation: it stays a sub-agent so review
keeps its own context.

Report the fallback rather than hide it. Say it in one line where it happens,
naming the pinned model and that review ran on the session model instead, so
whoever is gating right now sees it. Then resume the walk with `--fell-back` on
the `--after` call — `sapa gate --after <name> --result pass|fail --fell-back
--summary "…"` — which records that the pin was unreachable so the gate report
says review ran on the session model rather than asserting the pinned model ran.
That is the same disclosure the `absent`-plan case above puts on the PR; a silent
fallback would leave the report claiming the pinned model reviewed the change when
it did not. The re-spawn is the same review on a different model, not a fix, so it
spends no `max_fix_attempts` attempt.

The trigger is unreachability, not any error. The harness surfaces an unreachable
model as a visible error rather than a quiet run on another model — a model it
does not accept at all is refused at the call, and one the account cannot use
errors at spawn — so the pinned spawn is itself the check: read the error, and if
it means the model is unreachable, drop the override and spawn again. Do not fall
back on a transient fault such as a rate limit, an overload, or a timeout, which
is not unreachability; let that fail the step and be handled like any other
failing spawn rather than quietly downgrading the review. Do not pre-check access
before spawning either — there is nothing to consult, and a spawn that succeeds
needed no fallback.
