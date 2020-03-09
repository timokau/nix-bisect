"""Bisect a whole nixos + home-manager system"""

import tempfile
import stat
import time

from subprocess import Popen, PIPE
from multiprocessing import Process
from pathlib import Path

from nix_bisect import nix, test_util, git_bisect


def _main():
    process = Popen("bash", stdin=PIPE, stdout=PIPE, encoding="UTF-8")

    # Hack to "instantiate" the home-manager system configuration.
    with tempfile.TemporaryDirectory() as tmpdirname:
        # Monkey-patch "nix-build" by creating a mock nix-build script in a
        # temporary directory and then prepending that directory to PATH.
        # The goal here is to just print the instantiation result but not
        # actually do the building.
        nix_build_path = Path(tmpdirname).joinpath("nix-build")
        with open(nix_build_path, "w+") as nix_build_mock:
            nix_build_mock.write(
                """
                #!/usr/bin/env bash
                PATH="$old_PATH" nix-instantiate "$@"
            """
            )
        nix_build_path.chmod(nix_build_path.stat().st_mode | stat.S_IEXEC)
        (stdout, _stderr) = process.communicate(
            input=f"""
            export old_PATH="$PATH"
            export PATH="{tmpdirname}:$PATH"
            echo $PWD >&2
            home-manager -I nixpkgs=. build
        """
        )
    process.wait()

    home = stdout.strip()
    print(f"Home: {home}")
    # This is what nixos-rebuild instantiates internally
    nixos = nix.instantiate("system", nix_file="./nixos")
    print(f"Nixos: {nixos}")

    # Build the nixos and home-manager configurations at the same time for
    # optimal parallelization.
    build_target = [home, nixos]
    if len(nix.build_dry(build_target)[0]) > 500:
        print("Too many rebuilds, skipping")
        git_bisect.quit_skip()

    # Skip on system build failure.
    try:
        _build_result = nix.build(build_target)
    except nix.BuildFailure:
        print("System failed to build")
        git_bisect.quit_skip()

    # Switch to the previously built system.
    if test_util.exit_code("home-manager -I nixpkgs=. switch") != 0:
        git_bisect.quit_skip()
    if test_util.exit_code("sudo nixos-rebuild switch") != 0:
        git_bisect.quit_skip()

    # Test kitty
    if test_util.exit_code(f"kitty echo Hello World") != 0:
        print("Kitty failed to launch")
        git_bisect.quit_bad()
    else:
        git_bisect.quit_good()


class Sudoloop:
    """Keeps the sudo password cached"""

    def __init__(self, initialize=True):
        self.initialize = initialize

        def sudoloop():
            while True:
                # Extend sudo cache by 5 minutes but do not re-query the user
                # if the password is not already cached.
                test_util.exit_code("sudo -S --validate </dev/null 2>/dev/null")
                time.sleep(4 * 60)

        self.loop_process = Process(target=sudoloop)

    def __enter__(self):
        if self.initialize:
            # First initialize the cache in a blocking manner.
            test_util.exit_code("sudo --validate")
        self.loop_process.start()

    def __exit__(self, _type, _value, _traceback):
        self.loop_process.terminate()
        self.loop_process.join()


if __name__ == "__main__":
    with Sudoloop():
        _main()
