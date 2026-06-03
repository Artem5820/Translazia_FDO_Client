from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import re
import time

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtWebEngineWidgets import QWebEngineView

from ..config import AppSettings


class StreamCaptureSession(QObject):
    finished = Signal(str, str)
    failed = Signal(str, str)

    def __init__(self, room: str, view: QWebEngineView, settings: AppSettings, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.room = room
        self.view = view
        self.settings = settings
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._capture_frame)
        self.started_at = 0.0
        self.frames_written = 0
        self.output_path: Path | None = None
        self.writer: Any = None
        self.writer_size: tuple[int, int] | None = None
        self.cv2: Any = None
        self.np: Any = None
        self.active = False

    def start(self) -> None:
        try:
            import cv2
            import numpy as np
        except Exception as exc:
            self.failed.emit(self.room, f"Для захвата нужен opencv-python: {exc}")
            return

        self.cv2 = cv2
        self.np = np
        output_dir = Path(self.settings.analysis.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_room = re.sub(r"[^0-9A-Za-zА-Яа-яЁё-]+", "_", self.room)
        self.output_path = output_dir / f"{safe_room}_{stamp}.mp4"
        self.started_at = time.monotonic()
        self.frames_written = 0
        self.active = True
        interval_ms = max(100, int(1000 / max(0.2, float(self.settings.analysis.capture_fps))))
        self.timer.start(interval_ms)

    def stop(self) -> None:
        self.timer.stop()
        self.active = False
        if self.writer is not None:
            self.writer.release()
            self.writer = None
        self.writer_size = None

    @Slot()
    def _capture_frame(self) -> None:
        if not self.output_path or self.cv2 is None or self.np is None:
            self.stop()
            self.failed.emit(self.room, "Захват не был инициализирован.")
            return

        elapsed = time.monotonic() - self.started_at
        if elapsed >= float(self.settings.analysis.duration_seconds):
            self.stop()
            if self.frames_written == 0:
                self.failed.emit(self.room, "Не удалось получить кадры из окна трансляции.")
                return
            self.finished.emit(self.room, str(self.output_path))
            return

        pixmap = self.view.grab()
        if pixmap.isNull():
            return

        image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB888)
        width = image.width()
        height = image.height()
        bytes_per_line = image.bytesPerLine()
        bits = image.bits()
        try:
            bits.setsize(image.sizeInBytes())
        except AttributeError:
            pass
        array = self.np.frombuffer(bits, dtype=self.np.uint8).reshape((height, bytes_per_line))
        rgb = array[:, : width * 3].reshape((height, width, 3))
        frame = self.cv2.cvtColor(rgb, self.cv2.COLOR_RGB2BGR)
        frame_height, frame_width = frame.shape[:2]
        even_width = frame_width - (frame_width % 2)
        even_height = frame_height - (frame_height % 2)
        if even_width <= 0 or even_height <= 0:
            return
        if even_width != frame_width or even_height != frame_height:
            frame = frame[:even_height, :even_width]
            width = even_width
            height = even_height

        if self.writer is None:
            fourcc = self.cv2.VideoWriter_fourcc(*"mp4v")
            fps = max(0.2, float(self.settings.analysis.capture_fps))
            self.writer = self.cv2.VideoWriter(str(self.output_path), fourcc, fps, (width, height))
            if not self.writer.isOpened():
                self.stop()
                self.failed.emit(self.room, "OpenCV не смог создать видеофайл фрагмента.")
                return
            self.writer_size = (width, height)
        elif self.writer_size and (width, height) != self.writer_size:
            width, height = self.writer_size
            frame = self.cv2.resize(frame, (width, height), interpolation=self.cv2.INTER_AREA)

        self.writer.write(frame)
        self.frames_written += 1
