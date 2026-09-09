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
    for index, short in enumerate(shas):
        meta = git(repo, "show", "-s", "--format=%H%x00%s%x00%b", short).split("\x00")
        full, subject, body = meta[0].strip(), meta[1].strip(), meta[2].strip()
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

        # A narrative may key a commit by any unambiguous prefix of its sha.
        note = fallback_narrative(index, subject, body)
        for key, value in per_commit.items():
            if full.startswith(key) or key.startswith(short):
                note = {**note, **value}
                break

        commits.append(dict(
            short=short, hash=full, kind=kind, headline=headline, subject=subject, body=body,
            stage=note.get("stage") or str(index + 1),
            flow=note.get("flow", ""), why=note.get("why", ""),
            points=note.get("points", []), matrix=note.get("matrix"),
            matrixCaption=note.get("matrixCaption", ""),
            additions=sum(f["additions"] for f in files),
            deletions=sum(f["deletions"] for f in files),
            files=files,
        ))

    commits = fold_fixups(commits)
    folded = sum(len(c.get("followups", [])) for c in commits)

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
        figures=narrative.get("figures") or default_figures,
        stages=narrative.get("stages") or [],
        notes=narrative.get("notes") or [],
    )))


if __name__ == "__main__":
    main()
