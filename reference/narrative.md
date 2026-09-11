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
- `care` on more than a third of the commits warns.

## Starting one

```bash
python3 review.py narrate <range>
```

Writes `narrative.json` into the review's state directory with every commit keyed by its
sha and its subject beside it, and every field empty. The structure is the part a script
can get right — which commits exist, how long the rail is, what the keys are called. What
it cannot get right is which stages the change moves through and why a commit is there, so
those are left blank rather than guessed at.

It refuses to overwrite an existing file unless you pass `--force`.

An empty field falls back to git, so there is no cost to leaving one alone: an untouched
scaffold builds the same page as no narrative at all, and a `why` you have not written
keeps the commit's own message.

Stage marks are rail positions, counted after fixups are folded, so they match the numbers
the page draws beside each commit. Write them as strings.

## What the build checks

A narrative goes stale by design: rebasing and squashing rewrite shas, and the squash
button rebuilds the page straight afterwards. So staleness never blocks a build, it warns
on stderr — a key matching no commit, an ambiguous prefix, a mark past the end of the
rail, a commit claimed by two stages, a commit no stage claims.

A malformed entry does refuse to build: a stage missing `where` or `what`, a figure
missing `k` or `v`, a mark that is not a number, a key whose value is the wrong type. The
page would draw a frame around nothing, and nobody reading it would know.

## When a stage strip is worth drawing

Only when the commits really are a sequence through a mechanism, and the reader needs that
order to follow the change. A five-commit refactor that moves data through CI, then
Django, then a report earns one. Five unrelated fixes do not, and numbering them implies a
sequence that does not exist.

## Backticks

`why`, `points` and note `body` render backticked spans as inline code. Everything is
HTML-escaped first, so write prose and let the page handle it.
