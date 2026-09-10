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

# The title block, proportioned to the paper. It was one fixed size, and
# 470 units is a fifth of an ANSI B sheet and nearly half a letter one:
# on landscape letter it ate the drawing.
TITLEBLOCK = {
    "wide":   dict(w=470, h=146, band=30, r1=40, r2=34),
    "narrow": dict(w=408, h=126, band=26, r1=36, r2=31),
}
# Column fractions of the block's width: drawing no., rev, date, then
# the sheet number fills what is left.
TB_COLS = (150 / 470, 60 / 470, 130 / 470)
TB_W, TB_H = TITLEBLOCK["wide"]["w"], TITLEBLOCK["wide"]["h"]   # ANSI B, kept for callers

# The smallest text a placed drawing may print at. A pin name under
# about 5 pt is a smudge on paper, and a package nobody can build at the
# bench is not a package.
FLOOR_PT = 5.0


def titleblock(size):
    return TITLEBLOCK["wide" if PAGES[size][0] > 1300 else "narrow"]


def drawing_box(size="ansi-b", top_pad=46):
    """The width and height a placed drawing may use on this page. The
    same arithmetic `Page.full_box` does, available before a Page
    exists, so a drawing tool can size a sheet to the page it is going
    on instead of being scaled down to fit one."""
    w, h = PAGES[size]
    tb = titleblock(size)
    iw = w - 2 * (MARGIN + ZONE)
    ih = h - 2 * (MARGIN + ZONE)
    return iw - 12, ih - top_pad - (tb["h"] + 10)


def smallest_font_px(src):
    """The smallest font-size in an SVG's own stylesheet. Not a parse of
    the cascade: every sheet here declares its sizes in one <style>
    block, and this is what decides whether it can be printed."""
    sizes = [float(v) for v in re.findall(r"font-size:\s*([\d.]+)px", src)]
    return min(sizes) if sizes else 0.0


def esc(s):
    return html.escape(str(s), quote=False)


class Page:
    def __init__(self, meta, size="ansi-b"):
        self.w, self.h = PAGES[size]
        self.size = size
        self.tb = titleblock(size)
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

    def text(self, x, y, s, cls="tmf-body", anchor="start", px=None):
        size = f' style="font-size:{px:.1f}px"' if px else ""
        self.add(f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}"{size}>{esc(s)}</text>')

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

    # Advance of the title block's sans, as a fraction of its size. Used
    # only to decide whether a value has to be set smaller to fit its
    # cell; a title that runs out through the right-hand rule and off
    # the paper is worse than one set a point down.
    ADVANCE = 0.60

    def _cell(self, x, y, w, h, label, value, cls="tmf-val", px=None):
        self.add(f'<rect class="tmf-hair" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"/>')
        self.text(x + 6, y + 12, label.upper(), "tmf-lab")
        if px and value:
            room = w - 12
            need = self.ADVANCE * px * len(str(value))
            if need > room:
                px = max(10.0, room / (self.ADVANCE * len(str(value))))
            self.text(x + 6, y + h - 8, value, cls, px=px)
        else:
            self.text(x + 6, y + h - 8, value, cls)

    def _titleblock(self):
        ix, iy, iw, ih = self._inner
        tb = self.tb
        bw, bh = tb["w"], tb["h"]
        x = ix + iw - bw
        y = iy + ih - bh
        m = self.meta
        c1, c2, c3 = [round(bw * f) for f in TB_COLS]
        self.add(f'<rect class="tmf-rule" x="{x}" y="{y}" width="{bw}" height="{bh}"/>')
        self.add(f'<rect class="tmf-band" x="{x+1}" y="{y+1}" width="{bw-2}" height="{tb["band"]}"/>')
        self.text(x + 8, y + tb["band"] - 9, m.get("org", ""), "tmf-head")
        self.text(x + bw - 8, y + tb["band"] - 9, m.get("project", ""), "tmf-head", "end")
        r1 = y + tb["band"] + 1
        self._cell(x, r1, bw, tb["r1"], "sheet title", m.get("title", ""), "tmf-val-big", px=19.0)
        r2 = r1 + tb["r1"]
        self._cell(x, r2, c1, tb["r2"], "drawing no.", m.get("docno", ""))
        self._cell(x + c1, r2, c2, tb["r2"], "rev", m.get("rev", ""))
        self._cell(x + c1 + c2, r2, c3, tb["r2"], "date", m.get("date", ""))
        self._cell(x + c1 + c2 + c3, r2, bw - c1 - c2 - c3, tb["r2"], "sheet", m.get("sheet", ""))
        r3 = r2 + tb["r2"]
        h3 = bh - (r3 - y) - 1
        assert h3 >= 30, f"title block last row is {h3} units: a label and a value need 30"
        self._cell(x, r3, c1, h3, "drawn by", m.get("drawn", ""))
        self._cell(x + c1, r3, c2 + c3, h3, "source", m.get("source", ""))
        self._cell(x + c1 + c2 + c3, r3, bw - c1 - c2 - c3, h3, "scale", m.get("scale", "NTS"))
        self._tb = (x, y)

    def revisions(self, rows):
        """The revision strip, immediately left of the title block. Rows
        are (rev, date, what changed), newest last, as a drawing office
        writes them."""
        if not rows:
            return
        ix, iy, iw, ih = self._inner
        tb = self.tb
        w = min(470, iw - tb["w"] - 20)
        x = ix + iw - tb["w"] - w
        y = iy + ih - tb["h"]
        self.add(f'<rect class="tmf-rule" x="{x}" y="{y}" width="{w}" height="{tb["h"]}"/>')
        self.add(f'<rect class="tmf-band" x="{x+1}" y="{y+1}" width="{w-1}" height="{tb["band"]}"/>')
        cw = (44, 88)
        # A revision note is one line in a fixed column. Cut it here
        # rather than letting it run out through the title block, which
        # is what an untruncated one does and what it did.
        room = int((w - cw[0] - cw[1] - 14) / 6.3)
        for lab, cx in zip(("rev", "date", "revision"), (0, cw[0], cw[0] + cw[1])):
            self.text(x + cx + 6, y + tb["band"] - 9, lab.upper(), "tmf-lab")
        lh = (tb["h"] - tb["band"]) / max(len(rows), 4)
        cy = y + tb["band"]
        for rev, dt, what in rows[-4:]:
            cy += lh
            self.text(x + 6, cy - 5, rev, "tmf-tdm")
            self.text(x + cw[0] + 6, cy - 5, dt, "tmf-tdm")
            self.text(x + cw[0] + cw[1] + 6, cy - 5,
                      what if len(what) <= room else what[:room - 3] + "...", "tmf-td")
            self.add(f'<line class="tmf-hair" x1="{x}" y1="{cy:.1f}" x2="{x+w}" y2="{cy:.1f}"/>')
        for cx in (cw[0], cw[0] + cw[1]):
            self.add(f'<line class="tmf-hair" x1="{x+cx}" y1="{y}" x2="{x+cx}" y2="{y+tb["h"]}"/>')

    def header(self, left, right=""):
        ix, iy, iw, _ = self._inner
        self.text(ix + 8, iy + 20, left, "tmf-head")
        if right:
            self.text(ix + iw - 8, iy + 20, right, "tmf-head", "end")
        self.add(f'<line class="tmf-hair" x1="{ix+1}" y1="{iy+28}" x2="{ix+iw-1}" y2="{iy+28}"/>')
        return iy + 28

    def footer(self, text):
        """Above the title block, not through it."""
        ix, iy, iw, ih = self._inner
        self.text(ix + 8, iy + ih - self.tb["h"] - 8, text, "tmf-foot")

    def body_box(self, top_pad=40, right_of_titleblock=False):
        """The area a drawing or a table may use, clear of the frame,
        the header and the title block."""
        ix, iy, iw, ih = self._inner
        x, y = ix + 10, iy + top_pad
        w = iw - 20
        h = ih - top_pad - (self.tb["h"] + 28)   # 28: room for the footer line
        return x, y, w, h

    def full_box(self, top_pad=40):
        """The widest a drawing may be. Still stops above the title
        block: a schematic scaled into the whole sheet would be bigger
        and would have the title block sitting on top of a corner of it,
        which is how a pin number goes missing from a printed page."""
        ix, iy, iw, ih = self._inner
        return ix + 6, iy + top_pad, iw - 12, ih - top_pad - (self.tb["h"] + 10)

    # ------------------------------------------------------- placing things
    def place_svg(self, path, box, drop_heading=False):
        """Nest a source SVG, scaled to fit the box and centred. The
        nested viewBox does the scaling, so it stays vector and the
        source file is not touched.

        `drop_heading` removes the drawing's own title group and crops
        the space it occupied out of the viewBox, for a page whose title
        block already names the sheet. It returns the subtitle it
        dropped so the page can print it once, which keeps that sentence
        in the drawing where it belongs instead of in this package's
        JSON as a second copy."""
        src = Path(path).read_text()
        sub = ""
        if drop_heading:
            g = re.search(r'<g class="sheet-heading"[^>]*data-height="([\d.]+)"[^>]*>(.*?)</g>',
                          src, re.S)
            if g:
                t = re.search(r'<text class="sub"[^>]*>(.*?)</text>', g.group(2), re.S)
                sub = html.unescape(t.group(1)).strip() if t else ""
                self._crop_top = float(g.group(1))
                src = src[:g.start()] + src[g.end():]
            else:
                self._crop_top = 0.0
        else:
            self._crop_top = 0.0
        self._dropped_sub = sub
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
        top = getattr(self, "_crop_top", 0.0)
        sh -= top
        x, y, w, h = box
        scale = min(w / sw, h / sh)
        # A drawing is placed by scaling its viewBox, so its own type
        # scales with it. This is the only place that knows both the
        # type size and the scale, so it is the only place that can
        # refuse a page nobody could read.
        px = smallest_font_px(src)
        pt = px * scale * 0.75
        if px and pt < FLOOR_PT:
            raise AssertionError(
                f"{Path(path).name} is {sw:g} by {sh:g} and places at {scale*100:.0f}% "
                f"in this box, printing its smallest text ({px:g} px) at {pt:.1f} pt. "
                f"The floor is {FLOOR_PT} pt. Re-lay the sheet, split it, or give it "
                f"a bigger page in package.json.")
        self.add(f'<svg x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                 f'viewBox="0 {top:g} {sw:g} {sh:g}" preserveAspectRatio="xMidYMid meet">{inner}</svg>')
        return scale

    def table(self, box, headers, rows, widths=None, mono=(), strict=False):
        """A table that stops at the bottom of the box and says how many
        rows it could not fit, rather than drawing over the title block.

        `strict` refuses a cell whose text would run into the next
        column, by an estimate of its width (DejaVu at 12 px: about 7.2
        px per mono character, 6.6 per sans). SVG text does not clip, so
        an overlong cell prints on top of its neighbour and reads as
        neither; the first pin-map sheet did exactly that."""
        x, y, w, h = box
        n = len(headers)
        widths = widths or [1.0 / n] * n
        xs, acc = [], x
        for fr in widths:
            xs.append(acc)
            acc += w * fr
        if strict:
            for r in rows:
                for i, cell in enumerate(r[:n]):
                    est = len(cell) * (7.2 if i in mono else 6.6) + 12
                    if est > w * widths[i]:
                        raise AssertionError(
                            f"table cell {cell!r} needs about {est:.0f} px and column "
                            f"{headers[i]!r} is {w * widths[i]:.0f}: shorten it or widen the column")
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
        return drawn

    def steps(self, box, items, start=1):
        """As many steps as fit, numbered from `start`. Returns how many
        were drawn; the caller decides what to do with the rest, which
        on a paginated package is another sheet."""
        x, y, w, h = box
        cy = y + 18
        for i, it in enumerate(items, start):
            if cy > y + h - 8:
                return i - start
            self.text(x, cy, f"{i}.", "tmf-h2")
            for line in wrap(it, 96):
                self.text(x + 30, cy, line, "tmf-body")
                cy += 17
            cy += 8
        return len(items)

    def done(self, path):
        self._frame()
        self._titleblock()
        self.revisions(self.meta.get("revisions", []))
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
