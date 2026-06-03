from __future__ import annotations

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import sys
import threading

from .config import APP_DIR, AnalysisSettings


VIDEO_VENDOR = APP_DIR / "vendor" / "Module_video_analys"
AUDIO_VENDOR = APP_DIR / "vendor" / "SoundChecker"

VIDEO_STATES_RU = [
    "Преподаватель в кадре",
    "Демонстрация экрана",
    "Преподаватель отсутствует",
    "Аватарка преподавателя",
    "Выключенный микрофон",
    "Черный экран",
    "Зависший кадр",
    "Пустая аудитория",
    "Плохое качество изображения",
    "Окно трансляции не найдено",
]

AUDIO_STATES_RU = [
    "Тишина",
    "Наличие речи",
    "Громкость",
    "Перегруз и искажения",
    "Шум и отношение сигнал/шум",
    "Низкочастотный гул",
    "Высокочастотный шум",
    "Глухой или отфильтрованный звук",
    "Стабильный тон вместо речи",
]


@dataclass(slots=True)
class AnalysisSummary:
    status: str
    message: str
    issues_count: int
    payload: dict[str, Any]


class AnalysisManager:
    def __init__(self, settings: AnalysisSettings) -> None:
        self.settings = settings
        self.executor = ThreadPoolExecutor(max_workers=max(1, int(settings.max_parallel_analyzers)))

    def update_settings(self, settings: AnalysisSettings) -> None:
        if settings.max_parallel_analyzers != self.settings.max_parallel_analyzers:
            self.shutdown()
            self.executor = ThreadPoolExecutor(max_workers=max(1, int(settings.max_parallel_analyzers)))
        self.settings = settings

    def submit_video(
        self,
        room: str,
        video_path: str | Path,
        callback: Callable[[str, str, AnalysisSummary | None, str | None], None],
    ) -> Future:
        settings = self.settings

        def job() -> tuple[AnalysisSummary | None, str | None]:
            try:
                return analyze_stream_fragment(video_path, settings), None
            except Exception as exc:
                return None, str(exc)

        future = self.executor.submit(job)

        def done(done_future: Future) -> None:
            if done_future.cancelled():
                return
            try:
                summary, error = done_future.result()
            except CancelledError:
                return
            callback(room, str(video_path), summary, error)

        future.add_done_callback(done)
        return future

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)


_VIDEO_ANALYZER_LOCK = threading.Lock()
_VIDEO_ANALYZER_CACHE: dict[tuple[float, float, str], Any] = {}


def analyze_video_file(video_path: str | Path, settings: AnalysisSettings) -> AnalysisSummary:
    _ensure_sys_path(VIDEO_VENDOR)
    from vk_video_analyzer import AnalyzerConfig, VideoAnalyzer

    cache_key = (
        float(settings.sample_interval_seconds),
        float(settings.person_confidence),
        settings.device.strip(),
    )
    with _VIDEO_ANALYZER_LOCK:
        analyzer = _VIDEO_ANALYZER_CACHE.get(cache_key)
        if analyzer is None:
            config = AnalyzerConfig(
                sample_interval_sec=float(settings.sample_interval_seconds),
                person_confidence=float(settings.person_confidence),
                device=settings.device.strip() or None,
                save_observations=False,
            )
            analyzer = VideoAnalyzer(config)
            _VIDEO_ANALYZER_CACHE[cache_key] = analyzer

    result = analyzer.analyze(video_path)
    payload = result.to_dict(output_format="alerts")
    payload["диагностика"] = result.to_dict(output_format="full").get("итог", {})
    payload["проверенные_состояния"] = VIDEO_STATES_RU
    return summarize_video_payload(payload)


def analyze_stream_fragment(video_path: str | Path, settings: AnalysisSettings) -> AnalysisSummary:
    video_summary = analyze_video_file(video_path, settings)
    audio_summary: AnalysisSummary | None = None
    audio_error = ""

    if settings.audio_analysis_enabled:
        try:
            audio_summary = analyze_audio_file(video_path)
        except Exception as exc:
            audio_error = str(exc)

    return combine_analysis_summaries(video_summary, audio_summary, audio_error)


def analyze_audio_file(audio_or_video_path: str | Path) -> AnalysisSummary:
    _ensure_sys_path(AUDIO_VENDOR)
    from soundchecker.analyzer import analyze_audio
    from soundchecker.audio import load_audio

    samples, sample_rate = load_audio(audio_or_video_path)
    payload = analyze_audio(samples, sample_rate)
    return summarize_audio_payload(payload)


def summarize_video_payload(payload: dict[str, Any]) -> AnalysisSummary:
    total = payload.get("итог", {})
    issues = payload.get("проблемы", [])
    status = str(total.get("статус", "неизвестно"))
    state = str(total.get("состояние_трансляции", ""))
    main = str(total.get("основное_состояние", ""))
    message = " | ".join(part for part in (status, state, main) if part)
    return AnalysisSummary(status=status, message=message, issues_count=len(issues), payload=payload)


def summarize_audio_payload(payload: dict[str, Any]) -> AnalysisSummary:
    issues = payload.get("issues", [])
    if not isinstance(issues, list):
        issues = []
    status = str(payload.get("status", "unknown"))
    message = str(payload.get("status_message", status))
    return AnalysisSummary(status=status, message=message, issues_count=len(issues), payload=payload)


def combine_analysis_summaries(
    video_summary: AnalysisSummary,
    audio_summary: AnalysisSummary | None = None,
    audio_error: str = "",
) -> AnalysisSummary:
    video_payload = video_summary.payload
    video_problems = _normalized_video_problems(video_payload.get("проблемы", []))
    audio_problems = _audio_problems(audio_summary, audio_error)
    all_problems = [*video_problems, *audio_problems]

    video_total = video_payload.get("итог", {}) if isinstance(video_payload.get("итог", {}), dict) else {}
    primary_state = str(video_total.get("основное_состояние") or "Неизвестно")
    translation_state = str(video_total.get("состояние_трансляции") or video_summary.status)
    status = _combined_status(video_summary, audio_summary, audio_error, all_problems)
    quality = _quality_label(audio_summary, audio_error)

    audio_payload: dict[str, Any]
    if audio_summary is not None:
        audio_payload = audio_summary.payload
    elif audio_error:
        audio_payload = {
            "status": "error",
            "status_message": "Звук не проверен",
            "error": audio_error,
            "issues": [{"code": "audio_not_checked", "severity": "warning", "message": audio_error}],
        }
    else:
        audio_payload = {"status": "disabled", "status_message": "Аудиоанализ выключен", "issues": []}

    payload = {
        "версия": 3,
        "режим_вывода": "комбинированная_проверка",
        "итог": {
            "статус": status,
            "состояние_трансляции": translation_state,
            "основное_состояние": primary_state,
            "количество_проблем": len(all_problems),
            "есть_актуальная_проблема": bool(all_problems),
            "качество_проверки": quality,
            "проверенные_состояния": [*VIDEO_STATES_RU, *AUDIO_STATES_RU],
        },
        "проблемы": all_problems,
        "видео": video_payload,
        "звук": audio_payload,
    }
    message = " | ".join(part for part in (status, translation_state, primary_state, quality) if part)
    return AnalysisSummary(status=status, message=message, issues_count=len(all_problems), payload=payload)


def _normalized_video_problems(problems: Any) -> list[dict[str, Any]]:
    if not isinstance(problems, list):
        return []
    output: list[dict[str, Any]] = []
    for problem in problems:
        if isinstance(problem, dict):
            item = dict(problem)
            item.setdefault("источник", "видео")
            output.append(item)
        else:
            output.append({"источник": "видео", "тип": "Проблема видео", "описание": str(problem)})
    return output


def _audio_problems(audio_summary: AnalysisSummary | None, audio_error: str) -> list[dict[str, Any]]:
    if audio_summary is None:
        if not audio_error:
            return []
        return [
            {
                "источник": "звук",
                "тип": "Звук не проверен",
                "уровень": "предупреждение",
                "описание": audio_error,
                "код": "audio_not_checked",
            }
        ]

    issues = audio_summary.payload.get("issues", [])
    if not isinstance(issues, list):
        return []

    metrics = audio_summary.payload.get("metrics", {})
    output: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            output.append({"источник": "звук", "тип": "Проблема звука", "описание": str(issue)})
            continue
        output.append(
            {
                "источник": "звук",
                "тип": _audio_issue_title(str(issue.get("code", ""))),
                "уровень": _audio_severity_ru(str(issue.get("severity", "warning"))),
                "описание": str(issue.get("message") or issue.get("code") or "Проблема звука"),
                "код": str(issue.get("code", "")),
                "метрики": metrics,
            }
        )
    return output


def _combined_status(
    video_summary: AnalysisSummary,
    audio_summary: AnalysisSummary | None,
    audio_error: str,
    problems: list[dict[str, Any]],
) -> str:
    if any(problem.get("уровень") == "критично" for problem in problems):
        return "обнаружены критические проблемы"
    if problems:
        return "обнаружены проблемы"
    if audio_error:
        return "видео проверено, звук не проверен"
    if audio_summary is None:
        return video_summary.status
    if audio_summary.status == "ok" and video_summary.issues_count == 0:
        return "проблемы не обнаружены"
    return video_summary.status


def _quality_label(audio_summary: AnalysisSummary | None, audio_error: str) -> str:
    if audio_summary is not None:
        return "видео и звук проверены"
    if audio_error:
        return "видео проверено, звук не удалось проверить"
    return "проверено видео"


def _audio_issue_title(code: str) -> str:
    titles = {
        "empty_audio": "Аудиодорожка пустая",
        "too_short": "Слишком короткий аудиофрагмент",
        "no_speech": "Речь не обнаружена",
        "mostly_silence": "Почти полная тишина",
        "low_volume": "Низкая громкость",
        "clipping": "Перегруз или искажения",
        "low_snr": "Шум мешает речи",
        "power_hum": "Низкочастотный гул",
        "high_frequency_noise": "Высокочастотный шум",
        "muffled_or_filtered_audio": "Глухой или отфильтрованный звук",
        "tonal_signal": "Стабильный тон вместо речи",
    }
    return titles.get(code, "Проблема звука")


def _audio_severity_ru(severity: str) -> str:
    if severity == "critical":
        return "критично"
    if severity == "warning":
        return "предупреждение"
    return "информация"


def _ensure_sys_path(path: Path) -> None:
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)
