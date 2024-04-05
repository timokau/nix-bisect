{
  description = "Bisect nix builds. Flake maintained by @n8henrie.";

  inputs.nixpkgs.url = "github:nixos/nixpkgs/release-23.05";

  outputs =
    { self, nixpkgs }:
    let
      inherit (nixpkgs) lib;
      systems = [
        "aarch64-darwin"
        "x86_64-linux"
        "aarch64-linux"
      ];

      # This function build a closure that maps the above systems to a function
      # accepting a system and returning an attrset in which that system can be
      # used as `${system}`, making it easy to provide packages / apps / etc.
      # that apply symmetrically to each of the above systems without having to
      # repeat oneself. In other words, `packages.${system}.foo = ...` becomes `{
      # `packages = { system1.foo` = ...; system2.foo = ... };`
      systemClosure =
        attrs: builtins.foldl' (acc: system: lib.recursiveUpdate acc (attrs system)) { } systems;
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
          pkgs.lib.genAttrs
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
