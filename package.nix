{
  lib,
  buildPythonPackage,
  appdirs,
  numpy,
  pexpect,
}:

let
  apps = [
    "bisect-env"
    "extra-bisect"
    "nix-build-status"
  ];
  self = buildPythonPackage rec {
    pname = "nix-bisect";
    version = "git";
    src = lib.cleanSource ./.;

    propagatedBuildInputs = [
      appdirs
      numpy
      pexpect
    ];

    passthru.apps = lib.genAttrs apps (script: {
      type = "app";
      program = "${self}/bin/${script}";
    });

    meta = {
      description = "Bisect nix builds";
      homepage = "https://github.com/timokau/nix-bisect";
      license = lib.licenses.mit;
      mainProgram = "nix-build-status";
    };
  };
in
self
