#!/usr/bin/env bash
# The UNO's packed AT schedule, natively: tools/test-uno-schedule.cpp
# against the protocol's absolute latches, over random schedules and,
# if named, a real b3.py record, fed whole and streamed through a small
# ring. MUTATE=1 builds the mutation (a filler that sets the byte to zero)
# and MUTATE_RING=1 the ring's (a cursor that wraps a slot short); each
# must fail.
#   tools/test-uno-schedule.sh [record.txt]
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
out=$(mktemp)
flags=""
[ "${MUTATE:-0}" = 1 ] && flags="-DSCHEDULE_MUTATE"
[ "${MUTATE_RING:-0}" = 1 ] && flags="$flags -DSCHEDULE_MUTATE_RING"
g++ -std=c++17 -O2 -Wall $flags -o "$out" "$HERE/test-uno-schedule.cpp"
set +e; "$out" "$@"; rc=$?; set -e
rm -f "$out"
exit $rc
