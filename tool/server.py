#!/usr/bin/env python3
"""Serve the review page and carry questions to Claude.

GET  /         index.html and the other static files in this directory
GET  /thread   every thread with its turns and resolved state, as JSON
POST /ask      start a new thread, anchored to a diff line
POST /reply    add your turn to an existing thread
POST /resolve  mark a thread resolved, or reopen it

Bound to 127.0.0.1 only. There is no auth: anything that can reach the port can
read and append questions, so do not bind it to a routable interface.
"""
import http.server
import json
import os
import pathlib
import socketserver
import sys
import time
import uuid

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import paths  # noqa: E402

STATE = paths.state_dir()
QUESTIONS = STATE / "questions.jsonl"
ANSWERS = STATE / "answers.jsonl"
RESOLVED = STATE / "resolved.jsonl"
MESSAGES = STATE / "messages.jsonl"
MAX_BODY = 64 * 1024


def read_jsonl(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # A half-written append. It will be whole by the next poll.
            continue
    return rows


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATE), **kwargs)

    def log_message(self, fmt, *args):
        # The page polls /thread every few seconds; logging it buries everything else.
        if not self.path.startswith("/thread"):
            super().log_message(fmt, *args)

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] == "/thread":
            turns = {}
            # answers.jsonl predates threading; its rows are Claude turns.
            for answer in read_jsonl(ANSWERS):
                turns.setdefault(answer.get("question_id"), []).append({
                    "role": "claude",
                    "kind": "answer",
                    "text": answer.get("answer", ""),
                    "at": answer.get("answered_at", ""),
                })
            for message in read_jsonl(MESSAGES):
                turns.setdefault(message.get("thread_id"), []).append({
                    "role": message.get("role", "you"),
                    "kind": message.get("kind", "answer"),
                    "text": message.get("text", ""),
                    "at": message.get("at", ""),
                    "commit": message.get("commit", ""),
                    "stat": message.get("stat", ""),
                })
            for thread_turns in turns.values():
                thread_turns.sort(key=lambda turn: turn.get("at", ""))

            # Append-only, so the last row for an id is the current state.
            resolved = {}
            for row in read_jsonl(RESOLVED):
                resolved[row.get("question_id")] = bool(row.get("resolved"))

            threads = [
                {
                    **question,
                    "turns": turns.get(question.get("id"), []),
                    "resolved": resolved.get(question.get("id"), False),
                }
                for question in read_jsonl(QUESTIONS)
            ]
            return self._json({"threads": threads})
        return super().do_GET()

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return None

    def do_POST(self):
        if self.path == "/resolve":
            return self._resolve()
        if self.path == "/reply":
            return self._reply()
        if self.path != "/ask":
            return self._json({"error": "unknown endpoint"}, 404)

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return self._json({"error": "bad body length"}, 400)

        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return self._json({"error": "invalid json"}, 400)

        question = (payload.get("question") or "").strip()
        if not question:
            return self._json({"error": "empty question"}, 400)

        row = {
            "id": uuid.uuid4().hex[:12],
            "asked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "question": question[:4000],
            "commit": str(payload.get("commit", ""))[:40],
            "file": str(payload.get("file", ""))[:300],
            "side": str(payload.get("side", ""))[:8],
            "line": str(payload.get("line", ""))[:12],
            "code": str(payload.get("code", ""))[:400],
        }
        with QUESTIONS.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return self._json({"ok": True, "id": row["id"]})


    def _reply(self):
        payload = self._body()
        if payload is None:
            return self._json({"error": "invalid body"}, 400)
        thread_id = str(payload.get("thread_id", ""))
        if thread_id not in {row.get("id") for row in read_jsonl(QUESTIONS)}:
            return self._json({"error": "unknown thread"}, 404)
        text = (payload.get("text") or "").strip()
        if not text:
            return self._json({"error": "empty reply"}, 400)
        row = {
            "thread_id": thread_id,
            "role": "you",
            "text": text[:4000],
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with MESSAGES.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return self._json({"ok": True, "thread_id": thread_id})

    def _resolve(self):
        payload = self._body()
        if payload is None:
            return self._json({"error": "invalid body"}, 400)
        question_id = str(payload.get("question_id", ""))
        known = {row.get("id") for row in read_jsonl(QUESTIONS)}
        if question_id not in known:
            return self._json({"error": "unknown question"}, 404)
        row = {
            "question_id": question_id,
            "resolved": bool(payload.get("resolved", True)),
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with RESOLVED.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return self._json({"ok": True, **row})


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8777"))
    QUESTIONS.touch(exist_ok=True)
    ANSWERS.touch(exist_ok=True)
    RESOLVED.touch(exist_ok=True)
    MESSAGES.touch(exist_ok=True)
    print(f"review page on http://localhost:{port}")
    Server(("127.0.0.1", port), Handler).serve_forever()
