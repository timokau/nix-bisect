"""Bisect runner with that little extra"""

import sys
import argparse
from nix_bisect import bisect_runner, git


def _main():
    parser = argparse.ArgumentParser(description="git-bisect with extra features")

    subparsers = parser.add_subparsers(
        title="subcommands", description="valid subcommands", help="additional help"
    )

    good_parser = subparsers.add_parser("good")
    good_parser.add_argument(
        "rev",
        type=str,
        default="HEAD",
        help="Revision that will be marked as good",
        nargs="?",
    )

    def _handle_good(args):
        print("Good")
        bisect_runner.bisect_good(args.rev)
        git.checkout(bisect_runner.BisectRunner().get_next())

    good_parser.set_defaults(func=_handle_good)

    bad_parser = subparsers.add_parser("bad")
    bad_parser.add_argument(
        "rev",
        type=str,
        default="HEAD",
        help="Revision that will be marked as bad",
        nargs="?",
    )

    def _handle_bad(args):
        bisect_runner.bisect_bad(args.rev)
        git.checkout(bisect_runner.BisectRunner().get_next())

    bad_parser.set_defaults(func=_handle_bad)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_usage()
        return 128
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
