"""Cut-out 2D character rigs for The Wife, The Husband and The Roach.

Each character is a hierarchy of parts (legs, torso, arms, head, face features).
Parts are drawn once as antialiased sprites, then posed per frame by rotating
them around their pivots — the same technique as cut-out animation tools.
All colours come from assets/characters/characters.yaml.
"""
from __future__ import annotations

import functools
import math
from dataclasses import dataclass, field
from typing import Callable

import yaml
from PIL import Image

from . import config
from .draw import OUTLINE, Pen, make_sprite, rgba, shade

RES = 2.5  # sprite pixels per design unit (covers ~2.5x camera zoom crisply)


@functools.lru_cache(maxsize=1)
def bible() -> dict:
    with open(config.CHARACTERS_DIR / "characters.yaml") as f:
        return yaml.safe_load(f)


# ----------------------------------------------------------------------------
# Expressions
# ----------------------------------------------------------------------------
EXPRESSIONS = {
    #             eyes      brows      mouth
    "neutral":   ("open",   "neutral", "smile"),
    "happy":     ("happy",  "raised",  "grin"),
    "smug":      ("half",   "skeptic", "smirk"),
    "unbothered": ("half",  "flat",    "flat"),
    "shocked":   ("wide",   "high",    "o"),
    "scared":    ("wide",   "worried", "grimace"),
    "screaming": ("wide",   "worried", "scream"),
    "angry":     ("narrow", "angry",   "frown"),
    "furious":   ("narrow", "angry",   "grimace"),
    "sideeye":   ("half",   "flat",    "flat"),
    "confused":  ("open",   "skeptic", "wavy"),
    "nervous":   ("open",   "worried", "wavy"),
    "chewing":   ("half",   "neutral", "chew"),
    "pleading":  ("wide",   "worried", "smile"),
    "determined": ("narrow", "flat",   "flat"),
}
SHOUT_EXPRESSIONS = {"screaming", "scared", "furious", "shocked", "angry"}


# ----------------------------------------------------------------------------
# Face feature drawing (shared by all characters, parameterised by size)
# ----------------------------------------------------------------------------
@dataclass
class FaceSpec:
    eye_dx: float
    eye_rx: float
    eye_ry: float
    lid: str               # lid colour (skin)
    brow_color: str
    brow_w: float
    brow_len: float
    mouth_w: float
    lips: str
    outline_w: float = 5.0


def draw_eyes(p: Pen, fs: FaceSpec, variant: str, look: str):
    lx, ly = {"left": (-0.45, 0), "right": (0.45, 0), "up": (0, -0.4), "down": (0, 0.35),
              "camera": (0, 0.05), "center": (0, 0)}.get(look, (0, 0))
    for side in (-1, 1):
        cx = side * fs.eye_dx
        rx, ry = fs.eye_rx, fs.eye_ry
        if variant == "happy":
            p.arc(cx, ry * 0.25, rx, ry * 0.7, 200, 340, width=fs.outline_w * 1.3)
            continue
        if variant == "closed":
            p.arc(cx, -ry * 0.1, rx, ry * 0.45, 20, 160, width=fs.outline_w * 1.2)
            continue
        if variant == "wide":
            rx, ry = rx * 1.18, ry * 1.2
        p.ellipse(cx, 0, rx, ry, fill="#FFFFFF", width=fs.outline_w)
        pr = rx * (0.36 if variant == "wide" else 0.52)
        px = cx + lx * (rx - pr)
        py = ly * (ry - pr) + (ry * 0.1 if variant in ("half", "narrow") else 0)
        p.circle(px, py, pr, fill="#1A100C", outline=None, width=0)
        p.circle(px + pr * 0.35, py - pr * 0.35, pr * 0.32, fill="#FFFFFF", outline=None, width=0)
        if variant in ("half", "narrow"):
            # upper eyelid covering part of the eye
            if variant == "half":
                pts = [(cx - rx - 2, -ry - 4), (cx + rx + 2, -ry - 4), (cx + rx + 2, -ry * 0.05),
                       (cx - rx - 2, -ry * 0.05)]
                lid_line = [(cx - rx, -ry * 0.05), (cx + rx, -ry * 0.05)]
            else:  # angry: slanted lid, low on the inside
                inner = -side
                y_in, y_out = ry * 0.15, -ry * 0.45
                a = (cx + inner * rx, y_in)
                b = (cx - inner * rx, y_out)
                pts = [(a[0] + inner * 3, -ry - 6), (b[0] - inner * 3, -ry - 6), (b[0] - inner * 3, y_out), (a[0] + inner * 3, y_in)]
                lid_line = [a, b]
            p.poly(pts, fill=fs.lid, outline=None, width=0)
            p.line(lid_line, width=fs.outline_w * 1.25)


def draw_brows(p: Pen, fs: FaceSpec, variant: str):
    L, W = fs.brow_len, fs.brow_w
    for side in (-1, 1):
        cx = side * fs.eye_dx
        inner_x, outer_x = cx - side * L / 2, cx + side * L / 2
        if variant == "neutral":
            yi, yo, bow = 0, 2, -6
        elif variant == "raised":
            yi, yo, bow = -10, -6, -10
        elif variant == "high":
            yi, yo, bow = -24, -20, -12
        elif variant == "angry":
            yi, yo, bow = 14, -12, 0
        elif variant == "worried":
            yi, yo, bow = -16, 8, -2
        elif variant == "flat":
            yi, yo, bow = 4, 4, 0
        elif variant == "skeptic":
            yi, yo, bow = (-18, -14, -12) if side < 0 else (6, 6, 0)
        else:
            yi, yo, bow = 0, 0, 0
        mid = ((inner_x + outer_x) / 2, (yi + yo) / 2 + bow)
        p.line([(inner_x, yi), mid, (outer_x, yo)], color=fs.brow_color, width=W)


def draw_mouth(p: Pen, fs: FaceSpec, variant: str):
    w = fs.mouth_w
    dark = "#3A0F12"
    tongue = "#E07A82"
    ow = fs.outline_w
    if variant == "smile":
        p.arc(0, -w * 0.25, w * 0.5, w * 0.32, 25, 155, width=ow * 1.2)
    elif variant == "flat":
        p.line([(-w * 0.38, 0), (w * 0.38, 0)], width=ow * 1.2)
    elif variant == "frown":
        p.arc(0, w * 0.22, w * 0.42, w * 0.25, 205, 335, width=ow * 1.2)
    elif variant == "smirk":
        p.line([(-w * 0.35, 2), (w * 0.15, 0), (w * 0.45, -w * 0.16)], width=ow * 1.2)
    elif variant == "wavy":
        pts = [(-w * 0.4 + i * w * 0.1, math.sin(i * 1.6) * w * 0.05) for i in range(9)]
        p.line(pts, width=ow * 1.1)
    elif variant == "chew":
        pts = [(-w * 0.3 + i * w * 0.075, math.sin(i * 2.2) * w * 0.06) for i in range(9)]
        p.line(pts, width=ow * 1.2)
    elif variant == "o":
        p.ellipse(0, 0, w * 0.16, w * 0.21, fill=dark, width=ow)
    elif variant == "open_s":
        p.ellipse(0, 0, w * 0.3, w * 0.14, fill=dark, width=ow)
        p.ellipse(0, w * 0.07, w * 0.16, w * 0.06, fill=tongue, outline=None, width=0)
    elif variant == "open_l":
        p.ellipse(0, w * 0.05, w * 0.36, w * 0.28, fill=dark, width=ow)
        p.ellipse(0, w * 0.19, w * 0.2, w * 0.1, fill=tongue, outline=None, width=0)
        p.rrect(-w * 0.24, -w * 0.21, w * 0.24, -w * 0.12, 4, fill="#FFFFFF", outline=None, width=0)
    elif variant in ("grin", "scream", "grimace"):
        if variant == "grin":
            pts = [(-w * 0.5, -w * 0.08)] + [(math.cos(math.radians(a)) * w * 0.5, -w * 0.08 + math.sin(math.radians(a)) * w * 0.42) for a in range(10, 171, 10)]
            p.poly(pts, fill=dark, width=ow)
            p.poly([(-w * 0.42, -w * 0.06), (w * 0.42, -w * 0.06), (w * 0.36, w * 0.08), (-w * 0.36, w * 0.08)], fill="#FFFFFF", outline=None, width=0)
        elif variant == "scream":
            p.ellipse(0, w * 0.15, w * 0.42, w * 0.5, fill=dark, width=ow)
            p.rrect(-w * 0.3, -w * 0.3, w * 0.3, -w * 0.16, 6, fill="#FFFFFF", outline=None, width=0)
            p.ellipse(0, w * 0.48, w * 0.24, w * 0.12, fill=tongue, outline=None, width=0)
        else:  # grimace: clenched teeth
            p.rrect(-w * 0.48, -w * 0.15, w * 0.48, w * 0.15, w * 0.12, fill="#FFFFFF", width=ow)
            for i in range(1, 6):
                x = -w * 0.48 + i * w * 0.96 / 6
                p.line([(x, -w * 0.15), (x, w * 0.15)], width=ow * 0.6, round_caps=False)
            p.line([(-w * 0.46, 0), (w * 0.46, 0)], width=ow * 0.6, round_caps=False)
    else:
        p.line([(-w * 0.3, 0), (w * 0.3, 0)], width=ow)


# ----------------------------------------------------------------------------
# Rig definition
# ----------------------------------------------------------------------------
@dataclass
class PartDef:
    name: str
    parent: str | None
    offset: tuple            # pivot position in parent's local design coords
    z: int
    bbox: Callable[[str], tuple]
    draw: Callable[[Pen, str], None]
    default_variant: str = "base"


@dataclass
class Rig:
    name: str
    parts: dict = field(default_factory=dict)
    hands: dict = field(default_factory=dict)   # hand name -> (part, local point)
    extent: tuple = (-450, -1300, 450, 80)      # layer bounds in design units
    face: FaceSpec | None = None

    def add(self, part: PartDef):
        self.parts[part.name] = part

    _cache: dict = field(default_factory=dict)

    def sprite(self, part: str, variant: str):
        key = (part, variant)
        if key not in self._cache:
            d = self.parts[part]
            self._cache[key] = make_sprite(d.bbox(variant), lambda p: d.draw(p, variant), RES)
        return self._cache[key]


def _const_bbox(b):
    return lambda v: b


# ---------------------------------------------------------------------------- shared limbs
def _fuzzy(p: Pen, cx, cy, rx, ry, color):
    for i in range(18):
        a = 2 * math.pi * i / 18
        p.circle(cx + math.cos(a) * rx, cy + math.sin(a) * ry, ry * 0.42, fill=color, width=4)
    p.ellipse(cx, cy, rx, ry, fill=color, outline=None, width=0)
    for i in range(10):
        a = 2 * math.pi * i / 10 + 0.3
        p.arc(cx + math.cos(a) * rx * 0.55, cy + math.sin(a) * ry * 0.5, 6, 4, 180, 360,
              color=shade(color, 0.85), width=3)


def _hand(p: Pen, x, y, r, skin):
    p.circle(x, y, r, fill=skin, width=5)
    p.ellipse(x - r * 0.85, y - r * 0.2, r * 0.38, r * 0.55, fill=skin, width=4)  # thumb
    p.line([(x - r * 0.25, y + r * 0.35), (x + r * 0.35, y + r * 0.35)], color=shade(skin, 0.7), width=3)


# ---------------------------------------------------------------------------- WIFE
def build_wife() -> Rig:
    pal = bible()["wife"]["palette"]
    r = Rig("wife", extent=(-420, -1220, 420, 60))
    skin, pj, pjd, hearts = pal["skin"], pal["pajamas"], pal["pajamas_dark"], pal["hearts"]

    def heart_pattern(p, x0, y0, x1, y1, size=22, step=56, seed=0):
        row = 0
        y = y0 + step / 2
        while y < y1:
            x = x0 + (step / 2 if (row + seed) % 2 else 0) + step / 4
            while x < x1:
                p.heart(x, y, size, hearts)
                x += step
            y += step * 0.8
            row += 1

    def leg(p: Pen, v):
        p.capsule(0, 0, 0, 330, 42, pj)
        heart_pattern(p, -34, 10, 34, 320, size=20, step=44)
        p.rrect(-44, 318, 44, 346, 10, fill=pjd, width=5)
        if v == "bare":
            p.ellipse(0, 372, 46, 24, fill=skin, width=5)
        else:
            _fuzzy(p, 0, 372, 60, 28, pal["slippers"])

    for side, name in ((-1, "leg_L"), (1, "leg_R")):
        r.add(PartDef(name, "pelvis", (side * 44, 0), 1, _const_bbox((-100, -50, 100, 420)), leg))

    def pelvis(p, v):
        pass
    r.add(PartDef("pelvis", None, (0, -400), 0, _const_bbox((-2, -2, 2, 2)), pelvis))

    def torso(p: Pen, v):
        p.rrect(-26, -360, 26, -290, 10, fill=skin, width=5)        # neck
        body = [(-112, -300), (112, -300), (128, -120), (120, 30), (-120, 30), (-128, -120)]
        p.poly(body, fill=pj, width=6)
        heart_pattern(p, -110, -280, 110, 20, size=24, step=58, seed=1)
        p.poly(body, fill=None, width=6)
        # collar with piping and buttons
        p.poly([(-62, -302), (0, -230), (62, -302)], fill=skin, outline=None, width=0)
        p.line([(-70, -304), (0, -222), (70, -304)], color=pal["hearts"], width=10)
        p.line([(-70, -304), (0, -222), (70, -304)], width=4)
        for y in (-190, -120, -50):
            p.circle(0, y, 9, fill=pal["hearts"], width=3)
        p.line([(0, -222), (0, 26)], color=pjd, width=4, round_caps=False)
    r.add(PartDef("torso", "pelvis", (0, 0), 2, _const_bbox((-150, -380, 150, 50)), torso))

    def upper(p: Pen, v):
        p.capsule(0, 0, 0, 150, 34, pj)
        heart_pattern(p, -26, 0, 26, 150, size=18, step=40, seed=2)
    def fore(p: Pen, v):
        p.capsule(0, 0, 0, 40, 32, pj)
        p.rrect(-34, 30, 34, 50, 8, fill=pal["hearts"], width=4)
        p.capsule(0, 50, 0, 118, 21, skin)
        _hand(p, 0, 142, 29, skin)
    for side, s in (("L", -1), ("R", 1)):
        r.add(PartDef(f"upper_{side}", "torso", (s * 108, -278), 3, _const_bbox((-50, -45, 50, 195)), upper))
        r.add(PartDef(f"fore_{side}", f"upper_{side}", (0, 150), 4, _const_bbox((-50, -40, 50, 185)), fore))
        r.hands[side] = (f"fore_{side}", (0, 146))

    def head(p: Pen, v):
        hair = pal["hair"]
        # the puff: a tall curly cloud on top of the head
        for i in range(26):
            a = 2 * math.pi * i / 26
            p.circle(math.cos(a) * 128, -300 + math.sin(a) * 112, 40, fill=hair, width=5)
        p.ellipse(0, -300, 140, 122, fill=hair, outline=None, width=0)
        for i in range(14):
            a = 2 * math.pi * i / 14 + 0.2
            p.arc(math.cos(a) * 80, -300 + math.sin(a) * 70, 16, 12, 160, 380, color=shade(hair, 1.9), width=4)
        p.rrect(-58, -212, 58, -184, 12, fill="#C77DFF", width=5)   # scrunchie band
        # ears + gold hoops
        for s in (-1, 1):
            p.ellipse(s * 98, -118, 20, 26, fill=skin, width=5)
        p.ellipse(0, -122, 102, 112, fill=skin, width=6)
        # hairline
        p.arc(0, -150, 98, 80, 200, 340, color=hair, width=26)
        for s in (-1, 1):
            p.circle(s * 104, -70, 24, fill=None, outline=pal["hoops"], width=8)
        # nose and cheeks
        p.arc(0, -98, 16, 10, 20, 160, color=pal["skin_shadow"], width=5)
        for s in (-1, 1):
            p.ellipse(s * 60, -88, 16, 9, fill=shade(skin, 1.12), outline=None, width=0)
    r.add(PartDef("head", "torso", (0, -332), 6, _const_bbox((-185, -450, 185, 15)), head))

    fs = FaceSpec(eye_dx=40, eye_rx=21, eye_ry=26, lid=skin, brow_color=pal["hair"], brow_w=10,
                  brow_len=46, mouth_w=72, lips=pal["lips"])
    r.face = fs
    _add_face(r, fs, eyes=(0, -138), brows=(0, -180), mouth=(0, -66))
    return r


def _add_face(r: Rig, fs: FaceSpec, eyes, brows, mouth):
    def eyes_draw(p, v):
        variant, _, look = v.partition(":")
        draw_eyes(p, fs, variant, look or "center")
    ex = fs.eye_dx + fs.eye_rx * 1.5
    r.add(PartDef("eyes", "head", eyes, 7, _const_bbox((-ex, -fs.eye_ry * 1.6, ex, fs.eye_ry * 1.5)), eyes_draw, "open"))
    bx = fs.eye_dx + fs.brow_len
    r.add(PartDef("brows", "head", brows, 8, _const_bbox((-bx, -50, bx, 40)), lambda p, v: draw_brows(p, fs, v), "neutral"))
    mw = fs.mouth_w
    r.add(PartDef("mouth", "head", mouth, 8, _const_bbox((-mw * 0.65, -mw * 0.5, mw * 0.65, mw * 0.8)), lambda p, v: draw_mouth(p, fs, v), "smile"))


# ---------------------------------------------------------------------------- HUSBAND
def build_husband() -> Rig:
    pal = bible()["husband"]["palette"]
    r = Rig("husband", extent=(-440, -1220, 440, 60))
    skin, shirt = pal["skin"], pal["shirt"]

    r.add(PartDef("pelvis", None, (0, -420), 0, _const_bbox((-2, -2, 2, 2)), lambda p, v: None))

    def leg(p: Pen, v):
        p.capsule(0, 0, 0, 340, 48, pal["joggers"])
        p.line([(18, 20), (14, 320)], color=pal["joggers_dark"], width=6)
        p.rrect(-40, 330, 40, 362, 12, fill=pal["joggers_dark"], width=5)
        # black slide: foot + strap
        p.ellipse(0, 392, 58, 26, fill=skin, width=5)
        for i in range(4):
            p.circle(-30 + i * 20, 410, 9, fill=skin, width=3)
        p.ellipse(0, 418, 74, 14, fill=pal["slides"], width=4)
        p.rrect(-56, 372, 56, 400, 12, fill=pal["slides"], width=4)
    for side, name in ((-1, "leg_L"), (1, "leg_R")):
        r.add(PartDef(name, "pelvis", (side * 52, 0), 1, _const_bbox((-110, -60, 110, 440)), leg))

    def torso(p: Pen, v):
        p.rrect(-34, -380, 34, -300, 12, fill=skin, width=5)
        body = [(-130, -318), (130, -318), (142, -140), (134, 30), (-134, 30), (-142, -140)]
        p.poly(body, fill=shirt, width=6)
        p.arc(0, -318, 52, 36, 0, 180, color=pal["shirt_dark"], width=14)
        p.arc(0, -318, 52, 36, 0, 180, width=4)
        p.line([(-128, 10), (128, 10)], color=pal["shirt_dark"], width=6)
        p.arc(-50, -150, 50, 30, 30, 150, color=pal["shirt_dark"], width=4)
        p.arc(50, -150, 50, 30, 30, 150, color=pal["shirt_dark"], width=4)
    r.add(PartDef("torso", "pelvis", (0, 0), 2, _const_bbox((-165, -400, 165, 50)), torso))

    def upper(p: Pen, v):
        p.capsule(0, 40, 0, 160, 27, skin)
        p.poly([(-46, -12), (46, -12), (50, 82), (-50, 82)], fill=shirt, width=6)
        p.line([(-46, 70), (46, 70)], color=pal["shirt_dark"], width=6)
    def fore(p: Pen, v):
        p.capsule(0, 0, 0, 120, 25, skin)
        _hand(p, 0, 148, 32, skin)
    for side, s in (("L", -1), ("R", 1)):
        r.add(PartDef(f"upper_{side}", "torso", (s * 126, -296), 3, _const_bbox((-65, -40, 65, 200)), upper))
        r.add(PartDef(f"fore_{side}", f"upper_{side}", (0, 162), 4, _const_bbox((-55, -40, 55, 195)), fore))
        r.hands[side] = (f"fore_{side}", (0, 152))

    def head(p: Pen, v):
        hair, beard = pal["hair"], pal["beard"]
        for s in (-1, 1):
            p.ellipse(s * 106, -122, 22, 30, fill=skin, width=5)
        p.ellipse(0, -128, 110, 122, fill=skin, width=6)
        # short curly hair cap
        p.arc(0, -150, 104, 100, 190, 350, color=hair, width=34)
        for i in range(17):
            a = math.radians(188 + i * 10.5)
            p.circle(math.cos(a) * 100, -150 + math.sin(a) * 98, 17, fill=hair, width=4)
        for i in range(9):
            a = math.radians(205 + i * 16)
            p.arc(math.cos(a) * 82, -150 + math.sin(a) * 80, 8, 6, 180, 360, color="#3A2A24", width=3)
        # full beard around the jaw
        pts = [(-108, -150), (-96, -82), (-70, -30), (-34, -4), (0, 4), (34, -4), (70, -30), (96, -82), (108, -150),
               (86, -120), (62, -88), (34, -96), (0, -100), (-34, -96), (-62, -88), (-86, -120)]
        p.poly(pts, fill=beard, width=5)
        for i in range(12):
            a = math.radians(30 + i * 10)
            p.arc(math.cos(a) * 70, -70 + math.sin(a) * 50, 7, 5, 0, 180, color="#3A2A24", width=3)
        # mustache
        p.poly([(-46, -96), (0, -110), (46, -96), (40, -84), (0, -94), (-40, -84)], fill=beard, width=4)
        p.arc(0, -112, 18, 11, 20, 160, color=pal["skin_shadow"], width=5)
    r.add(PartDef("head", "torso", (0, -350), 6, _const_bbox((-145, -300, 145, 25)), head))

    fs = FaceSpec(eye_dx=43, eye_rx=21, eye_ry=25, lid=skin, brow_color=pal["hair"], brow_w=14,
                  brow_len=50, mouth_w=66, lips=pal["lips"])
    r.face = fs
    _add_face(r, fs, eyes=(0, -150), brows=(0, -194), mouth=(0, -64))
    return r


# ---------------------------------------------------------------------------- ROACH
def build_roach() -> Rig:
    pal = bible()["roach"]["palette"]
    r = Rig("roach", extent=(-300, -560, 300, 50))
    limbs = pal["limbs"]

    r.add(PartDef("pelvis", None, (0, -96), 0, _const_bbox((-2, -2, 2, 2)), lambda p, v: None))

    def leg(p: Pen, v):
        p.line([(0, 0), (8, 48), (0, 88)], color=OUTLINE, width=16)
        p.line([(0, 0), (8, 48), (0, 88)], color=limbs, width=9)
        for y in (24, 64):
            p.line([(6, y), (16, y - 8)], color=limbs, width=3)
        p.ellipse(4, 94, 20, 9, fill=limbs, width=4)
    for side, name in ((-1, "leg_L"), (1, "leg_R")):
        r.add(PartDef(name, "pelvis", (side * 28, 0), 1, _const_bbox((-40, -20, 45, 115)), leg))

    def body(p: Pen, v):
        # wing shell edges peeking out behind
        for s in (-1, 1):
            p.ellipse(s * 40, -82, 46, 96, fill=pal["shell_dark"], width=5)
        # middle legs (decorative)
        for s in (-1, 1):
            p.line([(s * 50, -80), (s * 92, -60), (s * 104, -20)], color=OUTLINE, width=13)
            p.line([(s * 50, -80), (s * 92, -60), (s * 104, -20)], color=limbs, width=7)
        p.ellipse(0, -76, 62, 88, fill=pal["shell"], width=6)
        p.ellipse(0, -66, 40, 66, fill=pal["belly"], outline=None, width=0)
        for i in range(5):
            y = -118 + i * 22
            p.arc(0, y, 38 - abs(i - 2) * 3, 8, 15, 165, color=pal["shell_dark"], width=4)
        p.ellipse(-30, -120, 9, 18, fill=pal["highlight"], outline=None, width=0)
    r.add(PartDef("torso", "pelvis", (0, 0), 2, _const_bbox((-130, -190, 130, 25)), body))

    def upper(p: Pen, v):
        p.line([(0, 0), (0, 56)], color=OUTLINE, width=15)
        p.line([(0, 0), (0, 56)], color=limbs, width=9)
    def fore(p: Pen, v):
        p.line([(0, 0), (0, 48)], color=OUTLINE, width=14)
        p.line([(0, 0), (0, 48)], color=limbs, width=8)
        for a in (-30, 0, 30):
            x, y = math.sin(math.radians(a)) * 16, 56 + math.cos(math.radians(a)) * 10
            p.line([(0, 50), (x, y)], color=OUTLINE, width=9)
            p.line([(0, 50), (x, y)], color=limbs, width=5)
        p.circle(0, 52, 10, fill=limbs, width=4)
    for side, s in (("L", -1), ("R", 1)):
        r.add(PartDef(f"upper_{side}", "torso", (s * 52, -132), 3, _const_bbox((-25, -15, 25, 70)), upper))
        r.add(PartDef(f"fore_{side}", f"upper_{side}", (0, 56), 4, _const_bbox((-30, -12, 30, 75)), fore))
        r.hands[side] = (f"fore_{side}", (0, 56))

    def antenna(p: Pen, v):
        side = -1 if v == "L" else 1
        pts = [(side * math.sin(t / 10 * 1.4) * 60, -t * 15 + (t * t) * 0.6) for t in range(11)]
        p.line(pts, color=OUTLINE, width=10)
        p.line(pts, color=limbs, width=5)
        p.circle(pts[-1][0], pts[-1][1], 7, fill=pal["shell"], width=3)
    for side, s in (("L", -1), ("R", 1)):
        r.add(PartDef(f"antenna_{side}", "head", (s * 20, -100), 5,
                      _const_bbox((-75, -120, 75, 10)), antenna, side))

    def head(p: Pen, v):
        p.ellipse(0, -56, 62, 56, fill=pal["head"], width=6)
        p.ellipse(-24, -92, 14, 8, fill=pal["highlight"], outline=None, width=0)
        for s in (-1, 1):   # little mandibles
            p.poly([(s * 30, -12), (s * 18, 2), (s * 10, -8)], fill=pal["shell_dark"], width=3)
    r.add(PartDef("head", "torso", (0, -158), 6, _const_bbox((-80, -125, 80, 15)), head))

    fs = FaceSpec(eye_dx=25, eye_rx=19, eye_ry=23, lid=pal["head"], brow_color=pal["brows"], brow_w=11,
                  brow_len=34, mouth_w=62, lips=pal["shell_dark"], outline_w=4.5)
    r.face = fs
    _add_face(r, fs, eyes=(0, -66), brows=(0, -100), mouth=(0, -30))
    return r


BUILDERS = {"wife": build_wife, "husband": build_husband, "roach": build_roach}


@functools.lru_cache(maxsize=None)
def get_rig(name: str) -> Rig:
    if name not in BUILDERS:
        raise KeyError(f"Unknown character '{name}'. Known: {sorted(BUILDERS)}")
    return BUILDERS[name]()


# ----------------------------------------------------------------------------
# Actions: procedural poses (angles in degrees, clockwise positive)
# ----------------------------------------------------------------------------
def _arms(out_L, bend_L, out_R=None, bend_R=None):
    if out_R is None:
        out_R, bend_R = out_L, bend_L
    return {"upper_L": out_L, "fore_L": -bend_L, "upper_R": -out_R, "fore_R": bend_R}


ACTIONS = [
    "idle", "talk", "walk", "run", "tremble", "scream", "jump", "hips", "point_L", "point_R",
    "hold_up", "wind_up", "read", "shrug", "eat", "sit", "freeze", "cross_arms", "dance",
    "chase", "crouch", "wave",
]


def pose(action: str, t: float, T: float, phase: float = 0.0) -> dict:
    """t: seconds since the action started; T: global episode time."""
    s = math.sin
    b = s(2 * math.pi * 0.45 * T + phase)
    P = {"torso": 0.0, "head": s(0.6 * T + phase) * 2.0, "leg_L": 0.0, "leg_R": 0.0, "dx": 0.0, "dy": b * 3}
    P.update(_arms(6 + b * 2, 8))
    if action == "talk":
        P["head"] += s(2 * math.pi * 1.4 * T) * 3.5
        P.update(_arms(8 + b * 2, 10, 24 + s(2 * math.pi * 0.9 * T) * 12, 60 + s(2 * math.pi * 0.9 * T) * 20))
    elif action in ("walk", "run", "chase"):
        f, amp = (1.8, 22) if action == "walk" else (3.2, 36)
        ph = 2 * math.pi * f * t
        P["leg_L"], P["leg_R"] = s(ph) * amp, -s(ph) * amp
        P["dy"] = -abs(s(ph)) * (10 if action == "walk" else 24)
        P["torso"] = 0 if action == "walk" else 6
        if action == "walk":
            P.update(_arms(8 + s(ph) * 16, 15, 8 - s(ph) * 16, 15))
        else:
            P.update(_arms(30 + s(ph) * 30, 80, 30 - s(ph) * 30, 80))
        if action == "chase":
            P.update({"upper_R": -160 + s(ph * 1.0) * 25, "fore_R": 20})
    elif action == "tremble":
        P["dx"] = s(2 * math.pi * 17 * T) * 5
        P["leg_L"], P["leg_R"] = 6 + s(2 * math.pi * 15 * T) * 3, -6
        P.update(_arms(28, 122))
        P["head"] = s(2 * math.pi * 11 * T) * 2
    elif action == "scream":
        w = s(2 * math.pi * 7 * T) * 9
        P.update(_arms(152 + w, 12, 152 - w, 12))
        P["dx"] = s(2 * math.pi * 21 * T) * 4
        P["head"] = -4 + s(2 * math.pi * 13 * T) * 3
    elif action == "jump":
        P["leg_L"], P["leg_R"] = 28, -28
        P.update(_arms(130, 20))
    elif action == "hips":
        P.update(_arms(44, 100))
        P["head"] = 6 + s(0.8 * T) * 2
    elif action == "point_L":
        P.update({"upper_L": 92, "fore_L": -4})
    elif action == "point_R":
        P.update({"upper_R": -92, "fore_R": 4})
    elif action == "hold_up":
        P.update({"upper_R": -128 + s(2 * math.pi * 1.2 * T) * 4, "fore_R": -22})
    elif action == "wind_up":
        P.update(_arms(44, 100, 158 + s(2 * math.pi * 1.5 * T) * 6, 42))
        P["head"] = 4
        P["torso"] = -3
    elif action == "read":
        P.update(_arms(24, 128))
        P["head"] = 5
    elif action == "shrug":
        P.update(_arms(48, 112))
        P["head"] = 8
        P["dy"] -= 6
    elif action == "eat":
        cyc = (t % 1.6) / 1.6
        lift = math.sin(math.pi * min(1, cyc / 0.55)) if cyc < 0.55 else 0
        P.update({"upper_R": -(25 + lift * 15), "fore_R": 85 + lift * 60})
        P["head"] = lift * -4
    elif action == "sit":
        P["leg_L"], P["leg_R"] = 72, -72
        P["dy"] = 64
    elif action == "freeze":
        P["dy"] = 0
        P["head"] = 0
    elif action == "cross_arms":
        P.update(_arms(18, 138))
    elif action == "dance":
        ph = 2 * math.pi * 2.0 * t
        P["torso"] = s(ph) * 9
        P["dx"] = s(ph) * 10
        P.update(_arms(110 + s(ph) * 30, 30, 110 - s(ph) * 30, 30))
        P["leg_L"], P["leg_R"] = s(ph) * 10, s(ph) * 10
    elif action == "crouch":
        P["leg_L"], P["leg_R"] = 34, -34
        P["dy"] = 50
        P.update(_arms(30, 110))
    elif action == "wave":
        P.update({"upper_R": -140, "fore_R": s(2 * math.pi * 2.5 * t) * 25})
    P["antenna_L"] = 6 + s(2 * math.pi * 0.7 * T + phase) * 8
    P["antenna_R"] = -6 - s(2 * math.pi * 0.7 * T + phase + 1) * 8
    return P


# ----------------------------------------------------------------------------
# Rendering a posed character
# ----------------------------------------------------------------------------
@functools.lru_cache(maxsize=20000)
def _xform(rig_name: str, part: str, variant: str, k_q: int, ang_q: int):
    rig = get_rig(rig_name)
    spr = rig.sprite(part, variant)
    k = k_q / 100.0
    f = k / spr.res
    w, h = spr.img.size
    W, H = max(1, int(round(w * f))), max(1, int(round(h * f)))
    img = spr.img.resize((W, H), Image.BILINEAR if f > 0.6 else Image.LANCZOS)
    px, py = spr.px * W / w, spr.py * H / h
    if ang_q == 0:
        return img, px, py
    a = math.radians(ang_q)
    rot = img.rotate(-ang_q, resample=Image.BICUBIC, expand=True)
    vx, vy = px - W / 2, py - H / 2
    rx, ry = vx * math.cos(a) - vy * math.sin(a), vx * math.sin(a) + vy * math.cos(a)
    return rot, rot.size[0] / 2 + rx, rot.size[1] / 2 + ry


def _rot(x, y, deg):
    a = math.radians(deg)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


def world_transforms(rig: Rig, angles: dict) -> dict:
    """Return {part: (x, y, angle)} with pivots in design units, origin at the feet."""
    out = {}

    def solve(name):
        if name in out:
            return out[name]
        d = rig.parts[name]
        if d.parent is None:
            res = (d.offset[0] + angles.get("dx", 0), d.offset[1] + angles.get("dy", 0), angles.get(name, 0.0))
        else:
            px, py, pa = solve(d.parent)
            ox, oy = _rot(d.offset[0], d.offset[1], pa)
            res = (px + ox, py + oy, pa + angles.get(name, 0.0))
        out[name] = res
        return res

    for n in rig.parts:
        solve(n)
    return out


def hand_position(rig: Rig, xf: dict, hand: str):
    part, (lx, ly) = rig.hands[hand]
    x, y, a = xf[part]
    ox, oy = _rot(lx, ly, a)
    return x + ox, y + oy, a


def render_character(name: str, state: dict, k: float, T: float, props_draw=None):
    """Render a character layer.

    state: {action, action_t, expr, look, mouth (override), variants{}, phase}
    k: pixels per design unit (actor scale x camera zoom)
    Returns (RGBA layer, anchor_x, anchor_y) where anchor is the feet origin.
    """
    rig = get_rig(name)
    angles = pose(state.get("action", "idle"), state.get("action_t", 0.0), T, state.get("phase", 0.0))
    angles.update(state.get("angle_overrides", {}))
    xf = world_transforms(rig, angles)

    expr = state.get("expr", "neutral")
    eyes, brows, mouth = EXPRESSIONS.get(expr, EXPRESSIONS["neutral"])
    # blink every few seconds unless eyes are already closed/happy
    ph = state.get("phase", 0.0)
    if eyes in ("open", "wide", "half") and ((T + ph * 1.7) % 3.9) < 0.11 and not state.get("no_blink"):
        eyes = "closed"
    if state.get("mouth"):
        mouth = state["mouth"]
    variants = {"eyes": f"{eyes}:{state.get('look', 'center')}", "brows": brows, "mouth": mouth,
                "antenna_L": "L", "antenna_R": "R"}
    variants.update(state.get("variants", {}))

    x0, y0, x1, y1 = rig.extent
    W, H = int((x1 - x0) * k) + 2, int((y1 - y0) * k) + 2
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ax, ay = -x0 * k, -y0 * k
    k_q = max(5, int(round(k * 100)))
    order = sorted(rig.parts.values(), key=lambda d: d.z)
    held = state.get("hold") or {}
    for d in order:
        if d.name == "pelvis":
            continue
        variant = variants.get(d.name, d.default_variant)
        x, y, a = xf[d.name]
        img, px, py = _xform(rig.name, d.name, variant, k_q, int(round(a)) % 360)
        layer.alpha_composite(img, (int(round(ax + x * k - px)), int(round(ay + y * k - py))))
        if props_draw and d.name in (rig.hands.get("L", ("",))[0], rig.hands.get("R", ("",))[0]):
            for hand, prop in held.items():
                if rig.hands[hand][0] == d.name:
                    hx, hy, ha = hand_position(rig, xf, hand)
                    props_draw(layer, prop, ax + hx * k, ay + hy * k, ha, k)
    return layer, ax, ay
