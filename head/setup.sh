#!/usr/bin/env bash
# The head on a Raspberry Pi 4 in one command, run on the Pi:
#
#   bash head/setup.sh --bridge /dev/ttyACM0 --baud 115200 --scope <ip> [--runs /home/pi/runs] [--port 6530]
#   bash head/setup.sh --dry-run ...          # print the steps, run none
#
# Installs what headd.py needs (python3-serial; gpiozero comes with
# Raspberry Pi OS), writes a systemd unit that runs the head from this
# checkout as the invoking user, enables it, starts it, and prints its
# status line. The addresses go into the unit on the Pi only: nothing
# here writes them into the repository. Re-run after a git pull to
# restart the service on the new code (the unit is rewritten, the
# service restarted). The unit CONFLICTS with serial-bridge.service: the
# two open the same port, and Linux lets two readers split one port's
# bytes without a word, so starting either stops the other, and
# `systemctl start serial-bridge` is how the bring-up tools get the
# port back. When the head stops, its pins are put back to the levels
# the boot config sets (GPIO17 low, GPIO27 low: reset released, the
# console off) with pinctrl, which leaves a level in place; gpiozero
# would leave them as inputs. --baud is the firmware's: the UNO bridge
# v1b talks at 115200, the ESP32 sheet at 921600 (headd.py's default).
# First real run 2026-09-17, on the UNO.
set -euo pipefail

BRIDGE=""
BAUD=""
SCOPE=""
RUNS="$HOME/runs"
PORT=6530
DRY=0
NO_SCOPE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --bridge) BRIDGE="$2"; shift 2 ;;
    --baud) BAUD="$2"; shift 2 ;;
    --scope) SCOPE="$2"; shift 2 ;;
    --no-scope) NO_SCOPE=1; shift ;;
    --runs) RUNS="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) echo "setup.sh: unknown argument $1" >&2; exit 2 ;;
  esac
done
if [ -z "$BRIDGE" ]; then echo "setup.sh: --bridge <serial device> is required" >&2; exit 2; fi
if [ -z "$SCOPE" ] && [ "$NO_SCOPE" = 0 ]; then echo "setup.sh: --scope <ip> or --no-scope" >&2; exit 2; fi

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
USER_NAME="$(id -un)"
UNIT=/etc/systemd/system/nes-bench-head.service
SCOPE_ARG="--scope $SCOPE"
BAUD_ARG="${BAUD:+--baud $BAUD}"
[ "$NO_SCOPE" = 1 ] && SCOPE_ARG="--no-scope"

run() {
  if [ "$DRY" = 1 ]; then echo "+ $*"; else echo "+ $*"; "$@"; fi
}

echo "== head setup: repo $REPO, user $USER_NAME, bridge $BRIDGE${BAUD:+ at $BAUD}, $SCOPE_ARG, runs $RUNS, UDP $PORT / HTTP $((PORT + 1))"

echo "== 1. packages"
run sudo apt-get install -y python3-serial python3-gpiozero python3-numpy

echo "== 2. the serial device"
if [ "$DRY" = 0 ] && [ ! -e "$BRIDGE" ]; then
  echo "   $BRIDGE is not present; the unit is written anyway and will start when it is (Restart=on-failure)"
fi
run sudo usermod -aG dialout "$USER_NAME"

echo "== 3. the runs directory"
run mkdir -p "$RUNS"

echo "== 4. the unit"
UNIT_TEXT="[Unit]
Description=nes-bench head: the bench under one script
After=network-online.target
Wants=network-online.target
Conflicts=serial-bridge.service

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$REPO
ExecStart=/usr/bin/python3 $REPO/head/headd.py --bridge $BRIDGE $BAUD_ARG $SCOPE_ARG --runs $RUNS --port $PORT
ExecStopPost=/usr/bin/pinctrl set 17 op dl
ExecStopPost=/usr/bin/pinctrl set 27 op dl
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"
if [ "$DRY" = 1 ]; then
  echo "+ write $UNIT:"; printf '%s' "$UNIT_TEXT" | sed 's/^/    /'
else
  printf '%s' "$UNIT_TEXT" | sudo tee "$UNIT" > /dev/null
fi
run sudo systemctl daemon-reload
run sudo systemctl enable nes-bench-head.service
run sudo systemctl restart nes-bench-head.service

echo "== 5. status"
if [ "$DRY" = 0 ]; then
  sleep 3
  sudo systemctl --no-pager --lines=5 status nes-bench-head.service || true
  echo "   from the workstation: python3 tools/bench.py $(hostname -I | awk '{print $1}'):$PORT status"
else
  echo "+ systemctl status nes-bench-head.service"
fi
echo "== done"
