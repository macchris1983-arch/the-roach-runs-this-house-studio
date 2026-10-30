"""Low-level drawing helpers: antialiased vector-ish drawing on top of Pillow.

Everything is drawn in *design units* through a Pen, supersampled, then
downscaled so edges are smooth without needing Cairo or any paid tool.
"""
from __future__ import annotations

import functools
import math
import subprocess
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

OUTLINE = (30, 20, 16, 255)
SUPERSAMPLE = 3


def rgba(c, a=255):
    if isinstance(c, str):
        c = c.lstrip("#")
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), a)
    if len(c) == 3:
        return (*c, a)
    return tuple(c)


def shade(c, f):
    r, g, b, a = rgba(c)
    return (max(0, min(255, int(r * f))), max(0, min(255, int(g * f))), max(0, min(255, int(b * f))), a)


class Pen:
    """Maps design coordinates to pixels on an RGBA image."""

    def __init__(self, img: Image.Image, scale: float, ox: float, oy: float):
        self.img = img
        self.d = ImageDraw.Draw(img)
        self.s = scale
        self.ox = ox
        self.oy = oy

    def p(self, x, y):
        return ((x + self.ox) * self.s, (y + self.oy) * self.s)

    def w(self, v):
        return max(1, int(round(v * self.s)))

    def ellipse(self, cx, cy, rx, ry, fill=None, outline=OUTLINE, width=5.0):
        x0, y0 = self.p(cx - rx, cy - ry)
        x1, y1 = self.p(cx + rx, cy + ry)
        self.d.ellipse([x0, y0, x1, y1], fill=rgba(fill) if fill else None,
                       outline=rgba(outline) if outline and width else None,
                       width=self.w(width) if outline and width else 0)

    def circle(self, cx, cy, r, **kw):
        self.ellipse(cx, cy, r, r, **kw)

    def rrect(self, x0, y0, x1, y1, r, fill=None, outline=OUTLINE, width=5.0):
        a = self.p(x0, y0)
        b = self.p(x1, y1)
        self.d.rounded_rectangle([a[0], a[1], b[0], b[1]], radius=r * self.s,
                                 fill=rgba(fill) if fill else None,
                                 outline=rgba(outline) if outline and width else None,
                                 width=self.w(width) if outline and width else 0)

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, width=0):
        self.rrect(x0, y0, x1, y1, 0, fill=fill, outline=outline, width=width)

    def poly(self, pts, fill=None, outline=OUTLINE, width=5.0):
        P = [self.p(x, y) for x, y in pts]
        if fill:
            self.d.polygon(P, fill=rgba(fill))
        if outline and width:
            self.d.line(P + [P[0]], fill=rgba(outline), width=self.w(width), joint="curve")
            for q in P:
                self._dot(q, width, outline)

    def line(self, pts, color=OUTLINE, width=5.0, round_caps=True):
        P = [self.p(x, y) for x, y in pts]
        self.d.line(P, fill=rgba(color), width=self.w(width), joint="curve")
        if round_caps:
            self._dot(P[0], width, color)
            self._dot(P[-1], width, color)

    def _dot(self, q, width, color):
        r = width * self.s / 2
        self.d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=rgba(color))

    def arc(self, cx, cy, rx, ry, a0, a1, color=OUTLINE, width=5.0, steps=24):
        pts = []
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
        self.line(pts, color=color, width=width)

    def capsule(self, x0, y0, x1, y1, r, fill, outline=OUTLINE, width=5.0):
        """Thick limb from (x0,y0) to (x1,y1) with radius r."""
        if outline and width:
            self.line([(x0, y0), (x1, y1)], color=outline, width=2 * r + 2 * width)
        self.line([(x0, y0), (x1, y1)], color=fill, width=2 * r)

    def heart(self, cx, cy, size, fill):
        pts = []
        for i in range(40):
            t = 2 * math.pi * i / 40
            x = 16 * math.sin(t) ** 3
            y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
            pts.append((cx + x * size / 32, cy + y * size / 32))
        self.poly(pts, fill=fill, outline=None, width=0)


@dataclass
class Sprite:
    img: Image.Image      # RGBA at `res` pixels per design unit
    px: float             # pivot x in pixels
    py: float             # pivot y in pixels
    res: float


def make_sprite(bbox, draw_fn, res: float) -> Sprite:
    """Render draw_fn(pen) where bbox=(x0,y0,x1,y1) is in part-local design
    coords with the pivot at (0,0). Returned at `res` px per unit, antialiased."""
    x0, y0, x1, y1 = bbox
    ss = res * SUPERSAMPLE
    W = max(2, int(math.ceil((x1 - x0) * ss)))
    H = max(2, int(math.ceil((y1 - y0) * ss)))
    big = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pen = Pen(big, ss, -x0, -y0)
    draw_fn(pen)
    w2 = max(1, int(round(W / SUPERSAMPLE)))
    h2 = max(1, int(round(H / SUPERSAMPLE)))
    small = big.resize((w2, h2), Image.LANCZOS)
    return Sprite(small, -x0 * res, -y0 * res, res)


@functools.lru_cache(maxsize=None)
def font_path(bold=True) -> str:
    """Find a bold display font installed on the system (Poppins preferred)."""
    for name in (["Poppins:style=ExtraBold", "Poppins:style=Bold", "DejaVu Sans:style=Bold"] if bold
                 else ["Poppins", "DejaVu Sans"]):
        try:
            out = subprocess.run(["fc-match", "-f", "%{file}", name], capture_output=True,
                                 text=True, timeout=10).stdout.strip()
            if out:
                return out
        except Exception:  # pragma: no cover - fc-match missing
            pass
    return "DejaVuSans-Bold.ttf"


@functools.lru_cache(maxsize=64)
def font(size: int, bold=True):
    try:
        return ImageFont.truetype(font_path(bold), size)
    except Exception:  # pragma: no cover
        return ImageFont.load_default()


def font_family(bold=True) -> str:
    try:
        out = subprocess.run(["fc-query", "-f", "%{family[0]}", font_path(bold)],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return out or "DejaVu Sans"
    except Exception:  # pragma: no cover
        return "DejaVu Sans"
