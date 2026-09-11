#!/usr/bin/env python3
"""Turn a git range into the JSON the review page renders.

    python3 build_data.py [<range>] [--repo <path>] [--narrative <file>]

Defaults to `origin/main...HEAD`. Everything the page shows comes from git; a
narrative file only adds the editorial layer on top (see narrative.example.json).
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

import paths

FILE_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$")
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")
COLLAPSE_DELETIONS_OVER = 40


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def check_range(repo, rng):
    """Fail with something actionable, rather than passing git's usage text along."""
    probe = subprocess.run(["git", "-C", str(repo), "rev-list", "--count", rng],
                           capture_output=True, text=True)
    if probe.returncode == 0:
        return
    hint = "try an explicit range such as HEAD~3..HEAD"
    if "origin/" in rng:
        hint = f"'git fetch origin' first, or pass an explicit range such as HEAD~3..HEAD"
    raise SystemExit(f"cannot resolve the range {rng!r} in {repo.name}: {hint}")


def parse_patch(patch):
    files, current = [], None
    old_no = new_no = 0
    for line in patch.split("\n"):
        match = FILE_RE.match(line)
        if match:
            current = dict(path=match.group(2), status="modified", rows=[])
            files.append(current)
            continue
        if current is None:
            continue
        if line.startswith("new file"):
            current["status"] = "added"
            continue
        if line.startswith("deleted file"):
            current["status"] = "deleted"
            continue
        if line.startswith(("index ", "--- ", "+++ ", "similarity ", "rename ", "Binary ")):
            continue
        hunk = HUNK_RE.match(line)
        if hunk:
            old_no, new_no = int(hunk.group(1)), int(hunk.group(3))
            current["rows"].append(dict(t="hunk", text=line.rstrip()))
            continue
        if not line:
            continue
        tag, body = line[0], line[1:]
        if tag == "+":
            current["rows"].append(dict(t="add", n=new_no, text=body))
            new_no += 1
        elif tag == "-":
            current["rows"].append(dict(t="del", o=old_no, text=body))
            old_no += 1
        elif tag == "\\":
            continue
        else:
            current["rows"].append(dict(t="ctx", o=old_no, n=new_no, text=body))
            old_no += 1
            new_no += 1
    return files


def title_from_branch(branch):
    """`ci/check-unsafe-migrations` -> `Check Unsafe Migrations`."""
    tail = branch.split("/")[-1]
    tail = re.sub(r"^\d+[-_]", "", tail)
    words = [w for w in re.split(r"[-_.]+", tail) if w]
    return " ".join(w.capitalize() for w in words) or branch or "Branch Review"


def shortstat_numbers(text):
    files = int(m.group(1)) if (m := re.search(r"(\d+) files? changed", text)) else 0
    adds = int(m.group(1)) if (m := re.search(r"(\d+) insertions?", text)) else 0
    dels = int(m.group(1)) if (m := re.search(r"(\d+) deletions?", text)) else 0
    return files, adds, dels


def matches_commit(key, full, short):
    """Whether a narrative key names this commit. Kept in one place so the check that
    validates a narrative and the code that applies it can never drift apart."""
    return full.startswith(key) or key.startswith(short)


# Three words, not a taxonomy of change kinds. What sort of change it is belongs in the
# one-line reason; these say only what the reviewer should do about it.
READ_MARKS = ("start", "care", "skim")
READ_WHY_MAX = 80


def validate_read_marks(per_commit, commit_count, problems, warnings):
    """Check the per-commit reading marks, and keep them scarce.

    A marker that every commit carries tells the reviewer nothing, so the limits here are
    the point rather than an afterthought: one commit may be the place to start, `skim`
    has to say why it is safe to skim, and a branch where most commits are marked as
    important has marked none of them.
    """
    starts = []
    cares = 0
    for key, value in per_commit.items():
        if not isinstance(value, dict):
            continue
        mark = value.get("read", "")
        why = value.get("readWhy", "")
        if not mark:
            if why:
                warnings.append(f"{key}: has a 'readWhy' but no 'read', so nothing is drawn")
            continue
        if mark not in READ_MARKS:
            problems.append(
                f"{key}: read {mark!r} is not one of " + ", ".join(repr(m) for m in READ_MARKS))
            continue
        if mark == "start":
            starts.append(key)
        if mark == "care":
            cares += 1
        if mark == "skim" and not why:
            problems.append(
                f"{key}: read 'skim' needs a 'readWhy' saying why it is safe to skim")
        if len(why) > READ_WHY_MAX:
            problems.append(
                f"{key}: 'readWhy' is {len(why)} characters, over the {READ_WHY_MAX} that fit "
                "on one line in the rail")

    if len(starts) > 1:
        problems.append("read 'start': only one commit can be the place to start, found "
                        + ", ".join(starts))
    if commit_count and cares > max(1, commit_count // 3):
        warnings.append(f"read 'care' is on {cares} of {commit_count} commits, which reads as "
                        "no emphasis at all")


def is_placeholder(entry):
    """An entry left exactly as the scaffold wrote it, with every field still empty.

    The scaffold ships one of each so the shape is visible without opening the reference.
    An untouched one is not something the reader should see, and it is not an error
    either, so it is dropped before the page and skipped by the checks below.
    """
    return isinstance(entry, dict) and not any(entry.values())


def mark_number(mark):
    """A stage mark as a rail position, or None if it does not name one.

    Written as strings in every narrative so far, because the page prints them straight
    into a chip, so both forms have to read as the same number.
    """
    if isinstance(mark, bool):
        return None
    if isinstance(mark, int):
        return mark
    if isinstance(mark, str) and mark.strip().isdigit():
        return int(mark.strip())
    return None


def validate_narrative(narrative, commits, fulls, shorts):
    """Check a narrative against the range it will be drawn on.

    Two kinds of wrong, and they are not the same. A malformed entry — a stage with no
    label, a figure with no value — is always a mistake in the file, and the page draws a
    frame around nothing, so refuse to build. A narrative that no longer matches its
    commits is not a mistake: rebasing and squashing rewrite shas by design, and the
    squash button rebuilds the page immediately afterwards. Failing there would leave a
    repo that had just been rewritten with no page to read it on. Those are warnings.

    Both are invisible on the page itself, which is the reason to say anything at all.
    """
    problems, warnings = [], []

    per_commit = narrative.get("commits", {})
    if not isinstance(per_commit, dict):
        problems.append("commits: must be an object keyed by sha prefix")
        per_commit = {}
    for key in per_commit:
        hits = [f for f, s in zip(fulls, shorts) if matches_commit(key, f, s)]
        if not hits:
            warnings.append(f"{key!r} matches no commit in this range")
        elif len(hits) > 1:
            warnings.append(f"{key!r} is ambiguous, it matches {len(hits)} commits")

    validate_read_marks(per_commit, len(commits), problems, warnings)

    seen = {}
    stages = narrative.get("stages") or []
    if not isinstance(stages, list):
        problems.append("stages: must be a list")
        stages = []
    for position, stage in enumerate(stages, 1):
        if is_placeholder(stage):
            continue
        if not isinstance(stage, dict) or not stage.get("where") or not stage.get("what"):
            problems.append(f"stages[{position}]: needs both 'where' and 'what'")
            continue
        marks = stage.get("marks") or []
        if not isinstance(marks, list):
            problems.append(f"stages[{position}] ({stage['where']!r}): 'marks' must be a list")
            continue
        for mark in marks:
            number = mark_number(mark)
            if number is None:
                problems.append(
                    f"stages[{position}] ({stage['where']!r}): mark {mark!r} is not a number")
            elif not 1 <= number <= len(commits):
                warnings.append(
                    f"stage {stage['where']!r} marks commit {number}, "
                    f"but the rail is {len(commits)} long")
            else:
                seen.setdefault(number, []).append(stage["where"])

    figures = narrative.get("figures") or []
    if not isinstance(figures, list):
        problems.append("figures: must be a list")
        figures = []
    for position, figure in enumerate(figures, 1):
        if is_placeholder(figure):
            continue
        if not isinstance(figure, dict) or not figure.get("k") or not figure.get("v"):
            problems.append(f"figures[{position}]: needs both 'k' and 'v'")

    for mark, wheres in sorted(seen.items()):
        if len(wheres) > 1:
            warnings.append(f"commit {mark} is claimed by {len(wheres)} stages: "
                            + ", ".join(repr(w) for w in wheres))
    if seen:
        missing = [n for n in range(1, len(commits) + 1) if n not in seen]
        if missing:
            warnings.append("no stage claims commit(s) "
                            + ", ".join(str(n) for n in missing))

    for warning in warnings:
        print(f"narrative: {warning}", file=sys.stderr)
    if problems:
        raise SystemExit("narrative: " + "\n           ".join(problems))


def fallback_narrative(index, subject, body):
    first_para = body.split("\n\n")[0].replace("\n", " ").strip() if body else ""
    return dict(stage=f"{index + 1}", flow="", why=first_para or subject, points=[], matrix=None)


FIXUP_RE = re.compile(r"^(fixup!|squash!|amend!)\s+")


def fold_fixups(commits):
    """Attach every fixup to the commit it amends, and return what is left.

    A fixup is not a commit to review on its own. It is an amendment to one already
    reviewed, and git squashes it away at the end, so listing it beside real commits
    doubles the length of a review with nothing new to read.

    Its diff still matters, so it moves inside its target rather than disappearing, and
    it keeps its own sha: threads anchor to that, so folding changes where a fixup is
    drawn and nothing else.

    A fixup whose target is not in the range has nothing to attach to and stays a commit
    of its own.
    """
    first_with_subject = {}
    for commit in commits:
        first_with_subject.setdefault(commit["subject"], commit)

    kept, kept_ids = [], set()
    for commit in commits:
        target_subject = commit["subject"]
        # "git commit --fixup" onto a fixup stacks the prefixes: fixup! fixup! <subject>.
        while FIXUP_RE.match(target_subject):
            target_subject = FIXUP_RE.sub("", target_subject, count=1)

        target = first_with_subject.get(target_subject)
        # Only fold backwards, onto a commit already kept. A target that comes later is
        # not the one this fixup amends.
        if target_subject != commit["subject"] and target is not None and id(target) in kept_ids:
            target.setdefault("followups", []).append(commit)
            continue

        kept.append(commit)
        kept_ids.add(id(commit))
    return kept


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("range", nargs="?", default="origin/main...HEAD")
    parser.add_argument("--repo", default=None)
    parser.add_argument("--narrative", default=None)
    args = parser.parse_args()

    repo = paths.repo_root(args.repo) if args.repo else paths.repo_root()
    rng = args.range
    base = rng.split("..")[0] or "origin/main"

    narrative = {}
    if args.narrative and pathlib.Path(args.narrative).exists():
        narrative = json.loads(pathlib.Path(args.narrative).read_text())
    per_commit = narrative.get("commits", {})

    check_range(repo, rng)
    shas = [s for s in git(repo, "log", "--format=%h", "--reverse", rng).strip().split("\n") if s]
    if not shas:
        raise SystemExit(f"no commits in range {rng}")

    commits = []
    fulls = []
    for index, short in enumerate(shas):
        meta = git(repo, "show", "-s", "--format=%H%x00%s%x00%b", short).split("\x00")
        full, subject, body = meta[0].strip(), meta[1].strip(), meta[2].strip()
        fulls.append(full)
        kind, _, headline = subject.partition(": ")
        if not headline:
            kind, headline = "", subject

        stats = {}
        for row in git(repo, "show", "--numstat", "--format=", short).strip().split("\n"):
            parts = row.split("\t")
            if len(parts) == 3 and parts[0] != "-":
                stats[parts[2]] = (int(parts[0]), int(parts[1]))

        files = parse_patch(git(repo, "show", "--format=", "--patch", "--unified=3", short))
        for entry in files:
            add, dele = stats.get(entry["path"], (0, 0))
            entry["additions"], entry["deletions"] = add, dele
            entry["collapsed"] = entry["status"] == "deleted" and dele > COLLAPSE_DELETIONS_OVER

        # A narrative may key a commit by any unambiguous prefix of its sha. Empty values
        # are skipped so a scaffold that has only been half filled in leaves the commit's
        # own message in place rather than replacing it with nothing.
        note = fallback_narrative(index, subject, body)
        for key, value in per_commit.items():
            if matches_commit(key, full, short):
                note = {**note, **{k: v for k, v in value.items() if v not in ("", [], None)}}
                break

        commits.append(dict(
            short=short, hash=full, kind=kind, headline=headline, subject=subject, body=body,
            stage=note.get("stage") or str(index + 1),
            read=note.get("read", ""), readWhy=note.get("readWhy", ""),
            flow=note.get("flow", ""), why=note.get("why", ""),
            points=note.get("points", []), matrix=note.get("matrix"),
            matrixCaption=note.get("matrixCaption", ""),
            additions=sum(f["additions"] for f in files),
            deletions=sum(f["deletions"] for f in files),
            files=files,
        ))

    commits = fold_fixups(commits)
    folded = sum(len(c.get("followups", [])) for c in commits)

    # After folding, because a stage's marks are rail positions and the rail is what is
    # left once fixups have moved inside the commits they amend.
    validate_narrative(narrative, commits, fulls, shas)

    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    total_files, total_adds, total_dels = shortstat_numbers(
        git(repo, "diff", "--shortstat", rng)
    )
    default_figures = [
        {"k": "commits", "v": str(len(commits))},
        {"k": "files changed", "v": str(total_files)},
        {"k": "lines added", "v": str(total_adds)},
        {"k": "lines removed", "v": str(total_dels)},
    ]
    if folded:
        default_figures.insert(1, {"k": "follow-ups", "v": str(folded)})

    print(json.dumps(dict(
        commits=commits,
        branch=branch,
        base=base,
        range=rng,
        repo=repo.name,
        totals=git(repo, "diff", "--shortstat", rng).strip(),
        title=narrative.get("title") or title_from_branch(branch),
        dek=narrative.get("dek") or (
            f"{len(commits)} commit{'s' if len(commits) != 1 else ''} on {branch}, "
            f"compared against {base}."
        ),
        eyebrow=narrative.get("eyebrow", ""),
        figures=[f for f in (narrative.get("figures") or []) if not is_placeholder(f)]
                or default_figures,
        stages=[s for s in (narrative.get("stages") or []) if not is_placeholder(s)],
        notes=[n for n in (narrative.get("notes") or []) if not is_placeholder(n)],
    )))


if __name__ == "__main__":
    main()
