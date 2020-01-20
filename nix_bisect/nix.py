"""Wrapper for nix functionality"""

from subprocess import run, PIPE


def log(drv):
    """Returns the build log of a store path."""
    result = run(
        ["nix", "log", "-f.", drv], stdout=PIPE, stderr=PIPE, encoding="utf-8"
    )
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


def build(drvs):
    """Builds `drvs`, returning a list of store paths"""
    if len(drvs) == 0:
        # nothing to do
        return ""

    build_process = run(["nix", "build", "--no-link"] + drvs)
    if build_process.returncode != 0:
        raise BuildFailure()

    location_process = run(
        ["nix-store", "--realize"] + drvs,
        stdout=PIPE,
        stderr=PIPE,
        encoding="utf-8",
    )
    location_process.check_returncode()
    storepaths = location_process.stdout.split("\n")
    return storepaths
