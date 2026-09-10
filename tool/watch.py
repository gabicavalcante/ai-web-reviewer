#!/usr/bin/env python3
"""Emit one line per new question or reply, so the Claude Code session is notified.

Replays the threads still owed an answer at startup, so a question asked while no
session was attached is delivered when one arrives instead of being skipped, and
keeps a heartbeat the page reads to tell "Claude is thinking" apart from "nobody
is listening".
"""
import json
import pathlib
import signal
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import paths  # noqa: E402

STATE = paths.state_dir()
QUESTIONS = STATE / "questions.jsonl"
MESSAGES = STATE / "messages.jsonl"
ANSWERS = STATE / "answers.jsonl"
RESOLVED = STATE / "resolved.jsonl"
HEARTBEAT = STATE / "watcher.alive"
# What the page's "No, skip it" button sent before replies carried a kind, so threads
# declined before then are recognised too.
LEGACY_SKIP = "No, skip the investigation."


def complete_rows(path):
    """Parsed rows, stopping at the first line that is not yet whole."""
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            rows.append(json.loads(stripped))
        except json.JSONDecodeError:
            break  # a partial append; pick it up on the next pass
    return rows


def turns_by_thread():
    """Every turn on every thread, oldest first, the way the server assembles them."""
    turns = {}
    for answer in complete_rows(ANSWERS):
        turns.setdefault(answer.get("question_id"), []).append({
            "role": "claude",
            "text": answer.get("answer", ""),
            "at": answer.get("answered_at", ""),
        })
    for message in complete_rows(MESSAGES):
        turns.setdefault(message.get("thread_id"), []).append({
            "role": message.get("role", "you"),
            "kind": message.get("kind", "answer"),
            "text": message.get("text", ""),
            "at": message.get("at", ""),
        })
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
    """Unresolved threads whose last turn is not Claude's, so still owed an answer."""
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
    """A reviewer's turn, with the kind that produced it.

    A decline arriving as bare prose leaves the reading session to infer what the
    reviewer meant from the button's wording. Naming the kind keeps that unambiguous,
    and keeps working if the button text changes.
    """
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
    # Anything already answered stays quiet; anything still waiting is replayed, because
    # the alternative is a question that sits behind a spinner nobody will ever answer.
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
                for path, describe in ((QUESTIONS, describe_question), (MESSAGES, describe_reply)):
                    rows = complete_rows(path)
                    for row in rows[seen[path]:]:
                        # Claude's own turns are written by answer.py; do not echo them back.
                        if path is MESSAGES and row.get("role") != "you":
                            continue
                        print(describe(row), flush=True)
                    seen[path] = max(seen[path], len(rows))
            except OSError as error:
                print(f"WATCHER-ERROR {error}", flush=True)
            time.sleep(1)
    finally:
        # The page reads this to decide whether a spinner is honest, so clear it on the
        # way out. A kill -9 cannot run this, which is why the page judges the heartbeat
        # by how fresh it is rather than by whether it exists.
        try:
            HEARTBEAT.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    # TaskStop and the Monitor timeout both send SIGTERM, whose default action skips the
    # cleanup above. Turning it into SystemExit lets the heartbeat be cleared.
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    main()
