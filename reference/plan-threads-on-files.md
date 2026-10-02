# Moving questions to the Files changed tab

Built. This is the design, and the measurements it rests on.

Files changed is the tab that opens and the one a reviewer reads. Questions could only be
asked on Commits, because a thread anchored to `(commit, file, side, line)` and a line there
has a commit behind it. So the reader was in one place and the asking in another.

## Threads live on one tab, not two

The first version of this plan kept both and tried to make one anchor mean the same thing
in each. It cannot. A commit's diff numbers lines in that commit's version of the file; the
final diff numbers them in the final version. Measured on a real branch, the same physical
line gets the same number in both views **23% of the time**:

```
added rows where both tabs agree on the line number : 178
added rows where they do not                        : 580
```

One home means one coordinate system, and the problem disappears.

## Anchored the way a pull request comment is

A review comment on GitHub is `(file, side, line)` in the pull request's own diff, with no
commit in it. A thread here records the same thing, in the final diff's coordinates.

Two reasons beyond simplicity. A reviewer often reads the same change in both places, and
the two anchors then name the same location. And it settles what happens when the branch
moves: see below.

The commit is still worth recording, because `git blame` on the tip knows it for any
surviving line, and it is useful to show. It is not part of the anchor.

## The diff changes, so a thread goes outdated

A question leads to a fixup, the fixup changes the final state, and the final state is what
the anchor points into. This is unavoidable in a view of the final state.

GitHub marks such a comment **outdated** and leaves it where it was asked. This does the
same. Re-anchoring is a text match, and a file has repeated lines:

```
6 times:  )
5 times:  """
3 times:  header, lines = get_header_and_lines_from_csv_file(file)
```

A thread placed on the wrong `)` is worse than one marked as no longer matching, so a
thread is re-anchored only where the match is exact and unique, and marked outdated
otherwise. That is the same judgement the orphan list already makes.

## Removed lines have to be visible

A reviewer asks "why did you drop this", and today there is nothing to click.

`renderFileLines` seeds its windows from `runs`, which are blame-derived surviving line
numbers. A deleted line has no line number to match on, so it appears only when it happens
to sit within three rows of a surviving line:

```
deleted lines in the final diff : 56
a stage pane renders            : 49   (incidentally, as context)
never shown                     : 7
```

A deletion standing on its own is invisible, and "Show the whole file" cannot help, because
the line is not in the file.

So a window is seeded from a deleted line too. Which stage owns it comes from reverse
blame: `git blame --reverse merge-base..tip` names, for each line of the file as it was,
the last commit that still had it. The tip means the line survived; any other answer means
the commit after that one took it out.

The first attempt matched removals by line text, read from the commits' own diffs. It was
measured on this branch and looked clean, and it was wrong in two ways the branch did not
happen to show. Text cannot tell two deletions of the same text apart, so every stage got
every line whose text it had removed anywhere in the file — a pane drawn around a deletion
thirty lines away that the stage had nothing to do with. And a commit's diff names a file
as it was, so a rename between the removal and the tip matched nothing at all. Seven to
ten percent of deleted lines on this repo's own history share text with another deleted
line in the same file; a braces-and-blank-lines codebase would be far higher.

Reverse blame has neither problem: it is per line, not per text, and blame crosses a
rename. It costs one `git blame` per file with deletions, roughly 7 to 45 ms per changed
file, the same order as the forward blame already being run.

Both the blame and the walk go along first parents. Without that, blame answers with the
last commit *anywhere in the range* that held the line, which across a fork is a commit on
the other side that never touched it; and pairing each commit with the next one `rev-list`
prints made a commit on one side the successor of a commit on the other. Measured on a
branch with two parallel removals merged together, the removals were credited to the wrong
side and to the merge, and the stage that made one of them fell off the rail. Along first
parents a side branch's work belongs to the merge that brought it in, which is also where
a reader of the branch meets it.

Membership follows from it. A stage listed on a file only when blame found surviving lines
for it is a stage that can never be listed for a removal, because a removed line is not
there to blame. So a stage earns a file through a removal too — but only a removal it made
on its own account. A stage that replaced a line and was replaced in turn has nothing of
its own left, and its removal reads as part of the edit that overtook it.

That is read per hunk, not per file. Over the whole file it also caught a stage whose
removal and whose addition were separate edits: the addition was rewritten by a later
stage, the removal still stood, and the stage lost both. A hunk the stage took lines out
of without putting any back is the stage's own work, whatever else it did elsewhere in
the same file.

One ceiling: a file emptied out is a removal per line, whether or not the file itself is
gone, so seeding a window from each of them draws the whole of it back into the page. Past
`MAX_GONE_ROWS` the pane says what the stage did instead. Gating that on the file being
deleted missed a file the branch guts but keeps, which is at least as common.

This is worth doing on its own, before any of the thread work. A view of the branch as it
stands should show what the branch removed.

## The narrative does a different job

A removal that is expected needs framing, not a question: `each row, checked` already says
"The legacy pass shares the loop and keeps its query". A removal that is surprising needs a
question, and that is what has no home today. Both, for different moments.

Note the room available. A stage's `what` is capped at 120 characters and a file note at 80.
Neither fits an explanation of a strategy change; a "before you push" note has no cap and is
where that belongs.

## What happens to the threads already written

They are in commit coordinates and cannot be translated reliably: 78% of added lines can be
placed in the final diff, 45% of deleted ones, 56% of context.

So they are not translated. They keep their own section, the way orphans do now, labelled
as asked on the commits view. That keeps what people wrote without building a translation
layer that is a heuristic in both directions.

## Order of work

1. ~~Render removed lines deliberately, attributed by stage.~~ Done.
2. ~~Make a row on the files tab askable.~~ Done.
3. ~~Anchor in final-diff coordinates, and mark a thread outdated when the diff no longer
   matches.~~ Done. The anchoring came with step 2; what step 3 added is the placing:
   a thread follows its text where there is one of it, and says it is out of date where
   there is not.
4. ~~Move the existing threads into their own section.~~ Done. The Commits tab is read
   only now: one tab holds the asking, so there is one coordinate system. Its threads are
   listed at the end of Files changed with a way to the line they were asked on, and still
   drawn on that line; one whose commit has gone is an orphan, as before.

## What this costs

The anchor format changes. `questions.jsonl` gains rows that mean something different from
the ones already in it, and every reader of that file has to tell them apart. That file is
in the state directory, which the version does not cover, and every row already on disk
still reads, so it shipped as a minor version rather than the major one this section
first called for.

The risk is in `paintThreads`, which runs every four seconds and which two separate reviews
have already found bugs in. It got its own QA round, which found seven more, each fixed
with a check that fails without the fix.
