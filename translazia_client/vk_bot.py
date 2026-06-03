from __future__ import annotations

from dataclasses import dataclass
import random
import time
from typing import Any

import requests

from .config import SourceSettings
from .models import StreamRoom
from .streams import parse_streams_text


class VkBotError(RuntimeError):
    pass


@dataclass(slots=True)
class VkBotResult:
    streams: list[StreamRoom]
    raw_messages: list[str]


class VkBotClient:
    API_URL = "https://api.vk.com/method"

    def __init__(self, settings: SourceSettings) -> None:
        self.settings = settings

    def fetch_streams(self) -> VkBotResult:
        if not self.settings.vk_access_token.strip():
            raise VkBotError("Не указан VK access token.")
        if not self.settings.vk_peer_id.strip():
            raise VkBotError("Не указан peer_id диалога с ботом.")

        started_at = int(time.time())
        if self.settings.vk_command.strip():
            self._send_command(self.settings.vk_command.strip())

        deadline = time.monotonic() + max(3, int(self.settings.vk_poll_timeout_sec))
        raw_messages: list[str] = []
        streams: list[StreamRoom] = []

        while time.monotonic() < deadline:
            messages = self._get_history()
            raw_messages = [
                str(item.get("text", ""))
                for item in messages
                if int(item.get("date", 0)) >= started_at and str(item.get("text", "")).strip()
            ]

            for text in raw_messages:
                streams.extend(parse_streams_text(text, source="VK bot"))

            if streams:
                return VkBotResult(streams=streams, raw_messages=raw_messages)
            time.sleep(2.0)

        latest_text = "\n\n".join(raw_messages)
        if latest_text:
            streams = parse_streams_text(latest_text, source="VK bot")
        return VkBotResult(streams=streams, raw_messages=raw_messages)

    def _send_command(self, command: str) -> None:
        self._call(
            "messages.send",
            {
                "peer_id": self.settings.vk_peer_id.strip(),
                "message": command,
                "random_id": random.randint(1, 2_147_483_647),
            },
        )

    def _get_history(self) -> list[dict[str, Any]]:
        response = self._call(
            "messages.getHistory",
            {
                "peer_id": self.settings.vk_peer_id.strip(),
                "count": 20,
            },
        )
        items = response.get("items", []) if isinstance(response, dict) else []
        if not isinstance(items, list):
            return []
        return items

    def _call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = {
            **params,
            "access_token": self.settings.vk_access_token.strip(),
            "v": self.settings.vk_api_version.strip() or "5.199",
        }
        try:
            response = requests.post(f"{self.API_URL}/{method}", data=payload, timeout=20)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            raise VkBotError(f"Ошибка подключения к VK API: {exc}") from exc
        except ValueError as exc:
            raise VkBotError("VK API вернул не JSON-ответ.") from exc

        if "error" in data:
            error = data["error"]
            message = error.get("error_msg", "неизвестная ошибка") if isinstance(error, dict) else str(error)
            raise VkBotError(f"VK API: {message}")

        result = data.get("response", {})
        return result if isinstance(result, dict) else {"value": result}
