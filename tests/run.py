#!/usr/bin/env python3
"""Run the tool's checks.

    python3 tests/run.py            # everything
    python3 tests/run.py paths      # only cases whose name contains "paths"

Exits non-zero when any case fails, printing what was expected and what came back. No
dependencies: the README promises the tool needs nothing outside the standard library,
and a suite that breaks that promise is a suite people skip.

Most of what is here is a bug that shipped. `tool/smoke.js` runs the built page's script
and catches a page that throws, which is a real class of failure and not this one: the
range the watcher resolved, the blame that met a PNG, and the name a squash handler used
after rewriting history were all outside any page.

Importing a case file is what registers its cases, so a new one goes in the list below.
"""

import pathlib
import sys

# Python validates a .pyc against the source's (mtime, size) in whole seconds. Reverting
# an edit that happens to be the same length, within the same second, leaves a cache that
# looks current and is not: a mutation test reported the tool still broken after the file
# had been put back. Nothing here is imported often enough for the cache to be worth that.
sys.dont_write_bytecode = True

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import harness  # noqa: E402
import units  # noqa: E402

# Importing a file is what registers its cases. Naming them here as well keeps the list
# in the docstring honest and stops a linter reading the import as dead.
CASE_FILES = [units]

if __name__ == "__main__":
    sys.exit(harness.run(sys.argv[1] if len(sys.argv) > 1 else ""))
