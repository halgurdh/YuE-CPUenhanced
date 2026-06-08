"""
CP Studio — Gradio Web UI
ChilledPunks aesthetic · RTX 3060 8GB optimized
Run: python yue_ui.py  →  http://localhost:7860
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import gradio as gr

# ─── Import from yue_studio ──────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from yue_studio import (
    PRESETS, MODELS, GENRE_TAGS, OUTPUT_DIR, INFERENCE_DIR,
    write_prompt_files, build_infer_command, RTX_3060_PROFILE,
    get_loop_config, MAX_SEGMENTS, MAX_DURATION_SECONDS,
    resolve_yue_python, python_has_torch, yue_subprocess_env, HF_HOME,
)

# ─── UI Constants ────────────────────────────────────────────────────────────

# Gradio 6.x theme — warm dark palette matching ChilledPunks aesthetic
THEME = gr.themes.Default(
    primary_hue="amber",
    secondary_hue="amber",
    neutral_hue="neutral",
).set(
    color_accent="hsl(35, 100%, 50%)",
    body_text_color="hsl(42, 50%, 85%)",
    body_text_color_subdued="hsl(42, 20%, 65%)",
    slider_color="hsl(35, 80%, 55%)",
    block_title_text_color="hsl(35, 100%, 55%)",
    block_label_text_color="hsl(42, 50%, 85%)",
    block_label_background_fill="hsl(35, 30%, 20%)",
    input_background_fill="hsl(35, 20%, 15%)",
    checkbox_label_background_fill="hsl(35, 20%, 15%)",
    checkbox_label_background_fill_selected="hsl(35, 80%, 55%)",
    checkbox_label_text_color="hsl(42, 50%, 85%)",
    checkbox_label_text_color_selected="hsl(42, 50%, 85%)",
    error_background_fill="hsl(0, 60%, 15%)",
    error_text_color="hsl(0, 80%, 80%)",
    body_background_fill="hsl(35, 20%, 12%)",
    background_fill_primary="hsl(35, 20%, 18%)",
    border_color_primary="hsl(35, 30%, 30%)",
)

# Preset choices for dropdown
PRESET_CHOICES = [("Custom", "custom")] + list(
    (k, f"{v['name']}") for k, v in PRESETS.items()
)

# Language choices
LANG_CHOICES = [
    ("English", "en"),
    ("Chinese", "zh"),
    ("Japanese/Korean", "jp-kr"),
]

# Stem splitting model choices (labels match stem_splitter.MODELS)
STEM_CHOICES = [
    ("HTDemucs 6S — 6 stems (default)", "htdemucs_6s"),
    ("HTDemucs — 4 stems", "htdemucs"),
    ("MDX Extra — 12 stems (slower)", "mdx_extra"),
    ("HTDemucs FT — 4 stems fine-tuned", "htdemucs_ft"),
]
STEM_DEFAULT_MODEL = "htdemucs_6s"

# Stage1 model size choices (1B vs 7B)
STAGE1_SIZE_CHOICES = [
    ("1B (default — faster, lower VRAM)", "1b"),
    ("7B", "7b"),
]

# Which YuE output track to feed into stem separation
STEM_SOURCE_CHOICES = [
    ("Auto (mixed → vocal → instrumental)", "auto"),
    ("Mixed output", "mixed"),
    ("Vocal output", "vocal"),
    ("Instrumental output", "instrumental"),
]

# Song structure choices for stitching
STRUCTURE_CHOICES = [
    ("Pop (intro→verse→chorus→verse→chorus→outro)", "pop"),
    ("Short (intro→verse→chorus→outro)", "short"),
    ("Extended (intro→verse→chorus→verse→chorus→bridge→chorus→outro)", "extended"),
    ("Custom (use lyrics section markers)", "custom"),
]

# ─── Helpers ───────────────────────────────────────────────────────────────

def apply_preset(preset_key):
    if not preset_key or preset_key not in PRESETS:
        return "", ""
    p = PRESETS[preset_key]
    return p["genre_tags"], p["lyric_template"]


def get_tags_for_category(category):
    tags = GENRE_TAGS.get(category, [])
    return ", ".join(tags)


def append_tag(current_tags, tag):
    """Add a tag to the genre_tags box if not already there."""
    tag = tag.strip()
    if not tag:
        return current_tags
    existing = [t.strip() for t in current_tags.split()]
    if tag not in existing:
        return (current_tags.strip() + " " + tag).strip()
    return current_tags


def build_genre_tag_string(
    genre, mood, vocals, instruments, timbre, language, custom,
    instrumental_only=False, no_drums=False,
):
    """Combine all tag selectors into a single tag string."""
    parts = []
    for v in [genre, mood, vocals, instruments, timbre, language]:
        if isinstance(v, list):
            parts.extend(v)
        elif v:
            parts.append(v)
    if custom.strip():
        parts.extend(custom.strip().split())
    if instrumental_only:
        parts += ["instrumental", "no-vocal"]
    if no_drums:
        parts.append("no-drums")
    # deduplicate preserving order
    seen = set()
    result = []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            result.append(p)
    return " ".join(result)


_TQDM_PCT = re.compile(r"\b(\d{1,3})%\|\\")


# ─── Post-processing helpers ───────────────────────────────────────────────

def _infer_env() -> dict:
    return yue_subprocess_env()


def _pick_audio_for_stems(output_dir: Path, source: str = "auto") -> Path | None:
    """Pick mixed / vocal / instrumental output for stem separation."""
    if source == "auto":
        stitched = output_dir / "stitched.wav"
        if stitched.exists():
            return stitched

    by_source = {
        "mixed": ["mixed_output.wav", "mixed*.wav"],
        "vocal": ["vocal_output.wav", "*vocal*.wav"],
        "instrumental": ["instrumental_output.wav", "*instrumental*.wav"],
    }
    if source in by_source:
        for pattern in by_source[source]:
            hits = sorted(output_dir.rglob(pattern))
            if hits:
                return hits[0]
    for pattern in ("mixed_output.wav", "mixed*.wav", "vocal_output.wav",
                    "instrumental_output.wav", "*.wav"):
        hits = sorted(output_dir.rglob(pattern))
        if hits:
            return hits[0]
    return None


def _best_stem_preview(stems: list[Path]) -> str | None:
    """Prefer vocals stem for the preview player."""
    for s in stems:
        if s.exists() and "vocal" in s.name.lower():
            return str(s)
    for s in stems:
        if s.exists():
            return str(s)
    return None


def run_stem_split_ui(
    output_dir: Path,
    model: str,
    log: str,
    source: str = "auto",
) -> tuple[str, str | None]:
    """Run stem separation. Returns (updated_log, stem_audio_path)."""
    try:
        from stem_splitter import split_stems
    except ImportError:
        log += "\n[yellow]⚠ audio-separator not installed. Skip stem split.[/yellow]\n"
        return log, None

    audio = _pick_audio_for_stems(output_dir, source)
    if audio is None:
        log += "\n[yellow]⚠ No audio file found for stem split.[/yellow]\n"
        return log, None

    out_dir = output_dir / "stems"
    log += (
        f"\n[green]▶ Splitting stems[/green]  "
        f"source={audio.name}  model={model}  → {out_dir}\n"
    )

    try:
        stems = split_stems(audio, output_dir=out_dir, model=model)
    except Exception as e:
        log += f"\n[red]✗ Stem split failed: {e}[/red]\n"
        return log, None

    if not stems:
        log += "\n[yellow]⚠ Stem split returned no files.[/yellow]\n"
        return log, None

    log += f"[green]✓ {len(stems)} stems written:[/green]\n"
    for s in stems:
        size_mb = s.stat().st_size / 1_048_576 if s.exists() else 0
        log += f"  → {s.name} ({size_mb:.1f} MB)\n"
    return log, _best_stem_preview(stems)


def preview_stitch_plan(
    lyrics: str,
    structure: str,
    include_intro: bool,
    include_outro: bool,
) -> str:
    """Live summary of the section-stitch plan for the UI."""
    try:
        from song_stitcher import (
            SongPlan, build_plan_from_lyrics, describe_plan,
            plan_total_bars, plan_total_calls, split_lyrics_into_sections,
        )
    except ImportError:
        return "_song_stitcher not available — install pydub + ffmpeg._"

    text = (lyrics or "").strip()
    if not text:
        return "_Add lyrics with `[verse]` / `[chorus]` markers to preview the stitch plan._"

    if structure == "custom":
        sections = split_lyrics_into_sections(text)
        if not sections:
            return "_No `[verse]` / `[chorus]` / … markers found in lyrics._"
        plan = SongPlan(name="custom", sections=sections)
    else:
        plan = build_plan_from_lyrics(
            text, preset=structure,
            add_intro=include_intro, add_outro=include_outro,
        )

    calls = plan_total_calls(plan)
    est_min = calls * 30 // 60
    est_sec = calls * 30 % 60
    return (
        f"**{describe_plan(plan)}**  \n"
        f"{plan_total_bars(plan)} bars · **{calls}** inference call(s) "
        f"(~{calls * 30}s GPU · ~{est_min}m {est_sec}s)"
    )


def _build_stitch_plan(lyrics: str, structure: str, include_intro: bool, include_outro: bool):
    from song_stitcher import (
        SongPlan, build_plan_from_lyrics, split_lyrics_into_sections,
    )
    if structure == "custom":
        sections = split_lyrics_into_sections(lyrics)
        if not sections:
            return None
        return SongPlan(name="custom", sections=sections)
    return build_plan_from_lyrics(
        lyrics, preset=structure,
        add_intro=include_intro, add_outro=include_outro,
    )


def _apply_loop_mode(
    genre_tags: str,
    loop_enabled: bool,
    loop_bars_in: int,
    segments: int,
    max_tokens: int,
) -> tuple[str, int, int, str]:
    """Mirror CLI loop-mode tag + token adjustments."""
    if not loop_enabled:
        return genre_tags, segments, max_tokens, ""

    loop_cfg = get_loop_config(genre_tags, segments=segments)
    notes: list[str] = []
    segments = min(int(segments), MAX_SEGMENTS)

    loop_bars = int(loop_bars_in) if int(loop_bars_in or 0) > 0 else None
    if loop_bars is not None:
        max_bars = int(MAX_DURATION_SECONDS / 2.4)
        if loop_bars > max_bars:
            notes.append(f"⚠ Loop bars clamped {loop_bars} → {max_bars} (30s cap)")
            loop_bars = max_bars
        loop_cfg["bars_per_section"] = loop_bars
        loop_cfg["loop_tags"] = (
            "loop seamless-loop" if loop_bars <= 8 else "loop extended"
        )

    raised = max(int(max_tokens), loop_cfg["bars_per_section"] * 750 + 500)
    if raised != int(max_tokens):
        notes.append(f"Loop Mode: max tokens {max_tokens} → {raised}")
        max_tokens = raised

    tags = genre_tags.split()
    added = [lt for lt in loop_cfg["loop_tags"].split() if lt not in tags]
    if added:
        tags.extend(added)
        genre_tags = " ".join(tags)

    notes.append(
        f"Loop Mode: {loop_cfg['detected_genre']} · "
        f"{loop_cfg['bars_per_section']} bars/section · ~{loop_cfg['segment_seconds']}s"
    )
    return genre_tags, segments, max_tokens, "\n".join(notes) + ("\n" if notes else "")


def _stream_infer(
    cmd: list[str],
    log: str,
    progress: gr.Progress,
    progress_base: float,
    progress_span: float,
    desc: str,
):
    """Run infer.py and yield (log, None, None) updates."""
    proc = subprocess.Popen(
        cmd,
        cwd=str(INFERENCE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=_infer_env(),
    )
    stage = 1
    for line in iter(proc.stdout.readline, ""):
        log += line
        ll = line.lower()
        m = _TQDM_PCT.search(line)
        if m:
            pct = int(m.group(1)) / 100
            if stage == 1:
                progress(progress_base + pct * progress_span * 0.6,
                         desc=f"{desc} — Stage 1 {m.group(1)}%")
            else:
                progress(progress_base + progress_span * 0.6 + pct * progress_span * 0.35,
                         desc=f"{desc} — Stage 2 {m.group(1)}%")
        elif "stage2" in ll or "stage 2" in ll:
            stage = 2
            progress(progress_base + progress_span * 0.6, desc=f"{desc} — Stage 2…")
        yield log, None, None
    proc.wait()
    yield log, proc.returncode, None


# ─── Main generation stream ────────────────────────────────────────────────

def run_generation_stream(
    preset_key,
    genre_tags,
    lyrics,

    # model
    lang,
    # quick options
    instrumental_only,
    no_drums,
    # ICL
    icl_mode,
    audio_file,
    vocal_file,
    instrumental_file,
    prompt_start,
    prompt_end,
    # generation
    segments,
    batch_size,
    max_tokens,
    rep_penalty,
    seed_str,
    cuda_idx,
    # loop mode
    loop_enabled,
    loop_bars_in,
    # post-processing
    stem_split,
    stem_model,
    stem_source,
    stitch_sections_flag,
    stitch_only_no_regen,
    structure,
    crossfade_ms,
    include_intro,
    include_outro,
    progress=gr.Progress(),
):
    g = genre_tags.strip()
    l = lyrics.strip()
    if not g and preset_key in PRESETS:
        g = PRESETS[preset_key]["genre_tags"]
    if not l and preset_key in PRESETS:
        l = PRESETS[preset_key]["lyric_template"]
    if not g:
        yield "✗ Genre tags required.", None, None
        return
    if not l:
        yield "✗ Lyrics required.", None, None
        return

    # Inject quick-option tags
    existing = g.split()
    if instrumental_only:
        for t in ["instrumental", "no-vocal"]:
            if t not in existing:
                existing.append(t)
    if no_drums and "no-drums" not in existing:
        existing.append("no-drums")
    g = " ".join(existing)

    g, segments, max_tokens, loop_note = _apply_loop_mode(
        g, loop_enabled, loop_bars_in, int(segments), int(max_tokens),
    )

    use_dual = (icl_mode == "dual" and vocal_file and instrumental_file)
    use_single = (icl_mode == "single" and audio_file)
    stage1_key = f"icl_{lang}" if (use_dual or use_single) else f"cot_{lang}"
    stage1_model = MODELS.get(stage1_key, MODELS["cot_en"])
    seed = int(seed_str) if str(seed_str).strip().isdigit() else None

    ts = time.strftime("%Y%m%d_%H%M%S")
    label = preset_key if preset_key in PRESETS else "custom"
    suffix = ""
    if loop_enabled:
        loop_cfg = get_loop_config(g, segments=int(segments))
        bars = int(loop_bars_in) if int(loop_bars_in or 0) > 0 else loop_cfg["bars_per_section"]
        suffix = f"_loop{bars}b"
    stitch_suffix = "_stitched" if stitch_sections_flag else ""
    output_dir = OUTPUT_DIR / f"{label}_{ts}{suffix}{stitch_suffix}"
    output_dir.mkdir(parents=True, exist_ok=True)

    infer_py = resolve_yue_python()
    if not python_has_torch(Path(infer_py)):
        yield (
            "✗ PyTorch not found for YuE inference.\n"
            f"  UI Python: {sys.executable}\n"
            f"  Tried:     {infer_py}\n"
            "  Activate the yue conda env, or set YUE_PYTHON to its python.exe\n"
            "  (e.g. %USERPROFILE%\\miniconda3\\envs\\yue\\python.exe).\n",
            None,
            None,
        )
        return

    log = (
        f"▶ Output: {output_dir}\n"
        f"▶ Inference Python: {infer_py}\n"
        f"▶ HF cache: {HF_HOME}\n"
    )
    if infer_py != sys.executable:
        log += f"  (UI launched with {sys.executable})\n"
    if loop_note:
        log += loop_note
    log += "─" * 60 + "\n"
    progress(0, desc="Starting…")
    yield log, None, None

    try:
        audio_out: str | None = None
        stems_audio: str | None = None

        # Stitch-only (no regeneration) uses existing per-section WAVs.
        # When stitch-only is enabled, we still run the single-track generation
        # (matching current UI behavior). If you want pure stitch-only without
        # regeneration, adjust this branch.

        # ── Single-track generation ───────────────────────────────
        genre_path, lyrics_path = write_prompt_files(g, l)
        cmd = build_infer_command(
            genre_path=genre_path,
            lyrics_path=lyrics_path,
            output_dir=output_dir,
            cuda_idx=int(cuda_idx),
            stage1_model=stage1_model,
            run_n_segments=int(segments),
            stage2_batch_size=int(batch_size),
            max_new_tokens=int(max_tokens),
            repetition_penalty=float(rep_penalty),
            seed=seed,
            use_audio_prompt=use_single,
            audio_prompt_path=Path(audio_file) if audio_file else None,
            use_dual_tracks=use_dual,
            vocal_track=Path(vocal_file) if vocal_file else None,
            instrumental_track=Path(instrumental_file) if instrumental_file else None,
            prompt_start=int(prompt_start),
            prompt_end=int(prompt_end),
            rescale=True,
        )
        log += f"▶ {' '.join(cmd)}\n" + "─" * 60 + "\n"
        yield log, None, None

        rc = 1
        for update in _stream_infer(cmd, log, progress, 0.05, 0.85, "Generating"):
            log = update[0]
            if update[1] is not None and isinstance(update[1], int):
                rc = update[1]
            else:
                yield log, None, None

        log += "\n" + "─" * 60 + "\n"
        if rc != 0:
            progress(1.0, desc="✗ Failed")
            yield log + f"✗ Generation failed (exit {rc})\n", None, None
            return

        audio_files = sorted(
            list(output_dir.rglob("*.wav")) + list(output_dir.rglob("*.mp3"))
        )
        log += f"✓ Generation done! {len(audio_files)} file(s)\n"
        for af in audio_files:
            log += f"  → {af.name}\n"
        audio_out = str(audio_files[-1]) if audio_files else None

        # ── Post-processing: Stem Split ───────────────────────────────
        if stem_split and audio_out:
            progress(0.95, desc="Splitting stems…")
            log += "\n" + "─" * 60 + "\n"
            log, stems_audio = run_stem_split_ui(
                output_dir, stem_model, log, source=stem_source,
            )

        # ── Post-processing: Stitch only (no regeneration) ──────────
        if stitch_only_no_regen:
            stitched = output_dir / "stitched.wav"
            if stitched.exists():
                log += f"\n[green]✓ Reusing cached stitch: {stitched.name}[/green]\n"
                audio_out = str(stitched)
            else:
                from song_stitcher import stitch_sections
                section_wavs = sorted(list(output_dir.rglob("*.wav")))

                # Filter out stems previews and already-stitched output.
                section_wavs = [
                    w for w in section_wavs
                    if w.name.lower() != "stitched.wav" and "/stems/" not in str(w).lower()
                ]

                if not section_wavs:
                    log += "\n[red]✗ Stitch-only failed: no per-section WAVs found under output dir.[/red]\n"
                    progress(1.0, desc="✗ Stitch-only failed")
                    yield log, audio_out, stems_audio
                    return

                log += "\n[green]▶ Stitch-only[/green] using existing section WAVs…\n"
                progress(0.97, desc="Stitching existing sections…")

                # Best-effort order: by call folder name then filename.
                section_wavs.sort(key=lambda p: (str(p.parent), p.name))

                stitch_sections(
                    [Path(w) for w in section_wavs],
                    stitched,
                    crossfade_ms=int(crossfade_ms),
                    silence_ms=0,
                )
                log += f"\n[green]✓ Stitch-only created {stitched.name}[/green]\n"
                audio_out = str(stitched)

        progress(1.0, desc="✓ Done!")
        yield log, audio_out, stems_audio

    except FileNotFoundError:
        progress(1.0, desc="✗ Error")
        yield log + f"✗ infer.py not found: {INFERENCE_DIR}\n  Set YUE_DIR env var.\n", None, None
    except Exception as e:
        progress(1.0, desc="✗ Error")
        yield log + f"✗ Error: {e}\n", None, None


# ─── Build UI ──────────────────────────────────────────────────────────────

CUSTOM_CSS = """
/* CSS variable overrides — Gradio 6.x reads these for input text */
:root {
    --input-text-color: #ede8d9;
    --body-text-color:  #ede8d9;
}

/* Plain inputs and textareas */
.gradio-container input:not([type=range]):not([type=checkbox]),
.gradio-container textarea {
    color: #ede8d9 !important;
}

/* Dropdown option list — light background, black text */
.gradio-container [role=option],
.gradio-container [role=listbox] li,
.gradio-container ul.options li {
    color: #111 !important;
    background-color: #f5f5f5 !important;
}

/* Selected / highlighted option */
.gradio-container [aria-selected=true],
.gradio-container [role=option]:hover {
    background-color: #f5a623 !important;
    color: #000 !important;
}

/* Multiselect tokens (chosen tags) */
.gradio-container .token,
.gradio-container .token span,
.gradio-container .wrap span {
    color: #ede8d9 !important;
}
"""


def build_ui():
    with gr.Blocks(title="CP Studio · ChilledPunks") as demo:

        gr.Markdown("""
# 🎵 CP Studio — ChilledPunks Edition
**Local full-song generation · RTX 3060 Ti 8GB optimized · [YuE](https://github.com/multimodal-art-projection/YuE)**
""")

        with gr.Row():
            with gr.Column(scale=3):
                with gr.Group():
                    gr.Markdown("### 🎛 Preset")
                    preset_dd = gr.Dropdown(
                        choices=PRESET_CHOICES,
                        value=PRESET_CHOICES[0][1],
                        label="ChilledPunks Genre Preset (or type custom)",
                        allow_custom_value=True,
                    )
                    load_btn = gr.Button("⬇ Load Preset", variant="secondary", size="sm")

                with gr.Accordion("🏷 Genre Tag Builder", open=True):
                    gr.Markdown("_Select tags from each category or type custom ones. Tags are combined into the genre box below._")
                    with gr.Row():
                        genre_sel = gr.Dropdown(GENRE_TAGS["Genre"], label="Genre", multiselect=True)
                        mood_sel = gr.Dropdown(GENRE_TAGS["Mood"], label="Mood", multiselect=True)
                    with gr.Row():
                        vocal_sel = gr.Dropdown(GENRE_TAGS["Vocals"], label="Vocals", multiselect=True)
                        instr_sel = gr.Dropdown(GENRE_TAGS["Instruments"], label="Instruments", multiselect=True)
                    with gr.Row():
                        timbre_sel = gr.Dropdown(GENRE_TAGS["Timbre / Production"], label="Timbre / Production", multiselect=True)
                        lang_tag = gr.Dropdown(GENRE_TAGS["Language"], label="Language tag", multiselect=False, value=None)
                    custom_tags = gr.Textbox(label="Extra custom tags (space-separated)", lines=1, value="")
                    with gr.Row():
                        instrumental_cb = gr.Checkbox(label="Instrumental only (no vocals)", value=False)
                        no_drums_cb = gr.Checkbox(label="No drums", value=False)
                    build_tags_btn = gr.Button("🔧 Build Genre Tags ↓", variant="secondary", size="sm")

                genre_box = gr.Textbox(
                    label="Genre Tags (edit freely)", lines=2,
                    value=PRESETS["lofi_hiphop"]["genre_tags"],
                )
                lyrics_box = gr.Textbox(
                    label="Lyrics", lines=12,
                    value=PRESETS["lofi_hiphop"]["lyric_template"],
                    placeholder="[verse]\n...\n\n[chorus]\n...",
                )

                with gr.Accordion("🎤 Style Reference (ICL) — optional", open=False):
                    gr.Markdown("Provide a 30s reference audio to guide the style. Dual-track gives best results.")
                    icl_mode = gr.Radio(
                        choices=[
                            ("None", "none"),
                            ("Single track", "single"),
                            ("Dual track (vocal + instrumental)", "dual"),
                        ],
                        value="none",
                        label="ICL mode",
                    )
                    with gr.Group(visible=False) as single_grp:
                        audio_ref = gr.Audio(label="Reference audio (30s)", type="filepath")
                    with gr.Group(visible=False) as dual_grp:
                        vocal_ref = gr.Audio(label="Vocal track (30s)", type="filepath")
                        inst_ref = gr.Audio(label="Instrumental track (30s)", type="filepath")
                    with gr.Row():
                        p_start = gr.Number(label="Start (s)", value=0, precision=0)
                        p_end = gr.Number(label="End (s)", value=30, precision=0)

with gr.Column(scale=2):
                with gr.Group():
                    gr.Markdown("### 🌐 Language Model")
                    lang_model = gr.Radio(
                        choices=LANG_CHOICES, value="en",
                        label="Lyrics language (ignored for instrumental only)",
                    )

                with gr.Accordion("⚙ Generation Settings (RTX 3060 8GB defaults)", open=True):
                    gr.Markdown("⚡ Default for 8GB VRAM: **Fast + stable**. Use YuE full-precision (GPU) with 1 segment (~30s) to avoid retries/OOM. For longer audio, switch to YuEGP (launch_yuegp.py) instead.")
# Model size selector (1B vs 7B)
                    stage1_size = gr.Radio(
                        choices=STAGE1_SIZE_CHOICES,
                        value="1b",
                        label="Stage1 Model Size",
                    )
                    # Fast/stable defaults
                    seg_sl = gr.Slider(1, 4, value=RTX_3060_PROFILE["run_n_segments"], step=1, label="Segments (1≈30s, 2≈1min) — keep 1 on 8GB")
                    batch_sl = gr.Slider(1, 4, value=RTX_3060_PROFILE["stage2_batch_size"], step=1, label="Batch size (keep ≤2 on 8GB)")
                    tok_sl = gr.Slider(1000, 6000, value=RTX_3060_PROFILE["max_new_tokens"], step=500, label="Max tokens")
                    # Slightly higher repetition penalty reduces loops/repeats and often stabilizes decoding
                    rep_sl = gr.Slider(1.0, 1.6, value=1.12, step=0.02, label="Repetition penalty")
                    seed_box = gr.Textbox(label="Seed (blank = random)", value="", max_lines=1)
                    # Prefer cuda:0 by default; UI previously used 1 which can be wrong on single-GPU setups
                    cuda_sl = gr.Slider(0, 7, value=0, step=1, label="CUDA device", interactive=True)



                with gr.Accordion("🔁 Loop Mode — pre-generation", open=False):
                    gr.Markdown("_Auto-detect bar count from genre and raise token budget. Clamped to 8GB VRAM max (1 segment ≈ 30s ≈ 12 bars)._")
                    with gr.Row():
                        loop_cb = gr.Checkbox(label="Enable Loop Mode", value=False)

                        loop_bars_in = gr.Number(label="Bars/section (0 = auto-detect)", value=0, precision=0)

                with gr.Accordion("🛠 Post-Processing", open=True):
                    gr.Markdown(
                        "_**Stem split** runs on the final mix after generation. "
                        "**Section stitch** can either generate sections (then stitch) "
                        "or stitch-only (never regenerate). _"
                    )
                    with gr.Group():
                        gr.Markdown("**🎚 Stem Split** — `pip install audio-separator`")
                        with gr.Row():
                            stem_cb = gr.Checkbox(label="Split into stems (vocals / drums / bass / …)", value=True)

                            stem_dd = gr.Dropdown(choices=STEM_CHOICES, value=STEM_DEFAULT_MODEL, label="Separation model", interactive=False)
                        stem_src_dd = gr.Dropdown(choices=STEM_SOURCE_CHOICES, value="auto", label="Source track", interactive=False)
                    with gr.Group():
                            gr.Markdown("**🔗 Section Stitch** — `pydub` + ffmpeg on PATH")
                            stitch_cb = gr.Checkbox(
                                label="Generate per-section + stitch into full song (chunks)",
                                value=False,
                                interactive=True,
                            )
                            stitch_only_no_regen_cb = gr.Checkbox(
                                label="Stitch only (no regeneration) — use existing per-section WAVs",
                                value=True,
                                interactive=True,
                            )

                            stitch_plan_md = gr.Markdown("_Plan preview updates from lyrics + structure._")
                            with gr.Row():
                                struct_dd = gr.Dropdown(choices=STRUCTURE_CHOICES, value="pop", label="Song structure", interactive=True)
                                crossfade_sl = gr.Slider(0, 5000, value=1500, step=100, label="Crossfade (ms)", interactive=True)
                            with gr.Row():
                                intro_cb = gr.Checkbox(label="Include intro", value=True, interactive=True)
                                outro_cb = gr.Checkbox(label="Include outro", value=True, interactive=True)

                gr.Markdown("### 🚀 Generate")
                with gr.Row():
                    gen_btn = gr.Button("Generate Track ▶", variant="primary")
                    stop_btn = gr.Button("■ Stop", variant="stop")

# Visible progress bar for generation step
                progress_bar = gr.Slider(
                    label="Generation Progress",
                    minimum=0,
                    maximum=1,
                    value=0,
                    step=0.01,
                    interactive=False,
                )

                gr.Markdown("### 🎧 Output")
                with gr.Row():
                    audio_out = gr.Audio(label="Generated track", type="filepath", interactive=False)
                    stems_audio = gr.Audio(label="Stems preview (vocals or first stem)", type="filepath", interactive=False)
                log_out = gr.Textbox(label="Log", lines=20, max_lines=50, interactive=False)

        gr.Markdown(
            """ 
---
**RTX 3060 8GB tips**
- 1 segment = ~30s audio · 2 segments = ~1 min (may OOM without flash-attn)
- For longer songs use [YuEGP](https://github.com/deepbeepmeep/YuEGP) (quantized, runs on 6GB+)
- **Loop Mode** auto-detects bar counts from genre (4/8/16) and bumps token budget
- **Stem Split** runs Demucs/MDX-Net on mixed/vocal/instrumental output → `<output>/stems/`
- **Section Stitch** generates intro/verse/chorus/… separately, then crossfades into `stitched.wav`
- Attribution when releasing: *"AI-assisted · YuE by HKUST/M-A-P"*

*YuE Apache 2.0 · ChilledPunks NL 🐻 Almere*
"""
        )

        def toggle_icl(mode):
            return gr.update(visible=mode == "single"), gr.update(visible=mode == "dual")

        def toggle_stem(enabled):
            return gr.update(interactive=enabled), gr.update(interactive=enabled)

        def toggle_stitch(enabled):
            # Generate+stitch widgets should match the main toggle.
            # Stitch-only must remain interactive at all times.
            return (
                gr.update(interactive=enabled),  # struct_dd
                gr.update(interactive=enabled),  # crossfade_sl
                gr.update(interactive=enabled),  # intro_cb
                gr.update(interactive=enabled),  # outro_cb
                gr.update(interactive=True),     # stitch_only_no_regen_cb (always interactive)
            )


        stitch_inputs = [lyrics_box, struct_dd, intro_cb, outro_cb]

        icl_mode.change(toggle_icl, icl_mode, [single_grp, dual_grp])
        stem_cb.change(toggle_stem, stem_cb, [stem_dd, stem_src_dd])

        stitch_cb.change(
            toggle_stitch,
            stitch_cb,
            [struct_dd, crossfade_sl, intro_cb, outro_cb, stitch_only_no_regen_cb],
        ).then(
            preview_stitch_plan, stitch_inputs, stitch_plan_md,
        )

        # Apply initial state on page load (so widgets aren't stuck disabled)
        demo.load(
            lambda enabled: toggle_stitch(enabled),
            inputs=[stitch_cb],
            outputs=[struct_dd, crossfade_sl, intro_cb, outro_cb, stitch_only_no_regen_cb],
        )

        for inp in stitch_inputs:
            inp.change(preview_stitch_plan, stitch_inputs, stitch_plan_md)
        demo.load(preview_stitch_plan, stitch_inputs, stitch_plan_md)

        load_btn.click(apply_preset, preset_dd, [genre_box, lyrics_box]).then(
            preview_stitch_plan, stitch_inputs, stitch_plan_md,
        )

        build_tags_btn.click(
            build_genre_tag_string,
            inputs=[genre_sel, mood_sel, vocal_sel, instr_sel, timbre_sel, lang_tag, custom_tags,
                    instrumental_cb, no_drums_cb],
            outputs=[genre_box],
        )

        ev = gen_btn.click(
            run_generation_stream,
            inputs=[
                preset_dd, genre_box, lyrics_box,
                lang_model,
                instrumental_cb, no_drums_cb,
                icl_mode, audio_ref, vocal_ref, inst_ref, p_start, p_end,
                seg_sl, batch_sl, tok_sl, rep_sl, seed_box, cuda_sl,
                loop_cb, loop_bars_in,
                stem_cb, stem_dd, stem_src_dd,
                stitch_cb, stitch_only_no_regen_cb, struct_dd, crossfade_sl, intro_cb, outro_cb,
            ],
            outputs=[log_out, audio_out, stems_audio],
        )
        stop_btn.click(fn=None, cancels=[ev])

    return demo


if __name__ == "__main__":
    infer_py = resolve_yue_python()
    if infer_py != sys.executable:
        print(f"YuE inference will use: {infer_py}")
        print(f"  (UI running on:        {sys.executable})")
    elif not python_has_torch(Path(infer_py)):
        print(
            "WARNING: PyTorch not found. Activate conda env 'yue' or set YUE_PYTHON.\n"
            "  Example: conda activate yue   OR   python launch_yue.py"
        )
    print(f"Hugging Face cache: {HF_HOME}")
    ui = build_ui()
    ui.queue()
    ui.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("YUE_UI_PORT", 7860)),
        share=False,
        show_error=True,
        theme=THEME,
        css=CUSTOM_CSS,
    )

