#!/usr/bin/env python3
"""A keydown logger page, and the server that writes what it sees to a file.

  python3 tools/keydown-log.py [--port 6546] [--log /tmp/keydown.log]

Step 6 of docs/pad-usb-protocol.md: the layer above the kernel. The Pi
already receives the pad's keys as evdev events (step 5, read with
EVIOCGRAB). What a browser emulator sees is one layer up: a DOM
KeyboardEvent with a `code` (the physical key, `KeyX`) and a `key`
(what that key means under the host's layout, `x`). This page logs
both, for every keydown and keyup, and POSTs each line here so the
record lands in a file nothing on the page can lose.

HOW IT IS RUN, and why an X server is in it. A headless browser
receives no physical input at all, and Xvfb reads no evdev, so the
browser has to sit on a display server that libinput feeds. On the Pi:

  sudo Xorg :1 vt8 -nolisten tcp -logfile /tmp/xorg.1.log &
  python3 tools/keydown-log.py &
  DISPLAY=:1 chromium --kiosk --no-first-run http://127.0.0.1:6546/ &

Then press the pad. Every event is one JSON line in the log, and the
page's title is the last code seen, so `xdotool getwindowname` or the
log answers without a screen. Xorg takes EVERY keyboard on the box,
the pad included, which is exactly the point; it also means a real
keyboard on the Pi types into the page while this runs.

WHAT A PASS LOOKS LIKE. A gives code KeyX and key x; B KeyZ/z; Select
ShiftRight/Shift; Start Enter/Enter; the cross ArrowUp, ArrowDown,
ArrowLeft, ArrowRight. `repeat: true` on a keydown is the host's
autorepeat while a button is held, not a second press by the pad: the
adapter sends one report per change (pad-usb.ino), and the page marks
those lines so nobody counts them as presses.

The page is tools/keydown-page.html beside this file, self-contained,
so the same file can be served from anywhere: the public site hosts a
copy at an unlisted path for a phone with the pad on its USB-C port,
which is step 7, and this server is the Pi's route to the same page.
"""
import argparse
import json
import sys
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE_FILE = Path(__file__).resolve().parent / "keydown-page.html"


class Handler(BaseHTTPRequestHandler):
    log_path = None

    def log_message(self, fmt, *args):  # quiet: the record is the log file
        pass

    def do_GET(self):
        body = PAGE_FILE.read_bytes()
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(n)
        try:
            rec = json.loads(raw)
        except ValueError:
            self.send_response(400); self.end_headers(); return
        rec["received"] = time.time()
        line = json.dumps(rec, sort_keys=True)
        with open(self.log_path, "a") as f:
            f.write(line + "\n")
        print(f"{rec.get('kind','?'):4} {rec.get('code','?'):12} key={rec.get('key')!r}"
              f"{'  repeat' if rec.get('repeat') else ''}", flush=True)
        self.send_response(204)
        self.end_headers()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=6546)
    ap.add_argument("--log", default="/tmp/keydown.log")
    a = ap.parse_args()
    Handler.log_path = a.log
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"keydown-log: http://127.0.0.1:{a.port}/  ->  {a.log}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
