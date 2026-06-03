from __future__ import annotations

from pathlib import Path
import shutil


def cleanup_results_folder(output_dir: str | Path) -> int:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    removed = 0
    for item in folder.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            removed += 1
        except FileNotFoundError:
            continue
    return removed
