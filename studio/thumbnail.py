"""Reel cover thumbnails: a key frame from the episode plus a bold title treatment.

Layout keeps text out of the zones Facebook/Instagram cover with UI
(bottom ~25% and the right edge), and stays readable when Facebook
crops the grid preview to the centre.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import config, episode, render
from .draw import font

SERIES = "THE ROACH RUNS THIS HOUSE"


def _fit_lines(text, max_w, start=150, min_size=70):
    words = text.upper().split()
    size = start
    while size >= min_size:
        f = font(size)
        lines, cur = [], ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if f.getlength(trial) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        if len(lines) <= 3 and all(f.getlength(l) <= max_w for l in lines):
            return lines, f, size
        size -= 6
    return lines, font(min_size), min_size


def make_thumbnail(ep_dir: Path, out: Path | None = None, at: float | None = None) -> Path:
    ep = episode.load(ep_dir)
    P = episode.plan(ep)
    fr = render.FrameRenderer(P)
    t = at if at is not None else ep.get("thumbnail_at", ep.get("cover_at", 1.0))
    frame = fr.render(int(t * config.FPS)).convert("RGBA")
    W, H = frame.size
    by0 = 110
    title = ep.get("thumbnail_text", ep["title"])
    lines, f, size = _fit_lines(title, W - 120, start=130)
    title_top = by0 + 120
    title_end = title_top + int(size * 1.08) * len(lines)
    # scene shrunk and dropped down so the title never covers a face;
    # the space above is filled with a blurred, enlarged copy of the frame
    img = frame.resize((int(W * 1.3), int(H * 1.3))).crop((int(W * 0.15), 0, int(W * 0.15) + W, H))
    img = img.filter(ImageFilter.GaussianBlur(28))
    oy_target = title_end + 40
    sc = (H - 50 - oy_target) / H
    fg = frame.resize((int(W * sc), int(H * sc)), Image.LANCZOS)
    mask = Image.new("L", fg.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, fg.size[0], fg.size[1]], radius=48, fill=255)
    border = Image.new("RGBA", (fg.size[0] + 16, fg.size[1] + 16), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle([0, 0, border.size[0], border.size[1]], radius=56, fill=(30, 20, 16, 255))
    ox, oy = (W - fg.size[0]) // 2, oy_target
    img.alpha_composite(border, (ox - 8, oy - 8))
    img.paste(fg, (ox, oy), mask)

    # darken the top so the title pops
    grad = Image.new("L", (1, H))
    for y in range(H):
        grad.putpixel((0, y), int(max(0, 170 * (1 - y / (H * 0.35)))))
    shade = Image.new("RGBA", (W, H), (20, 10, 30, 255))
    shade.putalpha(grad.resize((W, H)))
    img = Image.alpha_composite(img, shade)

    d = ImageDraw.Draw(img)
    # series badge
    sf = font(44)
    sw = sf.getlength(SERIES)
    bx0 = (W - sw) / 2 - 34
    d.rounded_rectangle([bx0, by0, bx0 + sw + 68, by0 + 78], radius=39, fill=(139, 58, 30, 255),
                        outline=(30, 20, 16, 255), width=6)
    d.text((W / 2, by0 + 39), SERIES, font=sf, fill="#FFE45C", anchor="mm")

    # episode title, big and outlined
    y = title_top
    for i, line in enumerate(lines):
        col = "#FFFFFF" if i < len(lines) - 1 else "#F6A8D3"
        d.text((W / 2 + 6, y + 8), line, font=f, fill=(30, 20, 16, 200), anchor="ma",
               stroke_width=max(8, size // 9), stroke_fill=(30, 20, 16, 200))
        d.text((W / 2, y), line, font=f, fill=col, anchor="ma", stroke_width=max(8, size // 9),
               stroke_fill=(30, 20, 16))
        y += int(size * 1.08)

    # episode tag above the bottom UI zone
    tag = f"EP {ep.get('episode', '')}"
    tf = font(48)
    d.rounded_rectangle([ox + 30, oy + 30, ox + 80 + tf.getlength(tag), oy + 110], radius=20, fill=(62, 142, 74, 255),
                        outline=(30, 20, 16, 255), width=5)
    d.text((ox + 55, oy + 70), tag, font=tf, fill="#FFFFFF", anchor="lm")

    out = Path(out or config.BUILD_DIR / ep["id"] / "thumbnail.jpg")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, quality=92)
    return out
