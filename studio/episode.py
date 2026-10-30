"""Episode production files: loading, validation and timeline evaluation.

An episode is one YAML file (episode.yaml) inside its own production folder:

    episodes/season-01/s01e01-kitchen-roach-panic/
        episode.yaml      <- script, shots, dialogue, sound cues (the source of truth)
        voice/            <- optional recorded/TTS WAVs named <line id>.wav
        notes.md          <- optional production notes

Times inside a shot (`at`) are seconds from the start of that shot, so shots
can be re-timed without touching anything else.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import config, rigs, world, audio

EASES = {
    "linear": lambda u: u,
    "in": lambda u: u * u,
    "out": lambda u: 1 - (1 - u) ** 2,
    "inout": lambda u: 3 * u * u - 2 * u * u * u,
    "snap": lambda u: 1.0,
    "overshoot": lambda u: 1 + 2.4 * (u - 1) ** 3 + 1.4 * (u - 1) ** 2,
}
NUMERIC = ("x", "y", "scale", "zoom", "rot")
DISCRETE = ("expr", "action", "look", "flip", "hold", "z", "mouth", "visible", "variants")


class EpisodeError(ValueError):
    pass


def load(path: Path) -> dict:
    path = Path(path)
    if path.is_dir():
        path = path / "episode.yaml"
    with open(path) as f:
        ep = yaml.safe_load(f)
    ep["_path"] = str(path)
    ep["_dir"] = str(path.parent)
    return ep


# ----------------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------------
def validate(ep: dict) -> list[str]:
    """Return a list of problems. An empty list means the episode file is valid."""
    errs = []
    for key in ("id", "title", "logline", "hook", "punchline", "shots"):
        if not ep.get(key):
            errs.append(f"missing required field '{key}'")
    shots = ep.get("shots") or []
    total = 0.0
    seen_lines = set()
    for i, s in enumerate(shots):
        tag = f"shot {s.get('id', i)}"
        d = s.get("dur")
        if not isinstance(d, (int, float)) or d <= 0:
            errs.append(f"{tag}: 'dur' must be a positive number")
            d = 0
        total += d or 0
        bg = s.get("background")
        if bg not in world.BACKGROUNDS:
            errs.append(f"{tag}: unknown background '{bg}'")
        for name, a in (s.get("actors") or {}).items():
            if name not in rigs.BUILDERS:
                errs.append(f"{tag}: unknown character '{name}'")
                continue
            for k in [a] + list(a.get("keys", [])):
                if k.get("expr") and k["expr"] not in rigs.EXPRESSIONS:
                    errs.append(f"{tag}/{name}: unknown expression '{k['expr']}'")
                if k.get("action") and k["action"] not in rigs.ACTIONS:
                    errs.append(f"{tag}/{name}: unknown action '{k['action']}'")
                for hand, prop in (k.get("hold") or {}).items():
                    if hand not in ("L", "R"):
                        errs.append(f"{tag}/{name}: hand must be L or R, got '{hand}'")
                    if prop and prop not in world.PROPS:
                        errs.append(f"{tag}/{name}: unknown prop '{prop}'")
                if k.get("at", 0) > (d or 0) + 1e-6:
                    errs.append(f"{tag}/{name}: key at {k.get('at')}s is after the shot ends ({d}s)")
        for p in s.get("props") or []:
            if p.get("name") not in world.PROPS:
                errs.append(f"{tag}: unknown prop '{p.get('name')}'")
        for fx in s.get("fx") or []:
            if fx.get("type") not in world.FX_TYPES:
                errs.append(f"{tag}: unknown fx '{fx.get('type')}'")
        for sc in s.get("sfx") or []:
            if sc.get("name") not in audio.SFX:
                errs.append(f"{tag}: unknown sound effect '{sc.get('name')}'")
            if sc.get("at", 0) > (d or 0):
                errs.append(f"{tag}: sfx '{sc.get('name')}' at {sc.get('at')}s is after the shot ends")
        for ln in s.get("lines") or []:
            if ln.get("who") not in rigs.BUILDERS:
                errs.append(f"{tag}: line by unknown character '{ln.get('who')}'")
            if not str(ln.get("text", "")).strip():
                errs.append(f"{tag}: empty dialogue line")
            lid = ln.get("id")
            if not lid or not re.match(r"^[A-Za-z0-9_-]+$", str(lid)):
                errs.append(f"{tag}: every line needs an id like L01")
            elif lid in seen_lines:
                errs.append(f"{tag}: duplicate line id '{lid}'")
            seen_lines.add(lid)
            if ln.get("at", 0) > (d or 0):
                errs.append(f"{tag}: line {lid} starts after the shot ends")
    if shots and not (config.MIN_SECONDS <= total <= config.MAX_SECONDS):
        errs.append(f"total length {total:.1f}s is outside {config.MIN_SECONDS:.0f}-{config.MAX_SECONDS:.0f}s")
    return errs


# ----------------------------------------------------------------------------
# Planning: absolute timings for shots, lines and sound cues
# ----------------------------------------------------------------------------
@dataclass
class Line:
    id: str
    who: str
    text: str
    start: float
    audio: object
    env: object
    source: str
    shout: bool = False

    @property
    def end(self):
        return self.start + len(self.audio) / audio.SR


@dataclass
class Plan:
    ep: dict
    shots: list
    duration: float
    lines: list = field(default_factory=list)
    sfx: list = field(default_factory=list)

    def shot_at(self, t):
        for s in self.shots:
            if s["_start"] <= t < s["_end"]:
                return s
        return self.shots[-1]


def plan(ep: dict) -> Plan:
    errs = validate(ep)
    if errs:
        raise EpisodeError("Episode file has problems:\n  - " + "\n  - ".join(errs))
    t = 0.0
    shots = []
    for s in ep["shots"]:
        s = dict(s)
        s["_start"], s["_end"] = t, t + s["dur"]
        t += s["dur"]
        shots.append(s)
    P = Plan(ep, shots, t)
    voice_dir = Path(ep["_dir"]) / "voice"
    bible = rigs.bible()
    for si, s in enumerate(shots):
        for ln in s.get("lines") or []:
            start = s["_start"] + ln.get("at", 0)
            wav = voice_dir / f"{ln['id']}.wav"
            if wav.exists():
                a, src = audio.load_wav(wav), f"file:{wav.name}"
            else:
                seed = sum(ord(c) for c in ln["id"]) + si
                a, _ = audio.babble(ln["text"], bible[ln["who"]]["voice"], seed=seed, shout=ln.get("shout", False))
                src = "synth:babble"
            P.lines.append(Line(ln["id"], ln["who"], ln["text"], start, a, audio.envelope_per_frame(a), src,
                                ln.get("shout", False)))
        for sc in s.get("sfx") or []:
            P.sfx.append((s["_start"] + sc.get("at", 0), sc["name"], sc.get("gain", 0.8)))
    P.lines.sort(key=lambda l: l.start)
    return P


def timing_problems(P: Plan) -> list[str]:
    """Lines that overlap each other or run past the end of the episode."""
    out = []
    for a, b in zip(P.lines, P.lines[1:]):
        if a.end > b.start + 0.05:
            out.append(f"line {a.id} ({a.who}) ends at {a.end:.2f}s but {b.id} starts at {b.start:.2f}s")
    if P.lines and P.lines[-1].end > P.duration:
        out.append(f"last line {P.lines[-1].id} runs past the end of the episode")
    return out


# ----------------------------------------------------------------------------
# Keyframe evaluation
# ----------------------------------------------------------------------------
def evaluate(base: dict, keys: list, t: float) -> tuple[dict, float]:
    """Evaluate a keyframed object at shot-time t.

    Numeric fields tween from the previous key to the next one; a key may set
    `from` (seconds) to hold still until then and `ease` for the curve.
    Discrete fields (expr, action, hold, ...) switch at the key time.
    Returns (state, action_start_time)."""
    state = {k: v for k, v in base.items() if k != "keys"}
    keys = sorted(keys or [], key=lambda k: k.get("at", 0))
    for f in NUMERIC:
        pts = [(0.0, state[f], None, None)] if f in state else []
        pts += [(k.get("at", 0), k[f], k.get("ease", "inout"), k.get("from")) for k in keys if f in k]
        if not pts:
            continue
        val = pts[0][1]
        for i, (at, v, ease, frm) in enumerate(pts):
            if t >= at:
                val = v
                continue
            if i == 0:
                break
            p_at, p_v = pts[i - 1][0], pts[i - 1][1]
            start = max(p_at, frm if frm is not None else p_at)
            if t <= start:
                val = p_v
            else:
                u = (t - start) / max(1e-6, at - start)
                val = p_v + (v - p_v) * EASES.get(ease or "inout", EASES["inout"])(min(1.0, u))
            break
        state[f] = val
    action_start = 0.0
    for key in keys:
        at = key.get("at", 0)
        if t < at:
            break
        for f in DISCRETE:
            if f in key:
                if f == "action" and key[f] != state.get("action"):
                    action_start = at
                state[f] = key[f]
    return state, action_start


class Camera:
    def __init__(self, x=540.0, y=960.0, zoom=1.0, dx=0.0, dy=0.0):
        self.zoom = max(1.0, zoom)
        hw, hh = config.WIDTH / (2 * self.zoom), config.HEIGHT / (2 * self.zoom)
        self.x = min(max(x + dx, hw), config.WIDTH - hw)
        self.y = min(max(y + dy, hh), config.HEIGHT - hh)

    def to_screen(self, wx, wy):
        return ((wx - self.x) * self.zoom + config.WIDTH / 2, (wy - self.y) * self.zoom + config.HEIGHT / 2)

    def view_box(self):
        hw, hh = config.WIDTH / (2 * self.zoom), config.HEIGHT / (2 * self.zoom)
        return (self.x - hw, self.y - hh, self.x + hw, self.y + hh)


def camera_at(shot: dict, t: float) -> Camera:
    cam = shot.get("camera") or {}
    st, _ = evaluate({"x": cam.get("x", 540), "y": cam.get("y", 960), "zoom": cam.get("zoom", 1.0)}, cam.get("keys"), t)
    dx = dy = 0.0
    for fx in shot.get("fx") or []:
        if fx["type"] == "shake":
            ft = t - fx.get("at", 0)
            if 0 <= ft < fx.get("dur", 0.5):
                amp = fx.get("amp", 18) * (1 - ft / fx.get("dur", 0.5))
                dx += math.sin(ft * 83) * amp
                dy += math.cos(ft * 67) * amp
    zoom = st["zoom"]
    if dx or dy:  # give the shake some room to move inside the background
        zoom *= 1.06
    return Camera(st["x"], st["y"], zoom, dx, dy)
