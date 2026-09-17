# Asking a question on the Files changed tab

Not built. This is the plan, written while the reasoning was fresh.

Today a thread can only be asked on the Commits tab, because the page needs a commit to
anchor it to and a line there has one. Files changed is the tab that opens, and it is the
branch as it stands, so it is where a reviewer is reading. They cannot ask there.

## Why it is possible at all

A thread anchors to `(commit, file, side, line)`. The files tab has three of the four and
appears to be missing the commit. It is not: `git blame` on the tip of the range says which
commit each surviving line came from, `surviving_lines()` already returns exactly that, and
the numbers it returns are the same new-side line numbers the final diff's `add` rows
carry. The build runs that pass on every file already, to weigh the stages.

So the commit is known. It is thrown away, because `runs` keeps the result grouped by stage
rather than by commit.

## What is attributable

Measured on `origin/main..ft/868kmk8v6-2-patent-partial-validators`, 14 commits, 9 files:

| row | attributable to a commit in the range |
| --- | --- |
| `add` | 758 of 787 |
| `ctx` | 5 of 134 |
| `del` | 0 of 56 |

Added lines are the case, and they are the lines people ask about. Context is mostly
pre-branch, which is the right answer rather than a gap. The 29 unattributed additions are
credited to commits outside the range, which a rename carrying content across will do.

Deleted lines cannot be attributed at all. Blame reads the file as it stands and a removed
line is not in it.

## The change

**`build_data.py`**. Keep the per-commit owner alongside the per-stage runs. The blame
pass already produces `sha -> [line numbers]` per file; `runs` reduces it to stages and
drops the shas. Emit both. One dict, no new git call.

**`review.tpl.html`**. Two edits.

`renderFileLines` sets `tr.dataset.commit` from that map, the way `renderFile` already does
from `commitShort`. Once a row carries a commit, the existing click handler, composer and
`/ask` call work unchanged: they read `tr.dataset.commit`.

`paintThreads` and `VALID_ANCHORS` have to cover the files pane. `board()` is hardcoded to
`#board` and every scan for a row runs over that subtree, which was deliberate: the files
view holds a second copy of the branch and the poll walks it every few seconds. Both panes
means either scanning both or scanning the visible one.

**`server.py`**. Nothing to do: the anchor format does not change.

## Why it is additive

Same four-part key, same shas, nothing on disk changes, no migration. A thread asked on
either tab shows on both, because both know which commit owns the line. Every thread
already written keeps working.

That is the strongest argument for doing it this way rather than inventing a file-level
anchor that does not need a commit.

## The question to settle first

What a question on a **deleted** line means. There is no commit behind it, so either:

- the files tab does not offer a question on a removed line, which is honest and loses
  something a reviewer plainly wants; or
- such a thread anchors to the file with no commit, which is a second kind of thread, and
  the orphan logic, the squash warning and `VALID_ANCHORS` all assume there is a commit.

This is a design decision, not an engineering one, and it should be made before the code.

## Cost

A day, not a week. The plumbing is small because the anchor is unchanged. The risk is in
`paintThreads` covering two panes, which is the part of the page that runs every four
seconds and the part two separate QA rounds have already found bugs in.

Do it on its own, with its own QA round. It is the largest change to how threads work since
they existed.
