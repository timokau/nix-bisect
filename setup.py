"""Install nix-bisect"""

from setuptools import setup, find_packages

setup(
    name="nix-bisect",
    version="0.4.1",
    description="Bisect nix builds",
    author="Timo Kaufmann",
    packages=find_packages(),
    install_requires=["appdirs", "pexpect",],
    entry_points={
        "console_scripts": [
            "nix-build-status=nix_bisect.build_status:_main",
            "bisect-env=nix_bisect.bisect_env:_main",
            "extra-bisect=nix_bisect.extra_bisect:_main",
        ]
    },
)
