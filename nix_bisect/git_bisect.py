"""Utilities for git-bisect.

Importing this file sets up an except-hook as a side-effect that will
cause any uncaught exception to exit with an exit code that aborts the
bisection process. This is usually preferable to indicating a failure
for the current commit, which should be done explicitly.
"""

import sys
import inspect

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


_quit_hooks = []


def register_quit_hook(hook):
    _quit_hooks.append(hook)


def _call_quit_hooks(result, reason):
    for hook in _quit_hooks:
        # make it possible for the lazy to pass lambdas without arguments
        args = len(inspect.signature(hook).parameters.keys())
        if args == 0:
            hook()
        elif args == 1:
            hook(result)
        else:
            hook(result, reason)


def abort(reason=None):
    """Exit with an exit code that aborts a bisect run."""
    _call_quit_hooks("abort", reason)
    sys.exit(128)


def quit_good(reason=None):
    """Exit with an exit code that indicates success."""
    _call_quit_hooks("good", reason)
    print(f"{_ANSI_GREEN}bisect: good{_ANSI_RESET}")
    sys.exit(0)


def quit_bad(reason=None):
    """Exit with an exit code that indicates failure."""
    _call_quit_hooks("bad", reason)
    print(f"{_ANSI_RED}bisect: bad{_ANSI_RESET}")
    sys.exit(1)


def quit_skip(reason=None):
    """Exit with an exit code that causes the commit to be skipped."""
    _call_quit_hooks("skip", reason)
    print(f"{_ANSI_BLUE}bisect: skip{_ANSI_RESET}")
    sys.exit(125)
