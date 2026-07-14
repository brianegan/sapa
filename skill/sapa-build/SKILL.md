---
name: sapa-build
description: Implement a stream's recorded plan — read the sapa:plan comment from the GitHub issue and write the code and tests it calls for in the working tree. Use once the plan is recorded and it's time to code, or when the user says "build this", "implement the plan", "sapa build", or "/sapa-build".
---

# sapa-build

Turn the plan recorded on the issue into working code. The `sapa:plan` comment is
the source of truth, so this can pick up a stream from a fresh session: read the
plan, implement it, stop. It does not push or open a PR — that is `/sapa-gate`
then `/sapa-submit`.

Rules (always): the configured remote (default `origin`) is the only remote;
GitHub goes through `gh`; read the plan from its issue comment, never re-derive it
from the issue body.

## Steps

First, mark the stream's stage for the window switcher: run `sapa status --stage
build` (best-effort — it no-ops outside a sapa stream and never needs your input).

1. **Find the issue.** Use the number the user gave, else derive it from the
   branch name (a leading number like `42-add-widget` → 42), else ask.
2. **Read the recorded plan.** Find the `sapa:plan` comment and read its body
   untruncated:

   ```
   id=$(gh api /repos/{owner}/{repo}/issues/<N>/comments --paginate \
     --jq '.[] | select(.body | contains("<!-- sapa:plan")) | .id')
   gh api /repos/{owner}/{repo}/issues/comments/$id --jq .body > "$(sapa tmp)/plan.md"
   ```

   `$(sapa tmp)` is this stream's own scratch directory, so a parallel stream's
   plan can't land in the file you read back. Confirm the read is whole: `sapa
   section plan --check --body-file "$(sapa tmp)/plan.md"` exits non-zero if the
   body is damaged — a truncated read
   that lost the closing marker. If it errors, stop and report; do not build from
   a half-read plan. If there is no `sapa:plan` comment at all (no id), stop and
   say the plan has not been recorded yet (run `/sapa-plan` first).
3. **Implement.** Write the code and tests the plan calls for, in this working
   tree. A recorded plan is an accepted plan; when the comment is
   `locked`/`locked-edited` the developer's version is authoritative — build what
   the comment says, not an earlier draft. Then stop; `/sapa-gate` runs the
   checks next.
