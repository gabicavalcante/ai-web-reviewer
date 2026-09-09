#!/usr/bin/env python3
"""Emit one line per new question or reply, so the Claude Code session is notified.

Starts at the end of both logs, so turns already handled do not replay.
"""
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import paths  # noqa: E402

STATE = paths.state_dir()
QUESTIONS = STATE / "questions.jsonl"
MESSAGES = STATE / "messages.jsonl"


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
    return "REPLY in thread {thread} · {text}".format(
        thread=row.get("thread_id", "?"),
        text=row.get("text", ""),
    )


def main():
    seen = {
        QUESTIONS: len(complete_rows(QUESTIONS)),
        MESSAGES: len(complete_rows(MESSAGES)),
    }
    while True:
        try:
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


if __name__ == "__main__":
    main()
