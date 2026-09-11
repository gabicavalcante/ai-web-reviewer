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

## Mannered prose

Mannered prose substitutes metaphor and flourish for direct statement. Instead of "a
parameter worth varying", the mannered writer produces "a dial worth turning". Instead of
"this point still matters", "this point earns its keep".

The phrases exist to display the writer, not to convey the idea, and readers can tell.
That is why mannered prose irritates: it makes the reader work harder so the writer can
perform. It is also imprecise, because metaphors drag in connotations the writer did not
choose and cannot control.

The fix is to say what you mean. When a literal phrase is available, use it.

| Mannered | Direct |
| --- | --- |
| a dial worth turning | a parameter worth varying |
| this point earns its keep | this point still matters |
| the guard the button trips | the check that refuses the squash |
| questions land on the floor | questions are never delivered |

This applies to everything the skill writes, not only the page: narrative fields, labels,
the answers posted into threads, and the messages reported back in the session.

**The short form is "Please remove all mannered prose."** Use it as a pass over a draft
when the full definition is not needed.

## Answers in a thread

The reviewer asked from a line in the diff and is waiting to get back to reading. What
makes an answer hard to use is usually its shape rather than its words.

- **The first sentence is the answer.** Not agreement, not a restatement of the question.
  "You're right:" and "Good question" cost a line and carry nothing.
- **A list of changes is a list.** Four edits buried in one sentence have to be unpacked by
  the reader before they can be checked off. Four bullets can be.
- **Say what changes and where.** A proposal the reviewer cannot act on without asking a
  follow-up is not finished.
- **Cut the part that explains why the fix works.** They are looking at the code and will
  see it. Keep the reason only where the fix looks wrong without it.
- **Answer what was asked.** A second thing you noticed belongs in its own thread, or
  nowhere.

`answer.py` refuses an answer over 1200 characters unless you pass `--long`. Reaching the
ceiling means cut, not ask for more room: lead with the answer, make the list a list, drop
the justification. `--long` is for the answer that genuinely needs it, and passing it
should be a decision you notice making.

## Every "the" points at something the reader has seen

You investigated the branch, so the parts have names in your head. The reader has the page
and the diff, and nothing else. "the boundary" sends them looking for a boundary they were
never shown. This is `deslop` pattern B12, and the quick check catches it: for every
`the <noun>`, find where the text introduced it.

The shared context is real, though. The reviewer is looking at the anchored line and has
read the diff, so re-narrating code they can see is its own failure. Introduce what is
missing, once.

## Rules that matter most here

- **No em dashes.** Use a period, a comma, a colon, or parentheses.
- **No idiom or phrasal verbs.** "goes red" is "fails". "the paths users hit" is "the
  paths users use". A reader who knows every word in "your call" still cannot derive it.
- **No metaphor as a technical term.** The worst case of mannered prose above: if a
  metaphor is doing the work of a term, name the mechanism. "arm the guard" is "turn the
  guard on".
- **Say it once.** A label, its tooltip and its status line should not restate each other.
- **Name the actor.** "The script collects failures", not "failures are collected".
- **Never assert what you have not checked.** A footer that says "working tree clean" on
  every page is a lie on most of them. If a claim is not computed from git, do not print
  it.

## Labels

Buttons say what happens when you press them, in the imperative: `Resolve`, `Reply`,
`Reopen`, `Yes, investigate`. A state label says what is true right now: `waiting for an
answer`, `waiting for you`, `resolved`. Do not mix the two moods in one row.
