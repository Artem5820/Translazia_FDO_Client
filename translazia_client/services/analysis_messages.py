from __future__ import annotations

from typing import Any


def short_analysis_message(room: str, summary: Any = None, error: str = "") -> str:
    problem = short_problem(summary, error)
    return f"{room} - {problem}" if room else problem


def short_problem(summary: Any = None, error: str = "") -> str:
    if error:
        return _short_error(error)
    payload = getattr(summary, "payload", {}) if summary is not None else {}
    problems = payload.get("проблемы", []) if isinstance(payload, dict) else []
    if not isinstance(problems, list) or not problems:
        return "норма"

    labels = [_problem_label(problem) for problem in problems if isinstance(problem, dict)]
    labels = [label for label in labels if label]
    if not labels:
        return "проблема"

    ordered = _dedupe(labels)
    if len(ordered) == 1:
        return ordered[0]
    return ", ".join(ordered[:2])


def compact_analysis_details(summary: Any = None, error: str = "", video_path: str = "") -> str:
    if error:
        return _short_error(error)

    payload = getattr(summary, "payload", {}) if summary is not None else {}
    problems = payload.get("проблемы", []) if isinstance(payload, dict) else []
    if not isinstance(problems, list) or not problems:
        return getattr(summary, "message", "Проблем не найдено") if summary is not None else "Проблем не найдено"

    lines: list[str] = []
    for problem in problems[:4]:
        if not isinstance(problem, dict):
            continue
        label = _problem_label(problem)
        if not label:
            continue
        duration = problem.get("длительность_сек")
        if isinstance(duration, (int, float)) and duration > 0:
            lines.append(f"{label}; {duration:g} сек.")
        else:
            lines.append(label)
    if video_path:
        lines.append(f"Фрагмент: {video_path}")
    return "\n".join(_dedupe(lines))


def _problem_label(problem: dict[str, Any]) -> str:
    source = str(problem.get("источник", "")).lower()
    code = str(problem.get("код", "")).lower()
    text = " ".join(
        str(problem.get(key, ""))
        for key in ("тип", "описание", "решение", "состояние")
    ).lower()

    if source == "звук" or code in AUDIO_CODES:
        return _audio_label(code, text)
    return _video_label(text)


AUDIO_CODES = {
    "empty_audio",
    "audio_not_checked",
    "too_short",
    "no_speech",
    "mostly_silence",
    "low_volume",
    "clipping",
    "low_snr",
    "power_hum",
    "high_frequency_noise",
    "muffled_or_filtered_audio",
    "tonal_signal",
}


def _audio_label(code: str, text: str) -> str:
    if code in {"no_speech", "mostly_silence", "empty_audio"} or "тишин" in text or "речь не обнаруж" in text:
        return "нет звука"
    if code == "audio_not_checked" or "не провер" in text or "ffmpeg" in text:
        return "звук не проверен"
    if code == "low_volume" or "низкая громкость" in text:
        return "тихий звук"
    if code in {"low_snr", "power_hum", "high_frequency_noise"} or "шум" in text or "гул" in text:
        return "шум в звуке"
    if code == "clipping" or "перегруз" in text:
        return "звук искажен"
    return "проблема звука"


def _video_label(text: str) -> str:
    if "черн" in text:
        return "нет видео"
    if "завис" in text:
        return "зависло видео"
    if "пустая аудитория" in text or "рабочее место без преподавателя" in text:
        return "пустая аудитория"
    if "преподавател" in text and ("нет" in text or "отсутств" in text or "пропал" in text):
        return "нет преподавателя"
    if "аватар" in text:
        return "камера выключена"
    if "плохое качество" in text or "низкое качество" in text or "размы" in text:
        return "плохое видео"
    if "окно трансляции не найдено" in text:
        return "окно не найдено"
    return "проблема видео"


def _short_error(error: str) -> str:
    lowered = error.lower()
    if "ffmpeg" in lowered or "audio" in lowered or "аудио" in lowered:
        return "звук не проверен"
    if "frame" in lowered or "кадр" in lowered or "video" in lowered:
        return "нет видео"
    return "ошибка проверки"


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
