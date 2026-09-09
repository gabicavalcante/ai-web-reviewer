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

## When a stage strip is worth drawing

Only when the commits really are a sequence through a mechanism, and the reader needs that
order to follow the change. A five-commit refactor that moves data through CI, then
Django, then a report earns one. Five unrelated fixes do not, and numbering them implies a
sequence that does not exist.

## Backticks

`why`, `points` and note `body` render backticked spans as inline code. Everything is
HTML-escaped first, so write prose and let the page handle it.
