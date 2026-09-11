---
name: web-reviewer
description: Serve a branch's diff as a local web page the reviewer reads in a browser, with inline question threads anchored to individual diff lines that reach Claude and get answered in place. Use when the user asks to review a branch or PR in a browser, wants a "web reviewer", asks for a diff UI instead of terminal output, wants to ask questions while reading a diff, or when a change is large enough that scrolling terminal diffs will lose them.
---

# Web reviewer

A local page that renders `git` commits as a readable diff and carries the reviewer's
questions back to you. Threads anchor to a specific commit, file and line, so neither of
you has to describe which code is under discussion.

## Run it

The scripts live in `tool/` inside this skill's own directory, which the harness prints
when the skill loads. Installed as a user skill that is:

```bash
TOOL="$HOME/.claude/skills/web-reviewer/tool"
python3 $TOOL/review.py serve                      # origin/main...HEAD
python3 $TOOL/review.py serve <base>..HEAD          # any range
python3 $TOOL/review.py where                       # print the state directory
```

It prints the URL, picking the next free port when 8777 is taken. Run it with
`run_in_background: true` so it survives the turn, then **arm the watcher** or no question
will ever reach you:

```
Monitor(command: "python3 $HOME/.claude/skills/web-reviewer/tool/watch.py",
        description: "questions on the diff review page", persistent: true)
```

Each new question or reply arrives as an event carrying the thread id, commit, file and
line. Reply into the thread:

```bash
printf '%s\n' "your answer" | python3 $TOOL/answer.py <thread-id>
printf '%s\n' "needs a repo sweep, want it?" | python3 $TOOL/answer.py --ask <thread-id>
printf '%s\n' "renamed it" | python3 $TOOL/answer.py --did <thread-id> <sha>
```

`--ask` asks permission to spend real time — a repo-wide sweep, subagents — before
answering. It is not for offering a change: say that in a plain answer, because the page
renders every `--ask` as a request to investigate. `--did` records a change with the
commit that carried it, so the thread reads *asked → answered → changed*.

## Judge complexity yourself

Answer from context when you can. When a question needs a repo-wide sweep, say what you
would have to check and use `--ask`; spawn subagents only after the reviewer says yes.
Never make them choose the cheap or expensive path up front, because they cannot see what
is already in your context. Fan several approved investigations out in parallel.

## Change requests land on top, never in place

A request in a thread is a request: make it. Commit it as `git commit --fixup=<sha>` so
the reviewed commits keep their hashes, then report it with `--did`. Squash with
`git rebase --autosquash` only once the review is finished.

Amending a reviewed commit changes its hash and shifts its line numbers, which orphans
every thread anchored to it. The page surfaces orphans in their own section rather than
hiding them, but the anchor is still lost. Do not amend mid-review unless asked, and say
what it will cost when you do.

## The build checks itself

`review.py build` runs the page's script against a minimal DOM (`tool/smoke.js`) when
`node` is available, and refuses to serve a page whose script throws. A page that throws
draws its header and then stops, which looks like missing data rather than broken code.
Without node the check is skipped with a message, so read the page before trusting it.

## Write the copy for a person

This covers everything you write here: the narrative fields, any new label, every answer
you post into a thread, and what you report back in the session. Run the `deslop` skill
over it, then read [reference/voice.md](reference/voice.md), which holds the rules. It is
short.

One test carries most of it. **Would you say this sentence to a colleague standing at
their desk?** "Staff must verify an authenticator code before Django Admin will serve them
anything" fails it. "Django Admin users should set authenticator code as MFA factor" is
the same fact, said. Name the thing rather than describing it, state the fact rather than
its effect on the reader, and remove all mannered prose, which is metaphor standing in for
direct statement.

Never print a claim you have not computed. A line like "working tree clean" is wrong on
most branches.

Some of this is enforced rather than asked for. `answer.py` refuses a thread answer over
1200 characters unless you pass `--long`, and the build refuses a `readWhy` over 80
characters, a stage `what` over 120, and a commit `why` over 450. Reaching a limit means
cut.

## The narrative layer

With no narrative the page is a good diff reader: title from the branch, figures from
`git`, each commit's "why" from its own message, and the editorial sections hidden.

After you have actually reviewed the branch, `python3 $TOOL/review.py narrate <range>`
writes a scaffold into the state directory: every commit keyed by sha with its subject,
and every field empty. Fill in what you worked out and rebuild. It is picked up on every
later build without a flag, so `--narrative FILE` is only for keeping one somewhere else.

Fill in nothing you have not worked out. Every field falls back to git when left empty, so
a scaffold you only half understand renders as the plain page, which is the honest one. A
data flow you inferred from the folder layout is decoration, and it will be read as though
someone had checked it. Annotate the commits that need it and leave the rest. See
[reference/narrative.md](reference/narrative.md) and
[tool/narrative.example.json](tool/narrative.example.json).

## Which commits to mark

`read` tells the reviewer what to do with a commit: `start`, `care`, `skim`, or nothing.
Most commits get nothing, and for most branches that is the whole of it.

Mark from what the reviewer needs, not from what the work cost you. The commit that took
longest is often the one that needs the least checking, and the change worth checking is
often three lines.

- `start` is the commit that makes the rest readable, usually where the mechanism first
  appears. It is not always the first one. Only one commit can have it.
- `care` is where behaviour changes in a way the reader has to check for themselves, and
  where you were unsure or did not verify something. Say which in `readWhy`.
- `skim` is mechanical: a move, a rename, formatting, generated output, tests that follow
  from a change already reviewed. The reason has to be enough for the reviewer to trust
  the skip, so name what makes it mechanical.

If you cannot say why a commit is safe to skim in under 80 characters, it is probably not
a skim.

## Where state lives

Threads are append-only JSONL in `~/.local/state/web-reviewer/<repo>-<hash>/`, keyed by
repo path, outside the repo so questions never land in git. They survive rebuilds,
restarts and rebases. The rendered `index.html` sits in the same directory.

Rebuild after new commits: `python3 $TOOL/review.py build <range>`, then reload.

## When the review is over

Nothing here stops on its own, and both halves have to be stopped separately.

The server is started in the background, so it reparents to init and outlives the terminal
that launched it, still holding its port. The watcher tails the logs, not the server, so
killing the server leaves it running; it ends when the session does, or when you stop it.

```bash
REPO=$(git rev-parse --show-toplevel)
for pid in $(ps -eo pid= -o args= | awk '/[s]erver\.py/ {print $1}'); do
  [ "$(readlink /proc/$pid/cwd)" = "$REPO" ] && kill "$pid"
done
```

Then `TaskStop` the Monitor. Read [reference/gotchas.md](reference/gotchas.md) before
adapting that loop — the pattern and the cwd are both easy to get wrong in ways that
silently find nothing.

Stopping costs nothing: threads are on disk, and a later session that re-arms the watcher
is handed everything still owed an answer. Leave them running only while the reviewer is
still reading, and if you do, tell them the URL and that questions will reach you for as
long as this session lives.

## Before you touch a running server

Read [reference/gotchas.md](reference/gotchas.md). The short version: never `pkill -f` a
pattern that appears in your own command line, find the server by pid and
`/proc/<pid>/cwd`, bound every `curl` with `--max-time`, and never probe a port by
connecting to it. The Monitor dies with the session while the page keeps recording
questions; re-arming it replays every thread still owed an answer, and while nothing is
attached the page says so instead of showing a spinner.
