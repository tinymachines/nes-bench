#!/usr/bin/env python3
"""The board map projected onto the eye's close-ups: every hole ringed,
every fifth column numbered, every chip pin named, the rail rows in red
(+5V) and blue (GND), so a wire's end is read beside its column number
on the sharp zoomed frame rather than on the whole-board frame. This is
the instrument the QA passes read with.

  python3 tools/view-rings.py captures/views-<stamp> u3-top,u2-top [DX,DY]
  python3 tools/view-rings.py captures/pose10 u3r,u1one      # by-hand grabs: the
                                                             # aim is read off the .toml

MEASURED 2026-09-13: a zoom-Z crop is centred at x = 960 + pan/36000*960*(1-100/Z),
y = 540 - tilt/36000*540*(1-100/Z) in the zoom-100 frame, scale Z/100. With the
rig's frame_rotate the map is turned back into the camera's frame first.
Output: <scratchpad or cwd>/rings-<name>.png.

What it cannot do, learned 2026-09-15: a Dupont housing hides which of its
positions carries a pin, and a raised end reads outward from the frame's
centre by height/142 mm per pixel of offset (the lens is about 142 mm over
the board), so a housing seated across two columns is settled by a meter or
the side eye, not from above."""
import json, sys
from pathlib import Path
sys.path.insert(0, 'tools')
from loadmod import load
from PIL import Image, ImageDraw, ImageFont
bo = load('tools/board-overlay.py')

import os
S = Path(os.environ.get('RINGS_OUT', '.'))
m = json.load(open('docs/board-map.json'))
boards = {name: bo.Board(b) for name, b in m['boards'].items() if b.get('rows')}
views = json.load(open('docs/eye-views.json'))['views']
vdir = Path(sys.argv[1])
names = sys.argv[2].split(',')
shift = [int(v) for v in sys.argv[3].split(',')] if len(sys.argv) > 3 else [0, 0]
font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 22)

pins = {}
for chip, c in m['chips'].items():
    for p in range(1, c['pins'] + 1):
        col, side, (x, y) = bo.pin_hole(boards[c['board']], c, p)
        pins[(chip, p)] = (c['board'], col, side)
for part, c in m.get('parts', {}).items():
    for p in range(1, c['pins'] + 1):
        col, side, (x, y) = bo.part_hole(boards[c['board']], c, p)
        pins[(part, p)] = (c['board'], col, side)

for name in names:
    v = views.get(name)
    if v is None:
        v = {}
        for line in (vdir / f'{name}.toml').read_text().splitlines():
            for k in ('zoom', 'pan', 'tilt'):
                if line.startswith(f'{k}_absolute ='):
                    v[k] = int(line.split('=')[1].split('#')[0])
    Z = v['zoom']
    cx = 960 + v['pan'] / 36000 * 960 * (1 - 100 / Z) + shift[0]
    cy = 540 - v['tilt'] / 36000 * 540 * (1 - 100 / Z) + shift[1]
    s = Z / 100
    im = Image.open(vdir / f'{name}.jpg').convert('RGB')
    d = ImageDraw.Draw(im)
    rot = m.get('frame_rotate', 0)
    def P(x, y):
        if rot == -90:
            x, y = y, 1080 - x  # map (turned frame) back to the camera's frame
        return ((x - cx) * s + 960, (y - cy) * s + 540)
    for bname, board in boards.items():
        for col in range(1, int(board.anchors[0, 0]) + 1):
            y = board.y(col)
            for side in ('middle', 'rails'):
                for i in range(5):
                    x = board.x(side, i, y)
                    u, w = P(x, y)
                    if -20 < u < 1940 and -20 < w < 1100:
                        d.ellipse([u - 9, w - 9, u + 9, w + 9], outline=(255, 0, 0) if col % 5 == 0 else (0, 200, 255), width=2)
                # column number beside the outermost hole
                x = board.x(side, 0 if side == 'middle' else 4, y)
                u, w = P(x, y)
                if -20 < u < 1940 and -20 < w < 1100:
                    d.text((u - 60 if side == 'middle' else u + 14, w - 12), str(col), fill=(255, 0, 0), font=font)
            for rail in ('GND', '+5V'):
                u, w = P(board.rail_x(rail, y), y)
                if -20 < u < 1940 and -20 < w < 1100:
                    d.ellipse([u - 9, w - 9, u + 9, w + 9], outline=(0, 0, 255) if rail == 'GND' else (255, 0, 0), width=2)
                    if rail == '+5V':
                        d.text((u - 10, w - 34), str(col), fill=(255, 0, 0), font=font)
    for (chip, p), (bname, col, side) in pins.items():
        board = boards[bname]
        y = board.y(col)
        x = board.x(side, 0 if side == 'middle' else 4, y)
        u, w = P(x, y)
        if -20 < u < 1940 and -20 < w < 1100:
            d.text((u - 130 if side == 'middle' else u + 50, w - 12), f'{chip}-{p}', fill=(0, 120, 0), font=font)
    out = S / f'rings-{name}.png'
    im.save(out)
    print('wrote', out, 'centre', round(cx), round(cy))
