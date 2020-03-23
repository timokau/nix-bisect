"""Simple command line interface for common use cases"""

import argparse
from pathlib import Path
from nix_bisect import nix, git, git_bisect, bisect_runner


def _perform_bisect(attrname, nix_file, to_pick, max_rebuilds, failure_line):
    for rev in to_pick:
        git.try_cherry_pick_all(rev)

    drv = nix.instantiate(attrname, nix_file)
    print(f"Instantiated {drv}.")

    num_rebuilds = len(nix.build_dry([drv])[0])
    if num_rebuilds == 0:
        return "good"

    if max_rebuilds is not None:
        if num_rebuilds > max_rebuilds:
            print(
                f"Need to rebuild {num_rebuilds} derivations, which exceeds the maximum."
            )
            return "skip rebuild_count"

    try:
        nix.build(nix.dependencies([drv]))
    except nix.BuildFailure as failure:
        failed_drvs = failure.drvs_failed
        print(f"Dependencies {failed_drvs} failed to build.")
        failed_name = Path(list(failed_drvs)[0]).name
        skip_id = "-".join(failed_name.split("-")[1:])
        return f"skip {skip_id}"

    if failure_line is not None:
        result = nix.log_contains(drv, failure_line)
        if result == "yes":
            print("Failure line detected.")
            return "bad"
        elif result == "no_success":
            print("Build success.")
            return "good"
        elif result == "no_fail":
            print("Failure without failure line.")
            return "skip unknown_build_failure"
        else:
            raise Exception()
    else:
        if nix.build_would_succeed([drv]):
            print("Build success.")
            return "good"
        else:
            print("Build failure.")
            return "bad"


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
