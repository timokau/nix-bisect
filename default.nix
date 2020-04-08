{ # `git ls-remote https://github.com/nixos/nixpkgs-channels nixos-unstable`
  nixpkgs-rev ? "ddf87fb1baf8f5022281dad13fb318fa5c17a7c6"
, pkgsPath ? builtins.fetchTarball {
    name = "nixpkgs-${nixpkgs-rev}";
    url = "https://github.com/nixos/nixpkgs/archive/${nixpkgs-rev}.tar.gz";
  }
, pkgs ? import pkgsPath {}
}:
let
  inherit (pkgs) lib;
  nix-bisect = pkgs.python3.pkgs.buildPythonPackage rec {
    pname = "nix-bisect";
    version = "git";
    src = lib.cleanSource ./.;
    propagatedBuildInputs = with pkgs.python3.pkgs; [
      appdirs
      numpy
      pexpect
    ];
  };
in
  # python3.withPackages(ps: with ps; [nix-bisect])
  nix-bisect
