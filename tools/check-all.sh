#!/usr/bin/env bash
# Every check this repository has, in one command.
#
#   tools/check-all.sh
#
# WHY THIS EXISTS. On 2026-09-23 a change removed a part from the
# pad-ble sheets, and docs/parts.md is generated from those sheets. I
# ran four gates before pushing: check-sheets, make-package --check,
# check-pad and test-pad-keymap. The repository has fourteen. The one
# that would have caught it, `parts.py --check`, was not among the four,
# and the site's pull found it instead, which is the wrong end of the
# rope to find it from.
#
# The failure was not forgetting a command; it was choosing a subset by
# hand every time and being right about it most times. So there is no
# subset to choose any more. It costs about three seconds.
#
# A check belongs here if it can answer on a desk, with no bench, no
# console and no instrument. The hardware ones (rig-check, bench-check,
# eye) need the part and are deliberately absent; they are not gates a
# commit can pass or fail.
#
# THIS FILE IS READ BY ANOTHER REPOSITORY. The site's pull runs it in
# this checkout and refuses to copy anything if it exits non-zero; it
# used to name eight of these gates by hand, which was the same
# choose-a-subset habit with somebody else's name on it. So there is
# one list and it is this one. Adding a check here strengthens both
# sides; renaming this file or changing what its exit status means
# breaks a build that is not ours.
set -u
cd "$(git rev-parse --show-toplevel)" || exit 1

fail=0
run() {
  local name=$1; shift
  local out
  if out=$("$@" 2>&1); then
    printf '  ok    %s\n' "$name"
  else
    printf '  FAIL  %s\n' "$name"
    printf '%s\n' "$out" | tail -4 | sed 's/^/          /'
    fail=$((fail + 1))
  fi
}

# The generators: each says whether the file committed here is the one
# it writes now. A stale one means a source changed and its derived
# document did not follow.
for t in breadboard build-guide cheatsheet draw-bench export-netlist \
         lab-notebook make-package parts wiring-diagram; do
  run "$t --check" python3 "tools/$t.py" --check
done

# The schematics' own rule check: a net with one end, a designator used
# twice, a supply pin nobody mentioned. THE --erc IS LOAD BEARING and
# not a verbosity flag: netlist.py returns 1 only when it is given, so
# running it plain adds a check that cannot fail, which is worse than
# not running it. Added 2026-09-23 after the roof's pull turned out to
# be carrying this one gate by hand because this file lacked it.
run "netlist --erc" python3 tools/netlist.py --erc

# The checkers: agreement between things that must say the same, and
# between a document and the thing it describes.
run "check-bringup" python3 tools/check-bringup.py
run "check-pad" python3 tools/check-pad.py
run "check-sheets" python3 tools/check-sheets.py

# The desk tests: firmware logic compiled natively, where the part is
# not needed to know the answer.
run "test-pad-keymap" tools/test-pad-keymap.sh
run "test-uno-schedule" tools/test-uno-schedule.sh

if [ "$fail" -eq 0 ]; then
  echo "check-all: every check agrees"
else
  echo "check-all: $fail check(s) disagree"
fi
exit $((fail > 0))
