"""Utilities for interacting with git."""

from subprocess import run, PIPE


def cur_commit():
    """Returns the rev of the current HEAD."""
    result = run(
        ["git", "rev-parse", "HEAD"],
        stdout=PIPE,
        stderr=PIPE,
        encoding="utf-8",
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
