from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
import os
import shutil

from ..analysis import AUDIO_VENDOR, VIDEO_VENDOR
from ..config import AppSettings


@dataclass(slots=True, frozen=True)
class HealthIssue:
    level: str
    title: str
    details: str = ""


def run_startup_healthcheck(settings: AppSettings) -> list[HealthIssue]:
    issues: list[HealthIssue] = []

    for package in ("PySide6", "requests", "cv2", "numpy"):
        if find_spec(package) is None:
            issues.append(HealthIssue("Ошибка", f"Не установлена зависимость {package}"))

    if find_spec("ultralytics") is None:
        issues.append(HealthIssue("Ошибка", "Не установлена зависимость ultralytics"))

    if not VIDEO_VENDOR.exists():
        issues.append(HealthIssue("Ошибка", "Не найден модуль видеоанализа", str(VIDEO_VENDOR)))
    else:
        for relative in ("vk_video_analyzer/analyzer.py", "models/vk_layout_best.pt", "yolo11n.pt"):
            path = VIDEO_VENDOR / relative
            if not path.exists():
                issues.append(HealthIssue("Ошибка", f"Не найден файл видеоанализа: {relative}", str(path)))

    if settings.analysis.audio_analysis_enabled:
        if not AUDIO_VENDOR.exists():
            issues.append(HealthIssue("Предупреждение", "Аудиоанализ включен, но SoundChecker не найден", str(AUDIO_VENDOR)))
        elif _find_ffmpeg() is None:
            issues.append(
                HealthIssue(
                    "Предупреждение",
                    "Аудиоанализ включен, но ffmpeg не найден",
                    "Укажите FFMPEG_BINARY или добавьте ffmpeg.exe в PATH. Без ffmpeg SoundChecker не сможет проверить звук в mp4-фрагментах.",
                )
            )

    if settings.source.mode == "file" and not Path(settings.source.local_file).exists():
        issues.append(HealthIssue("Ошибка", "Файл со ссылками не найден", settings.source.local_file))

    if settings.source.mode == "vk_bot":
        if not settings.source.vk_access_token.strip():
            issues.append(HealthIssue("Ошибка", "Для VK-бота не указан access token"))
        if not settings.source.vk_peer_id.strip():
            issues.append(HealthIssue("Ошибка", "Для VK-бота не указан peer_id"))

    return issues


def _find_ffmpeg() -> str | None:
    configured = os.environ.get("FFMPEG_BINARY")
    if configured and Path(configured).is_file():
        return configured

    found = shutil.which("ffmpeg")
    if found:
        return found

    try:
        import imageio_ffmpeg

        bundled = Path(imageio_ffmpeg.get_ffmpeg_exe())
        if bundled.is_file():
            return str(bundled)
    except Exception:
        pass

    candidates = [
        Path("C:/ffmpeg/bin/ffmpeg.exe"),
        Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
        Path("C:/Program Files/Gyan/FFmpeg/bin/ffmpeg.exe"),
    ]
    candidates.extend(Path.home().glob("AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/**/bin/ffmpeg.exe"))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None
