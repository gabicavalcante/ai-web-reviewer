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
        capture_output=True,
        text=True,
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
    base = (
        pathlib.Path(os.environ.get("XDG_STATE_HOME", pathlib.Path.home() / ".local/state"))
        / "web-reviewer"
    )
    digest = hashlib.sha256(str(repo.resolve()).encode()).hexdigest()[:8]
    target = base / f"{repo.name}-{digest}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def resolve_range(rng, repo=None):
    """A range with HEAD replaced by the branch it currently names.

    A range is not an identifier until this has happened. "origin/main...HEAD" is the
    default, so every branch in a checkout reviewed without an explicit range produces the
    same string, the same directory, and the second review overwrites the first page.

    Only an endpoint that is exactly HEAD is replaced. HEAD~3 resolves to a sha that moves
    every time a commit lands, and a key that changes on every commit is no key at all.

    Resolve once, when a review starts, and pass the result down. Resolving again later
    would follow a branch switch and point a running server at a directory nobody built.
    """
    sep = "..." if "..." in rng else ".." if ".." in rng else None
    if sep is None:
        return rng
    name = subprocess.run(
        ["git", "-C", str(repo or repo_root()), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    here = name.stdout.strip()
    if name.returncode != 0 or not here:
        return rng
    if here == "HEAD":
        sha = subprocess.run(
            ["git", "-C", str(repo or repo_root()), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
        )
        here = sha.stdout.strip() or "HEAD"
    return sep.join(here if part.strip() == "HEAD" else part for part in rng.split(sep))


def commit_range(rng, repo=None):
    """The range as one set of commits, for anything that has to count them.

    `git log a...b` is the symmetric difference, commits on either side. `git diff a...b`
    is merge-base..b, one side. The same string meant two different sets, and
    "origin/main...HEAD" is the default, so every commit origin/main gained since the
    branch started was listed on the rail and absent from the diff it was measured
    against. One real review showed 97 commits for a branch holding 23.

    Worse than untidy: the survival mark measures a commit against the diff, so all of
    those scored zero and the page printed "nothing it added is still in the branch" over
    work that was very much still in the branch.

    Separate from resolve_range on purpose. That one decides a review's identity, and
    rewriting it here would rename every folder on disk and orphan the threads inside.
    This is only for asking git which commits a range holds.
    """
    if "..." not in rng:
        return rng
    left, _, right = rng.partition("...")
    left, right = left.strip() or "origin/main", right.strip()
    found = subprocess.run(
        ["git", "-C", str(repo or repo_root()), "merge-base", left, right],
        capture_output=True,
        text=True,
    )
    base = found.stdout.strip()
    return f"{base}..{right}" if found.returncode == 0 and base else rng


def review_dir(rng, repo=None, create=False):
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

    Asking for the path does not create it. Only the two callers that write a file pass
    create, because a function that makes a directory when asked where something would go
    leaves one behind every time anything wonders.
    """
    # Trimmed from the front, because a range ends at the branch and that is the half
    # worth reading. "long-sha..ci/check-unsafe-migrations" cut to its first 48 characters
    # is all sha and no branch.
    slug = re.sub(r"[^A-Za-z0-9]+", "-", rng).strip("-").lower()
    slug = (slug[-48:].strip("-") if len(slug) > 48 else slug) or "review"
    digest = hashlib.sha256(rng.encode()).hexdigest()[:8]
    target = state_dir(repo) / f"{slug}-{digest}"
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


# What review_dir builds: a slug and eight hex characters of digest.
REVIEW_DIR = re.compile(r"-[0-9a-f]{8}$")


def reviews(repo=None):
    """Every review in this checkout, by directory.

    The state directory is a directory, so anything can be in it, and a store written by
    an older layout holds folders the tool no longer makes. Recognising the name a review
    has is steadier than listing the names it does not: a folder nobody expected is not a
    review either, and the watcher that has to ask "which review?" should not count it.
    """
    return sorted(
        p for p in state_dir(repo).iterdir() if p.is_dir() and REVIEW_DIR.search(p.name)
    )


def page(rng, repo=None, create=False):
    """The built page for one range."""
    return review_dir(rng, repo, create) / "index.html"


def narrative(rng, repo=None, create=False):
    """The narrative for one range, next to the page it renders."""
    return review_dir(rng, repo, create) / "narrative.json"


def logs(rng, repo=None, create=False):
    """The append-only thread logs for one review.

    Beside the page and the narrative, because everything a review has belongs together.
    Reading them then costs what this review holds rather than every question ever asked
    in the checkout, which is what made the cost of a poll grow without limit.
    """
    where = review_dir(rng, repo, create)
    return {
        "questions": where / "questions.jsonl",
        "messages": where / "messages.jsonl",
        "resolved": where / "resolved.jsonl",
        "answers": where / "answers.jsonl",
    }
