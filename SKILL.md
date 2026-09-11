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
you post into a thread. Run the `deslop` skill over it before you build the page.

Then remove all mannered prose. Mannered prose is metaphor and flourish standing in for
direct statement: "a dial worth turning" instead of "a parameter worth varying". It makes
the reader work harder so the writer can perform, and it is imprecise, because a metaphor
carries connotations you did not choose. Say what you mean, and use the literal phrase
whenever one exists. [reference/voice.md](reference/voice.md) has the rule in full.

A reviewer reads this, often not in their first language, so the implementation's
vocabulary does not belong in the interface. `halt` is `skip`; `arm` is `turn on`; `your
call` is `waiting for you`. Keep the code's own terms, which are precise and already
known.

Never print a claim you have not computed. A line like "working tree clean" is wrong on
most branches. Watch the definite articles too: "the boundary" is anchored for you and
points at nothing for the reader. [reference/voice.md](reference/voice.md) has the word
list and the rules.

## The narrative layer

With no narrative the page is a good diff reader: title from the branch, figures from
`git`, each commit's "why" from its own message, and the editorial sections hidden.

After you have actually reviewed the branch, `python3 $TOOL/review.py narrate <range>`
writes a scaffold into the state directory: every commit keyed by sha with its subject,
and every field empty. Fill in what you worked out and rebuild. It is picked up on every
later build without a flag, so `--narrative FILE` is only for keeping one somewhere else.

Fill in nothing you have not earned. Every field falls back to git when left empty, so a
scaffold you only half understand renders as the honest plain page. Annotate the commits
that need it and leave the rest. See [reference/narrative.md](reference/narrative.md) and
[tool/narrative.example.json](tool/narrative.example.json).

Do not invent a narrative you have not earned. A fabricated "data flow" is decoration,
and the fallback page is honest.

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
