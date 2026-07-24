---
name: sapa-watch
description: Monitor a stream's PR — fix CI failures, address review comments, keep it mergeable, and tear the stream down when it merges. Use to attach to an existing PR, or when the user says "watch this", "sapa watch", or "/sapa-watch". sapa-flow hands off here after submit; it also attaches to an existing PR on its own.
---

# sapa-watch

Watch this stream's PR and act on what happens, until it merges. Attaches to an
existing PR without gating, so it can also resume monitoring from a fresh
session.

Rules (always): the configured remote (default `origin`) is the only remote —
read it, the base branch, and the PR state from `sapa config -p`; GitHub goes
through `gh`, Jira through `acli`. The PR body goes through `sapa section` (never
clobbering human text); the issue plan goes through `sapa issue plan-comment`.

Before anything else, mark the stream's stage for the window switcher: run `sapa
status --stage watch` (best-effort — it no-ops outside a sapa stream). Teardown on
merge clears the status file, so no explicit clear is needed here.

## Find the PR

Use the PR for the current branch. `gh pr view` (or `gh pr list --head <branch>`)
to get its number and state.

## The watch loop

Do not reimplement the poll loop. `sapa watch` owns the mechanical half —
resolving the PR, polling with back-off, guarding empty or failed fetches, and
deduping — so the detection is written once and tested, not improvised each
session. Run it as a background process through Monitor and only wake to act when
it emits a line. Each line is one real change: the first tab-separated token is
the event type.

Before starting it, read `watch.base_behind` from `sapa config -p` (default
`protection` when the key or the `watch:` map is absent) and pass it as
`--base-behind <value>`, the same way the gate config threads through: config
parsing lives here, the helper stays mechanical. `protection` fires `base-behind`
only when GitHub reports `mergeStateStatus: BEHIND` (which needs an "up to date"
branch-protection rule); `any` also fires it when the base has genuinely moved
ahead without that rule, at the cost of a rebase and re-gate on every merge to the
base.

- `ci-failed	<checks> <attempts>` — CI is failing. `<attempts>` is how many
  fixes sapa has already pushed for this failure streak (the helper carries it and
  resets it to 0 the moment CI goes green again). This handler is a bounded,
  verified loop, not a single-shot patch — an autofix loop with no discipline and
  no stop patches the symptom, ships a latent bug, and can push guess after guess
  forever on your account and in public.

  1. **Stop if the attempts are spent.** Read `watch.max_ci_fix_attempts` from
     `sapa config -p` (default 3 when the key or the `watch:` map is absent) — this
     is the skill's own gate, not threaded to the helper. If `<attempts>` is `>= N`,
     do **not** push another guess. Escalate to the developer through the
     notification hook (the same path the self-comment and base-conflicted cases
     use) and say plainly that repeated fixes are not converging, which usually
     means the failure is deeper than the patch, possibly architectural. Then stop:
     leave the loop for the developer.
  2. **Find the root cause before editing.** Read the failing job output fully
     (`gh pr checks <N>`, then the run log). Invoke the harness `diagnosing-bugs`
     skill to establish *why* it fails and to reproduce the specific failing check
     locally — do not reimplement a debugging method here, and do not fix a symptom
     you cannot first reproduce.
  3. **Verify the fix locally before pushing.** With the failure reproduced, apply
     the fix, then confirm that same check now passes locally. CI is not the first
     test of a fix. This is the specific failing check, not a full `/sapa-gate`
     re-run: the gate already ran at submit and reruns when the base moves.
  4. **Record the attempt, then push.** Once the fix is green locally, run `sapa
     watch --bump-fix-attempt` (increments the persisted counter and prints the new
     value), then commit and push. The next `ci-failed` — if the fix does not hold —
     arrives carrying the raised count, so the bound is enforced across polls and
     across a resumed session. A fix that lands green resets the count to 0 on its
     own.
- `new-review	<id> <author> <state> <self|other>` /
  `new-comment	<id> <author> <self|other>` — a review or comment landed. The
  trailing marker says who wrote it: `self` is you (the authenticated gh user,
  this stream's developer), `other` is anyone else. Read it
  (`gh pr view <N> --comments`) and route on the marker:
  - **`self`** — your own comment on your own PR. Do **not** reply on GitHub (not
    the PR, not the issue): a public reply to yourself is noise. Instead surface
    its content here and escalate through the notification hook so clicking it
    opens this window, then handle it in the chat. GitHub is not the reply
    surface for your own words; this session is.
  - **`other`** — a colleague. Do not act on the comment yet. Receive it first,
    then route — "looks mechanical" is not "is correct," and an agent's default is
    to agree with a confident reviewer, so correctness needs an explicit step or
    it is skipped silently.
    1. **Understand it.** If it is ambiguous, do not implement on a partial
       reading. Resolve it through the routing below rather than guessing.
    2. **Verify it against the codebase.** Is it correct for this stack? Does it
       break existing behavior? Is there a reason the code is written the way it
       is? A rename, a dead-code removal, or a "this is redundant" can still rest
       on context the reviewer did not have. For "implement X" / "add X"
       suggestions, grep for actual usage first: if nothing uses it, propose
       removing it rather than building it.
    3. **Route on the outcome:**
       - **Correct and a simple, reasonable change** (rename, typo, an obvious
         small fix that verifies clean): make the change, push, and reply on
         GitHub that it is done.
       - **Correct but a judgement call** — it changes the approach, or it
         contradicts the recorded plan in a non-trivial way: do not guess, and do
         not silently rewrite the plan to match the reviewer. Escalate to the user
         through the notification hook so clicking it opens this window, and wait.
         A comment that contradicts the accepted plan is a judgement call, not an
         instruction.
       - **Incorrect**: reply on the thread with technical reasoning, citing the
         specific test, code, or constraint that shows why, rather than
         implementing it or punting it. This pushback is autonomous but gated on
         verification — post it directly only when a concrete artifact backs it. A
         softer "I would have done it differently" is not "incorrect"; that is a
         judgement call, so escalate instead. If the pushback later proves wrong,
         correct it factually and implement — no long apology.
       - **Cannot verify without more information**: ask rather than proceeding
         anyway, routed by who holds the answer. If the reviewer can resolve it (an
         ambiguous comment, or intent only they know), ask on the thread. If only
         the developer would know (product intent, why the plan chose this,
         context not in the code), escalate through the notification hook.

    Any reply you post to an `other` comment — done, pushback, or a clarifying
    question — goes out under your gh account, so lead it with an attribution line
    so the colleague knows it is your agent, not you typing, and that they are
    talking to sapa:

    ```
    🤖 _Sapa Workflow, on @<your-login>'s behalf:_

    <the reply>
    ```

    `<your-login>` is the authenticated gh user (`gh api user --jq .login`).
    Lead the body with the fix or the reasoning: no performative agreement, no
    thanks ("great catch!"). Keep the body technical. Before posting, if
    `writing_style:` in the config (`sapa config -p`) names a skill, run it over
    the reply prose as a final pass — the body under the attribution line, never
    the attribution line itself. Absent the key, post the reply as written. Invoke
    the skill the normal way (for example `/humanizer`); if it cannot be
    model-invoked, read its `SKILL.md` and apply its guidance by hand.
  - Refreshing the plan: when a change you make or sanction alters what the
    recorded plan says — your own `self` decision, an `other` comment you routed
    as a correct, reasonable change, or a judgement call the developer resolved in
    favor of the change — refresh the plan comment on the issue by re-running
    `/sapa-plan` step 4: re-author the plan (markdown for GitHub, ADF for Jira) and
    record it with `sapa issue plan-comment`, which overwrites sapa's own comment
    in place. Never touch the issue body. Never refresh the plan to match a
    colleague comment on its own — a comment that changes the approach escalates
    first (above), and the plan changes only once the developer agrees. If you
    reached for the whole `/sapa-plan` skill rather than just its step 4, it will
    have written `stage: plan`; re-run `sapa status --stage watch` afterward to
    restore this stage.
- `base-behind` — the base branch moved ahead: either branch protection needs the
  branch up to date (`protection` mode), or `any` mode detected the base is ahead
  on its own. Either way, if the rebase is trivial (no conflicts), invoke
  `/sapa-gate` (it rebases onto `<remote>/<base>` and re-runs the checks), then
  push, then re-run `sapa status --stage watch` — the gate wrote `stage: gate`
  at its start, so without this the status file is stranded there once you are
  back to watching. If it is not trivial, escalate.
- `base-conflicted` — the base moved and now conflicts with this branch
  (`mergeStateStatus: DIRTY`). This is by definition not the trivial case, so do
  not auto-rebase or guess at a resolution: escalate to the developer through the
  notification hook, naming the conflicting files (`git fetch <remote> && git
  merge-tree --write-tree <remote>/<base> HEAD`, or a `--no-commit` merge/rebase
  probe you abort, to list them). This is the same "escalate the non-trivial
  conflict" policy as `base-behind`, wired to the state that actually carries it.
- `merged` / `closed` — terminal. `sapa watch` emits this and exits; on `merged`,
  tear the stream down (below).

After you push a fix, `sapa watch` keeps running and will emit the next real
change; you do not restart it. It dedupes against what it has already seen, so
acting on an event will not make it fire again.

Any time a handler runs another phase skill in full — `/sapa-gate` on
`base-behind`, or the whole `/sapa-plan` skill if you reach for it on a review
rather than just its step 4 — that phase overwrites `stage` with its own, since
each phase writes `stage` once at its start and never restores it (`sapa-watch`
is the only phase that delegates mid-run). So after any such hand-off returns,
re-run `sapa status --stage watch` before looping, so the status file keeps
reporting this stage to whatever reads it.

If the PR was opened as a draft, the user may promote it to ready whenever they
choose; keep watching across that transition. (When it shipped ready there is
nothing to promote.) Your own comments and colleagues' comments split by the
`self`/`other` marker above: yours are handled here in the chat, theirs on
GitHub with Sapa Workflow attribution.

## Teardown on merge

When the PR is merged (`state: merged`), the stream is done. Tear it down:

```
sapa teardown
```

Run it from the project root or let the script relocate itself — it removes this
worktree and deletes the local branch, and refuses if there are uncommitted
changes. It then closes the VS Code window that was open on the worktree, so
there is no manual window management (macOS + VS Code, best-effort; disable with
`close_window: false` in `.sapa.yaml`). Report that the stream is merged and
cleaned up. This is the watch loop's terminal action, so stop after it.
