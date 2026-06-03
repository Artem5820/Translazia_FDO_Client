from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np


@dataclass(slots=True)
class Detection:
    class_name: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def area(self) -> float:
        return max(0.0, self.x2 - self.x1) * max(0.0, self.y2 - self.y1)

    def intersects(self, region: tuple[int, int, int, int]) -> bool:
        rx1, ry1, rx2, ry2 = region
        return not (self.x2 <= rx1 or self.x1 >= rx2 or self.y2 <= ry1 or self.y1 >= ry2)

    def intersection_area(self, region: tuple[int, int, int, int]) -> float:
        rx1, ry1, rx2, ry2 = region
        ix1 = max(self.x1, rx1)
        iy1 = max(self.y1, ry1)
        ix2 = min(self.x2, rx2)
        iy2 = min(self.y2, ry2)
        return max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)


class YoloDetector:
    def __init__(self, weights: str | Path, device: str | None = None, conf: float = 0.25) -> None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("ultralytics is not installed. Run `pip install -r requirements.txt`.") from exc

        self.model = YOLO(str(weights))
        self.device = device
        self.conf = conf
        self.names = self.model.names

    def detect(self, frame: np.ndarray) -> list[Detection]:
        results = self.model.predict(frame, conf=self.conf, device=self.device, verbose=False)
        if not results:
            return []

        boxes = results[0].boxes
        if boxes is None:
            return []

        detections: list[Detection] = []
        xyxy = boxes.xyxy.cpu().numpy()
        confidences = boxes.conf.cpu().numpy()
        classes = boxes.cls.cpu().numpy().astype(int)
        for coords, confidence, cls_id in zip(xyxy, confidences, classes, strict=False):
            x1, y1, x2, y2 = coords.tolist()
            class_name = str(self.names.get(int(cls_id), cls_id))
            detections.append(
                Detection(
                    class_name=class_name,
                    confidence=float(confidence),
                    x1=float(x1),
                    y1=float(y1),
                    x2=float(x2),
                    y2=float(y2),
                )
            )
        return detections


class OptionalTemplateMatcher:
    def __init__(self, templates_dir: Path | None) -> None:
        self.templates: list[np.ndarray] = []
        if templates_dir is None:
            return

        if not templates_dir.exists():
            return

        for path in sorted(templates_dir.glob("*.png")):
            template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if template is not None:
                self.templates.append(template)

    def match(self, image: np.ndarray, threshold: float = 0.78) -> float:
        if not self.templates:
            return 0.0

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        best = 0.0
        for template in self.templates:
            h, w = template.shape[:2]
            if gray.shape[0] < h or gray.shape[1] < w:
                continue
            result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            best = max(best, float(max_val))
        return best if best >= threshold else 0.0


def choose_available_person_weights(candidates: Iterable[str | Path], device: str | None, conf: float) -> YoloDetector:
    errors: list[str] = []
    for candidate in candidates:
        try:
            return YoloDetector(candidate, device=device, conf=conf)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{candidate}: {exc}")
    joined = "; ".join(errors)
    raise RuntimeError(f"Could not initialize any YOLO person detector. Tried: {joined}")
