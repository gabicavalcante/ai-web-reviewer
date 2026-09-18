# Moving questions to the Files changed tab

Not built. This is the design, and the measurements it rests on.

Files changed is the tab that opens and the one a reviewer reads. Questions can only be
asked on Commits, because a thread anchors to `(commit, file, side, line)` and a line there
has a commit behind it. So the reader is in one place and the asking is in another.

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

So a window is seeded from a deleted line too. Which stage owns it comes from the commits'
own diffs: the stage whose commit removed a line with that text. Measured on the same
branch:

```
deleted lines the final diff shows  : 56
attributable to exactly one stage   : 56
claimed by more than one stage      : 0
```

Clean on this branch, and a heuristic in general. Where two stages removed the same text,
show it under both rather than guessing.

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

1. Render removed lines deliberately, attributed by stage. Useful alone.
2. Make a row on the files tab askable: the click handler, the composer, and `/ask` already
   work from a row's dataset.
3. Anchor in final-diff coordinates, and mark a thread outdated when the diff no longer
   matches.
4. Move the existing threads into their own section.

Steps 1 and 2 are each worth having on their own, which is the order to build them in.

## What this costs

The anchor format changes, so this is a major version. `questions.jsonl` gains rows that
mean something different from the ones already in it, and every reader of that file has to
tell them apart.

The risk is in `paintThreads`, which runs every four seconds and which two separate reviews
have already found bugs in. It should get its own QA round.
