from __future__ import annotations

import argparse
import json
import sys

from .analyzer import AnalyzerConfig, analyze_audio
from .audio import AudioLoadError, load_audio
from .spectrogram import save_spectrogram


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze an audio track and print moderation JSON.")
    parser.add_argument("input", help="Path to audio or video file with an audio stream")
    parser.add_argument("--silence-dbfs", type=float, default=AnalyzerConfig.silence_dbfs)
    parser.add_argument("--min-speech-ratio", type=float, default=AnalyzerConfig.min_speech_ratio)
    parser.add_argument("--max-silence-ratio", type=float, default=AnalyzerConfig.max_silence_ratio)
    parser.add_argument("--low-level-dbfs", type=float, default=AnalyzerConfig.low_level_dbfs)
    parser.add_argument("--clipping-ratio", type=float, default=AnalyzerConfig.clipping_ratio)
    parser.add_argument("--min-snr-db", type=float, default=AnalyzerConfig.min_snr_db)
    parser.add_argument("--max-hum-ratio", type=float, default=AnalyzerConfig.max_hum_ratio)
    parser.add_argument("--max-high-freq-ratio", type=float, default=AnalyzerConfig.max_high_freq_ratio)
    parser.add_argument("--min-speech-band-ratio", type=float, default=AnalyzerConfig.min_speech_band_ratio)
    parser.add_argument("--max-tone-dominance-ratio", type=float, default=AnalyzerConfig.max_tone_dominance_ratio)
    parser.add_argument("--spectrogram", help="Optional path to save a spectrogram PNG")
    parser.add_argument("--english-keys", action="store_true", help="Print JSON with internal English field names")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = AnalyzerConfig(
        silence_dbfs=args.silence_dbfs,
        min_speech_ratio=args.min_speech_ratio,
        max_silence_ratio=args.max_silence_ratio,
        low_level_dbfs=args.low_level_dbfs,
        clipping_ratio=args.clipping_ratio,
        min_snr_db=args.min_snr_db,
        max_hum_ratio=args.max_hum_ratio,
        max_high_freq_ratio=args.max_high_freq_ratio,
        min_speech_band_ratio=args.min_speech_band_ratio,
        max_tone_dominance_ratio=args.max_tone_dominance_ratio,
    )

    try:
        samples, sample_rate = load_audio(args.input)
        result = analyze_audio(samples, sample_rate, config)
        if args.spectrogram:
            result["artifacts"] = {"spectrogram": str(save_spectrogram(samples, sample_rate, args.spectrogram))}
    except AudioLoadError as exc:
        result = {
            "status": "error",
            "status_message": "Ошибка загрузки аудио",
            "issues": [{"code": "audio_load_error", "severity": "critical", "message": str(exc)}],
        }
        print(json.dumps(_localize_keys(result) if not args.english_keys else result, ensure_ascii=False, indent=2))
        return 2

    print(json.dumps(_localize_keys(result) if not args.english_keys else result, ensure_ascii=False, indent=2))
    return 0


def _localize_keys(value):
    if isinstance(value, list):
        return [_localize_keys(item) for item in value]
    if not isinstance(value, dict):
        return value

    return {_KEY_TRANSLATIONS.get(key, key): _localize_keys(item) for key, item in value.items()}


_KEY_TRANSLATIONS = {
    "status": "статус",
    "status_message": "сообщение_статуса",
    "issues": "проблемы",
    "code": "код",
    "severity": "важность",
    "message": "сообщение",
    "metrics": "метрики",
    "duration_sec": "длительность_сек",
    "sample_rate_hz": "частота_дискретизации_гц",
    "rms_dbfs": "средняя_громкость_dbfs",
    "peak_dbfs": "пиковая_громкость_dbfs",
    "silence_ratio": "доля_тишины",
    "speech_ratio": "доля_речи",
    "clipping_ratio": "доля_перегруза",
    "noise_floor_dbfs": "уровень_шума_dbfs",
    "active_level_dbfs": "активный_уровень_dbfs",
    "snr_estimate_db": "оценка_snr_db",
    "vad_backend": "модуль_детекции_речи",
    "spectral": "спектральные_метрики",
    "centroid_hz": "спектральный_центр_гц",
    "bandwidth_hz": "ширина_спектра_гц",
    "low_freq_ratio": "доля_низких_частот",
    "speech_band_ratio": "доля_речевой_полосы",
    "high_freq_ratio": "доля_высоких_частот",
    "hum_ratio": "доля_гула",
    "tone_dominance_ratio": "доля_доминирующего_тона",
    "spectral_flatness": "спектральная_плоскостность",
    "thresholds": "пороги",
    "silence_dbfs": "порог_тишины_dbfs",
    "min_speech_ratio": "минимальная_доля_речи",
    "max_silence_ratio": "максимальная_доля_тишины",
    "low_level_dbfs": "порог_низкой_громкости_dbfs",
    "min_snr_db": "минимальный_snr_db",
    "max_hum_ratio": "максимальная_доля_гула",
    "max_high_freq_ratio": "максимальная_доля_высоких_частот",
    "min_speech_band_ratio": "минимальная_доля_речевой_полосы",
    "max_tone_dominance_ratio": "максимальная_доля_доминирующего_тона",
    "artifacts": "артефакты",
    "spectrogram": "спектрограмма",
}
