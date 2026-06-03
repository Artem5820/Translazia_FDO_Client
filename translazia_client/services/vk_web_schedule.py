from __future__ import annotations

from datetime import date
from pathlib import Path
import re

from ..config import SourceSettings
from ..models import StreamRoom, normalize_room, room_sort_key
from ..streams import load_streams_from_file


SCHEDULE_ROOM_RE = re.compile(r"(?:^|\s)([A-Za-zА-Яа-яЁё][-\s]?\d{2,4}\s*[A-Za-zА-Яа-яЁё]?)(?=\s|[-–—]|$)", re.IGNORECASE)
TIME_RANGE_RE = re.compile(r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}")
TEACHER_RE = re.compile(r"^\w[\w-]+\s+\w\.\w\.$", re.UNICODE)
GROUP_RE = re.compile(r"^\w[\w-]*-\d{2,4}$", re.UNICODE)


def parse_vk_web_schedule(text: str, settings: SourceSettings, target_date: date | None = None) -> list[StreamRoom]:
    url_by_room = _load_room_urls(settings.local_file)
    schedule_text = _extract_today_schedule_text(text)
    if not _looks_like_v505_schedule(schedule_text):
        return []
    schedule_date = _extract_schedule_date(schedule_text)
    if target_date is not None and schedule_date is not None and schedule_date != target_date:
        return []
    blocks = _extract_schedule_blocks(schedule_text)
    expected_count = _extract_expected_count(schedule_text)
    streams: list[StreamRoom] = []
    for block in blocks:
        room_match = SCHEDULE_ROOM_RE.search(block[0])
        if not room_match:
            continue
        room = normalize_room(room_match.group(1))
        url = url_by_room.get(_room_lookup_key(room), "")
        if not url:
            continue
        pair = _extract_pair(block[0])
        time = _extract_time(block)
        teacher = _extract_teacher(block)
        group = _extract_group(block)
        subject = _extract_subject(block)
        streams.append(
            StreamRoom(
                room=room,
                url=url,
                pair=pair,
                time=time,
                subject=subject,
                teacher=teacher,
                group=group,
                source="VK Web: V505_Control",
            )
        )
    result = sorted(_dedupe_by_room(streams), key=lambda item: room_sort_key(item.room))
    if expected_count > 0:
        return result[:expected_count]
    return result


def _extract_today_schedule_text(text: str) -> str:
    lines = text.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if "Онлайн трансляции" in line and ("Сегодня" in line or "Текущая" in line)
    ]
    if not starts:
        return ""
    start = starts[-1]
    for index in range(start - 1, -1, -1):
        line = lines[index].strip()
        if "V505_Control" in line:
            start = index
            break
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index].strip()
        if index > start + 5 and line in {"Сегодня", "Завтра", "Текущая неделя", "Следующая неделя", "Месяц", "Год", "Главное меню"}:
            end = index
            break
    return "\n".join(lines[start:end])


def _looks_like_v505_schedule(text: str) -> bool:
    return (
        "V505_Control" in text
        and "Онлайн трансляции" in text
        and "Аудиторий:" in text
        and bool(re.search(r"\b\d{2}\.\d{2}\.\d{4}\b", text))
    )


def _extract_expected_count(text: str) -> int:
    match = re.search(r"Аудиторий:\s*(\d+)", text, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def _extract_schedule_date(text: str) -> date | None:
    dates: list[date] = []
    for day, month, year in re.findall(r"\b(\d{2})\.(\d{2})\.(\d{4})\b", text):
        try:
            dates.append(date(int(year), int(month), int(day)))
        except ValueError:
            continue
    return dates[0] if dates else None


def _load_room_urls(path: str) -> dict[str, str]:
    try:
        streams = load_streams_from_file(Path(path))
    except Exception:
        return {}
    return {_room_lookup_key(stream.room): stream.url for stream in streams if stream.url}


def _extract_schedule_blocks(text: str) -> list[list[str]]:
    lines = [_clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    blocks: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        if _is_noise(line):
            continue
        is_schedule_start = bool(SCHEDULE_ROOM_RE.search(line)) and ("пар" in line.lower() or "пары" in line.lower())
        if is_schedule_start:
            if current:
                blocks.append(current)
            current = [line]
            continue
        if current:
            if len(current) >= 8:
                blocks.append(current)
                current = []
                continue
            current.append(line)

    if current:
        blocks.append(current)
    return [block for block in blocks if block and SCHEDULE_ROOM_RE.search(block[0])]


def _extract_pair(line: str) -> str:
    line_without_room = SCHEDULE_ROOM_RE.sub(" ", line, count=1)
    match = re.search(r"\b([1-6](?:\s*,\s*[1-6])*)\b", line_without_room)
    return f"пары {match.group(1).strip()}" if match else ""


def _extract_time(block: list[str]) -> str:
    joined = _normalize_time_text(" ".join(block))
    ranges = [
        item.replace(" ", "")
        for item in TIME_RANGE_RE.findall(joined)
    ]
    unique_ranges = list(dict.fromkeys(ranges))
    pair_numbers = _extract_pair_numbers(block[0])
    if 1 in pair_numbers and 2 in pair_numbers:
        if len(unique_ranges) >= 2:
            return f"{unique_ranges[0].split('-', 1)[0]}-{unique_ranges[-1].rsplit('-', 1)[-1]}"
        return "18:00-21:05"
    if pair_numbers == [1]:
        return unique_ranges[0] if unique_ranges else "18:00-19:25"
    if pair_numbers == [2]:
        return unique_ranges[-1] if unique_ranges else "19:40-21:05"
    if not unique_ranges:
        return ""
    first_start = unique_ranges[0].split("-", 1)[0]
    last_end = unique_ranges[-1].rsplit("-", 1)[-1]
    return f"{first_start}-{last_end}"


def _normalize_time_text(text: str) -> str:
    dash_chars = "\u2010\u2011\u2012\u2013\u2014\u2212\uFE58\uFE63\uFF0D"
    translation = str.maketrans({char: "-" for char in dash_chars})
    return text.translate(translation)


def _extract_pair_numbers(line: str) -> list[int]:
    line_without_room = SCHEDULE_ROOM_RE.sub(" ", line, count=1)
    match = re.search(r"\b([1-6](?:\s*,\s*[1-6])*)\b", line_without_room)
    if not match:
        return []
    return [int(item) for item in re.findall(r"[1-6]", match.group(1))]


def _extract_teacher(block: list[str]) -> str:
    for line in block[1:]:
        if TEACHER_RE.match(line):
            return line
    return ""


def _extract_group(block: list[str]) -> str:
    for line in reversed(block[1:]):
        if GROUP_RE.match(line):
            return line
    return ""


def _extract_subject(block: list[str]) -> str:
    parts: list[str] = []
    for line in block[1:]:
        if TIME_RANGE_RE.search(_normalize_time_text(line)) or TEACHER_RE.match(line) or GROUP_RE.match(line):
            continue
        if "сегодня" in line.lower() or "завтра" in line.lower():
            continue
        if _is_ui_or_chat_noise(line):
            continue
        parts.append(line)
    return " ".join(parts[:3]).strip()


def _clean_line(line: str) -> str:
    line = re.sub(r"^[\d.)\s]+", "", line.strip())
    while line and not line[0].isalnum():
        line = line[1:].strip()
    return re.sub(r"\s+", " ", line).strip()


def _is_noise(line: str) -> bool:
    lowered = line.lower()
    noise = {
        "сегодня",
        "завтра",
        "текущая неделя",
        "следующая неделя",
        "месяц",
        "год",
        "главное меню",
        "сообщение",
        "мессенджер",
    }
    return lowered in noise or lowered.startswith("поиск")


def _is_ui_or_chat_noise(line: str) -> bool:
    lowered = line.lower()
    fragments = (
        "вконтакте",
        "совершён вход",
        "совершен вход",
        "пк ф:",
        "звонок",
        "пригласила",
        "присоединилась",
        "сообщение",
        "только непрочитанные",
    )
    return any(fragment in lowered for fragment in fragments)


def _dedupe_by_room(items: list[StreamRoom]) -> list[StreamRoom]:
    seen: set[str] = set()
    result: list[StreamRoom] = []
    for item in items:
        key = _room_lookup_key(item.room)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _room_lookup_key(room: str) -> str:
    key = normalize_room(room).upper()
    match = re.search(r"(\d{2,4})([A-ZА-ЯЁ]*)", key, re.IGNORECASE)
    if not match:
        return key
    return f"{match.group(1)}{_latinize_suffix(match.group(2))}"


def _latinize_suffix(value: str) -> str:
    return value.translate(str.maketrans({"А": "A", "В": "B", "С": "C", "Е": "E", "Н": "H", "К": "K", "М": "M", "О": "O", "Р": "P", "Т": "T", "Х": "X"}))
