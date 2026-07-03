---
name: sapa
description: Gate a stream of work and ship it as a draft PR. Runs the project's configured quality gate in the working tree, captures the plan on the GitHub issue, then pushes to origin and opens a draft PR with a managed description. Use when a piece of work is ready to go up, or the user says "gate this", "ship it", "sapa", or "/sapa".
---

# Sapa

Sapa (Filipino for "stream") closes out a piece of work. It picks up after
`barry` and `worktree` have put you in a worktree and the code is written.

This skill covers the **gate + ship** half of the flow. The **watch** half
(monitoring the PR after it is up) is a separate phase and is not built yet.

Core rules, always:

- **`origin` is the only remote.** Never introduce or push to a second remote.
- **The gate runs in the current working tree**, not a copy. It blocks. If a
  step fails, stop and surface it. The user can fix and rerun, or cancel.
- **GitHub operations go through `gh-axi`**, invoked as `npx -y gh-axi ...`,
  never `gh`.
- **Never clobber human text.** The PR description and the issue plan are
  maintained through `sapa-section`, which refuses to overwrite anything a human
  has edited or locked.

## Inputs

Determine the **issue number** for this stream:

1. If the user passed one, use it.
2. Otherwise derive it from the branch name (a leading number, e.g.
   `123-add-widget` → 123, or a trailing `#123`).
3. If still unknown, ask the user before touching any issue.

## Step 1 — Locate the config

Run `sapa-config -p` to print the discovered `.sapa.yaml` (it walks up from the
current directory the way `worktree` finds `.bare`). If none is found, tell the
user and ask whether to proceed with a sensible default gate (test + format) or
stop so they can add a config.

The config is an ordered list of gate steps. Each step has a `name` and either:

- `run:` — a shell command. It may include a version-manager prefix such as
  `fvm flutter test`. Run it verbatim in the working tree.
- `skill:` — a skill to invoke for that step (e.g. a review skill). Invoke it and
  treat its findings as the step result.

```yaml
base: main            # PR base branch (default: main)
gate:
  - name: review
    skill: code-review
  - name: analyze
    run: fvm dart analyze
  - name: test
    run: fvm flutter test
  - name: format
    run: dart format .
```

## Step 2 — Capture the plan on the issue

If you and the user agreed on a plan for this work in this session, record it on
the issue before shipping, so it is durable and visible rather than trapped in
the session.

1. Read the current issue body: `npx -y gh-axi issue view <N> --full`.
2. Write the plan into a managed section, preserving everything else:

   ```
   printf '%s' "$PLAN_MARKDOWN" > /tmp/sapa-plan.md
   npx -y gh-axi issue view <N> --full | \
     sapa-section plan --content-file /tmp/sapa-plan.md > /tmp/sapa-issue-body.md
   ```

3. Read the status `sapa-section` printed on stderr. If it is `created` or
   `updated`, push the new body: `npx -y gh-axi issue edit <N> --body-file /tmp/sapa-issue-body.md`.
   If it is `locked` or `locked-edited`, the user owns that section — leave the
   issue as-is and mention it.

If there is no distinct plan (the work was trivial / auto-mode), skip this step.

## Step 3 — Run the gate

Run each configured step in order, in the working tree. This blocks.

- If every step passes, continue to Step 4.
- If a step fails, **stop**. Report which step failed and the relevant output as
  a finding. Apply a safe, mechanical fix if there is an obvious one and rerun
  the gate from the top. If the fix is a judgement call, ask the user. Do not
  proceed to ship until the gate is green.

The user may interrupt at any point to make a change; when they rerun `/sapa`,
start again from Step 1.

## Step 4 — Ship

Once the gate is green:

1. Commit any uncommitted work with a clear message if needed.
2. Push the branch to `origin` only: `git push -u origin HEAD`.
3. Build the PR description in a managed section so it is protected from the
   start. Generate a concise summary of what changed, then:

   ```
   printf '%s' "$PR_SUMMARY_MARKDOWN" > /tmp/sapa-pr.md
   # For a brand-new PR the body starts empty:
   printf '' | sapa-section pr-description --content-file /tmp/sapa-pr.md > /tmp/sapa-pr-body.md
   ```

   Append `\n\nCloses #<N>` to the body so the PR links the issue. Do not repeat
   the plan in the PR body — the plan lives on the issue.
4. Open the PR as a **draft**:

   ```
   npx -y gh-axi pr create --draft --base <base> \
     --title "<title>" --body-file /tmp/sapa-pr-body.md
   ```

5. Report the PR URL.

### Updating an existing PR's description

On a later run, read the current body with `npx -y gh-axi pr view <N> --full`,
pipe it through `sapa-section pr-description --content-file ...`, and only
`pr edit --body-file` if the status is `created`/`updated`. If it is `locked`
or `locked-edited`, leave the description alone.

If the user says the description is wrong or to leave it alone, rewrite the
section once with `--lock` (status `locked-now`) so Sapa never touches it again.

## Step 5 — Reconcile the plan

If what shipped diverged from the plan captured in Step 2, refresh the issue's
plan section (same `sapa-section plan` flow) so the issue tells the truth. If the
section is locked, add a short note as an issue comment instead of editing it.

## Next phase (not built here)

After the draft PR exists, the watch phase would monitor CI, address review
comments, and keep the branch mergeable. That is deliberately out of scope for
this build. Stop after reporting the draft PR URL.

## Helpers

- `sapa-config [-p] [--start DIR]` — find (`-p` prints) the `.sapa.yaml`.
- `sapa-section MARKER --content-file FILE [--body-file FILE] [--lock]` — edit a
  managed section of a body read from stdin or `--body-file`. Prints the new body
  to stdout and a status word (`created`, `updated`, `locked-now`,
  `locked-edited`, `locked`) to stderr. Never clobbers human edits.
