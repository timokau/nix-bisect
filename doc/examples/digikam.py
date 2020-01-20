"""Bisect a digikam segmentation fault.

This script was used to bisect a runtime segfault in the digikam
package. It is mostly used to find a valid commit and launch digikam,
the actual testing is then performed manually.
"""

from nix_bisect import nix, test_util, git_bisect


def _main():
    # The digikam attribute changed its name at some point.
    try:
        digikam = nix.instantiate("digikam")
    except nix.InstantiationFailure:
        # If this fails to evaluate too, the bisection will abort
        # because of the uncaught exception.
        digikam = nix.instantiate("kde4.digikam")

    # If a log is present for digikam but the package itself is neither
    # in the store nor substitutable, we assume a build failure. This is
    # not 100% accurate, but the best we can do.
    if nix.log(digikam) is not None and len(nix.build_dry([digikam])[0]) > 0:
        print("Cached failure")
        git_bisect.quit_skip()

    # Skip on dependency failure. This is mostly done to showcase the
    # feature, in this case we don't need to differentiate between
    # dependencies and the package itself.
    try:
        nix.build(nix.dependencies([digikam]))
    except nix.BuildFailure:
        print("Dependencies failed to build")
        git_bisect.quit_skip()

    # Skip on build failure.
    try:
        build_result = nix.build([digikam])
    except nix.BuildFailure:
        print("Digikam failed to build")
        git_bisect.quit_skip()

    # Sanity check the package.
    if test_util.exit_code(f"{build_result[0]}/bin/digikam -v") != 0:
        print("Digikam failed to launch")
        git_bisect.quit_skip()

    # Give digikam a clean slate to work with.
    test_util.shell(
        b"""
        echo "cleaning up"
        rm -f ~/Pictures/*.db
        rm -f ~/.config/digikamrc
        rm -rf ~/.local/share/digikam
        rm -rf ~/.cache/digikam
    """
    )

    # Now it's time for manual testing.
    test_util.exit_code(f"{build_result[0]}/bin/digikam")
    test_util.query_user()


if __name__ == "__main__":
    _main()
