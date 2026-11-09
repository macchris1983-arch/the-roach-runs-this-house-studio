"""Build a voice-audition reel: one title card per take with its audio, grouped by character."""
import glob, os, subprocess
from PIL import Image, ImageDraw, ImageFont
D = "episodes/season-03-cant-get-rid-of-him/voices"
TMP = os.environ.get("TMP_DIR", "/tmp/aud"); os.makedirs(TMP, exist_ok=True)
BLACK = subprocess.run(["fc-match", "-f", "%{file}", "Inter Display:style=Black"], capture_output=True, text=True).stdout
BOLD = "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"
order = ["roach", "husband", "wife", "son", "daughter", "cousin", "grandma"]
files = sorted(glob.glob(f"{D}/*.mp4"), key=lambda f: (order.index(os.path.basename(f).split("-")[1]), f))
segs, count = [], {}
for f in files:
    who, voice = os.path.basename(f)[3:-4].split("-", 1)
    count[who] = count.get(who, 0) + 1
    letter = "ABCDE"[count[who] - 1]
    im = Image.new("RGB", (720, 1280), (22, 10, 38)); d = ImageDraw.Draw(im)
    def c(y, s, font, fill):
        d.text(((720 - d.textlength(s, font=font)) / 2, y), s, font=font, fill=fill)
    c(430, who.upper(), ImageFont.truetype(BLACK, 110), (255, 196, 47))
    c(580, f"Option {letter}", ImageFont.truetype(BLACK, 80), (255, 255, 255))
    c(700, f"CapCut voice: {voice.replace('_', ' ')}", ImageFont.truetype(BOLD, 38), (200, 200, 220))
    png = f"{TMP}/{who}{letter}.png"; im.save(png)
    out = f"{TMP}/{who}{letter}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", png, "-i", f, "-af", "apad=pad_dur=0.8",
                    "-shortest", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-ar", "48000", "-ac", "2", out], check=True)
    segs.append(out)
with open(f"{TMP}/l.txt", "w") as fh:
    fh.writelines(f"file '{s}'\n" for s in segs)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{TMP}/l.txt", "-c", "copy",
                f"{D}/voice-auditions.mp4"], check=True)
print("DONE", len(segs))
