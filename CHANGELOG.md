# Changelog

Dates are the day the change landed. Versions follow [semver](https://semver.org).

## 2.1.0

Nothing to do on upgrade. Files changed is the tab that opens now, and a stage only appears
where the branch still passes through it.

### Files changed opens first

The branch as it stands is what a reviewer came to read. The commits are how it got there,
which is the second question and on a long branch sometimes not one at all. The README has
said that since the tab existed; the default disagreed with it. Commits is one click away,
and questions are still asked there, where a line has a commit behind it to anchor to.

### A stage is a step in a journey through the branch as it stands

A stage's file list came from history: any file any of its commits ever touched. The line
counts came from `git blame` on the tip. The two disagree whenever a later commit rewrote an
earlier one, and the file list won, so a stage listed files it had contributed nothing to.

A stage now lists a file when it accounts for something the final diff still shows: lines
that survive to the tip, or a file the branch removes. A stage left accounting for nothing is
not drawn, and the build says which one it dropped and why:

```
narrative: stage 'sqlmigrate' is not drawn: nothing it did is in the branch as it
           stands, so commit(s) 8, 11 belong to no stage
```

On one real review that took six stages to two, which is the journey that branch actually
takes. Marks are still commits: that is how a person reasons about a change, and every
narrative on disk keeps working. Only what gets drawn is read off the final state.

### The files view reads as a list to choose from

- A file is closed until its header says it is worth opening. The sentence a person wrote
  about it has moved into that header, where it is the reason to open the file or skip it,
  rather than a caption below the row.
- The file marked as the place to begin goes first in every pane it is drawn in.
- A stage name is no longer set in capitals. A stage is often named after a function, and
  `VALIDATE_PATENT_FILE_STRUCTURE_FOR_PARTIAL` is a wall where
  `validate_patent_file_structure_for_partial` is a name.
- The notes before you push are a queue of lines rather than three columns, each closed.
  Side by side, the longest one set the height of all of them.

### Writing a narrative

Two rules the reference never stated, both learned from reading a real one:

- A `where` is a place the work passes through, read in order as a journey, not the function
  that handles it. `the file's shape · the offices it names · each row, checked` is a
  journey; the four function names behind them are the file list again.
- A `what` says what happens at that step, so it starts with a verb. The two fields read as
  one line: *at the file's shape, check the header, the data rows and the dynamic fields.*

### Also

- A file header git had to quote, an accent in a path being the common case, no longer
  loses the file and reads its own header lines as content of the file before it.
- The range the page carries is the one you asked for. It keys the reviewed ticks in your
  browser, and the resolved form starts with a merge base, so it changed whenever main moved.
- The guard that names the other reviews in a checkout counts a narrative, not only threads.

## 2.0.0

Upgrade. A published 1.x is reachable from any website the reviewer has open.

### Any website you visited could rewrite your git history

The server binds `127.0.0.1` with no authentication, which accepts one threat, other
processes on your machine, and not the one that mattered. A browser sends a POST to
localhost on behalf of whatever page you have open, and a POST with a simple content type
needs no preflight to ask permission first. So any site open while a review was running
could reach the endpoints, and two of them write:

```
POST /squash  Origin: https://evil.example  ->  {"ok": true, "before": 2, "after": 1}
POST /ask     Origin: https://evil.example  ->  text of its choosing into the log your
                                                Claude session reads and acts on
```

Both are refused now. Nothing to do but upgrade.

### The squash button rewrote whatever branch was checked out

The range is fixed when the server starts; `HEAD` is wherever you are now. Serving a review
of `feature-a`, checking out `feature-b` and pressing Squash rewrote **`feature-b`** and
reported success for `feature-a`. The backup branch was filed under the wrong branch too.
It now refuses and names the branch to check out.

### The rail listed commits that were not yours, and called them dead work

`git log a...b` is the symmetric difference; `git diff a...b` is `merge-base..b`. The tool
used the three dot form for both, and `origin/main...HEAD` is the default, so every commit
`origin/main` gained since your branch started appeared on the rail. One real review showed
97 commits for a branch holding 23.

Those commits were then measured against a diff that never contained them, scored nothing,
and the page printed `nothing it added is still in the branch` over a colleague's merged
work. Both gone.

### A deleted line could disappear, taking the line numbers with it

A deleted line whose content begins `-- ` reaches git as `--- `, which is also how git
introduces the old side of a file. It was read as a header: dropped from the page, and
every old-side line number below it short by one. A question asked below that point was
recorded against a line you never clicked. SQL and Lua comments, YAML front matter and
email signatures all hit it. The same for an added line beginning `++ `.

### The watcher could stop reading, silently

One unreadable row, from a write that died or a full disk, hid every row after it for as
long as that watcher ran. The server reads the same file separately, so the page went on
showing those questions as waiting for an answer with nothing listening. A row that cannot
be read is now stepped over, and said once.

### A failed build destroyed the page you were reading

`smoke.js` refuses a page whose script throws, and it ran after the page had been written.
A typo in a hand-edited narrative was enough to leave you reloading onto a masthead and
nothing else, and a squash rebuilds after the rebase, so history was rewritten with no page
to read it on. The page is built beside the old one and moved over only once its script has
run.

### Every thread in a review could be orphaned at once

Threads are pinned to git's abbreviated sha, and git picks that width from how many objects
a repo holds. A repo that grew, or a colleague with `core.abbrev` set, moved every thread in
the review into the orphan list under `this commit is not part of the diff shown here`,
which was false, with no way back. A sha is now resolved before it is compared, and an
ambiguous one is left an orphan rather than guessed onto the wrong commit. The reviewed
ticks were keyed the same way and are fixed with it.

### Breaking: `review.py archive` is gone

This is the major bump. The command moved a review's four logs into a timestamped folder,
and it renamed `questions.jsonl` out from under a running watcher, which then swallowed
every question asked afterwards while the page drew a confident "waiting for an answer".

It was never used, and the isolation it offered arrived by another route: threads have been
per review since 1.0.0, so finishing one branch already leaves another alone. To put a
review's questions away, move its folder. An `archived-<stamp>/` folder in an older store is
yours to keep or delete; nothing reads it.

The prompt `archive the threads for this review` no longer does anything.

### The tool has checks now

69 of them, in `tests/`, in plain `python3` with no dependencies. `python3 tests/run.py`.
They run in CI on every push alongside `black` and `pyflakes`, and each one is there because
something shipped without it.

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
