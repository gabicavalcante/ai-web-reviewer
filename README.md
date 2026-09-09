# web-reviewer

Read a branch's diff in a browser and ask questions about individual lines, with the
answers appearing inline next to the code.

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
- Click any line number to open a thread anchored to that commit, file and line.
- Threads reach your Claude Code session, and answers render in place.
- Mark threads resolved, reopen them, hide the resolved ones.
- Threads survive rebuilds, restarts and rebases. When a rebase orphans one, the page
  shows it in its own section rather than dropping it.

## Install

```bash
git clone https://github.com/<you>/web-reviewer ~/development/personal/web-reviewer
ln -s ~/development/personal/web-reviewer ~/.claude/skills/web-reviewer
```

Then ask Claude Code to review a branch in the browser, or invoke `/web-reviewer`.

## Use it without Claude Code

The page and the server stand alone. From inside any git repo:

```bash
python3 ~/.claude/skills/web-reviewer/tool/review.py serve origin/main...HEAD
```

You get the diff reader and the thread UI. Questions are appended to
`~/.local/state/web-reviewer/<repo>-<hash>/questions.jsonl`, and anything that appends an
answer to `messages.jsonl` shows up in the thread, so the Claude Code integration is one
consumer rather than a requirement.

## The narrative layer

With no configuration the page takes its title from the branch, its figures from git, and
each commit's rationale from that commit's own message.

Pass `--narrative FILE` to add a data-flow strip, per-commit rationale, verification
tables and a list of open questions. Sections with no content stay hidden, so the plain
page never shows an empty frame. See [reference/narrative.md](reference/narrative.md).

## Layout

| Path | What it is |
| --- | --- |
| `SKILL.md` | Instructions for the agent |
| `reference/narrative.md` | The optional editorial layer |
| `reference/gotchas.md` | Operational traps worth not rediscovering |
| `tool/review.py` | Build and serve |
| `tool/build_data.py` | Git range to page data |
| `tool/review.tpl.html` | The page |
| `tool/server.py` | Static files plus `/thread` `/ask` `/reply` `/resolve` |
| `tool/answer.py` | Write a turn into a thread |
| `tool/watch.py` | Emit new questions and replies as events |

## Scope

The server binds `127.0.0.1` and has no authentication: anything that can reach the port
can read and append. It is a local review tool, not a service. Do not bind it to a
routable interface.
