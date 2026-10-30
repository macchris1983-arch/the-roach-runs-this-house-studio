"""Command line for the studio.  Run `python -m studio --help`."""
from __future__ import annotations

import argparse
import json
import sys

from . import config


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m studio", description="The Roach Runs This House production studio")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list episodes and their pipeline progress")
    p = sub.add_parser("status", help="detailed stage-by-stage status for one episode")
    p.add_argument("episode")
    p = sub.add_parser("new", help="create a new episode production folder from the template")
    p.add_argument("title")
    p.add_argument("--season", type=int, default=1)
    p.add_argument("--number", type=int)
    p.add_argument("--logline", default="")
    p.add_argument("--hook", default="")
    p.add_argument("--punchline", default="")
    p = sub.add_parser("validate", help="check an episode file and list missing assets")
    p.add_argument("episode")
    p = sub.add_parser("render", help="render the MP4 (add --preview for a fast low-res draft)")
    p.add_argument("episode")
    p.add_argument("--preview", action="store_true")
    p = sub.add_parser("qc", help="run automated quality control on the latest render")
    p.add_argument("episode")
    p = sub.add_parser("produce", help="validate + render + QC in one go")
    p.add_argument("episode")
    p = sub.add_parser("approve", help="record your approval (requires passing QC)")
    p.add_argument("episode")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--confirm-all", action="store_true", help="confirm every human-review item (you watched it)")
    p.add_argument("--notes", default="")
    p = sub.add_parser("export", help="build the ready-to-post Reels package (does NOT publish)")
    p.add_argument("episode")
    sub.add_parser("sheet", help="render the character model sheet")
    p = sub.add_parser("lock-characters", help="lock the approved character designs (QC then enforces them)")
    p.add_argument("--reviewer", required=True)
    sub.add_parser("sfx", help="export the sound-effect library as WAV files")
    p = sub.add_parser("prompts", help="write image/video-generation prompts for each shot (for optional external tools)")
    p.add_argument("episode")
    p = sub.add_parser("dashboard", help="start the local production dashboard")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1")

    a = ap.parse_args(argv)
    from . import pipeline

    if a.cmd == "list":
        for d in pipeline.all_episodes():
            s = pipeline.status(d)
            bar = "".join("█" if v["state"] == "done" else ("▒" if v["state"] in ("in_progress", "stale", "failed") else "·")
                          for v in s["stages"].values())
            print(f"{s['id']}  {bar}  {int(s['progress'] * 100):3d}%  {s['title']}")
    elif a.cmd == "status":
        s = pipeline.status(pipeline.find(a.episode))
        print(f"{s['id']} - {s['title']}  ({int(s['progress'] * 100)}%)")
        for k, v in s["stages"].items():
            print(f"  {k:<18} {v['state']:<12} {v['note']}")
    elif a.cmd == "new":
        d = pipeline.new_episode(a.title, a.season, a.number, a.logline, a.hook, a.punchline)
        print(f"created {config.rel(d)}")
    elif a.cmd == "validate":
        d = pipeline.find(a.episode)
        miss = pipeline.missing_assets(d)
        from . import episode
        if not miss:
            P = episode.plan(episode.load(d))
            miss = episode.timing_problems(P)
        print("OK - no problems found" if not miss else "Problems:\n  - " + "\n  - ".join(miss))
        return 1 if miss else 0
    elif a.cmd in ("render", "produce"):
        from . import render
        d = pipeline.find(a.episode)
        render.render_episode(d, preview=getattr(a, "preview", False))
        if a.cmd == "produce":
            return _qc(d)
    elif a.cmd == "qc":
        return _qc(pipeline.find(a.episode))
    elif a.cmd == "approve":
        from . import qc
        if not a.confirm_all:
            print("Watch the video first, then re-run with --confirm-all to confirm:")
            for h in qc.HUMAN_REVIEW:
                print(f"  - {h}")
            return 1
        rec = pipeline.approve(pipeline.find(a.episode), a.reviewer, [True] * len(qc.HUMAN_REVIEW), a.notes)
        print(f"approved {rec['episode_id']} ({rec['video_sha256'][:12]}) - publishing still requires you to post it yourself")
    elif a.cmd == "export":
        ex = pipeline.export(pipeline.find(a.episode))
        print(f"export package ready (not published): {config.rel(ex)}")
    elif a.cmd == "sheet":
        from . import sheet
        print(sheet.model_sheet())
    elif a.cmd == "lock-characters":
        print(pipeline.lock_characters(a.reviewer))
    elif a.cmd == "sfx":
        from . import audio
        names = audio.export_sfx_library(config.AUDIO_DIR / "sfx")
        print(f"wrote {len(names)} effects to {(config.AUDIO_DIR / 'sfx').relative_to(config.ROOT)}")
    elif a.cmd == "prompts":
        from . import prompts
        print(prompts.write_prompts(pipeline.find(a.episode)))
    elif a.cmd == "dashboard":
        from . import dashboard
        dashboard.serve(a.host, a.port)
    return 0


def _qc(d):
    from . import episode, qc
    ep = episode.load(d)
    r = qc.run_qc(d)
    for c in r.checks:
        print(f"  {c['status']:<4} {c['check']}: {c['detail']}")
    print(f"QC {'PASSED' if r.passed else 'FAILED'} - report: build/{ep['id']}/qc_report.md")
    return 0 if r.passed else 1


if __name__ == "__main__":
    sys.exit(main())
