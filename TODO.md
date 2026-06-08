# TODO

- [ ] Optimize `yue_ui.py` for speed:
  - [ ] Add caching for expensive runtime resolution/checks (`resolve_yue_python` / torch-availability gate in UI flow)
  - [ ] Reduce recursive filesystem scans (`rglob`) by preferring deterministic candidates and early-exit search
  - [ ] Improve log streaming performance to avoid repeated large-string concatenation hot path
  - [ ] Cache `song_stitcher` imports/helpers used by reactive preview callbacks
  - [ ] Narrow stitch-only section WAV discovery/sorting to avoid broad recursive work
  - [ ] Apply small hot-path micro-optimizations (keyword constants, less repeated split/join work)
- [ ] Run syntax validation (`python -m py_compile yue_ui.py yue_studio.py`)
- [ ] Mark completed items in this TODO
