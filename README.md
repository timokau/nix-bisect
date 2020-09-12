# Nix-bisect -- Bisect Nix Builds

Thanks to the reproducibility of [nix](https://nixos.org/nix/) and the monorepo approach of [nixpkgs](https://github.com/NixOS/nixpkgs) it is possible to bisect anything from a simple build failure to a regression in your system setup.

## Quick Usage Example

Imagine you just discovered that the `python3.pkgs.rpy2` build is failing on current master (which is assumed to be 0729b8c55e0dfaf302af4c57546871d47a652048):

```bash
$ git checkout 0729b8c55e0dfaf302af4c57546871d47a652048
HEAD is now at 0729b8c55e0 Revert Merge #82310: nixos/systemd: apply .link

$ nix build -f. python3.pkgs.rpy2
builder for '/nix/store/blxlihmb2a4x90x8as9f0hihwag6pa1a-python3.7-rpy2-3.2.6.drv' failed with exit code 1; last 10 log lines:
    /nix/store/4lf6ry28hv9ydflwy62blbsca9hqkwq2-python3.7-ipython-7.12.0/lib/python3.7/site-packages/IPython/paths.py:67: UserWarning: IPython parent '/homeless-shelter' is not a writable location, using a temp directory.
      " using a temp directory.".format(parent))
  
  rpy2/tests/robjects/test_pandas_conversions.py::TestPandasConversions::test_dataframe_int_nan[dtype0]
  rpy2/tests/robjects/test_pandas_conversions.py::TestPandasConversions::test_dataframe_int_nan[dtype1]
    /build/rpy2-3.2.6/rpy2/robjects/pandas2ri.py:63: UserWarning: Error while trying to convert the column "z". Fall back to string conversion. The error is: int() argument must be a string, a bytes-like object or a number, not 'NAType'
      % (name, str(e)))
  
  -- Docs: https://docs.pytest.org/en/latest/warnings.html
  = 4 failed, 674 passed, 12 skipped, 2 xfailed, 1 xpassed, 6 warnings in 30.07s =
[0 built (1 failed), 0.0 MiB DL]
error: build of '/nix/store/blxlihmb2a4x90x8as9f0hihwag6pa1a-python3.7-rpy2-3.2.6.drv' failed
```

as a first reaction, you check the build log to get a hint of what is causing the issue:

```bash
nix log /nix/store/blxlihmb2a4x90x8as9f0hihwag6pa1a-python3.7-rpy2-3.2.6.drv
[output elided]
```

you don't immediately recognize the failure. Instead of researching or debugging it, you decide to take advantage of nix and nixpkgs and bisect the failure first. You're fairly confident the build worked a while ago, so you just randomly check a previous commit. You can be generous in the step size here, since `git-biset` has a logarithmic runtime.


```
git co HEAD~5000
Updating files: 100% (9036/9036), done.
Previous HEAD position was 0729b8c55e0 Revert Merge #82310: nixos/systemd: apply .link
HEAD is now at 43165b29e2e Merge pull request #71894 from timokau/home-manager-2019-10-23

$ nix build -f. python3.pkgs.rpy2
[152 copied (1362.1 MiB), 377.5 MiB DL]
```

The build succeeded! Now you have a good commit and a bad commit. To make
bisection more robust, the only thing missing is a "failure line", e.g. a line
from the build log to distinguish the failure we're looking for from other
failures that may have come and gone in the meantime. Looking back at the build
log of the failed attempt, the line

> Incompatible C type sizes. The R array type is 4 bytes while the Python array type is 8 bytes.

seems pretty distinctive. Now we can go ahead with the bisect.

```bash
extra-bisect start 0729b8c55e0dfaf302af4c57546871d47a652048 HEAD
```

Now let `nix-bisect` take care of the actual bisection:

```bash
extra-bisect run \
	nix-build-status \
	--max-rebuild 100 \
	--failure-line 'Incompatible C type sizes. The R array type is 4 bytes while the Python array type is 8 bytes.' \
	python3.pkgs.rpy2
```

This takes a while. Fetch a coffee. In fact, fetch the can. On my laptop this
ran for a little over 2 hours. During the run it notices several intermediate
failures which prevent it from deciding whether the commit is good or bad. It
determines which commits fix those intermediate failures and automatically
cherry-picks those commits to continue the bisection

- fc7e4c926755f47edcda488eaea0c7fb82ff5af9 fix `texlive`
- ff741a5d52550f0bfcb07584c35349f8f9208e0c disable a failing `pandas` test
- eebda1d2f9cdffba3530428b34d97c493cc82677 fix an unrelated `rpy2` failure

Finally and without any human intervention we get the result: The build was
broken by a recent `pandas` 1.0 update! Some more research reveals that the bug
issue is actually known and already fixed upstream, the upstream repository I
searched first was just outdated.

As the last step, let's be good open source citizens and upstream our findings:

- https://github.com/rpy2/rpy2/issues/662
- https://github.com/NixOS/nixpkgs/pull/82773

## Explanation and Rationale

The naive way to bisect a nix build would be

```bash
git bisect run nix build -f. attrname
```

This is not perfect though. If you use `nix-bisect` and replace that command with

```bash
git bisect run nix-build-status attrname
```

You get the following benefits out of the box:

- nicer output, with color highlighting on bisect success/failure
- `bisect skip` on dependency failures, `bisect bad` only if the actual attribute fails to build
- the bisect is aborted on ctrl-c, instead of registering as a `bisect bad`
- if there is some unexpected failure, like an instantiation failure, the bisect is aborted instead of registering as a `bisect bad`

In addition to that out of the box behaviour you can also use it for more
complex use-cases. Consider this example:


```
git bisect run bisect-env --try-pick e3601e1359ca340b9eda1447436c41f5aa7c5293 nix-build-status --max-rebuilds 500 --failure-line="TypeError:"  'sage.tests.override { files=["src/sage/env.py"]; }'
```

This can be used to track down a failure in the sage build. It should be fairly
self-explanatory. In addition to the benefits mentioned above, it will

- Try to cherry-pick commit `e3601e1e` into the tree before starting the build.
  This is really useful to bisect when there are some already fixed
  intermediate failures. This option can be passed multiple times. When the
  commit fails to apply (for example because it is already applied on the
  current checkout), it is simply not applied. The tree is reset to the exact
  state it was before (including unstaged changes) once the build is finished.
  
- Skip on any build that would require more than 500 local builds.

- Register `bisect bad` only when the build fails *and* the specified text
  occurs in the build log. If the build fails without the text the current
  revision is skipped.

- Make use of cached builds *and* cached failures (which is only possible with `--failure-line`).

- Build the *overridden* attribute `sage.tests.override { files=["src/sage/env.py"]; }`.
  Plain `nix build` will not allow you to use overrides by default.

It is very hard, maybe impossible, to build a command-line interface that is
flexible enough to cover any possible use-case for bisecting nix builds.
Because of that, `nix-bisect` is not only a command line tool but primarily a
python library. The CLI is only a convenience for common use-cases.

If you have a more complex use-case, you can use `nix-bisect` to write a
bisection script in an arguably saner language than bash. You get nice utility
functions and abstractions.

As an example,
[here](https://github.com/timokau/nix-bisect/blob/712adc0cd3c34bd45c22c03c06d58e83d58da1c3/doc/examples/digikam.py)
is a script I used to debug a digikam segfault. It will build digikam
(transparently dealing with an change of its attrname that happened at some
point), skipping through all build failures. Once a build finally succeeds, it
will prompt me to manually check for a segfault and use my input to decide
whether the current revision is good or bad.

Keep in mind however that this is very early stages. Barely anything is
documented. I built this to scratch my own itch, and I continue developing it
whenever I need some feature.

Still, I can already be quite useful for some people. It is not packaged in
nixpkgs, but if you want to try it out simply use `nix-shell` with the
`default.nix` provided in this repository.
