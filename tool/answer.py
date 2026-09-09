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
QUESTIONS = STATE / "questions.jsonl"
MESSAGES = STATE / "messages.jsonl"


def known_ids():
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
        return subprocess.run(["git", "-C", REPO, *extra],
                              capture_output=True, text=True, check=True).stdout.strip()
    try:
        subject = git("show", "-s", "--format=%h %s", sha)
        stat = git("show", "--shortstat", "--format=", sha).strip()
    except subprocess.CalledProcessError:
        sys.exit(f"no such commit: {sha}")
    return {"commit": subject, "stat": stat}


def main():
    args = sys.argv[1:]
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
    if question_id not in known_ids():
        sys.exit(f"no question with id {question_id}")

    text = sys.stdin.read().strip()
    if not text:
        sys.exit("refusing to write an empty answer")

    row = {
        "thread_id": question_id,
        "role": "claude",
        "kind": kind,
        "text": text,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        **extra,
    }
    with MESSAGES.open("a") as handle:
        handle.write(json.dumps(row) + "\n")
    print(f"{kind} in thread {question_id} ({len(text)} chars)")


if __name__ == "__main__":
    main()
