"""Simple command line interface for common use cases"""

import argparse
from nix_bisect import nix, git, git_bisect, bisect_runner, exceptions
from nix_bisect.derivation import Derivation


def _perform_bisect(attrname, nix_file, to_pick, max_rebuilds, failure_line):
    for rev in to_pick:
        git.try_cherry_pick_all(rev)

    drv = nix.instantiate(attrname, nix_file)
    print(f"Instantiated {drv}.")

    try:
        drv = Derivation(drv, max_rebuilds=max_rebuilds)

        if not drv.can_build_deps():
            failed = drv.sample_dependency_failure()
            print(f"Dependency {failed} failed to build.")
            return f"skip dependency_failure"

        if drv.can_build():
            return "good"
        else:
            if failure_line is None or drv.log_contains(failure_line):
                return "bad"
            else:
                return "skip unknown_build_failure"
    except exceptions.ResourceConstraintException:
        return "skip resource_constraint"


def _main():
    parser = argparse.ArgumentParser(
        description="Build a package with nix, suitable for git-bisect."
    )
    parser.add_argument(
        "attrname", type=str, help="Name of the attr to build",
    )
    parser.add_argument(
        "--try-cherry-pick",
        action="append",
        default=[],
        help="Cherry pick a commit before building (only if it applies without issues).",
    )
    parser.add_argument(
        "--nix-file",
        "-f",
        help="Nix file that contains the attribute",
        type=str,
        default=".",
    )
    parser.add_argument(
        "--max-rebuilds",
        type=int,
        help="Skip when a certain rebuild count is exceeded.",
        default=None,
    )
    parser.add_argument(
        "--failure-line",
        help="Whether to try to detect cached failures with a failure line.",
        default=None,
    )
    parser.add_argument(
        "--bisect-runner",
        action="store_true",
        help="Use the custom bisect runner with autofix functionality.",
        default=False,
    )

    try:
        args = parser.parse_args()
    except SystemExit:
        git_bisect.abort()

    def bisect_fun():
        with git.git_checkpoint():
            result = _perform_bisect(
                args.attrname,
                args.nix_file,
                args.try_cherry_pick,
                args.max_rebuilds,
                args.failure_line,
            )
        return result

    if not args.bisect_runner:
        result = bisect_fun()
        if result == "good":
            git_bisect.quit_good()
        elif result == "bad":
            git_bisect.quit_bad()
        elif result.startswith("skip"):
            git_bisect.quit_skip()
        else:
            raise Exception("Unknown bisection result")
    else:
        bisect_runner.BisectRunner().run(bisect_fun)


if __name__ == "__main__":
    _main()
