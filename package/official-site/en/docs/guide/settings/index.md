# Settings Guide

Open **Settings** in TrailSnap and choose a section. Some server-wide options are visible only to administrators. The current application interface uses Chinese labels, shown in parentheses below.

<span id="main-configurations"></span>

## My settings

- **Profile (个人资料)**: manage your avatar, nickname and account details.
- **Appearance and viewing (外观与浏览)**: choose the color scheme, theme and whether to load originals when opening photos. These preferences are saved automatically on the current device. A new device follows the system appearance and loads previews first; originals can still be opened manually.
- **External tool authorization (外部工具授权)**: manage [access tokens](./tokensetting.md) for MCP, CLI and other tools.

## Photos and libraries

- **Photo folders (照片文件夹)**: connect existing [photo folders](./directories.md), configure scheduled scans, recycle-bin retention and generated image quality. Scheduled scanning is off by default and uses the server time zone when enabled. New installations retain deleted photos for 30 days by default; saved settings take precedence.
- **Connect mobile app / Mobile backup**: connect the mobile app and manage backups where supported.
- **Maps and locations (地图与地点)**: configure a [map API key and offline location data](./mapsetting.md).

## Smart features

- **Local recognition models (本地识别模型)**: configure the recognition service, manage face and OCR models, and adjust advanced face settings. The desktop app manages its own recognition service.
- **LLMs and captions (大模型与文案)**: manage [LLM connections](./aisetting.md), default models and prompts. Administrators can also schedule caption generation.

## Administration and maintenance

- **Members and registration (成员与注册)**: administrators manage members and self-registration.
- **Background tasks (后台任务)**: inspect progress, failures and processing performance.
- **Advanced maintenance (高级维护)**: maintain the index, run performance tests, or import and export the current account's configuration. Exports may contain secrets; they do not include photos or server-wide settings.

<span id="configuration-files"></span>

Device preferences, account settings and server-wide options have different scopes. Refer to each setting's description before changing it.
