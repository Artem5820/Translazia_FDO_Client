# Проверка соответствия итогового кода требованиям

## Функциональная проверка

Команды:

```powershell
python -m unittest discover -s tests -v
```

Ожидаемый результат:

```text
OK
```

Также была выполнена smoke-проверка создания контроллера Qt без запуска реальных трансляций:

```text
streams=12 rows=12
```

## Матрица соответствия

| Требование | Реализация | Проверка |
|---|---|---|
| Чтение файла ссылок | `streams.py`, `services/schedule_service.py` | `test_seed_file_has_twelve_rooms` |
| 12 аудиторий из seed-файла | `data/streams_seed.txt` | `test_seed_file_has_twelve_rooms` |
| Чекбоксы аудиторий | `views/main_window.py` | smoke-проверка GUI |
| Все выбраны по умолчанию | `MainWindow.set_streams` | smoke-проверка GUI |
| Запуск отдельных окон | `views/stream_window.py`, `controllers/main_controller.py` | ручная проверка |
| Раскладка по мониторам | `layout.py` | `test_layout_uses_two_screens_evenly` |
| Дополнительное окно уведомлений | `views/notification_window.py` | `test_layout_adds_notification_window_place` |
| Вывод проблем нейросетей | `MainController._on_analysis_finished` | ручная проверка + кодовая трассировка |
| MVC/blueprint | `controllers`, `views`, `services`, `blueprints` | `test_spdd_artifacts.py` |
| Версионируемые промпты | `spdd/prompts/*.md` | `test_spdd_artifacts.py` |
| Финальное подтверждение аудиторий | `views/launch_review_dialog.py` | smoke-проверка GUI |
| Проверка готовности окружения | `services/healthcheck.py` | smoke-проверка GUI |
| Московское время автозапуска | `services/time_service.py` | `test_parse_launch_time`, `test_now_moscow_timezone` |

## Ограничения

- Аудиоанализатор подключен как модуль, но реальный аудиозахват из WebView требует отдельного источника аудио или настройки `ffmpeg`.
- Проверка реальных VK Call окон требует авторизации VK в WebView и доступности ссылок.
