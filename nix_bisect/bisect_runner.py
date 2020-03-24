"""A python reimplementation of git-bisect"""

import subprocess
from nix_bisect import git, git_bisect


def named_skip(name, commit):
    """Mark a commit as belonging to a named skip range.

    In contrast to a regular `git bisect skip`, all commits between two commits
    in the range are considered skipped as well.
    """
    unique_name = git.rev_parse(commit)
    git.update_ref(f"refs/bisect/break/{name}/{unique_name}", commit)


def bisect_bad(commit):
    """Mark a commit as bad.

    Warning: This may have the side-effect of switching to a different
    revision.

    Unfortunately we don't have control about that. In the future we may want
    to manage the refs and the bisect-log manually.
    """
    subprocess.check_call(["git", "bisect", "bad", commit])


def bisect_good(commit):
    """Mark a commit as good.

    The same disclaimer as for `bisect_bad` applies.
    """
    subprocess.check_call(["git", "bisect", "good", commit])


def get_good_commits():
    """Returns all refs that are marked as good."""
    good_refs = []
    for ref in git.get_refs_with_prefix("refs/bisect"):
        parts = ref.split("/")
        if len(parts) == 3 and parts[2].startswith("good-"):
            good_refs.append(ref)
    return good_refs


def get_skip_range_commits():
    """Returns all refs that are marked with some skip range."""
    return git.get_refs_with_prefix("refs/bisect/break")


def get_named_skip_refs(name):
    """Returns all commits that are marked with the skip range `name`."""
    return git.get_refs_with_prefix(f"refs/bisect/break/{name}")


def get_skip_ranges():
    """Returns all skip range names"""
    return {ref.split("/")[3] for ref in git.get_refs_with_prefix("refs/bisect/break")}


def refs_for_commit(commit):
    """Returns all refs that point to a commit."""
    lines = subprocess.check_output(["git", "show-ref"]).decode().splitlines()
    result = dict()
    for line in lines:
        (target, ref) = line.split(" ")
        new_set = result.get(target, set())
        new_set.add(ref)
        result[target] = new_set
    return result[commit]


def skip_ranges_of_commit(commit):
    """Returns all named skip ranges a commit is marked with."""
    skip_ranges = []
    print(f"Skip ranges for {commit}")
    for ref in refs_for_commit(commit):
        print(f"Considering {ref}")
        if ref.startswith("refs/bisect/break/"):
            components = ref.split("/")
            if len(components) == 5:
                skip_ranges.append(components[3])
    return skip_ranges


def clear_skip_range(range_name):
    """Remove all refs that belong to a skip range"""
    for ref in git.get_refs_with_prefix(f"refs/bisect/break/{range_name}"):
        git.delete_ref(ref)


class BisectRunner:
    """Runs a bisection"""
    def __init__(self):
        # Should be persisted in git somehow, but this works as a POC.
        self.to_pick = []

    def get_next(self):
        """Computes the next commit to test.

        This takes skip-ranges into account and prioritizes finding the first
        commit that unbreaks a skip range.

        May add commits for cherry pick. Returns `False` when the bisect is
        finished.
        """
        considered_good = get_good_commits() + get_skip_range_commits()
        commit = git.get_bisect_info(considered_good, "refs/bisect/bad")["bisect_rev"]
        if git.rev_parse(commit) == git.rev_parse("refs/bisect/bad"):
            skip_ranges = []
            good_commits = [git.rev_parse(ref) for ref in get_good_commits()]
            for parent in git.parents(commit):
                if parent in good_commits:
                    print(f"First bad found! Here it is: {commit}")
                    return None
                skip_ranges += skip_ranges_of_commit(parent)
            for skip_range in skip_ranges:
                clear_skip_range(skip_range)
            print(f"cherry-pick {commit} to unbreak {skip_ranges}")
            self.to_pick.insert(0, commit)
            return self.get_next()
        return commit

    def run(self, bisect_fun):
        """Finds the first bad commit"""
        while True:
            next_commit = self.get_next()
            if next_commit is None:
                return
            git.checkout(next_commit)
            with git.git_checkpoint():
                for rev in self.to_pick:
                    git.try_cherry_pick_all(rev)
                result = bisect_fun()
            if result == "bad":
                bisect_bad("HEAD")
                git_bisect.print_bad()
            elif result == "good":
                bisect_good("HEAD")
                git_bisect.print_good()
            elif result.startswith("skip"):
                reason = result[len("skip ") :]
                git_bisect.print_skip(reason)
                named_skip(reason, "HEAD")
            else:
                raise Exception("Unknown bisection result.")
