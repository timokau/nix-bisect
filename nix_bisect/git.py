"""Utilities for interacting with git."""

from subprocess import run, PIPE
from math import log, floor, ceil
import signal


def cur_commit():
    """Returns the rev of the current HEAD."""
    result = run(
        ["git", "rev-parse", "HEAD"], stdout=PIPE, stderr=PIPE, encoding="utf-8",
    )
    result.check_returncode()
    return result.stdout.strip()


def commits_in_range(rev1, rev2):
    """Returns all commits withing a range"""
    result = run(
        ["git", "log", "--pretty=format:%H", f"{rev1}..{rev2}"],
        stdout=PIPE,
        stderr=PIPE,
        encoding="utf-8",
    )
    return result.stdout.splitlines()


def bisect_revisions():
    """Returns the amount of still possible first-bad commits.
    
    This is an approximation."""
    result = run(
        ["git", "bisect", "visualize", "--oneline"],
        stdout=PIPE,
        stderr=PIPE,
        encoding="utf-8",
    )
    result.check_returncode()
    lines = result.stdout.splitlines()
    interesting = [line for line in lines if "refs/bisect/skip" not in line]
    # the earliest known bad commit will be included in the bisect view
    return len(interesting) - 1


def bisect_steps_remaining():
    """Estimate of remaining steps, including the current one.

    This is an approximation."""
    # https://github.com/git/git/blob/566a1439f6f56c2171b8853ddbca0ad3f5098770/bisect.c#L1043
    return floor(log(bisect_revisions(), 2))


def bisect_status():
    """Reproduce the status line git-bisect prints after each step."""
    return "Bisecting: {} revisions left to test after this (roughly {} steps).".format(
        ceil((bisect_revisions() - 1) / 2), bisect_steps_remaining() - 1,
    )


class assure_nothing_unstaged:
    """Context that temporarily commits staged changes."""

    def __enter__(self):
        self.head_before = cur_commit()
        add(".")
        commit(f"TMP clean slate")
        return None

    def __exit__(self, type, value, traceback):
        s = signal.signal(signal.SIGINT, signal.SIG_IGN)
        reset(self.head_before)
        signal.signal(signal.SIGINT, s)


class git_checkpoint:
    """Context that remembers the repository's state

    The repositories state (including uncommited changes) is saved when the
    context is entered and restored when it is left.
    """

    def __enter__(self):
        self.head_before = cur_commit()

        # Create a commit that reflects the current state of the repo.
        add(".")
        commit(f"TMP clean slate")
        self.checkpint_rev = cur_commit()

        # Return to the original commit (soft reset).
        reset(self.head_before)
        return None

    def __exit__(self, type, value, traceback):
        # Don't exit in the middle of cleanup, can happen if someone is
        # impatient and hits ctrl-c multiple times.
        s = signal.signal(signal.SIGINT, signal.SIG_IGN)
        reset(self.checkpint_rev, extra_flags=["--hard"])
        clean(extra_flags=["-f"])
        reset(self.head_before)
        signal.signal(signal.SIGINT, s)


def try_cherry_pick_all(rev):
    """Tries to cherry pick all parents of a (merge) commit."""
    num_par = len(parents(rev))
    for i in range(1, num_par + 1):
        try_cherry_pick(rev, mainline=i)


def try_cherry_pick(rev, mainline=1):
    rev_name = rev + ("" if mainline == 1 else f"(mainline {mainline})")
    with assure_nothing_unstaged():
        result = run(
            ["git", "cherry-pick", "--mainline", str(mainline), "-n", rev],
            stdout=PIPE,
            stderr=PIPE,
            encoding="utf-8",
        )

        if result.returncode != 0:
            print(f"Cherry-pick of {rev_name} failed")
            print(result.stderr.splitlines()[0][len("error: ") - 1 :])
            reset("HEAD", extra_flags=["--hard"])
            return False

        print(f"Cherry-pick of {rev_name} succeeded")
        return True


def try_revert(rev):
    with assure_nothing_unstaged():
        result = run(
            ["git", "revert", "-n", rev], stdout=PIPE, stderr=PIPE, encoding="utf-8",
        )

        if result.returncode != 0:
            print("Revert failed")
            print(result.stderr.splitlines()[0][len("error: ") - 1 :])
            reset("HEAD", extra_flags=["--hard"])
            return False

        print("Revert succeeded")
        return True


def is_ancestor(rev, ancestor_from="HEAD"):
    result = run(
        ["git", "merge-base", "--is-ancestor", rev, ancestor_from],
        stdout=PIPE,
        stderr=PIPE,
        encoding="utf-8",
    )

    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    result.check_returncode()


def reset(rev, extra_flags=[]):
    result = run(
        ["git", "reset"] + extra_flags + [rev],
        stdout=PIPE,
        stderr=PIPE,
        encoding="utf-8",
    )
    result.check_returncode()


def clean(extra_flags=[]):
    result = run(
        ["git", "clean"] + extra_flags, stdout=PIPE, stderr=PIPE, encoding="utf-8",
    )
    result.check_returncode()


def add(path):
    result = run(["git", "add", path], stdout=PIPE, stderr=PIPE, encoding="utf-8",)
    result.check_returncode()


def commit(message):
    result = run(
        ["git", "commit", "--allow-empty", "-m", message],
        stdout=PIPE,
        stderr=PIPE,
        encoding="utf-8",
    )
    result.check_returncode()
