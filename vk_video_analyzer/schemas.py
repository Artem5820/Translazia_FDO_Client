from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

PROBLEM_MERGE_GAP_SEC = 6.0


SITUATIONS: dict[int, str] = {
    1: "teacher_in_frame",
    2: "screen_share",
    3: "teacher_temporarily_absent",
    4: "teacher_long_absent_early",
    5: "teacher_long_absent_late",
    6: "teacher_avatar_visible",
    7: "teacher_avatar_long_during_lesson",
    8: "teacher_avatar_after_lesson_time",
    9: "muted_microphone",
    10: "black_screen",
    11: "frozen_frame",
    12: "empty_room_without_teacher",
    13: "low_quality_or_blurry",
    14: "window_not_found",
}

SITUATIONS_RU: dict[int, str] = {
    1: "Преподаватель в кадре",
    2: "Демонстрация экрана",
    3: "Преподаватель ненадолго пропал",
    4: "Преподавателя долго нет в первые 5 минут",
    5: "Преподавателя долго нет после первых 5 минут",
    6: "Видна только аватарка преподавателя",
    7: "Аватарка преподавателя долго висит во время занятия",
    8: "Аватарка преподавателя осталась после нормального времени пары",
    9: "Обнаружен выключенный микрофон",
    10: "Черный экран",
    11: "Зависший кадр",
    12: "Пустая аудитория или рабочее место без преподавателя",
    13: "Плохое качество изображения",
    14: "Окно трансляции не найдено",
}

SITUATION_DESCRIPTIONS_RU: dict[int, str] = {
    1: "Преподаватель виден в кадре, трансляция выглядит нормальной.",
    2: "В основной области видна демонстрация экрана.",
    3: "Преподаватель пропал ненадолго, это не похоже на завершение пары.",
    4: "Преподавателя слишком долго нет в начале занятия, возможна проблема.",
    5: "Преподавателя долго нет после первых пяти минут, трансляция может быть уже завершена.",
    6: "Вместо камеры преподавателя видна только аватарка.",
    7: "Аватарка преподавателя долго висит во время занятия, вероятна проблема с камерой или форматом проведения.",
    8: "После нормального времени пары осталась только аватарка преподавателя, трансляция, вероятно, завершена.",
    9: "На трансляции виден выключенный микрофон преподавателя.",
    10: "Основная область трансляции почти полностью черная.",
    11: "Видеопоток долго не меняется и похож на зависший кадр.",
    12: "В кадре пустая аудитория или рабочее место без преподавателя.",
    13: "Изображение слишком темное или размытое для надежного анализа.",
    14: "Окно трансляции не удалось определить.",
}

STATE_TITLES_RU: dict[str, str] = {
    "teacher_present": "Преподаватель в кадре",
    "screen_share": "Демонстрация экрана",
    "teacher_missing": "Преподаватель отсутствует",
    "camera_off_avatar": "Аватарка преподавателя",
    "empty_room": "Пустая аудитория",
    "black_screen": "Черный экран",
    "frozen_frame": "Зависший кадр",
    "low_quality": "Низкое качество изображения",
    "window_not_found": "Окно трансляции не найдено",
    "no_data": "Нет данных",
}

DECISION_TITLES_RU: dict[str, str] = {
    "class_in_progress": "Пара идет нормально",
    "class_in_progress_with_issues": "Пара идет, но есть проблема",
    "possible_problem": "Возможна проблема",
    "technical_issue": "Техническая проблема",
    "likely_finished": "Трансляция, вероятно, завершена",
    "no_data": "Нет данных",
}

FLAG_TITLES_RU: dict[str, str] = {
    "teacher_in_main": "Преподаватель найден в основной области",
    "screen_share": "Обнаружена демонстрация экрана",
    "avatar_visible": "Видна аватарка преподавателя",
    "muted_icon": "Обнаружен значок выключенного микрофона",
    "empty_room": "Похоже на пустую аудиторию или рабочее место",
    "black_screen": "Обнаружен черный экран",
    "frozen_frame": "Обнаружен зависший кадр",
    "low_quality": "Низкое качество изображения",
    "window_not_found": "Окно трансляции не найдено",
    "person_in_tile": "Человек найден в правой плитке",
    "fullscreen_avatar": "Обнаружена полноэкранная аватарка",
}


@dataclass(slots=True)
class FrameObservation:
    timestamp_sec: float
    primary_state: str
    confidence: float
    flags: dict[str, bool]
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class SegmentRecord:
    start_sec: float
    end_sec: float
    duration_sec: float
    primary_state: str
    situation_ids: list[int]
    decision: str
    confidence: float
    flags: dict[str, bool]
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AnalysisResult:
    video: dict[str, Any]
    summary: dict[str, Any]
    segments: list[SegmentRecord]
    observations: list[FrameObservation]

    def to_dict(self, output_format: str = "alerts") -> dict[str, Any]:
        if output_format == "events":
            return self.to_events_dict_ru()
        if output_format == "full":
            return self.to_full_dict_ru()
        return self.to_alerts_dict_ru()

    def to_alerts_dict_ru(self) -> dict[str, Any]:
        raw_problems = [self._segment_to_problem_ru(segment) for segment in self.segments if self._is_problem_segment(segment)]
        problems = self._merge_problem_entries_ru(raw_problems)
        final_decision = str(self.summary.get("final_decision", "no_data"))
        summary_state = str(self.summary.get("summary_primary_state", self.summary.get("final_primary_state", "no_data")))
        has_active_problem = final_decision in {"class_in_progress_with_issues", "possible_problem", "technical_issue"}
        status = self._summary_status_ru(bool(problems), final_decision)

        return {
            "версия": 2,
            "режим_вывода": "только_проблемы",
            "видео": {
                "путь": self.video.get("path"),
                "длительность_сек": self.video.get("duration_sec"),
                "fps": self.video.get("fps"),
                "шаг_анализа_сек": self.video.get("sample_interval_sec"),
            },
            "итог": {
                "статус": status,
                "состояние_трансляции": DECISION_TITLES_RU.get(final_decision, final_decision),
                "основное_состояние": STATE_TITLES_RU.get(summary_state, summary_state),
                "количество_проблем": len(problems),
                "есть_актуальная_проблема": has_active_problem,
                "уверенное_время_занятия_сек": self.summary.get("confident_teaching_sec", 0.0),
                "возможное_время_занятия_сек": self.summary.get("possible_teaching_sec", 0.0),
            },
            "проблемы": problems,
        }

    @classmethod
    def _merge_problem_entries_ru(cls, problems: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not problems:
            return []

        merged: list[dict[str, Any]] = [dict(problems[0])]
        for current in problems[1:]:
            previous = merged[-1]
            gap_sec = float(current["начало_сек"]) - float(previous["конец_сек"])
            if cls._can_merge_problem_entries_ru(previous, current, gap_sec):
                previous["конец_сек"] = current["конец_сек"]
                previous["длительность_сек"] = round(
                    float(previous["конец_сек"]) - float(previous["начало_сек"]),
                    3,
                )
                previous["ситуации"] = cls._merge_string_lists_ru(previous["ситуации"], current["ситуации"])
                previous["признаки"] = cls._merge_string_lists_ru(previous["признаки"], current["признаки"])
                previous["уверенность"] = round(
                    max(float(previous["уверенность"]), float(current["уверенность"])),
                    3,
                )
                if current.get("описание") and current["описание"] not in previous.get("описание", ""):
                    previous["описание"] = " ".join(
                        part for part in [previous.get("описание", ""), current["описание"]] if part
                    )
                continue

            merged.append(dict(current))

        return merged

    @staticmethod
    def _can_merge_problem_entries_ru(left: dict[str, Any], right: dict[str, Any], gap_sec: float) -> bool:
        if gap_sec < 0 or gap_sec > PROBLEM_MERGE_GAP_SEC:
            return False

        comparable_keys = ("тип", "уровень", "состояние", "решение")
        return all(left.get(key) == right.get(key) for key in comparable_keys)

    @staticmethod
    def _merge_string_lists_ru(left: list[str], right: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for item in [*left, *right]:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

    def to_events_dict_ru(self) -> dict[str, Any]:
        final_decision = str(self.summary.get("final_decision", "no_data"))
        summary_state = str(self.summary.get("summary_primary_state", self.summary.get("final_primary_state", "no_data")))
        final_state = str(self.summary.get("final_primary_state", "no_data"))
        has_problems = any(self._is_problem_segment(segment) for segment in self.segments)
        events = self._build_problem_events_ru()
        return {
            "версия": 2,
            "режим_вывода": "события",
            "видео": {
                "путь": self.video.get("path"),
                "длительность_сек": self.video.get("duration_sec"),
                "fps": self.video.get("fps"),
                "шаг_анализа_сек": self.video.get("sample_interval_sec"),
            },
            "итог": {
                "статус": self._summary_status_ru(has_problems, final_decision),
                "состояние_трансляции": DECISION_TITLES_RU.get(final_decision, final_decision),
                "основное_состояние": STATE_TITLES_RU.get(summary_state, summary_state),
                "количество_событий": len(events),
                "есть_актуальная_проблема": final_decision in {"class_in_progress_with_issues", "possible_problem", "technical_issue"},
            },
            "события": events,
        }

    def to_full_dict_ru(self) -> dict[str, Any]:
        final_decision = str(self.summary.get("final_decision", "no_data"))
        summary_state = str(self.summary.get("summary_primary_state", self.summary.get("final_primary_state", "no_data")))
        return {
            "версия": 2,
            "режим_вывода": "полный",
            "видео": {
                "путь": self.video.get("path"),
                "длительность_сек": self.video.get("duration_sec"),
                "fps": self.video.get("fps"),
                "количество_кадров": self.video.get("frame_count"),
                "шаг_анализа_сек": self.video.get("sample_interval_sec"),
            },
            "итог": {
                "основное_состояние": STATE_TITLES_RU.get(summary_state, summary_state),
                "состояние_трансляции": DECISION_TITLES_RU.get(final_decision, final_decision),
                "количество_сэмплов": self.summary.get("sample_count", 0),
                "уверенное_время_занятия_сек": self.summary.get("confident_teaching_sec", 0.0),
                "возможное_время_занятия_сек": self.summary.get("possible_teaching_sec", 0.0),
            },
            "сегменты": [self._segment_to_full_ru(segment) for segment in self.segments],
            "наблюдения": [self._observation_to_ru(observation) for observation in self.observations],
        }

    @staticmethod
    def _is_problem_segment(segment: SegmentRecord) -> bool:
        return segment.decision in {"class_in_progress_with_issues", "possible_problem", "technical_issue"}

    @staticmethod
    def _severity_ru(decision: str) -> str:
        if decision == "technical_issue":
            return "критично"
        if decision == "class_in_progress_with_issues":
            return "ошибка"
        if decision == "possible_problem":
            return "предупреждение"
        return "информация"

    @staticmethod
    def _summary_status_ru(has_problems: bool, final_decision: str) -> str:
        if not has_problems:
            if final_decision == "likely_finished":
                return "трансляция, вероятно, завершена"
            return "проблемы не обнаружены"

        if final_decision in {"class_in_progress", "likely_finished"}:
            return "во время трансляции были проблемы"

        return "обнаружены проблемы"

    def _segment_to_problem_ru(self, segment: SegmentRecord) -> dict[str, Any]:
        situation_titles = [SITUATIONS_RU.get(situation_id, str(situation_id)) for situation_id in segment.situation_ids]
        descriptions = [SITUATION_DESCRIPTIONS_RU.get(situation_id, "") for situation_id in segment.situation_ids]
        return {
            "тип": situation_titles[0] if situation_titles else STATE_TITLES_RU.get(segment.primary_state, segment.primary_state),
            "уровень": self._severity_ru(segment.decision),
            "начало_сек": segment.start_sec,
            "конец_сек": segment.end_sec,
            "длительность_сек": segment.duration_sec,
            "состояние": STATE_TITLES_RU.get(segment.primary_state, segment.primary_state),
            "решение": DECISION_TITLES_RU.get(segment.decision, segment.decision),
            "ситуации": situation_titles,
            "описание": " ".join(item for item in descriptions if item),
            "признаки": self._true_flags_ru(segment.flags),
            "уверенность": segment.confidence,
        }

    def _build_problem_events_ru(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        event_id = 1

        for index, segment in enumerate(self.segments):
            if not self._is_problem_segment(segment):
                continue

            problem_payload = self._segment_to_problem_ru(segment)
            events.append(
                {
                    "ид": event_id,
                    "тип_события": "проблема_обнаружена",
                    "время_сек": segment.start_sec,
                    "состояние": STATE_TITLES_RU.get(segment.primary_state, segment.primary_state),
                    "решение": DECISION_TITLES_RU.get(segment.decision, segment.decision),
                    "проблема": problem_payload,
                }
            )
            event_id += 1

            if index + 1 < len(self.segments) and not self._is_problem_segment(self.segments[index + 1]):
                next_segment = self.segments[index + 1]
                events.append(
                    {
                        "ид": event_id,
                        "тип_события": "проблема_устранена",
                        "время_сек": segment.end_sec,
                        "предыдущая_проблема": problem_payload["тип"],
                        "новое_состояние": STATE_TITLES_RU.get(next_segment.primary_state, next_segment.primary_state),
                        "новое_решение": DECISION_TITLES_RU.get(next_segment.decision, next_segment.decision),
                    }
                )
                event_id += 1

        final_decision = str(self.summary.get("final_decision", "no_data"))
        final_state = str(self.summary.get("final_primary_state", "no_data"))
        events.append(
            {
                "ид": event_id,
                "тип_события": "трансляция_завершена",
                "время_сек": self.video.get("duration_sec"),
                "итоговое_состояние": STATE_TITLES_RU.get(final_state, final_state),
                "итоговое_решение": DECISION_TITLES_RU.get(final_decision, final_decision),
                "есть_актуальная_проблема": final_decision in {"class_in_progress_with_issues", "possible_problem", "technical_issue"},
            }
        )
        return events

    def _segment_to_full_ru(self, segment: SegmentRecord) -> dict[str, Any]:
        return {
            "начало_сек": segment.start_sec,
            "конец_сек": segment.end_sec,
            "длительность_сек": segment.duration_sec,
            "основное_состояние": STATE_TITLES_RU.get(segment.primary_state, segment.primary_state),
            "решение": DECISION_TITLES_RU.get(segment.decision, segment.decision),
            "ситуации": [SITUATIONS_RU.get(situation_id, str(situation_id)) for situation_id in segment.situation_ids],
            "признаки": self._true_flags_ru(segment.flags),
            "уверенность": segment.confidence,
        }

    def _observation_to_ru(self, observation: FrameObservation) -> dict[str, Any]:
        return {
            "время_сек": observation.timestamp_sec,
            "состояние": STATE_TITLES_RU.get(observation.primary_state, observation.primary_state),
            "уверенность": observation.confidence,
            "признаки": self._true_flags_ru(observation.flags),
            "метрики": self._metrics_to_ru(observation.metrics),
        }

    @staticmethod
    def _true_flags_ru(flags: dict[str, bool]) -> list[str]:
        return [FLAG_TITLES_RU.get(key, key) for key, value in flags.items() if value]

    @staticmethod
    def _metrics_to_ru(metrics: dict[str, float]) -> dict[str, float]:
        metric_titles = {
            "teacher_main_area_ratio": "доля_преподавателя_в_основной_области",
            "teacher_tile_area_ratio": "доля_преподавателя_в_плитке",
            "brightness_mean": "средняя_яркость",
            "brightness_std": "разброс_яркости",
            "freeze_streak_sec": "длительность_подозрения_на_зависание_сек",
            "mse_value": "похожесть_по_mse",
            "hist_similarity": "похожесть_по_гистограмме",
            "fullscreen_avatar": "полноэкранная_аватарка",
        }
        return {metric_titles.get(key, key): value for key, value in metrics.items()}
