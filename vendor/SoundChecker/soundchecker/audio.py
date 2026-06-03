from __future__ import annotations

import subprocess
import wave
import os
import shutil
from pathlib import Path

import numpy as np


TARGET_SAMPLE_RATE = 16_000


class AudioLoadError(RuntimeError):
    pass


def load_audio(path: str | Path, sample_rate: int = TARGET_SAMPLE_RATE) -> tuple[np.ndarray, int]:
    """Decode an audio/video file to mono float32 PCM in range [-1.0, 1.0]."""
    file_path = Path(path)
    if not file_path.exists():
        raise AudioLoadError(f"File does not exist: {file_path}")

    try:
        return _load_with_ffmpeg(file_path, sample_rate)
    except AudioLoadError:
        if file_path.suffix.lower() == ".wav":
            return _load_wav(file_path, sample_rate)
        raise


def _load_with_ffmpeg(path: Path, sample_rate: int) -> tuple[np.ndarray, int]:
    ffmpeg = _find_ffmpeg()
    if ffmpeg is None:
        raise AudioLoadError(
            "ffmpeg is not installed or is not available to Python. "
            "Set FFMPEG_BINARY to the full path of ffmpeg.exe or add its bin folder to PATH."
        )

    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "pipe:1",
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True)
    except FileNotFoundError as exc:
        raise AudioLoadError(f"ffmpeg executable was not found: {ffmpeg}") from exc
    except subprocess.CalledProcessError as exc:
        error = exc.stderr.decode("utf-8", errors="replace").strip()
        raise AudioLoadError(f"ffmpeg could not decode audio: {error}") from exc

    if not completed.stdout:
        raise AudioLoadError("Decoded audio stream is empty")

    samples = np.frombuffer(completed.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    return samples, sample_rate


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


def _load_wav(path: Path, sample_rate: int) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        source_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())

    if source_rate != sample_rate:
        raise AudioLoadError(
            f"WAV fallback only supports {sample_rate} Hz files when ffmpeg is unavailable; got {source_rate} Hz"
        )
    if sample_width != 2:
        raise AudioLoadError("WAV fallback only supports 16-bit PCM when ffmpeg is unavailable")

    data = np.frombuffer(frames, dtype=np.int16).astype(np.float32).reshape(-1, channels)
    mono = data.mean(axis=1) / 32768.0
    return mono, source_rate
