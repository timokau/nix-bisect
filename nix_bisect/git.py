"""Utilities for interacting with git."""

from subprocess import run, PIPE
from math import log, floor, ceil


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
