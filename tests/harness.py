"""What a case file needs, and the loop that runs them.

Kept apart from the cases so the pure-function checks and the end-to-end ones can share a
sandbox without one importing the other.
"""

import contextlib
import hashlib
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

TOOL = pathlib.Path(__file__).resolve().parent.parent / "tool"
sys.path.insert(0, str(TOOL))

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


class Failed(AssertionError):
    pass


def eq(got, want, what):
    if got != want:
        raise Failed(f"{what}\n    want: {want!r}\n    got:  {got!r}")


@contextlib.contextmanager
def sandbox():
    """A temporary repo, with the state directory pointed somewhere temporary too.

    state_dir() makes its folder as soon as it is asked for a path, so a case that only
    computed a path still wrote into the reviewer's real ~/.local/state. Eleven junk
    folders appeared there before this existed. XDG_STATE_HOME is the seam, so the tests
    use it rather than reaching inside paths.py.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        was = os.environ.get("XDG_STATE_HOME")
        os.environ["XDG_STATE_HOME"] = str(root / "state")
        try:
            repo = root / "repo"
            repo.mkdir()
            yield repo, scratch_repo(repo)
        finally:
            if was is None:
                os.environ.pop("XDG_STATE_HOME", None)
            else:
                os.environ["XDG_STATE_HOME"] = was


def scratch_repo(where):
    """A repo with one commit on `main`, an origin/main ref, and a branch off it.

    Cheap enough to make per case that needs one, which keeps cases independent: a test
    that leaves state behind turns the next failure into a puzzle.
    """

    def run(*args):
        return subprocess.run(
            ["git", "-C", str(where), *args], capture_output=True, text=True, check=True
        )

    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@t")
    run("config", "user.name", "T")
    (where / "a.txt").write_text("base\n")
    run("add", "-A")
    run("commit", "-qm", "base")
    run("update-ref", "refs/remotes/origin/main", "HEAD")
    return run


@contextlib.contextmanager
def serving(repo, rng):
    """A real review server over a real repo, on a port nobody else holds.

    The three scripts that touch git, the filesystem and the network resolve their paths
    at import time, and watch.py calls sys.exit while importing, so none of them can be
    driven in process. They are run the way a reviewer runs them, and the cases assert on
    what comes back over the socket and on what git says afterwards.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, str(TOOL / "review.py"), "serve", rng, "--port", str(port)],
        cwd=str(repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if proc.poll() is not None:
                raise Failed(f"the server exited before it listened:\n{proc.stdout.read()}")
            try:
                urllib.request.urlopen(base + "/thread", timeout=1).read()
                break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.1)
        else:
            raise Failed("the server never answered")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def post(base, path, body=None, headers=None):
    """POST to the server, returning (status, parsed body).

    A refusal is an answer, not an exception, so the 4xx a guard produces is returned the
    same way a 200 is. urllib raises on both, which would make every case that checks a
    rejection read as an error.
    """
    # None means no body at all, which is what the page sends to /rebuild. Sending "{}"
    # instead made a guard on the content type look like a broken guard.
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(base + path, data=data, method="POST")
    for key, value in (headers or {"Content-Type": "application/json"}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=10) as answer:
            return answer.status, json.loads(answer.read() or b"{}")
    except urllib.error.HTTPError as refused:
        raw = refused.read()
        try:
            return refused.code, json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return refused.code, {"raw": raw.decode("utf-8", "replace")}


@contextlib.contextmanager
def watching(repo, rng):
    """A real watcher over a review, with everything it has printed so far.

    Yields a function returning the lines it has written. The watcher polls once a
    second, so a case that appends a row has to give it a moment; `until` does the
    waiting so a slow machine does not turn into a flaky check.
    """
    proc = subprocess.Popen(
        [sys.executable, str(TOOL / "watch.py"), "--range", rng],
        cwd=str(repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines = []
    reader = threading.Thread(
        target=lambda: [lines.append(line.rstrip("\n")) for line in proc.stdout],
        daemon=True,
    )
    reader.start()
    try:
        yield lambda: list(lines)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def until(predicate, seconds=8):
    """Wait for something to become true, and say what was seen if it does not.

    The watcher's loop is a second long, so every case here would otherwise carry a sleep
    chosen by guesswork: too short is flaky, too long is a suite nobody runs.
    """
    deadline = time.time() + seconds
    while time.time() < deadline:
        found = predicate()
        if found:
            return found
        time.sleep(0.1)
    return None


def digest(path):
    """A file as a short hash, so a failed comparison prints a line and not a page."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12] if path.exists() else None


def get(base, path):
    """GET a JSON endpoint."""
    with urllib.request.urlopen(base + path, timeout=10) as answer:
        return json.loads(answer.read() or b"{}")


def build(repo, rng):
    """The page data for a range, as review.py gets it.

    Run as a subprocess rather than imported, because build_data resolves nothing at
    import and this is the interface review.py actually uses.
    """
    done = subprocess.run(
        [sys.executable, str(TOOL / "build_data.py"), "--", rng],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        raise Failed(f"build_data failed for {rng!r}:\n{done.stderr.strip()}")
    return json.loads(done.stdout)


def log(run, rng):
    """The subjects in a range, newest first."""
    return [s for s in run("log", "--format=%s", rng).stdout.split("\n") if s]


def commit(short, subject, additions=0):
    """A rail entry shaped the way build_data builds one, empty marks included.

    The empty strings matter: a helper that left them out made mark_survival look wrong
    when it was the fake commit that was unfaithful.
    """
    return dict(
        short=short,
        hash=short * 8,
        subject=subject,
        headline=subject,
        read="",
        readWhy="",
        additions=additions,
        deletions=0,
        files=[],
    )


def run(only=""):
    chosen = [c for c in CASES if only in c.__name__]
    if not chosen:
        raise SystemExit(f"no case matches {only!r}")
    failed = []
    for fn in chosen:
        try:
            fn()
        except Failed as problem:
            failed.append((fn.__name__, str(problem)))
        except Exception as problem:  # noqa: BLE001
            failed.append((fn.__name__, f"{type(problem).__name__}: {problem}"))
    for name, problem in failed:
        print(f"FAIL {name}\n  {problem}\n", file=sys.stderr)
    print(f"{len(chosen) - len(failed)} of {len(chosen)} passed")
    return 1 if failed else 0
