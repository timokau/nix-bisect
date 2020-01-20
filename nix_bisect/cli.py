"""Simple command line interface for common use cases"""

import argparse
import signal
from subprocess import run, PIPE

from nix_bisect import nix, git, git_bisect


class assure_nothing_unstaged:
    """Context that temporarily commits staged changes."""

    def __enter__(self):
        self.head_before = git.cur_commit()
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
        self.head_before = git.cur_commit()

        # Create a commit that reflects the current state of the repo.
        add(".")
        commit(f"TMP clean slate")
        self.checkpint_rev = git.cur_commit()

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


def try_cherry_pick(rev):
    with assure_nothing_unstaged():
        result = run(
            ["git", "cherry-pick", "-n", rev],
            stdout=PIPE,
            stderr=PIPE,
            encoding="utf-8",
        )

        if result.returncode != 0:
            print("Cherry-pick failed")
            print(result.stderr.splitlines()[0][len("error: ") - 1 :])
            reset("HEAD", extra_flags=["--hard"])
            return False

        print("Cherry-pick succeeded")
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


def _perform_bisect(attrname, to_pick):
    def _quit(result, reason):
        print(f"Quit hook: {result} because of {reason}.")

    git_bisect.register_quit_hook(_quit)

    for rev in to_pick:
        try_cherry_pick(rev)

    drv = nix.instantiate(attrname)
    print(f"Instantiated {drv}.")

    try:
        nix.build(nix.dependencies([drv]))
    except nix.BuildFailure:
        print("Dependencies failed to build.")
        git_bisect.quit_skip()

    # If a log is present but the package itself is neither in the store nor
    # substitutable, we assume a build failure. This is not 100% accurate, but
    # the best we can do.
    if nix.log(drv) is not None and len(nix.build_dry([drv])[0]) > 0:
        print("Cached failure.")
        git_bisect.quit_bad()

    try:
        _build_result = nix.build([drv])
    except nix.BuildFailure:
        print(f"Failed to build {attrname}.")
        git_bisect.quit_bad()

    # Success if build succeeded.
    git_bisect.quit_good()


def _main():
    parser = argparse.ArgumentParser(
        description="Check the truth of statements against a corpus."
    )
    parser.add_argument(
        "attrname", type=str, help="Name of the attr to build",
    )
    parser.add_argument(
        "--try-cherry-pick", action="append", default=[],
    )

    try:
        args = parser.parse_args()
    except SystemExit:
        git_bisect.abort()

    with git_checkpoint():
        _perform_bisect(args.attrname, args.try_cherry_pick)


if __name__ == "__main__":
    _main()
