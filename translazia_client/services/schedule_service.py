from __future__ import annotations

from pathlib import Path

from ..config import SourceSettings
from ..models import StreamRoom, room_sort_key
from ..streams import load_streams_from_file
from ..vk_bot import VkBotClient


def load_streams(settings: SourceSettings) -> tuple[list[StreamRoom], str]:
    if settings.mode == "vk_bot":
        result = VkBotClient(settings).fetch_streams()
        return sorted(result.streams, key=lambda item: room_sort_key(item.room)), "VK-бот"
    if settings.mode == "vk_web":
        raise RuntimeError(
            "VK Web-сессия подключена для сохранения входа. "
            "Откройте окно VK входа, авторизуйтесь и нажмите кнопку 5-Онлайн трансляции; "
            "автоматическое чтение ответа бота будет добавлено следующим шагом."
        )

    streams = load_streams_from_file(settings.local_file)
    return streams, Path(settings.local_file).name
