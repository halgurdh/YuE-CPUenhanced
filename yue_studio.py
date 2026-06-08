"""
YuE Studio — Local Music Generation
Inspired by ChilledPunks NL · Optimized for RTX 3060 8GB

Usage:
    python yue_studio.py                        # interactive wizard
    python yue_studio.py generate --preset lofi_hiphop
    python yue_studio.py generate --genre prompts/genre.txt --lyrics prompts/lyrics.txt
    python yue_studio.py generate --preset afro_pop --icl --vocal v.mp3 --instrumental i.mp3
    python yue_studio.py generate --preset trap --loop           # Loop Mode (auto-detect bars)
    python yue_studio.py generate --preset lofi_hiphop --loop --loop-bars 16 --loop-segments 2
    python yue_studio.py presets
    python yue_studio.py ui
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

console = Console()

# ─── RTX 3060 Ti 8GB profile ──────────────────────────────────────────────────
# At 8GB VRAM the safe defaults are:
#   - 1 segment only (≈30s audio) — 2 segments risks OOM at full precision
#   - stage2_batch_size = 2 (not 4)
#   - infer.py uses SDPA (PyTorch built-in) — no flash-attn needed on Windows
#   - Consider YuEGP or YuE-exllamav2 for quantized inference (links in README)
#
# HARD CAP: 8GB VRAM cannot safely exceed ~30s of audio.  Any attempt to
# generate more is forcibly clamped down.  For longer songs use
# YuEGP (quantized, 6GB+) or YuE-exllamav2 (see README).
MAX_SEGMENTS = 1          # ≈30 s of audio
MAX_DURATION_SECONDS = 30  # hard ceiling on output length
RTX_3060_PROFILE = {
    "run_n_segments": MAX_SEGMENTS,
    "stage2_batch_size": 2,
    "max_new_tokens": 3000,
    "repetition_penalty": 1.1,
    "max_segments": MAX_SEGMENTS,
    "max_duration_seconds": MAX_DURATION_SECONDS,
    "note": "8GB VRAM profile: 1 segment ≈ 30s audio. Uses PyTorch SDPA (no flash-attn required).",
}


def clamp_to_30s(segments: int, bars_per_section: int = 0) -> int:
    """
    Hard-clamp the segment count so output never exceeds ~30 s on 8GB VRAM.
    Extra segments are rejected (warning printed elsewhere).  Loop Mode
    uses this when the auto-bump would push over the cap.
    """
    return max(1, min(int(segments), MAX_SEGMENTS))

# ─── Models ──────────────────────────────────────────────────────────────────
MODELS = {
    "cot_en":    "m-a-p/YuE-s1-7B-anneal-en-cot",
    "icl_en":    "m-a-p/YuE-s1-7B-anneal-en-icl",
    "cot_zh":    "m-a-p/YuE-s1-7B-anneal-zh-cot",
    "icl_zh":    "m-a-p/YuE-s1-7B-anneal-zh-icl",
    "cot_jpkr":  "m-a-p/YuE-s1-7B-anneal-jp-kr-cot",
    "icl_jpkr":  "m-a-p/YuE-s1-7B-anneal-jp-kr-icl",
    "stage2":    "m-a-p/YuE-s2-1B-general",
    "upsampler": "m-a-p/YuE-upsampler",
}

# ─── Full genre tag library (from top_200_tags.json) ─────────────────────────
# Organised into categories for the genre selector
GENRE_TAGS = {
    "Genre": [
        "pop", "hip-hop", "rap", "rnb", "soul", "jazz", "blues", "rock", "indie",
        "electronic", "edm", "house", "techno", "trance", "drum-and-bass", "dubstep",
        "reggae", "reggaeton", "dancehall", "afropop", "afrobeats", "latin", "bossa-nova",
        "country", "folk", "classical", "orchestral", "ambient", "lofi", "chillout",
        "moombahton", "trap", "drill", "grime", "metal", "punk", "emo",
    ],
    "Mood": [
        "uplifting", "mellow", "energetic", "melancholic", "dark", "happy", "sad",
        "romantic", "aggressive", "chill", "groovy", "inspiring", "dreamy", "nostalgic",
        "intense", "playful", "emotional", "peaceful", "mysterious",
    ],
    "Vocals": [
        "male", "female", "vocal", "no-vocal", "instrumental", "choir", "rap-vocal",
        "spoken-word", "airy vocal", "bright vocal", "warm vocal", "deep vocal",
        "falsetto", "growl",
    ],
    "Instruments": [
        "piano", "guitar", "acoustic guitar", "electric guitar", "bass", "drums",
        "synthesizer", "synth", "violin", "saxophone", "trumpet", "flute", "harp",
        "ukulele", "banjo", "cello", "organ", "harmonica", "percussion",
    ],
    "Timbre / Production": [
        "vinyl", "lo-fi", "hi-fi", "raw", "polished", "warm", "bright", "dark",
        "heavy", "light", "airy", "gritty", "smooth", "distorted", "clean", "reverb",
        "delay", "808", "trap-beat", "boom-bap",
    ],
    "Language": [
        "English", "Mandarin", "Cantonese", "Japanese", "Korean",
    ],
}

# ─── ChilledPunks presets ─────────────────────────────────────────────────────
PRESETS = {
    "lofi_hiphop": {
        "name": "Lo-Fi Hip-Hop",
        "description": "Chill dusty beats — Allgood / Almere vibes",
        "genre_tags": "lofi hip-hop instrumental male mellow acoustic piano vinyl warm beats",
        "lyric_template": (
            "[verse]\nLate nights in the city glow\nNeon reflections on the canal below\n"
            "Beats drifting through the smoke-filled air\nA city full of souls without a care\n\n"
            "[chorus]\nJust let it breathe, let it flow\nLofi dreams where we go slow\n"
            "Through the haze we find our way\nOne more chill, one more day"
        ),
    },
    "afro_pop": {
        "name": "Afro-Pop",
        "description": "Groovy Afrobeats with catchy hooks — Kchris energy",
        "genre_tags": "afropop female uplifting dancehall groovy percussion bright vocal",
        "lyric_template": (
            "[verse]\nRising up, feeling the beat inside\nRhythm of the ancestors, ancient pride\n"
            "Dancing feet on Amsterdam stone\nCarrying melodies from home\n\n"
            "[chorus]\nMove your body, feel alive\nAfro soul, we will survive\n"
            "Every beat a heartbeat true\nThis music made for me and you"
        ),
    },
    "moombahton": {
        "name": "Moombahton",
        "description": "Half-time bass-driven underground",
        "genre_tags": "moombahton electronic bass male energetic synth dark vocal dance 808",
        "lyric_template": (
            "[verse]\nDeep in the underground we ride\nLow frequencies, nowhere to hide\n"
            "Bass drops heavy on your chest\nPutting every track to the test\n\n"
            "[chorus]\nFeel the bass, let it shake the floor\nMoombahton knocking at your door\n"
            "Subwoofer pressure, speakers blow\nUnderground vibes, let it go"
        ),
    },
    "hip_hop_nl": {
        "name": "Dutch Hip-Hop",
        "description": "Raw NL street rap — Ridicuul / Mc Drt style",
        "genre_tags": "hip-hop rap male gritty urban boom-bap bass kick snare raw",
        "lyric_template": (
            "[verse]\nStreets of Almere raised me right\nHustling hard from day to night\n"
            "Words like bullets, flow precise\nEvery rhyme paid the price\n\n"
            "[chorus]\nNever stop, never fold\nDutch rap, stories told\n"
            "From the blocks to the world stage\nFlipping struggle into rage"
        ),
    },
    "chillout": {
        "name": "Chillout / Ambient",
        "description": "Atmospheric slow-burn — late night radio",
        "genre_tags": "ambient electronic female airy piano pad atmospheric slow vocal dreamy reverb",
        "lyric_template": (
            "[verse]\nStars above the waterway tonight\nCity sleeps beneath the amber light\n"
            "Breathing slow, the world falls still\nTime dissolves, it always will\n\n"
            "[chorus]\nDrift away, let go of time\nEvery note a gentle climb\n"
            "In the quiet find yourself\nMelodies left on the shelf"
        ),
    },
    "rnb_soul": {
        "name": "R&B / Soul",
        "description": "Smooth soulful vocals with lush production",
        "genre_tags": "rnb soul female smooth warm saxophone piano emotional vocal expressive romantic",
        "lyric_template": (
            "[verse]\nYou walked in slow motion through the door\nI had been searching, what for?\n"
            "Something real in a world of pretend\nA feeling I hope never ends\n\n"
            "[chorus]\nGive me your soul, give me truth\nTake me back to when we were youth\n"
            "Every note every word every line\nSoul music making you mine"
        ),
    },
    "trap": {
        "name": "Trap",
        "description": "Heavy 808s, hi-hats, dark energy",
        "genre_tags": "trap rap male dark aggressive 808 hi-hat synthesizer bass energetic gritty",
        "lyric_template": (
            "[verse]\nWoke up in the dark again\nChasing moves, dodging pain\n"
            "Every day a different game\nSilent streets know my name\n\n"
            "[chorus]\nTrap life, no way out\n808s all through the drought\n"
            "Moving quiet, speaking loud\nRising solo from the crowd"
        ),
    },
    "jazz_soul": {
        "name": "Jazz Soul",
        "description": "Smooth jazz undertones with soulful delivery",
        "genre_tags": "jazz soul female saxophone piano smooth warm emotional vocal mellow nostalgic",
        "lyric_template": (
            "[verse]\nSmoke and candlelight, a jazz club haze\nYour silhouette through the smoky gaze\n"
            "Trumpet wails like a heart on fire\nThe bassist walks us a little higher\n\n"
            "[chorus]\nPlay it slow, make it breathe\nEvery note a place to grieve\n"
            "Jazz and soul, the oldest cure\nMusic keeps the heart pure"
        ),
    },
    "reggaeton": {
        "name": "Reggaeton",
        "description": "Dembow rhythm, tropical energy",
        "genre_tags": "reggaeton latin male female dancehall groovy percussion energetic vocal uplifting",
        "lyric_template": (
            "[verse]\nSunset on the Amstel shore\nDembow rhythm to the core\n"
            "Moving with the crowd tonight\nEverything is feeling right\n\n"
            "[chorus]\nBaila, baila, feel the beat\nMovement from your head to feet\n"
            "Reggaeton never stops\nUntil the morning drops"
        ),
    },
}

# ─── Genre → bar count mapping (Loop Mode) ───────────────────────────────────
# Used by get_loop_config() to auto-detect the number of bars per section
# based on the dominant genre. Values are common defaults for that genre's
# phrasing / loop length. Genres not listed fall back to 8 bars.
# Approximate seconds-per-bar: 4/4 at ~100 BPM ≈ 2.4 s/bar.
GENRE_BAR_COUNT = {
    # ── 4 bars  (~10 s) — short loops, phrases ─────────────────────────────
    "trap":              4,
    "drill":             4,
    "grime":             4,
    "lofi":              4,
    "lo-fi":             4,
    "lofi hip-hop":      4,
    "boom-bap":          4,
    "hip-hop":           4,
    "rap":               4,
    "reggaeton":         4,
    "dembow":            4,
    "moombahton":        4,
    "dubstep":           4,
    "drum-and-bass":     4,
    "dnb":               4,
    "house":             4,
    "techno":            4,
    # ── 8 bars  (~20 s) — default ─────────────────────────────────────────
    "pop":               8,
    "electronic":        8,
    "edm":               8,
    "dance":             8,
    "afropop":           8,
    "afrobeats":         8,
    "dancehall":         8,
    "latin":             8,
    "rnb":               8,
    "soul":              8,
    "jazz":              8,
    "bossa-nova":        8,
    "blues":             8,
    "rock":              8,
    "indie":             8,
    "country":           8,
    "folk":              8,
    "reggae":            8,
    "punk":              8,
    "emo":               8,
    "trance":            8,
    # ── 16 bars (~40 s) — longer phrasing ─────────────────────────────────
    "ambient":           16,
    "chillout":          16,
    "classical":         16,
    "orchestral":        16,
    "ballad":            16,
    "jazz soul":         16,
}

DEFAULT_BAR_COUNT = 8  # 4/4, ~20 s — used when no genre matches


def get_loop_config(genre_tags: str, segments: int = 1) -> dict:
    """
    Auto-detect a sensible loop configuration from genre tags.

    Picks the *longest* matching bar count from GENRE_BAR_COUNT (so a tag
    string of "lofi hip-hop female" → 4 bars from 'lofi hip-hop', and
    "ambient chillout" → 16 bars from 'ambient').

    Returns a dict with:
        bars_per_section : int    — detected bar count
        bars_total       : int    — bars_per_section × segments
        segment_seconds  : float  — estimated seconds per segment (4/4 @ 100 BPM)
        total_seconds    : float  — total estimated length
        loop_tags        : str    — tags to append for loop-style output
        detected_genre   : str    — the genre key that matched (or 'default')
    """
    tags = [t.strip().lower() for t in genre_tags.split() if t.strip()]
    matched_genre = None
    matched_bars  = None

    # 2-word keys first (e.g. "lofi hip-hop", "drum-and-bass", "jazz soul")
    bigrams = [" ".join(tags[i:i + 2]) for i in range(len(tags) - 1)]
    for bg in bigrams:
        if bg in GENRE_BAR_COUNT:
            matched_genre = bg
            matched_bars  = GENRE_BAR_COUNT[bg]
            break

    # then 1-word keys
    if matched_bars is None:
        for t in tags:
            if t in GENRE_BAR_COUNT:
                matched_genre = t
                matched_bars  = GENRE_BAR_COUNT[t]
                break

    if matched_bars is None:
        matched_bars  = DEFAULT_BAR_COUNT
        matched_genre = "default"

    # ~2.4 s per bar (4/4 @ 100 BPM) — rough but consistent
    seconds_per_bar   = 2.4
    bars_per_section  = matched_bars
    bars_total        = bars_per_section * max(1, segments)
    segment_seconds   = bars_per_section * seconds_per_bar
    total_seconds     = bars_total * seconds_per_bar

    # Loop-style tags — guide the model towards seamless looping output
    loop_tags = "loop seamless-loop" if bars_per_section <= 8 else "loop extended"

    return {
        "bars_per_section": bars_per_section,
        "bars_total":       bars_total,
        "segment_seconds":  round(segment_seconds, 1),
        "total_seconds":    round(total_seconds, 1),
        "loop_tags":        loop_tags,
        "detected_genre":   matched_genre,
    }


# ─── Paths ────────────────────────────────────────────────────────────────────
YUE_DIR       = Path(os.environ.get("YUE_DIR",    Path.home() / "YuE"))
INFERENCE_DIR = YUE_DIR / "inference"
OUTPUT_DIR    = Path(os.environ.get("YUE_OUTPUT", Path(__file__).parent / "output"))
PROMPTS_DIR   = Path(__file__).parent / "prompts"
# Hugging Face model cache (override with HF_HOME env var)
HF_HOME       = Path(os.environ.get("HF_HOME", r"J:\Ai"))


def yue_subprocess_env() -> dict:
    """Environment for YuE inference subprocesses (HF cache, CUDA, etc.)."""
    hf_home = Path(os.environ.get("HF_HOME", str(HF_HOME)))
    hub_cache = Path(os.environ.get("HUGGINGFACE_HUB_CACHE", str(hf_home / "hub")))
    hf_home.mkdir(parents=True, exist_ok=True)
    hub_cache.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["HF_HOME"] = str(hf_home)
    env["HUGGINGFACE_HUB_CACHE"] = str(hub_cache)
    env["TRANSFORMERS_CACHE"] = os.environ.get(
        "TRANSFORMERS_CACHE", str(hf_home / "transformers"),
    )
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    env["TOKENIZERS_PARALLELISM"] = "false"
    env.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    return env

_YUE_PYTHON: Optional[str] = None


def python_has_torch(python: Path) -> bool:
    if not python.exists():
        return False
    try:
        r = subprocess.run(
            [str(python), "-c", "import torch"],
            capture_output=True,
            timeout=60,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def resolve_yue_python() -> str:
    """Python interpreter with torch + YuE deps (not necessarily the UI's Python)."""
    global _YUE_PYTHON
    if _YUE_PYTHON is not None:
        return _YUE_PYTHON

    override = os.environ.get("YUE_PYTHON")
    if override:
        p = Path(override)
        if p.exists() and python_has_torch(p):
            _YUE_PYTHON = str(p)
            return _YUE_PYTHON

    home = Path.home()
    candidates = [
        # Prefer YuEGP for quantized / lower-VRAM friendly inference.
        home / "miniconda3/envs/yuegp/python.exe",
        home / "miniconda3/envs/yuegp/bin/python",
        # Fallback to full-precision YuE.
        home / "miniconda3/envs/yue/python.exe",
        home / "miniconda3/envs/yue/bin/python",
        home / "anaconda3/envs/yue/python.exe",
        home / "anaconda3/envs/yue/bin/python",
        # Last resort: current interpreter.
        Path(sys.executable),
    ]
    for p in candidates:
        if python_has_torch(p):
            _YUE_PYTHON = str(p)
            return _YUE_PYTHON

    _YUE_PYTHON = sys.executable
    return _YUE_PYTHON


def banner():
    console.print(Panel.fit(
        "[bold yellow]🎵  YuE Studio[/bold yellow]\n"
        "[dim]ChilledPunks NL · RTX 3060 8GB optimized[/dim]",
        border_style="yellow",
    ))


def list_presets():
    table = Table(title="ChilledPunks Presets", border_style="yellow", show_lines=True)
    table.add_column("Key", style="cyan bold", no_wrap=True)
    table.add_column("Name", style="white")
    table.add_column("Description", style="dim")
    for key, p in PRESETS.items():
        table.add_row(key, p["name"], p["description"])
    console.print(table)


def show_genre_tags():
    """Display all available genre tags organised by category."""
    console.print("\n[bold yellow]Available Genre Tags[/bold yellow]\n")
    for cat, tags in GENRE_TAGS.items():
        console.print(f"[bold cyan]{cat}:[/bold cyan]")
        console.print("  " + "  ".join(f"[dim]{t}[/dim]" for t in tags))
        console.print()


def write_prompt_files(genre_tags: str, lyrics: str) -> tuple[Path, Path]:
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    genre_path  = PROMPTS_DIR / "genre.txt"
    lyrics_path = PROMPTS_DIR / "lyrics.txt"
    genre_path.write_text(genre_tags.strip())
    lyrics_path.write_text(lyrics.strip())
    return genre_path, lyrics_path


def _clamp_cuda_idx(cuda_idx: int, default: int = 0) -> int:
    """Clamp cuda_idx to a valid range for this machine.

    Prevents `RuntimeError: CUDA error: invalid device ordinal` when the
    UI/CLI requests a non-existent CUDA device.

    Note: This runs in the UI/launcher process, not inside infer.py.
    """
    try:
        import torch  # type: ignore

        device_count = torch.cuda.device_count()
        if device_count is None or device_count <= 0:
            return default

        if int(cuda_idx) < 0 or int(cuda_idx) >= int(device_count):
            return default
        return int(cuda_idx)
    except Exception:
        return default


def build_infer_command(
    genre_path: Path,
    lyrics_path: Path,
    output_dir: Path,
    cuda_idx: int = 0,

    stage1_model: str = MODELS["cot_en"],
    stage2_model: str = MODELS["stage2"],
    run_n_segments: int = 1,          # RTX 3060 safe default
    stage2_batch_size: int = 2,       # RTX 3060 safe default
    max_new_tokens: int = 3000,
    repetition_penalty: float = 1.1,
    seed: Optional[int] = None,
    use_audio_prompt: bool = False,
    audio_prompt_path: Optional[Path] = None,
    use_dual_tracks: bool = False,
    vocal_track: Optional[Path] = None,
    instrumental_track: Optional[Path] = None,
    prompt_start: int = 0,
    prompt_end: int = 30,
    rescale: bool = True,
) -> list[str]:
    cuda_idx = _clamp_cuda_idx(cuda_idx, default=0)

    cmd = [
        resolve_yue_python(), str(INFERENCE_DIR / "infer.py"),
        "--cuda_idx",          str(cuda_idx),

        "--stage1_model",      stage1_model,
        "--stage2_model",      stage2_model,
        "--genre_txt",         str(genre_path),
        "--lyrics_txt",        str(lyrics_path),
        "--run_n_segments",    str(run_n_segments),
        "--stage2_batch_size", str(stage2_batch_size),
        "--output_dir",        str(output_dir),
        "--max_new_tokens",    str(max_new_tokens),
        "--repetition_penalty",str(repetition_penalty),
    ]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    if rescale:
        cmd.append("-r")
    if use_dual_tracks and vocal_track and instrumental_track:
        cmd += [
            "--use_dual_tracks_prompt",
            "--vocal_track_prompt_path",        str(vocal_track),
            "--instrumental_track_prompt_path", str(instrumental_track),
            "--prompt_start_time", str(prompt_start),
            "--prompt_end_time",   str(prompt_end),
        ]
    elif use_audio_prompt and audio_prompt_path:
        cmd += [
            "--use_audio_prompt",
            "--audio_prompt_path",  str(audio_prompt_path),
            "--prompt_start_time",  str(prompt_start),
            "--prompt_end_time",    str(prompt_end),
        ]
    return cmd


def run_generation(cmd: list[str], output_dir: Path, verbose: bool = False) -> bool:
    output_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"\n[bold green]▶ Starting generation[/bold green]  [dim]→ {output_dir}[/dim]\n")

    with Progress(
        SpinnerColumn(spinner_name="dots", style="yellow"),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("[yellow]Generating with YuE...", total=None)
        try:
            env = yue_subprocess_env()
            proc = subprocess.Popen(
                cmd,
                cwd=str(INFERENCE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
            for line in proc.stdout:
                line = line.rstrip()
                if verbose:
                    console.print(f"[dim]{line}[/dim]")
                elif line and any(kw in line.lower() for kw in
                                  ["stage", "segment", "generating", "saving", "done", "error", "oom", "warning"]):
                    progress.update(task, description=f"[yellow]{line[:90]}")
            proc.wait()
        except FileNotFoundError:
            console.print(f"\n[bold red]✗ infer.py not found at {INFERENCE_DIR}[/bold red]")
            console.print("[dim]Set YUE_DIR env var or edit yue_studio.py YUE_DIR.[/dim]")
            return False
        except KeyboardInterrupt:
            proc.terminate()
            console.print("\n[yellow]⚠ Interrupted.[/yellow]")
            return False

    if proc.returncode != 0:
        console.print(f"\n[bold red]✗ Generation failed (exit {proc.returncode})[/bold red]")
        if not verbose:
            console.print("[dim]Re-run with --verbose to see full output.[/dim]")
        return False

    generated = sorted(list(output_dir.rglob("*.wav")) + list(output_dir.rglob("*.mp3")))
    if generated:
        console.print(f"\n[bold green]✓ Done! {len(generated)} file(s):[/bold green]")
        for f in generated:
            size_mb = f.stat().st_size / 1_048_576
            console.print(f"  [cyan]→[/cyan] {f}  [dim]({size_mb:.1f} MB)[/dim]")
    else:
        console.print("\n[yellow]⚠ No audio files found in output dir.[/yellow]")
    return True


# ─── Interactive wizard ───────────────────────────────────────────────────────

def interactive_mode():
    banner()
    console.print()
    console.print(Panel(
        "[yellow]RTX 3060 Ti 8GB defaults:[/yellow] 1 segment (~30s audio), batch size 2\n"
        "For 2 segments (~1 min) try --segments 2 — watch for OOM.\n"
        "For longer songs install [bold]YuEGP[/bold] (quantized): github.com/deepbeepmeep/YuEGP",
        title="⚠ GPU Profile",
        border_style="yellow",
        expand=False,
    ))
    console.print()

    # Preset or custom
    list_presets()
    preset_key = Prompt.ask(
        "\n[yellow]Choose a preset[/yellow]",
        choices=list(PRESETS.keys()) + ["custom"],
        default="lofi_hiphop",
    )

    if preset_key == "custom":
        show_genre_tags()
        genre_tags = Prompt.ask("Genre tags (space-separated from list above)")
        console.print("[dim]Enter lyrics with section labels. Blank line x2 to finish.[/dim]")
        lines = []
        while True:
            line = input()
            if not line and lines and not lines[-1]:
                break
            lines.append(line)
        lyrics = "\n".join(lines).strip()
    else:
        preset = PRESETS[preset_key]
        console.print(f"\n[bold yellow]{preset['name']}[/bold yellow] — {preset['description']}")

        # Allow tag editing
        console.print(f"\n[dim]Default tags:[/dim] {preset['genre_tags']}")
        show_tags = Confirm.ask("Browse/edit genre tags?", default=False)
        if show_tags:
            show_genre_tags()
            genre_tags = Prompt.ask("Genre tags", default=preset["genre_tags"])
        else:
            genre_tags = preset["genre_tags"]

        # Lyrics
        console.print(f"\n[dim]Default lyrics preview:[/dim]\n{preset['lyric_template'][:200]}...\n")
        use_default = Confirm.ask("Use default lyrics?", default=True)
        if use_default:
            lyrics = preset["lyric_template"]
        else:
            console.print("[dim](blank line x2 to finish)[/dim]")
            lines = []
            while True:
                line = input()
                if not line and lines and not lines[-1]:
                    break
                lines.append(line)
            lyrics = "\n".join(lines).strip()

    # Quick options
    instrumental_only = Confirm.ask("\nInstrumental only? (no vocals)", default=False)
    no_drums          = Confirm.ask("No drums?", default=False)
    if instrumental_only:
        for t in ["instrumental", "no-vocal"]:
            if t not in genre_tags.split():
                genre_tags += f" {t}"
    if no_drums and "no-drums" not in genre_tags:
        genre_tags += " no-drums"

    # Language / model
    lang = Prompt.ask(
        "\nLanguage model",
        choices=["en", "zh", "jp-kr"],
        default="en",
    )

    # ICL
    use_icl  = Confirm.ask("\nStyle reference (ICL) — provide a 30s reference audio?", default=False)
    use_dual = False
    audio_path = vocal_path = inst_path = None
    stage1_key = f"icl_{lang}" if use_icl else f"cot_{lang}"
    stage1_model = MODELS.get(stage1_key, MODELS["cot_en"])

    if use_icl:
        use_dual = Confirm.ask("Dual-track (vocal + instrumental)? [recommended]", default=True)
        if use_dual:
            vocal_path = Path(Prompt.ask("Vocal track path"))
            inst_path  = Path(Prompt.ask("Instrumental track path"))
        else:
            audio_path = Path(Prompt.ask("Reference audio path (30s WAV/MP3)"))

    # Advanced / RTX 3060 section
    console.print(f"\n[bold]GPU Settings[/bold]  [dim](RTX 3060 8GB safe defaults shown)[/dim]")
    segments   = int(Prompt.ask("Segments (1=~30s, 2=~1min — [red]2 may OOM on 8GB[/red])", default="1"))
    batch_size = int(Prompt.ask("Stage2 batch size (keep ≤2 for 8GB)", default="2"))
    max_tokens = int(Prompt.ask("Max new tokens", default="3000"))
    rep_pen    = float(Prompt.ask("Repetition penalty", default="1.1"))
    seed_str   = Prompt.ask("Seed (blank=random)", default="")
    seed       = int(seed_str) if seed_str.strip().isdigit() else None
    cuda_idx   = int(Prompt.ask("CUDA device index", default="0"))
    verbose    = Confirm.ask("Show full inference output?", default=False)

    ts = time.strftime("%Y%m%d_%H%M%S")
    output_dir = OUTPUT_DIR / f"{preset_key}_{ts}"

    genre_path, lyrics_path = write_prompt_files(genre_tags, lyrics)
    cmd = build_infer_command(
        genre_path=genre_path,
        lyrics_path=lyrics_path,
        output_dir=output_dir,
        cuda_idx=cuda_idx,
        stage1_model=stage1_model,
        run_n_segments=segments,
        stage2_batch_size=batch_size,
        max_new_tokens=max_tokens,
        repetition_penalty=rep_pen,
        seed=seed,
        use_audio_prompt=use_icl and not use_dual,
        audio_prompt_path=audio_path,
        use_dual_tracks=use_dual,
        vocal_track=vocal_path,
        instrumental_track=inst_path,
        rescale=True,
    )

    console.print(f"\n[dim]{' '.join(cmd)}[/dim]")
    if Confirm.ask("\nRun now?", default=True):
        run_generation(cmd, output_dir, verbose=verbose)


def launch_ui():
    ui_path = Path(__file__).parent / "yue_ui.py"
    if not ui_path.exists():
        console.print("[red]✗ yue_ui.py not found.[/red]")
        sys.exit(1)
    console.print("[yellow]Launching Gradio UI on http://localhost:7860[/yellow]")
    subprocess.run([sys.executable, str(ui_path)])


# ─── Stem splitting helper ─────────────────────────────────────────────────
def _pick_mixed_output(output_dir) -> Optional[Path]:
    """Find the best audio file to split inside an output dir.

    Prefers `mixed_output.wav`, then `*mixed*.wav`, then any .wav.
    Accepts str or Path for convenience.
    """
    output_dir = Path(output_dir) if output_dir else None
    if not output_dir or not output_dir.exists():
        return None
    candidates = (
        list(output_dir.rglob("mixed_output.wav"))
        + list(output_dir.rglob("mixed*.wav"))
        + list(output_dir.rglob("*.wav"))
    )
    # De-dup while preserving order
    seen, out = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[0] if out else None


def run_stem_split(
    output_dir: Path,
    model: str = "htdemucs_6s",
    stems_output_dir: Optional[Path] = None,
) -> bool:
    """
    Run stem separation on the mixed_output.wav inside `output_dir`.

    Uses the `stem_splitter` module.  Writes to
    `<output_dir>/stems/` by default.

    Returns True on success, False on any failure (including missing
    audio-separator — we print a friendly message and return False so
    the rest of the pipeline can continue).
    """
    audio = _pick_mixed_output(output_dir)
    if audio is None:
        console.print("[yellow]⚠ No audio file found in output dir, skipping stem split.[/yellow]")
        return False

    out_dir = Path(stems_output_dir) if stems_output_dir else (output_dir / "stems")
    console.print(
        f"\n[bold green]▶ Splitting stems[/bold green]  "
        f"[dim]audio={audio.name}  model={model}  → {out_dir}[/dim]\n"
    )
    try:
        from stem_splitter import split_stems  # lazy import
    except ImportError:
        console.print(
            "[bold red]✗ audio-separator is not installed.[/bold red]\n"
            "  Run:  pip install audio-separator\n"
            "  (already listed in requirements_studio.txt — uncomment and install)"
        )
        return False

    try:
        stems = split_stems(audio, output_dir=out_dir, model=model)
    except Exception as e:
        console.print(f"[bold red]✗ Stem split failed:[/bold red] {e}")
        return False

    if not stems:
        console.print("[yellow]⚠ Stem split returned no files.[/yellow]")
        return False

    console.print(f"[bold green]✓ {len(stems)} stems written:[/bold green]")
    for s in stems:
        size_mb = s.stat().st_size / 1_048_576 if s.exists() else 0
        console.print(f"  [cyan]→[/cyan] {s}  [dim]({size_mb:.1f} MB)[/dim]")
    return True


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="YuE Studio — local music generation (RTX 3060 8GB optimized)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd")

    # generate
    gen = sub.add_parser("generate", help="Generate a track")
    gen.add_argument("--preset", choices=list(PRESETS.keys()))
    gen.add_argument("--genre",  type=Path)
    gen.add_argument("--lyrics", type=Path)
    gen.add_argument("--output", type=Path)
    gen.add_argument("--lang",   choices=["en","zh","jp-kr"], default="en")
    gen.add_argument("--segments",   type=int,   default=RTX_3060_PROFILE["run_n_segments"])
    gen.add_argument("--batch-size", type=int,   default=RTX_3060_PROFILE["stage2_batch_size"])
    gen.add_argument("--max-tokens", type=int,   default=RTX_3060_PROFILE["max_new_tokens"])
    gen.add_argument("--rep-penalty",type=float, default=RTX_3060_PROFILE["repetition_penalty"])
    gen.add_argument("--seed",   type=int,   default=None)
    gen.add_argument("--cuda",   type=int,   default=0)
    gen.add_argument("--icl",    action="store_true")
    gen.add_argument("--instrumental-only", action="store_true", dest="instrumental_only",
                     help="No vocals — adds 'instrumental no-vocal' to genre tags")
    gen.add_argument("--no-drums", action="store_true", dest="no_drums",
                     help="No drums — adds 'no-drums' to genre tags")
    gen.add_argument("--audio",         type=Path)
    gen.add_argument("--vocal",         type=Path)
    gen.add_argument("--instrumental",  type=Path)
    gen.add_argument("--prompt-start",  type=int, default=0)
    gen.add_argument("--prompt-end",    type=int, default=30)
    gen.add_argument("--verbose",       action="store_true")
    # ── Loop Mode ───────────────────────────────────────────────────────
    gen.add_argument("--loop", action="store_true",
                     help="Enable Loop Mode: auto-detect bar count from genre, "
                          "auto-raise --max-tokens, and append loop tags.")
    gen.add_argument("--loop-bars", type=int, default=None, dest="loop_bars",
                     help="Override the auto-detected bar count (e.g. 4, 8, 16, 32). "
                          "Implies --loop.")
    gen.add_argument("--loop-segments", type=int, default=None, dest="loop_segments",
                     help="Override the segment count when --loop is set. "
                          "Total bars = bars_per_section × segments.")
    gen.add_argument("--print-loop-config", action="store_true", dest="print_loop_config",
                     help="Print the detected loop configuration and exit.")
    # ── Post-processing: stem split ─────────────────────────────────────
    gen.add_argument("--stem-split", action="store_true", dest="stem_split",
                     help="After generation, run stem separation on the mixed "
                          "output (drums / bass / vocals / other / etc).")
    gen.add_argument("--stem-model", default="htdemucs_6s", dest="stem_model",
                     choices=["htdemucs_6s", "htdemucs", "mdx_extra", "htdemucs_ft"],
                     help="Stem-split model (default: htdemucs_6s = 6 stems).")
    gen.add_argument("--stems-output-dir", type=Path, default=None, dest="stems_output_dir",
                     help="Where to write the stems (default: <output_dir>/stems/).")

    sub.add_parser("presets", help="List presets")
    sub.add_parser("tags",    help="Show all genre tags")
    sub.add_parser("ui",      help="Launch Gradio web UI")
    sub.add_parser("interactive", help="Interactive wizard")

    # ── split (standalone stem separation) ──────────────────────────────
    splt = sub.add_parser("split", help="Split an audio file into stems")
    splt.add_argument("audio", type=Path, help="Path to the audio file (wav/mp3/flac/ogg)")
    splt.add_argument("--model", default="htdemucs_6s", dest="model",
                      choices=["htdemucs_6s", "htdemucs", "mdx_extra", "htdemucs_ft"],
                      help="Stem-split model (default: htdemucs_6s = 6 stems).")
    splt.add_argument("--output-dir", type=Path, default=None, dest="output_dir",
                      help="Where to write the stems (default: <audio>/stems/).")
    splt.add_argument("--source", choices=["auto", "mixed", "vocal", "instrumental"],
                      default="auto", dest="source",
                      help="Which output file to split when --source=auto picks the first one. "
                           "Used for batch post-processing only.")

    args = parser.parse_args()

    if args.cmd == "presets":
        banner(); list_presets(); return
    if args.cmd == "tags":
        banner(); show_genre_tags(); return
    if args.cmd == "ui":
        banner(); launch_ui(); return
    if args.cmd == "split":
        banner()
        ok = run_stem_split(
            output_dir=args.audio.parent,
            model=args.model,
            stems_output_dir=args.output_dir,
        )
        # If user passed a directory instead of a file, fall back to
        # the run_stem_split() helper which searches for mixed_output.
        if not ok and args.audio.is_dir():
            ok = run_stem_split(
                output_dir=args.audio,
                model=args.model,
                stems_output_dir=args.output_dir,
            )
        else:
            # Direct file path
            try:
                from stem_splitter import split_stems
            except ImportError:
                console.print(
                    "[bold red]✗ audio-separator is not installed.[/bold red]\n"
                    "  Run:  pip install audio-separator"
                )
                sys.exit(2)
            out_dir = args.output_dir or (args.audio.parent / "stems")
            try:
                stems = split_stems(args.audio, output_dir=out_dir, model=args.model)
            except Exception as e:
                console.print(f"[bold red]✗ Stem split failed:[/bold red] {e}")
                sys.exit(1)
            console.print(f"\n[bold green]✓ {len(stems)} stems written to {out_dir}:[/bold green]")
            for s in stems:
                size_mb = s.stat().st_size / 1_048_576 if s.exists() else 0
                console.print(f"  [cyan]→[/cyan] {s}  [dim]({size_mb:.1f} MB)[/dim]")
        return
    if args.cmd is None or args.cmd == "interactive":
        interactive_mode(); return

    # ── generate ──
    banner()
    if args.preset:
        p = PRESETS[args.preset]
        console.print(f"[bold yellow]{p['name']}[/bold yellow] — {p['description']}")
        genre_path, lyrics_path = write_prompt_files(p["genre_tags"], p["lyric_template"])
        label = args.preset
    elif args.genre and args.lyrics:
        genre_path, lyrics_path = args.genre, args.lyrics
        label = "custom"
    else:
        console.print("[red]✗ Provide --preset OR both --genre and --lyrics[/red]")
        sys.exit(1)

    # Inject instrumental / no-drums tags
    if getattr(args, "instrumental_only", False) or getattr(args, "no_drums", False):
        tags = Path(genre_path).read_text().strip().split()
        if getattr(args, "instrumental_only", False):
            for t in ["instrumental", "no-vocal"]:
                if t not in tags:
                    tags.append(t)
        if getattr(args, "no_drums", False) and "no-drums" not in tags:
            tags.append("no-drums")
        genre_path, _ = write_prompt_files(" ".join(tags), Path(lyrics_path).read_text())

    # ── Loop Mode processing ─────────────────────────────────────────────
    # --loop-bars and --loop-segments both imply --loop
    loop_enabled = (
        getattr(args, "loop", False)
        or getattr(args, "loop_bars", None) is not None
        or getattr(args, "loop_segments", None) is not None
    )

    # Read the *current* genre file (already has instrumental/no-drums tags
    # merged if those flags were set above).
    current_genre_tags = Path(genre_path).read_text().strip()
    loop_cfg = get_loop_config(current_genre_tags, segments=args.segments) if loop_enabled else None

    if loop_enabled:
        # 0) HARD 30s / 1-SEGMENT CAP (8GB VRAM)
        #    Any segment value >1 is rejected. We still honour --loop-bars
        #    and pack the bars into the single allowed segment.
        if getattr(args, "loop_segments", None) is not None and args.loop_segments > MAX_SEGMENTS:
            console.print(
                f"[bold red]⚠ 8GB VRAM cap: --loop-segments {args.loop_segments} → {MAX_SEGMENTS} "
                f"(max {MAX_DURATION_SECONDS}s)[/bold red]"
            )
            args.loop_segments = MAX_SEGMENTS
        if args.segments > MAX_SEGMENTS:
            console.print(
                f"[bold red]⚠ 8GB VRAM cap: --segments {args.segments} → {MAX_SEGMENTS} "
                f"(max {MAX_DURATION_SECONDS}s).  For longer songs use "
                f"[bold]YuEGP[/bold] (quantized, runs on 6GB+).[/bold red]"
            )
            args.segments = MAX_SEGMENTS

        # Override bar count (--loop-bars wins over auto-detect)
        if getattr(args, "loop_bars", None) is not None:
            # Cap loop-bars so the *single* segment doesn't exceed 30s.
            # 30s / 2.4s-per-bar = ~12 bars max for one segment.
            max_bars_per_segment = int(MAX_DURATION_SECONDS / 2.4)
            if args.loop_bars > max_bars_per_segment:
                console.print(
                    f"[yellow]⚠ Loop Mode: --loop-bars {args.loop_bars} → {max_bars_per_segment} "
                    f"to fit in one {MAX_DURATION_SECONDS}s segment[/yellow]"
                )
                args.loop_bars = max_bars_per_segment

            loop_cfg["bars_per_section"] = args.loop_bars
            loop_cfg["loop_tags"] = (
                "loop seamless-loop" if args.loop_bars <= 8 else "loop extended"
            )
            # Recompute totals (always single segment on 8GB)
            sec = args.loop_bars * 2.4
            loop_cfg["segment_seconds"]  = round(sec, 1)
            loop_cfg["bars_total"]       = args.loop_bars * MAX_SEGMENTS
            loop_cfg["total_seconds"]    = round(args.loop_bars * 2.4 * MAX_SEGMENTS, 1)
        # Override segment count if explicitly given (already capped above)
        if getattr(args, "loop_segments", None) is not None:
            segs = args.loop_segments
            loop_cfg["bars_total"]    = loop_cfg["bars_per_section"] * max(1, segs)
            loop_cfg["total_seconds"] = round(
                loop_cfg["bars_per_section"] * 2.4 * max(1, segs), 1
            )
            args.segments = segs

        # 1) Override --max-tokens so the model has enough budget for the
        #    longer phrasing. ~750 tokens per bar + 500 headroom is plenty
        #    for YuE's text-tokenizer output.
        original_tokens = args.max_tokens
        args.max_tokens = max(args.max_tokens, loop_cfg["bars_per_section"] * 750 + 500)
        if args.max_tokens != original_tokens:
            console.print(
                f"[dim]Loop Mode: raised --max-tokens {original_tokens} → {args.max_tokens} "
                f"({loop_cfg['bars_per_section']} bars × 750 + 500)[/dim]"
            )

        # 2) Append loop tags to the genre file
        tags = current_genre_tags.split()
        added = []
        for lt in loop_cfg["loop_tags"].split():
            if lt not in tags:
                tags.append(lt)
                added.append(lt)
        if added:
            console.print(
                f"[dim]Loop Mode: appended tags {added}  "
                f"(detected: {loop_cfg['detected_genre']}, "
                f"{loop_cfg['bars_per_section']} bars/section)[/dim]"
            )
            genre_path, _ = write_prompt_files(
                " ".join(tags), Path(lyrics_path).read_text()
            )

        # 3) If --segments wasn't overridden by user, would normally raise
        #    it to cover bars_total — but on 8GB we are hard-capped at 1.
        if getattr(args, "loop_segments", None) is None and args.segments < MAX_SEGMENTS:
            ideal = loop_cfg["bars_per_section"] // 12 + 1
            if ideal > MAX_SEGMENTS:
                console.print(
                    f"[dim]Loop Mode: {loop_cfg['bars_per_section']} bars would "
                    f"ideally need {ideal} segments — capped to {MAX_SEGMENTS} "
                    f"for 8GB VRAM (≤{MAX_DURATION_SECONDS}s total)[/dim]"
                )
            args.segments = MAX_SEGMENTS

        console.print(
            f"[bold yellow]Loop Mode[/bold yellow]  "
            f"genre=[cyan]{loop_cfg['detected_genre']}[/cyan]  "
            f"bars/section=[cyan]{loop_cfg['bars_per_section']}[/cyan]  "
            f"segments=[cyan]{args.segments}[/cyan]  "
            f"total bars=[cyan]{loop_cfg['bars_total']}[/cyan]  "
            f"~[cyan]{loop_cfg['total_seconds']:.1f}s[/cyan]  "
            f"[dim](capped to {MAX_DURATION_SECONDS}s for 8GB VRAM)[/dim]"
        )

        # --print-loop-config: print the JSON config and exit cleanly
        if getattr(args, "print_loop_config", False):
            console.print_json(data=loop_cfg)
            return

    use_dual = bool(args.vocal and args.instrumental)
    stage1_key   = f"icl_{args.lang}" if args.icl else f"cot_{args.lang}"
    stage1_model = MODELS.get(stage1_key, MODELS["cot_en"])

    ts = time.strftime("%Y%m%d_%H%M%S")
    output_dir = args.output or (OUTPUT_DIR / f"{label}_{ts}")
    if loop_enabled:
        output_dir = output_dir.with_name(f"{output_dir.name}_loop{loop_cfg['bars_per_section']}b")

    cmd = build_infer_command(
        genre_path=genre_path,
        lyrics_path=lyrics_path,
        output_dir=output_dir,
        cuda_idx=args.cuda,
        stage1_model=stage1_model,
        run_n_segments=args.segments,
        stage2_batch_size=args.batch_size,
        max_new_tokens=args.max_tokens,
        repetition_penalty=args.rep_penalty,
        seed=args.seed,
        use_audio_prompt=args.icl and bool(args.audio),
        audio_prompt_path=args.audio,
        use_dual_tracks=use_dual,
        vocal_track=args.vocal,
        instrumental_track=args.instrumental,
        prompt_start=args.prompt_start,
        prompt_end=args.prompt_end,
        rescale=True,
    )
    gen_ok = run_generation(cmd, output_dir, verbose=getattr(args, "verbose", False))
    if gen_ok and getattr(args, "stem_split", False):
        run_stem_split(
            output_dir=output_dir,
            model=getattr(args, "stem_model", "htdemucs_6s"),
            stems_output_dir=getattr(args, "stems_output_dir", None),
        )


if __name__ == "__main__":
    main()
