#!/usr/bin/env bash
# YuE Studio — One-shot installer
# Installs conda env, YuE repo, xcodec tokenizer, flash-attn, and studio deps.
# Usage: bash install.sh

set -e

YUE_DIR="${YUE_DIR:-$HOME/YuE}"
CONDA_ENV="yue"
PYTHON_VERSION="3.10"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  YuE Studio — Installer                 ║"
echo "║  RTX 3060 8GB edition · ChilledPunks NL ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Conda env ─────────────────────────────────────────────────────────────
if ! command -v conda &>/dev/null; then
    echo "⚠ conda not found. Install Miniconda first:"
    echo "  https://docs.conda.io/en/latest/miniconda.html"
    exit 1
fi

echo "→ Creating conda env '$CONDA_ENV' (Python $PYTHON_VERSION)..."
conda create -n "$CONDA_ENV" python="$PYTHON_VERSION" -y 2>/dev/null || true
# Activate in subshell
CONDA_BASE=$(conda info --base)
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "$CONDA_ENV"

# ── 2. PyTorch (CUDA 11.8 — compatible with RTX 3060) ───────────────────────
echo "→ Installing PyTorch (CUDA 11.8)..."
conda install pytorch torchvision torchaudio pytorch-cuda=11.8 \
    -c pytorch -c nvidia -y

# ── 3. Clone YuE ──────────────────────────────────────────────────────────────
if [ ! -d "$YUE_DIR" ]; then
    echo "→ Cloning YuE repo to $YUE_DIR..."
    git clone https://github.com/multimodal-art-projection/YuE.git "$YUE_DIR"
else
    echo "✓ YuE repo already at $YUE_DIR"
fi

echo "→ Installing YuE requirements..."
pip install -r "$YUE_DIR/requirements.txt"

# ── 4. xcodec tokenizer ───────────────────────────────────────────────────────
XCODEC_DIR="$YUE_DIR/inference/xcodec_mini_infer"
if [ ! -d "$XCODEC_DIR" ]; then
    echo "→ Downloading xcodec tokenizer..."
    # Ensure git-lfs
    if ! command -v git-lfs &>/dev/null; then
        echo "  Installing git-lfs..."
        sudo apt-get install -y git-lfs 2>/dev/null || brew install git-lfs 2>/dev/null || true
    fi
    git lfs install
    git clone https://huggingface.co/m-a-p/xcodec_mini_infer "$XCODEC_DIR"
else
    echo "✓ xcodec tokenizer already present"
fi

# ── 5. flash-attn (critical for 8GB VRAM) ────────────────────────────────────
echo "→ Installing flash-attn (required to fit in 8GB VRAM)..."
pip install flash-attn --no-build-isolation || {
    echo "⚠ flash-attn failed to build. Try:"
    echo "  pip install flash-attn --no-build-isolation"
    echo "  Or install a pre-built wheel from https://github.com/Dao-AILab/flash-attention/releases"
}

# ── 6. Studio dependencies ────────────────────────────────────────────────────
STUDIO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "→ Installing YuE Studio requirements..."
pip install -r "$STUDIO_DIR/requirements_studio.txt"

# ── 7. Write .env ─────────────────────────────────────────────────────────────
ENV_FILE="$STUDIO_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" <<EOF
# YuE Studio environment
export YUE_DIR="$YUE_DIR"
export YUE_OUTPUT="$STUDIO_DIR/output"
# export ANTHROPIC_API_KEY="sk-..."   # uncomment for lyrics_gen.py
# export YUE_UI_PORT=7860
EOF
    echo "✓ Created .env — edit to set ANTHROPIC_API_KEY"
fi

echo ""
echo "╔═══════════════════════════════════════════════╗"
echo "║  ✓ Installation complete!                    ║"
echo "╠═══════════════════════════════════════════════╣"
echo "║  Activate env:  conda activate yue           ║"
echo "║  Source .env:   source .env                  ║"
echo "║  Launch UI:     python yue_ui.py             ║"
echo "║  CLI wizard:    python yue_studio.py         ║"
echo "║  Quick test:    python yue_studio.py generate --preset lofi_hiphop"
echo "╚═══════════════════════════════════════════════╝"
echo ""
echo "⚠  RTX 3060 8GB: keep segments=1, batch_size=2"
echo "   For quantized (longer songs): github.com/deepbeepmeep/YuEGP"
