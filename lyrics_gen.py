"""
YuE Studio — AI Lyrics Generator (requires ANTHROPIC_API_KEY)

Usage:
    python lyrics_gen.py --preset lofi_hiphop --theme "Amsterdam canal nights"
    python lyrics_gen.py --style "trap" --theme "grinding through the winter" --output prompts/lyrics.txt
"""

import argparse
import os
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent))
from yue_studio import PRESETS

SYSTEM = """You are a lyricist for ChilledPunks, an independent music label in Almere, Netherlands.
Styles: lo-fi hip-hop, Afrobeats, Dutch rap, R&B, moombahton, chill electronic.

Rules:
- Authentic, not over-polished. Personal + universal themes.
- Use [verse], [chorus], [bridge], [outro] labels. Separate sections with a blank line.
- Max ~12 lines per section (≈30s at YuE defaults).
- Do NOT start with [intro] — less stable in YuE.
- Return ONLY the lyrics, no preamble, no explanation."""


def generate(preset_key, theme, style_hint="", sections=2):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    p = PRESETS.get(preset_key, {})
    prompt = (
        f"Write {sections}-section lyrics for a {p.get('name', preset_key)} track.\n"
        f"Genre tags: {p.get('genre_tags', style_hint)}\n"
        f"Theme: {theme}\n"
        + (f"Style notes: {style_hint}\n" if style_hint else "")
        + "Include [verse] and [chorus] at minimum."
    )
    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=800,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--preset",   choices=list(PRESETS.keys()), default="lofi_hiphop")
    p.add_argument("--theme",    required=True)
    p.add_argument("--style",    default="")
    p.add_argument("--sections", type=int, default=2)
    p.add_argument("--output",   type=Path)
    args = p.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("✗ Set ANTHROPIC_API_KEY"); sys.exit(1)

    print(f"Generating lyrics: {args.preset} / '{args.theme}'")
    lyrics = generate(args.preset, args.theme, args.style, args.sections)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(lyrics)
        print(f"✓ Saved → {args.output}")
    else:
        print("\n" + "─"*40 + "\n" + lyrics + "\n" + "─"*40)


if __name__ == "__main__":
    main()
