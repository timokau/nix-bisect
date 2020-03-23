"""Install nix-bisect"""

from setuptools import setup

setup(
    name="nix-bisect",
    version="0.3.0",
    description="Bisect nix builds",
    author="Timo Kaufmann",
    packages=["nix_bisect"],
    install_requires=["appdirs", "pexpect",],
    entry_points={"console_scripts": ["nix-bisect=nix_bisect.cli:_main",]},
)
