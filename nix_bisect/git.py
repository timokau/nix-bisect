"""Utilities for interacting with git."""

import subprocess
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


# FIXME create a worktree, periodically re-sync with original
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


def parents(rev):
    """Returns all parent revisions of a revision"""
    return (
        subprocess.check_output(["git", "rev-list", "-n", "1", "--parents", rev])
        .decode()
        .strip()
        .split(" ")[1:]
    )


def try_cherry_pick_all(rev):
    """Tries to cherry pick all parents of a (merge) commit."""
    num_par = len(parents(rev))
    any_success = False
    for i in range(1, num_par + 1):
        any_success = any_success or try_cherry_pick(rev, mainline=i)
    return any_success


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


def is_ancestor(ancestor, parent):
    """Returns `True` iff `ancestor` is an ancestor of `parent`."""
    try:
        subprocess.check_call(["git", "merge-base", "--is-ancestor", ancestor, parent],)
        return True
    except subprocess.CalledProcessError:
        return False


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


def checkout(commit):
    """Runs `git checkout`"""
    subprocess.check_call(["git", "checkout", commit])


def get_refs_with_prefix(prefix):
    """Returns a list of refs that start with a prefix.

    Internally calls `git for-each-ref`. The prefix has to be complete up to a
    `/`, i.e. `some/pre` will find `some/pre/asdf` but not some/prefix.
    """
    return (
        subprocess.check_output(["git", "for-each-ref", "--format=%(refname)", prefix],)
        .decode()
        .splitlines()
    )


def rev_list(include, exclude):
    """Find all revs that are reachable by `include` but not by `exclude`.

    Runs `git rev-list` internally.
    """
    args = include + ["--not"] + [exclude]
    return subprocess.check_output(["git", "rev-list"] + args).decode().splitlines()


def get_bisect_info(good_commits, bad_commit):
    """Returns a dict with info about the current bisect run.

    Internally runs `git rev-list --bisect-vars`. Information includes:

    - bisect_rev: midpoint revision
    - bisect_nr: expected number to be tested after bisect_rev
    - bisect_good: bisect_nr if good
    - bisect_bad: bisect_nr if bad
    - bisect_all: commits we are bisecting right now
    - biset_step: estimated steps after bisect_rev
    """
    args = [bad_commit] + [f"^{commit}" for commit in good_commits]
    lines = (
        subprocess.check_output(["git", "rev-list", "--bisect-vars"] + args)
        .decode()
        .splitlines()
    )
    key_values = [line.split("=") for line in lines]
    info = dict(key_values)
    # this is a quoted string; strip the quotes
    info["bisect_rev"] = info["bisect_rev"][1:-1]
    for key in ("bisect_nr", "bisect_good", "bisect_bad", "bisect_all", "bisect_steps"):
        info[key] = int(info[key])
    return info


def get_bisect_all(good_commits, bad_commit):
    """Returns a list with potential next commits, sorted by distance

    Internally runs `git rev-list --bisect-all`.
    """
    # Could also be combined with --bisect-vars, that may be more efficient.
    args = [bad_commit] + [f"^{commit}" for commit in good_commits]
    lines = (
        subprocess.check_output(["git", "rev-list", "--bisect-all"] + args)
        .decode()
        .splitlines()
    )
    # first is furthest away, last is equal to bad
    commits = [line.split(" ")[0] for line in lines]
    return commits


def rev_parse(commit_ish, short=False):
    """Parses a "commit_ish" to a unique full hash"""
    args = ["--short"] if short else []
    return (
        subprocess.check_output(["git", "rev-parse"] + args + [commit_ish])
        .decode()
        .strip()
    )


def update_ref(ref, value):
    """Updates or creates a reference."""
    subprocess.check_call(["git", "update-ref", ref, value])


def delete_ref(ref):
    """Deletes a reference."""
    subprocess.check_call(["git", "update-ref", "-d", ref])


def git_dir():
    """Returns the path to the .git directory (works with worktrees)"""
    return subprocess.check_output(["git", "rev-parse", "--git-dir"]).decode().strip()


def commit_msg(rev):
    """Returns the short commit message summary (the first line)"""
    return (
        subprocess.check_output(["git", "show", "--pretty=format:%s", "-s", rev])
        .decode()
        .strip()
    )


def rev_pretty(rev):
    """Pretty-print a revision for usage in logs."""
    return f"[{rev_parse(rev, short=True)}] {commit_msg(rev)}"
