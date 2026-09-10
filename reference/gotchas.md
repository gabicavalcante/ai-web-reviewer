# Operational traps

Each of these cost real time when this tool was built.

## Killing the server

`pkill -f "http.server 8777"` matches **your own shell's command line**, so it kills the
shell running it. The same is true of any `pgrep -f` check. Find the process by what it is
rather than by a pattern:

```bash
for pid in $(ps -eo pid= -o args= | awk '/python3 server\.py/ {print $1}'); do
  [ "$(readlink /proc/$pid/cwd)" = "$STATE_DIR" ] && kill "$pid"
done
```

The server runs as plain `python3 server.py` from the state directory, so grepping for the
directory in `args` finds nothing and you will wrongly conclude it stopped. The next start
then fails with `Address already in use`.

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
