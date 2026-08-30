# AI Service Design

The AI service hosts TrailSnap AI capabilities (e.g. OCR, face recognition, scene classification, image analysis). The backend task system calls it when needed.

## How it runs

- In Docker Compose deployment, it is provided as the `trailsnap-ai` service.
- Backend calls it via the internal network by default: `AI_API_URL=http://ai:8001`

## LLM Hosting

The AI service supports local LLM hosting and proxy capabilities:

- Supports running LLM services via natively compiled llama-server binary from llama.cpp
- Supports custom model paths, service ports, and idle timeouts
- Automatically handles model download, service start/stop, and idle resource recovery
- Provides OpenAI-format LLM proxy routes, transparently forwarding requests to the local llama.cpp service

The multimodal model uses MiniCPM-V-4_6-Q4_K_M, supporting image content understanding, tag generation, and other visual tasks.

## llama.cpp Installation

Using the built-in AI connection requires llama.cpp to be installed.

### Windows

```bash
# Install via winget
winget install llama.cpp

# Or download manually: https://github.com/ggerganov/llama.cpp/releases
```

### Linux

```bash
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
mkdir build && cd build
cmake .. -DLLAMA_CURL=ON
cmake --build . --config Release
sudo cp llama-server /usr/local/bin/
```

### macOS

```bash
brew install llama.cpp
```

## Common endpoints

- Source-development Swagger docs: `http://localhost:8001/docs`. In production Compose, AI stays private and has no user-facing port.

## Troubleshooting

- AI service not reachable: check `AI_API_URL` and Docker networking.
- Tasks not progressing: check task status/errors in **Settings → Task Management**.
- LLM task failed: confirm llama.cpp is installed and the `llama-server` command is available.
