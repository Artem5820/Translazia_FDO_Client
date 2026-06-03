from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(slots=True, frozen=True)
class StreamRoom:
    room: str
    url: str
    pair: str = ""
    time: str = ""
    subject: str = ""
    teacher: str = ""
    group: str = ""
    source: str = ""

    @property
    def label(self) -> str:
        details = [part for part in (self.time, self.subject, self.teacher, self.group) if part]
        if not details:
            return self.room
        return f"{self.room} - {' | '.join(details)}"


def normalize_room(value: str) -> str:
    room = (value or "").strip()
    room = re.sub(r"\s+", "", room)
    room = room.replace("B", "В").replace("b", "В").replace("V", "В").replace("v", "В")
    room = room.replace("_", "-")
    match = re.fullmatch(r"([A-Za-zА-Яа-яЁё])[- ]?(\d{2,4})([A-Za-zА-Яа-яЁё]?)", room)
    if not match:
        return room.upper()
    building = match.group(1).upper()
    number = match.group(2)
    suffix = match.group(3).upper()
    return f"{building}-{number}{suffix}"


def room_sort_key(room: str | None) -> tuple[str, int, int, str]:
    raw = normalize_room(room or "")
    match = re.match(r"^([A-Za-zА-Яа-яЁё])-?(\d{2,4})([A-Za-zА-Яа-яЁё]?)$", raw)
    if not match:
        return ("", 99, 9999, raw)
    building = match.group(1)
    digits = match.group(2)
    suffix = match.group(3)
    floor = int(digits[0]) if digits else 99
    tail = int(digits[1:]) if len(digits) > 1 else 0
    return (building, floor, tail, suffix)
