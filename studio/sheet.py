"""Model sheet: renders every character in every expression and key pose for review."""
from __future__ import annotations

from PIL import Image, ImageDraw

from . import config, rigs
from .draw import font


def _tile(name, state, k, size, bg):
    tile = Image.new("RGBA", size, bg)
    layer, ax, ay = rigs.render_character(name, state, k, T=0.37)
    x = int(size[0] / 2 - ax)
    y = int(size[1] - 40 - ay)
    tile.alpha_composite(layer, (x, y))
    return tile


def model_sheet(path=None):
    path = path or (config.CHARACTERS_DIR / "model_sheet.png")
    exprs = list(rigs.EXPRESSIONS)
    poses = ["idle", "hips", "scream", "tremble", "read", "wind_up", "shrug", "point_R"]
    cols = 8
    tw, th = 300, 420
    rows_per_char = (len(exprs) + len(poses) + cols - 1) // cols
    W = cols * tw
    H = 3 * (rows_per_char * th + 70) + 120
    sheet = Image.new("RGBA", (W, H), "#FBF6EC")
    d = ImageDraw.Draw(sheet)
    d.text((24, 24), "THE ROACH RUNS THIS HOUSE - model sheet (DRAFT v0.1 - needs approval)", font=font(44), fill="#2A1A12")
    y = 110
    for name, k in (("wife", 0.33), ("husband", 0.32), ("roach", 0.62)):
        d.text((24, y), rigs.bible()[name]["display_name"].upper(), font=font(40), fill="#5E3594")
        y += 60
        items = [("expr", e) for e in exprs] + [("pose", p) for p in poses]
        for i, (kind, val) in enumerate(items):
            state = {"expr": val, "action": "idle"} if kind == "expr" else {"expr": "neutral", "action": val}
            if kind == "pose" and val in ("scream", "tremble"):
                state["expr"] = "screaming" if val == "scream" else "scared"
            if kind == "pose" and val == "wind_up":
                state["expr"] = "determined"
            bg = "#FFFFFF" if kind == "expr" else "#F0E8FF"
            tile = _tile(name, state, k, (tw - 10, th - 40), bg)
            cx, cy = (i % cols) * tw + 5, y + (i // cols) * th
            sheet.alpha_composite(tile, (cx, cy))
            d.text((cx + 8, cy + th - 38), val, font=font(26), fill="#2A1A12")
        y += rows_per_char * th + 10
    sheet.convert("RGB").save(path)
    return path
