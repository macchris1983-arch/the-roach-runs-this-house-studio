"""Renderer: turns an episode plan into a finished 1080x1920 30 fps MP4 with
mixed audio and burned-in captions, using only Pillow, numpy and FFmpeg."""
from __future__ import annotations

import functools
import hashlib
import json
import math
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps

from . import audio, captions, config, episode, rigs, world

HELD = functools.partial(world.draw_prop, held=True)
TALK_CLOSED = {"smile", "flat", "frown", "smirk", "wavy", "chew", "grimace"}


def rig_hash() -> str:
    """Fingerprint of the character designs (bible + rig code) for continuity checks."""
    h = hashlib.sha256()
    h.update((config.CHARACTERS_DIR / "characters.yaml").read_bytes())
    h.update((Path(__file__).parent / "rigs.py").read_bytes())
    return h.hexdigest()[:16]


def _mouth_for(state, env_val):
    eyes, brows, mouth = rigs.EXPRESSIONS.get(state.get("expr", "neutral"), rigs.EXPRESSIONS["neutral"])
    shout = state.get("expr") in rigs.SHOUT_EXPRESSIONS
    if env_val > 0.55:
        return "scream" if shout else "open_l"
    if env_val > 0.18:
        return "open_l" if shout else "open_s"
    return mouth if mouth in TALK_CLOSED else "flat"


class FrameRenderer:
    def __init__(self, plan: episode.Plan):
        self.plan = plan
        self.frame_lines = {}   # who -> list of (start_frame, env)
        for ln in plan.lines:
            self.frame_lines.setdefault(ln.who, []).append((int(round(ln.start * config.FPS)), ln.env, ln))

    def speaking(self, who, fi):
        for start, env, ln in self.frame_lines.get(who, []):
            if start <= fi < start + len(env):
                return env[fi - start], ln
        return None, None

    def render(self, fi: int) -> Image.Image:
        T = fi / config.FPS
        shot = self.plan.shot_at(T)
        t = T - shot["_start"]
        cam = episode.camera_at(shot, t)
        bg = world.background(shot["background"])
        x0, y0, x1, y1 = cam.view_box()
        r = world.BG_RES
        frame = bg.resize((config.WIDTH, config.HEIGHT), Image.BILINEAR,
                          box=(x0 * r, y0 * r, x1 * r, y1 * r))
        frame = frame.convert("RGBA")

        drawables = []
        for p in shot.get("props") or []:
            st, _ = episode.evaluate({"x": p.get("x", 540), "y": p.get("y", 960), "scale": p.get("scale", 1.0),
                                      "rot": p.get("rot", 0), "z": p.get("z", 5), "visible": p.get("visible", True)},
                                     p.get("keys"), t)
            if st.get("visible", True):
                drawables.append((st["z"], "prop", p["name"], st))
        for i, (name, a) in enumerate((shot.get("actors") or {}).items()):
            base = {"x": a.get("x", 540), "y": a.get("y", 1700), "scale": a.get("scale", 1.0), "rot": 0,
                    "expr": a.get("expr", "neutral"), "action": a.get("action", "idle"), "look": a.get("look", "center"),
                    "flip": a.get("flip", False), "hold": a.get("hold", {}), "z": a.get("z", 10),
                    "visible": a.get("visible", True), "variants": a.get("variants", {})}
            st, astart = episode.evaluate(base, a.get("keys"), t)
            if not st.get("visible", True):
                continue
            st["action_t"] = t - astart
            st["phase"] = i * 1.37
            env, ln = self.speaking(name, fi)
            if env is not None:
                st["mouth"] = _mouth_for(st, env)
                if st["action"] == "idle":
                    st["action"] = "talk"
            drawables.append((st["z"], "actor", name, st))
        drawables.sort(key=lambda d: d[0])
        for _, kind, name, st in drawables:
            k = st["scale"] * cam.zoom
            sx, sy = cam.to_screen(st["x"], st["y"])
            if kind == "prop":
                world.draw_prop(frame, name, sx, sy, st.get("rot", 0), k)
                continue
            layer, ax, ay = rigs.render_character(name, st, k, T, props_draw=HELD)
            if st.get("flip"):
                layer = ImageOps.mirror(layer)
                ax = layer.size[0] - ax
            frame.alpha_composite(layer, (int(round(sx - ax)), int(round(sy - ay))))
        frame = frame.convert("RGB")
        for fx in shot.get("fx") or []:
            if fx["type"] == "shake":
                continue
            ft = t - fx.get("at", 0)
            until = fx.get("until", fx.get("at", 0) + fx.get("dur", 0.6) if fx["type"] not in ("darkness", "vignette") else shot["dur"])
            if 0 <= ft and t < until:
                world.fx_overlay(frame, fx, ft, cam)
        return frame


def measure_lufs(wav) -> float | None:
    """Integrated loudness of a WAV file, measured with FFmpeg's EBU R128 meter."""
    import re
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(wav), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True)
    found = re.findall(r"I:\s+([-\d.]+) LUFS", p.stderr)
    return float(found[-1]) if found else None


def loudnorm_filter(wav) -> str:
    """Two-pass EBU R128 normalisation: measure first, then apply in linear mode
    (one-pass loudnorm switches to 'dynamic' mode and can land 2-3 LU low)."""
    import json as _json
    base = f"loudnorm=I={config.TARGET_LUFS}:TP=-1.5:LRA=11"
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(wav), "-af", base + ":print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    try:
        m = _json.loads(p.stderr[p.stderr.rindex("{"):p.stderr.rindex("}") + 1])
        return (f"{base}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
                f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    except (ValueError, KeyError):
        return base


def _match_loudness(wav, master):
    """Pre-gain the mix towards the target loudness so the final limiter
    doesn't have to guess (single-pass loudnorm undershoots on sparse mixes)."""
    import numpy as np
    L = measure_lufs(wav)
    if L is None or L < -70:
        return master
    gain = 10 ** ((config.TARGET_LUFS - L) / 20)
    out = master * gain
    peak = float(np.max(np.abs(out))) or 1.0
    if peak > 0.89:  # soft-limit peaks instead of clipping
        out = np.tanh(out / 0.89) * 0.89
    return out.astype(master.dtype)


def _run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd[:6])}...\n{p.stderr[-2000:]}")
    return p


def render_episode(ep_path, out_dir=None, preview=False, log=print) -> dict:
    """Render an episode. Returns the render manifest (also saved as manifest.json)."""
    t0 = time.time()
    ep = episode.load(ep_path)
    plan = episode.plan(ep)
    issues = episode.timing_problems(plan)
    if issues:
        raise episode.EpisodeError("Dialogue timing problems:\n  - " + "\n  - ".join(issues))
    out_dir = Path(out_dir or config.BUILD_DIR / ep["id"])
    out_dir.mkdir(parents=True, exist_ok=True)
    fps = config.FPS
    nframes = int(round(plan.duration * fps))
    log(f"[render] {ep['id']} '{ep['title']}': {plan.duration:.1f}s, {nframes} frames, {len(plan.lines)} lines")

    # ---- audio
    voices = [(ln.start, ln.audio, ep.get("voice_gain", 1.0)) for ln in plan.lines]
    fx = [(t, audio.sfx(name), g) for t, name, g in plan.sfx]
    mcfg = ep.get("music") or {}
    track = audio.music(plan.duration, bpm=mcfg.get("bpm", 104), root_midi=mcfg.get("root_midi", 45),
                        mood=mcfg.get("mood", "sneaky_funk"), seed=mcfg.get("seed", 1)) if mcfg.get("enabled", True) else None
    master, vstem = audio.mix(plan.duration, voices, fx, track, mcfg.get("gain", 0.22))
    audio.write_wav(out_dir / "mix.wav", master)
    master = _match_loudness(out_dir / "mix.wav", master)
    audio.write_wav(out_dir / "mix.wav", master)
    audio.write_wav(out_dir / "voice_stem.wav", vstem)

    # ---- captions
    cues = captions.build_cues(plan)
    captions.write_srt(cues, out_dir / "captions.srt")
    captions.write_ass(cues, out_dir / "captions.ass")

    # ---- video
    mp4 = out_dir / ("preview.mp4" if preview else f"{ep['id']}.mp4")
    scale = ["-vf", f"ass={out_dir / 'captions.ass'}" + (",scale=540:960" if preview else "")]
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{config.WIDTH}x{config.HEIGHT}", "-r", str(fps), "-i", "-",
           "-i", str(out_dir / "mix.wav"), *scale,
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "28" if preview else "19", "-pix_fmt", "yuv420p",
           "-r", str(fps), "-g", str(fps * 2),
           "-af", loudnorm_filter(out_dir / "mix.wav"),
           "-c:a", "aac", "-b:a", "192k", "-ar", str(audio.SR),
           "-shortest", "-movflags", "+faststart", str(mp4)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    fr = FrameRenderer(plan)
    try:
        for fi in range(nframes):
            img = fr.render(fi)
            proc.stdin.write(img.tobytes())
            if fi % (fps * 5) == 0:
                log(f"[render]   frame {fi}/{nframes}  ({time.time() - t0:.0f}s elapsed)")
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode(errors="replace")
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed:\n{err[-2000:]}")

    # ---- contact sheet (one frame from the middle of every shot) for review
    thumbs = []
    for s in plan.shots:
        fi = int((s["_start"] + s["dur"] * 0.6) * fps)
        thumbs.append(fr.render(min(fi, nframes - 1)).resize((270, 480)))
    cols = min(5, len(thumbs))
    rows = math.ceil(len(thumbs) / cols)
    sheet = Image.new("RGB", (cols * 270, rows * 480), "white")
    for i, th in enumerate(thumbs):
        sheet.paste(th, ((i % cols) * 270, (i // cols) * 480))
    sheet.save(out_dir / "contact_sheet.jpg", quality=88)
    cover_t = ep.get("cover_at", plan.shots[0]["_start"] + 1.0)
    fr.render(int(cover_t * fps)).save(out_dir / "cover.jpg", quality=92)

    manifest = {
        "episode_id": ep["id"], "title": ep["title"], "rendered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "video": mp4.name, "preview": preview, "duration": round(plan.duration, 3), "frames": nframes, "fps": fps,
        "width": config.WIDTH, "height": config.HEIGHT, "rig_hash": rig_hash(),
        "characters_approved": bool(rigs.bible().get("approved")),
        "shots": [{"id": s.get("id"), "start": round(s["_start"], 3), "end": round(s["_end"], 3), "background": s["background"],
                   "actors": sorted((s.get("actors") or {}).keys())} for s in plan.shots],
        "lines": [{"id": l.id, "who": l.who, "text": l.text, "start": round(l.start, 3), "end": round(l.end, 3),
                   "voice_source": l.source} for l in plan.lines],
        "sfx": [{"t": round(t, 3), "name": n} for t, n, _ in plan.sfx],
        "music": {"source": "synth:studio.audio.music", **{k: v for k, v in mcfg.items()}},
        "asset_sources": {
            "characters": "generated:studio.rigs", "backgrounds": "generated:studio.world",
            "props": "generated:studio.world", "sfx": "generated:studio.audio", "music": "generated:studio.audio",
            "voices": sorted({l.source for l in plan.lines}), "font": captions.font_family(True),
        },
        "render_seconds": round(time.time() - t0, 1),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    log(f"[render] done: {mp4} in {manifest['render_seconds']}s")
    return manifest
