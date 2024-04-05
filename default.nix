{
  # `git ls-remote https://github.com/nixos/nixpkgs-channels nixos-unstable`
  nixpkgs-rev ? "ddf87fb1baf8f5022281dad13fb318fa5c17a7c6",
  pkgsPath ? builtins.fetchTarball {
    name = "nixpkgs-${nixpkgs-rev}";
    url = "https://github.com/nixos/nixpkgs/archive/${nixpkgs-rev}.tar.gz";
  },
  pkgs ? import pkgsPath { },
}:

pkgs.python3.pkgs.callPackage ./package.nix { }
