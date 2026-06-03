# SPDD Prompt 007: VK Web Authorization

## Requirements
- Show VK authorization state on the main startup screen.
- Open V505_Control in an embedded VK window: `https://vk.com/im/convo/-236401821?entrypoint=list_all`.
- Persist VK account authorization so the operator does not re-enter login and password every launch.
- Keep MVC and blueprint boundaries: UI in views, orchestration in controller, persistence/auth helpers in services.

## Entities
- `SourceSettings.vk_bot_url`: VK conversation URL for V505_Control.
- `SourceSettings.vk_web_command`: menu command/button text, default `5-Онлайн трансляции`.
- `VkAuthWindow`: embedded browser window for VK login and bot interaction.
- `VkAuthChecker`: service that detects persistent VK session cookies.

## Approach
- Configure `QWebEngineProfile.defaultProfile()` with persistent storage and cache under `data/`.
- Detect authorization from VK session cookies instead of asking for password inside application settings.
- Add a clear `VK` status card and a `VK вход` action in the main window.

## Structure
- `services/vk_web_profile.py`: persistent WebEngine profile.
- `services/vk_auth_service.py`: VK cookie session detection.
- `views/vk_auth_window.py`: embedded browser for login and V505_Control.
- `controllers/main_controller.py`: connect UI actions, check status at startup and after closing VK window.

## Operations
- On application start: configure persistent WebEngine profile, then check VK auth state.
- On `VK вход`: open V505_Control in the embedded browser.
- On `Проверить вход`: reload cookie status and update the main screen.

## Norms
- Do not store VK password in settings.
- Keep all VK session files in application data folders.
- Preserve existing file/API schedule loaders.

## Safeguards
- If VK is not authorized, show a warning event in the notifications window.
- Keep the current file schedule fallback working while VK Web schedule extraction is being developed.
