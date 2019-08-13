"""Utilities for git-bisect.

Importing this file sets up an except-hook as a side-effect that will
cause any uncaught exception to exit with an exit code that aborts the
bisection process. This is usually preferable to indicating a failure
for the current commit, which should be done explicitly.
"""

import sys

# colors for printing
_ANSI_BLUE = "\033[94m"
_ANSI_GREEN = "\033[92m"
_ANSI_RED = "\033[91m"
_ANSI_RESET = "\033[0m"
_ANSI_BOLD = "\033[1m"

# make sure uncaught exceptions abort the bisect instead of failing it
def _set_excepthook():
    def _handle_uncaught_exception(exctype, value, trace):
        old_hook(exctype, value, trace)
        abort()

    sys.excepthook, old_hook = _handle_uncaught_exception, sys.excepthook


_set_excepthook()



def abort():
    """Exit with an exit code that aborts a bisect run."""
    sys.exit(128)


def quit_good():
    """Exit with an exit code that indicates success."""
    print(f"{_ANSI_GREEN}bisect: good{_ANSI_RESET}")
    sys.exit(0)


def quit_bad():
    """Exit with an exit code that indicates failure."""
    print(f"{_ANSI_RED}bisect: bad{_ANSI_RESET}")
    sys.exit(1)


def quit_skip():
    """Exit with an exit code that causes the commit to be skipped."""
    print(f"{_ANSI_BLUE}bisect: skip{_ANSI_RESET}")
    sys.exit(125)
