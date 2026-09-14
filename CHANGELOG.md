# Changelog

Dates are the day the change landed. Versions follow [semver](https://semver.org).

## 1.0.0

First release, and the first version anyone other than its two users can install.

Nothing before this was versioned, so everything here is the starting point rather
than a change from something. What follows is what the tool does, and what it will
not do to you without a major version.

### What is covered by the version

- The prompts in the README's **What to say** table.
- The narrative file: its keys, its marks, and its length limits.
- The command line of `review.py`, `answer.py` and `watch.py`.

### What is not

The state directory's layout. It is internal, it changed twice in the week before
this release, and a page rebuilds from git.

### Installed as a plugin

`.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` make this repo a
marketplace of one plugin. Nothing moved: the manifest points its `skills` field at
the repo root, so the symlink install in the README keeps working unchanged.

### One break to know about, if you used it before this

Threads moved. They used to live at the top of a checkout's state directory, shared
by every review of that repo, and they now live in the folder of the review they
were asked in. A store written before this has questions no page will load. Ask
Claude Code to `move my old threads into the right review`, or
`archive the threads for this review` to start clean.
