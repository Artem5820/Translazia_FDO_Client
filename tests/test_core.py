from __future__ import annotations

from datetime import date
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from translazia_client.analysis import AnalysisSummary, combine_analysis_summaries, summarize_audio_payload
from translazia_client.layout import ScreenRect, compute_window_placements
from translazia_client.controllers.main_controller import _screens_with_notification_strip
from translazia_client.resources import APP_ICON_PATH, LOGO_PATH
from translazia_client.config import SourceSettings
from translazia_client.services.results_cleanup import cleanup_results_folder
from translazia_client.services.analysis_messages import compact_analysis_details, short_analysis_message
from translazia_client.services.vk_auth_service import is_vk_session_cookie
from translazia_client.services.time_service import moscow_timezone_name, now_moscow, parse_hhmm
from translazia_client.services.vk_web_schedule import _extract_time, parse_vk_web_schedule
from translazia_client.streams import load_streams_from_file, parse_streams_text


class CoreTests(unittest.TestCase):
    def test_parse_room_url_pairs(self) -> None:
        text = """В-506:
https://vk.com/call/join/abc
В-503А: https://vk.com/call/join/def
"""
        streams = parse_streams_text(text)
        self.assertEqual([stream.room for stream in streams], ["В-503А", "В-506"])
        self.assertTrue(streams[0].url.endswith("/def"))


    def test_layout_uses_two_screens_evenly(self) -> None:
        screens = [ScreenRect(0, 0, 1920, 1080), ScreenRect(1920, 0, 1920, 1080)]
        placements = compute_window_placements(screens, 12)
        self.assertEqual(len(placements), 12)
        self.assertEqual(sum(1 for placement in placements if placement.screen_index == 0), 6)
        self.assertEqual(sum(1 for placement in placements if placement.screen_index == 1), 6)

    def test_layout_adds_notification_window_place(self) -> None:
        screens = [ScreenRect(0, 0, 1920, 1080), ScreenRect(1920, 0, 1920, 1080)]
        placements = compute_window_placements(screens, 13)
        self.assertEqual(len(placements), 13)

    def test_notification_strip_width_is_240(self) -> None:
        _, notification = _screens_with_notification_strip()
        self.assertEqual(notification.width, 240)

    def test_seed_file_has_twelve_rooms(self) -> None:
        streams = load_streams_from_file("data/streams_seed.txt")
        self.assertEqual(len(streams), 12)

    def test_parse_launch_time(self) -> None:
        self.assertEqual(parse_hhmm("17:00"), (17, 0))
        self.assertIsNone(parse_hhmm("25:00"))
        self.assertIsNone(parse_hhmm("bad"))

    def test_now_moscow_timezone(self) -> None:
        self.assertIsNotNone(now_moscow().tzinfo)
        self.assertIn(moscow_timezone_name(), {"Europe/Moscow", "MSK"})

    def test_brand_assets_exist(self) -> None:
        self.assertTrue(LOGO_PATH.is_file())
        self.assertTrue(APP_ICON_PATH.is_file())

    def test_cleanup_results_folder_removes_contents(self) -> None:
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "result.json").write_text("{}", encoding="utf-8")
            nested = folder / "nested"
            nested.mkdir()
            (nested / "fragment.mp4").write_text("x", encoding="utf-8")
            removed = cleanup_results_folder(folder)
            self.assertEqual(removed, 2)
            self.assertEqual(list(folder.iterdir()), [])

    def test_vk_web_settings_defaults(self) -> None:
        settings = SourceSettings()
        self.assertIn("vk.com/im/convo/-236401821", settings.vk_bot_url)
        self.assertEqual(settings.vk_web_command, "5-Онлайн трансляции")

    def test_vk_session_cookie_detection(self) -> None:
        self.assertTrue(is_vk_session_cookie("remixsid", ".vk.com"))
        self.assertTrue(is_vk_session_cookie("remixstlid", "login.vk.com"))
        self.assertFalse(is_vk_session_cookie("remixsid", "example.com"))

    def test_vk_web_schedule_parser_merges_seed_links(self) -> None:
        settings = SourceSettings()
        text = """ВКонтакте Совершён вход в ваш аккаунт
V505_Control
🎥 Онлайн трансляции — Сегодня
📅 01.06.2026 — 01.06.2026
🔢 Аудиторий: 4

📅 Понедельник, 01.06.2026

1. 🏫 В200 — пары 1,2
⏱18:00-19:25, 19:40-21:05
Теплогенерирующие установки
лекция | практика
Усадский Д.Г.
ТГВ-2024

2. 🏫 В202 — пары 1,2
⏱18:00-19:25, 19:40-21:05
Проектирование конструкций объектов нефтегазовой отрасли
лекция | консультация
Савина О.В.
СЭНС-23

3. 🏫 В502 — пары 1,2
⏱18:00-19:25, 19:40-21:05
Технико-экономическое обоснование в строительстве и ЖКХ
практика
Соловьева А.С.
ЭМ-1в-24

4. 🏫 В503А — пары 1,2
⏱18:00-19:25, 19:40-21:05
Строительная механика
практика
Рекунов С.С.
ПГС-24
Сегодня
Завтра
"""
        streams = parse_vk_web_schedule(text, settings, date(2026, 6, 1))
        self.assertEqual(len(streams), 4)
        self.assertEqual([stream.room for stream in streams], ["В-200", "В-202", "В-502", "В-503А"])
        self.assertEqual(streams[0].time, "18:00-21:05")
        self.assertIn("Теплогенерирующие", streams[0].subject)
        self.assertTrue(streams[0].url.startswith("https://vk.com/call/join/"))

    def test_vk_web_schedule_time_uses_pair_numbers_when_first_range_is_missing(self) -> None:
        self.assertEqual(_extract_time(["B200 - pairs 1,2", "19:40-21:05"]), "18:00-21:05")

    def test_vk_web_schedule_ignores_stale_today_message_by_date(self) -> None:
        settings = SourceSettings()
        text = """V505_Control
🎥 Онлайн трансляции — Сегодня
📅 01.06.2026 — 01.06.2026
🔢 Аудиторий: 1

1. 🏫 В200 — пары 1,2
⏱18:00-19:25, 19:40-21:05
Теплогенерирующие установки
лекция | практика
Усадский Д.Г.
ТГВ-2024
"""

        streams = parse_vk_web_schedule(text, settings, date(2026, 6, 2))

        self.assertEqual(streams, [])

    def test_vk_web_schedule_ignores_group_chat_call_snippet(self) -> None:
        settings = SourceSettings()
        text = """V505_Control
Мессенджер
В-200
Стас И: Стас Иванов: 13м | В-206
https://vk.com/call/join/example
"""

        streams = parse_vk_web_schedule(text, settings, date(2026, 6, 2))

        self.assertEqual(streams, [])

    def test_combined_analysis_merges_video_and_audio_issues(self) -> None:
        video = AnalysisSummary(
            status="обнаружены проблемы",
            message="Черный экран",
            issues_count=1,
            payload={
                "итог": {
                    "состояние_трансляции": "Техническая проблема",
                    "основное_состояние": "Черный экран",
                },
                "проблемы": [{"тип": "Черный экран", "уровень": "критично", "описание": "Экран черный"}],
            },
        )
        audio = summarize_audio_payload(
            {
                "status": "critical",
                "status_message": "Обнаружена критическая проблема со звуком",
                "issues": [{"code": "mostly_silence", "severity": "critical", "message": "Аудио почти полностью состоит из тишины"}],
                "metrics": {"silence_ratio": 0.95, "speech_ratio": 0.0},
            }
        )

        summary = combine_analysis_summaries(video, audio)

        self.assertEqual(summary.issues_count, 2)
        self.assertEqual(summary.status, "обнаружены критические проблемы")
        self.assertEqual(summary.payload["итог"]["качество_проверки"], "видео и звук проверены")
        self.assertEqual(summary.payload["проблемы"][0]["источник"], "видео")
        self.assertEqual(summary.payload["проблемы"][1]["источник"], "звук")

    def test_combined_analysis_reports_audio_check_error(self) -> None:
        video = AnalysisSummary(
            status="проблемы не обнаружены",
            message="Пара идет нормально",
            issues_count=0,
            payload={
                "итог": {
                    "состояние_трансляции": "Пара идет нормально",
                    "основное_состояние": "Преподаватель в кадре",
                },
                "проблемы": [],
            },
        )

        summary = combine_analysis_summaries(video, audio_error="Decoded audio stream is empty")

        self.assertEqual(summary.issues_count, 1)
        self.assertEqual(summary.payload["проблемы"][0]["код"], "audio_not_checked")
        self.assertIn("звук не удалось проверить", summary.payload["итог"]["качество_проверки"])

    def test_short_analysis_message_for_audio_and_video(self) -> None:
        audio_summary = AnalysisSummary(
            status="обнаружены проблемы",
            message="long",
            issues_count=1,
            payload={"проблемы": [{"источник": "звук", "код": "mostly_silence", "описание": "Аудио почти полностью состоит из тишины"}]},
        )
        video_summary = AnalysisSummary(
            status="обнаружены проблемы",
            message="long",
            issues_count=1,
            payload={"проблемы": [{"источник": "видео", "тип": "Черный экран", "описание": "Основная область черная"}]},
        )

        self.assertEqual(short_analysis_message("В-505", audio_summary), "В-505 - нет звука")
        self.assertEqual(short_analysis_message("В-502", video_summary), "В-502 - нет видео")

    def test_compact_analysis_details_hides_long_ffmpeg_error(self) -> None:
        details = compact_analysis_details(error="ffmpeg could not decode audio: Output file does not contain any stream")

        self.assertEqual(details, "звук не проверен")
