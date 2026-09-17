#!/usr/bin/env bash
# The bench's checks with YOUR hand on the front panel, beside the Pi's.
#
#   scripts/hands-manual.sh [--walk] [extra bench-check flags]
#
# Runs tools/bench-check.py --hands manual: the bridge and the scope answer,
# the console's polls come at sixty a second with eight clocks in every one,
# TRIG stops the scope, and then it asks you for the two hands, reset and
# power, and measures each in the poll stream. The register walk is skipped
# by default because it takes a couple of minutes and the Pi's own run
# covers it; --walk puts it back.
#
# Before you start:
#   * the console's POWER switch ON (the relay rests open, so the switch is
#     what powers it: K1's contact sits in parallel with it, J3 brown and red)
#   * a game running that polls the pad
#   * nothing else talking to the scope
# Afterwards leave the switch OFF, which is the state the head's own runs
# assume (scripts/hands-head.sh, or bench-check.py --hands head).
#
# The two addresses are read out of bench.local.md, which git ignores, so
# nothing host-specific reaches a commit. Override with $BRIDGE and $SCOPE.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL="$ROOT/bench.local.md"
WALK="--no-walk"
if [ "${1:-}" = "--walk" ]; then WALK=""; shift; fi

# The bench's own .env first (gitignored; .env.example is the shape), then
# bench.local.md. Anything already in the environment wins over both.
if [ -f "$ROOT/.env" ]; then
  while IFS='=' read -r k v; do
    case "$k" in ''|\#*) continue;; esac
    eval ": \${$k:=\$v}" 2>/dev/null || true
    export "$k" 2>/dev/null || true
  done < "$ROOT/.env"
fi

pick() {   # first address in bench.local.md matching a pattern
  [ -f "$LOCAL" ] || return 0
  grep -oE "$1" "$LOCAL" | head -1
}
BRIDGE="${BRIDGE:-$(pick '[0-9]{1,3}(\.[0-9]{1,3}){3}:6545')}"
# the scope's line carries :5555; the port is cut off, tools take the address
SCOPE="${SCOPE:-$(pick '[0-9]{1,3}(\.[0-9]{1,3}){3}:5555' | cut -d: -f1)}"
if [ -z "${SCOPE:-}" ]; then SCOPE="$(pick '[0-9]{1,3}(\.[0-9]{1,3}){3}')"; fi
if [ -z "${BRIDGE:-}" ]; then
  echo "no bridge address: put it in bench.local.md as host:6545, or set \$BRIDGE" >&2
  exit 1
fi

cat <<'SAY'

  The console's POWER switch should be ON and a game running.
  You will be asked to hold RESET for two full seconds, then to throw
  POWER off, count three, and back on. Each has a listening window and
  the prompt says how long.

SAY
printf '  bridge %s, scope %s\n' "$BRIDGE" "${SCOPE:-none}"

set -x
python3 "$ROOT/tools/bench-check.py" --bridge "$BRIDGE" ${SCOPE:+--scope "$SCOPE"} \
  --hands manual $WALK "$@"
