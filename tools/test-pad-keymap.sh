#!/usr/bin/env bash
# The BLE pad adapter's key mapping and HID report descriptor, natively:
# tools/test-pad-keymap.cpp against firmware/pad-ble/keymap.h. The
# descriptor is parsed the way a host parses it and compared with what
# the code actually writes, so the two cannot drift apart silently.
# MUTATE=1 builds the header's two planted bugs and must fail.
#   tools/test-pad-keymap.sh
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
out=$(mktemp)
flags=""
[ "${MUTATE:-0}" = 1 ] && flags="-DKEYMAP_MUTATE"
g++ -std=c++17 -O2 -Wall $flags -o "$out" "$HERE/test-pad-keymap.cpp"
set +e; "$out" "$@"; rc=$?; set -e
rm -f "$out"
exit $rc
