"""Optional: consistent text prompts for external image/video generators.

The studio renders everything itself for $0. If you later choose to use an
outside generator (free tier or paid), these prompts keep the characters
consistent by always describing them from the same character bible.
No external service is called from here.
"""
from __future__ import annotations

from pathlib import Path

from . import config, episode, rigs

STYLE = ("2D flat cartoon, bold clean dark outlines, simple cel shading, bright warm colours, "
         "household sitcom comedy, vertical 9:16 composition, no text, no watermark, no logos")

LOOKS = {
    "wife": "Black woman, high curly afro puff hairstyle with a purple band, gold hoop earrings, purple pajamas "
            "with a pink heart print, pink fuzzy slippers",
    "husband": "Black man, short curly hair, full beard, green T-shirt, dark gray joggers, black slides",
    "roach": "small reddish-brown anthropomorphic cockroach standing upright, big expressive eyebrows, "
             "mischievous grin, long antennae",
}


def character_prompt(name: str) -> str:
    b = rigs.bible()[name]
    return f"{b['display_name']}: {LOOKS[name]}. Personality: {b['personality']}"


def write_prompts(ep_dir: Path) -> Path:
    ep = episode.load(ep_dir)
    out = [f"# Generation prompts - {ep['id']} {ep['title']}", "",
           "Use the character reference image as the image reference whenever the tool supports it.", "",
           "## Characters (paste these unchanged every time)", ""]
    out += [f"- {character_prompt(n)}" for n in ("wife", "husband", "roach")]
    out += ["", f"## Style\n\n{STYLE}", "", "## Shots", ""]
    for s in ep.get("shots") or []:
        who = ", ".join(f"{n} ({a.get('expr', 'neutral')}, {a.get('action', 'idle')})" for n, a in (s.get("actors") or {}).items())
        zoom = (s.get("camera") or {}).get("zoom", 1.0)
        framing = "close-up" if zoom >= 2 else "medium shot" if zoom >= 1.3 else "wide shot"
        lines = " / ".join(f"{l['who']}: \"{l['text']}\"" for l in s.get("lines") or [])
        out.append(f"### Shot {s['id']} ({s['dur']}s)\n\n{framing} in the {s['background'].replace('_', ' ')} at night. "
                   f"Characters: {who or 'none'}. {('Dialogue: ' + lines) if lines else ''}\n\nPrompt: {framing}, "
                   f"{s['background'].replace('_', ' ')}, {who}, {STYLE}\n")
    path = config.PROMPTS_DIR / f"{ep['id']}-{ep.get('slug', '')}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out))
    return path
