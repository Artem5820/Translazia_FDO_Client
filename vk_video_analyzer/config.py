from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_person_weights_candidates() -> tuple[str, ...]:
    root = _project_root()
    local_yolo = root / "yolo11n.pt"
    candidates: list[str] = []
    if local_yolo.exists():
        candidates.append(str(local_yolo))
    candidates.extend(["yolo11n.pt", "yolo12n.pt", "yolo26n.pt"])
    return tuple(candidates)


def _default_layout_weights() -> Path | None:
    candidate = _project_root() / "models" / "vk_layout_best.pt"
    return candidate if candidate.exists() else None


@dataclass(slots=True)
class AnalyzerConfig:
    sample_interval_sec: float = 2.0
    sidebar_ratio: float = 0.24
    top_tile_height_ratio: float = 0.35
    teacher_main_min_area_ratio: float = 0.015
    teacher_tile_min_area_ratio: float = 0.02
    black_mean_threshold: float = 18.0
    black_std_threshold: float = 12.0
    black_screen_problem_min_sec: float = 180.0
    dark_mean_threshold: float = 40.0
    blur_laplacian_threshold: float = 45.0
    freeze_min_duration_sec: float = 12.0
    freeze_mse_threshold: float = 1.2
    freeze_hist_threshold: float = 0.995
    avatar_hough_param2: float = 24.0
    avatar_min_radius_ratio: float = 0.12
    avatar_max_radius_ratio: float = 0.42
    fullscreen_avatar_min_radius_ratio: float = 0.18
    fullscreen_avatar_max_radius_ratio: float = 0.38
    avatar_max_person_area_ratio: float = 0.008
    avatar_edge_density_max: float = 0.09
    fullscreen_avatar_edge_density_max: float = 0.035
    screen_edge_density_threshold: float = 0.03
    screen_line_count_threshold: int = 80
    screen_line_count_strong_threshold: int = 140
    screen_brightness_std_min: float = 25.0
    short_absence_sec: float = 45.0
    long_absence_early_sec: float = 90.0
    long_absence_late_sec: float = 300.0
    first_five_minutes_sec: float = 300.0
    initial_avatar_grace_sec: float = 600.0
    normal_lesson_min_sec: float = 1800.0
    long_avatar_sec: float = 180.0
    min_window_width: int = 320
    min_window_height: int = 240
    person_confidence: float = 0.25
    device: str | None = None
    person_weights_candidates: tuple[str, ...] = field(default_factory=_default_person_weights_candidates)
    layout_weights: Path | None = field(default_factory=_default_layout_weights)
    mute_templates_dir: Path | None = None
    save_observations: bool = True
    extra_notes: dict[str, str] = field(default_factory=dict)
