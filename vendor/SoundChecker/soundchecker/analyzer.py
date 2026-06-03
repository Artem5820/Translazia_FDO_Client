from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


EPSILON = 1e-12
MIN_DBFS = -120.0


@dataclass(frozen=True)
class AnalyzerConfig:
    silence_dbfs: float = -45.0
    min_speech_ratio: float = 0.03
    max_silence_ratio: float = 0.85
    low_level_dbfs: float = -35.0
    clipping_ratio: float = 0.003
    min_snr_db: float = 12.0
    max_hum_ratio: float = 0.12
    max_high_freq_ratio: float = 0.28
    min_speech_band_ratio: float = 0.35
    max_tone_dominance_ratio: float = 0.45
    frame_ms: int = 30


def analyze_audio(samples: np.ndarray, sample_rate: int, config: AnalyzerConfig | None = None) -> dict[str, Any]:
    cfg = config or AnalyzerConfig()
    samples = np.asarray(samples, dtype=np.float32)

    if samples.size == 0:
        return {
            "status": "error",
            "status_message": "Ошибка анализа",
            "issues": [{"code": "empty_audio", "severity": "critical", "message": "Аудиодорожка пустая"}],
            "metrics": {"duration_sec": 0.0},
        }

    duration_sec = float(samples.size / sample_rate)
    rms = float(np.sqrt(np.mean(np.square(samples)) + EPSILON))
    peak = float(np.max(np.abs(samples)))
    rms_dbfs = _to_dbfs(rms)
    peak_dbfs = _to_dbfs(peak)
    clipping_ratio = float(np.mean(np.abs(samples) >= 0.98))

    frame_rms = _frame_rms(samples, sample_rate, cfg.frame_ms)
    frame_dbfs = np.array([_to_dbfs(value) for value in frame_rms], dtype=np.float32)
    silence_ratio = float(np.mean(frame_dbfs < cfg.silence_dbfs)) if frame_dbfs.size else 1.0
    noise_floor_dbfs = float(np.percentile(frame_dbfs, 10)) if frame_dbfs.size else -120.0
    active_level_dbfs = float(np.percentile(frame_dbfs, 90)) if frame_dbfs.size else -120.0
    snr_db = float(active_level_dbfs - noise_floor_dbfs)

    vad = _try_silero_vad(samples, sample_rate)
    speech_ratio = vad["speech_ratio"] if vad["available"] else max(0.0, 1.0 - silence_ratio)
    spectral = _spectral_metrics(samples, sample_rate)

    issues = _classify_issues(
        cfg=cfg,
        duration_sec=duration_sec,
        rms_dbfs=rms_dbfs,
        silence_ratio=silence_ratio,
        speech_ratio=speech_ratio,
        clipping_ratio=clipping_ratio,
        snr_db=snr_db,
        spectral=spectral,
    )

    status = _overall_status(issues)
    return {
        "status": status,
        "status_message": _status_message(status),
        "issues": issues,
        "metrics": {
            "duration_sec": round(duration_sec, 3),
            "sample_rate_hz": sample_rate,
            "rms_dbfs": round(rms_dbfs, 2),
            "peak_dbfs": round(peak_dbfs, 2),
            "silence_ratio": round(silence_ratio, 4),
            "speech_ratio": round(float(speech_ratio), 4),
            "clipping_ratio": round(clipping_ratio, 6),
            "noise_floor_dbfs": round(noise_floor_dbfs, 2),
            "active_level_dbfs": round(active_level_dbfs, 2),
            "snr_estimate_db": round(snr_db, 2),
            "vad_backend": vad["backend"],
            "spectral": spectral,
        },
        "thresholds": {
            "silence_dbfs": cfg.silence_dbfs,
            "min_speech_ratio": cfg.min_speech_ratio,
            "max_silence_ratio": cfg.max_silence_ratio,
            "low_level_dbfs": cfg.low_level_dbfs,
            "clipping_ratio": cfg.clipping_ratio,
            "min_snr_db": cfg.min_snr_db,
            "max_hum_ratio": cfg.max_hum_ratio,
            "max_high_freq_ratio": cfg.max_high_freq_ratio,
            "min_speech_band_ratio": cfg.min_speech_band_ratio,
            "max_tone_dominance_ratio": cfg.max_tone_dominance_ratio,
        },
    }


def _classify_issues(
    *,
    cfg: AnalyzerConfig,
    duration_sec: float,
    rms_dbfs: float,
    silence_ratio: float,
    speech_ratio: float,
    clipping_ratio: float,
    snr_db: float,
    spectral: dict[str, float],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    if duration_sec < 1.0:
        issues.append({"code": "too_short", "severity": "warning", "message": "Фрагмент короче 1 секунды"})
    if speech_ratio < cfg.min_speech_ratio:
        issues.append({"code": "no_speech", "severity": "critical", "message": "Речь не обнаружена"})
    if silence_ratio > cfg.max_silence_ratio:
        issues.append({"code": "mostly_silence", "severity": "critical", "message": "Аудио почти полностью состоит из тишины"})
    if rms_dbfs < cfg.low_level_dbfs:
        issues.append({"code": "low_volume", "severity": "warning", "message": "Слишком низкая громкость"})
    if clipping_ratio > cfg.clipping_ratio:
        issues.append({"code": "clipping", "severity": "warning", "message": "В аудио есть перегруз или искажения"})
    if snr_db < cfg.min_snr_db and speech_ratio >= cfg.min_speech_ratio:
        issues.append({"code": "low_snr", "severity": "warning", "message": "Речь может плохо различаться из-за шума"})
    if spectral["hum_ratio"] > cfg.max_hum_ratio:
        issues.append({"code": "power_hum", "severity": "warning", "message": "Обнаружен сильный низкочастотный гул"})
    if spectral["high_freq_ratio"] > cfg.max_high_freq_ratio and speech_ratio >= cfg.min_speech_ratio:
        issues.append({"code": "high_frequency_noise", "severity": "warning", "message": "Слишком много высокочастотного шума"})
    if spectral["speech_band_ratio"] < cfg.min_speech_band_ratio and speech_ratio >= cfg.min_speech_ratio:
        issues.append({"code": "muffled_or_filtered_audio", "severity": "warning", "message": "Звук похож на глухой или отфильтрованный"})
    if spectral["tone_dominance_ratio"] > cfg.max_tone_dominance_ratio and speech_ratio < 0.2:
        issues.append({"code": "tonal_signal", "severity": "warning", "message": "Аудио похоже на стабильный тон, а не на речь"})

    return issues


def _overall_status(issues: list[dict[str, str]]) -> str:
    if any(issue["severity"] == "critical" for issue in issues):
        return "critical"
    if issues:
        return "warning"
    return "ok"


def _status_message(status: str) -> str:
    messages = {
        "ok": "Проблем со звуком не обнаружено",
        "warning": "Обнаружены возможные проблемы со звуком",
        "critical": "Обнаружена критическая проблема со звуком",
        "error": "Ошибка анализа",
    }
    return messages.get(status, "Неизвестный статус")


def _frame_rms(samples: np.ndarray, sample_rate: int, frame_ms: int) -> np.ndarray:
    frame_size = max(1, int(sample_rate * frame_ms / 1000))
    frame_count = samples.size // frame_size
    if frame_count == 0:
        return np.array([np.sqrt(np.mean(np.square(samples)) + EPSILON)], dtype=np.float32)

    framed = samples[: frame_count * frame_size].reshape(frame_count, frame_size)
    return np.sqrt(np.mean(np.square(framed), axis=1) + EPSILON)


def _spectral_metrics(samples: np.ndarray, sample_rate: int) -> dict[str, float]:
    magnitude, frequencies = _stft_magnitude(samples, sample_rate)
    if magnitude.size == 0:
        return {
            "centroid_hz": 0.0,
            "bandwidth_hz": 0.0,
            "low_freq_ratio": 0.0,
            "speech_band_ratio": 0.0,
            "high_freq_ratio": 0.0,
            "hum_ratio": 0.0,
            "tone_dominance_ratio": 0.0,
            "spectral_flatness": 0.0,
        }

    power_by_freq = np.mean(np.square(magnitude), axis=1)
    total_power = float(np.sum(power_by_freq) + EPSILON)
    centroid = float(np.sum(frequencies * power_by_freq) / total_power)
    bandwidth = float(np.sqrt(np.sum(np.square(frequencies - centroid) * power_by_freq) / total_power))

    low_ratio = _band_ratio(power_by_freq, frequencies, 20, 300)
    speech_ratio = _band_ratio(power_by_freq, frequencies, 300, 3400)
    high_ratio = _band_ratio(power_by_freq, frequencies, 4000, sample_rate / 2)
    hum_ratio = _band_ratio(power_by_freq, frequencies, 45, 65) + _band_ratio(power_by_freq, frequencies, 95, 125)
    tone_dominance = float(np.max(power_by_freq) / total_power)

    frame_power = np.square(magnitude) + EPSILON
    flatness = float(np.mean(np.exp(np.mean(np.log(frame_power), axis=0)) / np.mean(frame_power, axis=0)))

    return {
        "centroid_hz": round(centroid, 2),
        "bandwidth_hz": round(bandwidth, 2),
        "low_freq_ratio": round(low_ratio, 4),
        "speech_band_ratio": round(speech_ratio, 4),
        "high_freq_ratio": round(high_ratio, 4),
        "hum_ratio": round(hum_ratio, 4),
        "tone_dominance_ratio": round(tone_dominance, 4),
        "spectral_flatness": round(flatness, 4),
    }


def _stft_magnitude(samples: np.ndarray, sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
    window_size = 1024
    hop_size = 512
    if samples.size < window_size:
        padded = np.zeros(window_size, dtype=np.float32)
        padded[: samples.size] = samples
        frames = padded.reshape(1, window_size)
    else:
        frame_count = 1 + (samples.size - window_size) // hop_size
        indexes = np.arange(window_size)[None, :] + hop_size * np.arange(frame_count)[:, None]
        frames = samples[indexes]

    window = np.hanning(window_size).astype(np.float32)
    spectrum = np.fft.rfft(frames * window, axis=1)
    magnitude = np.abs(spectrum).T
    frequencies = np.fft.rfftfreq(window_size, d=1 / sample_rate)
    return magnitude, frequencies


def _band_ratio(power_by_freq: np.ndarray, frequencies: np.ndarray, low_hz: float, high_hz: float) -> float:
    mask = (frequencies >= low_hz) & (frequencies < high_hz)
    return float(np.sum(power_by_freq[mask]) / (np.sum(power_by_freq) + EPSILON))


def _to_dbfs(value: float) -> float:
    return max(MIN_DBFS, float(20.0 * np.log10(max(value, EPSILON))))


def _try_silero_vad(samples: np.ndarray, sample_rate: int) -> dict[str, Any]:
    try:
        from silero_vad import get_speech_timestamps, load_silero_vad
    except Exception:
        return {"available": False, "backend": "energy_fallback", "speech_ratio": None}

    try:
        model = load_silero_vad()
        timestamps = get_speech_timestamps(samples, model, sampling_rate=sample_rate)
    except Exception:
        return {"available": False, "backend": "energy_fallback", "speech_ratio": None}

    speech_samples = sum(segment["end"] - segment["start"] for segment in timestamps)
    return {
        "available": True,
        "backend": "silero_vad",
        "speech_ratio": float(speech_samples / max(1, samples.size)),
    }
