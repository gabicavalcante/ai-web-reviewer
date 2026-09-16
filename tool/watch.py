#!/usr/bin/env python3
"""Emit one line per new question or reply, so the Claude Code session is notified.

Replays the threads still owed an answer at startup, so a question asked while no
session was attached reaches the next one. Keeps a heartbeat the page reads to tell
"Claude is thinking" apart from "nobody is listening".
"""

import json
import pathlib
import signal
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import paths  # noqa: E402


def review_range(argv):
    """The review this watcher belongs to, from --range.

    A watcher has to be told. It is started beside the server rather than by it, so it
    inherits nothing, and a review is a range. With one review in the checkout there is
    nothing to choose between, so that case does not need the flag.
    """
    if "--range" in argv:
        return argv[argv.index("--range") + 1]
    folders = paths.reviews()
    if len(folders) == 1:
        return None, folders[0]
    sys.exit(
        "which review? pass --range, the same one the server was started with.\n"
        + "reviews in this checkout:\n  "
        + "\n  ".join(sorted(p.name for p in folders))
    )


def review_of(rng):
    """The folder for a range, refusing rather than making one up.

    The range is resolved first, for the same reason review.py resolves it: the flag is
    copied from the serve command, the default is "origin/main...HEAD", and HEAD is not a
    name. Watching the unresolved string put the heartbeat in one folder while the server
    wrote questions to another, so the page reported no session attached and the watcher
    sat over a file nothing appends to.

    A missing folder is never a new review. The server makes a review; a watcher only
    joins one. Creating it here is how a mistyped range became a watcher that was running
    and silent at the same time.
    """
    where = paths.review_dir(paths.resolve_range(rng), create=False)
    if not where.is_dir():
        folders = [p.name for p in paths.reviews()]
        sys.exit(
            f"no review here for {rng!r}. Start the server for it first.\n"
            + (
                "reviews in this checkout:\n  " + "\n  ".join(folders)
                if folders
                else "there are no reviews here yet."
            )
        )
    return where


_arg = review_range(sys.argv[1:])
WHERE = _arg[1] if isinstance(_arg, tuple) else review_of(_arg)
QUESTIONS = WHERE / "questions.jsonl"
MESSAGES = WHERE / "messages.jsonl"
ANSWERS = WHERE / "answers.jsonl"
RESOLVED = WHERE / "resolved.jsonl"
HEARTBEAT = WHERE / "watcher.alive"
# What the page's "No, skip it" button sent before replies carried a kind, so threads
# declined before then are recognised too.
LEGACY_SKIP = "No, skip the investigation."


# Lines already reported as unreadable, so the same one is not complained about every
# second for the life of the watcher.
_UNREADABLE = set()


def complete_rows(path):
    """Parsed rows: waiting for a line still being written, stepping over a broken one.

    These two look alike and are not. Every row is written with a trailing newline, so a
    final line without one is an append in progress and will parse on the next pass. A
    line anywhere above that will never parse: the process writing it died, or the disk
    filled.

    Stopping at either hid every row below it for as long as the watcher ran, and the
    server reads the same file separately, so the page went on drawing those questions as
    waiting for an answer with nothing listening. Silence is the one failure this must not
    have, so an unreadable row is stepped over and said out loud once.
    """
    rows = []
    try:
        text = path.read_text()
    except FileNotFoundError:
        return rows
    lines = text.split("\n")
    # Whatever follows the last newline is unfinished, and "" when the file ends cleanly.
    lines.pop()
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            rows.append(json.loads(stripped))
        except json.JSONDecodeError:
            if (path, number) not in _UNREADABLE:
                _UNREADABLE.add((path, number))
                print(
                    f"WATCHER-ERROR {path.name} line {number} cannot be read, skipping it",
                    flush=True,
                )
    return rows


def turns_by_thread():
    """Every turn on every thread, oldest first, the way the server assembles them."""
    turns = {}
    for answer in complete_rows(ANSWERS):
        turns.setdefault(answer.get("question_id"), []).append(
            {
                "role": "claude",
                "text": answer.get("answer", ""),
                "at": answer.get("answered_at", ""),
            }
        )
    for message in complete_rows(MESSAGES):
        turns.setdefault(message.get("thread_id"), []).append(
            {
                "role": message.get("role", "you"),
                "kind": message.get("kind", "answer"),
                "text": message.get("text", ""),
                "at": message.get("at", ""),
            }
        )
    for thread in turns.values():
        thread.sort(key=lambda turn: turn.get("at", ""))
    return turns


def resolved_ids():
    # Append-only, so the last row for an id is the current state.
    state = {}
    for row in complete_rows(RESOLVED):
        state[row.get("question_id")] = bool(row.get("resolved"))
    return {question_id for question_id, is_resolved in state.items() if is_resolved}


def is_skip(turn):
    """A reviewer's decline. It ends the exchange, so the thread is owed nothing."""
    if turn.get("role") == "claude":
        return False
    return turn.get("kind") == "skip" or turn.get("text") == LEGACY_SKIP


def backlog():
    """Unresolved threads whose last turn is not Claude's, so still owed an answer.

    Every thread here belongs to this review, because the logs are the review's own. The
    branch a question was asked on is not consulted: a branch can change under a running
    server, and the thread still belongs to the review that was open at the time.
    """
    turns = turns_by_thread()
    resolved = resolved_ids()
    waiting = []
    for question in complete_rows(QUESTIONS):
        question_id = question.get("id")
        if question_id in resolved:
            continue
        thread = turns.get(question_id, [])
        if thread and (thread[-1].get("role") == "claude" or is_skip(thread[-1])):
            continue
        waiting.append((question, thread[-1] if thread else None))
    return waiting


def describe_question(row):
    return "QUESTION {id} · commit {commit} · {file}:{line} ({side}) · {question}".format(
        id=row.get("id", "?"),
        commit=row.get("commit", "?"),
        file=row.get("file", "?"),
        line=row.get("line", "?"),
        side=row.get("side", "?"),
        question=row.get("question", ""),
    )


def describe_reply(row):
    # Naming the kind saves the reading session inferring a decline from the button's
    # wording, and survives a reword of it.
    kind = row.get("kind", "answer")
    return "REPLY in thread {thread}{kind} · {text}".format(
        thread=row.get("thread_id", "?"),
        kind="" if kind == "answer" else f" [{kind}]",
        text=row.get("text", ""),
    )


def describe_backlog(question, last):
    """A replayed thread, marked so it is not mistaken for a question just asked."""
    line = "BACKLOG " + describe_question(question)
    if last is not None:
        line += " · last reply: " + (last.get("text") or "")
    return line


def main():
    # Answered threads stay quiet. A waiting one is replayed, or it sits behind a
    # spinner nobody will ever answer.
    for question, last in backlog():
        print(describe_backlog(question, last), flush=True)

    seen = {
        QUESTIONS: len(complete_rows(QUESTIONS)),
        MESSAGES: len(complete_rows(MESSAGES)),
    }
    try:
        while True:
            try:
                HEARTBEAT.write_text(str(time.time()))
                for path, describe in (
                    (QUESTIONS, describe_question),
                    (MESSAGES, describe_reply),
                ):
                    rows = complete_rows(path)
                    for row in rows[seen[path] :]:
                        # Claude's own turns are written by answer.py; do not echo them back.
                        if path is MESSAGES and row.get("role") != "you":
                            continue
                        print(describe(row), flush=True)
                    # Not max(). Holding the high-water mark meant a log that got
                    # shorter was never read again, and a watcher that has gone quiet
                    # looks exactly like one with nothing to say.
                    seen[path] = len(rows)
            except OSError as error:
                print(f"WATCHER-ERROR {error}", flush=True)
            time.sleep(1)
    finally:
        # The page reads this to decide whether a spinner is honest, so clear it on the
        # way out. A kill -9 cannot, which is why the server judges it by mtime.
        try:
            HEARTBEAT.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    # TaskStop and the Monitor timeout both send SIGTERM, whose default action would
    # skip the cleanup above.
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    main()
