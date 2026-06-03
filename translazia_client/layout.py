from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(slots=True, frozen=True)
class ScreenRect:
    x: int
    y: int
    width: int
    height: int


@dataclass(slots=True, frozen=True)
class WindowPlacement:
    x: int
    y: int
    width: int
    height: int
    screen_index: int


def compute_window_placements(screens: list[ScreenRect], window_count: int) -> list[WindowPlacement]:
    if window_count <= 0:
        return []
    if not screens:
        screens = [ScreenRect(0, 0, 1280, 720)]

    screen_count = min(len(screens), window_count)
    distribution = _distribute(window_count, screen_count)
    placements: list[WindowPlacement] = []
    window_index = 0

    for screen_index, count_on_screen in enumerate(distribution):
        rect = screens[screen_index]
        rows, cols = _best_grid(count_on_screen, rect.width, rect.height)
        cell_w = rect.width // cols
        cell_h = rect.height // rows

        for local_index in range(count_on_screen):
            row = local_index // cols
            col = local_index % cols
            is_last_col = col == cols - 1
            is_last_row = row == rows - 1
            x = rect.x + col * cell_w
            y = rect.y + row * cell_h
            w = rect.width - col * cell_w if is_last_col else cell_w
            h = rect.height - row * cell_h if is_last_row else cell_h
            placements.append(WindowPlacement(x=x, y=y, width=w, height=h, screen_index=screen_index))
            window_index += 1
            if window_index >= window_count:
                return placements

    return placements


def _distribute(total: int, buckets: int) -> list[int]:
    base = total // buckets
    remainder = total % buckets
    return [base + (1 if index < remainder else 0) for index in range(buckets)]


def _best_grid(count: int, width: int, height: int) -> tuple[int, int]:
    if count <= 1:
        return (1, 1)

    aspect = max(0.2, width / max(1, height))
    best: tuple[float, int, int] | None = None
    for cols in range(1, count + 1):
        rows = math.ceil(count / cols)
        cell_w = width / cols
        cell_h = height / rows
        cell_aspect = cell_w / max(1.0, cell_h)
        aspect_penalty = abs(math.log(max(0.01, cell_aspect / aspect)))
        empty_cells = rows * cols - count
        score = aspect_penalty + empty_cells * 0.08 + rows * 0.01
        if best is None or score < best[0]:
            best = (score, rows, cols)

    assert best is not None
    return best[1], best[2]
