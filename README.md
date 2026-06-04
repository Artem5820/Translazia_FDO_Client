# VK Video Analyzer

Инструмент для анализа записей видеоуроков и VK-трансляций.  
Модуль проходит по видео, определяет состояние трансляции и сохраняет результат в JSON или JSONL для дальнейшей обработки в сервисе или интерфейсе.

## Для чего нужен

Проект помогает автоматически находить проблемные участки в записи, например:

- преподаватель пропал из кадра
- вместо видео долго показывается аватар
- идёт демонстрация экрана
- в кадре пустая аудитория или рабочее место
- экран стал чёрным
- кадр завис
- качество изображения слишком низкое

На выходе можно получить как компактный список проблем, так и подробную структуру с сегментами, событиями и покадровыми наблюдениями.

## Что внутри

```text
vk_video_analyzer/        основной модуль анализатора
models/                   локальные веса layout-модели
requirements.txt          зависимости проекта
README.md                 описание проекта
```

## Стек

- Python
- OpenCV
- NumPy
- Ultralytics YOLO

## Установка

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Подготовка моделей

По умолчанию проект использует локальные веса:

- `yolo11n.pt` в корне проекта
- `models/vk_layout_best.pt` внутри папки `models`

Если эти файлы лежат в других местах, их можно передать через аргументы CLI.

## Быстрый запуск

```powershell
python -m vk_video_analyzer.cli `
  --video "C:\videos\lecture.mp4" `
  --output "C:\videos\lecture_alert.json"
```

## Форматы результата

- `alerts` - компактный JSON только с проблемами
- `full` - полный JSON с наблюдениями и сегментами
- `events` - итоговые события по найденным проблемам
- `live-events` - потоковый JSONL во время анализа

Пример сохранения событий:

```powershell
python -m vk_video_analyzer.cli `
  --video "C:\videos\lecture.mp4" `
  --output "C:\videos\lecture_events.json" `
  --format events
```

Пример потокового вывода:

```powershell
python -m vk_video_analyzer.cli `
  --video "C:\videos\lecture.mp4" `
  --output "C:\videos\lecture_live.jsonl" `
  --format live-events
```

## Основные аргументы CLI

- `--video` - путь к видеофайлу
- `--output` - путь к итоговому JSON или JSONL
- `--sample-interval` - шаг анализа в секундах
- `--device` - устройство для YOLO, например `cpu` или `0`
- `--person-conf` - порог уверенности для детекции человека
- `--person-weights` - список весов для person-модели
- `--layout-weights` - путь к layout-модели
- `--mute-templates-dir` - папка с PNG-шаблонами mute-иконки
- `--format` - формат результата
- `--only-on-problem` - не сохранять файл, если проблем не найдено
- `--no-observations` - не включать покадровые наблюдения в полный JSON

Пример с явным указанием весов:

```powershell
python -m vk_video_analyzer.cli `
  --video "C:\videos\lecture.mp4" `
  --output "C:\videos\lecture_alert.json" `
  --person-weights "C:\models\yolo11n.pt" `
  --layout-weights "C:\models\vk_layout_best.pt"
```

## Использование как Python-модуля

```python
from vk_video_analyzer import AnalyzerConfig, VideoAnalyzer

analyzer = VideoAnalyzer(AnalyzerConfig())
result = analyzer.analyze(r"C:\videos\lecture.mp4")
payload = result.to_dict(output_format="alerts")
```

Сохранение результата сразу в файл:

```python
from vk_video_analyzer import AnalyzerConfig, VideoAnalyzer

analyzer = VideoAnalyzer(AnalyzerConfig())
analyzer.analyze_to_json(
    video_path=r"C:\videos\lecture.mp4",
    output_path=r"C:\videos\lecture_alert.json",
    output_format="alerts",
)
```

## Что исключено из Git

В `.gitignore` уже добавлены:

- виртуальное окружение
- `__pycache__`
- служебные папки IDE
- временные и выходные файлы
- видеофайлы
- локальные веса моделей `.pt`

Это позволит выгружать в Git только код и документацию, без тяжёлых бинарников и мусора.

## Первая загрузка в Git

Если репозиторий ещё не инициализирован локально:

```powershell
git init
git add .
git commit -m "Initial commit"
```

Дальше можно привязать удалённый репозиторий и отправить код:

```powershell
git remote add origin <URL_РЕПОЗИТОРИЯ>
git branch -M main
git push -u origin main
```
