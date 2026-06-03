# VK Video Analyzer

Модуль для анализа учебных видеотрансляций с выдачей компактного JSON или событий JSONL. Проект подготовлен в runtime-виде для встраивания в другую программу.

## Что оставлено в проекте

- `vk_video_analyzer/` — основной модуль
- `models/vk_layout_best.pt` — дообученные веса для VK-специфичных классов
- `yolo11n.pt` — базовые веса для детекции человека
- `requirements.txt` — зависимости
- `README.md` — краткая инструкция

## Установка

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Быстрый запуск через CLI

По умолчанию модуль сам подхватит:

- `yolo11n.pt` для детекции человека
- `models/vk_layout_best.pt` для layout-детекции

Пример запуска:

```powershell
python -m vk_video_analyzer.cli `
  --video "C:\videos\lecture.mp4" `
  --output "C:\videos\lecture_alert.json"
```

## Форматы вывода

- `alerts` — компактный JSON только с проблемами
- `full` — полный JSON
- `events` — итоговые события по проблемам
- `live-events` — JSONL-события по мере анализа файла

Примеры:

```powershell
python -m vk_video_analyzer.cli `
  --video "C:\videos\lecture.mp4" `
  --output "C:\videos\lecture_events.json" `
  --format events
```

```powershell
python -m vk_video_analyzer.cli `
  --video "C:\videos\lecture.mp4" `
  --output "C:\videos\lecture_live.jsonl" `
  --format live-events
```

## Использование из Python

```python
from vk_video_analyzer import AnalyzerConfig, VideoAnalyzer

analyzer = VideoAnalyzer(AnalyzerConfig())
result = analyzer.analyze(r"C:\videos\lecture.mp4")
payload = result.to_dict(output_format="alerts")
```

Или сразу в файл:

```python
from vk_video_analyzer import AnalyzerConfig, VideoAnalyzer

analyzer = VideoAnalyzer(AnalyzerConfig())
analyzer.analyze_to_json(
    video_path=r"C:\videos\lecture.mp4",
    output_path=r"C:\videos\lecture_alert.json",
    output_format="alerts",
)
```

## Если нужно явно указать свои веса

```powershell
python -m vk_video_analyzer.cli `
  --video "C:\videos\lecture.mp4" `
  --output "C:\videos\lecture_alert.json" `
  --layout-weights "C:\models\vk_layout_best.pt"
```

## Что анализирует модуль

- преподаватель в кадре
- демонстрация экрана
- стартовая и длительная аватарка
- пустая аудитория или рабочее место
- черный экран
- зависание кадра
- низкое качество изображения
- события возникновения и устранения проблемы
