"""
Launch YuEGP Gradio server with configurable segment count.
Default: 2 segments (~1 min).  Pass --segments to override.

Usage:
    python launch_yuegp.py                   # 2 segments (safe default)
    python launch_yuegp.py --segments 4      # 4 segments (~2 min, may OOM)
    python launch_yuegp.py --segments 1      # 1 segment (~30s, bulletproof)
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from yue_studio import yue_subprocess_env

PYTHON = str(Path.home() / "miniconda3/envs/yuegp/python.exe")
INFERENCE_DIR = Path.home() / "YuEGP/inference"
SCRIPT = str(INFERENCE_DIR / "gradio_server.py")

parser = argparse.ArgumentParser(description="Launch YuEGP Gradio server")
parser.add_argument("--segments", type=int, default=2,
                    help="Max segments (1=~30s, 2=~1min, 3=~1.5min, 4=~2min). "
                         "Higher values risk OOM on 8GB VRAM.")
args = parser.parse_args()

# Map segments to profile (higher segments = more VRAM needed)
# Profile 4 = 12GB VRAM, Profile 3 = 8GB, Profile 2 = 6GB, Profile 1 = 4GB
segment_to_profile = {
    1: "2",  # 1 segment ~30s = 4GB
    2: "3",  # 2 segments ~1min = 6GB (safe for 8GB)
    3: "4",   # 3 segments ~1.5min = 8GB 
    4: "4",   # 4 segments ~2min = 12GB
}
profile = segment_to_profile.get(args.segments, "3")

result = subprocess.run(
    [PYTHON, SCRIPT, "--profile", profile, "--sdpa", "--segments", str(args.segments)],
    cwd=str(INFERENCE_DIR),
    env=yue_subprocess_env(),
)
sys.exit(result.returncode)
