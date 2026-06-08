# TODO — Section Stitch UI enable/disable bug


- [x] Update `yue_ui.py` so the Section Stitch enable logic consistently controls:

  - `struct_dd`, `crossfade_sl`, `intro_cb`, `outro_cb`
  - `stitch_only_no_regen_cb`
- [x] Ensure both:

  - the runtime `stitch_cb.change(...)` handler
  - the initial `demo.load(...)` handler
  apply the exact same enable/disable wiring.
- [x] Run a quick syntax check (python -m py_compile) for `yue_ui.py`.


