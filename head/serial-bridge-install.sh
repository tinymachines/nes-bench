#!/usr/bin/env bash
# The UNO's serial port on the LAN, as a systemd unit from this checkout.
# Run on the Pi:  bash head/serial-bridge-install.sh [--port /dev/ttyACM0] [--listen 0.0.0.0:6545]
set -euo pipefail
PORT=/dev/ttyACM0; LISTEN=0.0.0.0:6545
while [ $# -gt 0 ]; do case "$1" in
  --port) PORT="$2"; shift 2 ;; --listen) LISTEN="$2"; shift 2 ;;
  *) echo "unknown argument $1" >&2; exit 2 ;; esac; done
REPO="$(cd "$(dirname "$0")/.." && pwd)"
sudo tee /etc/systemd/system/serial-bridge.service >/dev/null <<UNIT
[Unit]
Description=nes-bench: the UNO serial port on the LAN (socket://<pi>:${LISTEN##*:})
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(id -un)
WorkingDirectory=$REPO
ExecStart=/usr/bin/python3 $REPO/head/serial-bridge.py --port $PORT --baud 115200 --listen $LISTEN
Restart=always
RestartSec=1

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now serial-bridge.service
sudo systemctl restart serial-bridge.service
sleep 1; systemctl --no-pager --lines=3 status serial-bridge.service || true
