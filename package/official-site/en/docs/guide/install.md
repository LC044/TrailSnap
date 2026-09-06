---
title: Installation
description: Choose between TrailSnap desktop installers and a self-hosted Docker deployment.
---

# Install TrailSnap

TrailSnap is available as a desktop app and as a self-hosted Docker stack.

| Option | Best for | Platforms | AI features |
| --- | --- | --- | --- |
| Desktop | One personal computer and the quickest setup | Windows, macOS, Linux | Install the base app first, then add the AI extension on demand |
| Docker | NAS, home server, and access from multiple devices | Any Docker Compose host | AI service is deployed with the stack; CPU, GPU, and OpenVINO modes are available |

::: tip Which should I choose?
Choose the desktop app for use on the current computer. Choose Docker when phones, tablets, and computers need to access one shared library over your LAN.
:::

## Desktop app

Open the [download page](/en/download) and choose the installer for your system:

- Windows 10/11 (x64): download and run the `.exe` installer.
- macOS (Apple Silicon): download the `.dmg` and drag TrailSnap into Applications. If macOS blocks the first launch, allow it under Privacy & Security.
- Linux (x64): use `.deb` on Debian/Ubuntu, or make the `.AppImage` executable on other distributions.

The base app includes photo management and the local service without forcing a large AI runtime download. For face recognition, OCR, classification, semantic search, or a local LLM, follow the [desktop AI extension guide](/en/docs/guide/desktop-ai-extension).

After installation:

1. Start TrailSnap.
2. Add a photo directory in Settings.
3. Scan a small folder first to verify permissions and runtime behavior.
4. Install the AI extension only if you need its capabilities.

## Docker deployment

Docker runs the frontend, backend, PostgreSQL, and AI service together. Complete the [preflight checklist](/en/docs/guide/preflight) first.

Windows PowerShell:

```powershell
irm https://trailsnap.cn/install.ps1 -OutFile install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Linux / macOS / WSL2:

```bash
curl -fsSL https://trailsnap.cn/install.sh | bash
```

The installer collects the photo path, one TrailSnap access port, time zone, and AI mode; generates `.env` and `docker-compose.yml`; pulls the images; and runs health checks. Available modes are generic CPU, NVIDIA GPU (CUDA), and OpenVINO for Intel CPUs, integrated graphics, and NPUs. Browsers, apps, and the CLI all use `http://<server-ip>:3180` by default.

Common commands from the installation directory:

```bash
docker compose --env-file .env ps
docker compose --env-file .env logs -f
docker compose --env-file .env restart
docker compose --env-file .env down
```

### Switch the AI acceleration mode

Run the installer again to see the current mode and select **Switch AI mode** from the existing-installation menu. Switching preserves the database, model cache, and photo-directory mounts.

You can also switch the AI image directly from the command line:

::: code-group

```powershell [Windows PowerShell]
# NVIDIA GPU / CUDA
.\install.ps1 -Upgrade -AiMode gpu

# Generic CPU
.\install.ps1 -Upgrade -AiMode cpu

# Intel OpenVINO
.\install.ps1 -Upgrade -AiMode openvino
```

```bash [Linux / macOS / WSL2]
# NVIDIA GPU / CUDA
./install.sh --upgrade --ai-mode gpu

# Generic CPU
./install.sh --upgrade --ai-mode cpu

# Intel OpenVINO
./install.sh --upgrade --ai-mode openvino
```

:::

GPU mode requires a working NVIDIA driver and NVIDIA Container Toolkit. The installer checks them before switching. After the service starts, the installer also verifies the runtime inside the AI container: GPU mode must expose `CUDAExecutionProvider`, while OpenVINO mode must expose `OpenVINOExecutionProvider`. A failed verification does not remove data or stop the other services; the installer prints diagnostic commands and a link to this guide.

You can also verify ONNX Runtime manually:

```bash
docker compose --env-file .env exec ai python -c "import onnxruntime as ort; print(ort.get_device()); print(ort.get_available_providers())"
```

GPU mode should report `GPU` and include `CUDAExecutionProvider`. If only `AzureExecutionProvider` and `CPUExecutionProvider` are shown, the container is still using the CPU runtime. OpenVINO mode should include `OpenVINOExecutionProvider`.

For manual configuration, GPU setup, and NAS-specific steps, see the [Docker deployment guide](/en/docs/guide/docker/).

## Next steps

- [Desktop AI extension](/en/docs/guide/desktop-ai-extension)
- [AI model connections](/en/docs/guide/settings/aisetting)
- [Data, privacy, and backups](/en/docs/guide/data-safety)
- [User manual](/en/docs/guide/user)
