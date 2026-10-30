"""Episode management: discovery, new-episode scaffolding, derived pipeline
status, the approval gate and the Facebook Reels export package.

Status is *derived from real files*, never typed in by hand, so an episode
can't be marked complete unless its deliverables exist and pass validation.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import config, episode, render


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ----------------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------------
def all_episodes() -> list[Path]:
    return sorted(p.parent for p in config.EPISODES_DIR.glob("season-*/*/episode.yaml"))


def find(ep_ref: str) -> Path:
    """Find an episode folder by id (s01e01), slug, or path."""
    p = Path(ep_ref)
    if (p / "episode.yaml").exists():
        return p
    if p.name == "episode.yaml" and p.exists():
        return p.parent
    for d in all_episodes():
        meta = yaml.safe_load((d / "episode.yaml").read_text()) or {}
        if ep_ref in (meta.get("id"), meta.get("slug"), d.name):
            return d
    raise FileNotFoundError(f"No episode '{ep_ref}'. Known: {[d.name for d in all_episodes()]}")


def render_dir(ep_dir: Path, ep_id: str) -> Path:
    return config.BUILD_DIR / ep_id


def export_dir(ep_dir: Path) -> Path:
    return config.EXPORTS_DIR / ep_dir.parent.name / ep_dir.name


# ----------------------------------------------------------------------------
# New episodes
# ----------------------------------------------------------------------------
def new_episode(title: str, season: int = 1, number: int | None = None, logline: str = "", hook: str = "",
                punchline: str = "") -> Path:
    season_dir = config.EPISODES_DIR / f"season-{season:02d}"
    season_dir.mkdir(parents=True, exist_ok=True)
    if number is None:
        nums = [int(m.group(1)) for d in season_dir.iterdir() if (m := re.match(r"s\d+e(\d+)", d.name))]
        number = max(nums, default=0) + 1
    ep_id = f"s{season:02d}e{number:02d}"
    d = season_dir / f"{ep_id}-{slugify(title)}"
    if d.exists():
        raise FileExistsError(f"{d} already exists; not overwriting")
    tpl = (config.TEMPLATES_DIR / "episode_template.yaml").read_text()
    text = (tpl.replace("{{ID}}", ep_id).replace("{{SLUG}}", slugify(title)).replace("{{TITLE}}", title)
            .replace("{{SEASON}}", str(season)).replace("{{NUMBER}}", str(number))
            .replace("{{LOGLINE}}", logline or "TODO: one-sentence premise")
            .replace("{{HOOK}}", hook or "TODO: what grabs attention in the first 2 seconds")
            .replace("{{PUNCHLINE}}", punchline or "TODO: the payoff"))
    d.mkdir(parents=True)
    (d / "voice").mkdir()
    (d / "voice" / ".gitkeep").write_text("")
    (d / "episode.yaml").write_text(text)
    (d / "notes.md").write_text(f"# {title} - production notes\n\n")
    return d


# ----------------------------------------------------------------------------
# Status
# ----------------------------------------------------------------------------
def status(ep_dir: Path) -> dict:
    ep_dir = Path(ep_dir)
    ep = episode.load(ep_dir)
    st = {s: {"state": "todo", "note": ""} for s in config.STAGES}

    def mark(stage, state, note=""):
        st[stage] = {"state": state, "note": note}

    shots = ep.get("shots") or []
    errs = episode.validate(ep) if shots else ["no shots yet"]
    n_lines = sum(len(s.get("lines") or []) for s in shots)
    mark("idea", "done" if ep.get("logline") and "TODO" not in str(ep.get("logline")) else "in_progress",
         ep.get("logline", "")[:120] if ep.get("logline") else "")
    if shots and n_lines and not errs:
        mark("script", "done", f"{n_lines} lines")
        mark("scenes", "done", f"{len(shots)} shots")
        chars = sorted({c for s in shots for c in (s.get("actors") or {})})
        from . import rigs
        draft = "" if rigs.bible().get("approved") else " (designs still DRAFT)"
        mark("character_visuals", "done", ", ".join(chars) + draft)
    elif shots:
        mark("script", "in_progress", "; ".join(errs)[:200])
    elif ep.get("outline"):
        mark("script", "in_progress", "outline written, shots not yet broken down")

    rd = render_dir(ep_dir, ep["id"])
    man_path = rd / "manifest.json"
    man = json.loads(man_path.read_text()) if man_path.exists() else None
    stale = False
    if man:
        rendered = datetime.fromisoformat(man["rendered_at"]).timestamp()
        src_mtime = (ep_dir / "episode.yaml").stat().st_mtime
        stale = src_mtime > rendered + 1 or man.get("rig_hash") != render.rig_hash()
        mp4 = rd / man["video"]
        ok = mp4.exists() and not man.get("preview")
        state = "stale" if stale else ("done" if ok else "in_progress")
        note = "source changed since render - re-render" if stale else ("preview only" if man.get("preview") else man["video"])
        for s in ("animation", "voice", "sound", "editing", "render"):
            mark(s, state, note if s == "render" else "")
        voices = sorted({l["voice_source"] for l in man["lines"]})
        st["voice"]["note"] = ", ".join(voices)
        mark("captions", state if (rd / "captions.srt").exists() else "todo", "burned in + captions.srt")
        st["sound"]["note"] = f"{len(man['sfx'])} sfx + original music"

    qc_path = rd / "qc_report.json"
    qc = json.loads(qc_path.read_text()) if qc_path.exists() else None
    if qc and man and not stale:
        fresh = qc["checked_at"] >= man["rendered_at"]
        if not fresh:
            mark("quality_check", "stale", "render is newer than the QC report")
        else:
            mark("quality_check", "done" if qc["passed"] else "failed",
                 f"{qc['fails']} fails, {qc['warnings']} warnings")

    appr_path = ep_dir / "approval.json"
    if appr_path.exists() and man and not stale:
        appr = json.loads(appr_path.read_text())
        mp4 = rd / man["video"]
        if mp4.exists() and appr.get("video_sha256") == sha256(mp4):
            mark("approval", "done", f"approved by {appr.get('reviewer')} {appr.get('approved_at', '')[:10]}")
        else:
            mark("approval", "stale", "video changed after approval")

    ex = export_dir(ep_dir)
    post = ex / "export.json"
    if post.exists():
        info = json.loads(post.read_text())
        vid = ex / info["video"]
        if vid.exists() and appr_path.exists() and json.loads(appr_path.read_text()).get("video_sha256") == info.get("video_sha256") == sha256(vid):
            mark("export", "done", f"ready to post: {config.rel(ex)}")
        else:
            mark("export", "stale", "export doesn't match the approved video")

    done = sum(1 for s in st.values() if s["state"] == "done")
    return {"id": ep["id"], "title": ep.get("title"), "season": ep.get("season"), "episode": ep.get("episode"),
            "dir": config.rel(ep_dir), "stages": st, "progress": round(done / len(config.STAGES), 3),
            "complete": all(s["state"] == "done" for s in st.values()), "logline": ep.get("logline", ""),
            "hook": ep.get("hook", ""), "punchline": ep.get("punchline", "")}


def missing_assets(ep_dir: Path) -> list[str]:
    """Things the episode needs that don't exist yet."""
    ep = episode.load(ep_dir)
    out = list(episode.validate(ep)) if ep.get("shots") else ["episode has no shots yet"]
    vdir = Path(ep_dir) / "voice"
    if ep.get("voice_provider") == "file":
        for s in ep.get("shots") or []:
            for ln in s.get("lines") or []:
                if not (vdir / f"{ln['id']}.wav").exists():
                    out.append(f"voice/{ln['id']}.wav (recording for: {ln['text']!r})")
    for wav in vdir.glob("*.wav") if vdir.exists() else []:
        ids = {ln["id"] for s in ep.get("shots") or [] for ln in s.get("lines") or []}
        if wav.stem not in ids:
            out.append(f"voice/{wav.name} doesn't match any line id (unused)")
    return out


# ----------------------------------------------------------------------------
# Approval + export
# ----------------------------------------------------------------------------
class GateError(RuntimeError):
    pass


def approve(ep_dir: Path, reviewer: str, confirmations: list[bool], notes: str = "") -> dict:
    from . import qc as qcmod
    ep_dir = Path(ep_dir)
    s = status(ep_dir)
    if s["stages"]["render"]["state"] != "done":
        raise GateError("Can't approve: the episode has no current full-quality render.")
    if s["stages"]["quality_check"]["state"] != "done":
        raise GateError(f"Can't approve: QC is '{s['stages']['quality_check']['state']}'. Run QC and fix failures first.")
    if len(confirmations) != len(qcmod.HUMAN_REVIEW) or not all(confirmations):
        raise GateError("Can't approve: every human-review item must be confirmed.")
    if not reviewer.strip():
        raise GateError("Can't approve: reviewer name required.")
    ep = episode.load(ep_dir)
    man = json.loads((render_dir(ep_dir, ep["id"]) / "manifest.json").read_text())
    mp4 = render_dir(ep_dir, ep["id"]) / man["video"]
    rec = {"episode_id": ep["id"], "reviewer": reviewer.strip(), "approved_at": _now(), "video": man["video"],
           "video_sha256": sha256(mp4), "human_review": dict(zip(qcmod.HUMAN_REVIEW, confirmations)), "notes": notes,
           "publish_permission": False}
    (ep_dir / "approval.json").write_text(json.dumps(rec, indent=2))
    return rec


def export(ep_dir: Path) -> Path:
    """Copy the approved deliverables into exports/ as a ready-to-post package.
    This never uploads or publishes anything."""
    ep_dir = Path(ep_dir)
    s = status(ep_dir)
    if s["stages"]["approval"]["state"] != "done":
        raise GateError("Can't export: the current render hasn't been approved.")
    ep = episode.load(ep_dir)
    rd = render_dir(ep_dir, ep["id"])
    man = json.loads((rd / "manifest.json").read_text())
    ex = export_dir(ep_dir)
    ex.mkdir(parents=True, exist_ok=True)
    name = f"{ep['id']}-{ep.get('slug', 'episode')}"
    shutil.copy2(rd / man["video"], ex / f"{name}.mp4")
    shutil.copy2(rd / "captions.srt", ex / f"{name}.en_US.srt")
    from . import thumbnail
    thumbnail.make_thumbnail(ep_dir, rd / "thumbnail.jpg")
    for f in ("thumbnail.jpg", "cover.jpg", "qc_report.md", "contact_sheet.jpg"):
        if (rd / f).exists():
            shutil.copy2(rd / f, ex / f)
    reels = ep.get("reels") or {}
    tags = " ".join(reels.get("hashtags", []))
    caption = reels.get("caption", ep["title"])
    if tags and not all(t in caption for t in reels.get("hashtags", [])):
        caption = f"{caption}\n\n{tags}"
    (ex / "post.txt").write_text(caption + "\n")
    (ex / "title.txt").write_text(reels.get("title", ep["title"]) + "\n")
    (ex / "POSTING_CHECKLIST.md").write_text(
        f"# Posting checklist - {ep['title']}\n\n"
        "Nothing has been posted. This package is ready for YOU to upload.\n\n"
        f"1. Facebook > Create > Reel > upload `{name}.mp4`\n"
        "2. Paste the caption from `post.txt`\n"
        "3. Captions are already burned into the video. Facebook also accepts `.srt` files on some upload\n"
        "   screens; if yours offers it, upload the `.srt` too (the filename's `en_US` tells Facebook the language).\n"
        "4. Upload `thumbnail.jpg` as the custom cover (title from `title.txt`)\n"
        "5. Audience: Public. Check the preview on your phone before posting\n")
    rec = {"episode_id": ep["id"], "exported_at": _now(), "video": f"{name}.mp4",
           "video_sha256": sha256(ex / f"{name}.mp4"), "captions": f"{name}.en_US.srt", "post_text": "post.txt",
           "thumbnail": "thumbnail.jpg", "title": reels.get("title", ep["title"]),
           "duration": man["duration"], "published": False}
    (ex / "export.json").write_text(json.dumps(rec, indent=2))
    return ex


def lock_characters(reviewer: str) -> Path:
    from . import rigs
    path = config.CHARACTERS_DIR / "approved_lock.json"
    rec = {"rig_hash": render.rig_hash(), "approved_by": reviewer, "approved_at": _now(),
           "version": rigs.bible().get("version")}
    path.write_text(json.dumps(rec, indent=2))
    return path
