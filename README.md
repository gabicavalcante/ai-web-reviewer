# web-reviewer

Read a branch's diff in a browser and ask questions about individual lines, with the
answers arriving beside the code they are about.

Built as a [Claude Code](https://claude.com/claude-code) skill. The page is plain HTML
served from a local Python process; there is no build step and no dependencies outside
the standard library.

## Why

Reviewing a large branch by scrolling terminal diffs loses you. And a question about a
diff usually arrives without the thing it needs most: which line it is about. This puts
the question on the line.

## What it does

- Renders a git range as a page: commits in a rail, diffs with line numbers, files
  collapsible, large deletions collapsed by default.
- Click any line to open a thread anchored to that commit, file and line. A line that
  already carries a thread is marked in the gutter.
- Threads reach your Claude Code session, and answers arrive in a panel beside the diff,
  so a long answer never pushes the code off the screen.
- Answers render `code`, **bold** and fenced blocks.
- Mark threads resolved, read a resolved one without reopening it, hide them entirely.
- Folds `fixup!` commits into the commit they amend, so a branch under review reads as
  long as the change is rather than as long as the review was.
- Notices when the branch has moved under the page, and offers to build it again.
- Squashes the fixups when the review is done, with guards and a backup branch.

## Requirements

Python 3 and git. `node` is optional: the build runs the page's script against a minimal
DOM and refuses to serve a page that throws, and without node that check is skipped with
a message.

## Install

```bash
git clone https://github.com/<you>/web-reviewer ~/development/personal/web-reviewer
ln -s ~/development/personal/web-reviewer ~/.claude/skills/web-reviewer
```

Then ask Claude Code to review a branch in the browser, or invoke `/web-reviewer`.

## How a question reaches Claude

Asking on the page appends to a log. Nothing reads that log on its own, so a session that
never started a watcher will leave every question unanswered with no sign that it is
doing so.

Claude Code arms the watcher when it opens the review, following `SKILL.md`. It runs
`tool/watch.py`, which prints one line per new question or reply, and the session answers
with `tool/answer.py`. If answers never arrive, that watcher is the first thing to check.

## Controls

| | |
| --- | --- |
| Click a line | Ask about it, or open the thread it already has |
| `j` `k` or arrows | Move between commits |
| `⌘/Ctrl + Enter` | Send the question or reply you are typing |
| `Esc` | Close the thread panel or the question box |
| `Changes only` | Hide unchanged context lines |
| `Wrap lines` | Wrap long lines instead of scrolling sideways |
| `Hide resolved` | Drop resolved threads out of the page |
| `Thread at the side` | Threads in a panel beside the diff, or as rows under the line |

## Change requests, and why fixups

A request made in a thread lands as `git commit --fixup=<sha>`, never as an amend. A
thread is anchored to a commit's sha, so amending a reviewed commit changes that sha and
orphans every thread on it. A fixup leaves the reviewed commits alone.

The page folds each fixup into the commit it amends and marks it as one, so the rail
stays as long as the change rather than growing with every correction. A fixup whose
target is outside the range stays a commit of its own.

When every commit is ticked, the page offers to squash. It refuses on a dirty working
tree, on a rebase already in progress, when there is nothing to squash, and when the
range contains commits that are already pushed, which is the only refusal it will let you
override. It writes a `pre-squash/<stamp>` branch first, and a rebase that does not apply
is aborted and rolled back rather than left half done.

Squashing rewrites every commit in the range, so the threads on them are orphaned. They
are not lost: the page keeps them in their own section, and they stay readable and
answerable there.

See `git help rebase` for what `--fixup` and `--autosquash` do.

## Use it without Claude Code

The page and the server stand alone. From inside any git repo:

```bash
python3 ~/.claude/skills/web-reviewer/tool/review.py serve origin/main...HEAD
```

You get the diff reader and the thread UI. Questions are appended to
`~/.local/state/web-reviewer/<repo>-<hash>/questions.jsonl`, and anything that appends an
answer to `messages.jsonl` shows up in the thread, so the Claude Code integration is one
consumer rather than a requirement.

`tool/answer.py` writes those turns. A plain turn is an answer; `--ask` marks it as a
question back to the reviewer, which the page offers a button to answer; `--did` records
a change with the commit it landed in.

State lives outside the repo, so questions never land in git and survive rebuilds and
restarts. The next section says where it goes and what removes it.

## Where state lives, and when it is cleaned

Threads live outside the repo, in a directory named for the repo plus a hash of its
absolute path, so two checkouts of the same project never collide:

```
~/.local/state/web-reviewer/<repo-name>-<hash>/
```

`python3 tool/review.py where` prints it.

| File | What it holds |
| --- | --- |
| `questions.jsonl` | One row per thread: the question, and the commit, file, side and line it is anchored to |
| `messages.jsonl` | Every turn after the opening question, each tagged with who wrote it |
| `resolved.jsonl` | One row each time a thread is resolved or reopened |
| `answers.jsonl` | An older reply format, still read so old reviews keep working |
| `index.html` | The rendered page, rewritten by every build |

The four logs are append-only, and a question is flushed and `fsync`ed before the browser
is told it was accepted. Nothing rewrites a row. Resolving a thread appends a row saying
so rather than removing anything, which is what makes it reversible, and `Hide resolved`
filters data that is all still on disk.

**Nothing ever cleans these files.** There is no retention rule, no pruning, and no
command to forget a review. The only file the tool deletes is the watcher's heartbeat. A
directory stays until you remove it:

```bash
rm -rf ~/.local/state/web-reviewer/<repo-name>-<hash>
```

That is cheap to live with, since a five-thread review is around 13 KB, but it
accumulates one directory per repo path, including repos you have since moved or deleted.
Moving a repo changes the hash, so the next run starts empty while the old threads stay
under the old name.

`index.html` is the part you can lose safely: `review.py build` regenerates it from git.
The logs are the only thing here that cannot be reconstructed.

The `pre-squash/<stamp>` branches a squash leaves behind are the same kind of leftover.
Nothing removes them either, and they are yours to delete once you trust the result.

## The narrative layer

With no configuration the page takes its title from the branch, its figures from git, and
each commit's rationale from that commit's own message.

`review.py narrate <range>` writes a scaffold next to the review's state: every commit
keyed by sha with its subject, every field empty. Fill in what you know and rebuild, and
it is picked up from then on without a flag. `--narrative FILE` points at one kept
elsewhere.

It adds a data-flow strip, per-commit rationale, verification tables, a list of open
questions, and a mark on each commit saying where to start, what to read closely and what
is safe to skim. Every field is optional and falls back to git, and sections with no
content stay hidden, so a half-written narrative renders as the plain page rather than as
empty frames. See [reference/narrative.md](reference/narrative.md).

Write it while the branch is fresh. A session that has just built something can say what
it was unsure about and what it did not check; a later one is reading the diff like anyone
else, and a reconstructed reason is indistinguishable from a remembered one. So narrate early. A long
session that has been answering review questions for an hour does not recall the work any
better than a short one, and may recall it worse.

## Layout

| Path | What it is |
| --- | --- |
| `SKILL.md` | Instructions for the agent |
| `reference/narrative.md` | The optional editorial layer |
| `reference/voice.md` | How the page's own copy is written |
| `reference/gotchas.md` | Operational traps worth not rediscovering |
| `tool/review.py` | Build and serve |
| `tool/build_data.py` | Git range to page data |
| `tool/paths.py` | Where the repo is and where state lives |
| `tool/review.tpl.html` | The page |
| `tool/server.py` | Static files plus `/thread` `/ask` `/reply` `/resolve` `/rebuild` `/squash` |
| `tool/answer.py` | Write a turn into a thread |
| `tool/watch.py` | Emit new questions and replies as events |
| `tool/smoke.js` | Run the built page's script, so a page that throws is not served |
| `tool/narrative.example.json` | A narrative to copy from |

## Scope

The server binds `127.0.0.1` and has no authentication: anything that can reach the port
can read and append, and `/squash` rewrites history in the repo it was started from. It is
a local review tool, not a service. Do not bind it to a routable interface.
