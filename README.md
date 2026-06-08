# 🎵 YuE Studio — ChilledPunks Edition

> Local full-song AI music generation  
> Powered by **[YuE](https://github.com/multimodal-art-projection/YuE)** (open-source Suno alternative)  
> Inspired by **[ChilledPunks NL](https://chilledpunks.com)** — independent label, Almere 🐻  
> **Optimized for RTX 3060ti 8GB**

---

## Files

| File | Purpose |
|------|---------|
| `yue_studio.py` | Main engine: CLI + interactive wizard + all logic |
| `yue_ui.py` | Gradio web UI (genre tag builder, ICL, live log) |
| `batch_gen.py` | Multi-take batch generation with seeds |
| `lyrics_gen.py` | AI lyrics via Claude API (optional) |
| `install.sh` | One-shot installer (Linux/WSL/Mac) |
| `requirements_studio.txt` | Studio Python deps |
| `prompts/genre.txt` | Example genre tags |
| `prompts/lyrics.txt` | Example lyrics |


---

## RESTART
taskkill /F /IM python.exe
set YUE_UI_PORT=7861 && python yue_ui.py
set YUE_UI_PORT=7861 && python -m py_compile yue_ui.py
python yue_ui.py


---

## Quick Start

### Step 1 — Install

```bash
bash install.sh
```

Or manually:

```bash
# Create conda env
conda create -n yue python=3.10
conda activate yue

# PyTorch (CUDA 11.8 — RTX 3060)
conda install pytorch torchvision torchaudio pytorch-cuda=11.8 -c pytorch -c nvidia

# Clone YuE
git clone https://github.com/multimodal-art-projection/YuE.git ~/YuE
pip install -r ~/YuE/requirements.txt

# REQUIRED for 8GB VRAM — reduces memory significantly
pip install flash-attn --no-build-isolation

# Download codec tokenizer
cd ~/YuE/inference
git lfs install
git clone https://huggingface.co/m-a-p/xcodec_mini_infer

# Studio deps
pip install -r requirements_studio.txt
```

### Step 2 — Configure

```bash
# Set YuE path (if not ~/YuE)
export YUE_DIR=~/YuE
export YUE_OUTPUT=./output
```

### Step 3 — Generate

```bash
# Interactive wizard (best starting point)
python yue_studio.py

# Quick CLI with preset
python yue_studio.py generate --preset lofi_hiphop

# Web UI
python yue_ui.py
# → open http://localhost:7860
```

---

## RTX 3060 8GB Guide

| Setting | Safe value | Notes |
|---------|-----------|-------|
| `--segments` | **1** | ~30s audio. 2 may OOM without flash-attn |
| `--batch-size` | **2** | Stage 2 batch. 4 will likely OOM |
| flash-attn | **required** | Cuts VRAM by ~30% |
| Max VRAM usage | ~7–7.5 GB | Leaves headroom |

### For longer songs on 8GB

Use **[YuEGP](https://github.com/deepbeepmeep/YuEGP)** — quantized YuE that runs on 6GB+ with 2–4 segments:
```bash
pip install YuEGP
python -m yuegp.infer --preset lofi_hiphop --segments 4
```

Or **[YuE-exllamav2](https://github.com/sgsdxzy/YuE-exllamav2)** for ExLlama2 quantized inference.

---

## Genre Tag System

YuE uses space-separated tags (no quotes). Build them from 5 components:

```
[genre] [instrument] [mood] [gender] [timbre]
```

**Examples:**
```
lofi hip-hop instrumental male mellow acoustic piano vinyl warm beats
afropop female uplifting dancehall groovy percussion bright vocal
moombahton electronic bass male energetic synth dark vocal dance 808
rnb soul female smooth warm saxophone piano emotional vocal expressive
```

**Available tag categories** (see `yue_studio.py GENRE_TAGS` for full list):

- **Genre**: pop, hip-hop, rap, rnb, soul, jazz, lofi, electronic, afropop, moombahton, trap, reggaeton, ambient...
- **Mood**: uplifting, mellow, energetic, dark, groovy, inspiring, dreamy, nostalgic...
- **Vocals**: male, female, vocal, no-vocal, instrumental, airy vocal, bright vocal, rap-vocal...
- **Instruments**: piano, guitar, bass, drums, saxophone, synthesizer, violin...
- **Timbre**: vinyl, lo-fi, warm, bright, gritty, smooth, 808, boom-bap...
- **Language**: English, Mandarin, Cantonese, Japanese, Korean

Full 200-tag list: [top_200_tags.json](https://github.com/multimodal-art-projection/YuE/blob/main/top_200_tags.json)

---

## Presets

| Key | Style | Description |
|-----|-------|-------------|
| `lofi_hiphop` | Lo-Fi Hip-Hop | Dusty chill beats — Allgood / Almere |
| `afro_pop` | Afro-Pop | Groovy Afrobeats — Kchris energy |
| `moombahton` | Moombahton | Half-time bass underground |
| `hip_hop_nl` | Dutch Hip-Hop | Raw NL rap — Ridicuul / Mc Drt |
| `chillout` | Chillout | Atmospheric late-night ambient |
| `rnb_soul` | R&B / Soul | Smooth soulful lush production |
| `trap` | Trap | Heavy 808s, hi-hats |
| `jazz_soul` | Jazz Soul | Smoky saxophone soulful delivery |
| `reggaeton` | Reggaeton | Dembow tropical energy |

---

## Usage Examples

### CLI
```bash
# List presets
python yue_studio.py presets

# Show all genre tags
python yue_studio.py tags

# Generate with preset
python yue_studio.py generate --preset afro_pop

# Custom genre + lyrics
python yue_studio.py generate \
  --genre prompts/genre.txt \
  --lyrics prompts/lyrics.txt \
  --segments 1 --batch-size 2 --seed 42

# With style reference (ICL dual-track)
python yue_studio.py generate \
  --preset rnb_soul --icl \
  --vocal stems/song_Vocals.wav \
  --instrumental stems/song_Instrumental.wav \
  --prompt-start 0 --prompt-end 30

# Chinese lyrics model
python yue_studio.py generate \
  --preset chillout --lang zh \
  --lyrics prompts/lyrics_zh.txt
```

### Batch (multiple takes)
```bash
# 3 random takes
python batch_gen.py --preset lofi_hiphop --count 3

# 5 takes with specific seeds
python batch_gen.py --preset trap --count 5 --seeds 1 42 100 999 2025
```

### AI Lyrics (needs ANTHROPIC_API_KEY)
```bash
export ANTHROPIC_API_KEY=sk-...

python lyrics_gen.py \
  --preset moombahton \
  --theme "underground rave on a Tuesday night" \
  --output prompts/lyrics.txt

# Then generate:
python yue_studio.py generate --preset moombahton --lyrics prompts/lyrics.txt
```

---

## Lyrics Format

```
[verse]
Line 1
Line 2
Line 3

[chorus]
Line 1
Line 2

[bridge]
Optional bridge

[outro]
Optional outro
```

- Each section ≈ 30s = 1 segment = one `run_n_segments` count
- Don't use `[intro]` — less stable in YuE
- Keep each section ≤ 12 lines

---

## ICL (Style Transfer)

Give YuE a 30s reference audio to guide the style:

```bash
# Install stem splitter
pip install audio-separator

# Split reference into vocal + instrumental
audio-separator my_reference.mp3 --output_dir ./stems
# → stems/my_reference_(Vocals).wav + stems/my_reference_(Instrumental).wav

# Generate with dual-track ICL
python yue_studio.py generate \
  --preset hip_hop_nl --icl \
  --vocal stems/my_reference_\(Vocals\).wav \
  --instrumental stems/my_reference_\(Instrumental\).wav
```

---

## Output

```
output/
├── lofi_hiphop_20250607_143022/
│   ├── mixed_output.wav          ← full mix
│   ├── vocal_output.wav          ← vocal only
│   └── instrumental_output.wav   ← instrumental only
└── batch_trap_20250607_160000/
    ├── take_01/
    ├── take_02_s42/               ← seed 42
    ├── take_03_s99/
    └── manifest.json
```

---

## Attribution

YuE is Apache 2.0 licensed. When releasing tracks:

> *"AI-assisted · YuE by HKUST/M-A-P"*

ChilledPunks: [chilledpunks.com](https://chilledpunks.com)
Discord: [discord.gg/fRzwdEY4rT](https://discord.gg/fRzwdEY4rT)
