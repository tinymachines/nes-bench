#!/usr/bin/env python3
"""Eyes versus scope: the grabber's picture against the family's own
decode of the same composite signal.

  python3 tools/eyes.py pair --scope <ip> --pi <host> <name> [--frames 8]
  python3 tools/eyes.py compare <name> [--ntsc-crt ../ntsc-crt]

`pair` takes both at once: the scope (CH3, the composite) is set up as
ntsc-crt's scope-capture.py sets it (12 Mpt, 5 ms/div, its setup saved
and restored), the Pi's grabber (/dev/video2, the Roxio) is asked for
`--frames` frames through ffmpeg, and the scope is STOPped the moment
those frames are in, so its record's last 240 ms end within a fraction
of a second of the last grabber frame. A static screen (a title) makes
the two the same picture; a running game makes them a second apart,
which the report cannot tell from a decoding difference. Written to
captures/<name>.u8 + .toml (the scope record, the rate the scope
reports) and captures/<name>-grabber.yuv + .jpg (the grabber's frames).
captures/ is ignored by git.

`compare` decodes the scope record with ntsc-crt's recover-real (--nes:
the NES profile, the transcribed table's own levels), takes the last
grabber frame's first field (the console is 240p: every field is the
whole picture), puts both on the console's own 256 x 240 pixel grid,
finds the grabber's horizontal window and any vertical offset by
correlation rather than by assumption, and reports: the mean absolute
difference per channel, the agreement of flat regions (blocks where
both pictures are flat, so chroma filtering at edges does not count),
the hue difference on saturated pixels, and the ten flat blocks that
disagree most, by console coordinates. Writes captures/<name>-compare.png
(decoder, grabber, difference) and captures/<name>-compare.json.

The decoder side is the measurement; the grabber is a TV chip's opinion
of the same signal. Where they agree, both are probably right; where
they differ on a flat colour, one of them is wrong, and the JSON says
which colour and where, so the question can be taken to the console.
"""
import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
CAPS = ROOT / "captures"
PORT = 5555
CHUNK = 250_000
GRAB_W, GRAB_H = 720, 480
NES_W, NES_H = 256, 240

# The grabber samples the line at 13.5 MHz (720 samples across the active
# line). The console's dot clock is 1.5 times the colour subcarrier,
# 5.369318 MHz, so one console pixel is 186.24 ns and covers 2.5142
# grabber samples; the 256 pixels of a line cover 643.6 of the 720.
NES_DOT_HZ = 315.0e6 / 88.0 * 1.5
GRAB_SAMPLES_PER_NES_PX = 13.5e6 / NES_DOT_HZ


# ------------------------------------------------------------- the scope
class Scope:
    def __init__(self, host):
        self.s = socket.create_connection((host, PORT), timeout=5)
        self.s.settimeout(15)

    def cmd(self, c):
        self.s.sendall(c.encode() + b"\n")

    def ask(self, c):
        self.cmd(c)
        out = b""
        while not out.endswith(b"\n"):
            out += self.s.recv(4096)
        return out.decode().strip()

    def ask_block(self, c):
        self.cmd(c)
        buf = b""
        while len(buf) < 11:
            buf += self.s.recv(4096)
        assert buf[0:1] == b"#", f"not a TMC block: {buf[:16]!r}"
        ndig = int(buf[1:2])
        length = int(buf[2:2 + ndig])
        need = 2 + ndig + length + 1
        while len(buf) < need:
            buf += self.s.recv(65536)
        return buf[2 + ndig:2 + ndig + length]


def pair(a):
    CAPS.mkdir(exist_ok=True)
    ch, scale, offset = 3, 0.2, -0.5
    sc = Scope(a.scope)
    idn = sc.ask("*IDN?")
    print(f"scope: {idn}")
    setup = sc.ask_block(":SYSTem:SETup?")
    print(f"  setup held ({len(setup)} bytes); it will be restored")
    for c in [":STOP", *[f":CHANnel{c}:DISPlay OFF" for c in (1, 2, 3, 4) if c != ch],
              f":CHANnel{ch}:DISPlay ON", f":CHANnel{ch}:PROBe 1", f":CHANnel{ch}:COUPling DC",
              f":CHANnel{ch}:BWLimit OFF", f":CHANnel{ch}:SCALe {scale}", f":CHANnel{ch}:OFFSet {offset}",
              ":ACQuire:TYPE NORMal", ":TIMebase:MAIN:SCALe 0.005", ":TRIGger:SWEep AUTO"]:
        sc.cmd(c)
        time.sleep(0.08)
    sc.cmd(":RUN")
    time.sleep(0.5)
    sc.cmd(":ACQuire:MDEPth 12000000")
    time.sleep(0.5)
    got = sc.ask(":ACQuire:MDEPth?")
    assert got.strip() == "12000000", f"memory depth did not take: {got!r}"
    time.sleep(1.5)
    # The grabber, then STOP the scope the moment the frames are in.
    yuv, jpg = f"/tmp/{a.name}-grabber.yuv", f"/tmp/{a.name}-grabber.jpg"
    cmd = (f"v4l2-ctl -d {a.device} --set-input=0 --set-standard=ntsc >/dev/null 2>&1; "
           f"ffmpeg -loglevel error -y -f v4l2 -standard NTSC -video_size {GRAB_W}x{GRAB_H} -i {a.device} "
           f"-map 0:v -frames:v {a.frames} -f rawvideo -pix_fmt yuyv422 {yuv} "
           f"-map 0:v -frames:v {a.frames} -update 1 {jpg}")
    t0 = time.time()
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", a.pi, cmd], capture_output=True, text=True)
    t_grab = time.time()
    sc.cmd(":STOP")
    t_stop = time.time()
    if r.returncode != 0:
        print(r.stderr)
        sys.exit("the grabber did not deliver frames")
    print(f"grabber: {a.frames} frames in {t_grab - t0:.2f} s; scope stopped {t_stop - t_grab:.3f} s after")
    time.sleep(0.3)
    srate = float(sc.ask(":ACQuire:SRATe?"))
    mdepth = int(float(sc.ask(":ACQuire:MDEPth?")))
    print(f"scope: {mdepth} points at {srate:.0f} Sa/s ({mdepth / srate * 1e3:.0f} ms)")
    sc.cmd(f":WAVeform:SOURce CHANnel{ch}")
    sc.cmd(":WAVeform:MODE RAW")
    sc.cmd(":WAVeform:FORMat BYTE")
    data = bytearray()
    for start in range(1, mdepth + 1, CHUNK):
        stop = min(start + CHUNK - 1, mdepth)
        sc.cmd(f":WAVeform:STARt {start}")
        sc.cmd(f":WAVeform:STOP {stop}")
        data += sc.ask_block(":WAVeform:DATA?")
        print(f"\r  read {len(data)}/{mdepth}", end="", flush=True)
    print()
    assert len(data) == mdepth, f"short read: {len(data)} of {mdepth}"
    lo, hi = min(data), max(data)
    if hi - lo < 30:
        sys.exit("the scope record is nearly flat: is the composite on CH3?")
    (CAPS / f"{a.name}.u8").write_bytes(bytes(data))
    (CAPS / f"{a.name}.toml").write_text(
        f'file = "{a.name}.u8"\nformat = "u8"\nrate_hz = {srate:.1f}\n'
        f'# captured {time.strftime("%Y-%m-%d %H:%M")} by tools/eyes.py pair: CH{ch} DC, '
        f'{scale * 1000:.0f} mV/div, {offset * 1000:.0f} mV offset, 12 Mpt, 5 ms/div; '
        f'the grabber frames ended {t_stop - t_grab:.3f} s before STOP\n')
    sc.s.sendall(b":SYSTem:SETup " + f"#9{len(setup):09d}".encode() + setup + b"\n")
    time.sleep(2.0)
    sc.cmd(":RUN")
    print("scope: setup restored and running")
    for f in (yuv, jpg):
        subprocess.run(["scp", "-q", "-o", "BatchMode=yes", f"{a.pi}:{f}", str(CAPS / Path(f).name)], check=True)
    print(f"wrote captures/{a.name}.u8, .toml, -grabber.yuv, -grabber.jpg")
    return 0


# ----------------------------------------------------------- the pictures
def yuyv_field_rgb(raw, frame=-1):
    """The first field of one 720x480 YUYV frame as float RGB (240 x 720 x 3)."""
    fs = GRAB_W * GRAB_H * 2
    n = len(raw) // fs
    k = n - 1 if frame < 0 else frame
    f = np.frombuffer(raw[k * fs:(k + 1) * fs], dtype=np.uint8).reshape(GRAB_H, GRAB_W * 2).astype(np.float64)
    f = f[0::2]                                   # the first field
    y = f[:, 0::2]
    u = np.repeat(f[:, 1::4], 2, axis=1)
    v = np.repeat(f[:, 3::4], 2, axis=1)
    y, u, v = 1.164 * (y - 16), u - 128, v - 128   # BT.601 limited range, as the grabber labels it
    r = y + 1.596 * v
    g = y - 0.392 * u - 0.813 * v
    b = y + 2.017 * u
    return np.clip(np.stack([r, g, b], axis=-1), 0, 255), n


def resample_columns(img, x0, step, n):
    """n columns starting at x0, each the mean of the samples it covers."""
    out = np.zeros((img.shape[0], n, img.shape[2]))
    for i in range(n):
        a, b = x0 + i * step, x0 + (i + 1) * step
        ia, ib = int(np.floor(a)), int(np.ceil(b))
        ia, ib = max(ia, 0), min(ib, img.shape[1])
        if ib <= ia:
            continue
        out[:, i] = img[:, ia:ib].mean(axis=1)
    return out


def luma(img):
    return 0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]


def corr(a, b):
    a, b = a - a.mean(), b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d else 0.0


def align(dec, grab):
    """dec: 240 x 256 x 3 on the console grid. grab: 240 x 720 x 3 samples.
    Finds x0 (where console pixel 0 starts in the grabber's line) and
    dy (grabber rows relative to decoder rows) by luma correlation."""
    step = GRAB_SAMPLES_PER_NES_PX
    pd = luma(dec).mean(axis=0)
    best = (-2.0, 0.0)
    for x0 in np.arange(0.0, GRAB_W - NES_W * step, 0.5):
        pg = luma(resample_columns(grab, x0, step, NES_W)).mean(axis=0)
        c = corr(pd, pg)
        if c > best[0]:
            best = (c, float(x0))
    x0 = best[1]
    g = resample_columns(grab, x0, step, NES_W)
    rd, rg = luma(dec).mean(axis=1), luma(g).mean(axis=1)
    bestdy = (-2.0, 0)
    for dy in range(-12, 13):
        if dy >= 0:
            c = corr(rd[:NES_H - dy], rg[dy:])
        else:
            c = corr(rd[-dy:], rg[:NES_H + dy])
        if c > bestdy[0]:
            bestdy = (c, dy)
    dy = bestdy[1]
    if dy >= 0:
        g2 = np.zeros_like(g); g2[:NES_H - dy] = g[dy:]
    else:
        g2 = np.zeros_like(g); g2[-dy:] = g[:NES_H + dy]
    return g2, {"x0_samples": x0, "x_corr": best[0], "dy_rows": dy, "y_corr": bestdy[0]}


def hue_sat(img):
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    mx, mn = img.max(axis=-1), img.min(axis=-1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    h = np.degrees(np.arctan2(np.sqrt(3) * (g - b), 2 * r - g - b)) % 360
    return h, sat


def compare(a):
    name = a.name
    u8, toml = CAPS / f"{name}.u8", CAPS / f"{name}.toml"
    yuv = CAPS / f"{name}-grabber.yuv"
    for p in (u8, toml, yuv):
        if not p.exists():
            sys.exit(f"{p} is missing: run `eyes.py pair` first")
    rate = None
    for line in toml.read_text().splitlines():
        if line.startswith("rate_hz"):
            rate = float(line.split("=")[1])
    assert rate, "no rate_hz in the toml"
    crt = Path(a.ntsc_crt).resolve()
    rec = crt / "target/release/examples/recover-real"
    if not rec.exists():
        sys.exit(f"{rec} is not built: cargo build --release -p ntsc-source-cap --example recover-real (in {crt})")
    r = subprocess.run([str(rec), str(u8), "u8", f"{rate:.0f}", "--nes"], capture_output=True, text=True, cwd=crt)
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        sys.exit("recover-real failed")
    lines = [l for l in r.stdout.splitlines() if l.startswith(("auto-level", "recovered"))]
    print("\n".join("decoder: " + l for l in lines))
    ppm = crt / "goldens" / "real-capture.ppm"
    dec_full = np.asarray(Image.open(ppm).convert("RGB")).astype(np.float64)   # 240 x 2048 x 3
    dec = dec_full.reshape(NES_H, NES_W, dec_full.shape[1] // NES_W, 3).mean(axis=2)
    Image.fromarray(dec.astype(np.uint8)).resize((NES_W * 3, NES_H * 3), Image.NEAREST).save(CAPS / f"{name}-decoded.png")

    raw = yuv.read_bytes()
    grab_full, nframes = yuyv_field_rgb(raw)
    grab, geo = align(dec, grab_full)
    Image.fromarray(grab.astype(np.uint8)).resize((NES_W * 3, NES_H * 3), Image.NEAREST).save(CAPS / f"{name}-grabber-grid.png")
    print(f"grabber: {nframes} frames; console pixel 0 at sample {geo['x0_samples']:.1f} of 720 "
          f"(corr {geo['x_corr']:.3f}); rows offset {geo['dy_rows']:+d} (corr {geo['y_corr']:.3f})")

    # Whole-picture differences, then flat blocks, then hue on saturated pixels.
    diff = np.abs(dec - grab)
    mad = diff.reshape(-1, 3).mean(axis=0)
    ly, lg = luma(dec), luma(grab)
    B = 16
    flat, worst = [], []
    for by in range(0, NES_H, B):
        for bx in range(0, NES_W, B):
            d, g = dec[by:by + B, bx:bx + B], grab[by:by + B, bx:bx + B]
            if luma(d).std() < 6 and luma(g).std() < 6:
                md, mg = d.reshape(-1, 3).mean(axis=0), g.reshape(-1, 3).mean(axis=0)
                e = float(np.abs(md - mg).mean())
                flat.append(e)
                worst.append((e, bx, by, [round(v) for v in md], [round(v) for v in mg]))
    worst.sort(reverse=True)
    hd, sd = hue_sat(dec); hg, sg = hue_sat(grab)
    satmask = (sd > 0.35) & (sg > 0.35) & (ly > 40) & (lg > 40)
    if satmask.any():
        dh = (hd[satmask] - hg[satmask] + 180) % 360 - 180
        hue_mean, hue_med, nsat = float(dh.mean()), float(np.median(dh)), int(satmask.sum())
        sat_ratio = float(np.median(sg[satmask] / np.maximum(sd[satmask], 1e-6)))
    else:
        hue_mean = hue_med = sat_ratio = float("nan"); nsat = 0
    report = {
        "name": name, "grabber_frames": nframes, "scope_rate_hz": rate,
        "geometry": geo,
        "mean_abs_diff_rgb": [round(float(v), 2) for v in mad],
        "luma_corr": round(corr(ly, lg), 4),
        "flat_blocks": len(flat), "flat_block_mean_abs_diff": round(float(np.mean(flat)), 2) if flat else None,
        "flat_blocks_worst": [{"x": bx, "y": by, "abs_diff": round(e, 1), "decoder_rgb": md, "grabber_rgb": mg}
                              for e, bx, by, md, mg in worst[:10]],
        "saturated_pixels": nsat, "hue_diff_deg_mean": round(hue_mean, 2), "hue_diff_deg_median": round(hue_med, 2),
        "grabber_over_decoder_saturation": round(sat_ratio, 3),
        "decoder_lines": lines,
    }
    (CAPS / f"{name}-compare.json").write_text(json.dumps(report, indent=1) + "\n")

    # The picture: decoder | grabber | difference (x4), each 2x.
    S = 2
    panel = Image.new("RGB", (NES_W * S * 3 + 40, NES_H * S + 40), "white")
    dr = ImageDraw.Draw(panel)
    for i, (img, label) in enumerate([(dec, "decoder (scope record, ntsc-crt --nes)"),
                                      (grab, "grabber (Roxio, first field)"),
                                      (np.clip(diff * 4, 0, 255), "abs difference x4")]):
        im = Image.fromarray(img.astype(np.uint8)).resize((NES_W * S, NES_H * S), Image.NEAREST)
        panel.paste(im, (10 + i * (NES_W * S + 10), 30))
        dr.text((10 + i * (NES_W * S + 10), 10), label, fill="black")
    dr.text((10, NES_H * S + 32 - 4), f"mean |diff| RGB {[round(float(v),1) for v in mad]}   luma corr {report['luma_corr']}   "
                                        f"flat blocks {len(flat)}: mean |diff| {report['flat_block_mean_abs_diff']}   "
                                        f"hue diff on {nsat} saturated px: median {report['hue_diff_deg_median']} deg", fill="black")
    panel.save(CAPS / f"{name}-compare.png")

    print(f"whole picture: mean |diff| RGB {report['mean_abs_diff_rgb']}, luma correlation {report['luma_corr']}")
    print(f"flat blocks ({len(flat)} of {NES_W // B * (NES_H // B)}): mean |diff| {report['flat_block_mean_abs_diff']}")
    print(f"hue on {nsat} saturated pixels: grabber minus decoder, median {report['hue_diff_deg_median']} deg, "
          f"mean {report['hue_diff_deg_mean']} deg; saturation ratio {report['grabber_over_decoder_saturation']}")
    print("worst flat blocks (console x, y; decoder RGB vs grabber RGB):")
    for w in report["flat_blocks_worst"]:
        print(f"  ({w['x']:3d},{w['y']:3d})  |diff| {w['abs_diff']:5.1f}   {w['decoder_rgb']}  vs  {w['grabber_rgb']}")
    print(f"wrote captures/{name}-compare.png and .json")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pair"); p.add_argument("name"); p.add_argument("--scope", required=True); p.add_argument("--pi", required=True)
    p.add_argument("--frames", type=int, default=8); p.add_argument("--device", default="/dev/video2")
    c = sub.add_parser("compare"); c.add_argument("name"); c.add_argument("--ntsc-crt", default=str(ROOT.parent / "ntsc-crt"))
    a = ap.parse_args()
    return pair(a) if a.cmd == "pair" else compare(a)


if __name__ == "__main__":
    sys.exit(main())
