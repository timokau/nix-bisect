{
  description = "Bisect nix builds. Flake maintained by @n8henrie.";

  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "aarch64-darwin"
        "x86_64-linux"
        "aarch64-linux"
      ];
      eachSystem = f: nixpkgs.lib.genAttrs systems f;
    in
    {
      packages = eachSystem (system: {
        default = self.packages.${system}.nix-bisect;
        nix-bisect = nixpkgs.legacyPackages.${system}.python3.pkgs.callPackage ./package.nix { };
      });

      apps = eachSystem (system: self.packages.${system}.default.passthru.apps);
      formatter = eachSystem (system: nixpkgs.legacyPackages.${system}.nixfmt-rfc-style);
    };
}
