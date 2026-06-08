"""
YuE Studio — Stem Splitter
Post-processing stem separation for generated tracks.

YuE only outputs `mixed_output.wav`, `vocal_output.wav`, and
`instrumental_output.wav`.  This module splits the mixed (or any other
track) into individual instrument stems — drums, bass, vocals, guitar,
piano, other — using the `audio-separator` library (Demucs / MDX-Net
under the hood).

Usage (library):
    from stem_splitter import split_stems
    paths = split_stems("output/foo/mixed_output.wav",
                        output_dir="output/foo/stems")
    # -> [Path("(Vocals).wav"), Path("drums.wav"), ...]

Usage (CLI):
    python stem_splitter.py output/foo/mixed_output.wav
    python stem_splitter.py output/foo/mixed_output.wav --model htdemucs
    python stem_splitter.py output/foo/mixed_output.wav --output-dir ./stems

Requires: pip install audio-separator   (already listed in
requirements_studio.txt — optional, only needed when you actually split)
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Optional


# Available model presets.  (4-stem, 6-stem, etc.)
MODELS = {
    "htdemucs_6s": "6 stems: vocals, drums, bass, other, guitar, piano",
    "htdemucs":    "4 stems: vocals, drums, bass, other",
    "mdx_extra":   "12 stems: vocals, drums, bass, guitar, piano, ..." \
                   " (slower, higher quality)",
    "htdemucs_ft": "4 stems (fine-tuned, higher quality)",
}
DEFAULT_MODEL = "htdemucs_6s"


def _try_import_separator():
    """Lazy import so the rest of YuE Studio works without audio-separator."""
    try:
        from audio_separator.separator import Separator  # type: ignore
        return Separator
    except ImportError as e:
        raise RuntimeError(
            "audio-separator is not installed.  Run:\n"
            "    pip install audio-separator\n"
            "then re-run.  See requirements_studio.txt for the full dep list."
        ) from e


def split_stems(
    audio_path: Path,
    output_dir: Optional[Path] = None,
    model: str = DEFAULT_MODEL,
    use_soundfile: bool = True,
) -> list[Path]:
    """
    Split an audio file into stems and return the list of stem paths.

    By default writes WAV files via soundfile (good quality, no
    ffmpeg re-encode).  Falls back to whatever audio-separator's
    default writer does if soundfile isn't available.

    Returns the list of stem file paths (in the order audio-separator
    produces them, which is alphabetical by stem name).
    """
    audio_path = Path(audio_path).expanduser().resolve()
    if not audio_path.exists():
        raise FileNotFoundError(f"audio file not found: {audio_path}")
    if audio_path.suffix.lower() not in (".wav", ".mp3", ".flac", ".ogg", ".m4a"):
        raise ValueError(f"unsupported audio format: {audio_path.suffix}")

    if output_dir is None:
        output_dir = audio_path.parent / "stems"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    Separator = _try_import_separator()
    # Try to use the soundfile writer (writes .wav) when available
    output_format = "WAV" if use_soundfile else None
    try:
        from audio_separator.separator.common import (
            common_separate_output_args,
        )  # type: ignore  # not all versions expose this
    except Exception:
        common_separate_output_args = None  # type: ignore

    separator = Separator(
        model_filename=model,
        output_dir=str(output_dir),
        output_format=output_format,
    )
    # Some versions of audio-separator take a list, some take a single
    # path; cover both.  We pass a single path here.
    try:
        result = separator.separate(str(audio_path))
    except TypeError:
        # Older API: separate([str(audio_path)])
        result = separator.separate([str(audio_path)])

    # Result is a list of (filename, audio_data) tuples (or a path list,
    # depending on version).  Build a concrete list of stem file paths.
    stems: list[Path] = []
    if isinstance(result, list):
        for item in result:
            if isinstance(item, tuple) and len(item) >= 1:
                # (filename, ...) tuple
                fname = item[0]
            elif isinstance(item, (str, Path)):
                fname = item
            else:
                continue
            p = Path(fname)
            if not p.is_absolute():
                p = output_dir / p
            stems.append(p)
    # If we still got nothing, fall back to scanning the output dir.
    if not stems:
        stems = sorted(output_dir.glob("*.wav"))
    return stems


# ─── CLI ────────────────────────────────────────────────────────────────────
def _cli() -> int:
    import argparse

    p = argparse.ArgumentParser(
        description="Split a generated YuE track into individual stems "
                    "(vocals, drums, bass, guitar, piano, other).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("audio", type=Path, help="Path to the audio file to split")
    p.add_argument("--model", choices=list(MODELS.keys()), default=DEFAULT_MODEL,
                   help=f"Model to use (default: {DEFAULT_MODEL})")
    p.add_argument("--output-dir", type=Path, default=None,
                   help="Where to write the stems (default: <audio>/stems/)")
    args = p.parse_args()

    try:
        stems = split_stems(args.audio, output_dir=args.output_dir, model=args.model)
    except RuntimeError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"✗ Stem split failed: {e}", file=sys.stderr)
        return 1

    print(f"\n✓ Split {len(stems)} stems from {args.audio}:")
    for s in stems:
        size_mb = s.stat().st_size / 1_048_576 if s.exists() else 0
        print(f"  → {s}  ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
