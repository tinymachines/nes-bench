#!/usr/bin/env python3
"""A drawing frame: border, zone grid, title block, and a place to put a drawing.

Not specific to this bench. It takes a page size and a dict of title
block fields, and gives back a page you can put a schematic, a table or
a list of steps on. `tools/make-package.py` is what drives it here; any
other project should be able to copy this file and its own package.json
and get the same looking document out.

Everything is drawn in CSS pixels at 96 dpi, because that is what SVG's
user unit is and what `rsvg-convert` maps to points at exactly 0.75.
So ANSI B, 17 by 11 inches, is 1632 by 1056 units and comes out of the
PDF as 1224 by 792 points, which is 17 by 11 inches. Nothing is scaled
on the way through and nothing needs a DPI argument.

Class names here are all prefixed `tmf-`. That is not tidiness: CSS
inside an SVG cascades over the whole document, nested SVGs included, so
a schematic that styles `.title` would restyle this frame's title block
the moment it was placed on the page.
"""
import html
import re
from pathlib import Path

# (width, height) in CSS px at 96 dpi, landscape.
PAGES = {
    "ansi-a": (1056, 816),    # 11 x 8.5 in
    "ansi-b": (1632, 1056),   # 17 x 11 in
    "a4": (1123, 794),        # 297 x 210 mm
    "a3": (1587, 1123),       # 420 x 297 mm
}

STYLE = """<style>
 .tmf-rule{fill:none;stroke:#111;stroke-width:1.2}
 .tmf-rule-thick{fill:none;stroke:#111;stroke-width:2.2}
 .tmf-hair{fill:none;stroke:#111;stroke-width:0.8}
 .tmf-zone{font:600 11px ui-monospace,'DejaVu Sans Mono',monospace;fill:#111}
 .tmf-lab{font:600 7.5px ui-monospace,'DejaVu Sans Mono',monospace;fill:#666;letter-spacing:.08em}
 .tmf-val{font:600 12px ui-sans-serif,'DejaVu Sans',sans-serif;fill:#111}
 .tmf-val-big{font:700 19px ui-sans-serif,'DejaVu Sans',sans-serif;fill:#111}
 .tmf-head{font:600 12px ui-sans-serif,'DejaVu Sans',sans-serif;fill:#111}
 .tmf-foot{font:10px ui-monospace,'DejaVu Sans Mono',monospace;fill:#666}
 .tmf-h1{font:700 26px ui-sans-serif,'DejaVu Sans',sans-serif;fill:#111}
 .tmf-h2{font:700 15px ui-sans-serif,'DejaVu Sans',sans-serif;fill:#111}
 .tmf-body{font:13px ui-sans-serif,'DejaVu Sans',sans-serif;fill:#111}
 .tmf-mono{font:12px ui-monospace,'DejaVu Sans Mono',monospace;fill:#111}
 .tmf-th{font:700 11px ui-sans-serif,'DejaVu Sans',sans-serif;fill:#111}
 .tmf-td{font:12px ui-sans-serif,'DejaVu Sans',sans-serif;fill:#111}
 .tmf-tdm{font:12px ui-monospace,'DejaVu Sans Mono',monospace;fill:#111}
 .tmf-band{fill:#f2f2f0}
 .tmf-em{font-weight:700}
</style>"""

MARGIN = 26      # paper edge to the outer rule
ZONE = 20        # width of the zone gutter
TB_W, TB_H = 470, 146   # title block


def esc(s):
    return html.escape(str(s), quote=False)


class Page:
    def __init__(self, meta, size="ansi-b"):
        self.w, self.h = PAGES[size]
        self.meta = meta
        self.o = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                  f'viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}">', STYLE,
                  f'<rect x="0" y="0" width="{self.w}" height="{self.h}" fill="#ffffff"/>']
        # The frame and the title block are computed now and DRAWN LAST,
        # in done(). Content goes on top of whatever is under it, and a
        # placed schematic carries its own white background, so drawing
        # the title block first put it underneath the drawing and hid it.
        # A title block is the one thing on a sheet that is never
        # covered.
        self._geometry()

    def add(self, s):
        self.o.append(s)

    def text(self, x, y, s, cls="tmf-body", anchor="start"):
        self.add(f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}">{esc(s)}</text>')

    # ---------------------------------------------------------- the frame
    def _geometry(self):
        m, z = MARGIN, ZONE
        self._inner = (m + z, m + z, self.w - 2 * (m + z), self.h - 2 * (m + z))

    def _frame(self):
        m, z = MARGIN, ZONE
        self.add(f'<rect class="tmf-rule-thick" x="{m}" y="{m}" width="{self.w-2*m}" height="{self.h-2*m}"/>')
        ix, iy = m + z, m + z
        iw, ih = self.w - 2 * (m + z), self.h - 2 * (m + z)
        self.add(f'<rect class="tmf-rule" x="{ix}" y="{iy}" width="{iw}" height="{ih}"/>')
        # Zone grid: numbers across, letters down, on all four edges, so a
        # note can say "U2 is in C5" and mean it on a printed page.
        cols = 8 if self.w > 1300 else 6
        rows = 4
        for i in range(cols):
            x0 = ix + iw * i / cols
            x1 = ix + iw * (i + 1) / cols
            lab = str(cols - i)
            self.text((x0 + x1) / 2, m + z - 6, lab, "tmf-zone", "middle")
            self.text((x0 + x1) / 2, self.h - m - z + 15, lab, "tmf-zone", "middle")
            if i:
                self.add(f'<line class="tmf-hair" x1="{x0:.1f}" y1="{m}" x2="{x0:.1f}" y2="{iy}"/>')
                self.add(f'<line class="tmf-hair" x1="{x0:.1f}" y1="{self.h-iy}" x2="{x0:.1f}" y2="{self.h-m}"/>')
        for j in range(rows):
            y0 = iy + ih * j / rows
            y1 = iy + ih * (j + 1) / rows
            lab = "ABCD"[j]
            self.text(m + z / 2, (y0 + y1) / 2 + 4, lab, "tmf-zone", "middle")
            self.text(self.w - m - z / 2, (y0 + y1) / 2 + 4, lab, "tmf-zone", "middle")
            if j:
                self.add(f'<line class="tmf-hair" x1="{m}" y1="{y0:.1f}" x2="{ix}" y2="{y0:.1f}"/>')
                self.add(f'<line class="tmf-hair" x1="{self.w-ix}" y1="{y0:.1f}" x2="{self.w-m}" y2="{y0:.1f}"/>')

    def _cell(self, x, y, w, h, label, value, cls="tmf-val"):
        self.add(f'<rect class="tmf-hair" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"/>')
        self.text(x + 6, y + 12, label.upper(), "tmf-lab")
        self.text(x + 6, y + h - 8, value, cls)

    def _titleblock(self):
        ix, iy, iw, ih = self._inner
        x = ix + iw - TB_W
        y = iy + ih - TB_H
        m = self.meta
        self.add(f'<rect class="tmf-rule" x="{x}" y="{y}" width="{TB_W}" height="{TB_H}"/>')
        self.add(f'<rect class="tmf-band" x="{x+1}" y="{y+1}" width="{TB_W-2}" height="30"/>')
        self.text(x + 8, y + 21, m.get("org", ""), "tmf-head")
        self.text(x + TB_W - 8, y + 21, m.get("project", ""), "tmf-head", "end")
        r1 = y + 31
        self._cell(x, r1, TB_W, 40, "sheet title", m.get("title", ""), "tmf-val-big")
        r2 = r1 + 40
        self._cell(x, r2, 150, 34, "drawing no.", m.get("docno", ""))
        self._cell(x + 150, r2, 60, 34, "rev", m.get("rev", ""))
        self._cell(x + 210, r2, 130, 34, "date", m.get("date", ""))
        self._cell(x + 340, r2, TB_W - 340, 34, "sheet", m.get("sheet", ""))
        r3 = r2 + 34
        h3 = TB_H - (r3 - y) - 1
        assert h3 >= 30, f"title block last row is {h3} units: a label and a value need 30"
        self._cell(x, r3, 150, h3, "drawn by", m.get("drawn", ""))
        self._cell(x + 150, r3, 190, h3, "source", m.get("source", ""))
        self._cell(x + 340, r3, TB_W - 340, h3, "scale", m.get("scale", "NTS"))
        self._tb = (x, y)

    def header(self, left, right=""):
        ix, iy, iw, _ = self._inner
        self.text(ix + 8, iy + 20, left, "tmf-head")
        if right:
            self.text(ix + iw - 8, iy + 20, right, "tmf-head", "end")
        self.add(f'<line class="tmf-hair" x1="{ix+1}" y1="{iy+28}" x2="{ix+iw-1}" y2="{iy+28}"/>')
        return iy + 28

    def footer(self, text):
        ix, iy, iw, ih = self._inner
        self.text(ix + 8, iy + ih - 8, text, "tmf-foot")

    def body_box(self, top_pad=40, right_of_titleblock=False):
        """The area a drawing or a table may use, clear of the frame,
        the header and the title block."""
        ix, iy, iw, ih = self._inner
        x, y = ix + 10, iy + top_pad
        w = iw - 20
        h = ih - top_pad - (TB_H + 14)
        return x, y, w, h

    def full_box(self, top_pad=40):
        """The widest a drawing may be. Still stops above the title
        block: a schematic scaled into the whole sheet would be bigger
        and would have the title block sitting on top of a corner of it,
        which is how a pin number goes missing from a printed page."""
        ix, iy, iw, ih = self._inner
        return ix + 6, iy + top_pad, iw - 12, ih - top_pad - (TB_H + 10)

    # ------------------------------------------------------- placing things
    def place_svg(self, path, box):
        """Nest a source SVG, scaled to fit the box and centred. The
        nested viewBox does the scaling, so it stays vector and the
        source file is not touched."""
        src = Path(path).read_text()
        mroot = re.search(r"<svg\b[^>]*>", src)
        if not mroot:
            raise ValueError(f"{path} has no <svg> root")
        vb = re.search(r'viewBox="([^"]+)"', mroot.group(0))
        if vb:
            _, _, sw, sh = [float(v) for v in vb.group(1).split()]
        else:
            sw = float(re.search(r'width="([\d.]+)"', mroot.group(0)).group(1))
            sh = float(re.search(r'height="([\d.]+)"', mroot.group(0)).group(1))
        inner = src[mroot.end():src.rindex("</svg>")]
        x, y, w, h = box
        self.add(f'<svg x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                 f'viewBox="0 0 {sw:g} {sh:g}" preserveAspectRatio="xMidYMid meet">{inner}</svg>')
        return min(w / sw, h / sh)

    def table(self, box, headers, rows, widths=None, mono=()):
        """A table that stops at the bottom of the box and says how many
        rows it could not fit, rather than drawing over the title block."""
        x, y, w, h = box
        n = len(headers)
        widths = widths or [1.0 / n] * n
        xs, acc = [], x
        for fr in widths:
            xs.append(acc)
            acc += w * fr
        lh = 19
        self.add(f'<rect class="tmf-band" x="{x}" y="{y}" width="{w}" height="{lh+2}"/>')
        for i, hd in enumerate(headers):
            self.text(xs[i] + 6, y + 14, hd.upper(), "tmf-th")
        self.add(f'<line class="tmf-rule" x1="{x}" y1="{y+lh+2}" x2="{x+w}" y2="{y+lh+2}"/>')
        cy = y + lh + 2
        drawn = 0
        for r in rows:
            if cy + lh > y + h:
                break
            cy += lh
            for i, cell in enumerate(r[:n]):
                self.text(xs[i] + 6, cy - 5, cell, "tmf-tdm" if i in mono else "tmf-td")
            self.add(f'<line class="tmf-hair" x1="{x}" y1="{cy:.1f}" x2="{x+w}" y2="{cy:.1f}"/>')
            drawn += 1
        left = len(rows) - drawn
        if left:
            self.text(x + 6, cy + 15, f"{left} more row(s) continue on the next sheet", "tmf-foot")
        return drawn

    def steps(self, box, items):
        x, y, w, h = box
        cy = y + 18
        for i, it in enumerate(items, 1):
            if cy > y + h - 8:
                self.text(x, cy, f"{len(items)-i+1} more step(s) continue on the next sheet", "tmf-foot")
                return i - 1
            self.text(x, cy, f"{i}.", "tmf-h2")
            for line in wrap(it, 96):
                self.text(x + 26, cy, line, "tmf-body")
                cy += 17
            cy += 8
        return len(items)

    def done(self, path):
        self._frame()
        self._titleblock()
        self.add("</svg>")
        Path(path).write_text("\n".join(self.o))
        return path


def wrap(s, n):
    out, line = [], ""
    for word in s.split():
        if len(line) + len(word) + 1 > n:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out
