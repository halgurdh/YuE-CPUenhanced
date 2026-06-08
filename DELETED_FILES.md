# Deleted Files Reference

> Documents why files were deleted from the YuE Studio project

## Summary

These files were deleted as part of project cleanup and restructuring. Reasons vary by category.

---

## Category 1: Part of YuE Repo (Correctly Removed)

These files belonged to the upstream YuE repository and are included when you clone/install YuE.

| Deleted File | Reason |
|-------------|--------|
| `inference/infer.py` | Core YuE inference script - in ~/YuE/inference/ |
| `inference/codecmanipulator.py` | Part of YuE inference module |
| `inference/mmtokenizer.py` | Part of YuE inference module |
| `inference/xcodec_mini_infer/` | Downloaded separately from HuggingFace |
| `finetune/README.md` | Optional finetuning guide (in YuE repo) |
| `finetune/` | Entire finetune module - not needed for inference only |
| `requirements.txt` | Generic YuE requirements - replaced by requirements_studio.txt |

### Action Required
Users should clone YuE repo separately:
```bash
git clone https://github.com/multimodal-art-projection/YuE.git ~/YuE
```

---

## Category 2: Evaluation/Research Data (Large, Optional)

These were research/evaluation files used for pitch analysis and model comparison.

| Deleted File | Reason |
|-------------|--------|
| `evals/pitch_range/` | Large research data (~300+ files) |
| `evals/pitch_range/README.md` | Eval documentation |
| `evals/pitch_range/main.py` |  Eval scripts |
| `evals/pitch_range/plot_violin_plot.py` | Visualization |
| `evals/pitch_range/raw_pitch_extracted/*` | Raw pitch data for multiple models |

### Why Removed
- Not needed for music generation
- Large file size (~hundreds of MB)
- Only needed for research purposes

---

## Category 3: Replaced by New Project Files

| Deleted File | Replacement | Notes |
|-------------|------------|-------|
| `prompt_egs/genre.txt` | `prompts/genre.txt` | Moved to prompts/ directory |
| `prompt_egs/lyrics.txt` | `prompts/lyrics.txt` | Moved to prompts/ directory |
| `top_200_tags.json` | Built into yue_studio.py | GENRE_TAGS constant |
| `requirements.txt` | `requirements_studio.txt` | Studio-specific deps only |

---

## Category 4: Logo/Assets

| Deleted File | Notes |
|-------------|-------|
| `assets/logo/yue.mp3` | Audio logo |
| `assets/logo/YuE.png` | Logo image |
| `assets/logo/YuE.svg` | Vector logo |
| `assets/logo/粤歌.png` | Chinese logo |
| `assets/logo/粤歌.svg` | Chinese vector logo |
| `assets/logo/歌源.png` | Chinese logo |
| `assets/logo/歌源.svg` | Chinese vector logo |

---

## Category 5: Config/License Files

| Deleted File | Notes |
|-------------|-------|
| `.gitattributes` | Git config - no longer needed |
| `NOTICE` | License notice (redundant) |

---

## Restoration Guide

If you need any of these files back:

### Option 1: Restore from Git History
```bash
# View deleted file
git show HEAD:path/to/file

# Restore deleted file
git restore --staged path/to/file
git restore path/to/file
```

### Option 2: Clone Original YuE
```bash
# Get full YuE repository
git clone https://github.com/multimodal-art-projection/YuE.git ~/YuE
```

---

## Current Project Structure

```
sample_generator/
├── yue_studio.py      # Main CLI engine
├── yue_ui.py          # Gradio web UI
├── batch_gen.py       # Batch generation
├── lyrics_gen.py      # AI lyrics generator
├── song_stitcher.py   # Audio stitching
├── stem_splitter.py  # Stem separation
├── prompts/           # Example prompts
│   ├── genre.txt
│   └── lyrics.txt
├── requirements_studio.txt
├── install.sh
���── output/
```

---

*Generated for YuE Studio - ChilledPunks Edition*
