{
  description = "Bisect nix builds. Flake maintained by @n8henrie.";

  inputs.nixpkgs.url = "github:nixos/nixpkgs/release-23.11";
  inputs.systems.url = "github:nix-systems/default";

  outputs =
    {
      self,
      nixpkgs,
      systems,
    }:
    let
      inherit (nixpkgs.lib) foldl' recursiveUpdate genAttrs;

      # This function build a closure that maps the above systems to a function
      # accepting a system and returning an attrset in which that system can be
      # used as `${system}`, making it easy to provide packages / apps / etc.
      # that apply symmetrically to each of the above systems without having to
      # repeat oneself. In other words, `packages.${system}.foo = ...` becomes `{
      # `packages = { system1.foo` = ...; system2.foo = ... };`
      systemClosure =
        attrs: foldl' (acc: system: recursiveUpdate acc (attrs system)) { } (import systems);
    in
    systemClosure (
      system:
      let
        pkgs = import nixpkgs { inherit system; };
        pname = "nix-bisect";
      in
      {
        packages.${system} = {
          default = self.packages.${system}.${pname};
          ${pname} = pkgs.callPackage ./. { inherit pkgs; };
        };

        apps.${system} =
          genAttrs
            [
              "bisect-env"
              "extra-bisect"
              "nix-build-status"
            ]
            (script: {
              type = "app";
              program = "${self.packages.${system}.${pname}}/bin/${script}";
            });
      }
    );
}
