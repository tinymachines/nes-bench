#!/usr/bin/env bash
# The bench's two eyes on a timer: one frame each, filed by the day.
#
#   scripts/grab.sh board            # the BRIO over the breadboard
#   scripts/grab.sh screen           # the console's picture, off the grabber
#   scripts/grab.sh side             # the second eye: the QuickCam low across the board
#   scripts/grab.sh all              # all three, board first
#
# Runs ON THE PI (the cameras are on its hub). Writes
#   $CAPTURES/YYYY/MM/DD/<YYYYMMDD>T<HHMMSS>_<TYPE>.jpg
# with CAPTURES defaulting to ~/captures, the stamp in the zone TZ names
# (the Pi's own if unset; the log line carries the offset), and one line
# per frame to $CAPTURES/grab.log. The cron line scripts/install-grab-cron.sh installs
# calls this every five minutes. Every device is named by its stable
# /dev/v4l/by-id path, because the /dev/videoN numbers move whenever a
# camera is plugged in.
#
# The board frame is taken the way tools/eye.py's `board` preset takes it
# (MEASURED 2026-09-13, re-swept in the fixed mount: focus 20, manual exposure 333 at gain 0, auto
# white balance, 1080p MJPG, a dozen frames skipped for the sensor to
# settle); EYE_PRESET=column zooms to the chip column (160, one degree of
# pan) and EYE_PRESET=chips to one chip (300). The screen frame is the
# grabber's fifth frame of an NTSC 720x480 stream, so the first frames'
# sync settle is not the one kept.
#
# One lock for both cameras: a hand-run eye.py or eyes.py that lands on
# the same second waits for the cron's frame instead of both failing with
# the device busy; a wait longer than 50 s gives up and says so.
set -u
TYPE="${1:-all}"
CAPTURES="${CAPTURES:-$HOME/captures}"
BRIO="/dev/v4l/by-id/usb-046d_Logitech_BRIO_1C8D6975-video-index0"
GRABBER="/dev/v4l/by-id/usb-1b80_Roxio_Video_Capture_USB_11111111111111111111-video-index0"
SIDE="/dev/v4l/by-id/usb-046d_0990_08DF0A45-video-index0"   # QuickCam Pro 9000, added 2026-09-13
EYE_PRESET="${EYE_PRESET:-board}"
# The zone the frames are stamped in: TZ if set, else what the cron
# installer recorded in $CAPTURES/.tz, else the Pi's own clock.
if [ -z "${TZ:-}" ] && [ -r "$CAPTURES/.tz" ]; then export TZ="$(cat "$CAPTURES/.tz")"; fi

case "$EYE_PRESET" in
  board)  ZOOM=100; PAN=0 ;;
  column) ZOOM=160; PAN=3600 ;;
  chips)  ZOOM=300; PAN=0 ;;
  *) echo "grab.sh: EYE_PRESET must be board, column or chips, not $EYE_PRESET" >&2; exit 2 ;;
esac

now=$(date +%Y%m%dT%H%M%S)
day="$CAPTURES/$(date +%Y/%m/%d)"
mkdir -p "$day"
log="$CAPTURES/grab.log"

note() { echo "$(date +%Y-%m-%dT%H:%M:%S%z) $*" | tee -a "$log"; }

grab_board() {
  local out="$day/${now}_board.jpg"
  if [ ! -e "$BRIO" ]; then note "board: no camera at $BRIO"; return 1; fi
  v4l2-ctl -d "$BRIO" --set-ctrl=focus_automatic_continuous=0,exposure_dynamic_framerate=0 >/dev/null 2>&1
  v4l2-ctl -d "$BRIO" --set-ctrl=auto_exposure=1 >/dev/null 2>&1
  v4l2-ctl -d "$BRIO" --set-ctrl=exposure_time_absolute=333,gain=0 >/dev/null 2>&1
  v4l2-ctl -d "$BRIO" --set-ctrl=white_balance_automatic=1,power_line_frequency=2 >/dev/null 2>&1
  v4l2-ctl -d "$BRIO" --set-ctrl=focus_absolute=20,zoom_absolute=$ZOOM,pan_absolute=$PAN,tilt_absolute=0 >/dev/null 2>&1
  v4l2-ctl -d "$BRIO" --set-fmt-video=width=1920,height=1080,pixelformat=MJPG >/dev/null 2>&1
  sleep 0.4
  if v4l2-ctl -d "$BRIO" --stream-mmap --stream-skip=12 --stream-count=1 --stream-to="$out" >/dev/null 2>&1 \
     && [ -s "$out" ]; then
    note "board: $out ($(stat -c %s "$out") bytes, preset $EYE_PRESET)"
  else
    rm -f "$out"; note "board: the BRIO gave no frame"; return 1
  fi
}

grab_screen() {
  local out="$day/${now}_screen.jpg"
  if [ ! -e "$GRABBER" ]; then note "screen: no grabber at $GRABBER"; return 1; fi
  v4l2-ctl -d "$GRABBER" --set-input=0 --set-standard=ntsc >/dev/null 2>&1
  if timeout 40 ffmpeg -loglevel error -y -f v4l2 -standard NTSC -video_size 720x480 -i "$GRABBER" \
       -frames:v 5 -update 1 -q:v 2 "$out" 2>>"$log" && [ -s "$out" ]; then
    note "screen: $out ($(stat -c %s "$out") bytes)"
  else
    rm -f "$out"; note "screen: the grabber gave no frame"; return 1
  fi
}

grab_side() {
  local out="$day/${now}_side.jpg"
  if [ ! -e "$SIDE" ]; then note "side: no camera at $SIDE"; return 1; fi
  v4l2-ctl -d "$SIDE" --set-fmt-video=width=1600,height=1200,pixelformat=MJPG >/dev/null 2>&1
  sleep 0.4
  if v4l2-ctl -d "$SIDE" --stream-mmap --stream-skip=15 --stream-count=1 --stream-to="$out" >/dev/null 2>&1 \
     && [ -s "$out" ]; then
    note "side: $out ($(stat -c %s "$out") bytes)"
  else
    rm -f "$out"; note "side: the QuickCam gave no frame"; return 1
  fi
}

exec 9>"$CAPTURES/.grab.lock"
if ! flock -w 50 9; then note "$TYPE: another grab held the cameras for 50 s; skipped"; exit 1; fi

rc=0
case "$TYPE" in
  board)  grab_board || rc=1 ;;
  screen) grab_screen || rc=1 ;;
  side)   grab_side || rc=1 ;;
  all)    grab_board || rc=1; grab_screen || rc=1; grab_side || rc=1 ;;
  *) echo "grab.sh: board, screen, side or all, not $TYPE" >&2; exit 2 ;;
esac
exit $rc
