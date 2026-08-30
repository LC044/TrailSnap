---
title: Desktop AI extension
description: Add face recognition, OCR, classification, semantic search, and local LLM capabilities to the TrailSnap desktop app.
---

# Desktop AI extension

TrailSnap ships its desktop AI runtime separately from the base installer. Users who do not need AI avoid a large download, while AI users install one platform-specific extension on demand.

::: info Docker users
The Docker AI service is managed by `docker-compose.yml`; do not install this desktop extension. This guide only applies to the Windows, macOS, and Linux desktop apps.
:::

## Included capabilities

- Face detection, recognition, and clustering
- OCR and ticket recognition
- Image classification and smart tags
- Image embeddings and semantic search
- Local multimodal LLM support (also requires `llama-server`)

The AI sidecar starts only when a related feature is used and stops after it has been idle.

## Online installation

1. Install and start the TrailSnap desktop app.
2. Open **Settings → AI Extensions**.
3. Select the extension for the current platform and click **Download and install**.
4. Keep the app open while the package is downloaded, verified, and installed.
5. Confirm that the extension shows **Installed** before starting an AI analysis task.

## Offline import

1. Open the [latest GitHub Release](https://github.com/LC044/TrailSnap/releases/latest).
2. Download the `TrailSnap-AI` `.tar.gz` for your platform: `win32-x64`, `darwin-arm64`, or `linux-x64`.
3. Do not extract or modify the archive.
4. In **Settings → AI Extensions**, click **Offline import** and select it.
5. TrailSnap verifies the manifest, platform, and checksum before installing it.

::: warning Match the platform
The extension contains native executables and cannot be shared across operating systems or CPU architectures. Only use packages from the official TrailSnap GitHub Release.
:::

## Local LLM and llama.cpp

Face, OCR, classification, and semantic search do not require `llama-server`. It is only needed for the bundled MiniCPM local multimodal model.

- Windows: use **One-click install**. TrailSnap downloads and verifies the runtime directly from the official llama.cpp GitHub Release; winget is not required.
- macOS: use **One-click install** (Homebrew is required).
- Linux: install or compile `llama-server`, add it to `PATH`, and restart TrailSnap.

```bash
brew install llama.cpp
```

## Extension vs. model connection

The desktop extension provides local face, OCR, and embedding runtimes. Model connections under AI Settings configure OpenAI-compatible, Ollama, and other services for chat or image understanding. They can be used independently. See [AI model settings](/en/docs/guide/settings/aisetting).

## Troubleshooting

- **Download or catalog failure:** verify GitHub access, refresh the catalog, or import the package offline.
- **AI unavailable after installation:** confirm the Installed state, restart TrailSnap, and inspect `logs/ai.log` and `logs/ai.err.log` in the app data directory.
- **Updates and removal:** uninstall or reinstall from the extension page. TrailSnap stops the running AI sidecar before changing the extension.
