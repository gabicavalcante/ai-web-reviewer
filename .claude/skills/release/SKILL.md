---
name: release
description: Cut a release of this repo as a plugin. Decide the version from what changed, write the changelog entry, bump the manifest, tag and push. Use when asked to release, cut a version, ship a version, tag a release, or publish the plugin.
---

# Release

This repo is one plugin, `ai-web-reviewer`, holding one skill, `web-reviewer`. A release
is a version in `.claude-plugin/plugin.json`, a changelog entry, and a git tag.

## Decide the number before writing anything

The README promises three surfaces will not change without a major bump. Read the diff
since the last tag and check each one:

```bash
git describe --tags --abbrev=0                  # the last release
git diff $(git describe --tags --abbrev=0)..HEAD --stat
```

| Changed | Bump |
| --- | --- |
| A prompt in the README's **What to say** table no longer works | major |
| A narrative key, mark or limit that an existing file relies on | major |
| An argument of `review.py`, `answer.py` or `watch.py` | major |
| Anything a reader will notice on the page | minor |
| A fix nobody has to do anything about | patch |

The state directory is not covered. It can move in a minor release, and has.

Say which rule you applied and why before you bump. A major version is cheap to
publish and expensive to take back.

## Then

1. Edit `version` in `.claude-plugin/plugin.json`.
2. Add a section at the top of `CHANGELOG.md`. Say what a reader has to do differently,
   not what the commits were. A release that asks nothing of anyone says so.
3. Commit both, with the version in the subject.
4. Tag and push:

```bash
claude plugin tag --dry-run          # check the name and version it would use
claude plugin tag -m "ai-web-reviewer %s" --push
```

`claude plugin tag` refuses a dirty tree, refuses a tag that exists, and checks that
`plugin.json` and the marketplace entry agree. Let it refuse. Do not pass `--force`.

## Before tagging, once

```bash
python3 tool/selftest.py
claude plugin validate .
python3 tool/review.py build HEAD~3..HEAD
```

The first runs the tool's own checks, each one holding down a bug that shipped. The second
checks both manifests. The third builds a page and runs `smoke.js` over it, so a page that
throws is caught before it is tagged rather than after. That third check is how the crash
on a branch containing a PNG was found, one commit before it would have been tagged.

GitHub Actions runs the same three on every push and pull request, so a red tag is the
second place you hear about it rather than the first.

## What a release does not include

Do not tag from a branch other than `main`, and do not tag a commit that is not pushed.
The marketplace serves what is on the remote, so a tag on an unpushed commit points at
something nobody can fetch.
