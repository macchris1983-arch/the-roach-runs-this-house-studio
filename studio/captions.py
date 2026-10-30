"""Captions: phrase-sized subtitle cues as SRT (for upload) and ASS (burned in)."""
from __future__ import annotations

import re
from pathlib import Path

from . import config
from .draw import font_family

SPEAKER_COLORS = {"wife": "#F6A8D3", "husband": "#8FE39B", "roach": "#FFB36B"}
MAX_CHARS = 22   # per caption row
MAX_ROWS = 2


def _rows(words, limit=MAX_CHARS):
    rows, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > limit:
            rows.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        rows.append(cur)
    return rows


def cues_for_line(line, min_dur=0.6):
    """Split one dialogue line into on-screen cues (max 2 rows of ~22 chars),
    timed proportionally to text length across the spoken audio."""
    words = line.text.split()
    rows = _rows(words)
    groups = [rows[i:i + MAX_ROWS] for i in range(0, len(rows), MAX_ROWS)]
    total_chars = sum(len(" ".join(g)) for g in groups) or 1
    dur = max(min_dur, line.end - line.start)
    t = line.start
    cues = []
    for g in groups:
        txt = "\n".join(g)
        d = dur * len(" ".join(g)) / total_chars
        cues.append({"line": line.id, "who": line.who, "start": t, "end": t + max(d, min_dur if len(groups) == 1 else 0.3),
                     "text": txt})
        t += d
    return cues


def build_cues(plan, linger=0.25):
    cues = []
    for ln in plan.lines:
        cues.extend(cues_for_line(ln))
    # let each cue linger a little, without overlapping the next or the end
    for a, b in zip(cues, cues[1:]):
        a["end"] = min(max(a["end"], a["end"] + linger), b["start"] - 0.02)
    if cues:
        cues[-1]["end"] = min(cues[-1]["end"] + linger, plan.duration - 0.05)
    return cues


def _ts_srt(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ts_ass(t):
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def write_srt(cues, path: Path):
    out = []
    for i, c in enumerate(cues, 1):
        out.append(f"{i}\n{_ts_srt(c['start'])} --> {_ts_srt(c['end'])}\n{c['text']}\n")
    path.write_text("\n".join(out), encoding="utf-8")


def _ass_color(hexcol):
    h = hexcol.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def write_ass(cues, path: Path):
    margin_v = int(config.HEIGHT * config.CAPTION_SAFE_BOTTOM)
    fam = font_family(True)
    styles = []
    for who, col in SPEAKER_COLORS.items():
        styles.append(f"Style: {who},{fam},96,{_ass_color(col)},&H000000FF,&H00140E0C,&H96000000,"
                      f"-1,0,0,0,100,100,0,0,1,8,3,2,60,60,{margin_v},1")
    events = []
    for c in cues:
        txt = c["text"].replace("\n", "\\N")
        pop = "{\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)}"
        events.append(f"Dialogue: 0,{_ts_ass(c['start'])},{_ts_ass(c['end'])},{c['who'].split('@')[0]},,0,0,0,,{pop}{txt}")
    doc = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {config.WIDTH}
PlayResY: {config.HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{chr(10).join(styles)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{chr(10).join(events)}
"""
    path.write_text(doc, encoding="utf-8")


def parse_srt(path: Path):
    blocks = re.split(r"\n\s*\n", Path(path).read_text(encoding="utf-8").strip())
    out = []

    def secs(s):
        h, m, rest = s.split(":")
        sec, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000

    for b in blocks:
        lines = b.strip().splitlines()
        if len(lines) < 3:
            continue
        a, _, z = lines[1].partition(" --> ")
        out.append({"start": secs(a.strip()), "end": secs(z.strip()), "text": "\n".join(lines[2:])})
    return out
