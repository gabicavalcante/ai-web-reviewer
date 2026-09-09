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

`--ask` renders a go-ahead button instead of a spinner, so a question back to the reviewer
never looks like a stalled answer. `--did` records a change with the commit that carried
it, so the thread reads *asked → answered → changed*.

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

## Write the copy for a person

Before you build the page, run the `deslop` skill over every string you wrote: the
narrative fields, any new label, any answer you post into a thread. A reviewer reads this,
often not in their first language, so the implementation's vocabulary does not belong in
the interface. `halt` is `skip`; `arm` is `turn on`; `your call` is `waiting for you`.
Keep the code's own terms, which are precise and already known.

Never print a claim you have not computed. A line like "working tree clean" is wrong on
most branches. [reference/voice.md](reference/voice.md) has the word list and the rules.

## The narrative layer

With no narrative the page is a good diff reader: title from the branch, figures from
`git`, each commit's "why" from its own message, and the editorial sections hidden.

After you have actually reviewed the branch, write a `narrative.json` and pass
`--narrative FILE` to add the data-flow strip, per-commit rationale, verification tables
and open questions. Annotate only the commits that need it; the rest fall back. See
[reference/narrative.md](reference/narrative.md) and
[tool/narrative.example.json](tool/narrative.example.json).

Do not invent a narrative you have not earned. A fabricated "data flow" is decoration,
and the fallback page is honest.

## Where state lives

Threads are append-only JSONL in `~/.local/state/web-reviewer/<repo>-<hash>/`, keyed by
repo path, outside the repo so questions never land in git. They survive rebuilds,
restarts and rebases. The rendered `index.html` sits in the same directory.

Rebuild after new commits: `python3 $TOOL/review.py build <range>`, then reload.

## Before you touch a running server

Read [reference/gotchas.md](reference/gotchas.md). The short version: never `pkill -f` a
pattern that appears in your own command line, find the server by pid and
`/proc/<pid>/cwd`, bound every `curl` with `--max-time`, and remember the Monitor dies
with the session while the page keeps recording questions.
