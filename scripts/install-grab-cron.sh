#!/usr/bin/env bash
# Put scripts/grab.sh on the Pi's crontab every five minutes, once.
#
#   scripts/install-grab-cron.sh            # on the Pi, in ~/nes-bench
#   scripts/install-grab-cron.sh --remove   # take the line out again
#
# Idempotent: the line is tagged, an existing tag is replaced, not doubled.
# Output goes to ~/captures/grab.log through grab.sh's own log line, so the
# cron line itself discards nothing but ffmpeg's stderr, which grab.sh
# already appends to the same log.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
TAG="# nes-bench grab"
LINE="*/5 * * * * $HERE/grab.sh all >/dev/null 2>&1 $TAG"
current="$(crontab -l 2>/dev/null | grep -v "$TAG" || true)"
if [ "${1:-}" = "--remove" ]; then
  printf '%s\n' "$current" | crontab -
  echo "removed: $TAG"
else
  { [ -n "$current" ] && printf '%s\n' "$current"; printf '%s\n' "$LINE"; } | crontab -
  echo "installed: $LINE"
fi
crontab -l
