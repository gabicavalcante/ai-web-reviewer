# Changelog

Dates are the day the change landed. Versions follow [semver](https://semver.org).

## 1.2.0

Both changes are about the squash bar telling you what it knows. Nothing to do on upgrade.

### The squash bar says why it cannot run

It used to offer a squash the server would refuse. Pressing it wrote the reason into the
same green bar the offer was in and changed nothing else on the page, which read as a
button that does nothing.

The guards now run when the page polls, not only when the press arrives. A bar that
cannot squash turns red, states the reason, and disables the button:

```
Cannot squash yet: 4 tracked file(s) have uncommitted changes. Commit or stash them first.
```

The dirty-tree message counts the files, since the old wording left you to go and find
out which. The check costs a `git status`, so the page asks for it only while the bar is
on screen, which is after every commit is ticked.

### The rail says which commits have fixups folded into them

Folding a fixup into the commit it amends is what keeps the rail as long as the change
rather than as long as the review. It also hid the only reason the squash bar appears:
the rail showed two ordinary commits, the bar offered to squash two fixups, and nothing
on screen connected them.

```
1  Draft a post on Supabase authorization  +289 -0  2 fixups inside  reviewed
```

The fixups were always drawn inside that commit's own diff, which is no help to someone
reading the rail and wondering what there is to squash.

## 1.1.0

Upgrade if you are on 1.0.0. Questions asked on the page never reached Claude in that
release, and the page could not tell you so.

### The watcher was reading the wrong folder

`review.py` resolves `HEAD` to the branch it names before keying a directory off it, and
`watch.py` and `answer.py` did not. `SKILL.md` tells the session to pass the watcher "the
range you served, the same string", and the default range is `origin/main...HEAD`. So the
server wrote questions into `origin-main-<branch>-<hash>` and the watcher sat over
`origin-main-head-<hash>`, a folder it had just created for itself.

Both processes ran, both were right about their own state, and no question was ever
delivered. The page reported no session attached, because it looks for the watcher's
heartbeat in its own folder. Reproduced on a new repo with 1.0.0: first branch, first
question, nothing.

Nothing to do but upgrade. Any stray `*-head-*` folder in your state directory is an
artifact of this and holds nothing.

A script that joins a review now refuses when the folder is missing, listing the reviews
that exist, instead of creating one. Only the server makes a review.

### A branch that touched an image could not be built at all

`git blame` on a binary file does not fail. It succeeds and prints the bytes, and decoding
them as UTF-8 threw, so the build died on any range containing a PNG, a font or a PDF:

```
UnicodeDecodeError: 'utf-8' codec can't decode byte 0x89 in position 383
```

Binary files are now found from `git diff --numstat`, which writes `-` for both counts,
and are never blamed.

### The rail says how much of each commit is still in the branch

The same `git blame` pass that orders the files tab now counts, per commit, how many of
its lines survive to the tip of the range.

- A commit with less than half left shows `12 of 77 survive` beside its diff numbers.
- A commit with none left is marked `skim`. A commit your narrative already marked keeps
  the mark you gave it.

On a branch that was reworked in place this is most of the rail. One branch measured here
has fifteen commits and ten of them no longer exist.

### `care` is capped at five

`care` warned past a third of the commits, which does not hold on a long branch: a third
of forty is thirteen, and nobody keeps thirteen in mind. It now warns past a third **or**
past five, whichever is fewer. Still a warning, so every existing narrative builds
unchanged.

### Also

- A review with no stages gets the full width. The hidden stage rail left the grid, and
  the file pane fell into the 340px column meant for it, so the diff rendered in a third
  of the page with paths truncated.
- `review.py serve` names the other reviews in the checkout when the one it is starting
  has no threads. Reading one branch against two different bases is two reviews with
  separate questions, which is correct and was invisible.
- The README's densest passages are rewritten in plain English, and it now shows a
  screenshot of the page.

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
