"""Global production settings for The Roach Runs This House studio."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Facebook Reels delivery format
WIDTH = 1080
HEIGHT = 1920
FPS = 30
MIN_SECONDS = 20.0
MAX_SECONDS = 40.0

AUDIO_RATE = 48000
TARGET_LUFS = -14.0

# Reels UI covers the bottom ~20% and the right edge; keep captions above it.
CAPTION_SAFE_BOTTOM = 0.30  # fraction of height reserved at the bottom

# Folders
ASSETS = ROOT / "assets"
CHARACTERS_DIR = ASSETS / "characters"
AUDIO_DIR = ASSETS / "audio"
EPISODES_DIR = ROOT / "episodes"
EXPORTS_DIR = ROOT / "exports"
BUILD_DIR = ROOT / "build"          # scratch renders (git-ignored)
TEMPLATES_DIR = ROOT / "templates"
PROMPTS_DIR = ROOT / "prompts"

# Pipeline stages, in order
STAGES = [
    "idea", "script", "scenes", "character_visuals", "animation", "voice",
    "sound", "captions", "editing", "render", "quality_check", "approval", "export",
]


def rel(path) -> str:
    """Path relative to the repo root when possible (for display)."""
    p = Path(path).resolve()
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)
