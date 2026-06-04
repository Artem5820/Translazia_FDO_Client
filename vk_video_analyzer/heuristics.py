from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .config import AnalyzerConfig


@dataclass(slots=True)
class LayoutRegions:
    main_region: tuple[int, int, int, int]
    sidebar_region: tuple[int, int, int, int]
    teacher_tile_region: tuple[int, int, int, int]


def split_layout(frame: np.ndarray, config: AnalyzerConfig) -> LayoutRegions:
    height, width = frame.shape[:2]
    sidebar_x1 = int(width * (1.0 - config.sidebar_ratio))
    tile_y2 = int(height * config.top_tile_height_ratio)
    return LayoutRegions(
        main_region=(0, 0, sidebar_x1, height),
        sidebar_region=(sidebar_x1, 0, width, height),
        teacher_tile_region=(sidebar_x1, 0, width, tile_y2),
    )


def crop(frame: np.ndarray, region: tuple[int, int, int, int]) -> np.ndarray:
    x1, y1, x2, y2 = region
    return frame[y1:y2, x1:x2]


def edge_density(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 180)
    return float(np.count_nonzero(edges)) / float(edges.size or 1)


def brightness_stats(image: np.ndarray) -> tuple[float, float]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(gray.mean()), float(gray.std())


def blur_score(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def line_count(image: np.ndarray) -> int:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 180)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 80, minLineLength=60, maxLineGap=10)
    return 0 if lines is None else int(len(lines))


def histogram_signature(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([gray], [0], None, [64], [0, 256])
    hist = cv2.normalize(hist, hist).flatten()
    return hist


def histogram_similarity(left: np.ndarray, right: np.ndarray) -> float:
    return float(cv2.compareHist(left.astype(np.float32), right.astype(np.float32), cv2.HISTCMP_CORREL))


def mse_similarity(left: np.ndarray, right: np.ndarray) -> float:
    diff = left.astype(np.float32) - right.astype(np.float32)
    return float(np.mean(diff * diff))


def detect_black_screen(image: np.ndarray, config: AnalyzerConfig) -> bool:
    mean_value, std_value = brightness_stats(image)
    return mean_value <= config.black_mean_threshold and std_value <= config.black_std_threshold


def detect_low_quality(image: np.ndarray, config: AnalyzerConfig) -> bool:
    mean_value, _ = brightness_stats(image)
    return mean_value <= config.dark_mean_threshold or blur_score(image) <= config.blur_laplacian_threshold


def detect_avatar(tile_image: np.ndarray, person_area_ratio: float, config: AnalyzerConfig) -> bool:
    if person_area_ratio > config.avatar_max_person_area_ratio:
        return False
    if edge_density(tile_image) > config.avatar_edge_density_max:
        return False

    gray = cv2.cvtColor(tile_image, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    min_radius = int(min(tile_image.shape[:2]) * config.avatar_min_radius_ratio)
    max_radius = int(min(tile_image.shape[:2]) * config.avatar_max_radius_ratio)
    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(20, min(tile_image.shape[:2]) // 4),
        param1=80,
        param2=config.avatar_hough_param2,
        minRadius=min_radius,
        maxRadius=max_radius,
    )
    return circles is not None


def detect_fullscreen_avatar(image: np.ndarray, person_area_ratio: float, config: AnalyzerConfig) -> bool:
    if person_area_ratio > config.avatar_max_person_area_ratio:
        return False
    if edge_density(image) > config.fullscreen_avatar_edge_density_max:
        return False

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    min_side = min(image.shape[:2])
    min_radius = int(min_side * config.fullscreen_avatar_min_radius_ratio)
    max_radius = int(min_side * config.fullscreen_avatar_max_radius_ratio)
    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(40, min_side // 3),
        param1=80,
        param2=config.avatar_hough_param2,
        minRadius=min_radius,
        maxRadius=max_radius,
    )
    if circles is None:
        return False

    circle_candidates = circles[0]
    if len(circle_candidates) > 4:
        return False

    image_h, image_w = image.shape[:2]
    center_x = image_w / 2.0
    center_y = image_h / 2.0
    x, y, _ = circle_candidates[0]
    return abs(x - center_x) <= image_w * 0.16 and abs(y - center_y) <= image_h * 0.16


def detect_screen_share(image: np.ndarray, person_in_main: bool, config: AnalyzerConfig) -> bool:
    if person_in_main:
        return False
    image_edge_density = edge_density(image)
    image_line_count = line_count(image)
    _, std_value = brightness_stats(image)
    has_dense_ui = (
        image_edge_density >= config.screen_edge_density_threshold
        and image_line_count >= config.screen_line_count_threshold
    )
    has_many_straight_lines = (
        image_edge_density >= config.screen_edge_density_threshold * 0.66
        and image_line_count >= config.screen_line_count_strong_threshold
    )
    return std_value >= config.screen_brightness_std_min and (has_dense_ui or has_many_straight_lines)


def detect_empty_room(image: np.ndarray, screen_share: bool, black_screen: bool) -> bool:
    if screen_share or black_screen:
        return False
    density = edge_density(image)
    return 0.01 <= density <= 0.07
