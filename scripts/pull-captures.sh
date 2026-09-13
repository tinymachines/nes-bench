#!/usr/bin/env bash
# Bring the Pi's timed frames to the workstation, and say which is newest.
#
#   scripts/pull-captures.sh <pi-host> [days]     # default: today and yesterday
#
# Copies ~/captures/YYYY/MM/DD/ for the last N days into captures/pi/ here
# (git ignores captures/), then prints the newest board and screen frame,
# which is what a QA pass looks at. The host is an argument on purpose:
# the Pi's address lives in bench.local.md, which git ignores.
set -eu
PI="${1:?the Pi, user@host}"
DAYS="${2:-2}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/captures/pi"
mkdir -p "$DEST"
for i in $(seq 0 $((DAYS - 1))); do
  d=$(date -d "-$i day" +%Y/%m/%d)
  mkdir -p "$DEST/$d"
  rsync -aq --ignore-existing "$PI:captures/$d/" "$DEST/$d/" 2>/dev/null || true
done
rsync -aq "$PI:captures/grab.log" "$DEST/grab.log" 2>/dev/null || true
for t in board screen; do
  f=$(find "$DEST" -name "*_$t.jpg" | sort | tail -1)
  echo "$t: ${f:-none}"
done
