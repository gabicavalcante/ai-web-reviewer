"""Checks over the pure parts: paths, folding, survival, marks, ordering.

No server and no page. Every case names the failure it holds down, so a case that starts
failing says what is about to go wrong rather than only that something did.
"""

import json

import build_data
import paths

from harness import build, build_stderr, case, commit, eq, Failed, sandbox

# --------------------------------------------------------------------------- paths


@case
def paths_resolve_range_replaces_head():
    """HEAD is not a name, so it is replaced before anything keys a directory off it.

    The watcher passed the range through unresolved, so the server wrote questions into
    one folder and the watcher sat over another. Both ran, neither complained, and no
    question was ever delivered.
    """
    with sandbox() as (repo, run):
        run("checkout", "-qb", "feature/login")
        eq(
            paths.resolve_range("origin/main...HEAD", repo),
            "origin/main...feature/login",
            "a three dot range ending in HEAD",
        )
        eq(
            paths.resolve_range("e8e4bb6..HEAD", repo),
            "e8e4bb6..feature/login",
            "a two dot range ending in HEAD",
        )


@case
def paths_resolve_range_splits_three_dots_first():
    """'origin/main...HEAD'.split('..') yields '.HEAD', which is not an endpoint.

    Splitting on two dots first turned the range into a different range, and the review
    it named was one nobody had built.
    """
    with sandbox() as (repo, _):
        got = paths.resolve_range("origin/main...HEAD", repo)
        if ".main" in got.replace("...", "") or got.count(".") != 3:
            raise Failed(f"three dots were not handled before two: {got!r}")
        eq(got, "origin/main...main", "the resolved default range")


@case
def paths_resolve_range_leaves_everything_else():
    """Only an endpoint that is exactly HEAD. HEAD~3 is a different commit every day, and
    a key that moves on every commit is no key at all."""
    with sandbox() as (repo, _):
        for rng in ("HEAD~3..main", "origin/main...topic", "abc1234..def5678", "main"):
            eq(paths.resolve_range(rng, repo), rng, f"{rng!r} should be left alone")


@case
def paths_review_dir_does_not_create():
    """Asking where something would go must not leave a directory behind.

    A watcher that created the folder it was pointed at turned a wrong range into a
    process that was running and silent at the same time.
    """
    with sandbox() as (repo, _):
        where = paths.review_dir("origin/main...main", repo)
        if where.exists():
            raise Failed(f"review_dir created {where} without create=True")
        eq(
            paths.review_dir("origin/main...main", repo, create=True).is_dir(),
            True,
            "create=True should make it",
        )


@case
def paths_review_dir_separates_ranges():
    """Two ranges of one repo are two reviews. Sharing a folder made each server report
    the other's build as stale and each Rebuild overwrite the other page."""
    with sandbox() as (repo, _):
        a = paths.review_dir("origin/main...main", repo)
        b = paths.review_dir("e8e4bb6..main", repo)
        if a == b:
            raise Failed(f"two ranges share one folder: {a}")


@case
def paths_review_dir_keeps_the_branch_end():
    """The name is trimmed from the front, because a range ends at the branch and that is
    the half a human reading `ls` needs."""
    with sandbox() as (repo, _):
        rng = "0123456789abcdef0123456789abcdef01234567..ci/check-unsafe-migrations"
        name = paths.review_dir(rng, repo).name
        if "ci-check-unsafe-migrations" not in name:
            raise Failed(f"the branch end was trimmed away: {name!r}")


@case
def paths_logs_live_in_the_review():
    """All four logs belong to the review, not to the checkout. Shared logs leaked one
    branch's questions onto another branch's page."""
    with sandbox() as (repo, _):
        where = paths.review_dir("origin/main...main", repo)
        logs = paths.logs("origin/main...main", repo)
        eq(sorted(logs), ["answers", "messages", "questions", "resolved"], "the four logs")
        for name, path in logs.items():
            eq(path.parent, where, f"{name} should sit in the review folder")


# ----------------------------------------------------------------------- fold_fixups


@case
def fold_fixups_folds_onto_its_target():
    """A fixup moves inside the commit it amends, so the rail stays as long as the change
    rather than as long as the review."""
    kept = build_data.fold_fixups(
        [
            commit("aaaaaaa", "Add the login form"),
            commit("bbbbbbb", "fixup! Add the login form"),
            commit("ccccccc", "Something else"),
        ]
    )
    eq([c["short"] for c in kept], ["aaaaaaa", "ccccccc"], "the rail after folding")
    eq([f["short"] for f in kept[0]["followups"]], ["bbbbbbb"], "what folded into commit 1")


@case
def fold_fixups_unwraps_stacked_prefixes():
    """`git commit --fixup` onto a fixup stacks them: fixup! fixup! <subject>."""
    kept = build_data.fold_fixups(
        [
            commit("aaaaaaa", "Add the login form"),
            commit("bbbbbbb", "fixup! fixup! Add the login form"),
        ]
    )
    eq(len(kept), 1, "a stacked fixup should still fold")
    eq([f["short"] for f in kept[0]["followups"]], ["bbbbbbb"], "the folded fixup")


@case
def fold_fixups_keeps_an_orphan():
    """A fixup whose target is outside the range has nothing to attach to."""
    kept = build_data.fold_fixups([commit("bbbbbbb", "fixup! Something older")])
    eq([c["short"] for c in kept], ["bbbbbbb"], "an orphan fixup stays a commit of its own")


@case
def fold_fixups_does_not_fold_forwards():
    """A target that comes later is not the commit this fixup amends."""
    kept = build_data.fold_fixups(
        [
            commit("bbbbbbb", "fixup! Add the login form"),
            commit("aaaaaaa", "Add the login form"),
        ]
    )
    eq(len(kept), 2, "a fixup before its target stays separate")


# --------------------------------------------------------------------- mark_survival


@case
def mark_survival_skims_a_commit_with_nothing_left():
    """A commit every later commit rewrote is work that no longer exists. Reading the rail
    in order means reading it, so it is marked."""
    commits = [commit("aaaaaaa", "Add the login form", additions=40)]
    build_data.mark_survival(commits, {})
    eq(commits[0]["read"], "skim", "a commit with no surviving line")
    eq(bool(commits[0]["readWhy"]), True, "skim has to say why")
    eq(commits[0]["autoSkim"], True, "the rail should not print the counts as well")


@case
def mark_survival_never_overrules_a_narrative():
    """This fills a gap. A mark a person wrote stays the mark they wrote."""
    commits = [commit("aaaaaaa", "Add the login form", additions=40)]
    commits[0]["read"] = "care"
    commits[0]["readWhy"] = "changes who can bypass the check"
    build_data.mark_survival(commits, {})
    eq(commits[0]["read"], "care", "a narrative mark")
    eq(commits[0].get("autoSkim"), None, "and no auto flag over it")


@case
def mark_survival_counts_the_followups_too():
    """A commit and its fixups are one entry on the rail, so they are counted together."""
    target = commit("aaaaaaa", "Add the login form", additions=40)
    target["followups"] = [commit("bbbbbbb", "fixup! Add the login form", additions=10)]
    build_data.mark_survival([target], {"b" * 56: 10})
    eq(target["added"], 50, "added, including the fixup")
    eq(target["alive"], 10, "alive, including the fixup")
    eq(target.get("read"), "", "something survives, so no skim")


@case
def mark_survival_leaves_a_pure_deletion_alone():
    """A commit that only removes lines added none, so there is nothing to have survived.
    Marking it skim would say its work is gone when its work is the deletion."""
    commits = [commit("aaaaaaa", "Drop the old helper", additions=0)]
    build_data.mark_survival(commits, {})
    eq(commits[0].get("read"), "", "a pure deletion is not skimmed")


@case
def mark_survival_survives_blame_counting_more_than_was_added():
    """Blame runs with -M, so a block a later commit copied inside a file is credited to
    the commit that wrote it. A commit can be blamed for more lines than it added."""
    commits = [commit("aaaaaaa", "Add the tests", additions=271)]
    build_data.mark_survival(commits, {"a" * 56: 379})
    eq(commits[0]["alive"], 379, "alive may exceed added")
    eq(commits[0].get("read"), "", "and that is not a reason to mark anything")


# ---------------------------------------------------------------- read marks, limits


def read_marks(per_commit, commit_count):
    problems, warnings = [], []
    build_data.validate_read_marks(per_commit, commit_count, problems, warnings)
    return problems, warnings


@case
def read_marks_cap_care_at_five():
    """A share of the branch was the only rule and it does not hold at the top: a third of
    forty is thirteen, and nobody keeps thirteen in mind."""
    for count, allowed in ((3, 1), (9, 3), (15, 5), (23, 5), (40, 5)):
        ok = {f"{i:07x}": {"read": "care", "readWhy": "why"} for i in range(allowed)}
        _, warnings = read_marks(ok, count)
        eq(warnings, [], f"{allowed} care marks on {count} commits")
        over = {f"{i:07x}": {"read": "care", "readWhy": "why"} for i in range(allowed + 1)}
        _, warnings = read_marks(over, count)
        eq(len(warnings), 1, f"{allowed + 1} care marks on {count} commits should warn")


@case
def read_marks_cap_is_a_warning_not_a_refusal():
    """It is a judgement about emphasis, not a malformed file, so every narrative written
    before the cap still builds."""
    over = {f"{i:07x}": {"read": "care", "readWhy": "why"} for i in range(9)}
    problems, warnings = read_marks(over, 23)
    eq(problems, [], "too many care marks must not refuse the build")
    eq(len(warnings), 1, "but it should say so")


@case
def read_marks_allow_only_one_start():
    """A branch has one place to begin."""
    two = {"aaaaaaa": {"read": "start"}, "bbbbbbb": {"read": "start"}}
    problems, _ = read_marks(two, 10)
    eq(len(problems), 1, "two start marks")


@case
def read_marks_require_a_reason_to_skim():
    """Skip this is the only mark that costs the reader something if it is wrong, so it
    carries its own evidence."""
    problems, _ = read_marks({"aaaaaaa": {"read": "skim"}}, 10)
    eq(len(problems), 1, "skim without a readWhy")
    problems, _ = read_marks({"aaaaaaa": {"read": "skim", "readWhy": "generated"}}, 10)
    eq(problems, [], "skim with one")


@case
def read_marks_bound_the_reason():
    """readWhy has one line in the rail. Reaching the limit means cut."""
    long = {"aaaaaaa": {"read": "care", "readWhy": "x" * (build_data.READ_WHY_MAX + 1)}}
    problems, _ = read_marks(long, 10)
    eq(len(problems), 1, "a readWhy over the limit")


@case
def read_marks_warn_about_a_reason_nothing_draws():
    """A readWhy with no read is not drawn anywhere, and silently dropping it is how a
    sentence someone wrote disappears."""
    _, warnings = read_marks({"aaaaaaa": {"readWhy": "orphaned"}}, 10)
    eq(len(warnings), 1, "a readWhy with no read")


@case
def read_marks_reject_an_unknown_mark():
    problems, _ = read_marks({"aaaaaaa": {"read": "important"}}, 10)
    eq(len(problems), 1, "a mark outside the three")


# ------------------------------------------------------------------- reading order


@case
def file_tier_puts_tests_last():
    """The code, then what documents it, then what tests it. A test read before its
    subject is a list of assertions about nothing."""
    eq(build_data.file_tier("api/urls.py"), 0, "code")
    eq(build_data.file_tier("README.md"), 1, "documentation")
    eq(build_data.file_tier("api/tests/test_urls.py"), 2, "a test")
    eq(build_data.file_tier("conftest.py"), 2, "conftest")
    eq(build_data.file_tier("api/urls_test.py"), 2, "the other naming convention")


@case
def test_stem_names_its_subject():
    eq(build_data.test_stem("common/tests/test_admin_mfa.py"), "admin_mfa", "test_ prefix")
    eq(build_data.test_stem("common/admin_mfa_test.py"), "admin_mfa", "_test suffix")


@case
def to_runs_joins_neighbours():
    """Line numbers are read and drawn as runs."""
    eq(build_data.to_runs([3, 1, 2, 7, 8, 20]), [[1, 3], [7, 8], [20, 20]], "three runs")
    eq(build_data.to_runs([]), [], "nothing")


# ------------------------------------------------------------------ narrative keys


@case
def matches_commit_takes_any_unambiguous_prefix():
    full, short = "10c7342051cb884ec3974974406082afb13c9a7b", "10c7342"
    for key in (full, short, "10c73420", "10c"):
        eq(build_data.matches_commit(key, full, short), True, f"key {key!r}")
    eq(build_data.matches_commit("deadbee", full, short), False, "an unrelated key")


@case
def mark_number_reads_both_forms():
    """Marks are written as strings in every narrative so far, and the page prints them
    straight into a chip, so both forms have to read as the same number."""
    eq(build_data.mark_number("3"), 3, "a string")
    eq(build_data.mark_number(3), 3, "an int")
    eq(build_data.mark_number(" 12 "), 12, "with spaces")
    for bad in ("two", "", None, True, 1.5):
        eq(build_data.mark_number(bad), None, f"{bad!r} names no position")


@case
def is_placeholder_only_matches_an_untouched_scaffold():
    eq(build_data.is_placeholder({"where": "", "what": "", "marks": []}), True, "untouched")
    eq(
        build_data.is_placeholder({"where": "CI", "what": "", "marks": []}),
        False,
        "half filled",
    )


# ------------------------------------------------------------------- reading a patch
#
# parse_patch decides what the reviewer sees and which line a thread is anchored to, so a
# row it drops is a line nobody reviews and a number it skips is a question filed against
# the wrong line.


def patch_for(repo, run, before, after, path="m.sql"):
    """The real diff git produces for one edit, which is what parse_patch has to read."""
    (repo / path).write_text(before)
    run("add", "-A")
    run("commit", "-qm", "before")
    (repo / path).write_text(after)
    run("add", "-A")
    run("commit", "-qm", "after")
    return run("diff", "HEAD~1", "HEAD").stdout


@case
def parse_patch_keeps_a_deleted_line_that_looks_like_a_header():
    """A deleted line whose content starts with "-- " reaches git's output as "--- ...",
    which is also how git introduces the old side of a file. Skipping it as a header drops
    a real deletion: SQL and Lua comments, YAML front matter, an email signature."""
    with sandbox() as (repo, run):
        patch = patch_for(
            repo,
            run,
            "-- add the index\nCREATE INDEX a;\nCREATE INDEX b;\n",
            "CREATE INDEX b;\n",
        )
        rows = build_data.parse_patch(patch)[0]["rows"]
        deleted = [r["text"] for r in rows if r["t"] == "del"]
        eq(deleted, ["-- add the index", "CREATE INDEX a;"], "the deleted lines")


@case
def parse_patch_keeps_old_line_numbers_straight():
    """Dropping a row without counting it shifts every old-side number after it, so a
    thread anchored below that point records a line the reviewer never clicked."""
    with sandbox() as (repo, run):
        patch = patch_for(
            repo,
            run,
            "-- add the index\nCREATE INDEX a;\nCREATE INDEX b;\nCREATE INDEX c;\n",
            "CREATE INDEX b;\nCREATE INDEX c;\n",
        )
        rows = build_data.parse_patch(patch)[0]["rows"]
        numbered = [(r["t"], r.get("o"), r["text"]) for r in rows if r["t"] != "hunk"]
        eq(
            numbered,
            [
                ("del", 1, "-- add the index"),
                ("del", 2, "CREATE INDEX a;"),
                ("ctx", 3, "CREATE INDEX b;"),
                ("ctx", 4, "CREATE INDEX c;"),
            ],
            "every row with its real old-side line number",
        )


@case
def parse_patch_ignores_a_mode_change():
    """A chmod has no hunk, and its "old mode"/"new mode" lines are not content. They were
    falling through to the context branch, which rendered them as two rows of diff with
    their first character eaten."""
    with sandbox() as (repo, run):
        (repo / "keep.txt").write_text("one\n")
        run("add", "-A")
        run("commit", "-qm", "add")
        run("update-index", "--chmod=+x", "keep.txt")
        run("commit", "-qm", "chmod")
        rows = build_data.parse_patch(run("diff", "HEAD~1", "HEAD").stdout)[0]["rows"]
        eq(rows, [], "a mode change has nothing to show")


@case
def parse_patch_does_not_let_one_file_bleed_into_the_next():
    """Named for what it actually holds down. It was written for a counter reset that
    turned out to be dead code, and it caught the in_hunk reset instead: without that,
    the second file's own headers are read as its content and it starts at line 0."""
    with sandbox() as (repo, run):
        (repo / "one.txt").write_text("a\nb\nc\n")
        (repo / "two.txt").write_text("x\ny\nz\n")
        run("add", "-A")
        run("commit", "-qm", "two files")
        (repo / "one.txt").write_text("a\nB\nc\n")
        (repo / "two.txt").write_text("x\nY\nz\n")
        run("add", "-A")
        run("commit", "-qm", "edit both")
        files = build_data.parse_patch(run("diff", "HEAD~1", "HEAD").stdout)
        eq(len(files), 2, "two files in the patch")
        for entry in files:
            first = [r for r in entry["rows"] if r["t"] != "hunk"][0]
            eq(first.get("o"), 1, f"{entry['path']} starts at old line 1")


@case
def parse_patch_keeps_an_added_line_that_looks_like_a_header():
    """The mirror of the deleted case: content beginning "++ " reaches git as "+++ ",
    which is how git introduces the new side. Markdown showing a diff, or C++ where a
    line starts with ++."""
    with sandbox() as (repo, run):
        patch = patch_for(
            repo, run, "one\ntwo\n", "++ plus comment\none\ntwo\n", path="notes.md"
        )
        rows = build_data.parse_patch(patch)[0]["rows"]
        added = [(r.get("n"), r["text"]) for r in rows if r["t"] == "add"]
        eq(added, [(1, "++ plus comment")], "the added line, with its new-side number")


@case
def parse_patch_reads_a_path_git_had_to_quote():
    """git quotes a path with non-ASCII in it unless told otherwise, and the quoted form
    never matched, so the file vanished from the review and its header lines were parsed
    as content rows belonging to whichever file came before it."""
    with sandbox() as (repo, run):
        (repo / "aaa.txt").write_text("one\ntwo\n")
        (repo / "café.txt").write_text("x\n")
        run("add", "-A")
        run("commit", "-qm", "base")
        (repo / "aaa.txt").write_text("one\ntwo\nthree\n")
        (repo / "café.txt").write_text("y\n")
        run("add", "-A")
        run("commit", "-qm", "edit")
        files = build_data.parse_patch(build_data.git(repo, "diff", "HEAD~1", "HEAD"))
        eq(sorted(f["path"] for f in files), ["aaa.txt", "café.txt"], "both files")
        first = [f for f in files if f["path"] == "aaa.txt"][0]
        eq(
            [r["text"] for r in first["rows"] if r["t"] != "hunk"],
            ["one", "two", "three"],
            "and nothing from the next file leaked into this one",
        )


@case
def parse_patch_marks_a_file_added_or_deleted():
    """status drives the badge and the collapse rule, and the refactor moved the block
    that sets it without anything watching."""
    with sandbox() as (repo, run):
        (repo / "gone.txt").write_text("bye\n")
        run("add", "-A")
        run("commit", "-qm", "base")
        (repo / "gone.txt").unlink()
        (repo / "fresh.txt").write_text("hello\n")
        run("add", "-A")
        run("commit", "-qm", "edit")
        got = {
            f["path"]: f["status"]
            for f in build_data.parse_patch(build_data.git(repo, "diff", "HEAD~1", "HEAD"))
        }
        eq(got, {"fresh.txt": "added", "gone.txt": "deleted"}, "the statuses")


# -------------------------------------------------- what a stage accounts for in the diff
#
# A stage is a step in a journey through the branch as it stands, so it lists a file when
# it accounts for something in the final diff: lines that survive to the tip, or a file the
# branch removes. Membership taken from history instead says a stage touched a file at some
# point, which is the commits tab's question asked in the wrong tab.


def staged(repo, run, stages, commits):
    """Build a range whose narrative marks `commits` to `stages`, and report what each
    stage ends up listing."""
    narrative = repo / "n.json"
    narrative.write_text(
        json.dumps(
            {
                "stages": [
                    {"where": where, "what": "what it does", "marks": marks}
                    for where, marks in zip(stages, commits)
                ]
            }
        )
    )
    data = build(repo, "origin/main..HEAD", narrative=narrative)
    final = data["final"] or {"order": [], "files": []}
    return {
        where: sorted(f["path"] for f in final["files"] if where in (f.get("stages") or []))
        for where in final["order"]
    }, data


@case
def a_stage_does_not_list_a_file_it_wrote_nothing_surviving_in():
    """The first stage edits a file, the second rewrites every line of that edit. History
    says both touched it; the branch only shows the second."""
    with sandbox() as (repo, run):
        (repo / "a.py").write_text("one\ntwo\n")
        run("add", "-A")
        run("commit", "-qm", "base")
        run("update-ref", "refs/remotes/origin/main", "HEAD")
        (repo / "a.py").write_text("one\nfirst pass\n")
        run("add", "-A")
        run("commit", "-qm", "First pass")
        (repo / "a.py").write_text("one\nsecond pass\n")
        run("add", "-A")
        run("commit", "-qm", "Second pass")
        listed, data = staged(repo, run, ["first", "second"], [["1"], ["2"]])
        eq(listed.get("second"), ["a.py"], "what the surviving stage lists")
        # Membership read off the file, so the check holds whether or not the stage that
        # wrote nothing surviving is still drawn.
        stages_of = {f["path"]: f["stages"] for f in data["final"]["files"]}
        eq(stages_of["a.py"], ["second"], "the stages a.py belongs to")


@case
def a_stage_that_only_deletes_a_file_still_lists_it():
    """Nothing it wrote survives, because the file does not. The removal is in the final
    diff, so the stage accounts for it and is part of the journey."""
    with sandbox() as (repo, run):
        (repo / "keep.py").write_text("one\n")
        (repo / "legacy.py").write_text("legacy\n")
        run("add", "-A")
        run("commit", "-qm", "base")
        run("update-ref", "refs/remotes/origin/main", "HEAD")
        (repo / "keep.py").write_text("one\ntwo\n")
        run("add", "-A")
        run("commit", "-qm", "The new path")
        run("rm", "-q", "legacy.py")
        run("commit", "-qm", "Drop the legacy module")
        listed, _ = staged(repo, run, ["new", "legacy"], [["1"], ["2"]])
        eq(listed.get("legacy"), ["legacy.py"], "a stage whose work is a deletion")
        eq(listed.get("new"), ["keep.py"], "and the one that added")


@case
def a_stage_accounting_for_nothing_is_not_drawn():
    """It is not a step in a journey through the branch as it stands, and drawing it in the
    strip says the work passes through somewhere it does not."""
    with sandbox() as (repo, run):
        (repo / "a.py").write_text("one\ntwo\n")
        run("add", "-A")
        run("commit", "-qm", "base")
        run("update-ref", "refs/remotes/origin/main", "HEAD")
        (repo / "a.py").write_text("one\nfirst pass\n")
        run("add", "-A")
        run("commit", "-qm", "First pass")
        (repo / "a.py").write_text("one\nsecond pass\n")
        run("add", "-A")
        run("commit", "-qm", "Second pass")
        _, data = staged(repo, run, ["first", "second"], [["1"], ["2"]])
        eq([s["where"] for s in data["stages"]], ["second"], "the strip")
        eq(data["final"]["order"], ["second"], "and the rail")


@case
def dropping_a_stage_says_which_one_and_why():
    """Someone wrote it. It goes because the branch no longer passes through it, and that
    is worth being told rather than noticing."""
    with sandbox() as (repo, run):
        (repo / "a.py").write_text("one\ntwo\n")
        run("add", "-A")
        run("commit", "-qm", "base")
        run("update-ref", "refs/remotes/origin/main", "HEAD")
        (repo / "a.py").write_text("one\nfirst pass\n")
        run("add", "-A")
        run("commit", "-qm", "First pass")
        (repo / "a.py").write_text("one\nsecond pass\n")
        run("add", "-A")
        run("commit", "-qm", "Second pass")
        narrative = repo / "n.json"
        narrative.write_text(
            json.dumps(
                {
                    "stages": [
                        {"where": "first", "what": "overwritten", "marks": ["1"]},
                        {"where": "second", "what": "survives", "marks": ["2"]},
                    ]
                }
            )
        )
        said = build_stderr(repo, "origin/main..HEAD", narrative).strip()
        eq(
            said,
            "narrative: stage 'first' is not drawn: nothing it did is in the branch as it "
            "stands, so commit(s) 1 belong to no stage",
            "what the build said",
        )


@case
def a_stage_keeps_a_file_a_later_commit_renamed():
    """Blame follows a rename; a commit's own diff does not. So the stage that wrote the
    lines names the old path and the final diff names the new one, and asking history
    which stages reach a file loses the stage whose work is sitting in it."""
    with sandbox() as (repo, run):
        (repo / "mod.py").write_text("base\n")
        run("add", "-A")
        run("commit", "-qm", "base")
        run("update-ref", "refs/remotes/origin/main", "HEAD")
        (repo / "mod.py").write_text("base\none\ntwo\nthree\n")
        run("add", "-A")
        run("commit", "-qm", "The work")
        run("mv", "mod.py", "pkg_mod.py")
        run("commit", "-qm", "Rename it")
        listed, data = staged(repo, run, ["the work"], [["1"]])
        eq(listed.get("the work"), ["mod.py", "pkg_mod.py"], "the files the stage lists")
        renamed = next(f for f in data["final"]["files"] if f["path"] == "pkg_mod.py")
        eq(renamed["lines"], {"the work": 3}, "its lines under the new path")


@case
def a_stage_whose_only_file_was_renamed_is_still_drawn():
    """The single-stage form of the same thing, where losing it empties the strip."""
    with sandbox() as (repo, run):
        (repo / "mod.py").write_text("base\n")
        run("add", "-A")
        run("commit", "-qm", "base")
        run("update-ref", "refs/remotes/origin/main", "HEAD")
        (repo / "mod.py").write_text("base\none\ntwo\nthree\n")
        run("add", "-A")
        run("commit", "-qm", "The work")
        run("mv", "mod.py", "pkg_mod.py")
        run("commit", "-qm", "Rename it")
        _, data = staged(repo, run, ["the work"], [["1"]])
        eq([s["where"] for s in data["stages"]], ["the work"], "the strip")
        eq(data["final"]["spent"], [], "nothing should have been called spent")


@case
def a_stage_whose_addition_was_deleted_does_not_keep_the_file():
    """Every surviving line predates the branch, so blame weighs nothing and the fallback
    decides. A stage that only added to the file, and whose addition is gone, accounts for
    nothing in it; the one that did the removing accounts for the removal."""
    with sandbox() as (repo, run):
        (repo / "a.py").write_text("older one\nolder two\n")
        run("add", "-A")
        run("commit", "-qm", "base")
        run("update-ref", "refs/remotes/origin/main", "HEAD")
        (repo / "a.py").write_text("older one\nolder two\nadded by A\n")
        run("add", "-A")
        run("commit", "-qm", "A adds a line")
        (repo / "a.py").write_text("older one\n")
        run("add", "-A")
        run("commit", "-qm", "B removes both")
        listed, data = staged(repo, run, ["A", "B"], [["1"], ["2"]])
        eq(listed.get("B"), ["a.py"], "the stage that did the removing")
        eq("A" in listed, False, f"the stage whose line went ({listed})")


@case
def a_stage_that_only_deletes_still_wins_the_fallback():
    """The same path, guarding the case it exists for: nothing to weigh, and the stage
    that removed the file keeps it."""
    with sandbox() as (repo, run):
        (repo / "legacy.py").write_text("old\n")
        run("add", "-A")
        run("commit", "-qm", "base")
        run("update-ref", "refs/remotes/origin/main", "HEAD")
        (repo / "keep.py").write_text("new\n")
        run("add", "-A")
        run("commit", "-qm", "A adds")
        run("rm", "-q", "legacy.py")
        run("commit", "-qm", "B removes")
        listed, _ = staged(repo, run, ["A", "B"], [["1"], ["2"]])
        eq(listed.get("B"), ["legacy.py"], "the removing stage keeps the file")
