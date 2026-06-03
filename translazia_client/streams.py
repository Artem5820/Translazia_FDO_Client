from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re

from .models import StreamRoom, normalize_room, room_sort_key


URL_RE = re.compile(r"https?://(?:www\.)?vk\.com/call/join/[^\s<>)\"']+", re.IGNORECASE)
ROOM_RE = re.compile(r"([A-Za-zА-Яа-яЁё])[- ]?(\d{2,4})([A-Za-zА-Яа-яЁё]?)")


def read_text_auto(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_streams_text(text: str, *, source: str = "") -> list[StreamRoom]:
    """Parse room/link pairs from a text file or a VK bot response."""

    rooms: list[StreamRoom] = []
    pending_room = ""

    for original_line in text.splitlines():
        line = original_line.strip()
        if not line:
            continue

        urls = URL_RE.findall(line)
        line_without_urls = URL_RE.sub(" ", line)
        room_from_line = _extract_room(line_without_urls)

        if line.endswith(":") and not urls:
            pending_room = normalize_room(line[:-1])
            continue

        if urls:
            room = normalize_room(room_from_line or pending_room or f"stream-{len(rooms) + 1}")
            for url in urls:
                rooms.append(StreamRoom(room=room, url=url.rstrip(".,;"), source=source))
            pending_room = ""
            continue

        if room_from_line:
            pending_room = normalize_room(room_from_line)

    return dedupe_rooms(rooms)


def load_streams_from_file(path: str | Path) -> list[StreamRoom]:
    return parse_streams_text(read_text_auto(path), source=str(path))


def dedupe_rooms(items: list[StreamRoom]) -> list[StreamRoom]:
    seen: set[tuple[str, str]] = set()
    result: list[StreamRoom] = []
    for item in items:
        normalized = replace(item, room=normalize_room(item.room))
        key = (normalized.room, normalized.url)
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return sorted(result, key=lambda item: room_sort_key(item.room))


def _extract_room(text: str) -> str:
    match = ROOM_RE.search(text)
    if not match:
        return ""
    return "".join(match.groups())
