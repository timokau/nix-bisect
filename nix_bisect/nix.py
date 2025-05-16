"""Wrapper for nix functionality"""

from subprocess import run, PIPE
import subprocess
from pathlib import Path
from typing import Set

import struct
import signal
import fcntl
import termios
import json
import re
import sys

import pexpect

from appdirs import AppDirs

from nix_bisect import exceptions

# Parse the error output of `nix build`
_CANNOT_BUILD_PAT = re.compile(b"cannot build derivation '([^']+)': (.+)")
_BUILD_FAILED_PAT = re.compile(b"build of ('[^']+'(, '[^']+')*) failed")
_BUILDER_FAILED_PAT = re.compile(b"builder for '([^']+)' failed with exit code (\\d+);")
_BUILD_TIMEOUT_PAT = re.compile(b"building of '([^']+)' timed out after.*")


def _nix_options_to_flags(nix_options):
    option_args = []
    for (name, value) in nix_options:
        option_args.append("--option")
        option_args.append(name)
        option_args.append(value)
    return option_args


def log(drv):
    """Returns the build log of a store path."""
    if drv.endswith(".drv"):
        cmd = ("nix", "log", drv)
    else:
        cmd = ("nix", "log", "-f.", drv)
    result = run(cmd, stdout=PIPE, stderr=PIPE, encoding="utf-8")
    if result.returncode != 0:
        return None
    return result.stdout


def build_dry(drvs, nix_options=()):
    """Returns a list of drvs to be built and fetched in order to
    realize `drvs`"""
    result = run(
        ["nix-store", "--realize", "--dry-run"]
        + _nix_options_to_flags(nix_options)
        + drvs,
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
        if "will be fetched" in line:
            cur = to_fetch
        elif "will be built" in line:
            cur = to_build
        elif line.startswith("/nix/store"):
            cur += [line]
        elif line.startswith("warning:"):
            print(f"dry build: {line}", file=sys.stderr)
        elif line != "":
            raise RuntimeError(f"dry-run parsing failed, line was:`{line}`")

    return (to_build, to_fetch)


class InstantiationFailure(Exception):
    """Failure during instantiation."""


def instantiate(attrname, nix_file=".", nix_options=(), nix_argstr=(), expression=True):
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
    option_args = _nix_options_to_flags(nix_options)

    if expression:
        if nix_file is not None:
            # We need to simulate --argstr support since we're calling nixpkgs
            # manually to allow for arbitrary nix expressions.
            call_args = ""
            for (name, val) in nix_argstr:
                call_args += f'{name} = "{val}";'
            arg = (
                f"with (import {Path(nix_file).absolute()} {{{call_args}}}); {attrname}"
            )
        else:
            arg = attrname
        command = ["nix-instantiate", "-E", arg] + option_args
    else:
        for name, val in nix_argstr:
            option_args.append("--argstr")
            option_args.append(name)
            option_args.append(val)
        command = ["nix-instantiate", nix_file, "-A", arg] + option_args
    result = run(command, stdout=PIPE, stderr=PIPE, encoding="utf-8",)

    if result.returncode == 0:
        return result.stdout.strip()

    raise InstantiationFailure(result.stderr)


def dependencies(drvs, nix_options=()):
    """Returns all dependencies of `drvs` that aren't already in the
    store."""
    (to_build, to_fetch) = build_dry(drvs, nix_options=nix_options)
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

    def __init__(self, drvs_failed: Set[str]):
        assert len(drvs_failed) > 0, "BuildFailure requires at least one derivation to blame."
        super(BuildFailure).__init__()
        self.drvs_failed = drvs_failed


def _build_uncached(drvs, nix_options=()):
    if len(drvs) == 0:
        # nothing to do
        return ""

    # We need to use pexpect instead of subprocess.Popen here, since `nix
    # build` will not produce its regular output when it does not detect a tty.
    build_process = pexpect.spawn(
        "nix",
        ["build", "--no-link"] + _nix_options_to_flags(nix_options) + [d + "^*" if d.endswith(".drv") else d for d in drvs],
        logfile=sys.stdout.buffer,
    )

    # adapted from the pexpect docs
    def _update_build_winsize():
        s = struct.pack("HHHH", 0, 0, 0, 0)
        a = struct.unpack(
            "hhhh", fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, s)
        )
        if not build_process.closed:
            build_process.setwinsize(a[0], a[1])

    _update_build_winsize()
    signal.signal(signal.SIGWINCH, lambda _sig, _data: _update_build_winsize())

    drvs_failed = set()
    try:
        while True:
            # This will fill the "match" instance attribute. Raises on EOF. We
            # can only reliably use this for the final error output, not for
            # the streamed output of the actual build (since `nix build` skips
            # lines and trims output). Use `nix.log` for that.
            build_process.expect(
                [
                    _CANNOT_BUILD_PAT,
                    _BUILD_FAILED_PAT,
                    _BUILD_TIMEOUT_PAT,
                    _BUILDER_FAILED_PAT,
                ],
                timeout=None,
            )

            line = build_process.match.group(0)
            # Re-match to find out which pattern matched. This doesn't happen very
            # often, so the wasted effort isn't too bad.
            # Can't wait for https://www.python.org/dev/peps/pep-0572/
            match = _CANNOT_BUILD_PAT.match(line)
            if match is not None:
                drv = match.group(1).decode()
                _reason = match.group(2).decode()
                drvs_failed.add(drv)
            match = _BUILD_FAILED_PAT.match(line)
            if match is not None:
                drv_list = match.group(1).decode()
                drvs = drv_list.split(", ")
                drvs = [drv.strip("'") for drv in drvs]  # strip quotes
                drvs_failed.update(drvs)
            match = _BUILD_TIMEOUT_PAT.match(line)
            if match is not None:
                drv = match.group(1).decode()
                drvs_failed.add(drv)
            match = _BUILDER_FAILED_PAT.match(line)
            if match is not None:
                drv = match.group(1).decode()
                _exit_code = match.group(2).decode()
                drvs_failed.add(drv)
    except pexpect.exceptions.EOF:
        pass

    if len(drvs_failed) > 0:
        raise BuildFailure(drvs_failed)

    location_process = run(
        ["nix-store", "--realize"] + drvs, stdout=PIPE, stderr=PIPE, encoding="utf-8",
    )
    location_process.check_returncode()
    storepaths = location_process.stdout.split("\n")
    return storepaths


def log_contains(drv, phrase, write_cache=True):
    """Checks if the build log of `drv` contains a phrase

    This may or may not cause a rebuild. Cached logs are only trusted if they
    were produced by nix-bisect. May return "yes", "no_fail" or "no_success".
    """
    cache_dir = Path(AppDirs("nix-bisect").user_cache_dir)

    # If we already tried this before, we can trust our own cache.
    logfile = cache_dir.joinpath("logs").joinpath(Path(drv).name)
    if logfile.exists():
        with open(logfile, "r") as f:
            log_content = f.read()
            # We only save logs of failures.
            return "yes" if phrase in log_content else "no_fail"

    # We have to be careful with nix's cache since it might be incomplete.
    log_content = log(drv)
    if log_content is not None and phrase in log_content:
        return "yes"

    # Make sure the cache is populated.
    success = True
    try:
        build([drv], use_cache=False, write_cache=write_cache)
    except BuildFailure:
        success = False
    log_content = log(drv)

    if phrase in log_content:
        return "yes"
    elif success:
        return "no_success"
    else:
        return "no_fail"


def references(drvs):
    """Returns all immediate dependencies of `drvs`.

    Runs `nix-store --query --references` internally.
    """
    return (
        subprocess.check_output(["nix-store", "--query", "--references"] + drvs)
        .decode()
        .splitlines()
    )


def build_would_succeed(
    drvs,
    nix_options=(),
    max_rebuilds=float("inf"),
    rebuild_blacklist=(),
    use_cache=True,
    write_cache=True,
):
    """Determines build success without actually building if possible"""
    rebuilds = build_dry(drvs, nix_options=nix_options)[0]
    rebuild_count = len(rebuilds)
    if rebuild_count == 0:
        return True

    blacklisted = []
    for regex in rebuild_blacklist:
        for drv_to_rebuild in rebuilds:
            if re.match(regex, drv_to_rebuild) is not None:
                blacklisted.append(drv_to_rebuild)

    if len(blacklisted) > 0:
        raise exceptions.BlacklistedBuildsException(blacklisted)
    elif rebuild_count > max_rebuilds:
        raise exceptions.TooManyBuildsException()

    try:
        build(
            drvs, nix_options=nix_options, use_cache=use_cache, write_cache=write_cache
        )
        return True
    except BuildFailure:
        return False


def build(drvs, nix_options=(), use_cache=True, write_cache=True):
    """Builds `drvs`, returning a list of store paths"""
    cache_dir = Path(AppDirs("nix-bisect").user_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = cache_dir.joinpath("logs")
    logs_dir.mkdir(exist_ok=True)

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
                raise BuildFailure(set([drv]))

    try:
        return _build_uncached(drvs, nix_options)
    except BuildFailure as bf:
        if write_cache:
            for drv in bf.drvs_failed:
                # Could save more details here in the future if needed.
                result_cache[drv] = False
                # If the build finished, we know that we can trust the logs are
                # complete if they are available. This is essential for caching
                # "skip"s.
                failure_log = log(drv)
                if failure_log is not None:
                    with open(logs_dir.joinpath(Path(drv).name), "w") as f:
                        f.write(failure_log)

            with open(cache_file, "w") as cf:
                # Write human-readable json for easy hacking.
                cf.write(json.dumps(result_cache, indent=4))
        raise bf
