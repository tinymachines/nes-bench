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
# Twice: the USB build (report ID 1, the header's default) and the BLE
# build (ID 0, no Report ID item), since the one header serves both.
rc=0
for id in 1 0; do
  echo "# report ID $id"
  g++ -std=c++17 -O2 -Wall $flags -DPAD_HID_REPORT_ID=$id -o "$out" "$HERE/test-pad-keymap.cpp"
  set +e; "$out" "$@"; r=$?; set -e
  [ $r -ne 0 ] && rc=$r
done
rm -f "$out"
exit $rc
