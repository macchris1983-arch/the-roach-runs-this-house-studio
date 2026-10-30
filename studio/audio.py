"""Audio engine: original character voices, sound effects, music and the final mix.

Everything here is synthesised from scratch with numpy, so every sound is
original and free. Real voice recordings (or any free TTS output) can replace
the synthesised voices by dropping WAV files into an episode's voice/ folder.
"""
from __future__ import annotations

import functools
import math
import random
import re
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile

from . import config

SR = config.AUDIO_RATE


def _t(dur):
    return np.arange(int(dur * SR)) / SR


def _env(n, a=0.005, r=0.05):
    e = np.ones(n)
    na, nr = min(n, int(a * SR)), min(n, int(r * SR))
    if na:
        e[:na] = np.linspace(0, 1, na)
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def _noise(dur, seed=0):
    return np.random.default_rng(seed).standard_normal(int(dur * SR))


def _bp(x, lo, hi, order=2):
    sos = signal.butter(order, [lo / (SR / 2), min(0.99, hi / (SR / 2))], btype="band", output="sos")
    return signal.sosfilt(sos, x)


def _lp(x, f, order=2):
    return signal.sosfilt(signal.butter(order, f / (SR / 2), output="sos"), x)


def _hp(x, f, order=2):
    return signal.sosfilt(signal.butter(order, f / (SR / 2), btype="high", output="sos"), x)


def _norm(x, peak=0.9):
    m = np.max(np.abs(x)) if len(x) else 0
    return x * (peak / m) if m > 0 else x


def _sweep(f0, f1, dur, shape="sine"):
    t = _t(dur)
    f = f0 * (f1 / f0) ** (t / dur)
    ph = 2 * np.pi * np.cumsum(f) / SR
    if shape == "square":
        return np.sign(np.sin(ph))
    if shape == "saw":
        return 2 * ((ph / (2 * np.pi)) % 1) - 1
    return np.sin(ph)


# ----------------------------------------------------------------------------
# Sound-effect library (all original, generated)
# ----------------------------------------------------------------------------
def sfx_light_switch():
    x = _hp(_noise(0.04, 1), 2000) * np.exp(-_t(0.04) * 120)
    return _norm(np.concatenate([x, np.zeros(int(0.03 * SR)), x * 0.6]), 0.7)


def sfx_record_scratch():
    t = _t(0.55)
    f = 300 + 900 * np.abs(np.sin(2 * np.pi * 3.2 * t))
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR)
    return _norm(_bp(_noise(0.55, 2), 300, 3500) * 0.6 * (0.4 + tone) * _env(len(t), 0.005, 0.15), 0.8)


def sfx_scream_sting():  # orchestral-ish hit + rising siren
    t = _t(1.1)
    hit = sum(np.sin(2 * np.pi * f * t) for f in (110, 220, 330, 440, 660)) * np.exp(-t * 4)
    siren = _sweep(500, 1500, 1.1, "saw") * 0.25 * np.exp(-t * 1.5)
    return _norm(_lp(hit + siren + _noise(1.1, 3) * 0.2 * np.exp(-t * 9), 6000), 0.9)


def sfx_boing():
    t = _t(0.6)
    f = 180 + 140 * np.sin(2 * np.pi * 9 * t) * np.exp(-t * 3) + 120 * (1 - t / 0.6)
    return _norm(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 4.5), 0.85)


def sfx_slide_whistle_up():
    t = _t(0.5)
    return _norm(_sweep(400, 1600, 0.5) * (1 + 0.02 * np.sin(2 * np.pi * 8 * t)) * _env(len(t), 0.02, 0.08), 0.6)


def sfx_slide_whistle_down():
    t = _t(0.6)
    return _norm(_sweep(1500, 300, 0.6) * _env(len(t), 0.02, 0.1), 0.6)


def sfx_whoosh():
    t = _t(0.45)
    x = _noise(0.45, 4)
    out = np.zeros_like(x)
    for i, (lo, hi) in enumerate(((300, 900), (700, 1800), (1500, 4000))):
        seg = _bp(x, lo, hi) * np.sin(np.pi * np.clip((t - i * 0.05) / 0.35, 0, 1))
        out += seg
    return _norm(out, 0.6)


def sfx_crash():
    t = _t(1.2)
    x = _noise(1.2, 5) * np.exp(-t * 3.5)
    clang = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, d in ((523, 3), (1180, 4), (1797, 6), (2600, 8)))
    thud = np.sin(2 * np.pi * 70 * t) * np.exp(-t * 10)
    return _norm(_hp(x, 500) * 0.7 + clang * 0.25 + thud, 0.9)


def sfx_swat():
    t = _t(0.25)
    return _norm(_bp(_noise(0.25, 6), 400, 5000) * np.exp(-t * 30) + np.sin(2 * np.pi * 120 * t) * np.exp(-t * 25), 0.9)


def sfx_ding():
    t = _t(1.0)
    x = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, d in ((1568, 3), (3136, 5), (4704, 8)))
    return _norm(x, 0.55)


def sfx_dun_dun_dun():
    out = []
    for f, d in ((147, 0.32), (139, 0.32), (110, 0.9)):
        t = _t(d)
        x = sum(np.sign(np.sin(2 * np.pi * f * m * t)) / m for m in (1, 2, 3)) * _env(len(t), 0.01, 0.12)
        out.append(_lp(x, 1800))
        out.append(np.zeros(int(0.06 * SR)))
    return _norm(np.concatenate(out), 0.75)


def sfx_scuttle():
    out = np.zeros(int(0.7 * SR))
    rnd = random.Random(9)
    for i in range(22):
        s = int((i * 0.03 + rnd.random() * 0.01) * SR)
        click = _hp(_noise(0.012, 10 + i), 1500) * np.exp(-_t(0.012) * 300)
        out[s:s + len(click)] += click * (0.6 + rnd.random() * 0.4)
    return _norm(out, 0.6)


def sfx_crunch():
    out = np.zeros(int(0.45 * SR))
    rnd = random.Random(11)
    for i in range(9):
        s = int(rnd.random() * 0.35 * SR)
        c = _bp(_noise(0.04, 20 + i), 800, 5000) * np.exp(-_t(0.04) * 80)
        out[s:s + len(c)] += c
    return _norm(out, 0.7)


def sfx_pop():
    t = _t(0.12)
    return _norm(_sweep(300, 900, 0.12) * np.exp(-t * 40), 0.7)


def sfx_gasp_sting():  # comedic "ooooh" crowd-ish pad
    t = _t(1.2)
    x = sum(np.sin(2 * np.pi * f * t * (1 - 0.06 * t)) for f in (220, 277, 330, 440))
    x += _bp(_noise(1.2, 12), 300, 1200) * 0.4
    return _norm(x * np.sin(np.pi * t / 1.2) ** 0.7, 0.55)


def sfx_footsteps_run():
    out = np.zeros(int(1.0 * SR))
    for i in range(8):
        s = int(i * 0.12 * SR)
        st = np.sin(2 * np.pi * 90 * _t(0.06)) * np.exp(-_t(0.06) * 60) + _bp(_noise(0.06, 30 + i), 200, 2000) * 0.4 * np.exp(-_t(0.06) * 50)
        out[s:s + len(st)] += st
    return _norm(out, 0.6)


def sfx_paper_rustle():
    t = _t(0.5)
    return _norm(_bp(_noise(0.5, 13), 2000, 8000) * (0.5 + 0.5 * np.abs(np.sin(2 * np.pi * 7 * t))) * _env(len(t), 0.02, 0.1), 0.45)


SFX = {name[4:]: fn for name, fn in globals().items() if name.startswith("sfx_") and callable(fn)}


@functools.lru_cache(maxsize=None)
def sfx(name: str) -> np.ndarray:
    if name not in SFX:
        raise KeyError(f"Unknown sound effect '{name}'. Known: {sorted(SFX)}")
    return SFX[name]().astype(np.float32)


def export_sfx_library(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    for name in sorted(SFX):
        wavfile.write(folder / f"{name}.wav", SR, (sfx(name) * 32767).astype(np.int16))
    return sorted(SFX)


# ----------------------------------------------------------------------------
# Character voices (built-in "cartoon babble" synthesiser)
# ----------------------------------------------------------------------------
VOWEL_FORMANTS = {"a": (800, 1250), "e": (520, 1850), "i": (330, 2300), "o": (520, 900),
                  "u": (360, 820), "y": (360, 2100)}


def _syllables(word: str):
    groups = re.findall(r"[aeiouyAEIOUY]+", word)
    if not groups:
        return ["e"] if re.search(r"[A-Za-z0-9]", word) else []
    out = []
    for g in groups:
        reps = len(g)
        out.append((g[0].lower(), reps))
    return out


def babble(text: str, voice: dict, seed: int = 0, shout: bool = False):
    """Synthesise a stylised, original cartoon voice for one line.

    Returns (audio float32 array, list of syllable onsets in seconds)."""
    rnd = random.Random(seed)
    f0 = voice.get("pitch_hz", 200)
    syl = voice.get("syllable_s", 0.12)
    bright = voice.get("brightness", 1.0)
    style = voice.get("style", "")
    chunks = []
    onsets = []
    cursor = 0.0
    words = re.findall(r"[A-Za-z0-9'$]+|[.,!?—…-]+", text)
    caps_words = sum(1 for w in words if w.isupper() and len(w) > 1)
    question = text.strip().endswith("?")
    exclaim = text.strip().endswith("!") or shout or caps_words >= 2
    n_words = len([w for w in words if re.match(r"[A-Za-z0-9]", w)])
    wi = 0
    for w in words:
        if not re.match(r"[A-Za-z0-9]", w):
            pause = 0.32 if any(c in w for c in ".!?") else 0.2
            if "…" in w or "..." in w:
                pause = 0.45
            chunks.append(np.zeros(int(pause * SR)))
            cursor += pause
            continue
        wi += 1
        loud = w.isupper() and len(w) > 1
        syls = _syllables(w)
        for si, (v, reps) in enumerate(syls):
            d = syl * rnd.uniform(0.85, 1.2) * (1 + 0.55 * (reps - 1)) * (1.35 if loud else 1)
            d = min(d, 1.6)
            t = _t(d)
            prog = wi / max(1, n_words)
            pitch = f0 * (1 + 0.07 * math.sin(si * 2.1 + wi)) * (1.18 if (loud or exclaim) else 1)
            if question and prog > 0.75:
                pitch *= 1 + 0.25 * (prog - 0.75) / 0.25
            if style == "sassy":
                pitch *= 1 + 0.1 * math.sin(wi * 1.3)
            vib = 1 + 0.025 * np.sin(2 * np.pi * 5.5 * t)
            glide = 1 + (0.08 if exclaim else 0.03) * (1 - t / d)
            ph = 2 * np.pi * np.cumsum(pitch * vib * glide) / SR
            src = sum(np.sin(ph * h) / h ** (1.3 / bright) for h in range(1, 14))
            if style == "raspy":
                src *= 1 + 0.35 * np.sin(2 * np.pi * 63 * t)
                src += _noise(d, rnd.randint(0, 10 ** 6)) * 0.12
            f1, f2 = VOWEL_FORMANTS.get(v, (500, 1500))
            sc = 1.12 if style in ("sassy", "raspy") else 0.95
            x = _bp(src, f1 * sc * 0.7, f1 * sc * 1.4) * 1.0 + _bp(src, f2 * sc * 0.8, min(f2 * sc * 1.25, 9000)) * 0.6
            x += _lp(src, 400) * 0.25
            cons = _bp(_noise(0.025, rnd.randint(0, 10 ** 6)), 1800, 7000) * 0.25
            x[:len(cons)] += cons[: len(x)]
            x *= _env(len(x), 0.012, min(0.05, d / 3)) * (1.4 if loud else 1.0)
            onsets.append(cursor)
            chunks.append(x)
            gap = 0.025 if si < len(syls) - 1 else 0.06
            chunks.append(np.zeros(int(gap * SR)))
            cursor += d + gap
    audio = np.concatenate(chunks) if chunks else np.zeros(int(0.3 * SR))
    # trim trailing silence
    nz = np.nonzero(np.abs(audio) > 1e-4)[0]
    if len(nz):
        audio = audio[: nz[-1] + int(0.05 * SR)]
    return _norm(audio, 0.8 if exclaim else 0.6).astype(np.float32), onsets


def load_wav(path: Path) -> np.ndarray:
    rate, raw = wavfile.read(path)
    if raw.dtype == np.int16:
        data = raw.astype(np.float32) / 32768.0
    elif raw.dtype == np.int32:
        data = raw.astype(np.float32) / 2147483648.0
    elif raw.dtype == np.uint8:
        data = (raw.astype(np.float32) - 128) / 128.0
    else:
        data = raw.astype(np.float32)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if rate != SR:
        g = math.gcd(rate, SR)
        data = signal.resample_poly(data, SR // g, rate // g).astype(np.float32)
    return data


def envelope_per_frame(audio: np.ndarray, fps: int = config.FPS) -> np.ndarray:
    """Mouth-openness envelope (0..1) for lip sync, one value per video frame."""
    hop = SR // fps
    n = int(math.ceil(len(audio) / hop))
    pad = np.zeros(n * hop, dtype=np.float32)
    pad[: len(audio)] = audio
    rms = np.sqrt((pad.reshape(n, hop) ** 2).mean(axis=1))
    peak = np.percentile(rms[rms > 0], 95) if np.any(rms > 0) else 1
    return np.clip(rms / (peak + 1e-9), 0, 1)


# ----------------------------------------------------------------------------
# Original music generator
# ----------------------------------------------------------------------------
SCALES = {"minor": [0, 2, 3, 5, 7, 8, 10], "major": [0, 2, 4, 5, 7, 9, 11], "dorian": [0, 2, 3, 5, 7, 9, 10]}
MOODS = {
    "sneaky_funk": {"scale": "dorian", "prog": [0, 3, 0, 4], "swing": 0.12},
    "sitcom_bounce": {"scale": "major", "prog": [0, 5, 3, 4], "swing": 0.08},
    "suspense": {"scale": "minor", "prog": [0, 5, 0, 6], "swing": 0.0},
}


def _note_hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def music(duration: float, bpm: float = 104, root_midi: int = 45, mood: str = "sneaky_funk", seed: int = 1):
    cfg = MOODS.get(mood, MOODS["sneaky_funk"])
    scale = SCALES[cfg["scale"]]
    rnd = random.Random(seed)
    beat = 60.0 / bpm
    n = int((duration + 1) * SR)
    out = np.zeros(n, dtype=np.float64)

    def add(x, at):
        s = int(at * SR)
        if s >= n:
            return
        e = min(n, s + len(x))
        out[s:e] += x[: e - s]

    def kick():
        t = _t(0.35)
        return np.sin(2 * np.pi * np.cumsum(50 + 110 * np.exp(-t * 28)) / SR) * np.exp(-t * 9)

    def snare(sd):
        t = _t(0.22)
        return _hp(_noise(0.22, sd), 1200) * np.exp(-t * 18) * 0.6 + np.sin(2 * np.pi * 190 * t) * np.exp(-t * 25) * 0.4

    def hat(sd):
        t = _t(0.05)
        return _hp(_noise(0.05, sd), 7000) * np.exp(-t * 70) * 0.35

    def bass(midi, d):
        t = _t(d)
        f = _note_hz(midi)
        x = 2 * ((f * t) % 1) - 1
        return _lp(x, 700) * _env(len(t), 0.005, 0.04) * np.exp(-t * 1.2)

    def keys(midis, d):
        t = _t(d)
        x = sum(np.sin(2 * np.pi * _note_hz(m) * t) + 0.3 * np.sin(4 * np.pi * _note_hz(m) * t) for m in midis)
        return x * np.exp(-t * 3) * _env(len(t), 0.005, 0.05) / len(midis)

    bass_pattern = [(0, 0, 0.75), (0.75, 0, 0.25), (1.5, 2, 0.5), (2, 4, 0.5), (2.75, 0, 0.25), (3, 6, 0.5), (3.5, 4, 0.5)]
    bar = 4 * beat
    nbars = int(duration / bar) + 2
    lead_notes = [rnd.choice([0, 2, 4, 4, 6, 7]) for _ in range(8)]
    for b in range(nbars):
        t0 = b * bar
        deg = cfg["prog"][b % len(cfg["prog"])]

        def degree(d, octave=0):
            return root_midi + scale[d % 7] + 12 * (d // 7) + 12 * octave
        for i in range(4):  # drums
            add(kick() * 0.9, t0 + i * beat if i % 2 == 0 else t0 + i * beat + 0.5 * beat)
            if i % 2 == 1:
                add(snare(b * 4 + i) * 0.7, t0 + i * beat)
            for h in range(2):
                sw = cfg["swing"] * beat if h == 1 else 0
                add(hat(b * 8 + i * 2 + h) * (0.8 if h == 0 else 0.5), t0 + i * beat + h * beat / 2 + sw)
        for at, step, d in bass_pattern:
            add(bass(degree(deg + step - (step and 0)) , d * beat) * 0.55, t0 + at * beat)
        chord = [degree(deg, 2), degree(deg + 2, 2), degree(deg + 4, 2)]
        for at in (0.5, 1.75, 2.5, 3.75):
            add(keys(chord, 0.3 * beat) * 0.35, t0 + at * beat)
        if b % 2 == 1:  # little lead hook every other bar
            for j, ln in enumerate(lead_notes[:4]):
                t = _t(0.4 * beat)
                f = _note_hz(degree(deg + ln, 3))
                x = np.sign(np.sin(2 * np.pi * f * t)) * 0.5 + np.sin(2 * np.pi * f * t)
                add(_lp(x, 3000) * _env(len(t), 0.005, 0.06) * 0.12, t0 + (2 + j * 0.5) * beat)
    out = out[: int(duration * SR)]
    fade = int(0.6 * SR)
    out[-fade:] *= np.linspace(1, 0, fade)
    return _norm(out, 0.8).astype(np.float32)


# ----------------------------------------------------------------------------
# Mixer
# ----------------------------------------------------------------------------
def mix(duration: float, voices: list, effects: list, music_track: np.ndarray | None, music_gain: float = 0.22):
    """voices/effects: list of (start_seconds, audio, gain). Music is ducked under dialogue."""
    n = int(duration * SR)
    vbus = np.zeros(n, dtype=np.float32)
    fbus = np.zeros(n, dtype=np.float32)
    for bus, items in ((vbus, voices), (fbus, effects)):
        for start, a, g in items:
            s = int(start * SR)
            if s >= n:
                continue
            e = min(n, s + len(a))
            bus[s:e] += a[: e - s] * g
    mbus = np.zeros(n, dtype=np.float32)
    if music_track is not None:
        m = music_track[:n]
        mbus[: len(m)] = m
        # sidechain duck: music drops ~8 dB whenever someone talks
        active = (np.abs(vbus) > 0.02).astype(np.float32)
        win = int(0.25 * SR)
        active = np.convolve(active, np.ones(win) / win, mode="same")
        duck = 1 - 0.6 * np.clip(active * 4, 0, 1)
        mbus *= duck * music_gain
    master = vbus + fbus + mbus
    peak = np.max(np.abs(master)) or 1
    master = master / peak * 0.89
    return master.astype(np.float32), vbus


def write_wav(path: Path, audio: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    stereo = np.stack([audio, audio], axis=1)
    wavfile.write(path, SR, (np.clip(stereo, -1, 1) * 32767).astype(np.int16))
