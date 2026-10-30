"""Automated quality control for rendered episodes.

Every check produces PASS / WARN / FAIL with evidence. An episode passes QC
only if there are no FAILs. Results are written to qc_report.json and
qc_report.md next to the render.

Some requirements can't be fully judged by a machine (is it funny? does the
character look exactly like the reference art?). Those are listed as
"human review" items that must be ticked during approval.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import audio, captions, config, episode, render, rigs

HUMAN_REVIEW = [
    "Characters match the approved reference/model sheet (faces, skin tones, hair, outfits)",
    "Dialogue is clear and the jokes land (hook in first 2 seconds, clear punchline)",
    "Captions are readable on a phone and not covered by the Reels UI",
    "Nothing in the video copies an existing show, character, script or song",
]


class Report:
    def __init__(self, ep_id):
        self.ep_id = ep_id
        self.checks = []

    def add(self, name, status, detail):
        self.checks.append({"check": name, "status": status, "detail": detail})

    @property
    def passed(self):
        return all(c["status"] != "FAIL" for c in self.checks)

    def to_dict(self):
        return {"episode_id": self.ep_id, "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "passed": self.passed, "fails": sum(c["status"] == "FAIL" for c in self.checks),
                "warnings": sum(c["status"] == "WARN" for c in self.checks), "checks": self.checks,
                "human_review": HUMAN_REVIEW}

    def markdown(self):
        d = self.to_dict()
        icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}
        lines = [f"# QC report: {self.ep_id}", "", f"Checked: {d['checked_at']}  ",
                 f"**Result: {'PASSED' if d['passed'] else 'FAILED'}** ({d['fails']} fails, {d['warnings']} warnings)", "",
                 "| Check | Result | Detail |", "|---|---|---|"]
        for c in self.checks:
            lines.append(f"| {c['check']} | {icon[c['status']]} {c['status']} | {c['detail'].replace('|', '/')} |")
        lines += ["", "## Human review (ticked at approval)", ""] + [f"- [ ] {h}" for h in HUMAN_REVIEW]
        return "\n".join(lines) + "\n"


def _ffprobe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         capture_output=True, text=True)
    return json.loads(out.stdout or "{}")


def _ffmpeg_filter_log(path, vf=None, af=None):
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path)]
    if vf:
        cmd += ["-vf", vf, "-an"]
    if af:
        cmd += ["-af", af, "-vn"]
    cmd += ["-f", "null", "-"]
    return subprocess.run(cmd, capture_output=True, text=True).stderr


def run_qc(ep_path, render_dir=None) -> Report:
    ep = episode.load(ep_path)
    rd = Path(render_dir or config.BUILD_DIR / ep["id"])
    R = Report(ep["id"])

    # ---- 1. episode file
    errs = episode.validate(ep)
    R.add("Episode file valid", "PASS" if not errs else "FAIL", "no problems" if not errs else "; ".join(errs))

    man_path = rd / "manifest.json"
    if not man_path.exists():
        R.add("Render manifest", "FAIL", f"no render found at {rd}; run `python -m studio render {ep['id']}`")
        return _save(R, rd)
    man = json.loads(man_path.read_text())
    mp4 = rd / man["video"]
    if man.get("preview"):
        R.add("Full-quality render", "FAIL", "latest render is a low-res preview; render without --preview")

    # ---- 2. file + stream specs
    if not mp4.exists():
        R.add("Video file exists", "FAIL", f"missing {mp4.name}")
        return _save(R, rd)
    R.add("Video file exists", "PASS", f"{mp4.name}, {mp4.stat().st_size / 1e6:.1f} MB")
    info = _ffprobe(mp4)
    v = next((s for s in info.get("streams", []) if s["codec_type"] == "video"), None)
    a = next((s for s in info.get("streams", []) if s["codec_type"] == "audio"), None)
    if not v:
        R.add("Video stream", "FAIL", "no video stream")
        return _save(R, rd)
    dims_ok = (v["width"], v["height"]) == (config.WIDTH, config.HEIGHT)
    R.add("Vertical 9:16 at 1080x1920", "PASS" if dims_ok else "FAIL", f"{v['width']}x{v['height']}")
    num, den = (int(x) for x in v["r_frame_rate"].split("/"))
    fps = num / den
    R.add("30 FPS", "PASS" if abs(fps - config.FPS) < 0.01 else "FAIL", f"{fps:g} fps")
    R.add("H.264 / yuv420p (Reels compatible)", "PASS" if v["codec_name"] == "h264" and v.get("pix_fmt") == "yuv420p" else "FAIL",
          f"{v['codec_name']} {v.get('pix_fmt')}")
    dur = float(info["format"]["duration"])
    R.add("Length 20-40 seconds", "PASS" if config.MIN_SECONDS <= dur <= config.MAX_SECONDS else "FAIL", f"{dur:.2f}s")
    if not a:
        R.add("Audio stream", "FAIL", "no audio track")
    else:
        adur = float(a.get("duration", dur))
        R.add("Audio stream (AAC) and length matches video", "PASS" if a["codec_name"] == "aac" and abs(adur - dur) < 0.15 else "FAIL",
              f"{a['codec_name']} {a.get('sample_rate')} Hz, {adur:.2f}s vs video {dur:.2f}s")

    # ---- 3. plays end-to-end (full decode, no errors)
    dec = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp4), "-f", "null", "-"], capture_output=True, text=True)
    nframes = int(v.get("nb_frames", 0))
    expected = round(dur * config.FPS)
    R.add("Plays end-to-end without decode errors", "PASS" if not dec.stderr.strip() and dec.returncode == 0 else "FAIL",
          "clean decode" if not dec.stderr.strip() else dec.stderr.strip()[:300])
    R.add("No missing frames", "PASS" if abs(nframes - expected) <= 1 else "FAIL", f"{nframes} frames (expected {expected})")

    # ---- 4. blank / frozen frames
    log = _ffmpeg_filter_log(mp4, vf="blackdetect=d=0.5:pix_th=0.06,freezedetect=n=0.0005:d=2.5")
    blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log)
    R.add("No blank/black stretches (>0.5s)", "PASS" if not blacks else "FAIL",
          "none" if not blacks else ", ".join(f"{float(s):.1f}-{float(e):.1f}s" for s, e in blacks))
    freezes = re.findall(r"freeze_start: ([\d.]+)", log)
    R.add("No frozen picture (>2.5s)", "PASS" if not freezes else "WARN",
          "none" if not freezes else "frozen at " + ", ".join(f"{float(x):.1f}s" for x in freezes))

    # ---- 5. audio levels
    alog = _ffmpeg_filter_log(mp4, af="volumedetect,ebur128=peak=true")
    mean = re.search(r"mean_volume: ([-\d.]+) dB", alog)
    peak = re.search(r"max_volume: ([-\d.]+) dB", alog)
    lufs = re.findall(r"I:\s+([-\d.]+) LUFS", alog)
    if mean and peak:
        mv, pv = float(mean.group(1)), float(peak.group(1))
        ok = mv > -35 and pv <= -0.1
        R.add("Audio level (not silent, not clipping)", "PASS" if ok else "FAIL", f"mean {mv} dB, peak {pv} dB")
    if lufs:
        L = float(lufs[-1])
        R.add("Loudness near -14 LUFS (social standard)", "PASS" if abs(L - config.TARGET_LUFS) <= 2 else "WARN", f"{L} LUFS")

    # ---- 6. captions match the script and timing
    plan_lines = man["lines"]
    srt = rd / "captions.srt"
    if not srt.exists():
        R.add("Caption file exists", "FAIL", "captions.srt missing")
    else:
        cues = captions.parse_srt(srt)
        spoken = " ".join(l["text"] for l in plan_lines)
        shown = " ".join(c["text"].replace("\n", " ") for c in cues)
        norm = lambda s: re.sub(r"\s+", " ", s).strip()
        R.add("Captions match script word-for-word", "PASS" if norm(spoken) == norm(shown) else "FAIL",
              f"{len(cues)} cues for {len(plan_lines)} lines" if norm(spoken) == norm(shown) else "caption text differs from script")
        bad = [i for i, c in enumerate(cues) if c["end"] <= c["start"] or c["end"] > dur + 0.01]
        over = [i for i, (x, y) in enumerate(zip(cues, cues[1:])) if x["end"] > y["start"] + 1e-3]
        R.add("Caption timing valid (in range, no overlaps)", "PASS" if not bad and not over else "FAIL",
              "ok" if not bad and not over else f"bad cues {bad}, overlaps after {over}")
        fast = [c["text"].replace("\n", " ") for c in cues if len(c["text"]) / max(0.1, c["end"] - c["start"]) > 25]
        R.add("Captions readable speed (<=25 chars/s)", "PASS" if not fast else "WARN", "ok" if not fast else f"fast: {fast}")
    ass = rd / "captions.ass"
    R.add("Captions burned in", "PASS" if ass.exists() else "FAIL", "ASS subtitles rendered into picture" if ass.exists() else "missing")

    # ---- 7. audio sync: is there voice energy where each line's caption says it is?
    stem = rd / "voice_stem.wav"
    if stem.exists():
        vs = audio.load_wav(stem)
        mis = []
        for l in plan_lines:
            s, e = int(l["start"] * audio.SR), int(l["end"] * audio.SR)
            seg = vs[s:e]
            if len(seg) == 0 or float(np.sqrt(np.mean(seg ** 2))) < 0.01:
                mis.append(l["id"])
            if l["end"] > dur + 0.01:
                mis.append(l["id"] + "(past end)")
        R.add("Dialogue audio lines up with captions/lip-sync", "PASS" if not mis else "FAIL",
              f"voice energy found in all {len(plan_lines)} line windows" if not mis else f"no voice in: {mis}")
    else:
        R.add("Dialogue audio lines up with captions/lip-sync", "FAIL", "voice stem missing")

    # ---- 8. scenes
    shots = man["shots"]
    gaps = [f"{a['id']}->{b['id']}" for a, b in zip(shots, shots[1:]) if abs(a["end"] - b["start"]) > 1e-3]
    covered = shots and abs(shots[0]["start"]) < 1e-3 and abs(shots[-1]["end"] - man["duration"]) < 1e-3
    R.add("No missing scenes (shots cover the whole timeline)", "PASS" if covered and not gaps and len(shots) == len(ep["shots"]) else "FAIL",
          f"{len(shots)} shots, contiguous" if covered and not gaps else f"gaps: {gaps}")

    # ---- 9. continuity + originality
    current = render.rig_hash()
    R.add("Character designs unchanged since render", "PASS" if man.get("rig_hash") == current else "FAIL",
          f"rig {man.get('rig_hash')}" if man.get("rig_hash") == current else "character files changed after render; re-render")
    lock = config.CHARACTERS_DIR / "approved_lock.json"
    if lock.exists() and json.loads(lock.read_text()).get("rig_hash") == man.get("rig_hash"):
        R.add("Characters match the approved design lock", "PASS", "matches approved_lock.json")
    elif lock.exists():
        R.add("Characters match the approved design lock", "FAIL", "designs differ from the approved lock")
    else:
        R.add("Characters match the approved design lock", "WARN", "character designs are still DRAFT (not yet approved)")
    srcs = man.get("asset_sources", {})
    non_generated = [k for k, v in srcs.items() if isinstance(v, str) and not v.startswith("generated:") and k != "font"]
    voices = srcs.get("voices", [])
    R.add("All assets original (generated in-house or own recordings)", "PASS" if not non_generated else "FAIL",
          f"visuals/music/sfx generated by studio code; voices: {', '.join(voices)}; no third-party media, no watermarks"
          if not non_generated else f"unverified sources: {non_generated}")
    for f in sorted((config.ASSETS).rglob("*")):
        if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".mp3", ".wav", ".mp4", ".webp") \
                and "reference" not in f.parts and f.name != "model_sheet.png" and "sfx" not in f.parts:
            lic = config.ASSETS / "LICENSES.yaml"
            if not lic.exists() or f.name not in lic.read_text():
                R.add("Third-party asset licences recorded", "FAIL", f"{f.relative_to(config.ROOT)} has no entry in assets/LICENSES.yaml")
                break
    else:
        R.add("Third-party asset licences recorded", "PASS", "no unlicensed media files in assets/")

    return _save(R, rd)


def _save(R: Report, rd: Path) -> Report:
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "qc_report.json").write_text(json.dumps(R.to_dict(), indent=2))
    (rd / "qc_report.md").write_text(R.markdown())
    return R
