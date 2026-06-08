#!/usr/bin/env python3
"""Append the rest of yue_ui.py (CSS rules, build_ui, __main__)."""
from pathlib import Path

REST = r'''
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
    with gr.Blocks(theme=THEME, title="YuE Studio · ChilledPunks", css=CUSTOM_CSS) as demo:

        gr.Markdown("""
# 🎵 YuE Studio — ChilledPunks Edition
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
                        genre_sel   = gr.Dropdown(GENRE_TAGS["Genre"],      label="Genre",      multiselect=True)
                        mood_sel    = gr.Dropdown(GENRE_TAGS["Mood"],       label="Mood",       multiselect=True)
                    with gr.Row():
                        vocal_sel   = gr.Dropdown(GENRE_TAGS["Vocals"],     label="Vocals",     multiselect=True)
                        instr_sel   = gr.Dropdown(GENRE_TAGS["Instruments"],label="Instruments",multiselect=True)
                    with gr.Row():
                        timbre_sel  = gr.Dropdown(GENRE_TAGS["Timbre / Production"], label="Timbre / Production", multiselect=True)
                        lang_tag    = gr.Dropdown(GENRE_TAGS["Language"],   label="Language tag",multiselect=False, value=None)
                    custom_tags = gr.Textbox(label="Extra custom tags (space-separated)", lines=1, value="")
                    with gr.Row():
                        instrumental_cb = gr.Checkbox(label="Instrumental only (no vocals)", value=False)
                        no_drums_cb     = gr.Checkbox(label="No drums", value=False)
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
                        choices=[("None", "none"), ("Single track", "single"), ("Dual track (vocal + instrumental)", "dual")],
                        value="none", label="ICL mode",
                    )
                    with gr.Group(visible=False) as single_grp:
                        audio_ref = gr.Audio(label="Reference audio (30s)", type="filepath")
                    with gr.Group(visible=False) as dual_grp:
                        vocal_ref = gr.Audio(label="Vocal track (30s)", type="filepath")
                        inst_ref  = gr.Audio(label="Instrumental track (30s)", type="filepath")
                    with gr.Row():
                        p_start = gr.Number(label="Start (s)", value=0,  precision=0)
                        p_end   = gr.Number(label="End (s)",   value=30, precision=0)

            with gr.Column(scale=2):
                with gr.Group():
                    gr.Markdown("### 🌐 Language Model")
                    lang_model = gr.Radio(
                        choices=LANG_CHOICES, value="en",
                        label="Lyrics language (ignored for instrumental only)",
                    )

                with gr.Accordion("⚙ Generation Settings (RTX 3060 8GB defaults)", open=True):
                    gr.Markdown("⚠ **8GB VRAM (RTX 3060 Ti)**: segments=1 (~30s) is safe. segments=2 (~1min) usually works — watch VRAM. Keep batch≤2.")
                    seg_sl    = gr.Slider(1, 4, value=RTX_3060_PROFILE["run_n_segments"],    step=1, label="Segments (1≈30s, 2≈1min)")
                    batch_sl  = gr.Slider(1, 4, value=RTX_3060_PROFILE["stage2_batch_size"], step=1, label="Batch size (≤2 for 8GB)")
                    tok_sl    = gr.Slider(1000, 6000, value=RTX_3060_PROFILE["max_new_tokens"], step=500, label="Max tokens")
                    rep_sl    = gr.Slider(1.0, 1.5, value=RTX_3060_PROFILE["repetition_penalty"], step=0.05, label="Repetition penalty")
                    seed_box  = gr.Textbox(label="Seed (blank = random)", value="", max_lines=1)
                    cuda_sl   = gr.Slider(0, 7, value=0, step=1, label="CUDA device")

                with gr.Accordion("🔁 Loop Mode — pre-generation", open=False):
                    gr.Markdown("_Auto-detect bar count from genre and raise token budget. Clamped to 8GB VRAM max (1 segment ≈ 30s ≈ 12 bars)._")
                    with gr.Row():
                        loop_cb      = gr.Checkbox(label="Enable Loop Mode", value=False)
                        loop_bars_in = gr.Number(label="Bars/section (0 = auto-detect)", value=0, precision=0)

                with gr.Accordion("🛠 Post-Processing — runs after generation", open=False):
                    gr.Markdown("_Optional automatic post-processing of the generated track._")
                    with gr.Group():
                        gr.Markdown("**🎚 Stem Split** (requires `audio-separator`)")
                        with gr.Row():
                            stem_cb = gr.Checkbox(label="Split into stems (vocals/drums/bass/…)", value=False)
                            stem_dd = gr.Dropdown(choices=STEM_CHOICES, value=STEM_DEFAULT_MODEL, label="Stem model")
                    with gr.Group():
                        gr.Markdown("**🔗 Section Stitching** (requires `pydub` + ffmpeg)")
                        with gr.Row():
                            stitch_cb = gr.Checkbox(label="Stitch generated sections with crossfade", value=False)
                            struct_dd = gr.Dropdown(choices=STRUCTURE_CHOICES, value="pop", label="Song structure")
                        crossfade_sl = gr.Slider(0, 5000, value=1500, step=100, label="Crossfade (ms)")
                        with gr.Row():
                            intro_cb = gr.Checkbox(label="Include intro", value=True)
                            outro_cb = gr.Checkbox(label="Include outro", value=True)

                gr.Markdown("### 🚀 Generate")
                with gr.Row():
                    gen_btn  = gr.Button("Generate Track ▶", variant="primary")
                    stop_btn = gr.Button("■ Stop", variant="stop")

                gr.Markdown("### 🎧 Output")
                with gr.Row():
                    audio_out   = gr.Audio(label="Generated track", type="filepath", interactive=False)
                    stems_audio = gr.Audio(label="Stems preview (vocals or first stem)", type="filepath", interactive=False)
                log_out = gr.Textbox(label="Log", lines=20, max_lines=50, interactive=False)

        gr.Markdown("""
---
**RTX 3060 8GB tips**
- 1 segment = ~30s audio · 2 segments = ~1 min (may OOM without flash-attn)
- For longer songs use [YuEGP](https://github.com/deepbeepmeep/YuEGP) (quantized, runs on 6GB+)
- **Loop Mode** auto-detects bar counts from genre (4/8/16) and bumps token budget
- **Stem Split** runs Demucs/MDX-Net on the mixed output (writes to `<output>/stems/`)
- **Section Stitching** uses pydub crossfades to merge per-section WAVs
- Attribution when releasing: *"AI-assisted · YuE by HKUST/M-A-P"*

*YuE Apache 2.0 · ChilledPunks NL 🐻 Almere*
""")

        def toggle_icl(mode):
            return gr.update(visible=mode == "single"), gr.update(visible=mode == "dual")

        icl_mode.change(toggle_icl, icl_mode, [single_grp, dual_grp])
        load_btn.click(apply_preset, preset_dd, [genre_box, lyrics_box])
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
                stem_cb, stem_dd,
                stitch_cb, struct_dd, crossfade_sl, intro_cb, outro_cb,
            ],
            outputs=[log_out, audio_out, stems_audio],
        )
        stop_btn.click(fn=None, cancels=[ev])

    return demo


if __name__ == "__main__":
    ui = build_ui()
    ui.queue()
    ui.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("YUE_UI_PORT", 7860)),
        share=False,
        show_error=True,
    )
'''

p = Path(r"c:\Projects\sample_generator\yue_ui.py")
# Find the partial CSS line that needs to be completed
text = p.read_text(encoding="utf-8") # Specify UTF-8 encoding
# Insert REST right before the comment that signals CSS completeness
# The partial CSS ends with: .gradio-container textarea { ... }\n\n
# We need to replace the truncated CSS block with the full one.
# Simpler: just append REST (the existing partial CSS is already there but missing the rest)
# Look for the start marker
marker = "/* Plain inputs and textareas */"
idx = text.find(marker)
if idx < 0:
    print("ERROR: marker not found")
    raise SystemExit(1)

# Find the closing of that block
end_idx = text.find("}\n\n/* Selected / highlighted option */", idx) # Adjust search pattern for the new structure
if end_idx < 0:
    end_idx = text.find("background-color: #f5f5f5 !important;\n}", idx)
    if end_idx < 0:
        print("ERROR: CSS end not found")
        raise SystemExit(1)

end_idx = text.find("\n}", end_idx) + 2  # include the closing }

# Truncate at end_idx, then append REST
new_text = text[:end_idx] + REST
p.write_text(new_text, encoding="utf-8") # Specify UTF-8 encoding
print(f"OK — file is now {len(new_text.splitlines())} lines")
