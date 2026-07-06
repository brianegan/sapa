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

Rules (always): the configured remote (default `origin`) is the only remote — its
name is configurable but there is never a second one; GitHub goes through `gh`.

## Step 1 — Locate the config

Run `sapa config -p` to print the discovered `.sapa.yaml` (it walks up from the
current directory the way `sapa worktree` finds `.bare`). If none is found, ask
whether to use a sensible default gate (test + format) or stop.

Read these top-level keys (all optional):

- `base:` — the branch the PR targets (default `main`).
- `remote:` — the single remote to fetch and rebase onto (default `origin`).
- `gate:` — the ordered list of gate steps below.

Each gate step has a `name` and either:

- `run:` — a shell command, run verbatim in the working tree. It may carry a
  version-manager prefix such as `fvm flutter test`.
- `skill:` — a skill to invoke for that step (for example a review skill). Treat
  its findings as the step result.

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

Once the rebase settles, the branch's changed files against the merge-base are
`git diff --name-only <remote>/<base>...HEAD` — the diff the gate holds. Step 3
hands this to each `run:` step so a script can scope to it.

## Step 3 — Run the gate (blocking)

Run each gate step in order, in the working tree. This blocks.

Give every `run:` step the diff as two environment variables, `SAPA_BASE` and
`SAPA_CHANGED_FILES` (newline-separated paths), so a script can gate only the
changed packages and fall back to all on a cross-cutting change. Set them on the
command itself — each step runs as its own shell, so a variable exported in an
earlier step would not survive; setting them inline keeps each step
self-contained:

```
SAPA_BASE=<base> \
SAPA_CHANGED_FILES="$(git diff --name-only <remote>/<base>...HEAD)" \
  <the run: command>
```

Use `<base>` and `<remote>` from the config; the triple-dot diffs against the
merge-base. Quote the substitution so the newline-separated paths survive. An
empty result (the branch matches the base) is fine — the variables come through
empty. This contract applies to `run:` steps only; a `skill:` step invokes a
skill rather than a shell, so the variables do not apply to it.

- All steps pass → report the branch is green and stop. `/sapa-submit` ships it
  next.
- A step fails → **stop**. Report the failing step and its output as a finding.
  Apply a safe, mechanical fix and rerun from the top; if it is a judgement call,
  ask. Do not certify green until every step passes. The user may interrupt to
  change something and rerun `/sapa-gate`.
