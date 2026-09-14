# web-reviewer

Reading a branch's diff is becoming harder with AI. This tool aims to help with that: it
shows the diff in a browser and allows you to ask questions about individual lines.

Built as a [Claude Code](https://claude.com/claude-code) skill. The page is plain HTML
served from a local Python process; there is no build step and no dependencies outside
the standard library.

- **[Install](#install)** 
- **[What to say](#what-to-say)** 
- **[Two ways to read a branch](#two-ways-to-read-a-branch)** 
- **[Controls](#controls)** 
- **[Where state lives](#where-state-lives-and-when-it-is-cleaned)** 
- **[The narrative layer](#the-narrative-layer)** 
- **[Without Claude Code](#use-it-without-claude-code)**

## Why

Scrolling a large diff in the terminal, you lose your place. And when you ask someone
about a diff, the question usually travels without the one detail it needs most: which
line it is about. This tool attaches the question to the line.

## What it does

- Renders a git range as a page: commits in a rail, diffs with line numbers, files
  collapsible, large deletions collapsed by default.
- Click any line to open a thread anchored to that commit, file and line. A line that
  already carries a thread is marked in the gutter.
- Threads reach your Claude Code session, and answers arrive in a panel beside the diff,
  so a long answer never pushes the code off the screen.
- Mark threads resolved, read a resolved one without reopening it, hide them entirely.
- Tucks each `fixup!` commit inside the commit it corrects, so the list stays as long as
  the change instead of growing every time you fix something.
- Notices when the branch has moved under the page, and offers to build it again.
- Squashes the fixups when the review is done, with guards and a backup branch.
- Reads the branch two ways: commit by commit, or as the files it leaves behind.
- Marks a commit or a file as where to start, what to read closely, what is safe to skim.
- Says how much of each commit is still in the branch, and skims the ones a later commit
  rewrote entirely.

## Two ways to read a branch

**Commits** is the rail down the left: one commit at a time, in order, with its diff
beside it. This is where questions are asked, because a line here has a commit behind it
to anchor a thread to.

Later commits often rewrite what earlier ones wrote. `git blame` tells you, for the branch
as it stands now, which commit each line came from, so the page can count how much of each
commit is still there.

A commit with less than half its lines left shows `12 of 77 survive` next to its `+` and
`−` counts. A commit with none left is labelled `skim`, so you know you can move past it.
If you wrote a narrative and labelled that commit yourself, your label stays.

On a branch that was rewritten many times this can be most of the list. One branch here
has fifteen commits, and ten of them no longer exist in the final code.

**Files changed** is the branch as it stands now. On a long branch it is the better place
to start, for the reason above: reading the commits in order means reading code that is no
longer there.

With a narrative, the files tab is a rail of stages rather than files. Choosing one shows
only the lines that stage wrote, wherever it wrote them, with three rows either side and
the gaps counted. `git blame` on the tip of the range says which commit each surviving
line came from, and each commit belongs to a stage, so a file touched by four stages
appears under all four, showing different lines each time. No stage has to own a file.

A stage can therefore have no lines left in the branch at all. The rail says so and names
the commits that did the work, which is worth knowing before opening it.

Files are ordered within a stage: the code, then what documents it, then what tests it,
with a test moved to sit under the file whose name it matches. Each file can be opened
whole from a button beneath it. Questions are asked on the Commits tab, not here.

Without a narrative there are no stages, so the tab lists the files plainly.

## Requirements

Python 3 and git. `node` is optional: the build runs the page's script against a minimal
DOM and refuses to serve a page that throws, and without node that check is skipped with
a message.

## Install

As a plugin:

```
/plugin marketplace add gabicavalcante/ai-web-reviewer
/plugin install ai-web-reviewer@ai-web-reviewer
```

The plugin is `ai-web-reviewer` and the skill inside it is `web-reviewer`, which is the
name you will see and invoke.

Or as a checkout you can edit, which is the same files:

```bash
git clone https://github.com/gabicavalcante/ai-web-reviewer ~/development/personal/web-reviewer
ln -s ~/development/personal/web-reviewer ~/.claude/skills/web-reviewer
```

Then ask Claude Code to review a branch in the browser, or invoke `/web-reviewer`.

## What to say

You talk to Claude Code. It runs the scripts, and the commands named later in this file
are what it runs, written down so you can run them yourself and so the page works without
it.

| What you want | Something that gets it |
| --- | --- |
| Start a review | `review this branch in the browser` |
| A different base | `open the web reviewer for my branch against develop` |
| A narrative, after it has read the branch | `now write the narrative and rebuild the page` |
| A change you asked for in a thread | `do it` in the thread, or `yes, apply that` |
| Rebuild after new commits | `rebuild the review page` |
| Put this review's threads aside | `archive the threads for this review` |
| Threads from an older layout | `move my old threads into the right review` |
| Where the files are | `where does this review keep its files?` |
| Finish | `squash the fixups and stop the review server` |

The wording does not matter. Asking to read a diff in a browser, or to ask questions while
reading one, is enough for Claude Code to open the skill.

## How a question reaches Claude

A question you ask on the page is written to a file, and nothing reads that file by
itself. If the Claude Code session never started the watcher, every question sits there
unanswered and nobody is told.

Claude Code arms the watcher when it opens the review, following `SKILL.md`. You do not
run any of this. If answers stop arriving, say `no answers are coming through, check the
watcher`.

What it runs, once, for as long as the review lasts:

```bash
python3 tool/watch.py --range origin/main...my-branch
```

Every question and reply becomes one line on its stdout:

```
QUESTION cb8d21a9b6ad · commit b7aab66 · index.md:47 (add) · Where are those checks applied?
REPLY in thread cb8d21a9b6ad [skip] · No, skip the investigation.
```

The session answers into the thread by id:

```bash
printf '%s\n' "Inside Postgres, on every query." | python3 tool/answer.py cb8d21a9b6ad
```

The page does not hide this. While a watcher is attached a thread shows the pulsing
"waiting for an answer"; with nothing attached it says so instead, and the question is
kept. When a session arms the watcher later, the watcher replays every thread still owed
an answer.

A review's threads are its own. Two reviews of one checkout keep separate logs, so a
question asked while reading one branch never appears on the other's page.

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
| `Mark reviewed` | Tick a commit off; the squash bar waits until every commit is ticked |
| `Commits` / `Files changed` | The two ways of reading, above the rail |

## Change requests, and why fixups

Reply `do it` in the thread and the change lands as a fixup, never as an amend. What that
means in git:

```bash
git commit --fixup=b7aab66          # the reviewed commit keeps its sha
git rebase -i --autosquash e8e4bb6  # once the review is over
```

A thread is anchored to a commit's sha, so amending a reviewed commit changes that sha and
orphans every thread on it. A fixup leaves the reviewed commits alone.

The page folds each fixup into the commit it amends and marks it as one, so the rail
stays as long as the change rather than growing with every correction. A fixup whose
target is outside the range stays a commit of its own.

When every commit is ticked, the page offers to squash. It refuses when:

| | |
| --- | --- |
| the range has no base commit | nothing to rebase onto |
| a tracked file has uncommitted changes | untracked files do not count, since a rebase does not care about them |
| a rebase is already in progress | |
| there are no fixups in the range | nothing to squash |
| commits in the range are already pushed | the only refusal it offers to override, after saying what a force push costs |

It writes a `pre-squash/<stamp>` branch first, and a rebase that does not apply is aborted
and rolled back rather than left half done.

Squashing rewrites every commit in the range, so the threads on them are orphaned. They
are not lost: the page keeps them in their own section, and they stay readable and
answerable there.

See `git help rebase` for what `--fixup` and `--autosquash` do.

## Use it without Claude Code

The page and the server run without Claude Code. From inside any git repo:

```bash
python3 ~/.claude/skills/web-reviewer/tool/review.py serve origin/main...HEAD
```

You get the diff reader and the thread UI. Questions are appended to
`questions.jsonl` in that review's folder, and anything that appends an answer to
`messages.jsonl` beside it shows up in the thread, so the Claude Code integration is one
consumer rather than a requirement. The next section says where that folder is.

`tool/answer.py` writes those turns. A plain turn is an answer; `--ask` marks it as a
question back to the reviewer, which the page offers a button to answer; `--did` records
a change with the commit that carried it.

State lives outside the repo, so questions never land in git and survive rebuilds and
restarts. The next section says where it goes and what removes it.

## Where state lives, and when it is cleaned

### Where it goes

Threads live outside the repo, in a directory named for the repo plus a hash of its
absolute path, so two checkouts of the same project never collide:

```
~/.local/state/web-reviewer/<repo-name>-<hash>/
```

Ask Claude Code `where does this review keep its files?`, or run `review.py where`.

Everything a review has is in one folder: the page, the narrative, and the threads asked
while reading it.

### What each file holds

| File | What it holds |
| --- | --- |
| `questions.jsonl` | One row per thread: the question, the branch it was asked on, and the commit, file, side and line it is anchored to |
| `messages.jsonl` | Every turn after the opening question, with who wrote it and what kind it is: an answer, a question back to the reviewer, a change that was made, or the reviewer's yes or no to one |
| `resolved.jsonl` | One row each time a thread is resolved or reopened |
| `answers.jsonl` | An older reply format. Nothing writes it now, and it is still read, so old reviews still render |
| `narrative.json` | The narrative for this review, if it has one |
| `index.html` | The rendered page, rewritten by every build |
| `watcher.alive` | A heartbeat, rewritten every second while a watcher runs, and removed when it stops. The page reads it to know whether anyone is listening |
| `archived-<stamp>/` | Logs put aside by `review.py archive` |

```
api-bbfa229b/                                          the checkout
  origin-main-ft-868m0r34p-django-mfa-46000731/        one review
    index.html
    narrative.json
    questions.jsonl
    messages.jsonl
    resolved.jsonl
  7568e62a7547c0295d1cb-ci-check-unsafe-migrations-9ce5ede9/
    index.html
    narrative.json
```

### How a review gets its name

If you review two different ranges of the same repo, those are two separate reviews and
they need separate folders. Sharing one folder went wrong twice over: each server said the
other's page was out of date, and each Rebuild button overwrote the other page.

So each review gets its own folder, and the files inside keep ordinary names. The narrative
you edit by hand is always `narrative.json`, and the folder around it tells you which
review it belongs to.

The folder is named after the range, so you can recognise it in `ls`, plus a short hash so
two ranges can never produce the same name. Long names are trimmed from the front, because
a range ends with the branch and that is the half worth reading.

One thing happens first: `HEAD` is replaced with the name of the branch it currently points
at. `HEAD` just means "wherever I am right now", so it is not a name for anything. The
default range is `origin/main...HEAD`, and without this step every branch you reviewed in
one checkout would write to the same folder, and the second would overwrite the first. The
swap happens once, when the review starts, and both the page and the server carry the
result. Switching branches while the server is running cannot move it.

### Why a review keeps its own threads

Reading a review costs what that review holds. When the threads were shared by the whole
checkout, every poll parsed every question ever asked in it: at two thousand threads that
was 3 MB read every second by the watcher and 3 MB sent every four by the server.

The server reads those logs and never serves them. It answers six endpoints and returns
`index.html` at `/`, and there is no directory behind it, so nothing that lands in a
review folder can be fetched over the port.

Anything else in the store was put there by whoever started the server, not by the tool.
It writes nothing outside this list.

### What is never removed

The four logs are only ever added to, never edited. A question is written the whole way to
the disk before the browser is told it was accepted, so a crash straight afterwards cannot
lose it. Nothing rewrites a row. Resolving a thread appends a row saying
so rather than removing anything, which is what makes it reversible, and `Hide resolved`
filters data that is all still on disk.

**Nothing ever cleans these files.** There is no retention rule, no pruning, and no
command to forget a review. The only file the tool deletes is the watcher's heartbeat.

To put a review's questions aside, ask for `archive the threads for this review`. To be
rid of a checkout's state entirely, say so and Claude Code will show you the directory
before removing it, or do it yourself:

```bash
rm -rf ~/.local/state/web-reviewer/<repo-name>-<hash>
```

Two reviews measured on this machine are 33 KB each: one of five threads with twenty
three replies, one of twelve threads. The directories are what accumulate, one per repo
path, including repos you have since moved or deleted. Moving a repo changes the hash, so
the next run starts empty while the old threads stay under the old name.

`index.html` is the only file here that can be lost safely: `rebuild the review page`
makes it again from git and the narrative. Everything else was written by a person: the
threads, and the narrative, which is prose somebody wrote about a branch and which no
command produces again.

Ask Claude Code to `archive the threads for this review`, or run `review.py archive
<range>`. It moves that review's logs into a timestamped subfolder, so finishing one
branch does not touch the review of another you are still reading. Nothing is deleted,
and moving them back is one `mv`.

The `pre-squash/<stamp>` branches a squash leaves behind are the same kind of leftover.
Nothing removes them either, and they are yours to delete once you trust the result.

## The narrative layer

With no configuration the page takes its title from the branch, its figures from git, and
each commit's rationale from that commit's own message.

Ask for it once the branch has been read: `now write the narrative and rebuild the page`.
Claude Code runs `review.py narrate <range>`, which writes a scaffold next to the review's
state: every commit keyed by sha with its subject, every file in the range by path, and
every field empty.
Fill in what you know and rebuild. Every later build reads that file without a flag.
`--narrative FILE` points at one kept elsewhere.

It adds a data-flow strip, per-commit rationale, verification tables and a list of open
questions. It also carries the two things the tool cannot determine: where to start, and
what a file is for.

```json
{
  "title": "MFA for Django Admin",
  "stages": [
    { "where": "every admin request", "what": "AdminSite.has_permission covers admin views",
      "marks": ["1", "12", "13"] }
  ],
  "commits": {
    "41a8d1143": { "read": "care", "readWhy": "the wizard asks its step conditions twice" }
  },
  "files": {
    "api/urls.py": { "read": "start", "note": "where the wizard is mounted" }
  }
}
```

The tool can order a file and weigh how much of the branch is in it. Only a person can say
that `api/urls.py` is where the wizard is mounted.

The build keeps the marks scarce. One commit may be the place to start, `skim` has to say
why skipping is safe, and a reason runs to 80 characters. Reaching a limit means cutting
the text rather than raising the limit.

Every field is optional and falls back to git, and sections with no content stay hidden,
so a half-written narrative renders as the plain page rather than as empty frames. See
[reference/narrative.md](reference/narrative.md).

Write it while the branch is fresh. A session that has just built the code can tell you
what it was unsure about and what it never checked. A later session is reading the diff
like anyone else, and a reason it works out from the code looks exactly like a reason it
remembers, so you cannot tell the two apart. A session that has spent an hour answering
review questions does not remember the work any better than a new one, and may remember it
worse.

## Layout

| Path | What it is |
| --- | --- |
| `SKILL.md` | Instructions for the agent |
| `.claude-plugin/` | The plugin and marketplace manifests |
| `.claude/skills/release/` | How to cut a release. Loads when working in this repo, and is not shipped to users |
| `reference/narrative.md` | The optional editorial layer |
| `reference/voice.md` | How the page's own copy is written |
| `reference/gotchas.md` | Operational traps worth not rediscovering |
| `tool/review.py` | Build and serve |
| `tool/build_data.py` | Git range to page data |
| `tool/paths.py` | Where the repo is and where state lives |
| `tool/review.tpl.html` | The page |
| `tool/server.py` | The page at `/`, plus `/thread` `/ask` `/reply` `/resolve` `/rebuild` `/squash` |
| `tool/answer.py` | Write a turn into a thread |
| `tool/watch.py` | Emit new questions and replies as events |
| `tool/smoke.js` | Run the built page's script, so a page that throws is not served |
| `tool/narrative.example.json` | A narrative to copy from |

## What a version promises

Three surfaces are covered by the version in
[`.claude-plugin/plugin.json`](.claude-plugin/plugin.json), and will not change under you
without a major bump:

- The prompts in [What to say](#what-to-say).
- The narrative file: its keys, its marks, and its length limits.
- The command line of `review.py`, `answer.py` and `watch.py`.

The state directory's layout is not one of them. It is internal, and a page rebuilds from
git. [CHANGELOG.md](CHANGELOG.md) records what moved and when.

## Scope

The server binds `127.0.0.1` and has no authentication: anything that can reach the port
can read and append, and `/squash` rewrites history in the repo it was started from. It is
a local review tool, not a service. Do not bind it to a routable interface.
