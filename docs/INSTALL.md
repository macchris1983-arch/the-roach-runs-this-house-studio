# Installation

Everything here is free and open-source.

## 1. Python 3.10 or newer

- Windows: install from python.org (tick "Add Python to PATH").
- Mac: `brew install python`
- Linux: usually already installed.

## 2. FFmpeg (must include libass, which most builds do)

- Windows: `winget install Gyan.FFmpeg` (or download from ffmpeg.org) and make sure `ffmpeg` and `ffprobe` work in a new terminal.
- Mac: `brew install ffmpeg`
- Ubuntu/Debian: `sudo apt install ffmpeg fontconfig`

Check: `ffmpeg -filters | grep ass` should list the `ass` and `subtitles` filters.

## 3. The studio

```bash
git clone https://github.com/macchris1983-arch/the-roach-runs-this-house-studio.git
cd the-roach-runs-this-house-studio
python -m venv .venv
# Windows: .venv\Scripts\activate     Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q                   # should say all tests passed
python -m studio produce s01e01       # renders Episode 1 and runs QC
```

## 4. Caption font (recommended)

Captions use **Poppins** (free, SIL Open Font Licence) if installed, otherwise DejaVu Sans. Install Poppins from fonts.google.com for the intended look; no code changes needed.

## Hardware

No GPU needed. Episode 1 (32 s) renders in about 1.5 minutes on a 2-core cloud machine; most laptops are similar or faster.

## Configuration

There are no API keys or accounts to configure. Production settings (resolution, fps, length limits, loudness, caption safe area) live in `studio/config.py`. See `config.example.env` for the empty template if you add optional integrations later.
