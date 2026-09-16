#!/usr/bin/env python3
"""Serve the review page and carry questions to Claude.

GET  /         index.html and the other static files in this directory
GET  /thread   every thread with its turns and resolved state, plus the commits
               currently in the reviewed range, as JSON
POST /rebuild  build the page again, for when those commits have moved
POST /squash   git rebase --autosquash the reviewed range, guarded and reversible
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
import subprocess
import sys
import time
import uuid

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import paths  # noqa: E402

STATE = paths.state_dir()
REPO = paths.repo_root()
# review.py passes the range it served, already resolved. The default matches its own.
RANGE = os.environ.get("REVIEW_RANGE") or "origin/main...HEAD"
# One side, the same set build_data puts on the rail. With the two-sided form a plain
# `git fetch` moved origin/main and the page announced new commits on your branch.
COMMITS = paths.commit_range(RANGE, REPO)
PORT = int(os.environ.get("PORT", "8777"))

# What the page's own origin looks like. A browser sends Origin on same-origin POSTs too,
# so the rule cannot be "refuse anything carrying Origin" without refusing the page.
OWN_ORIGINS = {
    f"http://localhost:{PORT}",
    f"http://127.0.0.1:{PORT}",
    f"http://[::1]:{PORT}",
}

LOGS = paths.logs(RANGE, REPO, create=True)
QUESTIONS = LOGS["questions"]
ANSWERS = LOGS["answers"]
RESOLVED = LOGS["resolved"]
MESSAGES = LOGS["messages"]
PAGE = paths.page(RANGE, REPO)
HEARTBEAT = paths.review_dir(RANGE, REPO) / "watcher.alive"
# watch.py refreshes the heartbeat every second, so a few missed ticks still read as
# attached while a stopped watcher goes stale before the page next polls.
WATCHER_STALE_AFTER = 10
MAX_BODY = 64 * 1024

FIXUP_PREFIXES = ("fixup!", "squash!", "amend!")


def git(*args, **kwargs):
    return subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, **kwargs
    )


def review_tip():
    """The branch this review is of, from the range the server was started with.

    RANGE is decided once, when the review starts. HEAD is whatever the reviewer has
    checked out since, and every part of the squash reads HEAD: the merge base, the fixup
    count, the rebase itself. So the button rewrote the branch that happened to be
    checked out and answered as though it had rewritten the one on the page.
    """
    tip = RANGE.split("...")[-1] if "..." in RANGE else RANGE.split("..")[-1]
    return tip.strip()


def review_base():
    """The commit the reviewed range starts from, which is what a rebase rewrites onto.

    A three dot range is measured from the merge base, so that is what has to be rebased
    onto: rebasing onto the left side itself would drag in everything main gained since.
    """
    if "..." in RANGE:
        left = RANGE.split("...")[0] or "origin/main"
        found = git("merge-base", left, "HEAD")
        return found.stdout.strip() if found.returncode == 0 else ""
    if ".." in RANGE:
        return RANGE.split("..")[0].strip()
    return ""


def pushed_in_range(base):
    """How many commits in the range the upstream already has.

    Squashing rewrites every one of them, so a branch that has been pushed needs a force
    push afterwards. Counting conservatively: with no upstream there is nothing to break.
    """
    upstream = git("rev-parse", "--abbrev-ref", "@{u}")
    if upstream.returncode != 0:
        return 0
    counted = git("rev-list", "--count", f"{base}..{upstream.stdout.strip()}")
    return int(counted.stdout.strip() or 0) if counted.returncode == 0 else 0


_revision = {"at": 0.0, "value": ""}


def current_branch():
    """The branch checked out now, or "" when git cannot say.

    A detached HEAD has no branch name, and a thread asked from one is stamped empty. It
    then groups with the threads whose origin is unknown, which is what it is.
    """
    name = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    return "" if name in ("", "HEAD") else name


def watcher_alive():
    """Whether a Monitor is currently tailing the logs.

    Judged by how fresh the heartbeat is rather than whether the file exists, because a
    watcher killed with SIGKILL never gets to remove it.
    """
    try:
        return (time.time() - HEARTBEAT.stat().st_mtime) < WATCHER_STALE_AFTER
    except OSError:
        return False


def revision(fresh=False):
    """The commits in the reviewed range, sorted, as one string.

    The page holds the same string for the commits built into it. They stop matching when
    a commit lands, which is the only way the page can tell it is behind: the diff is baked
    in at build time, while threads are polled.

    Sorted, so the answer does not depend on the order git happens to list them. Cached for
    a few seconds, because every open page asks for it every four.
    """
    now = time.monotonic()
    if not fresh and now - _revision["at"] < 3:
        return _revision["value"]
    result = subprocess.run(
        ["git", "-C", str(REPO), "rev-list", "--max-count=500", COMMITS],
        capture_output=True,
        text=True,
    )
    # An unresolvable range is not something to nag about: the page treats "" as unknown.
    _revision["value"] = (
        ",".join(sorted(result.stdout.split())) if result.returncode == 0 else ""
    )
    _revision["at"] = now
    return _revision["value"]


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


class Handler(http.server.BaseHTTPRequestHandler):
    """Serves one page and six endpoints, and nothing off the disk.

    It used to serve a directory, which meant whatever was in that directory was on the
    port: with the threads beside the page, a GET of /questions.jsonl returned them. The
    page loads nothing but itself, so there is no directory to serve.
    """

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
                turns.setdefault(answer.get("question_id"), []).append(
                    {
                        "role": "claude",
                        "kind": "answer",
                        "text": answer.get("answer", ""),
                        "at": answer.get("answered_at", ""),
                    }
                )
            for message in read_jsonl(MESSAGES):
                turns.setdefault(message.get("thread_id"), []).append(
                    {
                        "role": message.get("role", "you"),
                        "kind": message.get("kind", "answer"),
                        "text": message.get("text", ""),
                        "at": message.get("at", ""),
                        "commit": message.get("commit", ""),
                        "stat": message.get("stat", ""),
                    }
                )
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
            payload = {
                "threads": threads,
                "revision": revision(),
                "watcher": watcher_alive(),
            }
            # Only when asked. The page asks while the squash bar is on screen, which is
            # after every commit is ticked, so a git status does not run every four
            # seconds in every tab for a button nobody can see yet.
            if "squash=1" in self.path:
                blocked = self._squash_block()
                payload["squash"] = (
                    {"ready": True} if not blocked else {"ready": False, "why": blocked[0]}
                )
            return self._json(payload)

        if self.path.split("?")[0] in ("/", "/index.html"):
            if not PAGE.exists():
                return self._json({"error": "no page built for this range yet"}, 404)
            body = PAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return self.wfile.write(body)

        return self._json({"error": "not found"}, 404)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return None

    def _cross_site(self):
        """Why this write should be refused, or None.

        Binding 127.0.0.1 with no authentication accepts one threat: other processes on
        this machine. It does not cover the one that matters. A browser will send a POST
        to localhost on behalf of whatever page the reviewer has open, and a POST with a
        simple content type needs no preflight to ask permission first. So every website
        open while a review is running could reach these endpoints, and two of them write:
        /ask puts words into the log a Claude session reads and acts on, and /squash runs
        git rebase on the reviewer's repo.

        Two checks, because each covers what the other cannot. Origin and Sec-Fetch-Site
        are set by the browser and cannot be forged by a page, but a non-browser client
        sends neither, so a missing header cannot be treated as hostile. Requiring JSON
        closes that gap from the other side: a cross-site POST can only carry a simple
        content type without a preflight, and the preflight is one this server fails.
        """
        origin = self.headers.get("Origin")
        if origin is not None and origin not in OWN_ORIGINS:
            return f"refused a request from {origin}"
        site = self.headers.get("Sec-Fetch-Site")
        if site is not None and site not in ("same-origin", "none"):
            return f"refused a {site} request"
        if int(self.headers.get("Content-Length") or 0):
            kind = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if kind != "application/json":
                return "a body has to be sent as Content-Type: application/json"
        return None

    def do_POST(self):
        # Before the dispatch, so an endpoint added later is covered without remembering.
        refusal = self._cross_site()
        if refusal:
            return self._json({"error": refusal}, 403)

        if self.path == "/squash":
            return self._squash()
        if self.path == "/rebuild":
            return self._rebuild()
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
            # Which review this thread belongs to. Read from git now rather than from the
            # range this server started with, because the branch can change under a
            # running server, and a thread belongs to the branch it was asked about.
            #
            # The branch, not the range: a range moves as its base advances, which would
            # split one review into several.
            "branch": current_branch(),
            "question": question[:4000],
            "commit": str(payload.get("commit", ""))[:40],
            "file": str(payload.get("file", ""))[:300],
            "side": str(payload.get("side", ""))[:8],
            "line": str(payload.get("line", ""))[:12],
            "code": str(payload.get("code", ""))[:400],
        }
        paths.append_row(QUESTIONS, row)
        return self._json({"ok": True, "id": row["id"]})

    def _squash_block(self, force=False):
        """Why a squash cannot run now, or None.

        Split out of the press so the page can ask the same question before offering the
        button. A refusal that only arrives after the click reads as the button being
        broken, which is what it looked like: the message landed in a bar styled for
        success and changed nothing else about the page.

        Returns (message, http status, needs_force).
        """
        base = review_base()
        if not base:
            return (f"no base commit in the range {RANGE}", 400, False)

        # Before anything reads HEAD, because everything below does.
        tip = review_tip()
        here = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if tip and here != tip:
            return (
                f"this review is of {tip}, and {here} is checked out. Squashing would "
                f"rewrite {here}. Check out {tip} first.",
                409,
                False,
            )

        # --untracked-files=no because a rebase only refuses over tracked changes. Counting
        # untracked files here blocked the button on a scratch directory beside the post
        # being reviewed, which has nothing to do with the commits being squashed.
        dirty = [
            line
            for line in git("status", "--porcelain", "--untracked-files=no").stdout.split("\n")
            if line
        ]
        if dirty:
            return (
                f"{len(dirty)} tracked file(s) have uncommitted changes. Commit or "
                "stash them first.",
                409,
                False,
            )

        git_dir = pathlib.Path(git("rev-parse", "--git-dir").stdout.strip() or ".git")
        if not git_dir.is_absolute():
            git_dir = REPO / git_dir
        if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
            return ("a rebase is already in progress here", 409, False)

        subjects = [
            s for s in git("log", "--format=%s", f"{base}..HEAD").stdout.split("\n") if s
        ]
        if not any(s.startswith(FIXUP_PREFIXES) for s in subjects):
            return ("nothing to squash: no fixups in this range", 400, False)

        pushed = pushed_in_range(base)
        if pushed and not force:
            return (
                f"{pushed} commit(s) in this range are already pushed. Squashing "
                "rewrites them, so the branch would need a force push.",
                409,
                True,
            )
        # The caller needs the count it just walked, so it is handed back rather than
        # counted again. Extracting the guards and leaving "before = len(subjects)"
        # behind them threw a NameError after the rebase had already run: history
        # rewritten, page never rebuilt, reviewer told the squash failed.
        self._squash_subjects = subjects
        return None

    def _squash(self):
        """Run git rebase --autosquash over the reviewed range.

        Every guard here exists because the failure it prevents is worse than the button
        being unavailable: a rebase started from a web page that leaves the repo mid
        conflict, or rewrites commits someone else has pulled, is not a small mistake.
        """
        asked = self._body() or {}
        base = review_base()
        self._squash_subjects = []
        blocked = self._squash_block(force=bool(asked.get("force")))
        if blocked:
            message, status, needs_force = blocked
            payload = {"error": message}
            if needs_force:
                payload["needsForce"] = True
            return self._json(payload, status)

        head = git("rev-parse", "HEAD").stdout.strip()
        backup = "pre-squash/" + time.strftime("%Y%m%d-%H%M%S")
        made = git("branch", backup, head)
        if made.returncode != 0:
            return self._json(
                {"error": "could not make a backup branch: " + made.stderr.strip()[:200]}, 500
            )

        # true as the editor takes the todo list and the messages as git wrote them.
        env = dict(os.environ, GIT_SEQUENCE_EDITOR="true", GIT_EDITOR="true")
        run = subprocess.run(
            ["git", "-C", str(REPO), "rebase", "-i", "--autosquash", base],
            capture_output=True,
            text=True,
            env=env,
        )
        if run.returncode != 0:
            # Never leave a repo mid rebase because a button was pressed.
            subprocess.run(
                ["git", "-C", str(REPO), "rebase", "--abort"], capture_output=True, text=True
            )
            git("reset", "--hard", head)
            return self._json(
                {
                    "error": "the rebase did not apply and was rolled back: "
                    + (run.stderr or run.stdout).strip()[:400],
                    "backup": backup,
                },
                409,
            )

        before = len(self._squash_subjects)
        after = len(
            [s for s in git("log", "--format=%s", f"{base}..HEAD").stdout.split("\n") if s]
        )
        built = subprocess.run(
            [sys.executable, str(HERE / "review.py"), "build", "--", RANGE],
            capture_output=True,
            text=True,
            cwd=str(REPO),
        )
        if built.returncode != 0:
            return self._json(
                {
                    "error": "the squash worked but the page did not build: "
                    + (built.stderr or built.stdout).strip()[:400],
                    "backup": backup,
                },
                500,
            )

        return self._json(
            {
                "ok": True,
                "before": before,
                "after": after,
                "backup": backup,
                "head": head,
                "revision": revision(fresh=True),
            }
        )

    def _rebuild(self):
        """Rebuild index.html for the same range, so a reload shows the new commits.

        "--" so a range like --root..HEAD is not read as an option. The build runs its own
        smoke check and fails loudly, so a page that would throw is never written.
        """
        result = subprocess.run(
            [sys.executable, str(HERE / "review.py"), "build", "--", RANGE],
            capture_output=True,
            text=True,
            cwd=str(REPO),
        )
        if result.returncode != 0:
            problem = (result.stderr or result.stdout).strip() or "build failed"
            return self._json({"error": problem[:400]}, 500)
        return self._json({"ok": True, "revision": revision(fresh=True)})

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
        # "skip" marks a declined investigation, which settles the thread instead of
        # leaving it looking like it is still owed an answer.
        kind = str(payload.get("kind", "answer"))
        if kind not in {"answer", "go", "skip"}:
            kind = "answer"
        row = {
            "thread_id": thread_id,
            "role": "you",
            "kind": kind,
            "text": text[:4000],
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        paths.append_row(MESSAGES, row)
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
        paths.append_row(RESOLVED, row)
        return self._json({"ok": True, **row})


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    # PORT is read once at the top, because the cross-site guard needs it too.
    port = PORT
    QUESTIONS.touch(exist_ok=True)
    ANSWERS.touch(exist_ok=True)
    RESOLVED.touch(exist_ok=True)
    MESSAGES.touch(exist_ok=True)
    print(f"review page on http://localhost:{port}")
    Server(("127.0.0.1", port), Handler).serve_forever()
