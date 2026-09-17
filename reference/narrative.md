# The narrative layer

`narrative.json` adds the editorial layer to a page that already works without it. Every
key is optional; anything absent falls back to git.

| Key | Effect when present |
| --- | --- |
| `title` | Page title and browser tab. Default: derived from the branch name. |
| `dek` | The sentence under the title. Default: commit count and range. |
| `eyebrow` | A short qualifier in the top rule, e.g. `quality pass, no behaviour change`. |
| `figures` | The stat row. Each `{k, v, was?}`; `was` renders struck through, for a before/after. |
| `stages` | The data-flow strip. Each `{where, what, marks}` where `marks` are commit numbers. |
| `notes` | The "Before you push" cards. Each `{kind, title, body, tone}`; `tone: "info"` for neutral. |
| `commits` | Per-commit narrative, keyed by any unambiguous sha prefix. |

Per commit: `stage` (the rail label, e.g. `2 · Arm`), `flow` (where it sits in the data
flow), `why` (one or two sentences), `points` (specific consequences), and `matrix`
(rows of `[case, got, want, ok]` for a verification table).

## Saying what a file is for

`files` is keyed by path, and carries the same two things a commit carries: a `read` mark
and one line of prose.

```json
"files": {
  "api/urls.py": { "read": "start", "note": "where the wizard is mounted" },
  "common/auth/django/admin_mfa.py": { "note": "the gate every admin request passes" },
  "common/tests/test_admin_mfa.py": { "read": "skim", "note": "covers the wizard end to end" }
}
```

The tool can order a file and weigh how much of the branch is in it. It cannot say what
the file is for, and that sentence is what a list of twenty files is read by.

One file per stage may be `start`, because a stage has one place to begin. `skim` needs a
note saying why skipping is safe, and a note runs to 80 characters, which is the room it
has beside a path. A path the range does not contain warns rather than failing, since a
rebase moves files out from under a narrative.

## Telling the reviewer what to read first

`read` marks a commit in the rail, with `readWhy` giving the reason on one line. This is
the comment a person leaves on a pull request: "this one is just tests", "start here".

| `read` | Means |
| --- | --- |
| `start` | Read this first. One commit only. |
| `care` | The important one. Read it closely. |
| `skim` | Little to review. `readWhy` has to say why it is safe to skim. |

```json
"41a8d1143": { "read": "skim", "readWhy": "moved to another file, no behaviour change" }
```

A `skim` commit is dimmed in the rail rather than hidden, and can still be opened.

Say what the change is in `readWhy`, not in the mark. Three words are deliberate: they say
what the reviewer should do, and a longer list would turn into a classification exercise.

The build enforces the limits, because a mark on every commit marks nothing:

- More than one `start` fails the build.
- `skim` without a `readWhy` fails the build.
- A `readWhy` over 80 characters fails the build. It has one line in the rail.
- `care` warns past a third of the commits, and past five however long the branch is. A
  third of forty is thirteen, and nobody keeps thirteen in mind.

## What the rail marks on its own

Blame at the tip of the range says how many of a commit's lines are still in the branch.
Two marks follow from that, and neither needs a narrative:

| What blame says | What the rail does |
| --- | --- |
| nothing left | marks the commit `skim`, reason `nothing it added is still in the branch` |
| less than half left | prints `12 of 77 survive` beside the diff numbers |

The first only fills a gap. A commit the narrative already marked keeps the mark it was
given, and the counts are not printed underneath a line that has just said the same thing.

On a branch that was reworked in place this covers most of the rail. Without it a reviewer
reads fifteen commits before discovering that ten of them no longer exist.

Blame runs with `-M`, so a block a later commit copied inside a file is still credited to
the commit that wrote it, and a commit can be blamed for more lines than it added. One
commit on a real branch added 271 lines to a test file and was blamed for 379. So the
check is whether most of a commit is gone, not the difference between two numbers.

## Starting one

```bash
python3 review.py narrate <range>
```

Writes `narrative.json` into the review's folder with every commit keyed by its
sha and its subject beside it, and every field empty. The structure is the part a script
can get right: which commits exist, how long the rail is, what the keys are called. What
it cannot get right is which stages the change moves through and why a commit is there, so
those are left blank rather than guessed at.

It refuses to overwrite an existing file unless you pass `--force`.

The scaffold carries one blank `figure`, `stage` and `note` so their shape is in front of
you without opening this file. An entry whose fields are all still empty is dropped before
the page and skipped by the checks, so leaving one is the same as deleting it.

An empty field falls back to git, so there is no cost to leaving one alone: an untouched
scaffold builds the same page as no narrative at all, and a `why` you have not written
keeps the commit's own message.

Stage marks are rail positions, counted after fixups are folded, so they match the numbers
the page draws beside each commit. Write them as strings.

## What the build checks

A narrative goes stale by design: rebasing and squashing rewrite shas, and the squash
button rebuilds the page straight afterwards. So staleness never blocks a build, it warns
on stderr. A key matching no commit, an ambiguous prefix, a mark past the end of the
rail, a commit claimed by two stages, a commit no stage claims.

A malformed entry does refuse to build: a stage missing `where` or `what`, a figure
missing `k` or `v`, a mark that is not a number, a key whose value is the wrong type. The
page would draw a frame around nothing, and nobody reading it would know.

## When a stage strip is worth drawing

Only when the commits really are a sequence through a mechanism, and the reader needs that
order to follow the change. A five-commit refactor that moves data through CI, then
Django, then a report earns one. Five unrelated fixes do not, and numbering them implies a
sequence that does not exist.

## What a stage accounts for

A stage lists a file when it accounts for something the final diff still shows: lines that
survive to the tip, or a file the branch removes. A stage is a step in a journey through
the branch as it stands, so one that accounts for nothing is not a step in it and is not
drawn:

```
narrative: stage 'sqlmigrate' is not drawn: nothing it did is in the branch as it
           stands, so commit(s) 8, 11 belong to no stage
```

Marks are commits, which is how a person reasons about a change, and what gets drawn is
read off the final state. So a stage built on commits whose work a later commit rewrote
disappears, and the commits it claimed are named in the same line. The page says as much
about them on its own: a commit with nothing left is marked `skim`, and one with less than
half left carries its surviving count.

A removal is the one contribution blame cannot weigh, because it only sees what is still
there. So when a file has no surviving lines for any stage, the stages that took something
out of it keep it, and a stage that only added there, whose addition is gone, does not.

Which stages list a file is read off `git blame` on the tip, not off the commits' own
diffs. Blame follows a rename and a commit's diff does not, so a stage that wrote lines
into a file a later commit renamed still lists it under the name the branch ends with.

## Naming a stage

A `where` is a place the work passes through, read in order as a journey. The reader should
be able to follow the strip left to right and say what happens to the thing being changed,
without opening a single file.

```
circleci config · git, in the CI container · docker-compose run ·
django, in the api container · sqlmigrate · the developer's terminal
```

The failure is naming a stage after the function that handles it:

```
validate_patent_file_structure_for_partial · get_existing_ip_office_pairs ·
validate_patent_file_data_for_partial · import_patent_row
```

That is accurate, and it is the file list again. It says which functions the branch
touches, which the reader can already see, and not where the work goes. A name from the
code also carries the code's shape: four functions read as four things done, where
`the file's shape · the offices it names · each row, checked · each row, imported` reads as
one thing happening.

Where a data flow and a user flow are the same journey, name the one a person would
recognise. `the login wizard` and `every admin request` are both places in a request, and
both are places a reviewer has been.

## Backticks

`why`, `points` and note `body` render backticked spans as inline code. Everything is
HTML-escaped first, so write prose and let the page handle it.
