"""Install nix-bisect"""

from setuptools import setup

setup(
    name="nix-bisect",
    version="0.2.0",
    description="Bisect nix builds",
    author="Timo Kaufmann",
    packages=["nix_bisect"],
)
