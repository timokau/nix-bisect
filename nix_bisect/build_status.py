"""Determine the status of a nix build as lazily as possible in a
bisect-friendly format"""

import sys
import argparse
from pathlib import Path

from nix_bisect import nix, exceptions, git_bisect
from nix_bisect.derivation import Derivation


def drvish_to_drv(drvish, nix_file, nix_options, nix_argstr):
    """No-op on drv files, otherwise evaluate in the context of nix_file"""
    path = Path(drvish)
    if path.exists() and path.name.endswith(".drv"):
        return str(path)
    else:
        return nix.instantiate(
            drvish, nix_file, nix_options=nix_options, nix_argstr=nix_argstr
        )


def build_status(
    drvish,
    nix_file,
    nix_options,
    nix_argstr,
    failure_line=None,
    max_rebuilds=None,
    rebuild_blacklist=(),
):
    """Determine the status of `drvish` and return the result as indicated"""
    try:
        drv = drvish_to_drv(
            drvish, nix_file, nix_options=nix_options, nix_argstr=nix_argstr
        )
    except nix.InstantiationFailure:
        return "instantiation_failure"
    print(f"Querying status of {drv!r}.")

    try:
        drv = Derivation(
            drv,
            nix_options=nix_options,
            max_rebuilds=max_rebuilds,
            rebuild_blacklist=rebuild_blacklist,
        )

        if not drv.can_build_deps():
            failed = drv.sample_dependency_failure()
            print(f"Dependency {failed} failed to build.")
            return f"dependency_failure"

        if drv.can_build():
            return "success"
        else:
            if failure_line is None or drv.log_contains(failure_line):
                return "failure"
            else:
                return "failure_without_line"
    except exceptions.ResourceConstraintException as e:
        print(e)
        return "resource_limit"


class _ActionChoices(list):
    def __init__(self):
        self.named_choices = ["good", "bad", "skip", "skip-range"]
        # Add a dummy choice that will only show up in --help but will not
        # actually be accepted.
        choice_list = self.named_choices + ["<int>"]
        super().__init__(choice_list)

    # An extension of list that just pretends every integer is a member. Used
    # to accept arbitrary return codes as choices (in addition to named
    # actions).
    def __contains__(self, other):
        if self.named_choices.__contains__(other):
            return True
        try:
            _retcode = int(other)
            return True
        except ValueError:
            return False


def _main():
    def to_exit_code(action):
        try:
            return int(action)
        except ValueError:
            return {"good": 0, "bad": 1, "skip": 125, "skip-range": 129, "abort": 128,}[
                action
            ]

    action_choices = _ActionChoices()

    parser = argparse.ArgumentParser(
        description="Build a package with nix, suitable for git-bisect."
    )
    parser.add_argument(
        "drvish",
        type=str,
        help="Derivation or an attribute/expression that can be resolved to a derivation in the context of the nix file",
    )
    parser.add_argument(
        "--file",
        "-f",
        help="Nix file that contains the attribute",
        type=str,
        default=".",
    )
    parser.add_argument(
        "--option",
        nargs=2,
        metavar=("name", "value"),
        action="append",
        default=[],
        help="Set the Nix configuration option `name` to `value`.",
    )
    parser.add_argument(
        "--argstr",
        nargs=2,
        metavar=("name", "value"),
        action="append",
        default=[],
        help="Passed on to `nix instantiate`",
    )
    parser.add_argument(
        "--max-rebuilds", type=int, help="Number of builds to allow.", default=None,
    )
    parser.add_argument(
        "--failure-line",
        help="Line required in the build logs to count as a failure.",
        default=None,
    )
    parser.add_argument(
        "--on-success",
        default="good",
        choices=action_choices,
        help="Bisect action if the expression can be successfully built",
    )
    parser.add_argument(
        "--on-failure",
        default="bad",
        choices=action_choices,
        help="Bisect action if the expression can be successfully built",
    )
    parser.add_argument(
        "--on-dependency-failure",
        default="skip-range",
        choices=action_choices,
        help="Bisect action if the expression can be successfully built",
    )
    parser.add_argument(
        "--on-failure-without-line",
        default="skip-range",
        choices=action_choices,
        help="Bisect action if the expression can be successfully built",
    )
    parser.add_argument(
        "--on-instantiation-failure",
        default="skip-range",
        choices=action_choices,
        help="Bisect action if the expression cannot be instantiated",
    )
    parser.add_argument(
        "--on-resource-limit",
        default="skip",
        choices=action_choices,
        help="Bisect action if a resource limit like rebuild count is exceeded",
    )
    parser.add_argument(
        "--rebuild-blacklist",
        action="append",
        help="If any derivation matching this regex needs to be rebuilt, the build is skipped",
    )

    try:
        args = parser.parse_args()
    except SystemExit:
        git_bisect.abort()

    status = build_status(
        args.drvish,
        args.file,
        nix_options=args.option,
        nix_argstr=args.argstr,
        failure_line=args.failure_line,
        max_rebuilds=args.max_rebuilds,
        rebuild_blacklist=args.rebuild_blacklist
        if args.rebuild_blacklist is not None
        else (),
    )
    action_on_status = {
        "success": args.on_success,
        "failure": args.on_failure,
        "dependency_failure": args.on_dependency_failure,
        "failure_without_line": args.on_failure_without_line,
        "instantiation_failure": args.on_instantiation_failure,
        "resource_limit": args.on_resource_limit,
    }
    print(f"Build status: {status}")
    sys.exit(to_exit_code(action_on_status[status]))


if __name__ == "__main__":
    sys.exit(_main())
