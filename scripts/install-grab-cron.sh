#!/usr/bin/env bash
# Put scripts/grab.sh on the Pi's crontab every five minutes, once.
#
#   scripts/install-grab-cron.sh [--tz ZONE]   # on the Pi, in ~/nes-bench
#   scripts/install-grab-cron.sh --remove      # take the line out again
#
# --tz stamps and files the frames in that zone (America/New_York, say)
# when the Pi's own clock is set somewhere else: this Pi came provisioned
# on Europe/London, five hours ahead of the bench, so its first frames
# were filed under an evening that had not happened yet. Without --tz
# the Pi's zone is used and the log says which.
#
# Idempotent: the line is tagged, an existing tag is replaced, not doubled.
# Output goes to ~/captures/grab.log through grab.sh's own log line, so the
# cron line itself discards nothing but ffmpeg's stderr, which grab.sh
# already appends to the same log.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
TAG="# nes-bench grab"
TZ_PREFIX=""
if [ "${1:-}" = "--tz" ]; then
  TZ_PREFIX="TZ=${2:?--tz needs a zone} "
  mkdir -p "${CAPTURES:-$HOME/captures}" && printf '%s\n' "$2" > "${CAPTURES:-$HOME/captures}/.tz"
  shift 2
fi
LINE="*/5 * * * * ${TZ_PREFIX}$HERE/grab.sh all >/dev/null 2>&1 $TAG"
current="$(crontab -l 2>/dev/null | grep -v "$TAG" || true)"
if [ "${1:-}" = "--remove" ]; then
  printf '%s\n' "$current" | crontab -
  echo "removed: $TAG"
else
  { [ -n "$current" ] && printf '%s\n' "$current"; printf '%s\n' "$LINE"; } | crontab -
  echo "installed: $LINE"
fi
crontab -l
