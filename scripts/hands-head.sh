#!/usr/bin/env bash
# The bench's checks with the PI's hands on reset and power.
#
#   scripts/hands-head.sh [--no-walk] [extra bench-check flags]
#
# Runs tools/bench-check.py --hands head: the bridge and the scope answer,
# the console's polls, the trigger, the fifteen-byte register walk, then a
# reset from GPIO17 through OK1 and a power cycle from GPIO27 through K1,
# each measured in the poll stream.
#
# Before you start: the console's POWER switch OFF. The relay is in parallel
# with it (J3 brown and red), so with the switch on there is nothing for the
# head to switch. The run powers the console itself, waits twelve seconds
# for the game, and puts GPIO27 back as it found it at the end.
#
# Addresses come out of bench.local.md, which git ignores; $BRIDGE and
# $SCOPE override.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL="$ROOT/bench.local.md"
WALK=""
if [ "${1:-}" = "--no-walk" ]; then WALK="--no-walk"; shift; fi

pick() {
  [ -f "$LOCAL" ] || return 0
  grep -oE "$1" "$LOCAL" | head -1
}
BRIDGE="${BRIDGE:-$(pick '[0-9]{1,3}(\.[0-9]{1,3}){3}:6545')}"
SCOPE="${SCOPE:-$(pick '[0-9]{1,3}(\.[0-9]{1,3}){3}:5555' | cut -d: -f1)}"
if [ -z "${SCOPE:-}" ]; then SCOPE="$(pick '[0-9]{1,3}(\.[0-9]{1,3}){3}')"; fi
if [ -z "${BRIDGE:-}" ]; then
  echo "no bridge address: put it in bench.local.md as host:6545, or set \$BRIDGE" >&2
  exit 1
fi
printf '\n  The console POWER switch should be OFF: the Pi powers it through K1.\n'
printf '  bridge %s, scope %s\n\n' "$BRIDGE" "${SCOPE:-none}"
set -x
python3 "$ROOT/tools/bench-check.py" --bridge "$BRIDGE" ${SCOPE:+--scope "$SCOPE"} \
  --hands head $WALK "$@"
