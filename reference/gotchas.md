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
