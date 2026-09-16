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
    probe = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--count", rng], capture_output=True, text=True
    )
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

# How many commits may ask to be read closely. A share of the branch was the first rule,
# and it does not hold at the top: a third of forty is thirteen, and nobody holds thirteen.
# What a reader can keep in mind does not grow with the branch, so the count is capped
# too, and the stricter of the two applies.
CARE_MAX = 5
FILE_NOTE_MAX = 80

# Measured from a narrative that reads well, set just above the longest field in it.
#
# There is no cap on the dek, and the reason is worth keeping. A padded dek and a good one
# came out the same length when measured, so a limit there would refuse sentences that
# read well and pass sentences that do not. Length catches sprawl. It does not catch a
# sentence that states a fact as an effect on the reader, which is what a bad dek does,
# and only the examples in reference/voice.md catch that.
STAGE_WHAT_MAX = 120
WHY_MAX = 450


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
                f"{key}: read {mark!r} is not one of " + ", ".join(repr(m) for m in READ_MARKS)
            )
            continue
        if mark == "start":
            starts.append(key)
        if mark == "care":
            cares += 1
        if mark == "skim" and not why:
            problems.append(
                f"{key}: read 'skim' needs a 'readWhy' saying why it is safe to skim"
            )
        if len(why) > READ_WHY_MAX:
            problems.append(
                f"{key}: 'readWhy' is {len(why)} characters, over the {READ_WHY_MAX} that fit "
                "on one line in the rail"
            )

    if len(starts) > 1:
        problems.append(
            "read 'start': only one commit can be the place to start, found "
            + ", ".join(starts)
        )
    if commit_count:
        limit = min(CARE_MAX, max(1, commit_count // 3))
        if cares > limit:
            warnings.append(
                f"read 'care' is on {cares} of {commit_count} commits, and {limit} is as many "
                "as carries any emphasis"
            )


def git_maybe(repo, *args):
    """git, returning None instead of exiting when the command fails.

    Blame fails for good reasons: a file the branch deleted has no final content. That is
    not a build error.

    errors="replace" because blame on a binary file does not fail. It succeeds and prints
    the bytes, and decoding them as UTF-8 threw, so a branch that touched a PNG could not
    be built at all. Binary files are skipped before they get here, and this is the second
    line: no git output should be able to stop a build by not being text.
    """
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, errors="replace"
    )
    return result.stdout if result.returncode == 0 else None


BLAME_LINE = re.compile(r"^([0-9a-f]{40}) \d+ (\d+)")


def range_tip(rng):
    """The commit a range ends at.

    Blame has to read the branch under review, not whatever happens to be checked out.
    One repo can hold two reviews, and building one of them while the other's branch is
    checked out found nothing to attribute and said so silently.
    """
    # Three dots before two, or "origin/main...HEAD" splits into ".HEAD", which is not a
    # revision and which blame refuses for every file in silence.
    if "..." in rng:
        tip = rng.split("...")[-1]
    elif ".." in rng:
        tip = rng.split("..")[-1]
    else:
        tip = rng
    return tip.strip() or "HEAD"


def surviving_lines(repo, tip, path):
    """Which lines of the file as it stands now came from each commit.

    Blame credits the commit that last touched a line, so this is what survived rather
    than what was written. A commit whose work was rewritten later owns nothing here,
    which is the point: it should not be pulling a file into its stage, and its lines are
    not in the file to be read.
    """
    out = git_maybe(repo, "blame", "--line-porcelain", "-M", tip, "--", path)
    if out is None:
        return {}
    lines = {}
    for row in out.split("\n"):
        found = BLAME_LINE.match(row)
        if found:
            lines.setdefault(found.group(1), []).append(int(found.group(2)))
    return lines


def to_runs(numbers):
    """Sorted line numbers as [start, end] runs, which is how they are read and drawn."""
    runs = []
    for number in sorted(numbers):
        if runs and number == runs[-1][1] + 1:
            runs[-1][1] = number
        else:
            runs.append([number, number])
    return runs


def mark_survival(commits, alive_by_sha):
    """Say how much of each commit is still in the branch, and skim what is not.

    A commit and the fixups folded into it are one entry on the rail, so they are counted
    together. Blame credits a line to whoever touched it last, so a commit rewritten by a
    later one scores nothing, which is the case worth seeing: on a long branch the rail is
    full of work that no longer exists, and reading it in order means reading that.

    A mark the narrative already set is left alone. This fills a gap, it does not overrule
    a person.

    Blame runs with -M, so a block a later commit copied inside a file is credited to the
    commit that first wrote it, and a commit can be blamed for more lines than it added.
    On a real branch a commit that added 271 lines to a test file was blamed for 379, the
    difference being blocks a later commit copied. That is why the rail asks whether most
    of a commit is gone rather than subtracting one number from the other.
    """
    for commit in commits:
        sources = [commit] + list(commit.get("followups") or [])
        added = sum(source.get("additions", 0) for source in sources)
        alive = sum(alive_by_sha.get(source["hash"], 0) for source in sources)
        commit["added"] = added
        commit["alive"] = alive
        if added and not alive and not commit.get("read"):
            commit["read"] = "skim"
            commit["readWhy"] = "nothing it added is still in the branch"
            # So the rail does not print the counts underneath a line that already said it.
            commit["autoSkim"] = True


def file_tier(path):
    """Where a file sits in a reading order: the code, then what documents it, then what
    tests it. A test read before its subject is a list of assertions about nothing."""
    name = path.rsplit("/", 1)[-1]
    if name == "conftest.py" or name.startswith("test_") or "_test." in name:
        return 2
    if "/tests/" in "/" + path or path.startswith("tests/"):
        return 2
    if path.endswith((".md", ".rst", ".txt")):
        return 1
    return 0


def test_stem(path):
    """The name a test file is probably about. test_admin_mfa.py -> admin_mfa."""
    name = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    if name.startswith("test_"):
        name = name[5:]
    if name.endswith("_test"):
        name = name[:-5]
    return name


def pair_tests(files):
    """Move a test to sit under the file it names, when that file is in the same group.

    Only by name, so it is a guess, and a wrong guess costs an ordering rather than
    anything a reader would trust. A test that names nothing here stays with the tests.
    """
    subjects = {}
    for entry in files:
        if file_tier(entry["path"]) == 0:
            subjects.setdefault(test_stem(entry["path"]), entry["path"])

    ordered, deferred = [], {}
    for entry in files:
        if file_tier(entry["path"]) == 2:
            target = subjects.get(test_stem(entry["path"]))
            if target:
                deferred.setdefault(target, []).append(entry)
                continue
        ordered.append(entry)

    out = []
    for entry in ordered:
        out.append(entry)
        out.extend(deferred.pop(entry["path"], []))
    for rest in deferred.values():
        out.extend(rest)
    return out


def final_diff(repo, rng, commits, narrative):
    """The branch as one diff, with each file placed under the stage that reaches it first.

    The commit rail answers "how did this get built". On a long branch that is the wrong
    question to start with, because later commits rewrite earlier ones and reading in
    order means reading code that is no longer there. This answers "what does it do now",
    in the order the stages tell it.

    A file touched by several stages is listed once, under the first, and carries the
    others so the reader knows where else it matters. Repeating a whole file under four
    stages would be worse than telling them.
    """
    files = parse_patch(git(repo, "diff", "--patch", "--unified=3", rng))
    if not files:
        # A range whose diff is empty was undone by its own later commits, so every commit
        # on the rail has nothing left. Say that rather than leaving the counts unset.
        mark_survival(commits, {})
        return None
    tip = range_tip(rng)

    # numstat writes "-" for both counts of a binary file, which is how git says the file
    # has no lines. Blame does not say that: it prints the bytes and leaves the caller to
    # find out. So the paths are collected here and never blamed.
    stats, binary = {}, set()
    for row in git(repo, "diff", "--numstat", rng).strip().split("\n"):
        parts = row.split("\t")
        if len(parts) != 3:
            continue
        if parts[0] == "-":
            binary.add(parts[2])
        else:
            stats[parts[2]] = (int(parts[0]), int(parts[1]))
    for entry in files:
        add, dele = stats.get(entry["path"], (0, 0))
        entry["additions"], entry["deletions"] = add, dele
        entry["binary"] = entry["path"] in binary
        entry["collapsed"] = entry["status"] == "deleted" and dele > COLLAPSE_DELETIONS_OVER

    # Which stages reach a file, and which commit belongs to which stage. A mark is a rail
    # position, and a commit's followups are part of it, so a fixup belongs to its
    # target's stage.
    order, touched, stage_of = [], {}, {}
    for stage in narrative.get("stages") or []:
        if is_placeholder(stage) or not stage.get("where"):
            continue
        order.append(stage["where"])
        for mark in stage.get("marks") or []:
            index = mark_number(mark)
            if index is None or not 1 <= index <= len(commits):
                continue
            commit = commits[index - 1]
            for source in [commit] + list(commit.get("followups") or []):
                stage_of[source["hash"]] = stage["where"]
                for entry in source["files"]:
                    touched.setdefault(entry["path"], [])
                    if stage["where"] not in touched[entry["path"]]:
                        touched[entry["path"]].append(stage["where"])

    # Blame is already being run over every file below. Totalling it per commit as well
    # costs nothing and answers the question the rail cannot: how much of what a commit
    # added is still in the branch.
    alive_by_sha = {}

    # What the narrative says about individual files. The tool can order a file and weigh
    # it; only a person can say what it is for in this change.
    per_file = narrative.get("files") or {}
    problems, warnings = [], []
    if not isinstance(per_file, dict):
        problems.append("files: must be an object keyed by path")
        per_file = {}
    known = {entry["path"] for entry in files}
    for path in per_file:
        if path not in known:
            warnings.append(f"files: {path!r} is not in this range")

    for entry in files:
        said = per_file.get(entry["path"]) or {}
        if not isinstance(said, dict):
            problems.append(f"files[{entry['path']}]: must be an object")
            said = {}
        entry["read"] = said.get("read", "")
        entry["note"] = said.get("note", "")
        if entry["read"] and entry["read"] not in READ_MARKS:
            problems.append(
                f"files[{entry['path']}]: read {entry['read']!r} is not one of "
                + ", ".join(repr(m) for m in READ_MARKS)
            )
            entry["read"] = ""
        if entry["read"] == "skim" and not entry["note"]:
            problems.append(
                f"files[{entry['path']}]: read 'skim' needs a note saying why it "
                "is safe to skim"
            )
        if len(entry["note"]) > FILE_NOTE_MAX:
            problems.append(
                f"files[{entry['path']}]: note is {len(entry['note'])} characters, "
                f"over the {FILE_NOTE_MAX} that fit beside a path"
            )

    for entry in files:
        reaching = touched.get(entry["path"], [])
        # Ordered by how much of the file as it stands now each stage actually wrote.
        # Placing a file under the first stage to mention it put two thirds of this
        # branch under its first stage and left one stage with no files at all.
        weight, by_stage = {}, {}
        if entry["status"] != "deleted" and not entry["binary"]:
            for sha, numbers in surviving_lines(repo, tip, entry["path"]).items():
                alive_by_sha[sha] = alive_by_sha.get(sha, 0) + len(numbers)
                where = stage_of.get(sha)
                if where:
                    weight[where] = weight.get(where, 0) + len(numbers)
                    by_stage.setdefault(where, []).extend(numbers)
        if weight:
            ranked = sorted(reaching, key=lambda w: (-weight.get(w, 0), order.index(w)))
        else:
            # A deleted or binary file, or one whose surviving lines predate the branch.
            # Nothing to weigh, so the strip's own order decides.
            ranked = sorted(reaching, key=order.index)
        entry["stages"] = ranked
        entry["lines"] = {where: weight.get(where, 0) for where in ranked}
        # Where each stage's surviving lines are, so the page can show a stage's own work
        # inside a file another stage owns. Runs rather than line numbers, because that is
        # what a reader is shown and it keeps the page small.
        entry["runs"] = {where: to_runs(numbers) for where, numbers in by_stage.items()}

    # One place to start per stage, or the mark stops meaning anything. Checked here
    # rather than with the rest, because only now is it known which stage a file is under.
    starts = {}
    for entry in files:
        if entry.get("read") == "start":
            owner = (entry["stages"] or [None])[0]
            starts.setdefault(owner, []).append(entry["path"])
    for owner, paths in starts.items():
        if len(paths) > 1:
            problems.append(
                f"files: {len(paths)} files marked 'start' under "
                f"{owner or 'no stage'}: " + ", ".join(paths)
            )
    for warning in warnings:
        print(f"narrative: {warning}", file=sys.stderr)
    if problems:
        raise SystemExit("narrative: " + "\n           ".join(problems))

    mark_survival(commits, alive_by_sha)

    rank = {where: i for i, where in enumerate(order)}
    files.sort(
        key=lambda e: (
            rank.get((e["stages"] or [None])[0], len(order)),
            file_tier(e["path"]),
            -sum(e.get("lines", {}).values()),
            e["path"],
        )
    )

    # Pairing happens inside a group, because a test and its subject being in different
    # stages is a fact about the change and not something to reorder away.
    paired, group = [], []
    for entry in files:
        owner = (entry["stages"] or [None])[0]
        if group and (group[0]["stages"] or [None])[0] != owner:
            paired.extend(pair_tests(group))
            group = []
        group.append(entry)
    paired.extend(pair_tests(group))
    return {"files": paired, "order": order}


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
    for key, entry in per_commit.items():
        why = (entry or {}).get("why") or "" if isinstance(entry, dict) else ""
        if len(why) > WHY_MAX:
            problems.append(
                f"{key}: 'why' is {len(why)} characters, over {WHY_MAX}. One or two sentences"
            )
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
        if len(stage["what"]) > STAGE_WHAT_MAX:
            problems.append(
                f"stages[{position}] ({stage['where']!r}): 'what' is "
                f"{len(stage['what'])} characters, over {STAGE_WHAT_MAX}. It is "
                "one line in a box"
            )
        marks = stage.get("marks") or []
        if not isinstance(marks, list):
            problems.append(f"stages[{position}] ({stage['where']!r}): 'marks' must be a list")
            continue
        for mark in marks:
            number = mark_number(mark)
            if number is None:
                problems.append(
                    f"stages[{position}] ({stage['where']!r}): mark {mark!r} is not a number"
                )
            elif not 1 <= number <= len(commits):
                warnings.append(
                    f"stage {stage['where']!r} marks commit {number}, "
                    f"but the rail is {len(commits)} long"
                )
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
            warnings.append(
                f"commit {mark} is claimed by {len(wheres)} stages: "
                + ", ".join(repr(w) for w in wheres)
            )
    if seen:
        missing = [n for n in range(1, len(commits) + 1) if n not in seen]
        if missing:
            warnings.append("no stage claims commit(s) " + ", ".join(str(n) for n in missing))

    for warning in warnings:
        print(f"narrative: {warning}", file=sys.stderr)
    if problems:
        raise SystemExit("narrative: " + "\n           ".join(problems))


def fallback_narrative(index, subject, body):
    first_para = body.split("\n\n")[0].replace("\n", " ").strip() if body else ""
    return dict(
        stage=f"{index + 1}", flow="", why=first_para or subject, points=[], matrix=None
    )


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
        if (
            target_subject != commit["subject"]
            and target is not None
            and id(target) in kept_ids
        ):
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
    shas = [
        s for s in git(repo, "log", "--format=%h", "--reverse", rng).strip().split("\n") if s
    ]
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
            entry["collapsed"] = (
                entry["status"] == "deleted" and dele > COLLAPSE_DELETIONS_OVER
            )

        # A narrative may key a commit by any unambiguous prefix of its sha. Empty values
        # are skipped so a scaffold that has only been half filled in leaves the commit's
        # own message in place rather than replacing it with nothing.
        note = fallback_narrative(index, subject, body)
        for key, value in per_commit.items():
            if matches_commit(key, full, short):
                note = {**note, **{k: v for k, v in value.items() if v not in ("", [], None)}}
                break

        commits.append(
            dict(
                short=short,
                hash=full,
                kind=kind,
                headline=headline,
                subject=subject,
                body=body,
                stage=note.get("stage") or str(index + 1),
                read=note.get("read", ""),
                readWhy=note.get("readWhy", ""),
                flow=note.get("flow", ""),
                why=note.get("why", ""),
                points=note.get("points", []),
                matrix=note.get("matrix"),
                matrixCaption=note.get("matrixCaption", ""),
                additions=sum(f["additions"] for f in files),
                deletions=sum(f["deletions"] for f in files),
                files=files,
            )
        )

    commits = fold_fixups(commits)
    folded = sum(len(c.get("followups", [])) for c in commits)

    # After folding, because a stage's marks are rail positions and the rail is what is
    # left once fixups have moved inside the commits they amend.
    validate_narrative(narrative, commits, fulls, shas)

    # "" on a detached HEAD, matching what the server stamps on a thread. Leaving it as
    # the literal "HEAD" would make the page compare that string against real branch
    # names and file every orphan under another review.
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch == "HEAD":
        branch = ""
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

    print(
        json.dumps(
            dict(
                commits=commits,
                branch=branch,
                base=base,
                range=rng,
                repo=repo.name,
                totals=git(repo, "diff", "--shortstat", rng).strip(),
                title=narrative.get("title") or title_from_branch(branch),
                dek=narrative.get("dek")
                or (
                    f"{len(commits)} commit{'s' if len(commits) != 1 else ''} on {branch}, "
                    f"compared against {base}."
                ),
                eyebrow=narrative.get("eyebrow", ""),
                final=final_diff(repo, rng, commits, narrative),
                figures=[f for f in (narrative.get("figures") or []) if not is_placeholder(f)]
                or default_figures,
                stages=[s for s in (narrative.get("stages") or []) if not is_placeholder(s)],
                notes=[n for n in (narrative.get("notes") or []) if not is_placeholder(n)],
            )
        )
    )


if __name__ == "__main__":
    main()
