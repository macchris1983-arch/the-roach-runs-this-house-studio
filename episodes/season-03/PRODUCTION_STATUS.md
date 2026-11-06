# Season 3 — production status

## Completed

- Seven original 35-second episode scripts continue the final exchange from S02E07, The Main Event.
- 58 shots and 58 dialogue lines, each with an image-bound reference animation prompt.
- All five final reference sheets are mapped in the season manifest. The corrected two-arm/two-leg roach sheet is used.
- New adult guest characters: Pearl, Mr. Baines and Tasha. The guest roles are silent visual performances in this season's scripts.
- All seven `python -m studio validate s03eXX` commands returned exit 0 and OK.
- Source dialogue and speaker identities match every reference-plan entry; referenced image files exist.
- Source files were uploaded to GitHub and their blob hashes matched the locally checked files.

## Not completed

These are complete scripts and production plans, not completed new-art animated videos. The existing engine uses procedural cut-out rigs from `characters.yaml` and `studio/rigs.py`, not the new PNG character references. Its babble voice is scratch audio, not natural final dialogue. The image reference fields do not change that engine automatically.

The required `python -m studio produce s03eXX` commands were attempted locally. An initial production run was stopped without a completed result. A diagnostic reached frame 0/1050 at about 12 seconds; a 15-second trace found image rotation work in `studio/render.py`. Each subsequent bounded production attempt was stopped at 15 seconds (exit 124), before a completed render/QC result. This time limit is a local check limit, not proof the renderer can never complete. No render/QC pass, owner approval or finished new-art video is claimed.

| Episode | Validate | Bounded production attempt |
| --- | --- | --- |
| s03e01 | PASS | Timed out; no completed QC |
| s03e02 | PASS | Timed out; no completed QC |
| s03e03 | PASS | Timed out; no completed QC |
| s03e04 | PASS | Timed out; no completed QC |
| s03e05 | PASS | Timed out; no completed QC |
| s03e06 | PASS | Timed out; no completed QC |
| s03e07 | PASS | Timed out; no completed QC |

## Final animation handoff

1. Build one clean scene keyframe per shot using the identity references in `reference-plan.json`; never use a whole turnaround sheet as the literal video opening.
2. Preserve the premiere's face-down Husband position and the living-room landmarks from the Season 2 finale. Continue actions from the preceding shot rather than replaying arrivals.
3. Record distinct natural adult voices, retain the approved uncensored words, then align final durations to those performances. Planned shot durations are estimates, not word-aligned caption times.
4. Animate the active speaker's mouth only. Use the correct original faces, hair and wardrobe. Guests follow the supporting-cast reference; no extra limbs on the Roach.
5. Add low original music, short audience laughs only after the marked jokes, and captions from the final audio. Preserve natural gaps and the final reaction beat.
6. Review continuity, speech, lips, sound balance and caption accuracy before any approval/export. Do not publish or schedule from this package automatically.

No paid image/video/audio generation was submitted during this Season 3 build. No existing episodes, rigs, character locks or approval flags were changed. No code changes were made, so a code test-suite pass is not claimed.
