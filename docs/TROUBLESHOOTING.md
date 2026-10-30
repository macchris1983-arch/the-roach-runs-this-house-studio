# Troubleshooting

**`ffmpeg: command not found` / render fails immediately**
FFmpeg isn't on your PATH. Install it (see INSTALL.md) and open a new terminal.

**`No such filter: 'ass'`**
Your FFmpeg build lacks libass. Use the official builds from ffmpeg.org (Windows: gyan.dev "full" build) or Homebrew/apt packages.

**Captions use the wrong font**
Install Poppins, then re-render. On Linux run `fc-cache -f` after installing.

**`Episode file has problems: unknown expression 'x'`**
Typo in `episode.yaml`. The valid names are listed at the top of `templates/episode_template.yaml`.

**`Dialogue timing problems: line L04 ends at ... but L05 starts at ...`**
Two lines overlap. Move the second line's `at` later, or lengthen the shot's `dur`. Run `python -m studio validate <id>` to see every line's timing.

**`total length 18.2s is outside 20-40s`**
Add or lengthen shots. Reels between 20 and 40 s are the production target.

**A character is off-screen or cut off**
World coordinates are 1080 wide × 1920 tall; `y` is where the feet are. With `zoom: 2`, only half the width is visible around the camera's `x, y`. Render a `--preview` and check `contact_sheet.jpg`.

**QC: "Character designs unchanged since render: FAIL"**
`characters.yaml` or `studio/rigs.py` changed after the render. Re-render.

**QC: "Characters match the approved design lock: FAIL"**
The characters were changed after they were approved. Either revert the change or get the new design approved and re-run `lock-characters`.

**QC: "No voice in: [L03]"**
That line's audio is silent; usually an empty or very quiet `voice/L03.wav`. Re-record or delete it to fall back to the synth voice.

**Dashboard won't open**
Make sure `python -m studio dashboard` is still running, and use `http://127.0.0.1:8765`. Use `--port 8800` if 8765 is taken.

**Approval says "video changed after approval"**
You re-rendered after approving. Watch the new version and approve again.
