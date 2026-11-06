# The Roach Runs This House — Production Studio

An original 2D animated comedy series starring a husband, wife, and one troublemaking cockroach. This repo is a free-first production studio that turns a script file into a finished Facebook Reel: original characters, dialogue and voices, sound effects, music, captions, quality checks and a ready-to-post package.

**Everything renders locally for $0** with Python, Pillow, NumPy/SciPy and FFmpeg. No paid services, no API keys, nothing is ever posted automatically.

## What it does

```
IDEA → SCRIPT → SCENES → CHARACTER VISUALS → ANIMATION → VOICE → SOUND → CAPTIONS
     → EDITING → RENDER → QUALITY CHECK → APPROVAL → EXPORT
```

| Stage | How it works here |
|---|---|
| Script, scenes, storyboard | One `episode.yaml` per episode: shots, camera moves, acting keyframes, dialogue, sound cues |
| Character visuals | Cut-out 2D rigs for The Wife, The Husband and The Roach, drawn from `assets/characters/characters.yaml` (15 expressions, 26 actions, costume variants, extra roach cast) |
| Animation | Keyframed positions/expressions + procedural acting (walk, scream, tremble, wind-up…), automatic blinking and lip-sync |
| Voice | Built-in original "cartoon voice" synthesiser per character, **or** drop your own recordings in `voice/L01.wav` |
| Sound | 27 original synthesised SFX + an original generated music bed that ducks under dialogue |
| Captions | Speaker-coloured captions burned into the video + `.srt` file, placed above the Reels UI |
| Render | 1080×1920, 30 fps, H.264/AAC, two-pass loudness normalisation to −14 LUFS |
| Quality check | 23 automated checks + a 4-item human review checklist |
| Approval / export | You approve; the studio builds an export folder with MP4, SRT, cover, caption text and a posting checklist. **You post it yourself.** |

## Quick start

```bash
pip install -r requirements.txt        # Pillow, numpy, scipy, PyYAML, pytest
# also needs FFmpeg (with libass) on your PATH, see docs/INSTALL.md

python -m studio list                  # all episodes + pipeline progress
python -m studio produce s01e01        # render + QC Episode 1 (~1.5 min)
python -m studio dashboard             # open http://127.0.0.1:8765
```

Then watch `build/s01e01/s01e01.mp4`, and if you're happy:

```bash
python -m studio approve s01e01 --reviewer "Chris" --confirm-all
python -m studio export s01e01         # -> exports/season-01/s01e01-kitchen-roach-panic/
```

## Season 1

| # | Episode | Stage |
|---|---|---|
| 1 | Kitchen Roach Panic | **Full production file; renders and passes QC** |
| 2 | The Roach Called Backup | **Full production file; renders and passes QC** |
| 3 | The Dinner Disaster | **Full production file; renders and passes QC** |
| 4 | Who Changed My Password? | **Full production file; renders and passes QC** |
| 5 | The Midnight Snack | **Full production file; renders and passes QC** |
| 6 | The Roach Gets Promoted | **Full production file; renders and passes QC** |
| 7 | Don't Touch My Food | **Full production file; renders and passes QC** |
| 8 | The Neighbor's Wi-Fi | **Full production file; renders and passes QC** |
| 9 | The $20 Shopping Trip | **Full production file; renders and passes QC** |
| 10 | Couples Game Night | **Full production file; renders and passes QC** |

## Repository layout

```
studio/            the production engine (Python package)
assets/characters/ character bible, model sheet, reference/ (put official art here)
assets/audio/sfx/  generated sound-effect library
episodes/season-01/<episode>/episode.yaml   one folder per episode
templates/         episode template used by `python -m studio new`
prompts/           optional prompts for external image/video tools
docs/              install, production guide, troubleshooting, free tools
tests/             automated tests (python -m pytest)
build/             renders + QC reports (not committed)
exports/           approved ready-to-post packages (videos not committed)
```

## Docs

- [Installation](docs/INSTALL.md)
- [Production guide](docs/PRODUCTION_GUIDE.md): writing and producing an episode
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Free tools policy](docs/FREE_TOOLS.md)
- [AGENTS.md](AGENTS.md): rules for AI assistants working in this repo

## Rights

All characters, artwork, scripts, branding and episodes are proprietary. All rights reserved. See [LICENSE](LICENSE).


## Season 3 — No Free Rides

[Read all seven scripts and the season arc](episodes/season-03/README.md). The premiere picks up the Season 2 finale's “Rematch. Season three.” / “Pay rent first.” exchange. Each episode includes an engine-compatible source file and a shot-by-shot plan using the [new character reference images](assets/characters/reference/README.md).

Scripts and shot plans are complete; all seven source files passed validation. Finished animation in the new image style is pending. See the [production status and render limits](episodes/season-03/PRODUCTION_STATUS.md) before treating any local rig output as a final episode.
