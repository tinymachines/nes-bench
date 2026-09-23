#!/usr/bin/env bash
# Install this repository's git hooks, which are symlinks into tools/ so
# the tracked file is the one that runs and there is no second copy to
# drift.
#
#   tools/install-hooks.sh          # install
#   tools/install-hooks.sh --check  # say what is installed, change nothing
#
# A hook is NOT installed by cloning: .git/hooks is not part of a
# checkout, and this does not set core.hooksPath, which would silently
# disable every hook already in .git/hooks. So a fresh clone has no
# hooks until somebody runs this on purpose, which is the right way
# round for something that runs code on every commit.
#
# It refuses to overwrite a hook it did not write. A hook somebody else
# put there is theirs, and clobbering it is the kind of thing that is
# discovered weeks later.
set -eu

top=$(git rev-parse --show-toplevel)
cd "$top"
check=${1:-}

for hook in post-commit; do
  src="tools/$hook-hook.sh"
  dst=".git/hooks/$hook"
  want="../../$src"
  [ -f "$src" ] || { echo "install-hooks: $src is missing"; exit 1; }
  chmod +x "$src"

  if [ "$check" = "--check" ]; then
    if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$want" ]; then
      echo "install-hooks: $hook -> $src"
    elif [ -e "$dst" ]; then
      echo "install-hooks: $hook is installed but is NOT this repository's ($(readlink "$dst" 2>/dev/null || echo 'a plain file'))"
    else
      echo "install-hooks: $hook is not installed"
    fi
    continue
  fi

  if [ -e "$dst" ] && ! { [ -L "$dst" ] && [ "$(readlink "$dst")" = "$want" ]; }; then
    echo "install-hooks: $dst already exists and is not ours; leaving it alone."
    echo "               move it aside first if you want this one."
    exit 1
  fi
  ln -sfn "$want" "$dst"
  echo "install-hooks: $hook -> $src"
done
