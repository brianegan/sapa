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

Before anything else, mark the stream's stage for the window switcher: run `sapa
status --stage gate` (best-effort — it no-ops outside a sapa stream).

## Step 1 — Locate the config

Run `sapa gate --list` to print the resolved gate steps. `sapa gate` finds the
`.sapa.yaml` itself (walking up the way `sapa worktree` finds `.bare`) and reads
the keys it needs — `base:` (default `main`), `remote:` (default `origin`), and
the ordered `gate:` list. `sapa config -p` shows the whole file if you want the
other keys too.

Each line is `sapa-gate  list  <name>  run|skill  <command-or-skill>  <model>`:

- a `run:` step is a shell command the helper runs verbatim. It may carry a
  version-manager prefix such as `fvm flutter test`.
- a `skill:` step is a skill you invoke for that step. Treat its findings as the
  step result.
- `model:` (`-` when absent) names a model, the way the Agent tool's model
  override accepts (`fable`, `opus`, `sonnet`, `haiku`). It is meaningful for
  `skill:` steps; Step 3 says how to honour it. Absent, the step runs on the
  session model.

Exit 2 means there is nothing to run: no config, no `gate:` key, or a malformed
step. The message says which. On a missing config, ask whether to use a sensible
default gate (test + format) or stop; on a malformed one, report it and stop
rather than guessing what was meant.

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
the rebase just settled, and stops the moment something needs you. This blocks.

It emits one tab-separated line per result, each led by `sapa-gate` so a step's
own output can't be mistaken for one:

```
sapa-gate	plan	<absolute-path>	present|absent
sapa-gate	step	<name>	run	<exit>	<seconds>
sapa-gate	needs-skill	<name>	<skill>	<model-or->
sapa-gate	done	green
```

Act on the exit code:

- **0 — `done green`.** Every step passed. Report the branch is green and stop;
  `/sapa-submit` ships it next.
- **4 — `needs-skill`.** The walk has reached a `skill:` step, which needs this
  harness. Invoke it (below), and when it passes continue the walk with `sapa
  gate --after <name>`. Repeat until the gate ends on 0 or 1. A skill step whose
  findings are a genuine failure is treated like a failed step: stop and report.
- **1 — the last `step` line names the failing step.** Its output is directly
  above that line. Report it as a finding. Apply a safe, mechanical fix and
  rerun `sapa gate` from the top; if it is a judgement call, ask. Do not certify
  green until every step passes. The user may interrupt to change something and
  rerun `/sapa-gate`.
- **2 — nothing to run.** Back to Step 1: the config is missing or malformed.

### Invoking a `skill:` step

The `plan` line is the spec source for every `skill:` step: `sapa gate`
materializes the accepted plan once and prints its absolute path. Whichever
invocation path the step takes, its prompt must name that path as the accepted
spec for this change and say to review against it rather than discovering a
surface itself, and pass the path as the skill's argument too for skills that
read args. That keeps the contract skill-agnostic: any review skill that accepts
a spec path reviews against the plan, not against a guessed surface such as the
untouched issue body.

`absent` means there is no plan to review against: either none is recorded —
legitimate when `/sapa-gate` runs standalone before planning, an anomaly inside
the flow — or the read itself failed, which the helper says on stderr. Check
stderr and report which, because "no plan exists" and "could not check" call for
different follow-up. Either way, say so in the step prompt so the skill reports
its spec axis honestly rather than degrading to "no spec available" silently, and
warn visibly in the gate report that spec-compliance did not run. A green gate
must never imply the spec was checked when it was not. It is never a reason to
fail the step.

When the `needs-skill` line carries a model (anything but `-`), run that step
inside a single sub-agent pinned to that model via the Agent tool's model
override. The sub-agent's prompt: invoke that skill against the diff
`<remote>/<base>...HEAD`, using the materialized plan file as the spec source,
and return its findings verbatim. Treat the sub-agent's findings as the step
result, exactly as an in-session invocation would be. Sub-agents the skill itself
spawns inherit the pinned model, so a review skill's parallel reviewers run on it
too. With `-`, invoke the skill in-session with the same spec path.
