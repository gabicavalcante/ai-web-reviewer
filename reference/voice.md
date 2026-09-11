# Voice

A person reads this page, often not in their first language. Copy is part of the tool, so
it gets the same pass as any prose you publish. This covers everything the skill writes:
narrative fields, labels, the answers posted into threads, and what you report back in the
session.

**Run the `deslop` skill over it** before you build the page. If `deslop` is not available,
apply the rules below directly.

## The test

Would you say this sentence to a colleague standing at their desk?

That catches more than the rules below, because the failures are rarely about single
words. Take a description of the same change, written twice:

> Staff must verify an authenticator code after their password before Django Admin will
> serve them anything. A Waffle switch holds the whole feature off until someone turns it
> on, so merging this changes nothing by itself.

> Django Admin users should set authenticator code as MFA factor. A waffle switch holds
> this feature off, so merging it will not enable it by default.

Nobody says the first one out loud. Three things are wrong with it, and none of them is a
metaphor:

**It describes instead of naming.** "verify an authenticator code after their password" is
a paraphrase of "set authenticator code as MFA factor". The reader knows the term. Using
it is shorter and says more.

**It states a fact as an effect on the reader.** "before Django Admin will serve them
anything" is the same fact as the second version's first clause, dressed as a consequence.
That is what makes it sound written rather than said.

**It pads.** "the whole feature", "anything", "until someone turns it on", "by itself".
And the ending is vaguer for it: "changes nothing by itself" against "will not enable it
by default", which is shorter and more precise.

Length is a symptom here, not the cause. Both versions of a padded sentence often measure
the same, which is why there is no cap on the dek.

## Never touch the diff

The voice pass applies to the page's copy: labels, status lines, narrative fields, the
answers you write. It stops at the diff. The code under review is evidence, quoted
verbatim, and a `circleci step halt` in a config file stays `halt` no matter how the
sidebar words it. Rewriting quoted code would make the page lie about the branch.

## Name the thing, once

The reader is reviewing code, so keep the code's vocabulary: `sqlmigrate`, `foreign key`,
`exit code`, `rebase`, `MFA factor`. Those are precise and already known. Two ways to get
this wrong, in opposite directions.

The implementation's vocabulary leaking into the interface:

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

And the reverse: expanding a term the reader already knows into a description of it. If
the branch is about MFA factors, say `MFA factor`. Explaining it back to the person
reviewing it is longer, vaguer, and reads as though you are not sure they know.

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

## Rules the test cannot catch

- **No em dashes.** Use a period, a comma, a colon, or parentheses.
- **No idiom or phrasal verbs.** "goes red" is "fails". "the paths users hit" is "the
  paths users use". A reader who knows every word in "your call" still cannot derive it.
- **Say it once.** A label, its tooltip and its status line should not restate each other.
- **Name the actor.** "The script collects failures", not "failures are collected".
- **Every "the" points at something the reader has seen.** You investigated the branch, so
  the parts have names in your head. The reader has the page and the diff. "the boundary"
  sends them looking for a boundary they were never shown. This is `deslop` pattern B12,
  and the check is quick: for every `the <noun>`, find where the text introduced it. The
  shared context is real, though. The reviewer is looking at the anchored line and has
  read the diff, so re-narrating code they can see is its own failure. Introduce what is
  missing, once.
- **Never assert what you have not checked.** A footer that says "working tree clean" on
  every page is a lie on most of them. If a claim is not computed from git, do not print
  it.

## Labels

Buttons say what happens when you press them, in the imperative: `Resolve`, `Reply`,
`Reopen`, `Yes, investigate`. A state label says what is true right now: `waiting for an
answer`, `waiting for you`, `resolved`. Do not mix the two moods in one row.

## What the build and the scripts refuse

Rules can be reasoned around. These cannot, which is why the limits sit at the points
every piece of text passes through rather than in this file.

| Text | Limit | Where |
| --- | --- | --- |
| a thread answer | 1200 characters, or `--long` | `answer.py` |
| `readWhy` | 80 characters | build |
| stage `what` | 120 characters | build |
| commit `why` | 450 characters | build |
| `dek` | none, deliberately | see The test |

Reaching a limit means cut. It does not mean ask for more room.
