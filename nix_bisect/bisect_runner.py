"""A python reimplementation of git-bisect"""

import subprocess
from nix_bisect import git, git_bisect


def patchset_identifier(patchset):
    """Unique string identifier for a patchset to be used in ref names"""
    if len(patchset) == 0:
        return "nopatch"
    else:
        return "/".join([f"p_{rev}" for rev in patchset])


def named_skip(name, patchset, commit):
    """Mark a commit as belonging to a named skip range.

    In contrast to a regular `git bisect skip`, all commits between two commits
    in the range are considered skipped as well.
    """
    unique_name = git.rev_parse(commit)
    git.update_ref(
        f"refs/bisect/break/{patchset_identifier(patchset)}/markers/{name}/{unique_name}",
        commit,
    )


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


def get_skip_range_commits(patchset):
    """Returns all refs that are marked with some skip range."""
    return git.get_refs_with_prefix(
        f"refs/bisect/break/{patchset_identifier(patchset)}/markers"
    )


def within_range(commit, range_markers):
    """Whether or not a given commit is enclosed by a pair of range markers"""
    reached_by_range = False
    for marker in range_markers:
        if git.is_ancestor(commit, marker):
            reached_by_range = True
            break
    if not reached_by_range:
        return False

    can_reach_range = False
    for marker in range_markers:
        if git.is_ancestor(marker, commit):
            can_reach_range = True
            break
    return can_reach_range


def get_named_skip_refs(name, patchset):
    """Returns all commits that are marked with the skip range `name`."""
    return git.get_refs_with_prefix(
        f"refs/bisect/break/{patchset_identifier(patchset)}/markers/{name}"
    )


def get_skip_ranges(patchset):
    """Returns all skip range names"""
    return {
        ref.split("/")[-2]
        for ref in git.get_refs_with_prefix(
            f"refs/bisect/break/{patchset_identifier(patchset)}/markers"
        )
    }


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


def skip_ranges_of_commit(commit, patchset):
    """Returns all named skip ranges a commit is marked with."""
    skip_ranges = []
    for ref in refs_for_commit(commit):
        if ref.startswith(f"refs/bisect/break/{patchset_identifier(patchset)}/markers"):
            components = ref.split("/")
            skip_ranges.append(components[-2])
    return skip_ranges


def clear_refs_with_prefix(prefix):
    """Remove all refs that belong to a skip range"""
    for ref in git.get_refs_with_prefix(prefix):
        git.delete_ref(ref)


class BisectRunner:
    """Runs a bisection"""

    def __init__(self):
        # Should be persisted in git somehow, but this works as a POC.
        self.patchset = []

    def get_next(self):
        """Computes the next commit to test.

        This takes skip-ranges into account and prioritizes finding the first
        commit that unbreaks a skip range.

        May add commits for cherry pick. Returns `False` when the bisect is
        finished.
        """
        considered_good = get_good_commits() + get_skip_range_commits(self.patchset)
        commit = git.get_bisect_info(considered_good, "refs/bisect/bad")["bisect_rev"]
        if git.rev_parse(commit) == git.rev_parse("refs/bisect/bad"):
            skip_ranges = []
            good_commits = [git.rev_parse(ref) for ref in get_good_commits()]
            for parent in git.parents(commit):
                if parent in good_commits:
                    print(f"First bad found! Here it is: {commit}")
                    return None
                skip_ranges += skip_ranges_of_commit(parent, self.patchset)
            print(f"cherry-pick {commit} to unbreak {skip_ranges}")
            self.patchset.insert(0, commit)
            return self.get_next()
        return commit

    def _single_run(self, bisect_fun):
        with git.git_checkpoint():
            one_patch_succeeded = False
            for (i, rev) in enumerate(self.patchset):
                success = git.try_cherry_pick_all(rev)
                one_patch_succeeded = success or one_patch_succeeded
                if not one_patch_succeeded:
                    remaining_patchset = self.patchset[i + 1 :]
                    for skip_range in get_skip_ranges(remaining_patchset):
                        if within_range(
                            "HEAD", get_named_skip_refs(skip_range, remaining_patchset)
                        ):
                            print(
                                f"Commit with remaining patches matches known skip range {skip_range}."
                            )
                            return f"skip {skip_range}"
            return bisect_fun()

    def run(self, bisect_fun):
        """Finds the first bad commit"""
        while True:
            next_commit = self.get_next()
            if next_commit is None:
                return
            git.checkout(next_commit)
            result = self._single_run(bisect_fun)
            if result == "bad":
                bisect_bad("HEAD")
                git_bisect.print_bad()
            elif result == "good":
                bisect_good("HEAD")
                git_bisect.print_good()
            elif result.startswith("skip"):
                reason = result[len("skip ") :]
                git_bisect.print_skip(reason)
                named_skip(reason, self.patchset, "HEAD")
            else:
                raise Exception("Unknown bisection result.")
