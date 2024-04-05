{
  description = "Bisect nix builds. Flake maintained by @n8henrie.";

  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  inputs.systems.url = "github:nix-systems/default";

  outputs =
    {
      self,
      nixpkgs,
      systems,
    }:
    let
      inherit (nixpkgs.lib) foldl' recursiveUpdate;

      # This function build a closure that maps the above systems to a function accepting a system
      # and returning an attrset in which that system can be used as `${system}`, making it easy to
      # provide packages, apps, and so forth that apply symmetrically to each of the above systems
      # without having to repeat oneself.
      #
      # In other words, `packages.${system}.foo = ...` becomes:
      # ```nix
      # {
      #   packages = {
      #     system1.foo = ...;
      #     system2.foo = ...;
      #   };
      # }
      # ```
      systemClosure =
        attrs: foldl' (acc: system: recursiveUpdate acc (attrs system)) { } (import systems);
    in
    systemClosure (system: {
      packages.${system} = {
        default = self.packages.${system}.nix-bisect;
        nix-bisect = nixpkgs.legacyPackages.${system}.python3.pkgs.callPackage ./package.nix { };
      };

      apps.${system} = self.packages.${system}.default.passthru.apps;
    });
}
