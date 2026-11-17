---
title: Built-in desktop AI
description: AI is included in the TrailSnap desktop application and updated with it.
---

# Built-in desktop AI

The desktop installer includes the AI runtime for faces, OCR, tickets, classification, semantic search and local language models. No separate extension installation or local service address is required.

1. Install and open TrailSnap.
2. Open Settings → Local recognition models (本地识别模型) or LLMs and captions (大模型与文案) to view model downloads. Models are downloaded as needed; waiting tasks resume when ready.
3. Update the complete application from About TrailSnap. Downloaded models and photos are preserved.

AI starts on demand and exits when idle. Local language model inference dependencies are prepared automatically. Initial model preparation requires an internet connection.

Existing users can upgrade directly. Keep existing models; there is no need to uninstall or import an AI extension. Independently deployed Docker services retain their existing configuration.

## GPU and OpenVINO acceleration

CPU is included by default. Open **Settings → Local recognition models → Inference device** to see the current device. Windows x64 supports optional NVIDIA CUDA and Intel OpenVINO packages.

1. Download a package. TrailSnap automatically selects a download mirror, reports progress, retries failures and verifies the release signature and integrity. Your current runtime stays available.
2. Select **Use this device** after downloading. OpenVINO offers CPU, GPU and NPU; compatible hardware and drivers are required.
3. TrailSnap waits for current AI requests and model downloads, then validates and switches the device. A failed validation restores CPU and shows the reason.

CUDA requires a compatible NVIDIA driver; Python, CUDA Toolkit and PyTorch do not need separate installation. Per-model providers and fallback reasons appear under model runtime details. This selection applies to recognition models, independently of local language model inference.

Updates preserve models, packages and your selection. Packages must match the application version; an incompatible package uses CPU until you download the matching version. Other desktop platforms continue using the bundled runtime.
