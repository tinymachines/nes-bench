#!/usr/bin/env bash
# post-commit: rebuild the drawing packages and hold them to what built
# them. Install with tools/install-hooks.sh; the hook in .git/hooks is a
# symlink to this file, so this is the copy to read and to change.
#
# WHY A HOOK AT ALL. The site copies the package PDFs out of this
# working directory byte for byte and never builds them, because
# docs/package/ is gitignored and a fresh checkout has none. Their pull
# refuses when a package's record names a commit that is not the
# checkout's head, which is every commit until somebody rebuilds. The
# README gives the order to do it by hand; this removes the step where
# a person has to remember.
#
# IT CANNOT BLOCK A COMMIT AND DOES NOT TRY. git ignores a post-commit
# hook's exit status, and the commit already exists by the time this
# runs. So this reports, and a red line here means run the rebuild
# again or fix what it names; it never rewrites or amends anything,
# because a hook that edits history behind somebody is worse than a
# stale PDF.
#
# MEASURED 2026-09-23: a full rebuild of all three packages is about
# 7 seconds. That is the cost per commit, paid so the roof's deploy
# does not fail on a window nobody can see.
set -u

top=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$top" || exit 0

# During a rebase or a merge, HEAD churns once per commit and only the
# state at the end matters. Twenty commits replayed would cost twenty
# rebuilds and throw nineteen of them away, so this says what it is
# skipping rather than doing it or going quiet.
gitdir=$(git rev-parse --git-dir)
if [ -d "$gitdir/rebase-merge" ] || [ -d "$gitdir/rebase-apply" ] || [ -f "$gitdir/MERGE_HEAD" ]; then
  echo "post-commit: rebase or merge in progress, drawing packages left stale."
  echo "             run 'python3 tools/make-package.py' when it finishes."
  exit 0
fi

head=$(git rev-parse --short HEAD)
echo "post-commit: rebuilding the drawing packages at $head (about 7 s)..."

if ! out=$(python3 tools/make-package.py 2>&1); then
  # The line that says WHY is the last one; everything above it is the
  # traceback that led there. Printing twelve lines put the answer at
  # the bottom of eleven lines of noise, at the bottom of a commit,
  # which is where nobody reads.
  echo "post-commit: THE BUILD REFUSED, so the packages are stale until this is fixed:"
  echo "  $(echo "$out" | tail -1)"
  echo "  run 'python3 tools/make-package.py' to see the whole of it."
  exit 0
fi

# EVERY check, not the ones I would have picked. On 2026-09-23 a part
# came off the pad-ble sheets, docs/parts.md is generated from those
# sheets, and the four gates I ran by hand before pushing did not
# include parts.py --check. The site's pull found it, which is the
# wrong end of the rope. check-all.sh is the whole set and costs about
# three seconds, so there is no subset to choose any more.
if ! out=$(tools/check-all.sh 2>&1); then
  echo "post-commit: CHECKS DISAGREE, and the commit is already made:"
  echo "$out" | grep -v '^  ok ' | tail -8
  exit 0
fi

echo "post-commit: $(echo "$out" | tail -1)"
