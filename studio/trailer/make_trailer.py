"""Build the first trailer for The Roach Runs This House from existing approved assets.
All inputs are already in this repo; output: episodes/season-03-cant-get-rid-of-him/video/trailer-v1.mp4
Music is a simple original beat synthesized here (no outside audio)."""
import os, subprocess, wave, numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
V = f"{R}/episodes/season-03-cant-get-rid-of-him/video"
REF = f"{R}/assets/characters/reference-3d"
TMP = os.environ.get("TMP_DIR", "/tmp/trailer"); os.makedirs(TMP, exist_ok=True)
W, H, FPS, SR = 720, 1280, 30, 48000
BLACK = "/usr/share/fonts/truetype/inter/InterDisplay-Black.ttf"
for c in ["/usr/share/fonts/truetype/inter/InterDisplay-Black.ttf", "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"]:
    if os.path.exists(c): BLACK = c
if not os.path.exists(BLACK):
    BLACK = subprocess.run(["fc-match", "-f", "%{file}", "Inter Display:style=Black"], capture_output=True, text=True).stdout
BOLD = "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"
GOLD, PURPLE, WHITE = (255, 196, 47), (124, 58, 237), (255, 255, 255)

def bg():
    y = np.linspace(0, 1, H)[:, None]
    top, bot = np.array([28, 12, 48]), np.array([8, 4, 14])
    a = (top * (1 - y) + bot * y)[:, :, None].repeat(W, 1).transpose(0, 1, 2)
    a = np.broadcast_to((top * (1 - y) + bot * y)[:, None, :], (H, W, 3)).astype(np.uint8)
    return Image.fromarray(a.copy())

def text_center(d, y, s, font, fill, stroke=0):
    w = d.textlength(s, font=font)
    d.text(((W - w) / 2, y), s, font=font, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))

def card(lines, name):
    im = bg(); d = ImageDraw.Draw(im)
    total = sum(sz + 18 for _, sz, _ in lines); y = (H - total) / 2
    for s, sz, col in lines:
        text_center(d, y, s, ImageFont.truetype(BLACK, sz), col); y += sz + 18
    p = f"{TMP}/{name}.png"; im.save(p); return p

def cast(sheet, title, tag, name, crop=None):
    im = bg(); d = ImageDraw.Draw(im)
    sh = Image.open(f"{REF}/{sheet}").convert("RGB")
    if crop: sh = sh.crop(crop)
    sh = sh.resize((W - 40, int(sh.height * (W - 40) / sh.width)), Image.LANCZOS)
    y0 = (H - sh.height) // 2 - 40
    im.paste(sh, (20, y0))
    text_center(d, y0 - 150, title, ImageFont.truetype(BLACK, 76), GOLD, 3)
    text_center(d, y0 + sh.height + 50, tag, ImageFont.truetype(BOLD, 44), WHITE, 2)
    p = f"{TMP}/{name}.png"; im.save(p); return p

def title_card(name):
    im = bg(); d = ImageDraw.Draw(im)
    sh = Image.open(f"{REF}/roach-3d-sheet.png").convert("RGB")
    roach = sh.crop((150, 5, 290, 228)).resize((376, 600), Image.LANCZOS)   # front view
    a = np.asarray(roach).astype(int); white = (a.min(2) > 225) & (np.ptp(a, 2) < 25)
    m = Image.fromarray(np.where(white, 0, 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.2))
    im.paste(roach, ((W - 376) // 2, 520), m)
    for i, (s, sz, col) in enumerate([("THE ROACH", 110, GOLD), ("RUNS THIS", 92, WHITE), ("HOUSE", 130, GOLD)]):
        text_center(d, [110, 240, 345][i], s, ImageFont.truetype(BLACK, sz), col, 4)
    text_center(d, 1150, "COMING SOON", ImageFont.truetype(BOLD, 46), WHITE, 2)
    p = f"{TMP}/{name}.png"; im.save(p); return p

# ---- timeline: (kind, src, start, dur)
cards = {
 "c1": card([("THEY TRIED", 92, WHITE), ("SLIPPERS.", 120, GOLD)], "c1"),
 "c2": card([("BUG BOMBS.", 86, WHITE), ("THE DOG.", 86, WHITE), ("THE EXTERMINATOR.", 64, GOLD)], "c2"),
 "g":  cast("grandma-husbands-mom-3d-sheet.png", "GRANDMA", "\"My best customer.\"", "g"),
 "k":  cast("cousin-human-3d-sheet.png", "THE COUSIN", "\"He on payroll.\"", "k"),
 "b":  cast("brutus-rottweiler-3d-sheet.png", "BRUTUS", "\"We don't talk about Brutus.\"", "b", crop=(300, 25, 552, 200)),
 "s":  cast("supporting-cast-3d-sheet.png", "THE WHOLE BLOCK", "Tasha · Mr. Baines · Pearl", "s"),
 "c3": card([("ON MY MAMA...", 80, WHITE), ("HE AIN'T", 110, GOLD), ("GOING", 110, GOLD), ("NOWHERE.", 110, GOLD)], "c3"),
 "t":  title_card("t"),
}
TL = [("card", "c1", 0, 1.8),
      ("clip", f"{V}/e00-clip1-subtitled.mp4", 0.0, 2.4),
      ("clip", f"{V}/e00-clip1-subtitled.mp4", 4.1, 4.6),
      ("card", "c2", 0, 2.0),
      ("card", "g", 0, 1.6), ("card", "k", 0, 1.6), ("card", "b", 0, 1.6), ("card", "s", 0, 1.6),
      ("clip", f"{V}/e00-clip2-subtitled.mp4", 0.0, 6.0),
      ("card", "c3", 0, 2.2),
      ("card", "t", 0, 3.5)]

segs, voice, t = [], [], 0.0
for i, (kind, src, st, du) in enumerate(TL):
    out = f"{TMP}/seg{i:02d}.mp4"
    if kind == "card":
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", cards[src], "-t", str(du), "-r", str(FPS),
                        "-vf", "format=yuv420p,fade=in:0:4,fade=out:st=%.2f:d=0.15" % (du - 0.15), "-c:v", "libx264", "-preset", "veryfast", out], check=True)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(st), "-t", str(du), "-i", src, "-r", str(FPS),
                        "-vf", f"scale={W}:{H},format=yuv420p", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", out], check=True)
        a = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(st), "-t", str(du), "-i", src, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True).stdout
        voice.append((t, np.frombuffer(a, np.float32)))
    segs.append((out, kind, t, du)); t += du
TOTAL = t

# ---- original beat (~96 bpm bounce), ducked under dialogue
n = int(TOTAL * SR) + SR; mus = np.zeros(n, np.float32); beat = 60 / 96
def kick(): tt = np.arange(int(.25 * SR)) / SR; return np.sin(2 * np.pi * (50 + 90 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 9)
def snare(): tt = np.arange(int(.18 * SR)) / SR; return np.random.default_rng(1).normal(0, .5, tt.size) * np.exp(-tt * 22)
def hat(): tt = np.arange(int(.05 * SR)) / SR; return np.random.default_rng(2).normal(0, .25, tt.size) * np.exp(-tt * 80)
def bass(f, d): tt = np.arange(int(d * SR)) / SR; return np.tanh(2 * np.sin(2 * np.pi * f * tt)) * .35 * np.exp(-tt * 2.5)
def add(sig, at):
    i = int(at * SR); j = min(n, i + sig.size); mus[i:j] += sig[: j - i]
notes = [43.65, 43.65, 51.91, 38.89]   # F1, F1, G#1, D#1
b = 0; s = 0.0
while s < TOTAL + 1:
    add(kick(), s)
    if b % 4 in (1, 3): add(snare(), s)
    if b % 2 == 0: add(bass(notes[(b // 4) % 4], beat * 1.8), s)
    for k in range(2): add(hat(), s + k * beat / 2)
    s += beat; b += 1
duck = np.ones(n, np.float32)
for (o, kind, st, du) in segs:
    if kind == "clip": duck[int(st * SR): int((st + du) * SR)] = 0.22
duck = np.convolve(duck, np.ones(2400) / 2400, mode="same")
mix = mus * 0.45 * duck
for st, a in voice:
    i = int(st * SR); mix[i:i + a.size] += a[: n - i]
mix = mix[: int(TOTAL * SR)]
fade = int(1.0 * SR); mix[-fade:] *= np.linspace(1, 0, fade)
mix /= max(1.0, np.abs(mix).max() / 0.95)
with wave.open(f"{TMP}/mix.wav", "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((mix * 32767).astype("<i2").tobytes())

with open(f"{TMP}/list.txt", "w") as f:
    for o, *_ in segs: f.write(f"file '{o}'\n")
OUT = f"{V}/trailer-v1.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{TMP}/list.txt", "-i", f"{TMP}/mix.wav",
                "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-shortest", OUT], check=True)
print("DONE", OUT, round(TOTAL, 2), "s")
