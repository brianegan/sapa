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

Run `sapa-config -p` to print the discovered `.sapa.yaml` (it walks up from the
current directory the way `sapa-worktree` finds `.bare`). If none is found, ask
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

## Step 2 — Rebase onto the base

Bring the branch up to date with the base so the gate runs against what will
merge.

1. Commit any uncommitted work with a clear message first, so the tree is clean
   for the rebase.
2. `git fetch <remote>`, then `git rebase <remote>/<base>` using `remote` and
   `base` from the config.
3. Already up to date → no-op, continue.
4. **Conflict → stop.** Run `git rebase --abort`, report the conflict as a
   finding, and let the user resolve it before rerunning `/sapa-gate`. Never
   auto-resolve a rebase conflict — it is a judgement call.

## Step 3 — Run the gate (blocking)

Run each gate step in order, in the working tree. This blocks.

- All steps pass → report the branch is green and stop. `/sapa-submit` ships it
  next.
- A step fails → **stop**. Report the failing step and its output as a finding.
  Apply a safe, mechanical fix and rerun from the top; if it is a judgement call,
  ask. Do not certify green until every step passes. The user may interrupt to
  change something and rerun `/sapa-gate`.
