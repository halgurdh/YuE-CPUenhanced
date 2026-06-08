import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from yue_studio import resolve_yue_python, yue_subprocess_env

PYTHON = resolve_yue_python()
SCRIPT = str(Path(__file__).parent / "yue_ui.py")

result = subprocess.run([PYTHON, SCRIPT], env=yue_subprocess_env())
sys.exit(result.returncode)
