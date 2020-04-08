"""High-Level interface for determining facts about a derivation as efficiently
as possible."""

from pathlib import Path
import time

from nix_bisect import nix, gcroot


class Derivation:
    """A nix derivation and common operations on it, optimized for bisect"""

    def __init__(self, drv, nix_options=(), max_rebuilds=None, rebuild_blacklist=()):
        """Create a new derivation.

        The derivation's methods will throw TooManyBuildsException when the
        rebuild limit is exceeded.
        """
        self.drv = drv
        self.nix_options = nix_options
        self.max_rebuilds = max_rebuilds if max_rebuilds is not None else float("inf")
        self.rebuild_blacklist = rebuild_blacklist
        self._gcroot_name = f"nix-bisect-{Path(drv).name}-{round(time.time() * 1000.0)}"
        gcroot.create_tmp_gcroot(self._gcroot_name, drv)

    def __del__(self):
        gcroot.delete_tmp_gcroot(self._gcroot_name)

    def immediate_dependencies(self):
        """Returns the derivation's immediate dependencies."""
        return nix.references([self.drv])

    def can_build_deps(self):
        """Determines if the derivation's dependencies build would succeed.

        This may or may not actually build or fetch the dependencies. If
        possible, cached information is used.
        """
        return nix.build_would_succeed(
            self.immediate_dependencies(),
            nix_options=self.nix_options,
            max_rebuilds=self.max_rebuilds - 1,
            rebuild_blacklist=self.rebuild_blacklist,
        )

    def sample_dependency_failure(self):
        """Returns one dependency failure if it exists.

        This is a cheap-operation of can_build_deps has already been executed.
        In contrast, determining all failing dependencies might be much more
        expensive as it requires running `nix-build --keep-going`.
        """
        # This will use cached failures.
        try:
            nix.build(self.immediate_dependencies(), nix_options=self.nix_options)
        except nix.BuildFailure as bf:
            return bf.drvs_failed[0]
        return None

    def can_build(self):
        """Determines if the derivation's build would succeed.

        This may or may not actually build or fetch the derivation. If
        possible, cached information is used.
        """
        return nix.build_would_succeed(
            [self.drv],
            nix_options=self.nix_options,
            max_rebuilds=self.max_rebuilds,
            rebuild_blacklist=self.rebuild_blacklist,
        )

    def log_contains(self, line):
        """Determines if the derivation's build log contains a line.

        This may or may not actually build or fetch the derivation. If
        possible, cached information is used.
        """
        return nix.log_contains(self.drv, line) == "yes"
