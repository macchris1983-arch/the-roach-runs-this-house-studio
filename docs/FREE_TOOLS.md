# Free-first tools policy

Budget: **$0**. The core pipeline uses only free, open-source software that runs on your own computer:

| Tool | Used for | Licence |
|---|---|---|
| Python | everything | PSF licence |
| Pillow | drawing characters, sets, effects | MIT-CMU (HPND) |
| NumPy / SciPy | voice synthesis, SFX, music, mixing | BSD |
| PyYAML | episode files | MIT |
| FFmpeg + libass | encoding, captions, QC measurements | LGPL/GPL |
| Poppins font (optional) | captions | SIL Open Font Licence |

## Optional tools (not required, not integrated)

These are open-source and cost nothing to download. They are listed as upgrade paths only; none is required.

- **Audacity**: clean up recorded voice lines before dropping them into `voice/`.
- **Blender**: if the show ever moves to 3D or needs hand-animated shots.
- **Piper** (open-source local text-to-speech): can generate WAV voice lines to drop into `voice/`. Voice models have their own licences; check each model's licence before commercial use.

## Paid / credit-based generators

Online AI image/video/voice generators usually run on credits or subscriptions, and their free tiers and terms change often. The studio does **not** call any of them. `python -m studio prompts <id>` writes consistent per-shot prompts in `prompts/` in case you choose to try one manually. Before using any outside service, check its current pricing and its terms on commercial use and watermarks, and record any asset you import in `assets/LICENSES.yaml` (QC fails on unrecorded media files).
