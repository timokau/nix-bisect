"""Wrapper for nix functionality"""

from subprocess import run, PIPE, Popen
from pathlib import Path
import json
import re
import sys

from appdirs import AppDirs

# Parse the error output of `nix build`
_CANNOT_BUILD_PAT = re.compile(r"^cannot build derivation '([^']+)': (.+)")
_BUILD_FAILED_PAT = re.compile(r"^error: build of '([^']+)' failed$")
_BUILDER_FAILED_PAT = re.compile(
    r"builder for '([^']+)' failed with exit code (\d+);.*"
)


def log(drv):
    """Returns the build log of a store path."""
    result = run(["nix", "log", "-f.", drv], stdout=PIPE, stderr=PIPE, encoding="utf-8")
    if result.returncode != 0:
        return None
    return result.stdout


def build_dry(drvs):
    """Returns a list of drvs to be built and fetched in order to
    realize `drvs`"""
    result = run(
        ["nix-store", "--realize", "--dry-run"] + drvs,
        stdout=PIPE,
        stderr=PIPE,
        encoding="utf-8",
    )
    result.check_returncode()
    lines = result.stderr.splitlines()
    to_fetch = []
    to_build = []
    for line in lines:
        line = line.strip()
        if "these paths will be fetched" in line:
            cur = to_fetch
        elif "these derivations will be built" in line:
            cur = to_build
        elif line.startswith("/nix/store"):
            cur += [line]
        elif line != "":
            raise RuntimeError("dry-run parsing failed")

    return (to_build, to_fetch)


class InstantiationFailure(Exception):
    """Failure during instantiation."""


def instantiate(attrname, nix_file="./.", expression=True, system=None):
    """Instantiate an attribute.

    Parameters
    ----------

    attrname: string,
        Attribute or expression to instantiate.

    expression: bool
        If `True`, arbitrary nix expressions can be evaluated. This
        allows for overrides. The nix_file (or the current working
        directory by default) will be in scope by default. I.e. the
        expression will be implicitly prefixed by

        with (import nix_file {});

    nix_file: string,
        Nix file to instantiate an attribute from.
    """
    if system is not None:
        sys_arg = ["--option", "system", system]
    else:
        sys_arg = []

    if expression:
        if nix_file is not None:
            arg = f"with (import {nix_file} {{}}); {attrname}"
        else:
            arg = attrname
        command = ["nix-instantiate", "-E", arg] + sys_arg
    else:
        command = ["nix-instantiate", nix_file, "-A", arg] + sys_arg
    result = run(command, stdout=PIPE, stderr=PIPE, encoding="utf-8",)

    if result.returncode == 0:
        return result.stdout.strip()

    raise InstantiationFailure(result.stderr)


def dependencies(drvs):
    """Returns all dependencies of `drvs` that aren't already in the
    store."""
    (to_build, to_fetch) = build_dry(drvs)
    to_realize = to_build + to_fetch
    for drv in drvs:
        try:
            to_realize.remove(drv)
        except ValueError:
            # drv already in store
            pass
    return to_realize


class BuildFailure(Exception):
    """A failure during build."""

    def __init__(self, drvs_failed):
        super(BuildFailure).__init__()
        self.drvs_failed = drvs_failed


def _build_uncached(drvs):
    if len(drvs) == 0:
        # nothing to do
        return ""

    build_process = Popen(["nix", "build", "--no-link"] + drvs, stderr=PIPE, text=True)

    drvs_failed = set()
    for line in iter(build_process.stderr.readline, ""):
        # Can't wait for https://www.python.org/dev/peps/pep-0572/
        match = _CANNOT_BUILD_PAT.match(line)
        if match is not None:
            drv = match.group(1)
            _reason = match.group(2)
            drvs_failed.add(drv)
        match = _BUILD_FAILED_PAT.match(line)
        if match is not None:
            drv = match.group(1)
            drvs_failed.add(drv)
        match = _BUILDER_FAILED_PAT.match(line)
        if match is not None:
            drv = match.group(1)
            _exit_code = match.group(2)
            drvs_failed.add(drv)

        sys.stdout.write(line)

    if len(drvs_failed) > 0:
        raise BuildFailure(drvs_failed)

    location_process = run(
        ["nix-store", "--realize"] + drvs, stdout=PIPE, stderr=PIPE, encoding="utf-8",
    )
    location_process.check_returncode()
    storepaths = location_process.stdout.split("\n")
    return storepaths


def build(drvs, use_cache=True, write_cache=True):
    """Builds `drvs`, returning a list of store paths"""
    cache_dir = Path(AppDirs("nix-bisect").user_cache_dir)
    try:
        cache_dir.mkdir(parents=True)
    except FileExistsError:
        pass

    cache_file = cache_dir.joinpath("build-results.json")
    if (use_cache or write_cache) and cache_file.exists():
        with open(cache_file, "r") as cf:
            result_cache = json.loads(cf.read())
    else:
        result_cache = dict()

    if use_cache:
        for drv in drvs:
            # innocent till proven guilty
            if not result_cache.get(drv, True):
                print(f"Cached failure of {drv}.")
                raise BuildFailure([drv])

    try:
        return _build_uncached(drvs)
    except BuildFailure as bf:
        if write_cache:
            for drv in bf.drvs_failed:
                # Could save more details here in the future if needed.
                result_cache[drv] = False
            with open(cache_file, "w") as cf:
                # Write human-readable json for easy hacking.
                cf.write(json.dumps(result_cache, indent=4))
        raise bf
