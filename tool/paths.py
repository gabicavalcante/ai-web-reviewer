"""Where the repo is and where this review's state lives.

Shared by every script in the tool so they all agree, without any of them
hardcoding a path.
"""
import hashlib
import os
import re
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


def review_dir(rng, repo=None):
    """One directory per review, inside the repo's state directory.

    Two ranges of one repo are two reviews, and they cannot share a page: each server
    reported the other's build as stale, and each Rebuild overwrote the other page.

    A directory rather than a hashed filename, so the files inside keep plain names. A
    narrative is meant to be opened and edited by hand, and `narrative-50fe69b9.json`
    beside `narrative-9ce5ede9.json` does not say which review it belongs to. The name
    carries the range for a human reading `ls`, plus a hash of it so two ranges that
    sanitise to the same text do not collide.

    The threads stay one level up. They are keyed by repo, and a thread outlives the
    range it was asked in.
    """
    # Trimmed from the front, because a range ends at the branch and that is the half
    # worth reading. "long-sha..ci/check-unsafe-migrations" cut to its first 48 characters
    # is all sha and no branch.
    slug = re.sub(r"[^A-Za-z0-9]+", "-", rng).strip("-").lower()
    slug = (slug[-48:].strip("-") if len(slug) > 48 else slug) or "review"
    digest = hashlib.sha256(rng.encode()).hexdigest()[:8]
    target = state_dir(repo) / f"{slug}-{digest}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def page(rng, repo=None):
    """The built page for one range."""
    return review_dir(rng, repo) / "index.html"


def narrative(rng, repo=None):
    """The narrative for one range, next to the page it renders."""
    return review_dir(rng, repo) / "narrative.json"


def logs(repo=None):
    """The append-only thread logs for this repo's review."""
    where = state_dir(repo)
    return {
        "questions": where / "questions.jsonl",
        "messages": where / "messages.jsonl",
        "resolved": where / "resolved.jsonl",
        "answers": where / "answers.jsonl",
    }
