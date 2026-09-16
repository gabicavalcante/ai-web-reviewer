"""What a case file needs, and the loop that runs them.

Kept apart from the cases so the pure-function checks and the end-to-end ones can share a
sandbox without one importing the other.
"""

import contextlib
import os
import pathlib
import subprocess
import sys
import tempfile

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
