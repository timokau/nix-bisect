# Nix-bisect -- Bisect Nix Builds

Thanks to the reproducibility of [nix](https://nixos.org/nix/) and the monorepo approach of [nixpkgs](https://github.com/NixOS/nixpkgs) it is possible to bisect anything from a simple build failure to a regression in your system setup.

The naive way to bisect a nix build would be

```bash
git bisect run nix build -f. attrname
```

This is not perfect though. If you use `nix-bisect` and replace that command with

```bash
git bisect run python3 -m nix_bisect.cli attrname
```

You get the following benefits out of the box:

- nicer output, with color highlighting on bisect success/failure
- `bisect skip` on dependency failures, `bisect bad` only if the actual attribute fails to build
- the bisect is aborted on ctrl-c, instead of registering as a `bisect bad`
- if there is some unexpected failure, like an instantiation failure, the bisect is aborted instead of registering as a `bisect bad`

In addition to that out of the box behaviour you can also use it for more complex use-cases. Consider this example:


```
git bisect run python3 -m nix_bisect.cli --try-cherry-pick e3601e1359ca340b9eda1447436c41f5aa7c5293 --max-rebuilds 500 --failure-line="TypeError:"  'sage.tests.override { files=["src/sage/env.py"]; }'
```

This can be used to track down a failure in the sage build. It should be fairly self-explanatory. In addition to the benefits mentioned above, it will

- Try to cherry-pick commit `e3601e1e` into the tree before starting the build. This is really useful to bisect when there are some already fixed intermediate failures. This option can be passed multiple times. When the commit fails to apply (for example because it is already applied on the current checkout), it is simply not applied. The tree is reset to the exact state it was before (including unstaged changes) once the build is finished.
  
- Skip on any build that would require more than 500 local builds.

- Register `bisect bad` only when the build fails *and* the specified text occurs in the build log. If the build fails without the text the current revision is skipped.

- Make use of cached builds *and* cached failures (which is only possible with `--failure-line`).

- Build the *overridden* attribute `sage.tests.override { files=["src/sage/env.py"]; }`. Plain `nix build` will not allow you to use overrides by default.

It is very hard, maybe impossible, to build a command-line interface that is flexible enough to cover any possible use-case for bisecting nix builds. Because of that, `nix-bisect` is not only a command line tool but primarily a python library. The CLI is only a convenience for common use-cases.

If you have a more complex use-case, you can use `nix-bisect` to write a bisection script in an arguably saner language than bash. You get nice utility functions and abstractions.

As an example, [here](https://github.com/timokau/nix-bisect/blob/712adc0cd3c34bd45c22c03c06d58e83d58da1c3/doc/examples/digikam.py) is a script I used to debug a digikam segfault. It will build digikam (transparently dealing with an change of its attrname that happened at some point), skipping through all build failures. Once a build finally succeeds, it will prompt me to manually check for a segfault and use my input to decide whether the current revision is good or bad.

Keep in mind however that this is very early stages. Barely anything is documented. I built this to scratch my own itch, and I continue developing it whenever I need some feature.

Still, I can already be quite useful for some people. It is not packaged in nixpkgs, but if you want to try it out simply add this expression to your python packages:

```nix
(python3.pkgs.buildPythonPackage rec {
  pname = "nix-bisect";
  version = "0.2.0";
  src = pkgs.fetchFromGitHub {
    owner = "timokau";
    repo = "nix-bisect";
    rev = "v${version}";
    sha256 = "0rg7ndwbn44kximipabfbvvv5jhgi6vs87r64wfs5by81iw0ivam";
  };
})
```
