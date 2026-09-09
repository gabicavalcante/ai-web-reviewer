# Voice

A person reads this page, often not in their first language. Copy is part of the tool, so
it gets the same pass as any prose you publish.

**Run the `deslop` skill over every string you write** before building the page: the
narrative fields, any new UI label, any answer you post into a thread. If `deslop` is not
available, apply the rules below directly.

## Never touch the diff

The voice pass applies to the page's copy: labels, status lines, narrative fields, the
answers you write. It stops at the diff. The code under review is evidence, quoted
verbatim, and a `circleci step halt` in a config file stays `halt` no matter how the
sidebar words it. Rewriting quoted code would make the page lie about the branch.

## The page's own words, not the machine's

The reader is reviewing code, so keep the code's vocabulary: `sqlmigrate`, `foreign key`,
`exit code`, `rebase`. Those are precise and already known. What to cut is the vocabulary
of the *implementation* leaking into the interface.

| Machine's word | The page's word |
| --- | --- |
| halt | skip |
| arm / armed | turn on / active |
| emit | write, print, send |
| invoke | run, call |
| spawn | start |
| assert (as a verb, in prose) | check |
| swallow (an error) | hide, ignore |
| fail open | pass when it should not |
| your call | waiting for you |
| N/A | not applicable, or say the thing |

Their word is not always shorter. It is the one whose meaning a reader can work out from
the parts.

## Rules that matter most here

- **No em dashes.** Use a period, a comma, a colon, or parentheses.
- **No idiom or phrasal verbs.** "goes red" is "fails". "the paths users hit" is "the
  paths users use". A reader who knows every word in "your call" still cannot derive it.
- **No metaphor as a technical term.** If a metaphor is doing the work of a term, say the
  mechanism. "arm the guard" is "turn the guard on", or better, name what it does.
- **Say it once.** A label, its tooltip and its status line should not restate each other.
- **Name the actor.** "The script collects failures", not "failures are collected".
- **Never assert what you have not checked.** A footer that says "working tree clean" on
  every page is a lie on most of them. If a claim is not computed from git, do not print
  it.

## Labels

Buttons say what happens when you press them, in the imperative: `Resolve`, `Reply`,
`Reopen`, `Yes, investigate`. A state label says what is true right now: `waiting for an
answer`, `waiting for you`, `resolved`. Do not mix the two moods in one row.
