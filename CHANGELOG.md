# Changes for nix-bisect

## [0.3.0] - 2020-03-24

- Successful cached builds are no longer unnecessarily fetched.
- We now cache logs of failures, even dependency failures. This enables
  reliable skip caching (since `nix log` is not reliable) and transitive build
  failure caching (i.e. caching of dependency failures).
- There is a new `nix-bisect` entrypoint which can be called directly instead
  of calling the python module.
- The nix file to build an attribute from can now be changed by passing
  `--nix-file` or `-f`.
- There is now a new (very experimental) bisect runner that can be enabled with
  the `--bisect-runner` flag. When that flag is used, `nix-bisect` should used
  standalone instead of as a parameter of `git bisect`. Taking full control of
  the bisection opens the door to many possible improvements.
- One such improvement is already implemented: The bisect runner will
  treat skips as ranges (i.e. a commit between two skips is assumed to be
  skipped as well) and automatically identifies which commit "unbreak" this
  range. It then automatically cherry-picks those "unbreak" commits to enable
  further bisection.

## [0.2.0] - 2020-01-21

- Added a simple command line interface.
- Various changes to the library

## 0.1.0 - 2019-08-13

- Initial version, library only

[unreleased]: https://github.com/timokau/nix-bisect/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/timokau/nix-bisect/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/timokau/nix-bisect/compare/v0.1.0...v0.2.0
