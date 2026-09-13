#!/usr/bin/env python3
"""The bench's eye: the Logitech BRIO on the Pi, aimed at the board.

  python3 tools/eye.py grab NAME [--pi HOST] [--focus N] [--exposure N|auto]
                            [--gain N] [--zoom N] [--pan N] [--tilt N] [--wb auto|K]
                            [--preset board|chips] [--size WxH] [--settle N]
  python3 tools/eye.py sweep NAME [--pi HOST] [--from A --to B --step S]
  python3 tools/eye.py show [--pi HOST]

`grab` applies the settings (every one a UVC control, set by name through
v4l2-ctl on the Pi), streams the camera for `--settle` frames so the
sensor lands on them, keeps the next frame as captures/NAME.jpg and
writes captures/NAME.toml beside it with every control as the camera
reports it back, so a picture always says how it was taken. `sweep`
steps the lens through a range of focus values and scores the sharpness
of the frame's chip column (the variance of a Laplacian over the centre
strip, divided by the mean level squared so a brighter frame does not
score higher), the measurement the default focus came from. `show`
prints the camera's controls as they stand.

MEASURED 2026-09-13, the camera on the arm over the breadboard at
1080p (the Pi's hub is USB 2, so 4K is not on offer): the focus peaks at
25 on the 0..255 scale (0 is far); auto white balance settles near
3300 K under the bench light and reads neutral where a fixed 4500 K reads
warm; a manual exposure of 333 (units of 100 microseconds, a whole
number of 60 Hz mains cycles) at gain 0 holds the level steady, where
the auto exposure follows a hand in the frame. Zoom is the sensor
cropped: 100 is the whole board, 300 fills the frame with one chip's
column, and pan and tilt (units of 1/3600 degree) move the crop.

Presets: `board` (the defaults: whole breadboard, focus 25, auto white
balance, manual exposure 333), `column` (zoom 160, pan one degree right:
the three chips, the ribbon, the jumpers and the rail wires in one
frame, row numbers legible) and `chips` (zoom 300: one chip and its
pins). Pan and tilt step in whole degrees on this camera.
The device is the camera's stable name under /dev/v4l/by-id, because the
/dev/videoN numbers move whenever a camera is plugged in (the BRIO took
four of them and moved the grabber).
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAPS = ROOT / "captures"
DEVICE = "/dev/v4l/by-id/usb-046d_Logitech_BRIO_1C8D6975-video-index0"

PRESETS = {
    "board": dict(focus=25, exposure=333, gain=0, zoom=100, pan=0, tilt=0, wb="auto"),
    "chips": dict(focus=25, exposure=333, gain=0, zoom=300, pan=0, tilt=0, wb="auto"),
    "column": dict(focus=25, exposure=333, gain=0, zoom=160, pan=3600, tilt=0, wb="auto"),
}

CONTROLS = ["brightness", "contrast", "saturation", "white_balance_automatic", "white_balance_temperature",
            "gain", "sharpness", "backlight_compensation", "auto_exposure", "exposure_time_absolute",
            "exposure_dynamic_framerate", "pan_absolute", "tilt_absolute", "focus_absolute",
            "focus_automatic_continuous", "zoom_absolute", "power_line_frequency"]


def ssh(host: str, script: str, timeout: int = 60) -> str:
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes", host, script],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        sys.exit(f"ssh {host}: {r.stderr.strip()[:400]}")
    return r.stdout


def settings_script(a) -> str:
    """The v4l2-ctl lines that put the camera where the arguments say."""
    s = [f"v4l2-ctl -d {DEVICE} --set-ctrl=focus_automatic_continuous=0,exposure_dynamic_framerate=0 >/dev/null 2>&1"]
    if a.exposure == "auto":
        s.append(f"v4l2-ctl -d {DEVICE} --set-ctrl=auto_exposure=3 >/dev/null 2>&1")
    else:
        s.append(f"v4l2-ctl -d {DEVICE} --set-ctrl=auto_exposure=1 >/dev/null 2>&1")
        s.append(f"v4l2-ctl -d {DEVICE} --set-ctrl=exposure_time_absolute={int(a.exposure)},gain={a.gain} >/dev/null 2>&1")
    if a.wb == "auto":
        s.append(f"v4l2-ctl -d {DEVICE} --set-ctrl=white_balance_automatic=1 >/dev/null 2>&1")
    else:
        s.append(f"v4l2-ctl -d {DEVICE} --set-ctrl=white_balance_automatic=0 >/dev/null 2>&1")
        s.append(f"v4l2-ctl -d {DEVICE} --set-ctrl=white_balance_temperature={int(a.wb)} >/dev/null 2>&1")
    s.append(f"v4l2-ctl -d {DEVICE} --set-ctrl=focus_absolute={a.focus},zoom_absolute={a.zoom},pan_absolute={a.pan},tilt_absolute={a.tilt} >/dev/null 2>&1")
    return "\n".join(s)


def grab_script(a, out: str) -> str:
    w, h = a.size.split("x")
    return (f"v4l2-ctl -d {DEVICE} --set-fmt-video=width={w},height={h},pixelformat=MJPG >/dev/null 2>&1\n"
            f"sleep 0.4\n"
            f"v4l2-ctl -d {DEVICE} --stream-mmap --stream-skip={a.settle} --stream-count=1 --stream-to={out} >/dev/null 2>&1\n")


def report_script() -> str:
    names = ",".join(CONTROLS)
    return f"v4l2-ctl -d {DEVICE} --get-ctrl={names} 2>&1; v4l2-ctl -d {DEVICE} --get-fmt-video 2>&1 | grep -E 'Width|Pixel'"


def apply_preset(a):
    p = PRESETS[a.preset]
    for k, v in p.items():
        if getattr(a, k) is None:
            setattr(a, k, v)


def cmd_grab(a):
    apply_preset(a)
    CAPS.mkdir(exist_ok=True)
    remote = f"/tmp/eye-{a.name}.jpg"
    t0 = time.time()
    rep = ssh(a.pi, settings_script(a) + "\n" + grab_script(a, remote) + "\n" + report_script(), timeout=90)
    subprocess.run(["scp", "-q", "-o", "ConnectTimeout=8", f"{a.pi}:{remote}", str(CAPS / f"{a.name}.jpg")], check=True)
    dt = time.time() - t0
    toml = [f'file = "{a.name}.jpg"', f'device = "{DEVICE}"', f'taken = "{time.strftime("%Y-%m-%d %H:%M:%S")}"',
            f'preset = "{a.preset}"', f"# {dt:.1f} s over ssh; the controls as the camera reported them after the frame:"]
    for line in rep.strip().splitlines():
        m = re.match(r"\s*(\w+):\s*(-?\d+)(?:\s*\((.*)\))?", line)
        if m:
            toml.append(f"{m.group(1)} = {m.group(2)}" + (f"  # {m.group(3)}" if m.group(3) else ""))
        elif "Width" in line or "Pixel" in line:
            toml.append("# " + line.strip())
    (CAPS / f"{a.name}.toml").write_text("\n".join(toml) + "\n")
    print(f"wrote captures/{a.name}.jpg and .toml ({dt:.1f} s): preset {a.preset}, focus {a.focus}, exposure {a.exposure}, gain {a.gain}, zoom {a.zoom}, pan {a.pan}, tilt {a.tilt}, wb {a.wb}")


def sharpness(path: Path) -> tuple[float, float]:
    from PIL import Image
    import numpy as np
    im = Image.open(path).convert("L")
    w, h = im.size
    crop = np.asarray(im.crop((w * 0.40, h * 0.20, w * 0.70, h * 0.85)), dtype=float)
    lap = np.abs(4 * crop[1:-1, 1:-1] - crop[:-2, 1:-1] - crop[2:, 1:-1] - crop[1:-1, :-2] - crop[1:-1, 2:])
    mean = max(crop.mean(), 1.0)
    return lap.var() / mean ** 2 * 1e4, mean


def cmd_sweep(a):
    apply_preset(a)
    CAPS.mkdir(exist_ok=True)
    values = list(range(a.from_, a.to + 1, a.step))
    lines = [settings_script(a), "mkdir -p /tmp/eye-sweep"]
    for f in values:
        lines.append(f"v4l2-ctl -d {DEVICE} --set-ctrl=focus_absolute={f} >/dev/null 2>&1; sleep 0.5")
        lines.append(grab_script(a, f"/tmp/eye-sweep/f{f}.jpg"))
    ssh(a.pi, "\n".join(lines), timeout=600)
    local = CAPS / f"{a.name}-sweep"
    local.mkdir(exist_ok=True)
    subprocess.run(["scp", "-q", "-o", "ConnectTimeout=8", f"{a.pi}:/tmp/eye-sweep/*.jpg", str(local)], check=True)
    rows = [(f, *sharpness(local / f"f{f}.jpg")) for f in values]
    best = max(rows, key=lambda r: r[1])
    for f, s, m in rows:
        print(f"focus {f:3d}: sharpness {s:8.2f}  level {m:5.1f}" + ("  <- best" if f == best[0] else ""))
    print(f"best focus {best[0]} (the scene must hold still through the sweep; a hand in it scores as blur)")


def cmd_show(a):
    print(ssh(a.pi, report_script()))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in [("grab", cmd_grab), ("sweep", cmd_sweep), ("show", cmd_show)]:
        c = sub.add_parser(name)
        c.set_defaults(fn=fn)
        c.add_argument("--pi", required=True, help="the Pi, user@host (bench.local.md has the address; never committed)")
        if name != "show":
            c.add_argument("name")
            c.add_argument("--preset", default="board", choices=sorted(PRESETS))
            c.add_argument("--focus", type=int); c.add_argument("--exposure"); c.add_argument("--gain", type=int)
            c.add_argument("--zoom", type=int); c.add_argument("--pan", type=int); c.add_argument("--tilt", type=int)
            c.add_argument("--wb"); c.add_argument("--size", default="1920x1080"); c.add_argument("--settle", type=int, default=12)
        if name == "sweep":
            c.add_argument("--from", dest="from_", type=int, default=10); c.add_argument("--to", type=int, default=60); c.add_argument("--step", type=int, default=5)
    a = p.parse_args()
    if not a.pi:
        sys.exit("--pi user@host is required (the Pi's address lives in bench.local.md, not here)")
    a.fn(a)


if __name__ == "__main__":
    main()
