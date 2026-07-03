# Sapa

Sapa (Filipino for "stream") closes out a piece of work. It picks up after
`barry` and `worktree` have put you in a worktree and the code is written, then
gates the work, captures the plan on the GitHub issue, and ships it as a draft
PR.

It is a Claude Code skill plus two small helper scripts. There is no daemon, no
binary, and no second remote: everything runs in the Claude session that did the
work, and `origin` is the only remote it touches.

See [PRD.md](PRD.md) for the full design and rationale.

## What's here

- `skill/SKILL.md` — the `/sapa` skill: locate config, capture the plan on the
  issue, run the gate in the working tree, push to `origin`, open a draft PR with
  a managed description.
- `bin/sapa-config` — finds the project's `.sapa.yaml` by walking up from the
  current directory, the same way `worktree` finds `.bare`.
- `bin/sapa-section` — maintains a machine-managed section inside a PR
  description or issue body and never clobbers text a human has edited or locked.
- `.sapa.yaml` — Sapa's own gate config (it gates itself).
- `tests/` — tests for the two helpers.

## Install

Put the helpers on your `PATH` and the skill where Claude Code can find it:

```sh
ln -sf "$PWD/bin/sapa-config"  ~/bin/sapa-config
ln -sf "$PWD/bin/sapa-section" ~/bin/sapa-section
ln -sfn "$PWD/skill"           ~/.claude/skills/sapa
```

GitHub access uses `gh-axi`, invoked on demand as `npx -y gh-axi`.

## Config

Drop a `.sapa.yaml` at the root of any repo. Each gate step is a shell command
(`run:`, which may carry a version-manager prefix) or a skill (`skill:`):

```yaml
base: main
gate:
  - name: review
    skill: code-review
  - name: analyze
    run: fvm dart analyze
  - name: test
    run: fvm flutter test
```

## Test

```sh
python3 tests/test_sapa_section.py
bash tests/test_sapa_config.sh
```
