# Prompt v002 - MVC, blueprint и окно уведомлений

## Причина изменения

После первой генерации основной файл клиента стал слишком большим. Требуется привести приложение к MVC/blueprint-подходу и добавить отдельное окно уведомлений и ошибок.

## REASONS

### Requirements

- Разделить код по папкам `controllers`, `views`, `services`, `blueprints`, `ui`.
- Оставить `app.py` минимальной точкой входа.
- Добавить окно `Уведомления и ошибки`.
- При запуске трансляций всегда добавлять это окно к сетке окон.
- Если нейросеть нашла проблему, выводить ее в основном клиенте и в отдельном окне уведомлений.

### Entities

- `MainController`
- `MainWindow`
- `StreamWindow`
- `NotificationWindow`
- `StreamCaptureSession`
- `DesktopBlueprint`
- `AnalysisSummary`

### Approach

Перенести UI в `views`, сценарии в `controllers`, операции захвата и загрузки расписания в `services`. `DesktopBlueprint` должен создавать и показывать контроллер. Раскладка окон должна рассчитываться для `N + 1`.

### Structure

```text
translazia_client/
  app.py
  blueprints/desktop.py
  controllers/main_controller.py
  controllers/bridge.py
  services/capture.py
  services/schedule_service.py
  views/main_window.py
  views/stream_window.py
  views/settings_dialog.py
  views/notification_window.py
  ui/styles.py
```

### Operations

1. Создать новые пакеты.
2. Перенести классы из старого `app.py`.
3. Обновить импорты.
4. Добавить вывод ошибок и проблем в `NotificationWindow`.
5. Добавить тест, что раскладка поддерживает дополнительное окно.
6. Проверить запуск GUI без открытия реальных трансляций.

### Norms

- UI-классы не должны содержать бизнес-логику.
- Контроллеры должны связывать сигналы и сервисы.
- Сообщения пользователю писать на русском языке.
- Тесты должны быть быстрыми и не открывать реальные VK-окна.

### Safeguards

- Не удалять подключенные нейросетевые модули.
- Не менять формат seed-файла.
- Не запускать анализ в UI-потоке.
- Не скрывать ошибки анализа.
