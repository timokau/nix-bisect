"""Run a command in a temporary environment"""

import sys
import argparse
import subprocess
from nix_bisect import git_bisect, git


class EnvSetupFailedException(Exception):
    """Raised when a mandatory action could not be completed"""


def run_with_env(function, env_setup):
    """Run a function in a certain environment"""

    def pick(rev):
        success = git.try_cherry_pick_all(rev)
        if not success:
            raise EnvSetupFailedException("Cherry-pick failed")

    action_to_function = {
        "try_pick": git.try_cherry_pick_all,
        "pick": pick,
    }

    with git.git_checkpoint():
        for (action, rev) in env_setup:
            action_to_function[action](rev)

        return function()


def _main():
    # Ordered list of actions to apply
    class _AppendShared(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            if not "setup_actions" in namespace:
                setattr(namespace, "setup_actions", [])
            previous = namespace.setup_actions
            previous.append((self.dest, values))
            setattr(namespace, "setup_actions", previous)

    parser = argparse.ArgumentParser(
        description="Run a program with a certain environment"
    )
    parser.add_argument(
        "cmd", type=str, help="Command to run",
    )
    parser.add_argument(
        "args", type=str, nargs=argparse.REMAINDER,
    )
    parser.add_argument(
        "--try-pick",
        action=_AppendShared,
        default=[],
        help="Cherry pick a commit before building (only if it applies without issues).",
    )
    parser.add_argument(
        "--pick",
        action=_AppendShared,
        default=[],
        help="Cherry pick a commit before building, abort on failure.",
    )

    try:
        args = parser.parse_args()
    except SystemExit:
        git_bisect.abort()

    setup_actions = args.setup_actions if hasattr(args, "setup_actions") else []

    def cmd():
        return subprocess.call([args.cmd] + args.args)

    try:
        return run_with_env(cmd, setup_actions)
    except EnvSetupFailedException:
        print("Environment setup failed.")
        return 125


if __name__ == "__main__":
    sys.exit(_main())
