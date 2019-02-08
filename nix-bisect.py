#!/usr/bin/env nix-shell
#! nix-shell -i python3 -p "python3.withPackages(ps: with ps; [ pytimeparse pexpect ])" -p nix
# examples
# git bisect run ~/nix-bisect/nix-bisect.py --failure-line 'pthread_create: Invalid argument' --success-line 'Sorting sources by runtime' --success-timeout 5m sage.tests --run-before 'git reset --hard && git -c rerere.enabled=false merge --no-commit BISECT_HEAD'
# git bisect run ~/nix-bisect/nix-bisect.py --failure-line 'pthread_create: Invalid argument' --success-line 'Sorting sources by runtime' --timeout 5m sage.tests --run-before 'git reset --hard && git diff HEAD..timokau/sage-8.5 pkgs/applications/science/math/sage | patch -p1' --no-skip-range

from subprocess import run, Popen, PIPE, STDOUT
import sys
import shutil
import pexpect
import re
import time
import signal
import logging


# https://github.com/tartley/colorama
# https://docs.python.org/3.5/library/logging.html
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def soft_skip():
    pass

def evaluate_log(log, failure_line = None, success_line = None):
    if success_line is not None and success_line in log:
        return True
    elif failure_line is not None and failure_line in log:
        return False
    else:
        return None

# either a binary cache or an earlier build
# returns (log, success) or None
def cached_result(drv, failure_line = None, success_line = None):
    result = run([
            'nix',
            'log',
            '-f.',
            drv,
        ],
        stdout = PIPE,
        stderr = PIPE,
        encoding = "utf-8",
    )
    (built, fetched) = dry_run(drv)
    log_text = result.stdout
    if result.returncode == 0 and len(log_text) > 0:
        if len(built) == 0:
            # TODO is this a success even if success_line is not found?
            logging.info("Successful build cached")
            return (log_text, True)
        else:
            success = evaluate_log(log_text, failure_line, success_line)
            if success is not None:
                print(f"Found cached success={success}")
                return (log_text, success)
            else:
                print(f"Cache nonconclusive")
                return (None, None)
    else:
        # print("Build not cached")
        return (None, None)

# takes time in the order of 2s
def dry_run(drv):
    result = run([
            'nix-build',
            '--dry-run',
            drv,
        ],
        stdout = PIPE,
        stderr = PIPE,
        encoding = "utf-8",
    )
    result.check_returncode()
    lines = result.stderr.splitlines()
    fetched = []
    built = []
    cur = fetched
    for line in lines:
        line = line.strip()
        if "these paths will be fetched" in line :
            cur = fetched
        elif "these derivations will be built" in line:
            cur = built
        elif line.startswith("/nix/store"):
            cur += [ line ]
        elif line != "":
            raise RuntimeError("dry-run parsing failed")

    return (built, fetched)

def cur_commit():
    result = run([
            'git',
            'rev-parse',
            'HEAD',
        ],
        stdout = PIPE,
        stderr = PIPE,
        encoding = "utf-8",
    )
    result.check_returncode()
    return result.stdout.strip()

def commits_in_range(rev1, rev2):
    result = run([
            'git',
            'log',
            '--pretty=format:%H',
            f'{rev1}..{rev2}',
        ],
        stdout = PIPE,
        stderr = PIPE,
        encoding = "utf-8",
    )
    return len(result.stdout.splitlines())

def range_order(rev1, rev2):
    in_range = commits_in_range(rev1, rev2)
    if commits_in_range(rev1, rev2) != 0:
        return (rev1, rev2, in_range)
    else:
        return (rev2, rev1, commits_in_range(rev2, rev1))

def abort():
    # abort bisect process
    sys.exit(128)

def skip_range(rev1, rev2):
    (rev1, rev2, commits) = range_order(rev1, rev2)
    result = run([
            'git',
            'bisect',
            'skip',
            rev1,
            f'{rev1}..{rev2}',
        ],
        stdout = PIPE,
        stderr = STDOUT,
        encoding = "utf-8",
    )
    print(f"Skipping {commits} commits")
    # max fail when bisect is done
    # result.check_returncode()

def instantiate(attrname, nixpkgs_dir):
    result = run([
            'nix-instantiate',
            nixpkgs_dir,
            '-A',
            attrname,
        ],
        stdout = PIPE,
        stderr = PIPE,
        encoding = "utf-8",
    )
    if result.returncode == 0:
        return result.stdout.strip()
    else:
        print(result.stderr)
        return None


def _references(storepath):
    result = run([
            'nix-store',
            '--query',
            '--references',
            storepath,
        ],
        stdout = PIPE,
        stderr = PIPE,
        encoding = "utf-8",
    )
    result.check_returncode()
    return result.stdout.splitlines()


def build_dependencies(drv, nixpkgs_dir = '.'):
    result = run([
            'nix',
            '--max-jobs', '2',
            'build',
            '-f',
            nixpkgs_dir,
        ] + _references(drv),
    )

    return result.returncode == 0

ANSI_ERASE_LINE='\x1b[K'
def nix_build(drv, timeout = None, on_timeout = "skip", failure_line = None, success_line = None):
    # use pexpect to simulate tty

    # \r
    # querying info about missing paths\x1b[K\r
    # [\x1b[34;1m1\x1b[0m/\x1b[32;1m0\x1b[0m/1 built] building \x1b[1mclamav-0.101.0\x1b[0m (unpackPhase): unpacking sources\x1b[K\r
    starttime = time.time()
    p = pexpect.spawn(f'nix-build {drv}', dimensions=(1, 2**16 - 1))
    buf = b""
    # ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    log = ''
    while True:
        try:
            elapsed = time.time() - starttime
            expect_timeout = None if timeout is None else timeout - elapsed
            p.expect(b'\r\n', timeout=expect_timeout)
        except pexpect.EOF:
            break
        except pexpect.TIMEOUT:
            p.kill(signal.SIGTERM)
            print("Timeout out, interpreting as {}".format(on_timeout))
            if on_timeout == "skip":
                return (log, None)
            elif timeout == "good":
                return (log, True)
            elif timeout == "bad":
                return (log, False)
            else:
                raise RuntimeError()
        line = p.before
        line = line.decode("utf-8")
        # line = ansi_escape.sub('', line)
        success = evaluate_log(line, failure_line, success_line)
        if success is not None:
            p.kill(signal.SIGTERM)
            p.close()
            if not success:
                print(f"\nFailure line detected: {line}")
            else:
                print(f"\nSuccess line detected: {line}")
            return (log, success)
        max_len = shutil.get_terminal_size().columns
        line = line[:max_len]
        sys.stdout.write(line + ANSI_ERASE_LINE + '\r')
        log += line + '\n'
    p.close()
    print(f"\nBuild finished with exit status {p.exitstatus}")
    return (log, p.exitstatus == 0)

def cache_to_file(l, f):
    import pickle
    with open(f, 'wb') as handle:
        pickle.dump(l, handle)

def cache_from_file(f):
    import pickle
    try:
        with open(f, 'rb') as handle:
            l = pickle.load(handle)
    except FileNotFoundError:
        return dict()
    return l

def run_cleanup(cleanup):
    print(f"Running cleanup script: {cleanup}")
    result = run([
            'sh',
            '-c',
            cleanup,
        ],
    )

def quit_good(cleanup):
    run_cleanup(cleanup)
    print(f"{bcolors.OKGREEN}bisect: good{bcolors.ENDC}")
    sys.exit(0)

def quit_bad(cleanup, exitcode = 1):
    run_cleanup(cleanup)
    print(f"{bcolors.FAIL}bisect: bad{bcolors.ENDC}")
    sys.exit(exitcode)

def quit_skip(cleanup, skip_cache):
    run_cleanup(cleanup)
    # TODO skip_cache instance variable
    print(f"{bcolors.OKBLUE}bisect: skip{bcolors.ENDC}")
    if skip_cache is not None:
        skip_cache[drv] = (cur_commit(), "skip")
        cache_to_file(skip_cache, CACHE_FILE)
    sys.exit(125)

def signal_handler(sig, frame):
    print("Interrupt detected, aborting!")
    abort()

def main():
    import argparse
    import pytimeparse

    signal.signal(signal.SIGINT, signal_handler)
    parser = argparse.ArgumentParser(
        description='Bisect nix builds',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog = """
        EXAMPLES:
        adf
        """,
    )
    parser.add_argument('installable', type=str, help='argument to pass to nixw')
    parser.add_argument('-t', '--timeout', type=pytimeparse.parse, dest='timeout', default=None, help='Time after which the build is considered a success')
    parser.add_argument('--on-timeout', type=str, dest='on_timeout', default='skip', choices=['skip', 'good', 'bad'], help='What to do on timeout')
    parser.add_argument('--failure-line', type=str, dest='failure_line', default=None, help='Log line that indicates failure')
    parser.add_argument('--success-line', type=str, dest='success_line', default=None, help='Log line that indicates success')
    parser.add_argument('--ignore-cached-failures', action='store_true', dest='ignore_cached_failures', default=False, help='Log line that indicates failure')
    parser.add_argument('--run-before', type=str, dest='run_before', default=None, help='Commands to execute before testing a commit')
    parser.add_argument('--run-after', type=str, dest='run_after', default='git reset --hard', help='Commands to execute after testing a commit (cleanup)')
    parser.add_argument('--no-skip-range', action='store_true', dest='no_skip_range', default=False, help='Do not skip ranges')
    parser.add_argument('-f', '--nixpkgs-dir', type=str, dest='nixpkgs_dir', default='.', help='Directory to build from\nsome long desc')

    args = parser.parse_args()
    CACHE_FILE='.nix-bisect-cache'
    skip_cache = cache_from_file(CACHE_FILE)
    if args.no_skip_range:
        skip_cache = dict()

    while True:
        if args.run_before is not None:
            print("Running run-before script")
            result = run([
                    'sh',
                    '-c',
                    args.run_before,
                ],
            )
            if result.returncode != 0:
                print("Failed")
                quit_skip(args.run_after, None)
        print("Instantiating")
        drv = instantiate(args.installable, args.nixpkgs_dir)
        if drv is None:
            print("Failed")
            quit_skip(args.run_after, skip_cache)
        cached = skip_cache.get(drv)
        if cached is not None:
            (commit, result) = cached
            if result == "skip":
                cur = cur_commit()
                print(f'Skipping range {cur}..{commit}')
                if not args.no_skip_range:
                    skip_range(cur, commit)
        else:
            break

    (log, success) = cached_result(drv, args.failure_line, args.success_line)
    # TODO check for failure line in cached result
    if success is not None and not success and args.ignore_cached_failures:
        print("Ignoring cache")
        success = None
    if success is None:
        (build, fetched) = dry_run(drv)
        rebuilds = len(build)
        if rebuilds > 200: # FIXME
            print(f"{rebuilds} rebuild necessary, skipping.")
            quit_skip(args.run_after, skip_cache)
        else:
            print("Building dependencies")
            success = build_dependencies(drv)
            if not success:
                print(f"Dependencies failed. Skipping.")
                skip_cache[drv] = (cur_commit(), "skip")
                cache_to_file(skip_cache, CACHE_FILE)
                quit_skip(args.run_after, skip_cache)
            print("Building target")
            (log, success) = nix_build(drv, timeout = args.timeout, on_timeout=args.on_timeout, failure_line = args.failure_line, success_line = args.success_line)
    if success:
        print("Success")
        quit_good(args.run_after)
    else:
        print("Bad")
        quit_bad(args.run_after)

if __name__ == "__main__":
    import traceback
    # try:
    main()
    # except:
    #     # make sure script failure doesn't mess with bisect result
    #     traceback.print_exc()
    #     abort()
