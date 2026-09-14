# Operational traps

Each of these cost real time when this tool was built.

## Killing the server

`pkill -f "http.server 8777"` matches **your own shell's command line**, so it kills the
shell running it. The same is true of any `pgrep -f` check. Find the process by what it is
rather than by a pattern:

```bash
REPO=$(git rev-parse --show-toplevel)
for pid in $(ps -eo pid= -o args= | awk '/[s]erver\.py/ {print $1}'); do
  [ "$(readlink /proc/$pid/cwd)" = "$REPO" ] && kill "$pid"
done
```

Two details that look like nits and are not. `review.py` execs the server by absolute
path, so its `args` read `python3 /long/path/tool/server.py` — a pattern like
`python3 server.py` matches nothing and you conclude it stopped. And it inherits the
**repo** as its cwd, not the state directory, so that is what identifies which review a
process belongs to. The bracketed `[s]` keeps the pattern from matching the `awk` that
carries it.

Get either wrong and the search comes back empty while the server is still holding the
port. The next start quietly picks a different one, and the reviewer opens a page nobody
is listening to.

## Bound every request

A `curl` with no `--max-time` inside a compound command can hang the whole command until
the tool timeout, and buffered stdout from earlier in that command is then lost, so the
failure looks like it happened somewhere it did not.

## The watcher is session-scoped

`Monitor` lives as long as the Claude Code session. The page keeps serving and keeps
appending questions to `questions.jsonl` after the session ends, but nothing wakes you.

Two things make that survivable, and both have to keep working:

`watch.py` replays on startup. It emits every unresolved thread whose last turn is not
Claude's, prefixed `BACKLOG`, so questions asked while nothing was attached arrive when a
session re-arms the watcher. It used to seek to the end of both logs, which silently
dropped them.

`watch.py` writes `watcher.alive` every second, and `/thread` reports it as `watcher`.
The page shows the pulsing "waiting for an answer" only when that is fresh; otherwise it
says no session is attached. Judge the heartbeat by mtime, not existence: `kill -9` leaves
the file behind.

## The store is keyed by repo, so a thread says which branch it came from

Every review of a checkout appends to the same four logs, because `state_dir()` keys on
the repo path. Without something on the row saying where it came from, a thread from an
earlier review of another branch is indistinguishable from one whose commit was rebased
away from this one, and both land in the orphan section.

`/ask` stamps `branch` from git at the moment the question is asked, not from the range
the server started with, because the branch changes under a running server. The page then
splits orphans in two: rebased away from this review, and a collapsed group from other
reviews. The status line counts only this review, or it reports questions asked on another
branch as questions asked here.

Two places have to agree on what "no branch" means. A detached HEAD gives `HEAD` from
`rev-parse --abbrev-ref`, and both `server.py` and `build_data.py` turn that into `""`. If
one of them kept the literal string, the page would compare `HEAD` against real branch
names and file every orphan under another review.

Renaming a branch strands its threads under the old name. There is no fix for that in this
design, and `review.py archive` is the way out.

## One repo can hold two reviews, and they must not share a file

The state directory is keyed by repo, so reviewing two branches of one checkout puts both
in it. Anything named for the directory rather than the range is then shared by two
reviews that disagree.

It happened twice. A single `index.html` meant each server reported the other's build as
stale, and clicking Rebuild overwrote the other page, so two open tabs took turns
demanding a rebuild. A single `narrative.json` put one review's title and stage strip on
the other's page, which built cleanly and read as though it were right.

The page and the narrative are both named from a hash of the range now, and the server
resolves `/` to its own range's page rather than to whatever was written last. Anything
else added beside them needs the same treatment.

## The server's root is the review, not the store

`SimpleHTTPRequestHandler` serves whatever directory it is given. Rooted at the store, a
GET of `/questions.jsonl` returned every question ever asked in that checkout, from every
branch, over the port. It is rooted at the review's own directory now, which holds the
page and its narrative and nothing else.

Anything added beside the page is served. Anything added beside the threads is not.

## Theme colors come from tokens, never from a `[data-theme]` guard

`:root:not([data-theme="light"]) .btn { color: var(--ground) }` looks like a dark-mode
rule but matches the default un-stamped state too, so it applies in light mode, and its
specificity beats a plain `.btn.ghost`. That shipped white text on a white button. Define
a token in all three theme blocks and let components read it.

## `os.execv` discards buffered stdout

`review.py` prints the URL and then replaces itself with the server. Without an explicit
`sys.stdout.flush()` the URL is lost and the log looks empty.

## Rebuilding does not orphan threads, rebasing does

Threads anchor on `(commit, file, side, line)`. A rebuild from the same commits reattaches
everything. A rebase or amend changes hashes and line numbers, and those threads move to
the orphan section with their original anchor and code snippet preserved.

## Never check a port by connecting to it

`connect_ex` to a closed loopback port hangs on WSL2 rather than returning
`ECONNREFUSED` — the SYN is dropped, so nothing ever comes back. An unbounded check
therefore blocks forever on the first free candidate, which is usually the port you
wanted, and `review.py serve` never reaches the line that prints the URL. Ask by binding
instead: it answers immediately and needs no network round trip.

Give the check the same `SO_REUSEADDR` the server sets. Without it the check is stricter
than the server it is checking for: a port just vacated sits in `TIME_WAIT`, a plain bind
refuses it, and the port walks up by one on every restart.
