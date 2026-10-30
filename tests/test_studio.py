"""Automated tests for the studio. Run: python -m pytest -q
(set RUN_SLOW=1 to include the full render + QC integration test, ~2 min)."""
import copy
import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest
import yaml

from studio import audio, captions, config, episode, pipeline, qc, render, rigs, world

EP1 = config.EPISODES_DIR / "season-01" / "s01e01-kitchen-roach-panic"


# ---------------------------------------------------------------- episode files
def test_episode1_is_valid_and_in_length_range():
    ep = episode.load(EP1)
    assert episode.validate(ep) == []
    P = episode.plan(ep)
    assert config.MIN_SECONDS <= P.duration <= config.MAX_SECONDS
    assert episode.timing_problems(P) == []
    assert len(P.lines) == 12


def test_validation_catches_mistakes():
    ep = copy.deepcopy(episode.load(EP1))
    ep["shots"][0]["actors"]["roach"]["expr"] = "teleporting"
    ep["shots"][0]["sfx"].append({"at": 0, "name": "not_a_sound"})
    ep["shots"][1]["background"] = "moon_base"
    ep["shots"] = ep["shots"][:2]
    errs = " | ".join(episode.validate(ep))
    assert "unknown expression 'teleporting'" in errs
    assert "unknown sound effect 'not_a_sound'" in errs
    assert "unknown background 'moon_base'" in errs
    assert "outside 20-40s" in errs


def test_duplicate_line_ids_rejected():
    ep = copy.deepcopy(episode.load(EP1))
    ep["shots"][1]["lines"][0]["id"] = "L01"
    assert any("duplicate line id" in e for e in episode.validate(ep))


def test_keyframes_interpolate_and_hold():
    base = {"x": 0.0, "expr": "neutral", "action": "idle"}
    keys = [{"at": 2.0, "x": 100.0, "from": 1.0, "ease": "linear"}, {"at": 1.5, "expr": "shocked"}]
    assert episode.evaluate(base, keys, 0.5)[0]["x"] == 0.0          # holding until `from`
    assert episode.evaluate(base, keys, 1.5)[0]["x"] == pytest.approx(50.0)
    assert episode.evaluate(base, keys, 3.0)[0]["x"] == 100.0
    assert episode.evaluate(base, keys, 1.0)[0]["expr"] == "neutral"
    assert episode.evaluate(base, keys, 1.6)[0]["expr"] == "shocked"


def test_camera_never_shows_outside_the_set():
    cam = episode.Camera(x=0, y=0, zoom=2.0, dx=-500, dy=-500)
    x0, y0, x1, y1 = cam.view_box()
    assert x0 >= 0 and y0 >= 0 and x1 <= config.WIDTH and y1 <= config.HEIGHT


# ---------------------------------------------------------------- characters & art
@pytest.mark.parametrize("name", ["wife", "husband", "roach"])
def test_every_expression_and_action_renders(name):
    for expr in rigs.EXPRESSIONS:
        layer, ax, ay = rigs.render_character(name, {"expr": expr}, 0.3, T=0.2)
        assert layer.getbbox() is not None
    for act in rigs.ACTIONS:
        layer, _, _ = rigs.render_character(name, {"action": act, "action_t": 0.4}, 0.3, T=0.4)
        assert layer.getbbox() is not None


def test_backgrounds_and_props_exist():
    for bg in world.BACKGROUNDS:
        img = world.background(bg)
        assert img.size == (config.WIDTH * world.BG_RES, config.HEIGHT * world.BG_RES)
    for p in world.PROPS:
        img, _, _ = world.prop_image(p, 100, 0)
        assert img.getbbox() is not None


def test_frame_is_reels_size():
    P = episode.plan(episode.load(EP1))
    fr = render.FrameRenderer(P)
    for fi in (0, 60, 400, 900):
        assert fr.render(fi).size == (1080, 1920)


# ---------------------------------------------------------------- audio
def test_sound_effects_are_audible():
    for name in audio.SFX:
        x = audio.sfx(name)
        assert len(x) > 0 and np.max(np.abs(x)) > 0.2, name


def test_voices_are_deterministic_and_distinct():
    b = rigs.bible()
    a1, _ = audio.babble("I pay rent.", b["roach"]["voice"], seed=3)
    a2, _ = audio.babble("I pay rent.", b["roach"]["voice"], seed=3)
    h, _ = audio.babble("I pay rent.", b["husband"]["voice"], seed=3)
    assert np.array_equal(a1, a2)
    assert not np.array_equal(a1[: len(h)], h[: len(a1)])
    env = audio.envelope_per_frame(a1)
    assert env.min() >= 0 and env.max() <= 1 and env.max() > 0.5


def test_recorded_voice_overrides_synth(tmp_path):
    ep_dir = tmp_path / "ep"
    shutil.copytree(EP1, ep_dir)
    tone = (np.sin(np.linspace(0, 2000, audio.SR)) * 0.5).astype(np.float32)
    audio.write_wav(ep_dir / "voice" / "L02.wav", tone)
    P = episode.plan(episode.load(ep_dir))
    l2 = next(l for l in P.lines if l.id == "L02")
    assert l2.source == "file:L02.wav"
    assert abs(len(l2.audio) - audio.SR) < 10


def test_music_is_original_length():
    m = audio.music(25.0, seed=4)
    assert len(m) == int(25.0 * audio.SR)
    assert np.max(np.abs(m)) > 0.3


# ---------------------------------------------------------------- captions
def test_captions_cover_script_exactly(tmp_path):
    P = episode.plan(episode.load(EP1))
    cues = captions.build_cues(P)
    joined = " ".join(c["text"].replace("\n", " ") for c in cues)
    assert joined == " ".join(l.text for l in P.lines)
    for a, b in zip(cues, cues[1:]):
        assert a["end"] <= b["start"]
    for c in cues:
        assert all(len(r) <= captions.MAX_CHARS + 12 for r in c["text"].split("\n"))
    captions.write_srt(cues, tmp_path / "c.srt")
    back = captions.parse_srt(tmp_path / "c.srt")
    assert [c["text"] for c in back] == [c["text"] for c in cues]


# ---------------------------------------------------------------- pipeline
@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    for name in ("EPISODES_DIR", "BUILD_DIR", "EXPORTS_DIR"):
        monkeypatch.setattr(config, name, tmp_path / name.lower())
    return tmp_path


def test_new_episode_scaffold_and_status(sandbox):
    d = pipeline.new_episode("The Midnight Snack", season=1, logline="x", hook="y", punchline="z")
    assert (d / "episode.yaml").exists() and (d / "voice").is_dir()
    with pytest.raises(FileExistsError):
        pipeline.new_episode("The Midnight Snack", season=1, number=1)
    s = pipeline.status(d)
    assert s["stages"]["render"]["state"] == "todo"
    assert not s["complete"]


def test_cannot_approve_or_export_without_render(sandbox):
    d = pipeline.new_episode("Test Ep")
    with pytest.raises(pipeline.GateError):
        pipeline.approve(d, "me", [True] * len(qc.HUMAN_REVIEW))
    with pytest.raises(pipeline.GateError):
        pipeline.export(d)


def test_outline_episodes_are_not_marked_scripted():
    for d in pipeline.all_episodes():
        s = pipeline.status(d)
        if s["id"] != "s01e01":
            assert s["stages"]["script"]["state"] != "done"
            assert s["stages"]["render"]["state"] == "todo"


def test_season_one_has_ten_distinct_episodes():
    eps = [yaml.safe_load((d / "episode.yaml").read_text()) for d in pipeline.all_episodes()]
    s1 = [e for e in eps if e["season"] == 1]
    assert len(s1) == 10
    assert len({e["punchline"] for e in s1}) == 10
    assert all(e.get("hook") and e.get("punchline") for e in s1)


# ---------------------------------------------------------------- full render + QC (slow)
@pytest.mark.skipif(not os.environ.get("RUN_SLOW"), reason="set RUN_SLOW=1 to run the full render test")
def test_full_render_qc_approve_export(sandbox):
    dst = config.EPISODES_DIR / "season-01" / EP1.name
    shutil.copytree(EP1, dst)
    man = render.render_episode(dst, log=lambda m: None)
    assert man["frames"] == round(man["duration"] * 30)
    r = qc.run_qc(dst)
    assert r.passed, [c for c in r.checks if c["status"] == "FAIL"]
    # QC must catch a broken caption file
    srt = config.BUILD_DIR / "s01e01" / "captions.srt"
    good = srt.read_text()
    srt.write_text(good.replace("cereal", "ceral"))
    assert not qc.run_qc(dst).passed
    srt.write_text(good)
    assert qc.run_qc(dst).passed
    with pytest.raises(pipeline.GateError):
        pipeline.approve(dst, "me", [True, False, True, True])
    pipeline.approve(dst, "Tester", [True] * len(qc.HUMAN_REVIEW))
    ex = pipeline.export(dst)
    info = json.loads((ex / "export.json").read_text())
    assert info["published"] is False and (ex / info["video"]).exists()
    assert pipeline.status(dst)["complete"]
