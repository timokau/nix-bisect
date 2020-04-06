"""Utility functions for dealing with nix gc-roots"""

from pathlib import Path
import tempfile
import os

STATE_DIR = Path(os.environ.get("NIX_STATE_DIR", "/nix/var/nix/"))
USER = os.environ.get("USER", "user-unknown")
GCROOT_DIR = Path(STATE_DIR).joinpath("gcroots/per-user").joinpath(USER)


def gcroot_path(name):
    """Path to a gcroot file with name `name`"""
    return GCROOT_DIR.joinpath(name)


def tmp_path(name):
    """Path to the gcroot indirection in the tmp dir"""
    return Path(tempfile.gettempdir()).joinpath(f"nix-bisect-gcroot-{name}")


def create_tmp_gcroot(name, target):
    """Create an indirect gcroot in tmpdir.

    This has the advantage of automatically being cleaned up in case of a crash.
    """
    tmpfile = tmp_path(name)
    os.symlink(target, tmpfile)
    create_gcroot(name, tmpfile)


def create_gcroot(name, target):
    """Create a gcroot"""
    os.symlink(target, gcroot_path(name))


def delete_gcroot(name):
    """Delete a gcroot and its indirect temporary file"""
    os.remove(gcroot_path(name))


def delete_tmp_gcroot(name):
    """Delete a gcroot and its indirect temporary file"""
    os.remove(tmp_path(name))
    delete_gcroot(name)
