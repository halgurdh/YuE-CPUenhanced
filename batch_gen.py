"""
YuE Studio — Batch Generator
Generate multiple takes with different seeds.

Usage:
    python batch_gen.py --preset lofi_hiphop --count 3
    python batch_gen.py --genre prompts/genre.txt --lyrics prompts/lyrics.txt --count 5 --seeds 1 42 99
"""

import argparse
import json
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent))
from yue_studio import (
    PRESETS, OUTPUT_DIR, RTX_3060_PROFILE,
    build_infer_command, write_prompt_files, run_generation,
    MODELS,
)

console = Console()


def batch_generate(
    genre_tags, lyrics, label,
    count=3, seeds=None, lang="en", icl=False,
    segments=None, batch_size=None, cuda_idx=0, rep_penalty=1.1,
):
    segments   = segments   or RTX_3060_PROFILE["run_n_segments"]
    batch_size = batch_size or RTX_3060_PROFILE["stage2_batch_size"]
    seeds = (seeds or []) + [None] * max(0, count - len(seeds or []))
    stage1 = MODELS.get(f"icl_{lang}" if icl else f"cot_{lang}", MODELS["cot_en"])

    ts_base   = time.strftime("%Y%m%d_%H%M%S")
    batch_dir = OUTPUT_DIR / f"batch_{label}_{ts_base}"
    genre_path, lyrics_path = write_prompt_files(genre_tags, lyrics)

    console.print(f"\n[bold yellow]Batch: {count} takes → {batch_dir}[/bold yellow]\n")

    results = []
    for i in range(count):
        seed    = seeds[i]
        run_dir = batch_dir / f"take_{i+1:02d}{'_s'+str(seed) if seed is not None else ''}"
        console.print(f"[bold]Take {i+1}/{count}[/bold]  seed={seed if seed is not None else 'random'}")
        cmd = build_infer_command(
            genre_path=genre_path, lyrics_path=lyrics_path,
            output_dir=run_dir, cuda_idx=cuda_idx, stage1_model=stage1,
            run_n_segments=segments, stage2_batch_size=batch_size,
            repetition_penalty=rep_penalty, seed=seed,
        )
        ok    = run_generation(cmd, run_dir)
        files = list(run_dir.rglob("*.wav")) + list(run_dir.rglob("*.mp3"))
        results.append({"take": i+1, "seed": seed, "dir": str(run_dir),
                         "files": [str(f) for f in files], "ok": ok})

    table = Table(title="Batch Summary", border_style="yellow")
    table.add_column("Take", style="cyan"); table.add_column("Seed")
    table.add_column("Files"); table.add_column("Status")
    for r in results:
        table.add_row(str(r["take"]), str(r["seed"] or "random"),
                      str(len(r["files"])),
                      "[green]✓[/green]" if r["ok"] else "[red]✗[/red]")
    console.print(table)

    manifest = batch_dir / "manifest.json"
    manifest.write_text(json.dumps(results, indent=2))
    console.print(f"[dim]Manifest → {manifest}[/dim]")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--preset",  choices=list(PRESETS.keys()))
    p.add_argument("--genre",   type=Path)
    p.add_argument("--lyrics",  type=Path)
    p.add_argument("--count",   type=int,   default=3)
    p.add_argument("--seeds",   type=int,   nargs="*")
    p.add_argument("--lang",    choices=["en","zh","jp-kr"], default="en")
    p.add_argument("--icl",     action="store_true")
    p.add_argument("--segments",    type=int, default=None)
    p.add_argument("--batch-size",  type=int, default=None)
    p.add_argument("--cuda",        type=int, default=0)
    p.add_argument("--rep-penalty", type=float, default=1.1)
    args = p.parse_args()

    if args.preset:
        pr = PRESETS[args.preset]
        genre_tags, lyrics, label = pr["genre_tags"], pr["lyric_template"], args.preset
    elif args.genre and args.lyrics:
        genre_tags = args.genre.read_text()
        lyrics     = args.lyrics.read_text()
        label = "custom"
    else:
        print("✗ Provide --preset OR --genre + --lyrics"); sys.exit(1)

    batch_generate(
        genre_tags=genre_tags, lyrics=lyrics, label=label,
        count=args.count, seeds=args.seeds, lang=args.lang, icl=args.icl,
        segments=args.segments, batch_size=args.batch_size,
        cuda_idx=args.cuda, rep_penalty=args.rep_penalty,
    )


if __name__ == "__main__":
    main()
