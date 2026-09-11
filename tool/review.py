#!/usr/bin/env python3
"""Build and serve the web review page for a git range.

    python3 review.py serve  [<range>] [--port N] [--narrative FILE]
    python3 review.py build  [<range>] [--narrative FILE]
    python3 review.py narrate [<range>] [--force]
    python3 review.py where

Range defaults to origin/main...HEAD. `serve` picks a free port when the one
asked for is taken, and prints the URL it settled on.
"""
import argparse
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import paths  # noqa: E402

# The artifact host supplies this skeleton when a page is published; served locally
# the tool supplies it, so one template covers both.
SKELETON = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 16 16%22%3E%3Ctext y=%2213%22 font-size=%2213%22%3E%F0%9F%94%8D%3C/text%3E%3C/svg%3E">
<style>
  :root { color-scheme: light dark; }
  body { margin: 0; }
  img { max-width: 100%; }
  [hidden] { display: none !important; }
</style>
"""


def build(rng, narrative):
    repo = paths.repo_root()
    state = paths.state_dir(repo)
    # A narrative written for this review lives beside its state, so it is picked up
    # on every rebuild without repeating the flag.
    if not narrative and (state / "narrative.json").exists():
        narrative = state / "narrative.json"
    command = [sys.executable, str(HERE / "build_data.py")]
    if narrative:
        command += ["--narrative", str(pathlib.Path(narrative).resolve())]
    # "--" so a range like --root..HEAD is not read as an option
    command += ["--", rng]
    data = subprocess.run(command, capture_output=True, text=True, cwd=repo)
    if data.returncode != 0:
        raise SystemExit(data.stderr.strip() or "build_data.py failed")
    # Warnings about the narrative are the only thing on stderr, and swallowing them on a
    # successful build would hide the very mistakes they exist to report.
    if data.stderr.strip():
        print(data.stderr.strip(), file=sys.stderr)
    payload = data.stdout.strip()

    template = (HERE / "review.tpl.html").read_text()
    if template.count("/*__DATA__*/") != 1:
        raise SystemExit("template placeholder missing")
    # Any "<" inside the JSON would let a diff of an HTML file close the inline
    # script tag. In JSON, "<" only ever appears inside a string, where \u003c is
    # the same character, so escaping every one is safe and keeps the data intact.
    payload = payload.replace("<", "\\u003c")

    page = template.replace("/*__DATA__*/", payload)
    split = page.index('<div class="shell">')
    out = SKELETON + page[:split] + "</head>\n<body>\n" + page[split:] + "\n</body>\n</html>\n"
    target = state / "index.html"
    target.write_text(out)
    print(f"built {target} ({len(out):,} bytes)")
    smoke(target)
    return target


def smoke(page):
    """Run the page's script against a minimal DOM, when node is available.

    A page whose script throws renders a masthead and nothing else, which looks like
    a data problem rather than a code one. Better to refuse to serve it.
    """
    if not shutil.which("node"):
        print("node not found, skipping the smoke check")
        return
    result = subprocess.run(
        ["node", str(HERE / "smoke.js"), str(page)], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "the page script failed its smoke check")
    print(result.stdout.strip())


def narrate(rng, force):
    """Write a narrative scaffold for this range, for a reader to fill in.

    The structure is the part a script can get right: which commits exist, what they are
    called, how long the rail is, what the keys are named. The judgement is the part it
    cannot — which stages a change really moves through, and why a commit is there — so
    every one of those fields is left empty rather than guessed at. An empty field falls
    back to git, so a half-filled scaffold renders as the plain page rather than as blanks.
    """
    repo = paths.repo_root()
    target = paths.state_dir(repo) / "narrative.json"
    if target.exists() and not force:
        raise SystemExit(
            f"{target} already exists.\n"
            "Edit it, or pass --force to replace it with an empty scaffold.")

    data = subprocess.run([sys.executable, str(HERE / "build_data.py"), "--", rng],
                          capture_output=True, text=True, cwd=repo)
    if data.returncode != 0:
        raise SystemExit(data.stderr.strip() or "build_data.py failed")
    page = json.loads(data.stdout)
    commits = page["commits"]

    scaffold = {
        "title": "",
        "dek": "",
        "eyebrow": "",
        "figures": [],
        "stages": [],
        "notes": [],
        "commits": {
            commit["hash"][:9]: {
                # Not read by the build. Here so whoever fills this in can tell the
                # commits apart without keeping git log open beside it.
                "subject": commit["subject"],
                # "start" (one only), "care", or "skim" with a reason. Left empty means
                # the commit is read in its turn like any other.
                "read": "",
                "readWhy": "",
                "stage": "",
                "flow": "",
                "why": "",
                "points": [],
            }
            for commit in commits
        },
    }
    target.write_text(json.dumps(scaffold, indent=2, ensure_ascii=False) + "\n")
    print(f"scaffold written to {target}")
    print(f"{len(commits)} commit(s) on the rail, numbered 1 to {len(commits)} for stage marks.")
    print("Every key is optional. Anything left empty falls back to git, so fill in only")
    print("what you have actually worked out, then run `review.py build` to see it.")


def free_port(preferred):
    """The first port near `preferred` that nothing holds.

    Asked by binding: a connect probe waits for the other end to refuse, and a loopback
    stack that drops SYN to a closed port (WSL2 does) never sends that refusal, so the
    probe blocks forever and the server never starts.
    """
    for candidate in [preferred] + list(range(preferred + 1, preferred + 20)):
        with socket.socket() as probe:
            # The same option the server sets: a port just vacated sits in TIME_WAIT,
            # which refuses a plain bind but not the server's, so without this the port
            # drifts up by one on every restart.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", candidate))
            except OSError:
                continue  # someone is holding it
            return candidate
    raise SystemExit(f"no free port near {preferred}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["serve", "build", "narrate", "where"])
    parser.add_argument("range", nargs="?", default="origin/main...HEAD")
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--narrative", default=None)
    parser.add_argument("--force", action="store_true",
                        help="narrate: replace an existing narrative.json")
    args = parser.parse_args()

    if args.action == "where":
        print(paths.state_dir())
        return

    if args.action == "narrate":
        narrate(args.range, args.force)
        return

    build(args.range, args.narrative)
    if args.action == "build":
        return

    port = free_port(args.port)
    print(f"review page on http://localhost:{port}")
    # execv discards Python's buffered stdout, so the URL above has to be on its
    # way out before the process is replaced.
    sys.stdout.flush()
    os.environ["PORT"] = str(port)
    # The server reports whether these commits are still the ones in the repo.
    os.environ["REVIEW_RANGE"] = args.range
    os.execv(sys.executable, [sys.executable, str(HERE / "server.py")])


if __name__ == "__main__":
    main()
