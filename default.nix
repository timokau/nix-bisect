{
  # `git ls-remote https://github.com/nixos/nixpkgs-channels nixos-unstable`
  # Use the flake.lock nixpkgs revision as the default
  nixpkgs-rev ?
    let
      lockFile = builtins.fromJSON (builtins.readFile ./flake.lock);
    in
    lockFile.nodes.nixpkgs.locked.rev,
  pkgsPath ? builtins.fetchTarball {
    name = "nixpkgs-${nixpkgs-rev}";
    url = "https://github.com/nixos/nixpkgs/archive/${nixpkgs-rev}.tar.gz";
  },
  pkgs ? import pkgsPath { },
}:

pkgs.python3.pkgs.callPackage ./package.nix { }
