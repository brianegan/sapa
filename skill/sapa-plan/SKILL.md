---
name: sapa-plan
description: Read a stream's GitHub issue and agree a plan, then record it on the issue. Use at the start of a stream, or when the user says "plan this", "sapa plan", or "/sapa-plan". Does not gate, push, or open a PR.
---

# sapa-plan

Turn a GitHub issue into an agreed plan, recorded on the issue so it is durable
and visible rather than trapped in this session.

Rules (always): `origin` is the only remote; GitHub goes through `npx -y gh-axi`,
never `gh`; never clobber human text (the plan is written with `sapa-section`,
which refuses to overwrite an edited or locked section).

## Steps

1. **Find the issue.** Use the number the user gave, else derive it from the
   branch name (a leading number like `42-add-widget` → 42), else ask.
2. **Read it.** `npx -y gh-axi issue view <N> --full`.
3. **Plan with the user.** Discuss the approach until you agree. Keep the plan
   about intent and decisions, not file-by-file code.
4. **Record it on the issue.** Write the agreed plan into the managed section:

   ```
   printf '%s' "$PLAN_MARKDOWN" > /tmp/sapa-plan.md
   npx -y gh-axi issue view <N> --full \
     | sapa-section plan --content-file /tmp/sapa-plan.md > /tmp/sapa-issue.md
   ```

   Check the status `sapa-section` printed on stderr. If `created` or `updated`,
   push it: `npx -y gh-axi issue edit <N> --body-file /tmp/sapa-issue.md`. If
   `locked` or `locked-edited`, the user owns that section — leave it and say so.

Stop here. Gating and shipping are `/sapa-ship`.
