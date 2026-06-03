# SoundChecker audio module

Модуль анализирует аудиодорожку трансляции и выводит JSON для сервера/клиента модератора. Сейчас это CLI-прототип: на вход можно передать аудио или видеофайл с аудиопотоком.

## Что проверяется

- доля тишины;
- наличие речи через Silero VAD, если пакет доступен;
- общий уровень громкости;
- клиппинг/перегруз;
- грубая оценка отношения полезного сигнала к шуму;
- спектральные признаки: энергия в речевой полосе, низкочастотный гул, высокочастотный шум, доминирующий тон.

## Установка

Требуется Python 3.10+ и `ffmpeg` в `PATH`. Базовая версия работает только с `numpy`; Silero VAD подключается опционально.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Опционально для готовой VAD-модели:

```powershell
pip install -r requirements-vad.txt
```

Если установка Silero/Torch не проходит на Python 3.13, используйте Python 3.10 или 3.11. Без Silero модуль все равно выводит JSON, но `speech_ratio` считается энергетическим fallback-методом.

## Запуск

```powershell
python -m soundchecker .\sample.mp4
```

С сохранением спектрограммы:

```powershell
python -m soundchecker .\sample.mp4 --spectrogram .\sample_spectrogram.png
```

Пример JSON:

```json
{
  "status": "critical",
  "issues": [
    {
      "code": "mostly_silence",
      "severity": "critical",
      "message": "Audio is mostly silent"
    }
  ],
  "metrics": {
    "duration_sec": 30.0,
    "sample_rate_hz": 16000,
    "rms_dbfs": -48.2,
    "peak_dbfs": -20.1,
    "silence_ratio": 0.91,
    "speech_ratio": 0.01,
    "clipping_ratio": 0.0,
    "noise_floor_dbfs": -72.3,
    "active_level_dbfs": -36.1,
    "snr_estimate_db": 36.2,
    "vad_backend": "silero_vad",
    "spectral": {
      "centroid_hz": 850.0,
      "bandwidth_hz": 1200.0,
      "low_freq_ratio": 0.12,
      "speech_band_ratio": 0.72,
      "high_freq_ratio": 0.04,
      "hum_ratio": 0.01,
      "tone_dominance_ratio": 0.08,
      "spectral_flatness": 0.11
    }
  }
}
```

Спектральные предупреждения:

- `power_hum`: выраженный гул около 50/60 Гц и гармоник;
- `high_frequency_noise`: слишком много энергии в верхних частотах, похоже на шипение;
- `muffled_or_filtered_audio`: мало энергии в речевой полосе 300-3400 Гц;
- `tonal_signal`: стабильный тон вместо речи.

## Датасеты для следующего этапа

Для первой версии свой датасет не обязателен: лучше начать с готового VAD и накопления реальных фрагментов из тестовых трансляций с ручной разметкой проблем. Когда понадобится обучение/валидация, полезны:

- AudioSet: общая разметка звуковых событий;
- MUSAN: речь, музыка и шумы для аугментации;
- DNS Challenge: шумная речь и шумы для задач шумоподавления/оценки качества;
- Common Voice Russian и Golos: русская речь;
- LibriSpeech: чистая английская речь для базовых проверок пайплайна.

## Интеграция

Сервер может вызывать модуль как процесс и читать stdout. Позже тот же анализатор можно обернуть в HTTP/gRPC без изменения ядра `soundchecker.analyzer`.
