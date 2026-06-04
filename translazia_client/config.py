from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, TypeVar
import json
import sys


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data"
CONFIG_PATH = DATA_DIR / "settings.json"


@dataclass(slots=True)
class SourceSettings:
    mode: str = "file"
    local_file: str = str(DATA_DIR / "streams_seed.txt")
    vk_bot_url: str = "https://vk.com/im/convo/-236401821?entrypoint=list_all"
    vk_web_command: str = "5-Онлайн трансляции"
    vk_access_token: str = ""
    vk_peer_id: str = ""
    vk_command: str = "Онлайн трансляции"
    vk_api_version: str = "5.199"
    vk_poll_timeout_sec: int = 30


@dataclass(slots=True)
class LaunchSettings:
    launch_time_msk: str = "17:00"
    remind_minutes_before: int = 15
    auto_launch_at_time: bool = False


@dataclass(slots=True)
class AnalysisSettings:
    enabled: bool = True
    interval_minutes: int = 5
    duration_seconds: int = 30
    capture_fps: float = 1.0
    sample_interval_seconds: float = 2.0
    person_confidence: float = 0.25
    device: str = ""
    max_parallel_analyzers: int = 1
    output_dir: str = str(DATA_DIR / "captures")
    keep_video_fragments: bool = True
    audio_analysis_enabled: bool = True


@dataclass(slots=True)
class AppSettings:
    source: SourceSettings = field(default_factory=SourceSettings)
    launch: LaunchSettings = field(default_factory=LaunchSettings)
    analysis: AnalysisSettings = field(default_factory=AnalysisSettings)


T = TypeVar("T")


def load_settings(path: str | Path = CONFIG_PATH) -> AppSettings:
    settings_path = Path(path)
    if not settings_path.exists():
        settings = AppSettings()
        save_settings(settings, settings_path)
        return settings

    try:
        raw = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return AppSettings()

    return AppSettings(
        source=_merge_dataclass(SourceSettings, raw.get("source", {})),
        launch=_merge_dataclass(LaunchSettings, raw.get("launch", {})),
        analysis=_merge_dataclass(AnalysisSettings, raw.get("analysis", {})),
    )


def save_settings(settings: AppSettings, path: str | Path = CONFIG_PATH) -> None:
    settings_path = Path(path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _to_plain(settings)
    settings_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _merge_dataclass(cls: type[T], data: dict[str, Any]) -> T:
    default = cls()
    values = asdict(default)
    if isinstance(data, dict):
        for key in values.keys():
            if key in data:
                values[key] = data[key]
    return cls(**values)


def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _to_plain(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    return value
