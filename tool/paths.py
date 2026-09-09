"""Where the repo is and where this review's state lives.

Shared by every script in the tool so they all agree, without any of them
hardcoding a path.
"""
import hashlib
import os
import pathlib
import subprocess


def repo_root(start=None):
    """The git work tree containing `start` (default: the current directory)."""
    result = subprocess.run(
        ["git", "-C", str(start or pathlib.Path.cwd()), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise SystemExit("not inside a git work tree")
    return pathlib.Path(result.stdout.strip())


def state_dir(repo=None):
    """Per-repo state, outside the repo so questions never land in git.

    The directory name carries the repo's basename for a human reading `ls`, plus a
    hash of its absolute path so two checkouts of the same project do not collide.
    """
    repo = pathlib.Path(repo) if repo else repo_root()
    base = pathlib.Path(
        os.environ.get("XDG_STATE_HOME", pathlib.Path.home() / ".local/state")
    ) / "web-reviewer"
    digest = hashlib.sha256(str(repo.resolve()).encode()).hexdigest()[:8]
    target = base / f"{repo.name}-{digest}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def logs(repo=None):
    """The append-only thread logs for this repo's review."""
    where = state_dir(repo)
    return {
        "questions": where / "questions.jsonl",
        "messages": where / "messages.jsonl",
        "resolved": where / "resolved.jsonl",
        "answers": where / "answers.jsonl",
    }
