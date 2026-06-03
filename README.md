# Translazia FDO Client

Desktop-client for monitoring online evening classes of the Faculty of Distance Education. The application receives the current schedule from the VK bot `V505_Control`, opens selected VK Call broadcasts in separate windows, arranges them across available monitors, and checks each stream with video/audio analysis modules.

## Main Features

- VK Web authorization with saved local session, so the account does not need to log in again after each restart.
- Automatic request of today's online broadcast schedule from the `V505_Control` bot on startup, after successful authorization, and by the refresh button.
- Matching bot schedule with classroom VK Call links from the local seed file.
- Opening 2-12 classroom broadcasts in equal screen areas, with a fixed notification panel on the right.
- Automatic VK Call join attempts, page reload, and retry when VK shows call errors or the stream does not connect.
- Multi-window mode and single-room focus mode with carousel navigation between classrooms.
- Per-window sound toggle and global sound toggle in the notification panel.
- Compact notification log with colored event types: audio, video, connection, waiting, mixed issues, and normal state.
- Neural checks only for active/open stream windows. A closed room is treated as a finished class.
- First stream check after launch; if no video/audio is detected before the lesson starts, the client writes that the class has not started and does not spam repeated alerts until video appears.
- Results/captures cleanup on app start, app close, and by timer.

## Architecture

The project is organized according to MVC principles and uses a blueprint-style application bootstrap.

```text
translazia_client/
  app.py                  Application entry point
  blueprints/             Desktop blueprint wiring
  controllers/            Main application orchestration and UI logic
  views/                  PySide6 windows and dialogs
  services/               Schedule, VK, capture, logging, cleanup, health checks
  models.py               Domain models
  analysis.py             Video/audio analysis integration
  assets/                 App logo and icons
spdd/                     SPDD artifacts and structured prompts
tests/                    Unit and behavior tests
vendor/                   External analysis modules
```

The SPDD materials are stored in `spdd/`: requirements, REASONS Canvas, generated prompts, verification notes, test scenarios, and conclusion.

## Requirements

- Windows 10/11.
- Python 3.11 recommended.
- VK account with access to the `V505_Control` bot dialog.
- Installed dependencies from `requirements.txt`.
- `ffmpeg` is required for reliable audio checks. Either add `ffmpeg.exe` to `PATH` or set the `FFMPEG_BINARY` environment variable.

## Installation

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

If the virtual environment already exists, just activate it and update dependencies:

```powershell
.\venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```powershell
.\venv\Scripts\python.exe run_client.py
```

You can also run:

```powershell
.\start_client.bat
```

## VK Authorization And Schedule

1. Start the application.
2. Open `VK вход`.
3. Log in to VK in the embedded browser.
4. The session is saved locally in the client profile.
5. The client automatically requests today's online broadcast schedule from `V505_Control`.

The app requests the current schedule instead of reusing stale messages from previous days. If the bot is slow, the client waits between retry attempts to avoid message spam.

## Stream Monitoring

After clicking `Запустить трансляции`, the client opens all selected classrooms and arranges windows automatically. The notification panel remains fixed on the right side of the screen.

During monitoring:

- If a room is closed manually, it is removed from active checks.
- If a stream page fails to connect, the page is reloaded and the client attempts to join again.
- If the lesson has not started, the notification panel shows a single waiting message.
- When video appears, the client reports that the lesson started.
- Audio and video issues are logged with different colors.

## Tests

Run all tests:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Runtime Data

Runtime files are created locally:

- logs: `translazia_client/data/logs/`
- captures/results: configured output directory, usually under `translazia_client/data/captures/`
- VK session/profile data: local client data directory

Do not publish local sessions, logs, captures, or generated result files to GitHub.

## Recommended Git Exclusions

Before publishing the repository, exclude local and runtime folders:

```gitignore
venv/
.idea/
__pycache__/
*.pyc
translazia_client/data/logs/
translazia_client/data/captures/
data/
```

Keep source code, tests, assets, SPDD artifacts, and `requirements.txt` in the repository.

## Repository Description

Suggested GitHub repository name:

```text
translazia-fdo-client
```

Suggested description:

```text
Desktop client for VK-based FDO online broadcast scheduling, launch, monitoring, and neural video/audio checks.
```
