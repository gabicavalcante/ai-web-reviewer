#!/usr/bin/env python3
"""Add a Claude turn to a thread, so it shows up inline on the review page.

    python3 answer.py <thread-id> <<'EOF'
    the answer text
    EOF

    python3 answer.py --ask <thread-id> <<'EOF'
    This needs a repo-wide sweep. Want me to run it?
    EOF

    python3 answer.py --did <thread-id> <sha> <<'EOF'
    Renamed it, as a fixup on commit 2.
    EOF

--ask marks the turn as a question back to the reviewer, so the page offers a
go-ahead button instead of showing the thread as still awaiting a reply.

--did records a change made in response to the thread, with the commit it landed
in, so the thread reads as asked -> answered -> changed.

--long allows an answer past the length ceiling, for the few that need it.

--range names the review the thread is in. Without it the id is looked for across
the reviews in this checkout.

Reads the body from stdin, so it can be long and contain any quoting.
"""

import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import paths  # noqa: E402

REPO = paths.repo_root()
STATE = paths.state_dir()


def review_of(thread_id, rng=None):
    """The review a thread belongs to, as its directory.

    A range can be passed, and the session that opened the review knows it. Without one
    the id is looked for across the reviews in this checkout, because the alternative is
    an answer that goes nowhere when a flag is forgotten. Ids are random, so a search
    finds at most one.
    """
    if rng:
        # Resolved, because the flag is copied from the serve command and the default
        # range ends in HEAD, which names a different branch on every checkout. Not
        # created: a review the server has not made holds no thread, so making the
        # folder here would only hide the wrong range behind an empty one.
        where = paths.review_dir(paths.resolve_range(rng, REPO), REPO, create=False)
        if where.is_dir():
            return where
        print(f"no review here for {rng!r}, looking for the thread instead", file=sys.stderr)
    folders = paths.reviews(REPO)
    for folder in folders:
        questions = folder / "questions.jsonl"
        if questions.exists() and f'"{thread_id}"' in questions.read_text():
            return folder
    sys.exit(
        f"no review in this checkout has a thread {thread_id}.\n"
        + (
            "reviews here:\n  " + "\n  ".join(p.name for p in folders)
            if folders
            else "there are no reviews here yet."
        )
    )


# Long enough for a proposal with four parts, a quoted replacement sentence and a closing
# question, measured from one that did that well. Short enough to refuse the version of
# the same answer that explained itself first and buried the list in a paragraph.
#
# The ceiling is here rather than in a rule because a rule can be reasoned around and an
# exit code cannot. Reaching it is the prompt to cut, and --long is for the answer that
# has earned the room, which makes taking the room a decision instead of a drift.
ANSWER_MAX = 1200


def known_ids(QUESTIONS):
    if not QUESTIONS.exists():
        return set()
    ids = set()
    for line in QUESTIONS.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                ids.add(json.loads(line)["id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return ids


def describe_commit(sha):
    """Subject and shortstat for a commit, so the thread records what actually landed."""

    def git(*extra):
        return subprocess.run(
            ["git", "-C", REPO, *extra], capture_output=True, text=True, check=True
        ).stdout.strip()

    try:
        subject = git("show", "-s", "--format=%h %s", sha)
        stat = git("show", "--shortstat", "--format=", sha).strip()
    except subprocess.CalledProcessError:
        sys.exit(f"no such commit: {sha}")
    return {"commit": subject, "stat": stat}


def main():
    args = sys.argv[1:]
    allow_long = "--long" in args
    args = [a for a in args if a != "--long"]
    rng = None
    if "--range" in args:
        at = args.index("--range")
        rng = args[at + 1]
        args = args[:at] + args[at + 2 :]
    kind = "answer"
    extra = {}
    if args and args[0] == "--ask":
        kind = "ask"
        args = args[1:]
    elif args and args[0] == "--did":
        kind = "did"
        args = args[1:]
        if len(args) != 2:
            sys.exit(__doc__)
        extra = describe_commit(args[1])
        args = args[:1]
    if len(args) != 1:
        sys.exit(__doc__)
    question_id = args[0]
    where = review_of(question_id, rng)
    questions, messages = where / "questions.jsonl", where / "messages.jsonl"
    if question_id not in known_ids(questions):
        sys.exit(
            f"no question with id {question_id} in {where.name}.\n"
            "If that is the wrong review, drop --range and the id is looked for "
            "across all of them."
        )

    text = sys.stdin.read().strip()
    if not text:
        sys.exit("refusing to write an empty answer")
    if len(text) > ANSWER_MAX and not allow_long:
        sys.exit(
            f"this answer is {len(text)} characters, over the {ANSWER_MAX} a thread reply "
            f"gets.\n"
            "Lead with the answer, make the list of changes a list, and cut the part that\n"
            "explains why the fix works. If it still needs the room, pass --long."
        )

    row = {
        "thread_id": question_id,
        "role": "claude",
        "kind": kind,
        "text": text,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        **extra,
    }
    paths.append_row(messages, row)
    print(f"{kind} in thread {question_id} ({len(text)} chars)")


if __name__ == "__main__":
    main()
