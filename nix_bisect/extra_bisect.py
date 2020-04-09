"""Bisect runner with that little extra"""

import sys
import argparse
import subprocess
import shlex
from nix_bisect import bisect_runner, git, git_bisect


def _setup_start_parser(parser):
    parser.add_argument("bad", nargs="?")
    parser.add_argument("good", nargs="*", default=[])

    def _handle_start(args):
        try:
            extra_args = [args.bad] if args.bad is not None else []
            extra_args.extend(args.good)
            subprocess.check_call(["git", "bisect", "start"] + extra_args)
        except subprocess.CalledProcessError:
            # `git bisect start` already prints the appropriate error message
            return 1
        return 0

    parser.set_defaults(func=_handle_start)


def _setup_good_parser(parser):
    parser.add_argument(
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
        return 0

    parser.set_defaults(func=_handle_good)


def _setup_bad_parser(parser):
    parser.add_argument(
        "rev",
        type=str,
        default="HEAD",
        help="Revision that will be marked as bad",
        nargs="?",
    )

    def _handle_bad(args):
        bisect_runner.bisect_bad(args.rev)
        git.checkout(bisect_runner.BisectRunner().get_next())
        return 0

    parser.set_defaults(func=_handle_bad)


def _setup_skip_parser(parser):
    parser.add_argument(
        "rev",
        type=str,
        default="HEAD",
        help="Revision that will be marked as belonging to the skip range",
        nargs="?",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="default",
        help="Name of the skip range, purely for display",
    )

    def _handle_skip(args):
        bisect_runner.bisect_skip(args.rev)
        git.checkout(bisect_runner.BisectRunner().get_next())
        return 0

    parser.set_defaults(func=_handle_skip)


def _setup_skip_range_parser(parser):
    parser.add_argument(
        "rev",
        type=str,
        default="HEAD",
        help="Revision that will be marked as belonging to the skip range",
        nargs="?",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="default",
        help="Name of the skip range, purely for display",
    )

    def _handle_skip_range(args):
        patchset = bisect_runner.read_patchset()
        bisect_runner.named_skip(args.name, patchset, args.rev)
        git.checkout(bisect_runner.BisectRunner().get_next())
        return 0

    parser.set_defaults(func=_handle_skip_range)


def _setup_env_parser(parser):
    parser.add_argument(
        "cmd", type=str, help="Command to run", default="bash", nargs="?",
    )
    parser.add_argument(
        "args", type=str, nargs=argparse.REMAINDER,
    )

    def _handle_env(args):
        patchset = bisect_runner.read_patchset()
        arg_list = bisect_runner.bisect_env_args(patchset)
        arg_list.append(args.cmd)
        arg_list.extend(args.args)
        return subprocess.call(["bisect-env"] + arg_list)

    parser.set_defaults(func=_handle_env)


def _setup_run_parser(parser):
    parser.add_argument(
        "cmd", type=str, help="Command that controls the bisect",
    )
    parser.add_argument(
        "args", type=str, nargs=argparse.REMAINDER,
    )

    def _handle_run(args):
        runner = bisect_runner.BisectRunner()
        while True:
            subprocess_args = ["bisect-env"]
            subprocess_args.extend(
                bisect_runner.bisect_env_args(bisect_runner.read_patchset())
            )
            subprocess_args.append(args.cmd)
            subprocess_args.extend(args.args)

            quoted_cmd = " ".join([shlex.quote(arg) for arg in subprocess_args])
            bisect_runner.bisect_append_log(f"# $ {quoted_cmd}")
            print(f"$ {quoted_cmd}")

            return_code = subprocess.call(subprocess_args)
            if return_code == 0:
                git_bisect.print_good()
                bisect_runner.bisect_good("HEAD")
            elif return_code == 125:
                git_bisect.print_skip()
                bisect_runner.bisect_skip("HEAD")
            elif return_code == 129:
                git_bisect.print_skip_range()
                patchset = bisect_runner.read_patchset()
                bisect_runner.named_skip("runner-skip", patchset, "HEAD")
            elif 1 <= return_code <= 127:
                git_bisect.print_bad()
                bisect_runner.bisect_bad("HEAD")
            else:
                break
            next_commit = runner.get_next()
            if next_commit is None:
                break
            git.checkout(next_commit)
        return 0

    parser.set_defaults(func=_handle_run)


def _main():
    parser = argparse.ArgumentParser(description="git-bisect with extra features")

    subparsers = parser.add_subparsers(
        title="subcommands", description="valid subcommands", help="additional help"
    )

    _setup_good_parser(subparsers.add_parser("good"))
    _setup_bad_parser(subparsers.add_parser("bad"))
    _setup_skip_parser(subparsers.add_parser("skip"))
    _setup_skip_range_parser(subparsers.add_parser("skip-range"))
    _setup_env_parser(subparsers.add_parser("env"))
    _setup_run_parser(subparsers.add_parser("run"))
    _setup_start_parser(subparsers.add_parser("start"))

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_usage()
        return 128
    return args.func(args)


if __name__ == "__main__":
    sys.exit(_main())
