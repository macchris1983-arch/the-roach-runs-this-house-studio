# Production guide

How to take an episode from idea to a ready-to-post Facebook Reel. Target is 3 Reels a day, so the workflow is built around editing one text file and pressing render.

## 1. Idea → production folder

```bash
python -m studio new "The Midnight Snack" --logline "..." --hook "..." --punchline "..."
```

Or use **+ New episode** in the dashboard. Season 1 episodes 2–10 already have folders with an `outline:` (8 beats) to break down.

## 2. Script → shots

Open `episodes/season-01/<episode>/episode.yaml`. Use Episode 1 as the reference; it uses every feature. Each shot has:

```yaml
- id: B                      # shot name
  dur: 2.9                   # seconds
  background: kitchen        # kitchen | living_room | bedroom
  camera: {x: 740, y: 1180, zoom: 2.3, keys: [{at: 2.0, zoom: 2.6, from: 0.5}]}
  props: [{name: table, x: 720, y: 1330, z: 12}]
  actors:
    roach: {x: 770, y: 1326, scale: 1.0, z: 13, action: eat, expr: unbothered,
            hold: {R: spoon}, keys: [{at: 1.0, expr: smug, look: camera}]}
  fx:  [{type: flash, at: 0.4, dur: 0.2}]
  sfx: [{at: 0.1, name: crunch, gain: 0.6}]
  lines:
    - {id: L02, who: roach, at: 0.3, text: "It's soggy. You let it sit too long."}
```

- `at` times are seconds **from the start of the shot**.
- Keys change things over time. Numbers (x, y, scale, zoom) glide; `from:` holds still until that time; `ease:` is `linear | in | out | inout | overshoot | snap`. Words (expr, action, look, hold) switch instantly.
- Every dialogue line needs a unique `id` (L01, L02…). Captions are generated from `text`, so the text you write is exactly what appears on screen.
- Lip-sync, blinking and talking gestures are automatic.
- The full list of expressions, actions, props, effects and sounds is at the top of `templates/episode_template.yaml`.

**Comedy checklist:** hook in the first 2 s (visual + first line), one clear escalation, a twist, a punchline that lands on a close-up, and an ending that loops back to the opening.

Check your work any time:

```bash
python -m studio validate s01e05      # typos, unknown names, length, overlapping lines
python -m studio render s01e05 --preview   # quick 540x960 draft
```

## 3. Voices

By default each character gets an original synthesised cartoon voice (their own pitch and style). To use real voices, record each line (phone voice memo is fine), convert to WAV, and save it as `voice/L01.wav`, `voice/L02.wav`… in the episode folder. Recorded files automatically replace the synth for that line and drive the lip-sync. Free options: your own voice/actors, Audacity for cleanup, or any local open-source TTS that outputs WAV.

## 4. Render + QC

```bash
python -m studio produce s01e05
```

Writes to `build/s01e05/`: the MP4, `captions.srt`, `mix.wav`, `contact_sheet.jpg` (one frame per shot), `cover.jpg`, `manifest.json`, and `qc_report.md`.

QC verifies: 1080×1920, 30 fps, H.264/yuv420p, 20–40 s, AAC audio of matching length, a clean full decode, no missing frames, no black stretches or long freezes, audio not silent or clipping, loudness ≈ −14 LUFS, captions word-for-word with the script, valid caption timing, readable caption speed, voice present in every caption window (sync), no missing shots, characters unchanged since render and matching the approved lock, and that every asset is generated in-house or licensed.

## 5. Approve → export

Watch the video on your phone. Then, in the dashboard (tick the 4 human-review boxes) or:

```bash
python -m studio approve s01e05 --reviewer "Chris" --confirm-all
python -m studio export s01e05
```

The export folder has the MP4, an `.srt`, `cover.jpg`, `post.txt` (caption + hashtags), the QC report and `POSTING_CHECKLIST.md`. Approval is tied to the exact video file (SHA-256), so any re-render needs re-approval. **The studio never posts; you upload to Facebook yourself.**

## Locking the character designs

The current designs are a draft built from the written description. When you approve them (after matching them to your reference image):

1. Set `approved: true` in `assets/characters/characters.yaml`
2. `python -m studio sheet` and check `assets/characters/model_sheet.png`
3. `python -m studio lock-characters --reviewer "Chris"`

From then on QC fails any render whose characters differ from the lock.

## Producing 3 a day

1. Break down tomorrow's 3 outlines into shots (copy a similar episode's shots and change them).
2. `validate` → `produce` each.
3. Batch review on your phone; approve + export.
4. Post on your own schedule.
